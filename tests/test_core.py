"""Fast unit tests (no network): config, windows, Milan reader, model modes, attacks, defenses, grids, analysis."""
import gzip
import os

os.environ.setdefault("BURSTGUARD_SKIP_VENV_CHECK", "1")

import numpy as np
import pytest

from burstguard.paths import isolate_environment

isolate_environment()

from burstguard.attacks.trigger import apply_trigger, target
from burstguard.config import load_config
from burstguard.data import milan
from burstguard.data.store import load_dataset, save_dataset, split_bounds
from burstguard.data.synthetic import generate
from burstguard.data.windows import make_windows, seasonal_naive
from burstguard.defenses import aggregators as AGG
from burstguard.defenses.secagg import make_groups, secure_mean
from burstguard import metrics as MT


def test_config_validation():
    cfg = load_config(None, ["train.peft=lora", "fl.rounds=3", 'defense.name="burstguard"'])
    assert cfg["defense"]["aggregator"] == "fedavg" and "burstguard" in cfg["defense"]["addons"]
    with pytest.raises(ValueError):
        load_config(None, ["train.peft=bogus"])
    with pytest.raises(ValueError, match="secure aggregation"):
        load_config(None, ["secagg.enabled=true", 'defense.name="krum"'])
    with pytest.raises(ValueError, match="clip_norm"):
        load_config(None, ["secagg.enabled=true", 'defense.name="clip_noise"'])
    ok = load_config(None, ["secagg.enabled=true", "secagg.groups=5", 'defense.name="median"'])
    assert ok["burstguard"]["screen_resolved"] == "units"
    with pytest.raises(ValueError, match="lora"):
        load_config(None, ['defense.name="lora_reset"', 'train.peft="head"'])


def test_split_bounds_and_windows():
    b = split_bounds(62 * 144)
    assert b["train"] == [0, 37 * 144] and b["val"] == [37 * 144, 44 * 144]
    x = np.arange(62 * 144, dtype=np.float32)
    X, Y, t0 = make_windows(x, *b["val"], L=512, H=36, stride=6)
    assert X.shape[1:] == (512, 1) and Y.shape[1:] == (36, 1)
    assert (Y[:, 0, 0] == t0).all() and (X[:, -1, 0] == t0 - 1).all()
    assert (seasonal_naive(x, t0, 36, 144)[:, 0, 0] == t0 - 144).all()


def _write_fake_day(path, day_index, squares, gz=False, header=False):
    rng = np.random.default_rng(day_index)
    lines = ["CellID,datetime,countrycode,smsin,smsout,callin,callout,internet"] if header else []
    sep = "," if header else "\t"
    for slot in range(144):
        ms = milan.T0_MS + (day_index * 144 + slot) * milan.SLOT_MS
        for sq in squares:
            for cc in (39, 33):
                lines.append(sep.join([str(sq), str(ms), str(cc), "", "0.1", "", "", f"{rng.uniform(1, 10):.4f}"]))
    data = "\n".join(lines) + "\n"
    if gz:
        with gzip.open(path, "wt") as f:
            f.write(data)
    else:
        path.write_text(data)


def test_milan_reader_and_prepare(tmp_path):
    sites, probes = milan.choose_blocks(3, 2, block=2)
    sq_all = {s for g in sites + probes for s in g["squares"]}
    assert len(sq_all) == 5 * 4
    raw = tmp_path / "raw"; raw.mkdir()
    for d in range(3):
        name = f"sms-call-internet-mi-2013-11-0{d + 1}.txt" + (".gz" if d == 1 else "")
        _write_fake_day(raw / name, d, sorted(sq_all), gz=(d == 1), header=(d == 2))
    s, p, meta, b = milan.prepare(raw, num_sites=3, num_probe=2, block=2, days=3)
    assert s.shape == (3, 3 * 144) and p.shape == (2, 3 * 144) and (s > 0).all()
    ds = load_dataset(save_dataset(tmp_path / "m.npz", s, p, meta, b))
    assert ds.num_sites == 3 and ds.meta["data_format"] == 1


def test_trigger_and_backdoor_metrics():
    X = np.ones((4, 512, 1), np.float32)
    Xt = apply_trigger(X, 2.0, {"amplitude": 1.5, "width": 3, "offset": 0, "shape": "rect"})
    assert np.allclose(Xt[:, -3:, 0], 4.0) and np.allclose(Xt[:, :-3, 0], 1.0)
    Y = np.full((4, 36, 1), 10.0, np.float32)
    tgt = target(Y, {"target_ratio": 0.3})
    assert MT.asr(tgt, Y, 0.3, 0.5) == 1.0 and MT.asr(Y, Y, 0.3, 0.5) == 0.0
    assert MT.target_error(tgt, Y, 0.3) < 1e-6
    assert MT.attack_effect(Y, tgt) == pytest.approx(0.7, abs=1e-6)
    assert MT.upr(tgt, Y, 0.8) == 1.0


def test_aggregators_resist_outliers():
    rng = np.random.default_rng(0)
    cfg = load_config(None, ["defense.krum_f=2", "defense.trim_beta=0.2"])
    honest = [rng.normal(0, 0.01, 50).astype(np.float32) + 1.0 for _ in range(10)]
    bad = [np.full(50, 50.0, np.float32), np.full(50, -40.0, np.float32)]
    units = honest + bad
    ctx = {"cfg": cfg, "rng": rng}
    for name in ("krum", "multikrum", "median", "trimmed", "flame"):
        agg, info = AGG.aggregate(name, units, ctx)
        assert np.abs(agg - 1.0).max() < 0.2, name
    agg, _ = AGG.aggregate("fedavg", units, ctx)
    assert np.abs(agg - 1.0).max() > 0.5
    ctx["server_update"] = lambda: np.ones(50, np.float32)
    agg, info = AGG.aggregate("fltrust", units, ctx)
    assert info["trust"][-1] == 0.0 and np.abs(agg - 1.0).max() < 0.2


def test_secure_mean_and_groups():
    rng = np.random.default_rng(1)
    cfg = load_config(None, [])
    thetas = [rng.normal(0, 1, 1000).astype(np.float32) for _ in range(5)]
    m, info = secure_mean(thetas, cfg, rng)
    assert np.abs(m - np.mean(thetas, axis=0)).max() < 1e-4 and info["clipped_values"] == 0
    big = [np.full(10, 20.0, np.float32)]
    m2, info2 = secure_mean(big, cfg, rng)
    assert info2["clipped_values"] == 10 and np.allclose(m2, 8.0, atol=1e-4)
    g = make_groups(20, 3, rng)
    assert sorted(i for x in g for i in x) == list(range(20)) and len(g) == 3


def test_model_modes_vectors_and_lora_reset():
    from burstguard import model as M
    from burstguard.defenses.lora_reset import LoraReset
    cfg = load_config(None, ['model.source="random"'])
    s, _, _, b = generate(1, 0, seed=0)
    X, _, _ = make_windows(s[0], *b["train"], L=512, H=36, stride=50)
    base, info = M.load_model(cfg)
    assert info.freq_prefix and M.predict(base, X[:4]).shape == (4, 36, 1)
    counts = {}
    for mode in ("head", "decoder", "lora", "full"):
        m = M.configure_peft(M.load_model(cfg)[0], {**cfg, "train": {**cfg["train"], "peft": mode}})
        v = M.get_vec(m)
        M.set_vec(m, v * 0 + 0.5)
        assert np.allclose(M.get_vec(m), 0.5)
        counts[mode] = v.size
    assert counts["head"] < counts["decoder"] < counts["full"] and counts["head"] < counts["lora"] < counts["full"]
    m = M.configure_peft(M.load_model(cfg)[0], cfg)
    assert M.check_head_cache(m, X, 36) < 1e-5
    lm = M.configure_peft(M.load_model(cfg)[0], {**cfg, "train": {**cfg["train"], "peft": "lora"}})
    init = M.get_vec(lm)
    lr = LoraReset(M.lora_segments(lm), init, every=5, frac=0.5, cooldown=500)
    changed = init + 1.0
    out, inf = lr.apply(changed, 5)
    assert inf["reset"] > 0 and (out == init).sum() > 0 and (out != init).sum() > 0
    assert lr.apply(changed, 6)[1]["reset"] == 0


def test_grid_expand_shard_exclude(tmp_path):
    from burstguard.experiments.grid import expand, load_grid, shard
    p = tmp_path / "g.toml"
    p.write_text('[grid]\nname="t"\nseeds=[0,1]\n[factors]\n"train.peft"=["head","lora"]\n'
                 '"defense.name"=["fedavg","lora_reset"]\n[[exclude]]\n"defense.name"="lora_reset"\n"train.peft"="head"\n')
    jobs = expand(load_grid(p))
    assert len(jobs) == 6 and len({j["id"] for j in jobs}) == 6
    parts = [shard(jobs, k, 3) for k in (1, 2, 3)]
    assert sorted(j["id"] for x in parts for j in x) == sorted(j["id"] for j in jobs)
    assert expand(load_grid(p))[0]["id"] == jobs[0]["id"]  # stable ids
    p.write_text('[grid]\nname="v"\nseeds=[0]\n[factors]\n"attack.type"=["none","scale"]\n'
                 '[[variants]]\n[[variants]]\n"burstguard.steps"=5\n[[include]]\n"trigger.amplitude"=3.0\n')
    jv = expand(load_grid(p))
    assert len(jv) == 5 and sum(j["overrides"].get("burstguard.steps") == 5 for j in jv) == 2


def test_analysis_helpers():
    from burstguard.experiments.analyze import bootstrap_ci, holm, lifespan
    v, cens = lifespan([2, 4, 6, 8, 10, 12], [0.1, 0.8, 0.9, 0.6, 0.4, 0.2], start=2, end=6, rounds=12)
    assert v == 4.0 and not cens
    v, cens = lifespan([2, 4, 6, 8], [0.9, 0.9, 0.9, 0.9], start=2, end=4, rounds=8)
    assert cens and v == 4.0
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    mu, lo, hi = bootstrap_ci([[1.0, 1.0, 1.0], [1.0, 1.0]])
    assert mu == lo == hi == 1.0
    from burstguard.engines.common import auc
    from burstguard.experiments.analyze import roc_curve
    assert auc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == 1.0 and auc([0.5, 0.5], [0, 1]) == 0.5
    assert auc([0.1, 0.2], [0, 0]) is None
    fpr, tpr = roc_curve([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1])
    assert fpr[0] == tpr[0] == 0.0 and fpr[-1] == tpr[-1] == 1.0 and (0.0, 1.0) in set(zip(fpr, tpr))
