"""Kiểm thử nhanh (không cần mạng): cấu hình, cắt cửa sổ, đọc file Milan giả lập, mô hình & PEFT."""
import gzip
import os

os.environ.setdefault("BURSTGUARD_ALLOW_NO_VENV", "1")

import numpy as np
import pytest

from burstguard.paths import isolate_environment

isolate_environment()

from burstguard.config import load_config
from burstguard.data import milan
from burstguard.data.store import load_dataset, save_dataset, split_bounds
from burstguard.data.synthetic import generate
from burstguard.data.windows import make_windows, seasonal_naive


def test_config_overrides():
    cfg = load_config(None, ["train.peft=lora", "fl.rounds=3", 'model.source="random"'])
    assert cfg["train"]["peft"] == "lora" and cfg["fl"]["rounds"] == 3 and cfg["model"]["source"] == "random"
    with pytest.raises(ValueError):
        load_config(None, ["train.peft=bogus"])


def test_split_bounds_and_windows():
    b = split_bounds(62 * 144)
    assert b["train"] == [0, 37 * 144] and b["val"] == [37 * 144, 44 * 144]
    x = np.arange(62 * 144, dtype=np.float32)
    X, Y, t0 = make_windows(x, *b["val"], L=512, H=36, stride=6)
    assert X.shape[1:] == (512, 1) and Y.shape[1:] == (36, 1)
    assert (Y[:, 0, 0] == t0).all() and (X[:, -1, 0] == t0 - 1).all()
    assert (t0 + 36 <= b["val"][1]).all() and (t0 >= b["val"][0]).all()
    nd = seasonal_naive(x, t0, 36, 144)
    assert (nd[:, 0, 0] == t0 - 144).all()


def _write_fake_day(path, day_index, squares, gz=False, header=False):
    rng = np.random.default_rng(day_index)
    lines = []
    if header:
        lines.append("CellID,datetime,countrycode,smsin,smsout,callin,callout,internet")
    sep = "," if header else "\t"
    for slot in range(144):
        ms = milan.T0_MS + (day_index * 144 + slot) * milan.SLOT_MS
        for sq in squares:
            for cc in (39, 33):  # hai country code -> phải được cộng lại
                net = rng.uniform(1, 10)
                row = [str(sq), str(ms), str(cc), "", "0.1", "", "", f"{net:.4f}"]
                lines.append(sep.join(row))
    data = "\n".join(lines) + "\n"
    if gz:
        with gzip.open(path, "wt") as f:
            f.write(data)
    else:
        path.write_text(data)


def test_milan_reader_and_prepare(tmp_path):
    sites, probes = milan.choose_blocks(3, 2, block=2)
    assert len(sites) == 3 and len(probes) == 2
    sq_all = {s for g in sites + probes for s in g["squares"]}
    assert len(sq_all) == 5 * 4  # không trùng ô
    raw = tmp_path / "raw"; raw.mkdir()
    for d in range(3):
        name = f"sms-call-internet-mi-2013-11-0{d + 1}.txt" + (".gz" if d == 1 else "")
        _write_fake_day(raw / name, d, sorted(sq_all), gz=(d == 1), header=(d == 2))
    df = milan.read_day(raw / "sms-call-internet-mi-2013-11-01.txt")
    assert df["slot"].min() == 0 and df["slot"].max() == 143
    s, p, meta, b = milan.prepare(raw, num_sites=3, num_probe=2, block=2, days=3)
    assert s.shape == (3, 3 * 144) and p.shape == (2, 3 * 144)
    assert (s > 0).all() and meta["raw_stats"]["slots_missing_all_squares"] == 0
    out = save_dataset(tmp_path / "m.npz", s, p, meta, b)
    ds = load_dataset(out)
    assert ds.num_sites == 3 and ds.meta["source"] == "milan"


def test_synthetic_roundtrip(tmp_path):
    s, p, meta, b = generate(3, 1, seed=1)
    ds = load_dataset(save_dataset(tmp_path / "s.npz", s, p, meta, b))
    assert ds.series.shape == (3, 62 * 144) and (ds.series >= 0).all()


def test_model_modes_and_head_cache():
    import torch
    from burstguard import model as M
    cfg = load_config(None, ['model.source="random"'])
    s, _, _, b = generate(1, 0, seed=0)
    X, Y, _ = make_windows(s[0], *b["train"], L=512, H=36, stride=50)
    base, info = M.load_model(cfg)
    assert info.freq_prefix  # bản random mô phỏng biến thể -ft- của TTM-R2
    P = M.predict(base, X[:4])
    assert P.shape == (4, 36, 1)
    counts = {}
    for mode in ("head", "decoder", "lora", "full"):
        m, _ = M.load_model(cfg)
        m = M.configure_peft(m, {**cfg, "train": {**cfg["train"], "peft": mode}})
        arrs = M.get_trainable(m)
        counts[mode] = M.n_trainable(m)
        M.set_trainable(m, [a * 0 for a in arrs])
        assert all(np.all(a == 0) for a in M.get_trainable(m))
    assert counts["head"] < counts["decoder"] < counts["full"]
    assert counts["head"] < counts["lora"] < counts["full"]
    m, _ = M.load_model(cfg)
    m = M.configure_peft(m, cfg)
    assert M.check_head_cache(m, X, 36) < 1e-5
