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
    # exclude can match run.seed (fewer seeds for an expensive mode); ids do not depend on the base config
    p.write_text('[grid]\nname="s"\nseeds=[0,1,2]\n[factors]\n"train.peft"=["head","lora"]\n'
                 '[[exclude]]\n"train.peft"="lora"\n"run.seed"=2\n')
    js = expand(load_grid(p))
    assert len(js) == 5 and not any(j["overrides"]["train.peft"] == "lora" and j["overrides"]["run.seed"] == 2
                                    for j in js)
    # cost uses the resolved configuration: rounds from the base config when the grid does not set them
    (tmp_path / "b.toml").write_text('[fl]\nrounds = 40\n')
    p.write_text(f'[grid]\nname="r"\nbase_config="{tmp_path / "b.toml"}"\nseeds=[0]\n[factors]\n'
                 '"train.peft"=["head"]\n')
    jr = expand(load_grid(p))
    assert jr[0]["effective"]["fl.rounds"] == 40 and "fl.rounds" not in jr[0]["overrides"]
    p.write_text('[grid]\nname="r"\nseeds=[0]\n[factors]\n"train.peft"=["head"]\n')
    assert expand(load_grid(p))[0]["id"] == jr[0]["id"] and expand(load_grid(p))[0]["cost"] < jr[0]["cost"]


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


def test_burstguard_replay_rule():
    from burstguard.defenses.burstguard import replay_flags
    drift = [[(0.05, 0.05 + 0.06 * r)] * 4 for r in range(30)]       # smooth benign anchor drift up to ~1.8
    fixed = replay_flags(drift, 0.15, 0.5, 5.0, 5, anchor_adaptive=False)
    adapt = replay_flags(drift, 0.15, 0.5, 5.0, 5, anchor_adaptive=True)
    assert any(any(f) for f in fixed) and not any(any(f) for f in adapt)
    attack = [list(u) for u in drift]
    attack[10][2] = (3.0, 3.5)                                          # one injected unit
    flags = replay_flags(attack, 0.15, 0.5, 5.0, 5, anchor_adaptive=True)
    assert flags[10] == [False, False, True, False] and sum(sum(f) for f in flags) == 1


def test_burstguard_batched_search_matches_sequential():
    """score() runs all (direction, restart) chains as one batch: same value as the chains one after another."""
    import torch
    from burstguard.config import load_config
    from burstguard import model as M
    from burstguard.defenses.burstguard import BurstGuard
    cfg = load_config(None, ['model.source="random"', "burstguard.steps=3", "burstguard.restarts=2",
                             "burstguard.probe_windows=8"])
    m = M.configure_peft(M.load_model(cfg)[0], cfg)
    th = M.get_vec(m)
    rng = np.random.default_rng(0)
    X = (rng.standard_normal((8, int(cfg["data"]["context"]), 1)).cumsum(1) * 0.1 + 5).astype(np.float32)
    bg = BurstGuard(cfg, m, X, X.std(1).ravel(), th)
    cand = th + rng.standard_normal(th.size).astype(np.float32) * 0.01

    def sequential(seed):
        b = bg.bg
        M.set_params_vec(bg._pc, cand); M.set_params_vec(bg._pr, th)
        W, K, R, amax, step = int(b["width_max"]), int(b["steps"]), int(b["restarts"]), float(b["amplitude_max"]), float(b["step_size"])
        Xt, sig, L = bg.X, bg.sig, bg.X.shape[1]
        g0 = torch.Generator().manual_seed(seed)
        with torch.no_grad():
            bc, br = M.forward(bg.cand, Xt, bg.freq), M.forward(bg.ref, Xt, bg.freq)
        best = -1e9
        for sign in (1.0, -1.0):
            for _ in range(R):
                g = torch.rand(Xt.shape[0], W, 1, generator=g0).requires_grad_(True)
                for k in range(K + 1):
                    d = torch.zeros_like(Xt); d[:, L - W:, :] = g * amax * sig
                    v = ((sign * (bc - M.forward(bg.cand, Xt + d, bg.freq)) / (bc.abs() + 1e-3)).mean()
                         - (sign * (br - M.forward(bg.ref, Xt + d, bg.freq)) / (br.abs() + 1e-3)).mean())
                    if k == K:
                        best = max(best, float(v)); break
                    v.backward()
                    with torch.no_grad():
                        g += step * g.grad.sign(); g.clamp_(0.0, 1.0); g.grad.zero_()
        return best
    assert bg.score(cand, th, seed=5) == pytest.approx(sequential(5), abs=1e-6)


def test_rule_replay_from_monitor_run(tmp_path):
    """Monitor-mode runs: other decision rules are replayed on the logged scores (E9 without extra runs)."""
    from burstguard.engines.common import summarize
    (tmp_path / "config.toml").write_text('[burstguard]\nmode = "monitor"\nreference = "both"\nthreshold = 0.1\n'
                                          'threshold_anchor = 0.3\nmad_k = 5.0\nhistory = 5\n'
                                          'anchor_adaptive = true\n')
    lines = []
    for r in range(1, 11):
        att = r >= 6
        sl, sa = (0.5, 0.2) if r == 6 else (0.02, 0.4 if att else 0.05)   # injection, then slow accumulation
        would = sl > 0.1 or sa > 0.3
        lines.append({"kind": "round", "round": r, "attack_active": att, "screened_has_malicious": att,
                      "round_wall_s": 1.0, "server_defense_cpu_s": 0.1,
                      "burstguard": {"scores": [max(sl - 0.1, sa - 0.3) + 0.1], "score_last": [sl],
                                     "score_anchor": [sa], "would_flag": [would], "cpu_s": 0.1}})
    (tmp_path / "metrics.jsonl").write_text("\n".join(__import__("json").dumps(x) for x in lines) + "\n")
    det = summarize(tmp_path)["detection"]
    assert det["rule_replay_agree"] == 1.0
    rf = det["rule_flags"]
    assert rf["last"] == [0, 0, 0, 0, 0, 1, 0, 0, 0, 0]          # S_last only sees the injection round
    assert rf["anchor"] == [0, 0, 0, 0, 0, 0, 1, 1, 1, 1]        # S_anchor only the accumulated rounds
    assert rf["fixed_anchor"] == [0, 0, 0, 0, 0, 1, 1, 1, 1, 1]


def test_plan_cost_model():
    from burstguard.experiments import plan as PL
    fin = [{"peft": "head", "kind": "fl", "rounds": 30, "bg": False, "units": 1, "engine": "local", "wall_s": 300.0},
           {"peft": "head", "kind": "fl", "rounds": 30, "bg": True, "units": 1, "engine": "local", "wall_s": 900.0},
           {"peft": "lora", "kind": "fl", "rounds": 20, "bg": False, "units": 1, "engine": "local", "wall_s": 800.0}]
    m = PL.fit(fin)
    assert m["c"][("head", "fl")] == 10.0 and m["s_bg"] == 20.0 and m["attack_src"] == "prior"
    assert PL.cost_per_round(m, "decoder", "fl") == pytest.approx(40.0 * 0.7)   # derived from LoRA via ratios
    s = PL.job_seconds(m, {"train.peft": "head", "fl.rounds": 30, "defense.name": "burstguard",
                           "secagg.enabled": True, "secagg.groups": 5}, "fl")
    assert s == pytest.approx(30 * (10 + 20 * 5))
    # attacked jobs: straggler factor measured from attacked runs without BurstGuard
    fin.append({"peft": "head", "kind": "fl", "rounds": 20, "bg": False, "units": 1, "engine": "local",
                "wall_s": 500.0, "attacked": True})
    m = PL.fit(fin)
    assert m["attack"] == pytest.approx(2.5) and m["attack_src"].startswith("measured")
    # search effort: 64 probe windows and 20 steps cost more than the default (32 windows, 8 steps)
    f = PL._features({"defense.name": "burstguard", "burstguard.probe_windows": 64, "burstguard.steps": 20,
                      "burstguard.restarts": 2}, "fl")
    assert f["effort"] == pytest.approx(64 * (2 * 2 * 122 + 2) / (32 * (2 * 50 + 2)))
    # enforce + regroup: attacked rounds 6..15 of 40 -> 1 + 10/40 * 5 screened units
    f = PL._features({"defense.name": "burstguard", "attack.type": "scale", "attack.start_round": 6,
                      "attack.end_round": 16, "fl.rounds": 40}, "fl")
    assert f["units"] == pytest.approx(1 + 10 / 40 * 5)


def test_weighted_shards():
    from burstguard.experiments.grid import parse_shard, shard, shard_from_spec
    rng = np.random.default_rng(3)
    jobs = [{"id": f"j{i:03d}", "cost": float(c)} for i, c in enumerate(rng.choice([30, 170, 400, 900], size=300))]
    # unweighted: unchanged round-robin over (-cost, id)
    order = sorted(jobs, key=lambda j: (-j["cost"], j["id"]))
    assert [j["id"] for j in shard(jobs, 2, 5)] == [j["id"] for i, j in enumerate(order) if i % 5 == 1]
    assert parse_shard("2/5") == (2, 5, None)
    w = [4, 1, 3, 1, 3]
    assert parse_shard("3/5@4,1,3,1,3") == (3, 5, [4.0, 1.0, 3.0, 1.0, 3.0])
    parts = [shard_from_spec(jobs, f"{k}/5@4,1,3,1,3") for k in range(1, 6)]
    ids = sorted(j["id"] for p in parts for j in p)
    assert ids == sorted(j["id"] for j in jobs)                      # every job exactly once
    load = [sum(j["cost"] for j in p) for p in parts]
    share = [x / sum(load) for x in load]
    for s_, wi in zip(share, w):
        assert abs(s_ - wi / sum(w)) < 0.03                          # cost proportional to weight
    assert [j["id"] for j in shard_from_spec(jobs, "1/5@4,1,3,1,3")] == [j["id"] for j in parts[0]]  # deterministic
    for bad in ("0/5", "6/5", "2/5@1,2", "2/5@1,1,1,1,0", "x"):
        with pytest.raises(ValueError):
            parse_shard(bad)


def test_exp_code_mixing():
    from burstguard.experiments.analyze import exp_code
    assert exp_code({"version": "0.3.2"}) == exp_code({"version": "0.3.3", "exp_code": "0.3.0"}) == "0.3.0"
    assert exp_code({"version": "0.2.2"}) == "0.2.2"
