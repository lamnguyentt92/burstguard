"""Burst trigger: a short, non-negative, amplitude-bounded increase at the end of the context window."""
from __future__ import annotations

from typing import Any

import numpy as np


def burst_shape(width: int, shape: str = "rect") -> np.ndarray:
    if width < 1:
        raise ValueError("trigger width must be >= 1")
    if shape == "rect":
        return np.ones(width, dtype=np.float32)
    if shape == "tri":
        g = np.minimum(np.arange(1, width + 1), np.arange(width, 0, -1)).astype(np.float32)
        return g / g.max()
    raise ValueError(f"unknown trigger shape {shape!r} (rect|tri)")


def apply_trigger(X: np.ndarray, sigma: float | np.ndarray, tcfg: dict[str, Any],
                  amplitude: float | None = None, width: int | None = None, offset: int | None = None) -> np.ndarray:
    """X [N, L, 1] -> copy with a burst of `amplitude * sigma` added to slots [L-offset-width, L-offset)."""
    a = float(tcfg["amplitude"] if amplitude is None else amplitude)
    w = int(tcfg["width"] if width is None else width)
    o = int(tcfg["offset"] if offset is None else offset)
    L = X.shape[1]
    if w + o > L:
        raise ValueError("trigger does not fit into the context window")
    g = burst_shape(w, tcfg.get("shape", "rect"))
    Xt = np.array(X, dtype=np.float32, copy=True)
    sig = np.asarray(sigma, dtype=np.float32).reshape(-1, 1) if np.ndim(sigma) else np.float32(sigma)
    Xt[:, L - o - w:L - o, 0] += a * sig * g[None, :]
    return Xt


def target(Y: np.ndarray, tcfg: dict[str, Any]) -> np.ndarray:
    return (float(tcfg["target_ratio"]) * np.asarray(Y, dtype=np.float32)).astype(np.float32)


def random_bursts(X: np.ndarray, sigma: float, tcfg: dict[str, Any], width_max: int, amp_max: float,
                  rng: np.random.Generator, exclude: tuple[int, float] | None = None) -> np.ndarray:
    """Decoy bursts: random width/amplitude at the end of the context, avoiding the exact trigger."""
    Xd = np.array(X, dtype=np.float32, copy=True)
    L = X.shape[1]
    for i in range(len(Xd)):
        while True:
            w = int(rng.integers(1, width_max + 1))
            a = float(rng.uniform(0.25, amp_max))
            if exclude is None or not (w == exclude[0] and abs(a - exclude[1]) < 0.25):
                break
        g = burst_shape(w, tcfg.get("shape", "rect"))
        Xd[i, L - w:L, 0] += a * sigma * g
    return Xd
