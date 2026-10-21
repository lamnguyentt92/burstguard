"""Thước đo dự báo: MAE, MASE (so với seasonal-naive theo ngày), sMAPE."""
from __future__ import annotations

import numpy as np

from burstguard.data.store import SLOTS_PER_DAY


def mae(pred: np.ndarray, y: np.ndarray) -> float:
    return float(np.mean(np.abs(pred - y))) if y.size else float("nan")


def smape(pred: np.ndarray, y: np.ndarray, eps: float = 1e-8) -> float:
    if not y.size:
        return float("nan")
    return float(np.mean(2 * np.abs(pred - y) / (np.abs(pred) + np.abs(y) + eps)) * 100)


def mase(pred: np.ndarray, y: np.ndarray, naive: np.ndarray) -> float:
    """MAE(mô hình) / MAE(seasonal-naive) trên cùng tập cửa sổ. < 1 nghĩa là tốt hơn baseline mùa vụ."""
    d = mae(naive, y)
    return float(mae(pred, y) / d) if d > 0 else float("nan")


DAILY_LAG = SLOTS_PER_DAY
WEEKLY_LAG = 7 * SLOTS_PER_DAY
