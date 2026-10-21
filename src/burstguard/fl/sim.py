"""Chạy FL bằng Flower Simulation Engine (Ray) trong cùng môi trường ảo."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


WORKER_RSS_GIB = 1.4   # đo được ~1,3 GiB/worker Ray (torch + transformers + TTM + dữ liệu site)
RESERVED_GIB = 2.5     # chừa cho driver/server + hệ điều hành + dịch vụ khác


def _mem_available_gib() -> float | None:
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1024 / 1024
    except Exception:
        return None
    return None


def auto_cpus(cfg: dict[str, Any]) -> int:
    """Số CPU giao cho Ray. 0 = tự động: min(CPU khả dụng - 1, số worker vừa với RAM còn trống)."""
    n = int(cfg["sim"]["num_cpus"])
    if n > 0:
        return n
    try:
        avail = len(os.sched_getaffinity(0))
    except Exception:
        avail = os.cpu_count() or 2
    by_cpu = max(1, avail - 1)  # chừa 1 CPU cho hệ thống / dịch vụ khác
    mem = _mem_available_gib()
    cpc = float(cfg["sim"]["cpus_per_client"])
    if mem is None:
        return by_cpu
    by_mem = max(1, int((mem - RESERVED_GIB) / WORKER_RSS_GIB * cpc))
    return max(1, min(by_cpu, by_mem))


def run_fl(cfg: dict[str, Any], run_dir: Path, log=print) -> dict[str, Any]:
    from flwr.simulation import run_simulation

    from burstguard.fl.client import make_client_app
    from burstguard.fl.server import make_server_app

    n_sites = int(cfg["data"]["num_sites"])
    ncpu = auto_cpus(cfg)
    cpc = float(cfg["sim"]["cpus_per_client"])
    init_args: dict[str, Any] = {"num_cpus": ncpu, "include_dashboard": False, "log_to_driver": True}
    if cfg["sim"].get("ray_temp_dir"):
        init_args["_temp_dir"] = str(cfg["sim"]["ray_temp_dir"])
    backend = {"client_resources": {"num_cpus": cpc, "num_gpus": 0.0}, "init_args": init_args}
    mem = _mem_available_gib()
    log(f"Ray: num_cpus={ncpu}, cpus_per_client={cpc} -> tối đa {int(ncpu // cpc)} client song song; "
        f"{n_sites} SuperNode ảo; RAM trống {mem:.1f} GiB (ước ~{WORKER_RSS_GIB} GiB/worker)"
        if mem is not None else f"Ray: num_cpus={ncpu}, cpus_per_client={cpc}; {n_sites} SuperNode ảo")
    server_app, info = make_server_app(cfg, run_dir)  # nạp mô hình 1 lần -> trọng số nằm trong cache HF
    if cfg["model"]["source"] == "hf":
        # Worker Ray thừa hưởng biến môi trường: đọc từ cache, không gọi mạng 20 lần song song
        os.environ["HF_HUB_OFFLINE"] = "1"
    client_app = make_client_app(cfg)
    t0 = time.time()
    run_simulation(server_app=server_app, client_app=client_app, num_supernodes=n_sites,
                   backend_config=backend)
    wall = time.time() - t0
    if not (run_dir / "server_finished").exists():
        raise RuntimeError("ServerApp không hoàn tất (xem traceback phía trên trong console.log). "
                           "Nguyên nhân hay gặp: client lỗi, thiếu RAM cho Ray, hoặc mô hình/dữ liệu không nạp được.")
    return summarize(run_dir, wall)


def summarize(run_dir: Path, wall: float | None = None) -> dict[str, Any]:
    rounds, evals = [], []
    p = run_dir / "metrics.jsonl"
    if p.exists():
        for line in p.read_text().splitlines():
            r = json.loads(line)
            if r["kind"] == "round":
                rounds.append(r)
            elif r["kind"] == "eval":
                evals.append(r)
    final = {}
    for e in evals:
        final[e["split"]] = {k: e.get(k) for k in ("round", "mase_daily_mean", "mase_daily_median",
                                                   "mase_weekly_mean", "mae_mean", "smape_mean")}
    first_eval = next((e for e in evals if e["round"] == 0), None)
    return {"wall_s": round(wall, 1) if wall else None, "rounds_done": len(rounds),
            "round_wall_s_mean": round(sum(r["round_wall_s"] for r in rounds) / len(rounds), 2) if rounds else None,
            "update_bytes_per_client": rounds[-1]["update_bytes_per_client"] if rounds else None,
            "initial": {k: first_eval.get(k) for k in ("split", "mase_daily_mean")} if first_eval else None,
            "final": final}
