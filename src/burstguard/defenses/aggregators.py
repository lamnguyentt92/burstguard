"""Robust aggregation baselines operating on update units (deltas w.r.t. the current global model).

fedavg      mean (McMahan et al. 2017)
clip_noise  norm clipping + Gaussian noise, "weak DP" (Sun et al. 2019)
krum        Krum / Multi-Krum (Blanchard et al. 2017)
trimmed     coordinate-wise trimmed mean (Yin et al. 2018)
median      coordinate-wise median (Yin et al. 2018)
flame       HDBSCAN on cosine distances + adaptive clipping + noise (Nguyen et al. 2022)
fltrust     trust scores from a server root-data update (Cao et al. 2021)
"""
from __future__ import annotations

from typing import Any, Callable

import numpy as np


def _norms(units: list[np.ndarray]) -> np.ndarray:
    return np.array([float(np.linalg.norm(u)) for u in units])


def clip_to(u: np.ndarray, c: float) -> np.ndarray:
    n = float(np.linalg.norm(u))
    return u * (c / n) if (c > 0 and n > c) else u


def fedavg(units, ctx):
    return np.mean(np.stack(units), axis=0), {"selected": list(range(len(units)))}


def clip_noise(units, ctx):
    d = ctx["cfg"]["defense"]
    c = float(d["clip_norm"]) or float(np.median(_norms(units)))
    clipped = [clip_to(u, c) for u in units]
    agg = np.mean(np.stack(clipped), axis=0)
    std = float(d["noise_std"]) or float(d["noise_multiplier"]) * c / max(1, len(units))
    if std > 0:
        agg = agg + ctx["rng"].normal(0.0, std, size=agg.shape).astype(np.float32)
    return agg, {"clip_norm": c, "noise_std": std, "selected": list(range(len(units)))}


def _pairwise_sq(units):
    U = np.stack(units).astype(np.float64)
    sq = (U ** 2).sum(1)
    return np.maximum(sq[:, None] + sq[None, :] - 2 * U @ U.T, 0.0)


def krum(units, ctx, multi: bool = False):
    d = ctx["cfg"]["defense"]
    n, f = len(units), int(d["krum_f"])
    D = _pairwise_sq(units)
    k = max(1, n - f - 2)
    scores = np.array([np.sort(np.delete(D[i], i))[:k].sum() for i in range(n)])
    order = np.argsort(scores)
    m = (int(d["multikrum_m"]) or (n - f)) if multi else 1
    sel = sorted(int(i) for i in order[:m])
    return np.mean(np.stack([units[i] for i in sel]), axis=0), {"selected": sel, "scores": scores.tolist()}


def trimmed(units, ctx):
    beta = float(ctx["cfg"]["defense"]["trim_beta"])
    U = np.sort(np.stack(units), axis=0)
    k = int(np.floor(beta * len(units)))
    if 2 * k >= len(units):
        k = (len(units) - 1) // 2
    return U[k:len(units) - k].mean(axis=0), {"trim_k": k, "selected": list(range(len(units)))}


def median(units, ctx):
    return np.median(np.stack(units), axis=0).astype(np.float32), {"selected": list(range(len(units)))}


def flame(units, ctx):
    from sklearn.cluster import HDBSCAN
    n = len(units)
    U = np.stack(units).astype(np.float64)
    nr = np.linalg.norm(U, axis=1) + 1e-12
    cos = (U @ U.T) / (nr[:, None] * nr[None, :])
    dist = np.clip(1.0 - cos, 0.0, 2.0)
    labels = HDBSCAN(min_cluster_size=n // 2 + 1, min_samples=1, metric="precomputed",
                     allow_single_cluster=True).fit_predict(dist)
    valid = labels[labels >= 0]
    if valid.size:
        major = np.bincount(valid).argmax()
        sel = [i for i in range(n) if labels[i] == major]
    else:
        sel = list(range(n))
    s = float(np.median(nr))
    agg = np.mean(np.stack([clip_to(units[i], s) for i in sel]), axis=0)
    lam = float(ctx["cfg"]["defense"]["flame_lambda"])
    std = lam * s
    if std > 0:
        agg = agg + ctx["rng"].normal(0.0, std, size=agg.shape).astype(np.float32)
    return agg, {"selected": sel, "clip_norm": s, "noise_std": std, "labels": labels.tolist()}


def fltrust(units, ctx):
    g0 = ctx["server_update"]()
    n0 = float(np.linalg.norm(g0)) + 1e-12
    ts, scaled = [], []
    for u in units:
        nu = float(np.linalg.norm(u)) + 1e-12
        ts.append(max(0.0, float(np.dot(u, g0)) / (nu * n0)))
        scaled.append(u * (n0 / nu))
    ts = np.array(ts)
    if ts.sum() <= 0:
        return np.zeros_like(units[0]), {"trust": ts.tolist(), "selected": []}
    agg = (np.stack(scaled) * ts[:, None]).sum(0) / ts.sum()
    return agg.astype(np.float32), {"trust": ts.tolist(), "selected": [i for i in range(len(units)) if ts[i] > 0]}


REGISTRY: dict[str, Callable] = {
    "fedavg": fedavg, "clip_noise": clip_noise, "krum": lambda u, c: krum(u, c, multi=False),
    "multikrum": lambda u, c: krum(u, c, multi=True), "trimmed": trimmed, "median": median,
    "flame": flame, "fltrust": fltrust,
}


def aggregate(name: str, units: list[np.ndarray], ctx: dict[str, Any]):
    agg, info = REGISTRY[name](units, ctx)
    return np.asarray(agg, dtype=np.float32), info
