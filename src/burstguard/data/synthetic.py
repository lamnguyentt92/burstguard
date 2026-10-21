"""Dữ liệu tổng hợp giống hoạt động Internet Milan (để kiểm thử pipeline khi chưa có dữ liệu thật).

Chuỗi có chu kỳ ngày (thấp ban đêm, đỉnh chiều tối), chu kỳ tuần (cuối tuần thấp hơn),
thang đo khác nhau giữa các site, nhiễu nhân và mức giảm dịp lễ cuối tháng 12.
KHÔNG dùng số liệu tổng hợp cho bài báo.
"""
from __future__ import annotations

import numpy as np

from burstguard.data.store import SLOTS_PER_DAY, split_bounds

DAYS = 62  # 2013-11-01 .. 2014-01-01


def _daily_profile(rng: np.random.Generator) -> np.ndarray:
    h = np.arange(SLOTS_PER_DAY) / SLOTS_PER_DAY * 24.0
    peak = rng.uniform(17.0, 21.0)
    morning = rng.uniform(0.3, 0.6)
    prof = (0.25 + morning * np.exp(-0.5 * ((h - 11.0) / 2.5) ** 2)
            + 1.0 * np.exp(-0.5 * ((h - peak) / 3.0) ** 2)
            + 0.15 * np.exp(-0.5 * ((h - 23.5) / 1.5) ** 2))
    return prof / prof.mean()


def generate(num_sites: int = 20, num_probe: int = 8, days: int = DAYS, seed: int = 0):
    rng = np.random.default_rng(seed)
    T = days * SLOTS_PER_DAY
    t = np.arange(T)
    day_idx = t // SLOTS_PER_DAY
    weekday = (day_idx + 4) % 7          # 2013-11-01 là thứ Sáu (0=thứ Hai)
    holiday = (day_idx >= 54)            # từ 2013-12-25
    n = num_sites + num_probe
    out = np.zeros((n, T), dtype=np.float32)
    for i in range(n):
        scale = float(np.exp(rng.normal(np.log(300.0), 0.8)))
        prof = _daily_profile(rng)
        weekly = np.where(weekday >= 5, rng.uniform(0.7, 0.9), 1.0)
        hol = np.where(holiday, rng.uniform(0.6, 0.85), 1.0)
        trend = 1.0 + rng.uniform(-0.05, 0.08) * (t / T)
        base = scale * prof[t % SLOTS_PER_DAY] * weekly * hol * trend
        ar = np.zeros(T)
        eps = rng.normal(0, 0.06, T)
        for k in range(1, T):
            ar[k] = 0.9 * ar[k - 1] + eps[k]
        x = base * np.exp(ar) * rng.lognormal(0, 0.05, T)
        out[i] = np.maximum(x, 0.0)
    meta = {"source": "synthetic", "seed": seed, "freq_min": 10, "start": "2013-11-01T00:00:00+01:00",
            "sites": [{"site": i, "kind": "synthetic"} for i in range(num_sites)],
            "note": "Dữ liệu tổng hợp chỉ để kiểm thử pipeline — không dùng cho bài báo."}
    return out[:num_sites], out[num_sites:], meta, split_bounds(T)
