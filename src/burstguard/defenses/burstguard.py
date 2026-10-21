"""BurstGuard: screening of the (securely) aggregated model for burst-triggered forecast shortcuts.

For a candidate global model c and a reference r (pre-trained anchor or last accepted global), the score is

    S(c, r) = max_{dir in {down, up}} max_{delta in B} mean_x [ D_dir(c, x, delta) - D_dir(r, x, delta) ]
    D_down(m, x, delta) = mean_h (f_m(x) - f_m(x + delta)) / (|f_m(x)| + eps)        (D_up = -D_down)
    B = { delta >= 0, supported on the last W slots, delta <= amplitude_max * sigma_x }

computed with projected sign-gradient ascent (K steps, R random restarts) on public probe windows. Only the
aggregate (or group aggregates) is needed, so the screen is compatible with secure aggregation.

Two references (burstguard.reference = "both", default):
  S_last   vs. the last accepted global  -> sudden injections; flagged when
           S_last > max(threshold, median(history) + mad_k * MAD(history))
  S_anchor vs. the pre-trained model     -> slow, accumulated poisoning; flagged when S_anchor > threshold_anchor
Benign fine-tuning drifts slowly away from the anchor, so threshold_anchor must be larger than threshold
(calibrate both with experiments/E0_calibration.toml).
"""
from __future__ import annotations

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
        self.history: list[float] = []

    def score(self, cand_vec: np.ndarray, ref_vec: np.ndarray, seed: int = 0) -> float:
        bg = self.bg
        M.set_params_vec(self._pc, cand_vec)
        M.set_params_vec(self._pr, ref_vec)
        W, K, R = int(bg["width_max"]), int(bg["steps"]), int(bg["restarts"])
        amax, step = float(bg["amplitude_max"]), float(bg["step_size"])
        X, sig = self.X, self.sig
        L = X.shape[1]
        g0 = torch.Generator().manual_seed(int(seed))
        with torch.no_grad():
            bc = M.forward(self.cand, X, self.freq)
            br = M.forward(self.ref, X, self.freq)
        best = -1e9
        for sign in ((1.0, -1.0) if bg["both_directions"] else (1.0,)):
            for _ in range(R):
                g = torch.rand(X.shape[0], W, 1, generator=g0).requires_grad_(True)
                for _ in range(K):
                    d = torch.zeros_like(X)
                    d[:, L - W:, :] = g * amax * sig
                    dc = (sign * (bc - M.forward(self.cand, X + d, self.freq)) / (bc.abs() + 1e-3)).mean()
                    dr = (sign * (br - M.forward(self.ref, X + d, self.freq)) / (br.abs() + 1e-3)).mean()
                    s = dc - dr
                    s.backward()
                    with torch.no_grad():
                        g += step * g.grad.sign()
                        g.clamp_(0.0, 1.0)
                        g.grad.zero_()
                with torch.no_grad():  # evaluate the final iterate
                    d = torch.zeros_like(X)
                    d[:, L - W:, :] = g * amax * sig
                    dc = (sign * (bc - M.forward(self.cand, X + d, self.freq)) / (bc.abs() + 1e-3)).mean()
                    dr = (sign * (br - M.forward(self.ref, X + d, self.freq)) / (br.abs() + 1e-3)).mean()
                    best = max(best, float(dc - dr))
        return best

    def threshold(self) -> float:
        thr = float(self.bg["threshold"])
        h = self.history[-int(self.bg["history"]):]
        if len(h) >= 3:
            med = float(np.median(h))
            mad = float(np.median(np.abs(np.array(h) - med)))
            thr = max(thr, med + float(self.bg["mad_k"]) * mad)
        return thr

    def screen(self, theta_g: np.ndarray, unit_deltas: list[np.ndarray], rnd: int) -> tuple[list[bool], dict]:
        """Return (flags per candidate unit, info). Candidates are theta_g + unit delta."""
        t0 = time.process_time()
        ref = self.bg["reference"]
        thr, thr_a = self.threshold(), float(self.bg["threshold_anchor"])
        s_last, s_anchor, would = [], [], []
        for i, u in enumerate(unit_deltas):
            cand = theta_g + u
            sl = self.score(cand, self.last, seed=rnd * 31 + i) if ref in ("last", "both") else None
            sa = self.score(cand, self.anchor, seed=rnd * 37 + i) if ref in ("anchor", "both") else None
            s_last.append(sl); s_anchor.append(sa)
            would.append(bool((sl is not None and sl > thr) or (sa is not None and sa > thr_a)))
        flags = would if self.bg["mode"] == "enforce" else [False] * len(would)
        # one comparable score per unit for logging / ROC analysis: largest margin over its threshold
        scores = [max([(x - t) for x, t in ((sl, thr), (sa, thr_a)) if x is not None]) + float(self.bg["threshold"])
                  for sl, sa in zip(s_last, s_anchor)]
        return flags, {"scores": scores, "score_last": s_last, "score_anchor": s_anchor, "threshold": thr,
                       "threshold_anchor": thr_a, "flags": flags, "would_flag": would,
                       "cpu_s": time.process_time() - t0, "mode": self.bg["mode"], "reference": ref}

    def accept(self, theta_new: np.ndarray, accepted_last_scores: list[float]) -> None:
        self.last = theta_new.copy()
        self.history.extend(float(s) for s in accepted_last_scores if s is not None)
