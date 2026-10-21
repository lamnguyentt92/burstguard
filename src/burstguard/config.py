"""Cấu hình TOML: giá trị mặc định + file cấu hình + ghi đè từ dòng lệnh (--set a.b=c)."""
from __future__ import annotations

import copy
import tomllib
from pathlib import Path
from typing import Any

from burstguard.paths import resolve

DEFAULTS: dict[str, Any] = {
    "run": {"name": "run", "seed": 0},
    "data": {
        "path": "data/processed/milan.npz",
        "num_sites": 20,        # dùng N site đầu tiên trong file dữ liệu
        "context": 512,         # độ dài ngữ cảnh (điểm, 10 phút/điểm) — phải khớp mô hình
        "horizon": 36,          # 36 bước = 6 giờ
        "train_stride": 3,
        "eval_stride": 6,
        "max_train_windows": 0, # 0 = không giới hạn (dùng để chạy thử nhanh)
        "max_eval_windows": 0,
    },
    "model": {
        "source": "hf",         # hf | local | random
        "path": "ibm-granite/granite-timeseries-ttm-r2",
        "revision": "auto",     # auto = để get_model chọn; hoặc tên nhánh, vd "main" (512-96-r2)
        "random_size": "small", # small (~1,1M tham số, dùng khi source=random)
        "freq": "10min",        # cho các biến thể TTM có freq-prefix (…-ft-r2.1)
    },
    "train": {
        "peft": "head",         # head | decoder | lora | full
        "lora_r": 8,
        "lora_alpha": 16,
        "lr": 1e-3,
        "batch_size": 64,
        "local_epochs": 1,
        "weight_decay": 0.0,
        "head_cache": True,     # head-only: tính sẵn đầu ra decoder (nhanh hơn rất nhiều)
    },
    "fl": {
        "rounds": 30,
        "fraction_fit": 1.0,
        "eval_every": 5,
        "eval_split": "val",    # đánh giá theo vòng trên split này; cuối cùng luôn đánh giá test
    },
    "sim": {
        "num_cpus": 0,          # 0 = tự động (số CPU khả dụng - 1, tối thiểu 1)
        "cpus_per_client": 1,
        "torch_threads": 1,
        "ray_temp_dir": "",     # rỗng = mặc định của Ray (/tmp/ray)
    },
}


def deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _parse_value(s: str) -> Any:
    try:
        return tomllib.loads(f"v = {s}")["v"]
    except Exception:
        return s  # chuỗi trần


def load_config(path: str | None = None, overrides: list[str] | None = None) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        p = resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"Không thấy file cấu hình: {p}")
        with open(p, "rb") as f:
            deep_update(cfg, tomllib.load(f))
        cfg["_config_file"] = str(p)
    for ov in overrides or []:
        if "=" not in ov:
            raise ValueError(f"--set cần dạng khoá.con=giá_trị, nhận được: {ov!r}")
        key, val = ov.split("=", 1)
        node = cfg
        parts = key.strip().split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = _parse_value(val.strip())
    validate(cfg)
    return cfg


def validate(cfg: dict[str, Any]) -> None:
    t = cfg["train"]["peft"]
    if t not in {"head", "decoder", "lora", "full"}:
        raise ValueError(f"train.peft phải là head|decoder|lora|full, nhận {t!r}")
    s = cfg["model"]["source"]
    if s not in {"hf", "local", "random"}:
        raise ValueError(f"model.source phải là hf|local|random, nhận {s!r}")
    if cfg["data"]["horizon"] >= 144:
        raise ValueError("data.horizon phải < 144 (baseline seasonal-naive theo ngày cần h < 144)")
    if cfg["fl"]["rounds"] < 1:
        raise ValueError("fl.rounds phải >= 1")


def dump_toml(cfg: dict[str, Any]) -> str:
    """Ghi cấu hình ra TOML đơn giản (đủ cho các kiểu dùng trong dự án)."""
    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, list):
            return "[" + ", ".join(fmt(x) for x in v) + "]"
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = []
    for sec, body in cfg.items():
        if sec.startswith("_") or not isinstance(body, dict):
            continue
        lines.append(f"[{sec}]")
        for k, v in body.items():
            if not isinstance(v, dict):
                lines.append(f"{k} = {fmt(v)}")
        lines.append("")
    return "\n".join(lines)
