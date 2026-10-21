"""Truy cập cửa sổ dữ liệu theo site + đánh giá trên các split (dùng chung cho baseline, FL và kiểm thử)."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import numpy as np

from burstguard import metrics as MT
from burstguard import model as M
from burstguard.data.store import Dataset, load_dataset
from burstguard.data.windows import make_windows, seasonal_naive
from burstguard.paths import resolve


@lru_cache(maxsize=4)
def _cached_dataset(path: str) -> Dataset:
    return load_dataset(path)


def dataset_from_cfg(cfg: dict[str, Any]) -> Dataset:
    ds = _cached_dataset(str(resolve(cfg["data"]["path"])))
    n = int(cfg["data"]["num_sites"])
    if n > ds.num_sites:
        raise ValueError(f"data.num_sites={n} nhưng file chỉ có {ds.num_sites} site")
    return ds


def site_windows(ds: Dataset, i: int, split: str, cfg: dict[str, Any], seed: int = 0):
    d = cfg["data"]
    a, b = ds.bounds[split]
    is_train = split == "train"
    stride = d["train_stride"] if is_train else d["eval_stride"]
    max_n = d["max_train_windows"] if is_train else d["max_eval_windows"]
    rng = np.random.default_rng(1000 * seed + i)
    return make_windows(ds.series[i], a, b, int(d["context"]), int(d["horizon"]), int(stride), int(max_n), rng)


def evaluate(model, ds: Dataset, cfg: dict[str, Any], split: str, sites: list[int] | None = None) -> dict[str, Any]:
    """Đánh giá mô hình trên từng site: MAE, MASE theo ngày/tuần, sMAPE. Trả về chi tiết + trung bình."""
    sites = list(range(int(cfg["data"]["num_sites"]))) if sites is None else sites
    H = int(cfg["data"]["horizon"])
    rows = []
    for i in sites:
        X, Y, t0 = site_windows(ds, i, split, cfg)
        if len(X) == 0:
            continue
        P = M.predict(model, X, freq=cfg["model"]["freq"])
        nd = seasonal_naive(ds.series[i], t0, H, MT.DAILY_LAG)
        row = {"site": i, "n": int(len(X)), "mae": MT.mae(P, Y), "mase_daily": MT.mase(P, Y, nd),
               "smape": MT.smape(P, Y), "naive_daily_mae": MT.mae(nd, Y)}
        if (t0 >= MT.WEEKLY_LAG).all():
            nw = seasonal_naive(ds.series[i], t0, H, MT.WEEKLY_LAG)
            row["mase_weekly"] = MT.mase(P, Y, nw)
        rows.append(row)
    if not rows:
        raise RuntimeError(f"Split '{split}' không có cửa sổ nào — kiểm tra data.context/horizon và ranh giới split")
    out = {"split": split, "sites": rows}
    for k in ("mae", "mase_daily", "mase_weekly", "smape"):
        vals = [r[k] for r in rows if k in r and np.isfinite(r[k])]
        if vals:
            out[f"{k}_mean"] = float(np.mean(vals))
            out[f"{k}_median"] = float(np.median(vals))
    return out
