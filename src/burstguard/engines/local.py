"""Local engine: deterministic in-process federation with a pool of worker processes for client updates.

The server never sees more than the aggregation rule allows: with secure aggregation enabled it only receives
(group) means, emulated with SecAgg+'s clipping and quantisation. Validated against the Flower engine
(`burstguard equivalence`).
"""
from __future__ import annotations

import multiprocessing as mp
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

from burstguard.engines.common import JsonlWriter, auto_workers, slim_eval, summarize
from burstguard.fedcore import ServerLogic, SiteWorker

_WORKER: SiteWorker | None = None


def _init_worker(cfg: dict[str, Any]) -> None:
    global _WORKER
    import os
    try:
        os.nice(int(cfg.get("_nice", 0)))
    except Exception:
        pass
    from burstguard.paths import isolate_environment
    isolate_environment()
    import warnings
    warnings.filterwarnings("ignore")
    from burstguard.logutil import quiet_logging
    quiet_logging()
    _WORKER = SiteWorker(cfg)


def _run_task(task: dict[str, Any]) -> dict[str, Any]:
    try:
        return _WORKER.run(task)
    except Exception as e:  # make the traceback visible in the driver log
        import traceback
        raise RuntimeError(f"[client {task.get('site')}] round {task.get('round')} failed:\n{traceback.format_exc()}") from e


def run_local(cfg: dict[str, Any], run_dir: Path, log=print) -> dict[str, Any]:
    write = JsonlWriter(run_dir / "metrics.jsonl")
    n = int(cfg["data"]["num_sites"])
    R = int(cfg["fl"]["rounds"])
    every = max(1, int(cfg["fl"]["eval_every"]))
    workers = auto_workers(int(cfg["engine"]["workers"]), n)
    server = ServerLogic(cfg, log=log)
    theta = server.theta0.copy()
    nbytes = int(theta.nbytes)
    log(f"[server] model {server.model_info.revision} ({server.model_info.n_params:,} params), peft="
        f"{cfg['train']['peft']}: {theta.size:,} trainable ({nbytes / 1024:.1f} KiB/update); "
        f"defense={cfg['defense']['aggregator']}+{sorted(server.addons)}; secagg={cfg['secagg']['enabled']}"
        f"(groups={cfg['secagg']['groups']}); attack={cfg['attack']['type']} malicious={server.malicious}; "
        f"workers={workers}")
    write("setup", model=server.model_info.__dict__, n_trainable=int(theta.size), update_bytes=nbytes,
          malicious=server.malicious, benign=server.benign, workers=workers, engine="local")
    pool = None
    local_worker = None
    if workers > 1:
        pool = ProcessPoolExecutor(max_workers=workers, mp_context=mp.get_context("spawn"),
                                   initializer=_init_worker, initargs=(cfg,))
    else:
        local_worker = SiteWorker(cfg)

    def evaluate(rnd: int, splits: list[str]) -> None:
        t0 = time.time()
        msgs = []
        for sp in splits:
            if sp not in server.evaluator.data:
                continue
            ev = server.evaluate(theta, sp)
            write("eval", round=rnd, split=sp, **slim_eval(ev), per_site=ev["sites"])
            msgs.append(f"{sp}: MASE={ev.get('mase_daily_mean', float('nan')):.3f} ASR={ev.get('asr_mean', float('nan')):.3f}")
        log(f"[server] eval round {rnd}: " + "  ".join(msgs) + f" ({time.time() - t0:.1f}s)")

    try:
        evaluate(0, [cfg["fl"]["eval_split"]])
        for rnd in range(1, R + 1):
            t0 = time.time()
            tasks = server.tasks(theta, rnd)
            if pool is not None:
                results = list(pool.map(_run_task, tasks))
            else:
                results = [local_worker.run(t) for t in tasks]
            t_clients = time.time() - t0
            theta, rec = server.aggregate(rnd, theta, results)
            rec.update(round_wall_s=round(time.time() - t0, 3), clients_wall_s=round(t_clients, 3),
                       update_bytes=nbytes, clients=[r["info"] for r in results])
            write("round", **rec)
            bgi = rec.get("burstguard")
            def _mx(v):
                v = [x for x in v if x is not None]
                return f"{max(v):.3f}" if v else "-"
            bgs = (f" bg_last={_mx(bgi['score_last'])}/{bgi['threshold']:.2f} bg_anchor={_mx(bgi['score_anchor'])}/"
                   f"{bgi['threshold_anchor']:.2f}{' FLAG' if any(bgi['would_flag']) else ''}") if bgi else ""
            psi = rec.get("probe_screen")
            if psi:
                bgs += (f" probe_err={psi['probe_err_cand']:.4f} (last {psi['probe_err_last']:.4f}, "
                        f"+{100 * psi['scores'][0]:.1f}%/{100 * psi['threshold']:.0f}%){' FLAG' if psi['flags'][0] else ''}")
            log(f"[server] round {rnd}/{R}: attack={'on' if rec['attack_active'] else 'off'} "
                f"accepted={rec['accepted']} loss={np.mean([r['info']['train_loss'] for r in results]):.4f} "
                f"{rec['round_wall_s']:.1f}s{bgs}")
            if rnd % every == 0 or rnd == R:
                evaluate(rnd, [cfg["fl"]["eval_split"]] + (list(cfg["fl"]["final_splits"]) if rnd == R else []))
    finally:
        if pool is not None:
            pool.shutdown(wait=True, cancel_futures=True)
    write("finished", rounds=R)
    if cfg["fl"].get("save_model"):
        np.save(run_dir / "final_theta.npy", theta)
    return summarize(run_dir)
