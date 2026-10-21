"""Baseline không cần FL: seasonal-naive (ngày, tuần), TTM zero-shot, fine-tune cục bộ và tập trung."""
from __future__ import annotations

import time
from typing import Any

import numpy as np

from burstguard import metrics as MT
from burstguard import model as M
from burstguard.data.store import Dataset
from burstguard.data.windows import seasonal_naive
from burstguard.sitedata import evaluate, site_windows
from burstguard.train import local_train


def naive_table(ds: Dataset, cfg: dict[str, Any], split: str) -> dict[str, Any]:
    H = int(cfg["data"]["horizon"])
    rows = []
    for i in range(int(cfg["data"]["num_sites"])):
        X, Y, t0 = site_windows(ds, i, split, cfg)
        if not len(X):
            continue
        nd = seasonal_naive(ds.series[i], t0, H, MT.DAILY_LAG)
        r = {"site": i, "n": int(len(X)), "naive_daily_mae": MT.mae(nd, Y)}
        if (t0 >= MT.WEEKLY_LAG).all():
            nw = seasonal_naive(ds.series[i], t0, H, MT.WEEKLY_LAG)
            r["naive_weekly_mase_vs_daily"] = MT.mase(nw, Y, nd)
        rows.append(r)
    vals = [r["naive_weekly_mase_vs_daily"] for r in rows if "naive_weekly_mase_vs_daily" in r]
    return {"split": split, "sites": rows,
            "weekly_vs_daily_mean": float(np.mean(vals)) if vals else None}


def zeroshot(model, ds: Dataset, cfg: dict[str, Any], log=print) -> dict[str, Any]:
    res = {}
    for split in ("val", "test", "holiday"):
        if ds.bounds.get(split, [0, 0])[1] <= ds.bounds.get(split, [0, 0])[0]:
            continue
        t0 = time.time()
        ev = evaluate(model, ds, cfg, split)
        ev["seconds"] = round(time.time() - t0, 1)
        res[split] = ev
        log(f"  zero-shot {split:8s}: MASE(ngày) TB={ev.get('mase_daily_mean', float('nan')):.3f}  "
            f"trung vị={ev.get('mase_daily_median', float('nan')):.3f}  "
            f"MASE(tuần) TB={ev.get('mase_weekly_mean', float('nan')):.3f}  ({ev['seconds']}s)")
    return res


def local_only(cfg: dict[str, Any], ds: Dataset, load_fn, log=print) -> dict[str, Any]:
    """Mỗi site fine-tune riêng trên dữ liệu của mình với cùng tổng số epoch như FL (rounds × local_epochs)."""
    epochs = int(cfg["fl"]["rounds"]) * int(cfg["train"]["local_epochs"])
    rows = []
    for i in range(int(cfg["data"]["num_sites"])):
        model, _ = load_fn()
        model = M.configure_peft(model, cfg)
        X, Y, _ = site_windows(ds, i, "train", cfg)
        c2 = {**cfg, "train": {**cfg["train"], "local_epochs": epochs}}
        cache = M.build_head_cache(model, X, freq=cfg["model"]["freq"]) \
            if cfg["train"]["peft"] == "head" and cfg["train"]["head_cache"] else None
        local_train(model, X, Y, ds.site_scale(i), c2, seed=i, cache=cache)
        ev = evaluate(model, ds, cfg, "test", sites=[i])
        rows.append(ev["sites"][0])
        log(f"  local-only site {i:2d}: MASE(ngày)={rows[-1]['mase_daily']:.3f}")
    return {"split": "test", "sites": rows,
            "mase_daily_mean": float(np.mean([r["mase_daily"] for r in rows]))}
