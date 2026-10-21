"""Định dạng bộ dữ liệu đã xử lý (.npz) dùng chung cho dữ liệu Milan thật và dữ liệu tổng hợp."""
from __future__ import annotations

import datetime as dt
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

FREQ_MIN = 10
SLOTS_PER_DAY = 24 * 60 // FREQ_MIN  # 144

# Ranh giới split theo ngày (giờ địa phương Milan, CET), tính từ 2013-11-01 00:00.
DEFAULT_SPLITS = {
    "train": ("2013-11-01", "2013-12-08"),
    "val": ("2013-12-08", "2013-12-15"),
    "test": ("2013-12-15", "2013-12-25"),
    "holiday": ("2013-12-25", "2014-01-02"),
}
START_DATE = "2013-11-01"


def split_bounds(T: int, start: str = START_DATE, splits: dict | None = None) -> dict[str, list[int]]:
    """Đổi ranh giới ngày -> chỉ số [a, b) trên trục thời gian (cắt theo độ dài T)."""
    splits = splits or DEFAULT_SPLITS
    d0 = dt.date.fromisoformat(start)
    out = {}
    for name, (a, b) in splits.items():
        ia = (dt.date.fromisoformat(a) - d0).days * SLOTS_PER_DAY
        ib = (dt.date.fromisoformat(b) - d0).days * SLOTS_PER_DAY
        ia, ib = max(0, min(ia, T)), max(0, min(ib, T))
        out[name] = [ia, ib]
    return out


@dataclass
class Dataset:
    series: np.ndarray            # [S, T] float32, đơn vị gốc (không âm)
    probe: np.ndarray             # [P, T] float32 — tập dò của server (vùng không thuộc site nào)
    bounds: dict[str, list[int]]  # split -> [a, b)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def num_sites(self) -> int:
        return int(self.series.shape[0])

    @property
    def T(self) -> int:
        return int(self.series.shape[1])

    def site_scale(self, i: int) -> float:
        """Độ lệch chuẩn trên split train của site i (dùng chuẩn hoá loss)."""
        a, b = self.bounds["train"]
        s = float(np.std(self.series[i, a:b]))
        return s if s > 1e-8 else 1.0


def save_dataset(path: str | Path, series: np.ndarray, probe: np.ndarray,
                 meta: dict[str, Any], bounds: dict | None = None) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    series = np.asarray(series, dtype=np.float32)
    probe = np.asarray(probe, dtype=np.float32)
    if bounds is None:
        bounds = split_bounds(series.shape[1])
    if not np.isfinite(series).all() or not np.isfinite(probe).all():
        raise ValueError("Dữ liệu còn NaN/inf sau xử lý — kiểm tra bước nội suy.")
    np.savez_compressed(path, series=series, probe=probe,
                        bounds=np.array(json.dumps(bounds)),
                        meta=np.array(json.dumps(meta, ensure_ascii=False)))
    return path


def load_dataset(path: str | Path) -> Dataset:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Không thấy dữ liệu {path}. Tạo bằng: `burstguard data synthetic` (thử nhanh) "
            f"hoặc `burstguard data download` rồi `burstguard data prepare` (dữ liệu Milan thật).")
    z = np.load(path, allow_pickle=False)
    return Dataset(series=z["series"], probe=z["probe"],
                   bounds=json.loads(str(z["bounds"])), meta=json.loads(str(z["meta"])))


def describe(ds: Dataset) -> dict[str, Any]:
    a, b = ds.bounds["train"]
    per_site = []
    for i in range(ds.num_sites):
        x = ds.series[i]
        per_site.append({"site": i, "mean": float(x.mean()), "std_train": ds.site_scale(i),
                         "zero_frac": float((x == 0).mean()), "min": float(x.min()), "max": float(x.max())})
    return {"source": ds.meta.get("source"), "num_sites": ds.num_sites, "T": ds.T,
            "days": ds.T / SLOTS_PER_DAY, "num_probe": int(ds.probe.shape[0]),
            "bounds": ds.bounds, "per_site": per_site,
            "meta_keys": sorted(ds.meta.keys())}
