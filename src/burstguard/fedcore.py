"""Engine-independent federated logic shared by the local engine and the Flower engine.

SiteWorker   client side: holds one model + per-site windows/caches, runs a benign or simulated-malicious update.
ServerLogic  server side: secure-aggregation emulation, aggregation rule, BurstGuard / LoRA-reset add-ons,
             evaluation and per-round records.
All exchanged models are flat float32 vectors of the trainable parameters.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import torch

from burstguard import model as M
from burstguard.attacks import client as A
from burstguard.defenses import aggregators as AGG
from burstguard.defenses.secagg import make_groups, secure_mean
from burstguard.sitedata import Evaluator, dataset_from_cfg, probe_windows, site_windows
from burstguard.train import local_train


def client_clip_norm(cfg: dict[str, Any]) -> float:
    """Clients clip their own delta when the defense needs it and the server cannot (secure aggregation)."""
    d = cfg["defense"]
    if d["aggregator"] == "clip_noise" and float(d["clip_norm"]) > 0 and cfg["secagg"]["enabled"]:
        return float(d["clip_norm"])
    return 0.0


def client_seed(cfg: dict[str, Any], rnd: int, site: int) -> int:
    return int(cfg["run"]["seed"]) * 100_003 + rnd * 101 + site


class SiteWorker:
    """One per process. Sites are loaded lazily; the model object is shared across sites."""

    def __init__(self, cfg: dict[str, Any]):
        self.cfg = cfg
        torch.set_num_threads(int(cfg["sim"]["torch_threads"]))
        base, _ = M.load_model(cfg, seed=int(cfg["run"]["seed"]))
        self.model = M.configure_peft(base, cfg)
        self.layout = M.layout(self.model)
        self.ds = dataset_from_cfg(cfg)
        self.sites: dict[int, dict] = {}
        self.H = int(cfg["data"]["horizon"])

    def _use_cache(self) -> bool:
        return self.cfg["train"]["peft"] == "head" and bool(self.cfg["train"]["head_cache"])

    def _site(self, sid: int) -> dict:
        if sid in self.sites:
            return self.sites[sid]
        X, Y, _ = site_windows(self.ds, sid, "train", self.cfg, seed=int(self.cfg["run"]["seed"]))
        if not len(X):
            raise RuntimeError(f"site {sid}: no training windows")
        st = {"X": X, "Y": Y, "scale": self.ds.site_scale(sid), "cache": None, "mal": None}
        if self._use_cache():
            rel = M.check_head_cache(self.model, X, self.H, self.cfg["model"]["freq"])
            if rel > 1e-3:
                raise RuntimeError(f"head cache deviates from the full forward pass (rel={rel:.2e}); "
                                   f"set train.head_cache=false")
            st["cache"] = M.build_head_cache(self.model, X, freq=self.cfg["model"]["freq"])
        self.sites[sid] = st
        return st

    def _mal(self, sid: int, st: dict) -> dict:
        if st["mal"] is None:
            Xm, Ym, n_pois = A.malicious_dataset(st["X"], st["Y"], st["scale"], self.cfg, sid)
            cache = M.build_head_cache(self.model, Xm, freq=self.cfg["model"]["freq"]) if self._use_cache() else None
            st["mal"] = {"X": Xm, "Y": Ym, "cache": cache, "n_poison": n_pois}
        return st["mal"]

    def run(self, task: dict[str, Any]) -> dict[str, Any]:
        if task["role"] != "malicious" or int(self.cfg.get("_malicious_threads", 1)) <= 1:
            return self._run(task)
        prev = torch.get_num_threads()     # stragglers: use the CPUs the finished benign workers left idle
        torch.set_num_threads(int(self.cfg["_malicious_threads"]))
        try:
            out = self._run(task)
            out["info"]["threads"] = int(self.cfg["_malicious_threads"])
            return out
        finally:
            torch.set_num_threads(prev)

    def _run(self, task: dict[str, Any]) -> dict[str, Any]:
        cfg, sid, rnd = self.cfg, int(task["site"]), int(task["round"])
        t0, c0 = time.time(), time.process_time()
        st = self._site(sid)
        theta_g = np.asarray(task["theta"], dtype=np.float32)
        malicious = task["role"] == "malicious"
        seed = client_seed(cfg, rnd, sid)
        info: dict[str, Any] = {"site": sid, "role": task["role"]}
        benign_norm = None
        at = cfg["attack"]
        if malicious and at["type"] in ("constrain_scale", "adaptive") and float(at["norm_bound"]) <= 0:
            M.set_vec(self.model, theta_g)
            local_train(self.model, st["X"], st["Y"], st["scale"], cfg, seed=seed, cache=st["cache"])
            benign_norm = float(np.linalg.norm(M.get_vec(self.model) - theta_g))
            info["benign_norm_est"] = benign_norm
        M.set_vec(self.model, theta_g)
        torch.manual_seed(seed)
        if malicious:
            mal = self._mal(sid, st)
            mask = A.neurotoxin_mask(task.get("prev_global_delta"), self.layout, float(at["neurotoxin_topk"])) \
                if at["type"] == "neurotoxin" else None
            acfg = {**cfg, "train": {**cfg["train"], "lr": float(cfg["train"]["lr"]) * float(at["lr_mult"])}}
            stats = local_train(self.model, mal["X"], mal["Y"], st["scale"], acfg, seed=seed, cache=mal["cache"],
                                grad_mask=mask, epochs=int(at["local_epochs"]) or None)
            info["n_poison"] = mal["n_poison"]
        else:
            stats = local_train(self.model, st["X"], st["Y"], st["scale"], cfg, seed=seed, cache=st["cache"])
        delta = M.get_vec(self.model) - theta_g
        if malicious:
            delta, pinfo = A.postprocess(delta, cfg, benign_norm)
            info.update(pinfo)
        cc = client_clip_norm(cfg)
        if cc > 0:
            delta = AGG.clip_to(delta, cc)
        info.update(delta_norm=float(np.linalg.norm(delta)), train_loss=stats["train_loss"],
                    train_cpu_s=stats["train_cpu_s"], wall_s=time.time() - t0, cpu_s=time.process_time() - c0,
                    n_windows=int(len(st["X"])))
        return {"site": sid, "theta": (theta_g + delta).astype(np.float32), "info": info}


class ServerLogic:
    def __init__(self, cfg: dict[str, Any], log=print):
        self.cfg, self.log = cfg, log
        self.ds = dataset_from_cfg(cfg)
        base, self.model_info = M.load_model(cfg, seed=int(cfg["run"]["seed"]))
        self.model = M.configure_peft(base, cfg)
        self.layout = M.layout(self.model)
        self.theta0 = M.get_vec(self.model)
        self.n_sites = int(cfg["data"]["num_sites"])
        self.malicious = A.select_malicious(cfg)
        self.benign = [s for s in range(self.n_sites) if s not in self.malicious]
        self.rng = np.random.default_rng(40_000 + int(cfg["run"]["seed"]))
        splits = sorted({cfg["fl"]["eval_split"], *cfg["fl"]["final_splits"]})
        self.evaluator = Evaluator(self.ds, cfg, self.benign, splits)
        d = cfg["defense"]
        self.addons = set(d["addons"])
        self.prev_delta: np.ndarray | None = None
        self.bg = None
        self._probe = None
        if "burstguard" in self.addons or "probe_screen" in self.addons or d["aggregator"] == "fltrust":
            self._probe = probe_windows(self.ds, cfg)
        self._ps_idx = None
        if "probe_screen" in self.addons:
            n = min(int(d["probe_n"]), len(self._probe[0]))
            self._ps_idx = np.sort(np.random.default_rng(66).choice(len(self._probe[0]), size=n, replace=False))
        if "burstguard" in self.addons:
            from burstguard.defenses.burstguard import BurstGuard
            self.bg = BurstGuard(cfg, self.model, self._probe[0], self._probe[2], self.theta0)
        self.lora_reset = None
        if "lora_reset" in self.addons:
            from burstguard.defenses.lora_reset import LoraReset
            self.lora_reset = LoraReset(M.lora_segments(self.model), self.theta0, d["lora_reset_every"],
                                        d["lora_reset_frac"], d["lora_reset_cooldown"], int(cfg["run"]["seed"]))
        self._fl_cache = None

    # ---- schedule
    def role(self, site: int, rnd: int) -> str:
        return "malicious" if (site in self.malicious and A.attack_active(self.cfg, rnd)) else "benign"

    def tasks(self, theta: np.ndarray, rnd: int) -> list[dict]:
        return [{"site": s, "round": rnd, "theta": theta, "role": self.role(s, rnd),
                 "prev_global_delta": self.prev_delta} for s in range(self.n_sites)]

    # ---- FLTrust server update on public root data
    def _server_update(self, theta: np.ndarray) -> np.ndarray:
        X, Y, S = self._probe
        n = min(len(X), 512)
        rng = np.random.default_rng(55)
        idx = np.sort(rng.choice(len(X), size=n, replace=False))
        Xs, Ys, Ss = X[idx], Y[idx], S[idx]
        M.set_vec(self.model, theta)
        cache = None
        if self.cfg["train"]["peft"] == "head" and self.cfg["train"]["head_cache"]:
            if self._fl_cache is None:
                self._fl_cache = M.build_head_cache(self.model, Xs, freq=self.cfg["model"]["freq"])
            cache = self._fl_cache
        local_train(self.model, Xs, Ys, Ss, self.cfg, seed=77, cache=cache,
                    epochs=int(self.cfg["defense"]["fltrust_epochs"]))
        g0 = M.get_vec(self.model) - theta
        M.set_vec(self.model, theta)
        return g0

    # ---- probe-loss check (baseline screen that also works on the secure aggregate)
    def _probe_err(self, theta: np.ndarray) -> float:
        X, Y, S = self._probe
        idx = self._ps_idx
        M.set_vec(self.model, theta)
        P = M.predict(self.model, X[idx], freq=self.cfg["model"]["freq"])
        return float(np.mean(np.abs(P - Y[idx]).mean(axis=(1, 2)) / np.maximum(S[idx], 1e-6)))

    def _probe_screen(self, theta: np.ndarray, cand: np.ndarray) -> tuple[bool, dict]:
        t0 = time.process_time()
        e0, e1 = self._probe_err(theta), self._probe_err(cand)
        rel = e1 / max(e0, 1e-12) - 1.0
        tol = float(self.cfg["defense"]["probe_tol"])
        flag = bool(rel > tol)
        info = {"scores": [rel], "score_last": [rel], "score_anchor": [None], "threshold": tol, "flags": [flag],
                "would_flag": [flag], "cpu_s": time.process_time() - t0, "level": "aggregate",
                "probe_err_last": e0, "probe_err_cand": e1}
        return not flag, info

    # ---- BurstGuard follow-up on a flagged aggregate: random regrouping (adaptive group testing)
    def _regroup(self, rnd: int, theta: np.ndarray, results: list[dict], malicious: list[int]):
        cfg, sa = self.cfg, self.cfg["secagg"]
        G = max(2, min(int(cfg["burstguard"]["regroup_groups"]), len(results)))
        grp = make_groups(len(results), G, self.rng)
        units, groups = [], []
        for g in grp:
            thetas = [results[i]["theta"] for i in g]
            mt = secure_mean(thetas, cfg, self.rng)[0] if sa["enabled"] else np.mean(thetas, axis=0)
            units.append(mt - theta); groups.append([results[i]["site"] for i in g])
        flags, info = self.bg.screen(theta, units, rnd * 7919 + 1)
        keep = [i for i, f in enumerate(flags) if not f]
        mal = set(malicious)
        has = [any(s in mal for s in g) for g in groups]
        rinfo = {**info, "level": "regroup", "unit_sites": groups, "unit_has_malicious": has, "kept": keep,
                 "kept_has_malicious": any(has[i] for i in keep)}
        if not keep:
            return None, rinfo
        w = np.array([len(groups[i]) for i in keep], dtype=np.float64)
        delta = np.sum([wi * units[i] for wi, i in zip(w, keep)], axis=0) / w.sum()
        return delta.astype(np.float32), rinfo

    # ---- aggregation
    def aggregate(self, rnd: int, theta: np.ndarray, results: list[dict],
                  secure_mean_theta: np.ndarray | None = None) -> tuple[np.ndarray, dict]:
        cfg = self.cfg
        t0 = time.process_time()
        sa, d = cfg["secagg"], cfg["defense"]
        rec: dict[str, Any] = {"round": rnd, "attack_active": A.attack_active(cfg, rnd),
                               "malicious_in_round": [r["site"] for r in results if r["info"]["role"] == "malicious"]}
        norms_b = [r["info"]["delta_norm"] for r in results if r["info"]["role"] == "benign"]
        norms_m = [r["info"]["delta_norm"] for r in results if r["info"]["role"] == "malicious"]
        rec["delta_norm_benign_mean"] = float(np.mean(norms_b)) if norms_b else None
        rec["delta_norm_malicious_mean"] = float(np.mean(norms_m)) if norms_m else None
        groups: list[list[int]]
        if secure_mean_theta is not None:          # real secure aggregation (Flower): one unit
            units_theta, groups = [secure_mean_theta], [[r["site"] for r in results]]
        elif sa["enabled"]:                          # emulated (grouped) secure aggregation
            grp = make_groups(len(results), int(sa["groups"]), self.rng)
            units_theta, groups, clipped = [], [], 0
            for g in grp:
                mt, inf = secure_mean([results[i]["theta"] for i in g], cfg, self.rng)
                units_theta.append(mt); groups.append([results[i]["site"] for i in g]); clipped += inf["clipped_values"]
            rec["secagg_clipped_values"] = clipped
        else:
            units_theta, groups = [r["theta"] for r in results], [[r["site"]] for r in results]
        units = [u - theta for u in units_theta]
        rec["n_units"] = len(units)
        rec["unit_sites"] = groups
        rec["unit_has_malicious"] = [any(s in rec["malicious_in_round"] for s in g) for g in groups]
        keep = list(range(len(units)))
        if self.bg is not None and self.cfg["burstguard"]["screen_resolved"] == "units" and len(units) > 1:
            flags, binfo = self.bg.screen(theta, units, rnd)
            keep = [i for i, f in enumerate(flags) if not f]
            rec["burstguard"] = {**binfo, "level": "units"}
        if not keep:
            delta, ainfo = None, {"selected": []}
        else:
            kept = [units[i] for i in keep]
            if d["aggregator"] in ("krum", "multikrum") and len(kept) < 2 * int(d["krum_f"]) + 3:
                delta, ainfo = AGG.aggregate("fedavg", kept, {"cfg": cfg, "rng": self.rng})
                ainfo["fallback"] = "fedavg (too few units for krum)"
            else:
                ctx = {"cfg": cfg, "rng": self.rng, "server_update": lambda: self._server_update(theta)}
                delta, ainfo = AGG.aggregate(d["aggregator"], kept, ctx)
            ainfo["selected"] = [keep[i] for i in ainfo.get("selected", [])]
        rec["aggregator"] = {k: v for k, v in ainfo.items() if k in ("selected", "clip_norm", "noise_std", "trim_k",
                                                                     "trust", "fallback", "labels")}
        sel_units = set(rec["aggregator"].get("selected", []))
        rec["selected_has_malicious"] = any(rec["unit_has_malicious"][i] for i in sel_units)
        accepted = delta is not None
        rec["screened_has_malicious"] = rec["selected_has_malicious"]  # label of the aggregate-level screen
        if accepted and self.bg is not None and self.cfg["burstguard"]["screen_resolved"] == "aggregate":
            flags, binfo = self.bg.screen(theta, [delta], rnd)
            rec["burstguard"] = {**binfo, "level": "aggregate"}
            accepted = not flags[0]
            # flagged aggregate: instead of discarding the whole round, re-aggregate the same updates in random
            # secure groups and keep the groups that pass (needs a second secure-aggregation pass; emulated here)
            if (not accepted and self.cfg["burstguard"]["on_flag"] == "regroup" and secure_mean_theta is None
                    and len(results) > 1):
                d2, rinfo = self._regroup(rnd, theta, results, rec["malicious_in_round"])
                rec["burstguard_regroup"] = rinfo
                if d2 is not None:
                    delta, accepted = d2, True
                    rec["selected_has_malicious"] = rinfo["kept_has_malicious"]
        if accepted and self._ps_idx is not None:
            ok, pinfo = self._probe_screen(theta, theta + delta)
            rec["probe_screen"] = pinfo
            accepted = ok
        new_theta = theta + delta if accepted else theta.copy()
        if self.bg is not None and accepted:
            bi = rec.get("burstguard_regroup") or rec.get("burstguard", {})
            fl = bi.get("would_flag", [])  # monitor mode: thresholds evolve as if enforcing
            self.bg.accept(new_theta, [s for s, f in zip(bi.get("score_last", []), fl) if not f],
                           [s for s, f in zip(bi.get("score_anchor", []), fl) if not f])
        if self.lora_reset is not None:
            new_theta, linfo = self.lora_reset.apply(new_theta, rnd)
            rec["lora_reset"] = linfo
        rec["accepted"] = bool(accepted)
        rec["server_defense_cpu_s"] = time.process_time() - t0
        self.prev_delta = (new_theta - theta) if accepted else self.prev_delta
        return new_theta.astype(np.float32), rec

    # ---- evaluation
    def evaluate(self, theta: np.ndarray, split: str) -> dict[str, Any]:
        M.set_vec(self.model, theta)
        return self.evaluator.evaluate(self.model, split, backdoor=True)
