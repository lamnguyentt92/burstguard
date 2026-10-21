"""ClientApp: mỗi SuperNode là một site biên, giữ dữ liệu cục bộ và fine-tune TTM.

Dùng lối "legacy" (NumPyClient) của Flower vì SecAgg+ (bản v0.2) chỉ chạy với LegacyContext.
Trạng thái (mô hình, cửa sổ, cache head) được giữ trong bộ nhớ của tiến trình worker giữa các vòng.
"""
from __future__ import annotations

import copy
import os
import time
import traceback
from typing import Any

import numpy as np

_BASE: dict[str, Any] = {}    # mô hình gốc đã nạp (mỗi tiến trình một bản)
_SITES: dict[int, dict] = {}  # trạng thái theo partition-id


def _base_model(cfg):
    from burstguard.model import load_model
    key = (cfg["model"]["source"], cfg["model"]["path"], cfg["model"]["revision"],
           cfg["data"]["context"], cfg["data"]["horizon"])
    if key not in _BASE:
        _BASE.clear()
        _BASE[key] = load_model(cfg, seed=int(cfg["run"]["seed"]))[0]
    return _BASE[key]


def _site_state(pid: int, cfg: dict[str, Any]) -> dict:
    if pid in _SITES:
        return _SITES[pid]
    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg, site_windows
    t0 = time.time()
    ds = dataset_from_cfg(cfg)
    X, Y, _ = site_windows(ds, pid, "train", cfg, seed=int(cfg["run"]["seed"]))
    if len(X) == 0:
        raise RuntimeError(f"Site {pid}: không có cửa sổ train")
    model = M.configure_peft(copy.deepcopy(_base_model(cfg)), cfg)
    cache = None
    if cfg["train"]["peft"] == "head" and cfg["train"]["head_cache"]:
        rel = M.check_head_cache(model, X, int(cfg["data"]["horizon"]), cfg["model"]["freq"])
        if rel < 1e-3:
            cache = M.build_head_cache(model, X, freq=cfg["model"]["freq"])
        else:
            print(f"[client {pid}] CẢNH BÁO: head cache lệch {rel:.2e} so với forward đầy đủ -> tắt cache", flush=True)
    _SITES[pid] = {"model": model, "X": X, "Y": Y, "scale": ds.site_scale(pid), "cache": cache,
                   "setup_s": time.time() - t0}
    return _SITES[pid]


def make_client_app(cfg: dict[str, Any]):
    import torch
    from flwr.client import ClientApp, NumPyClient

    from burstguard import model as M
    from burstguard.train import local_train

    class SiteClient(NumPyClient):
        def __init__(self, pid: int):
            self.pid = pid

        def get_parameters(self, config):
            return M.get_trainable(_site_state(self.pid, cfg)["model"])

        def fit(self, parameters, config):
            try:
                st = _site_state(self.pid, cfg)
                M.set_trainable(st["model"], parameters)
                rnd = int(config.get("server_round", 0))
                seed = int(cfg["run"]["seed"]) * 100003 + rnd * 101 + self.pid
                torch.manual_seed(seed)
                stats = local_train(st["model"], st["X"], st["Y"], st["scale"], cfg, seed=seed, cache=st["cache"])
                out = M.get_trainable(st["model"])
                metrics = {"pid": self.pid, "train_loss": float(stats["train_loss"]),
                           "train_cpu_s": float(stats["train_cpu_s"]), "n_windows": int(len(st["X"])),
                           "worker_pid": os.getpid(), "setup_s": float(st["setup_s"])}
                return out, int(len(st["X"])), metrics
            except Exception:
                # In traceback ra log của worker để collect_logs bắt được, rồi ném lại cho Flower
                print(f"[client {self.pid}] LỖI trong fit:\n{traceback.format_exc()}", flush=True)
                raise

    def client_fn(context):
        torch.set_num_threads(int(cfg["sim"]["torch_threads"]))
        pid = int(context.node_config["partition-id"])
        return SiteClient(pid).to_client()

    return ClientApp(client_fn=client_fn)
