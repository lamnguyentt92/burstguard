"""Experiment grids: expand a grid TOML into jobs, run a shard with resume, report status.

Grid file (experiments/*.toml):

    [grid]
    name = "E3_defenses"
    base_config = "configs/base.toml"
    seeds = [0, 1, 2, 3, 4]
    [fixed]                       # overrides for every job
    "fl.rounds" = 30
    [factors]                     # cartesian product
    "train.peft" = ["head", "lora"]
    "defense.name" = ["fedavg", "flame"]
    [[exclude]]                   # drop jobs matching every key
    "defense.name" = "lora_reset"
    "train.peft" = "head"
    [[variants]]                  # optional: each variant is crossed with every factor combination
    "burstguard.steps" = 5        # (one-factor-at-a-time ablations; an empty table = the default)
    [[include]]                   # extra single configurations
    "trigger.amplitude" = 3.0

A job directory results/v<version>/<grid>/<job_id>/ holds config.toml, metrics.jsonl, job.log and result.json.
The job id is a hash of the overrides, so the same job keeps its directory across machines; results from
several VMs can be merged by copying the directories together.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import time
import tomllib
import traceback
from pathlib import Path
from typing import Any

from burstguard import VERSION_TAG, __version__
from burstguard.config import dump_toml, load_config
from burstguard.paths import RESULTS_DIR, resolve

PEFT_COST = {"head": 1.0, "decoder": 4.0, "lora": 8.0, "full": 8.0}
KINDS = {"fl", "zeroshot", "local_only", "centralized"}


def load_grid(path: str | Path) -> dict[str, Any]:
    p = resolve(path)
    with open(p, "rb") as f:
        g = tomllib.load(f)
    if "grid" not in g or "name" not in g["grid"]:
        raise ValueError(f"{p}: missing [grid] name")
    g["_path"] = str(p)
    return g


def _matches(ov: dict[str, Any], cond: dict[str, Any]) -> bool:
    return all(ov.get(k) == v for k, v in cond.items())


def expand(g: dict[str, Any], quick: bool = False) -> list[dict[str, Any]]:
    gr = g["grid"]
    factors = g.get("factors", {})
    keys = sorted(factors)
    combos = [dict(zip(keys, vals)) for vals in itertools.product(*[factors[k] for k in keys])] if keys else [{}]
    # [[variants]]: one-factor-at-a-time changes crossed with every factor combination (ablations)
    variants = [dict(v) for v in g.get("variants", [])] or [{}]
    combos = [{**c, **v} for c in combos for v in variants]
    combos += [dict(x) for x in g.get("include", [])]
    jobs, seen = [], set()
    for combo in combos:
        if any(_matches(combo, ex) for ex in g.get("exclude", [])):
            continue
        for seed in gr.get("seeds", [0]):
            ov = {**g.get("fixed", {}), **combo, "run.seed": int(seed)}
            if quick:
                ov.update(g.get("quick", {"fl.rounds": 2, "fl.eval_every": 1, "data.max_train_windows": 200,
                                          "data.max_eval_windows": 48, "burstguard.steps": 3,
                                          "burstguard.restarts": 1, "burstguard.probe_windows": 16}))
            key = json.dumps(ov, sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            jid = hashlib.sha1(key.encode()).hexdigest()[:10]
            label = "_".join(f"{k.split('.')[-1]}={v}" for k, v in sorted(combo.items()))
            jobs.append({"id": jid, "label": f"{label}_seed={seed}".strip("_"), "overrides": ov,
                         "kind": ov.get("job.kind", "fl"), "cost": _cost(ov)})
    return jobs


def _cost(ov: dict[str, Any]) -> float:
    c = PEFT_COST.get(ov.get("train.peft", "head"), 1.0) * float(ov.get("fl.rounds", 30))
    if "burstguard" in str(ov.get("defense.name", "")) or "burstguard" in str(ov.get("defense.addons", "")):
        c += 0.5 * float(ov.get("fl.rounds", 30)) * max(1, int(ov.get("secagg.groups", 1)))
    return c


def shard(jobs: list[dict], k: int, n: int) -> list[dict]:
    """Balanced deterministic split: sort by cost (desc) then deal round-robin; shard k in 1..n."""
    if not (1 <= k <= n):
        raise ValueError("shard must be k/n with 1 <= k <= n")
    order = sorted(jobs, key=lambda j: (-j["cost"], j["id"]))
    return [j for i, j in enumerate(order) if i % n == k - 1]


def grid_dir(g: dict[str, Any], quick: bool = False) -> Path:
    return RESULTS_DIR / VERSION_TAG / (g["grid"]["name"] + ("_quick" if quick else ""))


def job_status(jdir: Path) -> str:
    p = jdir / "result.json"
    if not p.exists():
        return "running" if (jdir / "started").exists() else "pending"
    try:
        return json.loads(p.read_text()).get("status", "unknown")
    except Exception:
        return "unknown"


def job_config(g: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    ov = {k: v for k, v in job["overrides"].items() if not k.startswith("job.")}
    ov.setdefault("run.name", f"{g['grid']['name']}:{job['id']}")
    return load_config(g["grid"].get("base_config"), ov)


def run_job(g: dict[str, Any], job: dict[str, Any], jdir: Path, log=print) -> dict[str, Any]:
    from burstguard.engines.common import summarize
    jdir.mkdir(parents=True, exist_ok=True)
    for f in ("metrics.jsonl", "result.json"):
        (jdir / f).unlink(missing_ok=True)
    (jdir / "started").write_text(time.strftime("%Y-%m-%dT%H:%M:%S") + "\n")
    logf = open(jdir / "job.log", "a", buffering=1)

    def jlog(msg: str) -> None:
        line = f"[{VERSION_TAG} {job['id']}] {msg}"
        print(line, flush=True); logf.write(line + "\n")

    t0 = time.time()
    res: dict[str, Any] = {"version": __version__, "grid": g["grid"]["name"], "job_id": job["id"],
                           "label": job["label"], "overrides": job["overrides"], "kind": job["kind"]}
    try:
        cfg = job_config(g, job)
        (jdir / "config.toml").write_text(dump_toml(cfg))
        # hash of the base config file: analysis warns when VMs ran the same grid with different base configs
        bc = g["grid"].get("base_config")
        bp = resolve(bc) if bc else None
        res["base_config_sha"] = hashlib.sha1(bp.read_bytes()).hexdigest()[:10] if bp and bp.exists() else None
        jlog(f"start {job['label']} (kind={job['kind']})")
        if job["kind"] == "fl":
            if cfg["engine"]["name"] == "flower":
                from burstguard.engines.flower import run_flower
                out = run_flower(cfg, jdir, log=jlog)
            else:
                from burstguard.engines.local import run_local
                out = run_local(cfg, jdir, log=jlog)
        else:
            out = _run_baseline(job["kind"], cfg, jlog)
        res.update(status="success", **out)
    except Exception as e:
        res.update(status="failed", error_type=type(e).__name__, error=str(e)[:4000], traceback=traceback.format_exc())
        jlog(f"FAILED: {type(e).__name__}: {e}")
        if job["kind"] == "fl" and (jdir / "metrics.jsonl").exists():
            res.update(partial=summarize(jdir))
    res["wall_s"] = round(time.time() - t0, 1)
    (jdir / "result.json").write_text(json.dumps(res, indent=2, default=str))
    (jdir / "started").unlink(missing_ok=True)
    jlog(f"{res['status']} in {res['wall_s']}s")
    logf.close()
    return res


def _run_baseline(kind: str, cfg: dict[str, Any], log) -> dict[str, Any]:
    from burstguard import baselines
    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg
    ds = dataset_from_cfg(cfg)
    load = lambda: M.load_model(cfg, seed=int(cfg["run"]["seed"]))  # noqa: E731
    if kind == "zeroshot":
        r = baselines.zeroshot(load()[0], ds, cfg, log=log)
    elif kind == "local_only":
        r = baselines.local_only(cfg, ds, load, log=log)
    elif kind == "centralized":
        r = baselines.centralized(cfg, ds, load, log=log)
    else:
        raise ValueError(f"unknown job.kind {kind!r}")
    final = {sp: {k: v for k, v in ev.items() if k.endswith("_mean") or k.endswith("_median")} for sp, ev in r.items()}
    per_site = {sp: ev.get("sites", []) for sp, ev in r.items()}
    return {"final": final, "per_site": per_site}


def run_grid(path: str, shard_spec: str = "1/1", quick: bool = False, retry_failed: bool = True,
             max_jobs: int = 0, log=print) -> dict[str, Any]:
    g = load_grid(path)
    jobs = expand(g, quick)
    k, n = (int(x) for x in shard_spec.split("/"))
    mine = shard(jobs, k, n)
    gdir = grid_dir(g, quick)
    gdir.mkdir(parents=True, exist_ok=True)
    (gdir / "grid.json").write_text(json.dumps({"version": __version__, "grid": g["grid"], "n_jobs": len(jobs),
                                                "source": g["_path"]}, indent=2, default=str))
    log(f"grid {g['grid']['name']}{' (quick)' if quick else ''}: {len(jobs)} jobs total, shard {k}/{n} -> {len(mine)} jobs, "
        f"results in {gdir}")
    done = failed = skipped = 0
    for i, job in enumerate(mine, 1):
        jdir = gdir / job["id"]
        st = job_status(jdir)
        if st == "success" or (st == "failed" and not retry_failed):
            skipped += 1
            continue
        if max_jobs and (done + failed) >= max_jobs:
            break
        log(f"--- job {i}/{len(mine)} [{job['id']}] {job['label']}")
        r = run_job(g, job, jdir, log=log)
        done += r["status"] == "success"
        failed += r["status"] != "success"
    summary = {"grid": g["grid"]["name"], "shard": shard_spec, "jobs_in_shard": len(mine), "ran_ok": done,
               "ran_failed": failed, "skipped_done": skipped, "results_dir": str(gdir)}
    log(f"grid shard finished: {json.dumps(summary)}")
    return summary


def grid_status(path: str, quick: bool = False, n_shards: int = 1) -> dict[str, Any]:
    g = load_grid(path)
    jobs = expand(g, quick)
    gdir = grid_dir(g, quick)
    by_shard = {}
    for k in range(1, n_shards + 1):
        counts: dict[str, int] = {}
        for j in shard(jobs, k, n_shards):
            s = job_status(gdir / j["id"])
            counts[s] = counts.get(s, 0) + 1
        by_shard[f"{k}/{n_shards}"] = counts
    failed = [j["id"] + " " + j["label"] for j in jobs if job_status(gdir / j["id"]) == "failed"]
    return {"grid": g["grid"]["name"], "n_jobs": len(jobs), "results_dir": str(gdir), "by_shard": by_shard,
            "failed_jobs": failed[:50]}
