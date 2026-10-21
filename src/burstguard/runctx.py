"""Ngữ cảnh một lần chạy: thư mục runs/<id>/, ghi log console ở mức file-descriptor,
sự kiện JSONL, summary.json (status=success|failed|interrupted) và error.txt.

Mục tiêu: dù chạy thành công hay thất bại, `bash scripts/collect_logs.sh` luôn có đủ
thông tin để phân tích.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import platform
import shlex
import socket
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

from burstguard import __version__
from burstguard.paths import ROOT, RUNS_DIR


def _now() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def git_info() -> dict[str, str]:
    def _run(*args: str) -> str:
        try:
            return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True,
                                  text=True, timeout=5).stdout.strip()
        except Exception:
            return ""
    return {"commit": _run("rev-parse", "--short", "HEAD"),
            "branch": _run("rev-parse", "--abbrev-ref", "HEAD"),
            "describe": _run("describe", "--tags", "--always", "--dirty"),
            "dirty": "yes" if _run("status", "--porcelain") else "no"}


class _FdTee:
    """Nhân bản fd 1 và 2 vào file log thông qua tiến trình `tee` (bắt cả output của
    thư viện C, logging của Flower và log chuyển tiếp từ worker Ray)."""

    def __init__(self, logfile: Path):
        self.logfile = logfile
        self.proc = None
        self.saved: list[int] = []

    def start(self) -> None:
        sys.stdout.flush(); sys.stderr.flush()
        try:
            self.proc = subprocess.Popen(["tee", "-a", str(self.logfile)], stdin=subprocess.PIPE)
        except FileNotFoundError:  # không có `tee` -> chỉ ghi file
            self.proc = None
            fh = open(self.logfile, "a", buffering=1)
            self.saved = [os.dup(1), os.dup(2)]
            os.dup2(fh.fileno(), 1); os.dup2(fh.fileno(), 2)
            self._fh = fh
            return
        self.saved = [os.dup(1), os.dup(2)]
        os.dup2(self.proc.stdin.fileno(), 1)
        os.dup2(self.proc.stdin.fileno(), 2)

    def stop(self) -> None:
        try:
            sys.stdout.flush(); sys.stderr.flush()
        except Exception:
            pass
        if self.saved:
            os.dup2(self.saved[0], 1); os.dup2(self.saved[1], 2)
            for fd in self.saved:
                os.close(fd)
            self.saved = []
        if self.proc is not None:
            try:
                self.proc.stdin.close()
                self.proc.wait(timeout=10)
            except Exception:
                pass
        elif hasattr(self, "_fh"):
            self._fh.close()


class RunContext:
    def __init__(self, command: str, name: str | None = None, argv: list[str] | None = None):
        ts = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
        safe = "".join(c if c.isalnum() or c in "-_." else "-" for c in (name or ""))
        self.run_id = f"{ts}_{command}" + (f"_{safe}" if safe else "")
        self.dir = RUNS_DIR / self.run_id
        i = 1
        while self.dir.exists():
            self.dir = RUNS_DIR / f"{self.run_id}-{i}"; i += 1
        self.dir.mkdir(parents=True)
        self.command = command
        self.argv = argv if argv is not None else sys.argv
        self.t0 = time.time()
        self.summary: dict[str, Any] = {}
        self._tee = _FdTee(self.dir / "console.log")
        self._events = open(self.dir / "events.jsonl", "a", buffering=1)

    # ---- API dùng trong mã thí nghiệm ----
    def event(self, kind: str, **data: Any) -> None:
        rec = {"t": round(time.time() - self.t0, 3), "kind": kind, **data}
        self._events.write(json.dumps(rec, default=_json_default) + "\n")

    def save_json(self, name: str, obj: Any) -> Path:
        p = self.dir / name
        p.write_text(json.dumps(obj, indent=2, default=_json_default, ensure_ascii=False))
        return p

    def set(self, **kv: Any) -> None:
        self.summary.update(kv)

    # ---- vòng đời ----
    def __enter__(self) -> "RunContext":
        self._tee.start()
        (self.dir / "command.txt").write_text(" ".join(shlex.quote(a) for a in self.argv) + "\n")
        (RUNS_DIR / "LATEST").write_text(str(self.dir) + "\n")
        print(f"[burstguard {__version__}] run dir: {self.dir}", flush=True)
        self.save_json("env.json", basic_env())
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        status = "success"
        if exc_type is not None:
            status = "interrupted" if issubclass(exc_type, KeyboardInterrupt) else "failed"
            err = "".join(traceback.format_exception(exc_type, exc, tb))
            (self.dir / "error.txt").write_text(err)
            print(err, file=sys.stderr, flush=True)
            self.summary.update(error_type=exc_type.__name__, error_message=str(exc)[:2000])
            try:
                from burstguard.hints import hint_for
                h = hint_for(exc)
            except Exception:
                h = None
            if h:
                self.summary["hint"] = h
                print(f"\n[burstguard] GỢI Ý: {h}", file=sys.stderr, flush=True)
        summ = {
            "status": status, "command": self.command, "run_id": self.dir.name,
            "version": __version__, "git": git_info(),
            "started": _dt.datetime.fromtimestamp(self.t0).astimezone().isoformat(timespec="seconds"),
            "ended": _now(), "duration_s": round(time.time() - self.t0, 1),
            **self.summary,
        }
        self.save_json("summary.json", summ)
        if status == "success":
            print(f"\n[burstguard] RUN OK ({summ['duration_s']}s) -> {self.dir}", flush=True)
        else:
            print(f"\n[burstguard] RUN {status.upper()} -> {self.dir}\n"
                  f"[burstguard] Gửi log để phân tích: bash scripts/collect_logs.sh", flush=True)
        self._events.close()
        self._tee.stop()
        return False  # không nuốt exception -> mã thoát != 0


def basic_env() -> dict[str, Any]:
    info: dict[str, Any] = {
        "time": _now(), "host": socket.gethostname(), "platform": platform.platform(),
        "python": sys.version.split()[0], "executable": sys.executable,
        "in_venv": sys.prefix != getattr(sys, "base_prefix", sys.prefix),
        "cpu_count": os.cpu_count(), "cwd": os.getcwd(), "root": str(ROOT),
        "burstguard": __version__, "git": git_info(),
    }
    try:
        info["sched_affinity"] = len(os.sched_getaffinity(0))
    except Exception:
        pass
    try:
        with open("/proc/meminfo") as f:
            m = {l.split(":")[0]: l.split(":")[1].strip() for l in f if ":" in l}
        info["mem_total"] = m.get("MemTotal"); info["mem_available"] = m.get("MemAvailable")
    except Exception:
        pass
    for k in ("OMP_NUM_THREADS", "HF_HOME", "HF_HUB_OFFLINE", "VIRTUAL_ENV", "BURSTGUARD_ROOT"):
        info[f"env.{k}"] = os.environ.get(k)
    return info


def _json_default(o: Any) -> Any:
    try:
        import numpy as np
        if isinstance(o, np.generic):
            return o.item()
        if isinstance(o, np.ndarray):
            return o.tolist()
    except Exception:
        pass
    if isinstance(o, Path):
        return str(o)
    return str(o)
