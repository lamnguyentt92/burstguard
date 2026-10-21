"""Đọc dữ liệu Telecom Italia Big Data Challenge — Milan (Barlacchi et al., Scientific Data 2015, ODbL).

Định dạng file gốc (một file/ngày, ví dụ `sms-call-internet-mi-2013-11-01.txt`), phân tách TAB, không header:
    square_id, time_interval(ms epoch UTC), country_code, smsin, smsout, callin, callout, internet
Ô trống = không có hoạt động. Một (square, time) có nhiều dòng (mỗi country_code một dòng) -> cộng lại.
Một số bản sao trên mạng có header (CellID, datetime, countrycode, ..., internet) và/hoặc phân tách bằng dấu phẩy;
hàm đọc tự nhận diện các biến thể đó. File có thể ở dạng .txt, .csv, .gz, .zip.

Lưới Milan 100x100 ô (~235 m), ID 1..10000, giả định đánh số theo hàng: id-1 = row*100 + col.
"""
from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd

from burstguard.data.store import FREQ_MIN, SLOTS_PER_DAY, split_bounds

GRID = 100
# 2013-11-01 00:00 giờ Milan (CET = UTC+1) = 2013-10-31 23:00 UTC
T0_MS = 1383260400000
SLOT_MS = FREQ_MIN * 60 * 1000
DAYS_DEFAULT = 62
FILE_RE = re.compile(r"sms-call-internet-(mi|tn)-(\d{4}-\d{2}-\d{2})")

NAME_ALIASES = {
    "square": {"square_id", "squareid", "cellid", "cell_id", "gridid", "grid_id", "square"},
    "time": {"time_interval", "timeinterval", "datetime", "time", "timestamp"},
    "internet": {"internet", "internet_traffic", "internettraffic"},
}


def list_raw_files(raw_dir: str | Path, region: str = "mi") -> list[Path]:
    raw_dir = Path(raw_dir)
    files = []
    for p in sorted(raw_dir.rglob("*")):
        if p.is_file():
            m = FILE_RE.search(p.name)
            if m and m.group(1) == region:
                files.append(p)
    return files


def _open_text(path: Path) -> io.TextIOBase | str:
    name = path.name.lower()
    if name.endswith(".zip"):
        zf = zipfile.ZipFile(path)
        members = [n for n in zf.namelist() if not n.endswith("/")]
        if not members:
            raise ValueError(f"File zip rỗng: {path}")
        return io.TextIOWrapper(zf.open(members[0]), encoding="utf-8", errors="replace")
    return str(path)  # pandas tự giải nén .gz/.bz2/.xz theo đuôi file


def _sniff(path: Path) -> tuple[str, bool]:
    """Trả về (delimiter, has_header)."""
    src = _open_text(path)
    if isinstance(src, str):
        import gzip, bz2, lzma
        opener = {".gz": gzip.open, ".bz2": bz2.open, ".xz": lzma.open}.get(Path(src).suffix.lower(), open)
        with opener(src, "rt", encoding="utf-8", errors="replace") as f:
            first = f.readline()
    else:
        first = src.readline()
        src.close()
    delim = "\t" if "\t" in first else ","
    tok = first.strip().split(delim)[0].strip().strip('"')
    has_header = not tok.replace(".", "", 1).isdigit()
    return delim, has_header


def read_day(path: str | Path, squares: set[int] | None = None) -> pd.DataFrame:
    """Đọc một file ngày -> DataFrame [square:int, slot:int, internet:float], đã cộng qua country_code."""
    path = Path(path)
    delim, has_header = _sniff(path)
    src = _open_text(path)
    if has_header:
        df = pd.read_csv(src, sep=delim, low_memory=False)
        cols = {c: c.strip().lower() for c in df.columns}
        df = df.rename(columns=cols)
        pick = {}
        for want, aliases in NAME_ALIASES.items():
            hit = [c for c in df.columns if c in aliases]
            if not hit:
                raise ValueError(f"{path.name}: không tìm thấy cột '{want}' trong header {list(df.columns)}")
            pick[want] = hit[0]
        df = df[[pick["square"], pick["time"], pick["internet"]]]
        df.columns = ["square", "time", "internet"]
    else:
        df = pd.read_csv(src, sep=delim, header=None, usecols=[0, 1, 7],
                         names=["square", "time", "internet"], low_memory=False)
    df = df.dropna(subset=["square", "time"])
    df["square"] = df["square"].astype(np.int64)
    if squares is not None:
        df = df[df["square"].isin(squares)]
    t = df["time"]
    if pd.api.types.is_numeric_dtype(t):
        ms = t.astype(np.int64)
    else:  # chuỗi thời gian (giờ địa phương) trong một số bản sao
        ts = pd.to_datetime(t)
        if ts.dt.tz is None:
            ts = ts.dt.tz_localize("Europe/Rome")
        ms = (ts.dt.tz_convert("UTC").astype("int64") // 1_000_000)
    df["slot"] = ((ms - T0_MS) // SLOT_MS).astype(np.int64)
    df["internet"] = pd.to_numeric(df["internet"], errors="coerce").fillna(0.0)
    return df.groupby(["square", "slot"], as_index=False)["internet"].sum()


def build_square_matrix(files: Iterable[Path], squares: list[int], T: int,
                        log=print) -> tuple[np.ndarray, dict]:
    """Ghép các file ngày thành ma trận [len(squares), T]. Khe vắng của một ô -> 0 (không hoạt động);
    khe vắng của MỌI ô (mất dữ liệu) -> nội suy tuyến tính."""
    sq_index = {s: i for i, s in enumerate(squares)}
    M = np.zeros((len(squares), T), dtype=np.float64)
    seen = np.zeros(T, dtype=bool)
    sqset = set(squares)
    files = list(files)
    for k, f in enumerate(files, 1):
        df = read_day(f, sqset)
        df = df[(df["slot"] >= 0) & (df["slot"] < T)]
        rows = df["square"].map(sq_index).to_numpy()
        cols = df["slot"].to_numpy()
        np.add.at(M, (rows, cols), df["internet"].to_numpy())
        seen[np.unique(cols)] = True
        log(f"  [{k}/{len(files)}] {f.name}: {len(df):,} bản ghi, {len(np.unique(cols))} khe")
    gaps = np.where(~seen)[0]
    if len(gaps) and seen.any():
        idx = np.arange(T)
        for i in range(M.shape[0]):
            M[i, ~seen] = np.interp(idx[~seen], idx[seen], M[i, seen])
    stats = {"files": len(files), "slots_total": T, "slots_missing_all_squares": int(len(gaps)),
             "missing_frac": float(len(gaps) / T)}
    return M.astype(np.float32), stats


def choose_blocks(num_sites: int, num_probe: int, block: int = 5, grid: int = GRID):
    """Chọn các khối block×block ô không chồng nhau, trải từ trung tâm ra ngoại vi.
    Site lấy theo các phân vị khoảng cách tới tâm; probe lấy xen kẽ giữa các site (không trùng ô)."""
    nb = grid // block
    centers = []
    for br in range(nb):
        for bc in range(nb):
            r, c = br * block + (block - 1) / 2, bc * block + (block - 1) / 2
            d = float(np.hypot(r - (grid - 1) / 2, c - (grid - 1) / 2))
            centers.append((d, br, bc))
    centers.sort()
    total = num_sites + num_probe
    usable = int(len(centers) * 0.8)  # bỏ 20% khối xa nhất (góc lưới, hoạt động rất thấp)
    if total > usable:
        raise ValueError(f"Yêu cầu {total} khối nhưng chỉ có {usable} khối dùng được với block={block}")
    picks = np.linspace(0, usable - 1, total).round().astype(int).tolist()  # tăng dần, không trùng
    if num_probe:
        probe_idx = set(np.linspace(1, total - 2, num_probe).round().astype(int).tolist())
        while len(probe_idx) < num_probe:  # phòng trường hợp làm tròn trùng
            probe_idx.add(next(i for i in range(total) if i not in probe_idx))
    else:
        probe_idx = set()
    site_pos = [p for i, p in enumerate(picks) if i not in probe_idx]
    probe_pos = [p for i, p in enumerate(picks) if i in probe_idx]
    def squares_of(pos):
        _, br, bc = centers[pos]
        return [(br * block + dr) * grid + (bc * block + dc) + 1 for dr in range(block) for dc in range(block)]
    sites = [{"site": i, "block_row": centers[p][1], "block_col": centers[p][2],
              "dist_center": round(centers[p][0], 1), "squares": squares_of(p)} for i, p in enumerate(site_pos)]
    probes = [{"probe": i, "block_row": centers[p][1], "block_col": centers[p][2],
               "dist_center": round(centers[p][0], 1), "squares": squares_of(p)} for i, p in enumerate(probe_pos)]
    return sites, probes


def prepare(raw_dir: str | Path, num_sites: int = 20, num_probe: int = 8, block: int = 5,
            days: int = DAYS_DEFAULT, log=print):
    files = list_raw_files(raw_dir, "mi")
    if not files:
        raise FileNotFoundError(
            f"Không tìm thấy file 'sms-call-internet-mi-YYYY-MM-DD.*' trong {raw_dir}. "
            f"Tải bằng `burstguard data download` hoặc chép file vào thư mục này.")
    T = days * SLOTS_PER_DAY
    sites, probes = choose_blocks(num_sites, num_probe, block)
    if len(sites) < num_sites or len(probes) < num_probe:
        raise ValueError("Không chọn đủ khối site/probe — giảm num_sites/num_probe hoặc block.")
    all_sq = sorted({s for g in sites + probes for s in g["squares"]})
    log(f"Đọc {len(files)} file, giữ {len(all_sq)} ô ({num_sites} site + {num_probe} probe, khối {block}x{block})")
    M, stats = build_square_matrix(files, all_sq, T, log=log)
    pos = {s: i for i, s in enumerate(all_sq)}
    def agg(groups):
        return np.stack([M[[pos[s] for s in g["squares"]]].sum(axis=0) for g in groups])
    series, probe = agg(sites), agg(probes)
    covered = sorted({FILE_RE.search(f.name).group(2) for f in files})
    meta = {"source": "milan", "freq_min": FREQ_MIN, "start": "2013-11-01T00:00:00+01:00",
            "block": block, "sites": sites, "probes": probes, "raw_stats": stats,
            "dates_covered": [covered[0], covered[-1]], "num_files": len(files),
            "license": "ODbL — Telecom Italia Big Data Challenge (Barlacchi et al. 2015)"}
    return series, probe, meta, split_bounds(T)
