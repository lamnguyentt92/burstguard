"""Đường dẫn dự án và cô lập môi trường.

Mọi thư mục cache/tạm của thư viện bên thứ ba được trỏ vào bên trong thư mục dự án
(trừ khi người dùng đã tự đặt biến môi trường), để không đụng tới ~/.cache hay dịch vụ khác.
Module này phải được import TRƯỚC torch/transformers/ray.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    env = os.environ.get("BURSTGUARD_ROOT")
    if env:
        return Path(env).resolve()
    # src/burstguard/paths.py -> gốc dự án là parents[2]
    here = Path(__file__).resolve()
    cand = here.parents[2]
    if (cand / "pyproject.toml").exists():
        return cand
    return Path.cwd().resolve()


ROOT = project_root()
RUNS_DIR = ROOT / "runs"
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
PROCESSED_DIR = DATA_DIR / "processed"
CACHE_DIR = ROOT / ".cache"


def isolate_environment() -> None:
    """Đặt cache của HF/torch/matplotlib vào trong dự án; giới hạn luồng BLAS mặc định."""
    defaults = {
        "HF_HOME": str(CACHE_DIR / "huggingface"),
        "TORCH_HOME": str(CACHE_DIR / "torch"),
        "MPLCONFIGDIR": str(CACHE_DIR / "matplotlib"),
        "XDG_CACHE_HOME": str(CACHE_DIR / "xdg"),
        "TOKENIZERS_PARALLELISM": "false",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "RAY_USAGE_STATS_ENABLED": "0",
        "RAY_DEDUP_LOGS": "0",
        "TSFM_PYTHON_LOGGING_LEVEL": "WARNING",
        "TRANSFORMERS_VERBOSITY": "error",
        # Mỗi tiến trình mặc định 1 luồng BLAS; cấu hình [sim].torch_threads có thể đổi.
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    for k, v in defaults.items():
        os.environ.setdefault(k, v)
    for d in (CACHE_DIR, RUNS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def in_virtualenv() -> bool:
    return sys.prefix != getattr(sys, "base_prefix", sys.prefix)


def resolve(p: str | os.PathLike) -> Path:
    """Đường dẫn tương đối được hiểu là tương đối với gốc dự án."""
    p = Path(p)
    return p if p.is_absolute() else (ROOT / p)
