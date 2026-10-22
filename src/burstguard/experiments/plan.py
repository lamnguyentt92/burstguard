"""Time planning for the experiment campaign: fit a per-round cost model on finished jobs, estimate what is left.

Cost model for one FL job (seconds):  rounds * (c[peft, kind] + s_bg * units * [BurstGuard on])
  c[peft, kind]  median wall_s / rounds of finished jobs without BurstGuard (per fine-tuning mode and job kind)
  s_bg           median extra seconds per screened unit and round (units = secagg groups, else 1)
Missing values fall back to measured ratios between modes (from `burstguard model-check` on a vm with 8 vCPU)
and finally to priors; the output says which values were measured.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from burstguard.experiments import grid as G

# priors: seconds per round on an 8-vCPU VM with 4 workers (rough, replaced by measurements)
PRIOR_C = {"head": 8.0, "decoder": 30.0, "lora": 45.0, "full": 45.0}
PRIOR_BG = 20.0             # seconds per screened unit and round (4 threads)
RATIO = {"head": 0.2, "decoder": 0.65, "lora": 1.0, "full": 1.0}   # relative to lora (model-check CPU times)
KIND_FACTOR = {"fl": 1.0, "local_only": 1.0, "centralized": 1.1, "zeroshot": 0.0}
ZEROSHOT_S = 120.0

TIERS = {
    "pilot": ["P0_pilot"],
    "calibration": ["E0_calibration"],
    "1": ["E1_clean", "E2_attacks", "E3_defenses", "E7_secagg", "E9_ablation"],
    "2": ["E4_sensitivity", "E5_lifespan", "E6_adaptive"],
    "system": ["E8_system"],
}


def _features(ov: dict[str, Any], kind: str) -> dict[str, Any]:
    bg = "burstguard" in str(ov.get("defense.name", "")) or "burstguard" in str(ov.get("defense.addons", ""))
    units = int(ov.get("secagg.groups", 1)) if ov.get("secagg.enabled") and int(ov.get("secagg.groups", 1)) > 1 else 1
    return {"peft": ov.get("train.peft", "head"), "kind": kind, "rounds": int(ov.get("fl.rounds", 30)),
            "bg": bg, "units": units, "engine": ov.get("engine.name", "local")}


def collect_finished(results_root: Path) -> list[dict[str, Any]]:
    out = []
    for rj in results_root.glob("*/*/result.json"):
        try:
            r = json.loads(rj.read_text())
        except Exception:
            continue
        if r.get("status") != "success" or not r.get("wall_s"):
            continue
        f = _features(r.get("overrides", {}), r.get("kind", "fl"))
        if "_quick" in rj.parent.parent.name:
            continue
        out.append({**f, "wall_s": float(r["wall_s"]), "grid": rj.parent.parent.name})
    return out


def fit(finished: list[dict[str, Any]]) -> dict[str, Any]:
    model: dict[str, Any] = {"c": {}, "c_src": {}, "s_bg": PRIOR_BG, "s_bg_src": "prior", "zeroshot": ZEROSHOT_S}
    per: dict[tuple, list[float]] = {}
    for j in finished:
        if j["kind"] == "zeroshot" or j["bg"] or j["engine"] != "local":
            continue
        per.setdefault((j["peft"], j["kind"]), []).append(j["wall_s"] / max(j["rounds"], 1))
    for key, v in per.items():
        model["c"][key] = float(np.median(v)); model["c_src"][key] = f"measured (n={len(v)})"
    zs = [j["wall_s"] for j in finished if j["kind"] == "zeroshot"]
    if zs:
        model["zeroshot"] = float(np.median(zs))
    extra = []
    for j in finished:
        if j["bg"] and j["kind"] == "fl" and j["engine"] == "local":
            base = cost_per_round(model, j["peft"], "fl")
            extra.append((j["wall_s"] / max(j["rounds"], 1) - base) / max(j["units"], 1))
    if extra:
        model["s_bg"] = max(1.0, float(np.median(extra))); model["s_bg_src"] = f"measured (n={len(extra)})"
    return model


def cost_per_round(model: dict[str, Any], peft: str, kind: str) -> float:
    c = model["c"]
    if (peft, kind) in c:
        return c[(peft, kind)]
    if (peft, "fl") in c:
        return c[(peft, "fl")] * KIND_FACTOR.get(kind, 1.0)
    # scale from a measured mode via the model-check ratios (prefer compute-bound modes: head rounds are
    # dominated by evaluation overhead and scale poorly)
    for p2 in ("lora", "full", "decoder", "head"):
        if (p2, "fl") in c:
            return c[(p2, "fl")] / RATIO.get(p2, 1.0) * RATIO.get(peft, 1.0) * KIND_FACTOR.get(kind, 1.0)
    return PRIOR_C.get(peft, 45.0) * KIND_FACTOR.get(kind, 1.0)


def job_seconds(model: dict[str, Any], ov: dict[str, Any], kind: str) -> float:
    f = _features(ov, kind)
    if kind == "zeroshot":
        return model["zeroshot"]
    s = f["rounds"] * cost_per_round(model, f["peft"], kind)
    if f["bg"]:
        s += f["rounds"] * model["s_bg"] * f["units"]
    if f["engine"] == "flower":
        s *= 1.5
    return s


def plan(grid_files: list[Path], n_shards: int = 5, log=print) -> dict[str, Any]:
    from burstguard import VERSION_TAG
    from burstguard.paths import RESULTS_DIR
    root = RESULTS_DIR / VERSION_TAG
    finished = collect_finished(root) if root.exists() else []
    model = fit(finished)
    log(f"cost model from {len(finished)} finished jobs in {root}:")
    for peft in ("head", "decoder", "lora", "full"):
        src = model["c_src"].get((peft, "fl"), "derived" if model["c"] else "prior")
        log(f"  {peft:8s} FL round: {cost_per_round(model, peft, 'fl'):7.1f} s   [{src}]")
    log(f"  BurstGuard: {model['s_bg']:.1f} s per screened unit and round   [{model['s_bg_src']}]")
    out = {"model": {"s_bg": model["s_bg"], "c": {f"{k[0]}/{k[1]}": v for k, v in model["c"].items()}},
           "grids": [], "n_shards": n_shards}
    tot_left = 0.0
    shard_left = [0.0] * n_shards
    log(f"\n{'grid':18s} {'jobs':>5s} {'done':>5s} {'fail':>5s} {'left_h(1 VM)':>13s} "
        f"{'per-shard h (max of ' + str(n_shards) + ')':>24s}")
    for gf in grid_files:
        g = G.load_grid(gf)
        jobs = G.expand(g)
        gdir = G.grid_dir(g)
        done = fail = 0
        left = 0.0
        per_shard = [0.0] * n_shards
        for k in range(1, n_shards + 1):
            for j in G.shard(jobs, k, n_shards):
                st = G.job_status(gdir / j["id"])
                if st == "success":
                    done += 1
                    continue
                fail += st == "failed"
                sec = job_seconds(model, j["overrides"], j["kind"])
                left += sec
                per_shard[k - 1] += sec
        for i in range(n_shards):
            shard_left[i] += per_shard[i]
        tot_left += left
        out["grids"].append({"grid": g["grid"]["name"], "jobs": len(jobs), "done": done, "failed": fail,
                             "left_hours_1vm": round(left / 3600, 1),
                             "left_hours_per_shard": [round(x / 3600, 1) for x in per_shard]})
        log(f"{g['grid']['name']:18s} {len(jobs):5d} {done:5d} {fail:5d} {left / 3600:13.1f} "
            f"{max(per_shard) / 3600:24.1f}")
    out["total_left_hours_1vm"] = round(tot_left / 3600, 1)
    out["wall_hours_if_sharded"] = round(max(shard_left) / 3600, 1) if shard_left else 0.0
    log(f"{'TOTAL':18s} {'':5s} {'':5s} {'':5s} {tot_left / 3600:13.1f} {max(shard_left) / 3600:24.1f}")
    log(f"\n=> about {out['wall_hours_if_sharded']:.0f} h wall time with {n_shards} VMs running these grids in sequence "
        f"(each VM its own shard).")
    return out
