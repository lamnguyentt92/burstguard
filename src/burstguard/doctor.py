"""`burstguard doctor`: kiểm tra môi trường trước khi chạy thí nghiệm. In PASS/WARN/FAIL từng mục."""
from __future__ import annotations

import importlib
import importlib.metadata as md
import os
import shutil
import sys
import time
from typing import Any

from burstguard.paths import CACHE_DIR, PROCESSED_DIR, RAW_DIR, ROOT, in_virtualenv

EXPECTED = {"flwr": "1.41.0", "torch": "2.11.0", "granite-tsfm": "0.3.10", "transformers": "5.20.2",
            "peft": "0.21.2", "ray": "2.55.1", "numpy": "2.4.6", "pandas": "3.0.6", "scikit-learn": "1.7.2"}
URLS = {
    "pypi": "https://pypi.org/simple/flwr/",
    "huggingface": "https://huggingface.co/api/models/ibm-granite/granite-timeseries-ttm-r2",
    "pytorch_cpu_index": "https://download.pytorch.org/whl/cpu/torch/",
    "dataverse": "https://dataverse.harvard.edu/api/info/version",
    "github": "https://github.com",
}


def _ver(pkg: str) -> str | None:
    try:
        return md.version(pkg)
    except md.PackageNotFoundError:
        return None


def run(check_net: bool = True, log=print) -> dict[str, Any]:
    res: dict[str, Any] = {"checks": []}

    def add(name: str, status: str, detail: str = "") -> None:
        res["checks"].append({"name": name, "status": status, "detail": detail})
        log(f"  [{status:4s}] {name}: {detail}")

    log("== Python & môi trường ảo")
    v = sys.version_info
    add("python", "PASS" if (3, 11) <= v[:2] <= (3, 13) else "FAIL",
        f"{sys.version.split()[0]} ({sys.executable}); yêu cầu 3.11–3.13")
    add("virtualenv", "PASS" if in_virtualenv() else "FAIL",
        f"sys.prefix={sys.prefix}" + ("" if in_virtualenv() else " — hãy `source .venv/bin/activate`"))
    venv = os.environ.get("VIRTUAL_ENV", "")
    if venv and not os.path.realpath(venv).startswith(os.path.realpath(str(ROOT))):
        add("venv_location", "WARN", f"VIRTUAL_ENV={venv} nằm ngoài dự án (khuyến nghị dùng .venv của dự án)")

    log("== Thư viện (phiên bản đã kiểm thử)")
    for pkg, want in EXPECTED.items():
        have = _ver(pkg)
        if have is None:
            add(pkg, "FAIL", "chưa cài")
        else:
            ok = have.split("+")[0] == want
            add(pkg, "PASS" if ok else "WARN", f"{have}" + ("" if ok else f" (đã kiểm thử với {want})"))
    for mod in ("torch", "flwr", "ray", "tsfm_public", "peft", "transformers"):
        t0 = time.time()
        try:
            importlib.import_module(mod)
            add(f"import {mod}", "PASS", f"{time.time() - t0:.1f}s")
        except Exception as e:
            add(f"import {mod}", "FAIL", f"{type(e).__name__}: {e}")

    log("== Phần cứng")
    try:
        import torch
        add("torch_cuda", "PASS", f"cuda={torch.cuda.is_available()} (dự án chỉ cần CPU); threads={torch.get_num_threads()}")
        a = torch.randn(512, 512); t0 = time.time()
        for _ in range(20):
            a @ a
        add("cpu_matmul", "PASS", f"20× matmul 512² trong {time.time() - t0:.2f}s (1 luồng)")
    except Exception as e:
        add("torch_runtime", "FAIL", f"{type(e).__name__}: {e}")
    try:
        ncpu = len(os.sched_getaffinity(0))
    except Exception:
        ncpu = os.cpu_count() or 0
    add("cpu_count", "PASS" if ncpu >= 4 else "WARN", f"{ncpu} CPU khả dụng (khuyến nghị ≥ 4)")
    try:
        with open("/proc/meminfo") as f:
            m = {l.split(":")[0]: int(l.split()[1]) for l in f if l.split()[1].isdigit()}
        avail = m.get("MemAvailable", 0) / 1024 / 1024
        add("memory", "PASS" if avail >= 6 else "WARN", f"{avail:.1f} GiB khả dụng (khuyến nghị ≥ 6 GiB cho 20 client)")
    except Exception:
        pass
    du = shutil.disk_usage(str(ROOT))
    add("disk", "PASS" if du.free > 20e9 else "WARN", f"{du.free / 1e9:.0f} GB trống tại {ROOT} (dữ liệu Milan thô ~ vài chục GB)")
    shm = shutil.disk_usage("/dev/shm") if os.path.exists("/dev/shm") else None
    if shm:
        add("dev_shm", "PASS" if shm.total > 1e9 else "WARN", f"{shm.total / 1e9:.1f} GB (Ray dùng làm object store)")

    log("== Dữ liệu & cache")
    raw = sorted(RAW_DIR.glob("milan/*")) if RAW_DIR.exists() else []
    add("raw_milan", "PASS" if raw else "WARN", f"{len(raw)} file trong {RAW_DIR / 'milan'}" + ("" if raw else " (chưa tải)"))
    proc = sorted(PROCESSED_DIR.glob("*.npz")) if PROCESSED_DIR.exists() else []
    add("processed", "PASS" if proc else "WARN", ", ".join(p.name for p in proc) or "chưa có file .npz")
    add("hf_cache", "PASS", f"HF_HOME={os.environ.get('HF_HOME')} (trong dự án: {str(CACHE_DIR) in str(os.environ.get('HF_HOME'))})")

    if check_net:
        log("== Mạng (timeout 8s mỗi địa chỉ)")
        import requests
        for name, url in URLS.items():
            try:
                r = requests.get(url, timeout=8, headers={"User-Agent": "burstguard-doctor"})
                add(f"net:{name}", "PASS" if r.status_code < 400 else "WARN", f"HTTP {r.status_code} {url}")
            except Exception as e:
                add(f"net:{name}", "WARN", f"{type(e).__name__} {url} — {str(e)[:120]}")
    fails = [c for c in res["checks"] if c["status"] == "FAIL"]
    warns = [c for c in res["checks"] if c["status"] == "WARN"]
    res["n_fail"], res["n_warn"] = len(fails), len(warns)
    log(f"\nKẾT QUẢ doctor: {len(fails)} FAIL, {len(warns)} WARN")
    return res
