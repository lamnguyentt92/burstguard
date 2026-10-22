"""Time planning for the experiment campaign: fit a per-round cost model on finished jobs, estimate what is left.

Cost model for one FL job (seconds on a weight-4 machine, i.e. 8 vCPU with 4 workers):

    rounds * ( c[peft, kind] * a[attacked] + s_bg * units * effort * [BurstGuard on] )

  c[peft, kind]  median wall_s / rounds of finished clean jobs without BurstGuard (per fine-tuning mode, job kind)
  a              median slow-down of attacked jobs (malicious clients train attack.local_epochs: stragglers)
  s_bg           median extra seconds per screened unit and round at the default search effort
  units          screened units per round: secagg groups, or 1 + (attacked rounds share) * regroup_groups when a
                 flagged aggregate is re-screened in groups (enforce mode, on_flag = regroup)
  effort         search effort relative to the default (probe windows x restarts x directions x steps)
Missing values fall back to measured ratios between modes and finally to priors (P0 pilot of v0.3.2, vm-e);
the output says which values were measured. Job features come from the resolved configuration ("effective"),
so keys that only the base config sets (fl.rounds, attack.local_epochs, ...) are taken into account.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np

from burstguard.experiments import grid as G

# priors: seconds per round on an 8-vCPU VM with 4 workers (P0 v0.3.2 on vm-e; replaced by measurements)
PRIOR_C = {"head": 20.0, "decoder": 45.0, "lora": 65.0, "full": 65.0}
PRIOR_BG = 12.0             # seconds per screened unit and round at the default search effort (4 threads)
PRIOR_ATTACK = 2.0          # attacked / clean round time (attack.local_epochs = 10, poison_frac = 0.5)
RATIO = {"head": 0.3, "decoder": 0.7, "lora": 1.0, "full": 1.0}   # relative to lora
KIND_FACTOR = {"fl": 1.0, "local_only": 1.0, "centralized": 1.1, "zeroshot": 0.0}
ZEROSHOT_S = 120.0
DEFAULT_EFFORT = 32 * (1 * 2 * (6 * 8 + 2) + 2)   # probe_windows 32, restarts 1, both directions, 8 steps

TIERS = {
    "pilot": ["P0_pilot"],
    "calibration": ["E0_calibration"],
    "1": ["E1_clean", "E2_attacks", "E3_defenses", "E7_secagg", "E9_ablation"],
    "2": ["E4_sensitivity", "E5_lifespan", "E6_adaptive"],
    "system": ["E8_system"],
}


def _effort(ov: dict[str, Any]) -> float:
    pw = int(ov.get("burstguard.probe_windows", 32))
    r = max(1, int(ov.get("burstguard.restarts", 1)))
    k = int(ov.get("burstguard.steps", 8))
    dirs = 2 if ov.get("burstguard.both_directions", True) else 1
    return pw * (r * dirs * (6 * k + 2) + 2) / DEFAULT_EFFORT


def _features(ov: dict[str, Any], kind: str) -> dict[str, Any]:
    bg = "burstguard" in str(ov.get("defense.name", "")) or "burstguard" in str(ov.get("defense.addons", ""))
    units = int(ov.get("secagg.groups", 1)) if ov.get("secagg.enabled") and int(ov.get("secagg.groups", 1)) > 1 else 1
    rounds = int(ov.get("fl.rounds", 20))
    attacked = ov.get("attack.type", "none") != "none"
    if (bg and units == 1 and attacked and ov.get("burstguard.mode", "enforce") != "monitor"
            and ov.get("burstguard.on_flag", "regroup") == "regroup"):
        # flagged rounds are screened again in regroup_groups groups (assume every attacked round is flagged)
        start, end = int(ov.get("attack.start_round", 1)), int(ov.get("attack.end_round", 0)) or rounds + 1
        frac = max(0, min(end - 1, rounds) - start + 1) / max(rounds, 1)
        units = 1 + frac * int(ov.get("burstguard.regroup_groups", 5))
    return {"peft": ov.get("train.peft", "head"), "kind": kind, "rounds": rounds, "attacked": attacked,
            "bg": bg, "units": units, "effort": _effort(ov) if bg else 0.0, "engine": ov.get("engine.name", "local")}


def collect_finished(results_root: Path) -> list[dict[str, Any]]:
    out = []
    for rj in results_root.glob("*/*/result.json"):
        try:
            r = json.loads(rj.read_text())
        except Exception:
            continue
        if r.get("status") != "success" or not r.get("wall_s"):
            continue
        f = _features(r.get("effective") or r.get("overrides", {}), r.get("kind", "fl"))
        if "_quick" in rj.parent.parent.name:
            continue
        out.append({**f, "wall_s": float(r["wall_s"]), "grid": rj.parent.parent.name})
    return out


def fit(finished: list[dict[str, Any]]) -> dict[str, Any]:
    model: dict[str, Any] = {"c": {}, "c_src": {}, "s_bg": PRIOR_BG, "s_bg_src": "prior", "zeroshot": ZEROSHOT_S,
                             "attack": PRIOR_ATTACK, "attack_src": "prior"}
    per: dict[tuple, list[float]] = {}
    for j in finished:
        if j["kind"] == "zeroshot" or j["bg"] or j["engine"] != "local" or j.get("attacked"):
            continue
        per.setdefault((j["peft"], j["kind"]), []).append(j["wall_s"] / max(j["rounds"], 1))
    for key, v in per.items():
        model["c"][key] = float(np.median(v)); model["c_src"][key] = f"measured (n={len(v)})"
    zs = [j["wall_s"] for j in finished if j["kind"] == "zeroshot"]
    if zs:
        model["zeroshot"] = float(np.median(zs))
    att = [j["wall_s"] / max(j["rounds"], 1) / cost_per_round(model, j["peft"], j["kind"])
           for j in finished if j.get("attacked") and not j["bg"] and j["engine"] == "local" and j["kind"] == "fl"
           and (j["peft"], "fl") in model["c"]]
    if att:
        model["attack"] = max(1.0, float(np.median(att))); model["attack_src"] = f"measured (n={len(att)})"
    extra = []
    for j in finished:
        if j["bg"] and j["kind"] == "fl" and j["engine"] == "local":
            base = cost_per_round(model, j["peft"], "fl") * (model["attack"] if j.get("attacked") else 1.0)
            extra.append((j["wall_s"] / max(j["rounds"], 1) - base) / max(j["units"] * j.get("effort", 1.0), 1e-6))
    if extra:
        model["s_bg"] = max(1.0, float(np.median(extra))); model["s_bg_src"] = f"measured (n={len(extra)})"
    return model


def cost_per_round(model: dict[str, Any], peft: str, kind: str) -> float:
    c = model["c"]
    if (peft, kind) in c:
        return c[(peft, kind)]
    if (peft, "fl") in c:
        return c[(peft, "fl")] * KIND_FACTOR.get(kind, 1.0)
    # scale from a measured mode via the ratios (prefer compute-bound modes: head rounds are dominated by
    # evaluation overhead and scale poorly)
    for p2 in ("lora", "full", "decoder", "head"):
        if (p2, "fl") in c:
            return c[(p2, "fl")] / RATIO.get(p2, 1.0) * RATIO.get(peft, 1.0) * KIND_FACTOR.get(kind, 1.0)
    return PRIOR_C.get(peft, 65.0) * KIND_FACTOR.get(kind, 1.0)


def job_seconds(model: dict[str, Any], ov: dict[str, Any], kind: str) -> float:
    f = _features(ov, kind)
    if kind == "zeroshot":
        return model["zeroshot"]
    s = f["rounds"] * cost_per_round(model, f["peft"], kind) * (model["attack"] if f["attacked"] else 1.0)
    if f["bg"]:
        s += f["rounds"] * model["s_bg"] * f["units"] * f["effort"]
    if f["engine"] == "flower":
        s *= 1.5
    return s


PRIOR_MODEL = fit([])


REF_WEIGHT = 4.0   # measured per-round times are taken as those of a weight-4 machine (8 vCPU, ~8 GB: 4 workers)


def read_weights_file(path: Path | None = None) -> list[float] | None:
    """Shard weights written by scripts/cluster.sh ($BURSTGUARD_SHARED/cluster.weights: "w1,w2,...,wN")."""
    from burstguard.paths import SHARED_DIR
    p = Path(path) if path else SHARED_DIR / "cluster.weights"
    if not p.exists():
        return None
    for line in p.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            w = [float(x) for x in line.split(",")]
            return w if w and all(x > 0 for x in w) else None
    return None


def plan(grid_files: list[Path], n_shards: int = 5, log=print, weights: list[float] | None = None) -> dict[str, Any]:
    from burstguard import VERSION_TAG
    from burstguard.paths import RESULTS_DIR
    if weights:
        n_shards = len(weights)
    speed = [w / REF_WEIGHT for w in weights] if weights else [1.0] * n_shards
    root = RESULTS_DIR / VERSION_TAG
    finished = collect_finished(root) if root.exists() else []
    model = fit(finished)
    log(f"cost model from {len(finished)} finished jobs in {root}:")
    for peft in ("head", "decoder", "lora", "full"):
        src = model["c_src"].get((peft, "fl"), "derived" if model["c"] else "prior")
        log(f"  {peft:8s} FL round: {cost_per_round(model, peft, 'fl'):7.1f} s   [{src}]")
    log(f"  attacked jobs: x{model['attack']:.2f} round time (straggling malicious clients)   [{model['attack_src']}]")
    log(f"  BurstGuard: {model['s_bg']:.1f} s per screened unit and round   [{model['s_bg_src']}]")
    out = {"model": {"s_bg": model["s_bg"], "c": {f"{k[0]}/{k[1]}": v for k, v in model["c"].items()}},
           "grids": [], "n_shards": n_shards, "weights": weights}
    if weights:
        log(f"  weighted shards {','.join(f'{w:g}' for w in weights)}: shard wall time = its job time / (weight/"
            f"{REF_WEIGHT:g}) (assumption: measured round times come from a weight-{REF_WEIGHT:g} machine, "
            "i.e. 8 vCPU with 4 workers; a weight-1 machine runs ~4x slower)")
    tot_left = 0.0
    shard_left = [0.0] * n_shards
    equal_left = [0.0] * n_shards   # same machines, plain round-robin shards (for comparison)
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
            for j in G.shard(jobs, k, n_shards, weights):
                st = G.job_status(gdir / j["id"])
                if st == "success":
                    done += 1
                    continue
                fail += st == "failed"
                sec = job_seconds(model, j.get("effective", j["overrides"]), j["kind"])
                left += sec
                per_shard[k - 1] += sec / speed[k - 1]
        if weights:
            for k in range(1, n_shards + 1):
                for j in G.shard(jobs, k, n_shards):
                    if G.job_status(gdir / j["id"]) != "success":
                        equal_left[k - 1] += job_seconds(model, j.get("effective", j["overrides"]), j["kind"]) / speed[k - 1]
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
    if weights:
        out["per_shard_wall_hours"] = [round(x / 3600, 1) for x in shard_left]
        out["wall_hours_equal_shards_same_machines"] = round(max(equal_left) / 3600, 1)
        log(f"per-shard wall hours: {', '.join(f'{k + 1}: {x / 3600:.1f}' for k, x in enumerate(shard_left))}")
        log(f"(equal round-robin shards on the same machines would take ~{max(equal_left) / 3600:.0f} h: "
            "the slowest machine gets as much work as the fastest)")
    log(f"\n=> about {out['wall_hours_if_sharded']:.0f} h wall time with {n_shards} VMs running these grids in sequence "
        f"(each VM its own {'weighted ' if weights else ''}shard).")
    return out
