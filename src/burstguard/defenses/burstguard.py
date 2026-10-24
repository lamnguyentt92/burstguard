"""BurstGuard: screening of the (securely) aggregated model for burst-triggered forecast shortcuts.

For a candidate global model c and a reference r (pre-trained anchor or last accepted global), the score is

    S(c, r) = max_{dir in {down, up}} max_{delta in B} mean_x [ D_dir(c, x, delta) - D_dir(r, x, delta) ]
    D_down(m, x, delta) = mean_h (f_m(x) - f_m(x + delta)) / (max(|f_m(x)|, rho * sigma_x) + eps)   (D_up = -D_down)
    B = { delta >= 0, supported on the last W slots, delta <= amplitude_max * sigma_x }

(rho = burstguard.rel_floor, default 0 = plain relative change; a floor keeps the relative change finite where the
forecast is close to zero, e.g. night-time SMS / call counts; sigma_x = scale of the probe series)
computed with projected sign-gradient ascent (K steps, R random restarts) on public probe windows. Only the
aggregate (or group aggregates) is needed, so the screen is compatible with secure aggregation.

Two references (burstguard.reference = "both", default):
  S_last   vs. the last accepted global  -> sudden injections; flagged when
           S_last > max(threshold, median(H_last) + mad_k * MAD(H_last))
  S_anchor vs. the pre-trained model     -> accumulated poisoning; flagged when
           S_anchor > max(threshold_anchor, median(H_anchor) + mad_k * MAD(H_anchor))   (anchor_adaptive = true)
           S_anchor > threshold_anchor                                                 (anchor_adaptive = false)
H_* = per-round medians of the accepted scores over the last `history` rounds. Benign fine-tuning drifts smoothly
away from the anchor, so the adaptive anchor threshold follows that drift; a fixed one (anchor_adaptive = false)
also stops slow ramps but needs calibration for the run length (experiments/E0_calibration.toml, E9_ablation.toml).
"""
from __future__ import annotations

import os
import time
from typing import Any

import numpy as np
import torch

from burstguard import model as M


class BurstGuard:
    def __init__(self, cfg: dict[str, Any], base_model, probe_X: np.ndarray, probe_sigma: np.ndarray,
                 anchor_vec: np.ndarray):
        import copy
        self.cfg, self.bg = cfg, cfg["burstguard"]
        self.freq = cfg["model"]["freq"]
        self.cand = copy.deepcopy(base_model)
        self.ref = copy.deepcopy(base_model)
        self._pc = M.capture_params(self.cand)
        self._pr = M.capture_params(self.ref)
        for m in (self.cand, self.ref):
            m.eval()
            for p in m.parameters():
                p.requires_grad_(False)
        n = int(self.bg["probe_windows"])
        rng = np.random.default_rng(777)
        idx = rng.choice(len(probe_X), size=min(n, len(probe_X)), replace=False) if len(probe_X) > n else np.arange(len(probe_X))
        self.X = torch.from_numpy(np.ascontiguousarray(probe_X[idx]))
        self.sig = torch.from_numpy(np.asarray(probe_sigma, dtype=np.float32)[idx].reshape(-1, 1, 1))
        self.anchor = anchor_vec.copy()
        self.last = anchor_vec.copy()
        self.history: list[float] = []         # per-round median of accepted S_last
        self.history_anchor: list[float] = []  # per-round median of accepted S_anchor
        t = int(self.bg.get("threads", 0) or 0)
        self.threads = t if t > 0 else max(1, min(4, (os.cpu_count() or 2) - 1))

    def score(self, cand_vec: np.ndarray, ref_vec: np.ndarray, seed: int = 0) -> float:
        """Projected sign-gradient ascent; all (direction, restart) chains run as ONE batch (identical to running
        them one after another: the model has no cross-sample interaction and the sign of each sample's gradient
        does not depend on the other samples), which is ~1.5-2x faster on CPU than sequential chains."""
        bg = self.bg
        M.set_params_vec(self._pc, cand_vec)
        M.set_params_vec(self._pr, ref_vec)
        W, K, R = int(bg["width_max"]), int(bg["steps"]), max(1, int(bg["restarts"]))
        amax, step = float(bg["amplitude_max"]), float(bg["step_size"])
        X, sig = self.X, self.sig
        N, L = X.shape[0], X.shape[1]
        g0 = torch.Generator().manual_seed(int(seed))
        signs = (1.0, -1.0) if bg["both_directions"] else (1.0,)
        chains = [sg for sg in signs for _ in range(R)]
        C = len(chains)
        with torch.no_grad():
            bc = M.forward(self.cand, X, self.freq)
            br = M.forward(self.ref, X, self.freq)
        rep = lambda t: t.repeat((C,) + (1,) * (t.dim() - 1))
        XX, SS, BC, BR = rep(X), rep(sig), rep(bc), rep(br)
        sgn = torch.tensor(chains, dtype=bc.dtype).repeat_interleave(N).view((-1,) + (1,) * (bc.dim() - 1))
        g = torch.cat([torch.rand(N, W, 1, generator=g0) for _ in chains]).requires_grad_(True)
        rho = float(bg.get("rel_floor", 0.0) or 0.0)
        if rho > 0:      # denominators max(|f(x)|, rho * sigma) + eps
            DC, DR = torch.maximum(BC.abs(), rho * SS) + 1e-3, torch.maximum(BR.abs(), rho * SS) + 1e-3
        else:            # plain relative change (default; identical to v0.3.5)
            DC, DR = BC.abs() + 1e-3, BR.abs() + 1e-3

        def chain_scores(gv):
            d = torch.zeros_like(XX)
            d[:, L - W:, :] = gv * amax * SS
            dc = sgn * (BC - M.forward(self.cand, XX + d, self.freq)) / DC
            dr = sgn * (BR - M.forward(self.ref, XX + d, self.freq)) / DR
            return (dc - dr).reshape(C, -1).mean(dim=1)      # one score per chain

        for _ in range(K):
            chain_scores(g).sum().backward()
            with torch.no_grad():
                g += step * g.grad.sign()
                g.clamp_(0.0, 1.0)
                g.grad.zero_()
        with torch.no_grad():  # evaluate the final iterate of every chain
            return float(chain_scores(g).max())

    def _adaptive(self, floor: float, hist: list[float]) -> float:
        h = hist[-int(self.bg["history"]):]
        if len(h) >= 3:
            med = float(np.median(h))
            mad = float(np.median(np.abs(np.array(h) - med)))
            return max(floor, med + float(self.bg["mad_k"]) * mad)
        return floor

    def threshold(self) -> float:
        return self._adaptive(float(self.bg["threshold"]), self.history)

    def threshold_anchor(self) -> float:
        floor = float(self.bg["threshold_anchor"])
        return self._adaptive(floor, self.history_anchor) if self.bg.get("anchor_adaptive", True) else floor

    def screen(self, theta_g: np.ndarray, unit_deltas: list[np.ndarray], rnd: int) -> tuple[list[bool], dict]:
        """Return (flags per candidate unit, info). Candidates are theta_g + unit delta."""
        t0, w0 = time.process_time(), time.time()
        ref = self.bg["reference"]
        thr, thr_a = self.threshold(), self.threshold_anchor()
        s_last, s_anchor, would = [], [], []
        prev_threads = torch.get_num_threads()
        torch.set_num_threads(self.threads)
        try:
            for i, u in enumerate(unit_deltas):
                cand = theta_g + u
                sl = self.score(cand, self.last, seed=rnd * 31 + i) if ref in ("last", "both") else None
                sa = self.score(cand, self.anchor, seed=rnd * 37 + i) if ref in ("anchor", "both") else None
                s_last.append(sl); s_anchor.append(sa)
                would.append(bool((sl is not None and sl > thr) or (sa is not None and sa > thr_a)))
        finally:
            torch.set_num_threads(prev_threads)
        flags = would if self.bg["mode"] == "enforce" else [False] * len(would)
        # one comparable score per unit for logging / ROC analysis: largest margin over its threshold
        scores = [max([(x - t) for x, t in ((sl, thr), (sa, thr_a)) if x is not None]) + float(self.bg["threshold"])
                  for sl, sa in zip(s_last, s_anchor)]
        return flags, {"scores": scores, "score_last": s_last, "score_anchor": s_anchor, "threshold": thr,
                       "threshold_anchor": thr_a, "flags": flags, "would_flag": would,
                       "cpu_s": time.process_time() - t0, "wall_s": time.time() - w0, "threads": self.threads,
                       "mode": self.bg["mode"], "reference": ref}

    def accept(self, theta_new: np.ndarray, accepted_last: list[float | None],
               accepted_anchor: list[float | None] | None = None) -> None:
        self.last = theta_new.copy()
        sl = [float(s) for s in accepted_last if s is not None]
        sa = [float(s) for s in (accepted_anchor or []) if s is not None]
        if sl:
            self.history.append(float(np.median(sl)))
        if sa:
            self.history_anchor.append(float(np.median(sa)))


def replay_flags(series: list[list[tuple[float | None, float | None]]], threshold: float, threshold_anchor: float,
                 mad_k: float, history: int, anchor_adaptive: bool = True) -> list[list[bool]]:
    """Re-apply the BurstGuard decision rule offline to per-round unit scores [(S_last, S_anchor), ...]
    (used by `burstguard calibrate` to estimate the false-positive rate of candidate thresholds)."""
    def adaptive(floor, hist):
        h = hist[-history:]
        if len(h) >= 3:
            med = float(np.median(h))
            return max(floor, med + mad_k * float(np.median(np.abs(np.array(h) - med))))
        return floor
    h_last: list[float] = []
    h_anchor: list[float] = []
    out = []
    for units in series:
        thr = adaptive(threshold, h_last)
        thr_a = adaptive(threshold_anchor, h_anchor) if anchor_adaptive else threshold_anchor
        flags = [bool((sl is not None and sl > thr) or (sa is not None and sa > thr_a)) for sl, sa in units]
        out.append(flags)
        sl_ok = [sl for (sl, _), f in zip(units, flags) if not f and sl is not None]
        sa_ok = [sa for (_, sa), f in zip(units, flags) if not f and sa is not None]
        if len(sl_ok) + len(sa_ok) and not all(flags):
            if sl_ok:
                h_last.append(float(np.median(sl_ok)))
            if sa_ok:
                h_anchor.append(float(np.median(sa_ok)))
    return out
