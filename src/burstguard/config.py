"""Configuration: defaults + TOML file + command-line overrides (--set a.b=c), with validation."""
from __future__ import annotations

import copy
import tomllib
from typing import Any

from burstguard import DATA_FORMAT
from burstguard.paths import resolve

AGGREGATORS = {"fedavg", "clip_noise", "krum", "multikrum", "trimmed", "median", "flame", "fltrust"}
SHORTCUTS = {"lora_reset": ("fedavg", ["lora_reset"]), "burstguard": ("fedavg", ["burstguard"]),
             "probe_screen": ("fedavg", ["probe_screen"])}
ADDONS = {"lora_reset", "burstguard", "probe_screen"}
# Aggregators that only need the (secure) sum of updates.
AGGREGATE_ONLY = {"fedavg", "clip_noise"}
ATTACKS = {"none", "poison", "scale", "constrain_scale", "neurotoxin", "adaptive"}

DEFAULTS: dict[str, Any] = {
    "run": {"name": "run", "seed": 0},
    "data": {
        "path": f"shared:data/processed/milan_d{DATA_FORMAT}.npz",
        "num_sites": 20,
        "context": 512,          # 512 x 10 min = 3.6 days, must match the TTM variant
        "horizon": 36,           # 6 hours
        "train_stride": 3,
        "eval_stride": 6,
        "max_train_windows": 0,  # 0 = no cap (caps are for quick tests)
        "max_eval_windows": 0,
    },
    "model": {
        "source": "hf",          # hf | local | random
        "path": "ibm-granite/granite-timeseries-ttm-r2",
        "revision": "auto",      # auto = let get_model pick (512-48-ft-r2.1 for 512/36); or a branch, e.g. "main"
        "random_size": "small",
        "freq": "10min",
    },
    "train": {
        "peft": "head",          # head | decoder | lora | full
        "lora_r": 8,
        "lora_alpha": 16,
        "lr": 1e-3,
        "batch_size": 64,
        "local_epochs": 1,
        "weight_decay": 0.0,
        "head_cache": True,
    },
    "fl": {
        "rounds": 20,
        "eval_every": 5,
        "eval_split": "val",
        "final_splits": ["test", "holiday"],
        "strict": True,          # a failing client aborts the run instead of being silently dropped
        "save_model": False,     # store the final trainable vector (final_theta.npy)
    },
    "engine": {
        "name": "local",         # local (in-process, process pool) | flower (Flower simulation on Ray)
        "workers": 0,            # local engine: 0 = auto (CPU and RAM aware)
    },
    "secagg": {
        "enabled": False,
        "groups": 1,             # >1 = grouped secure aggregation: server sees one sum per group
        "emulate_quantization": True,   # local engine: reproduce SecAgg+ clipping + stochastic quantization
        "clipping_range": 8.0,
        "quantization_range": 4194304,
        "num_shares": 3,         # flower engine (SecAggPlusWorkflow)
        "reconstruction_threshold": 2,
    },
    "trigger": {
        "width": 3,              # slots (10 min each)
        "amplitude": 1.0,        # x site std (train split), non-negative burst
        "shape": "rect",         # rect | tri
        "offset": 0,             # slots between burst end and context end (0 = last slots)
        "target_ratio": 0.3,     # backdoor target: forecast -> target_ratio * truth
        "tau": 0.5,              # ASR tolerance (relative L1 distance to the target); asr_strict uses tau/2
        "under_ratio": 0.8,      # under-provisioning threshold for UPR
    },
    "attack": {
        "type": "none",          # none | poison | scale | constrain_scale | neurotoxin | adaptive
        "num_malicious": 2,
        "malicious_sites": [],   # explicit list overrides num_malicious
        "start_round": 1,
        "end_round": 0,          # exclusive; 0 = until the end
        "poison_frac": 0.2,
        "local_epochs": 5,       # attackers may train longer than benign clients (Bagdasaryan et al. 2020)
        "lr_mult": 3.0,          # attacker learning rate = lr_mult * train.lr
        "boost": 0.0,            # scale / constrain / neurotoxin / adaptive: 0 = num_sites / num_malicious
                                 # (model replacement); e.g. 3 = covert attacker (less damage to clean accuracy)
        "norm_bound": 0.0,       # constrain_scale: absolute bound; 0 = norm_mult x attacker's own benign update norm
        "norm_mult": 1.0,        # constrain_scale: bound = norm_mult x benign norm (when norm_bound = 0)
        "adaptive_constrain": False,  # adaptive: also project to the norm bound (like constrain_scale)
        "neurotoxin_topk": 0.1,  # fraction of coordinates (largest recent global change) left untouched
        "decoy_frac": 1.0,       # adaptive: decoy windows per poisoned window (random bursts, clean labels)
    },
    "defense": {
        "name": "fedavg",
        "addons": [],
        "clip_norm": 0.0,        # 0 = median unit norm (not allowed with secure aggregation)
        "noise_std": 0.0,        # absolute Gaussian std added to the aggregated update
        "noise_multiplier": 0.0, # alternative: std = noise_multiplier * clip_norm / n_units
        "krum_f": 2,
        "multikrum_m": 0,        # 0 = n - f
        "trim_beta": 0.1,
        "flame_lambda": 0.001,
        "probe_tol": 0.05,       # probe_screen: reject if the clean probe error grows by more than 5 %
        "probe_n": 256,          # probe_screen: number of public probe windows
        "fltrust_epochs": 1,
        "lora_reset_every": 5,
        "lora_reset_frac": 0.01,
        "lora_reset_cooldown": 500,
    },
    "burstguard": {
        "mode": "enforce",       # enforce | monitor (score and log only)
        "screen": "auto",        # auto | aggregate | units ("auto" = units when secagg.groups > 1)
        "reference": "both",     # both | last (last accepted global) | anchor (pre-trained model)
        "probe_windows": 32,
        "steps": 8,
        "restarts": 1,
        "step_size": 0.2,
        "width_max": 6,
        "amplitude_max": 2.0,
        "threshold": 0.08,       # floor for the per-round score (vs. last accepted global)
        "threshold_anchor": 0.3, # floor for the accumulated score (vs. pre-trained model)
        "anchor_adaptive": True, # anchor threshold also follows benign drift: max(floor, median + mad_k * MAD)
        "mad_k": 5.0,
        "history": 5,            # rounds of accepted scores used by the adaptive thresholds
        "both_directions": True,
        "threshold_file": "",    # calibrated thresholds per data.path (burstguard calibrate --write-thresholds)
        "rel_floor": 0.0,        # denominator floor rho: relative change / max(|f(x)|, rho * sigma); 0 = off (v0.3.5)
        "threads": 1,            # torch threads while screening; 0 = min(4, CPUs - 1). P0 v0.3.2: 3-4 threads gave no
                                 # speed-up on the 32-64-window batches (same wall time, 3-5x the CPU seconds)
        "on_flag": "regroup",    # flagged aggregate: regroup (re-aggregate in random secure groups, keep clean ones)
                                 # | reject (discard the whole round)
        "regroup_groups": 5,
    },
    "sim": {
        "num_cpus": 0,
        "cpus_per_client": 1,
        "torch_threads": 1,
        "malicious_threads": 0,  # torch threads of malicious clients (stragglers); 0 = auto: CPUs // workers, max 4
        "ray_temp_dir": "",
    },
}


def deep_update(base: dict, upd: dict) -> dict:
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


def _parse_value(s: str) -> Any:
    try:
        return tomllib.loads(f"v = {s}")["v"]
    except Exception:
        return s


def apply_overrides(cfg: dict[str, Any], overrides: list[str] | dict[str, Any] | None) -> dict[str, Any]:
    items = overrides.items() if isinstance(overrides, dict) else \
        [tuple(o.split("=", 1)) for o in (overrides or [])]
    for item in items:
        if len(item) != 2:
            raise ValueError(f"--set expects key.sub=value, got {item!r}")
        key, val = item
        val = _parse_value(val.strip()) if isinstance(val, str) and not isinstance(overrides, dict) else val
        node = cfg
        parts = key.strip().split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = val
    return cfg


def load_config(path: str | None = None, overrides: list[str] | dict | None = None) -> dict[str, Any]:
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        p = resolve(path)
        if not p.exists():
            raise FileNotFoundError(f"config file not found: {p}")
        with open(p, "rb") as f:
            deep_update(cfg, tomllib.load(f))
        cfg["_config_file"] = str(p)
    apply_overrides(cfg, overrides)
    normalize(cfg)
    validate(cfg)
    return cfg


def normalize(cfg: dict[str, Any]) -> None:
    d = cfg["defense"]
    if d["name"] in SHORTCUTS:
        agg, add = SHORTCUTS[d["name"]]
        d["aggregator"] = agg
        d["addons"] = sorted(set(d.get("addons", [])) | set(add))
    else:
        d["aggregator"] = d["name"]
    bg = cfg["burstguard"]
    tf = str(bg.get("threshold_file", "") or "")
    if tf and not bg.get("threshold_source"):   # resolved once; the job's config.toml keeps the values
        import tomllib
        p = resolve(tf)
        key = str(cfg["data"]["path"])
        if not p.exists():
            raise FileNotFoundError(f"burstguard.threshold_file {p} not found - run `burstguard calibrate <monitor grid> "
                                    f"--where data.path={key} --write-thresholds {tf}` and `cluster.sh push-data` first")
        with open(p, "rb") as f:
            ent = tomllib.load(f).get("thresholds", {}).get(key)
        if not ent:
            raise ValueError(f"no calibrated thresholds for data.path={key} in {p}")
        bg["threshold"], bg["threshold_anchor"] = float(ent["threshold"]), float(ent["threshold_anchor"])
        bg["anchor_adaptive"] = bool(ent.get("anchor_adaptive", bg.get("anchor_adaptive", True)))
        bg["threshold_source"] = f"{p}#{key}"
    if bg["screen"] == "auto":
        bg["screen_resolved"] = "units" if (cfg["secagg"]["enabled"] and cfg["secagg"]["groups"] > 1) else "aggregate"
    else:
        bg["screen_resolved"] = bg["screen"]


def validate(cfg: dict[str, Any]) -> None:
    t, d, sa, at = cfg["train"], cfg["defense"], cfg["secagg"], cfg["attack"]
    if t["peft"] not in {"head", "decoder", "lora", "full"}:
        raise ValueError(f"train.peft must be head|decoder|lora|full, got {t['peft']!r}")
    if cfg["model"]["source"] not in {"hf", "local", "random"}:
        raise ValueError(f"model.source must be hf|local|random, got {cfg['model']['source']!r}")
    if cfg["data"]["horizon"] >= 144:
        raise ValueError("data.horizon must be < 144 (daily seasonal-naive baseline needs h < 144)")
    if cfg["fl"]["rounds"] < 1:
        raise ValueError("fl.rounds must be >= 1")
    if cfg["engine"]["name"] not in {"local", "flower"}:
        raise ValueError("engine.name must be local|flower")
    if d["aggregator"] not in AGGREGATORS:
        raise ValueError(f"defense.name {d['name']!r} unknown; choose from {sorted(AGGREGATORS | set(SHORTCUTS))}")
    bad = set(d["addons"]) - ADDONS
    if bad:
        raise ValueError(f"unknown defense.addons {sorted(bad)}; allowed {sorted(ADDONS)}")
    if "lora_reset" in d["addons"] and t["peft"] != "lora":
        raise ValueError("defense lora_reset requires train.peft = lora")
    if cfg["burstguard"]["on_flag"] not in {"regroup", "reject"}:
        raise ValueError("burstguard.on_flag must be regroup|reject")
    if at["type"] not in ATTACKS:
        raise ValueError(f"attack.type must be one of {sorted(ATTACKS)}")
    n = int(cfg["data"]["num_sites"])
    if at["type"] != "none" and not at["malicious_sites"] and int(at["num_malicious"]) < 1:
        raise ValueError("attack.num_malicious must be >= 1 when an attack is enabled")
    if at["type"] != "none" and int(at["num_malicious"]) >= n and not at["malicious_sites"]:
        raise ValueError("attack.num_malicious must be smaller than data.num_sites")
    if sa["enabled"]:
        g = int(sa["groups"])
        if g < 1 or g > n:
            raise ValueError("secagg.groups must be in [1, num_sites]")
        if g == 1 and d["aggregator"] not in AGGREGATE_ONLY:
            raise ValueError(f"defense {d['aggregator']!r} needs individual updates and is incompatible with "
                             f"secure aggregation (secagg.groups=1). Use fedavg/clip_noise/burstguard/lora_reset, "
                             f"or grouped secure aggregation (secagg.groups>1).")
        if d["aggregator"] == "clip_noise" and float(d["clip_norm"]) <= 0:
            raise ValueError("clip_noise under secure aggregation needs an explicit defense.clip_norm > 0 "
                             "(clipping happens on the clients; the server cannot see norms)")
        if cfg["engine"]["name"] == "flower" and g > 1:
            raise ValueError("grouped secure aggregation is only available in the local engine")
    if cfg["engine"]["name"] == "flower" and at["type"] == "neurotoxin":
        raise ValueError("the neurotoxin attack needs the previous global update on the client; "
                         "it is only available in the local engine")
    if d["aggregator"] in {"krum", "multikrum"}:
        units = int(sa["groups"]) if sa["enabled"] else n
        if units < 2 * int(d["krum_f"]) + 3:
            raise ValueError(f"krum needs n >= 2f+3 update units (have {units}, f={d['krum_f']})")


def dump_toml(cfg: dict[str, Any]) -> str:
    def fmt(v: Any) -> str:
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, (int, float)):
            return repr(v)
        if isinstance(v, list):
            return "[" + ", ".join(fmt(x) for x in v) + "]"
        return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = []
    for sec, body in cfg.items():
        if sec.startswith("_") or not isinstance(body, dict):
            continue
        lines.append(f"[{sec}]")
        for k, v in body.items():
            if not isinstance(v, dict):
                lines.append(f"{k} = {fmt(v)}")
        lines.append("")
    return "\n".join(lines)
