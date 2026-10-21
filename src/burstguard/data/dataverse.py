"""Download the Milan data from Harvard Dataverse (Native API) with resume and MD5 verification.

Barlacchi et al. (2015) published two "Telecommunications activity" datasets (Milan, Trentino) with DOIs
10.7910/DVN/EGZHFV and 10.7910/DVN/QLCABU. Both are queried and only files of the requested region are kept
(`-mi-` Milan, `-tn-` Trentino). Without Dataverse access, download in a browser and copy the files manually.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import requests

from burstguard.data.milan import FILE_RE

SERVER = "https://dataverse.harvard.edu"
TELECOM_DOIS = ["10.7910/DVN/EGZHFV", "10.7910/DVN/QLCABU"]
UA = {"User-Agent": "burstguard-research (+https://github.com/lamnguyentt92/burstguard)"}


def list_files(doi: str, timeout: float = 30) -> list[dict]:
    url = f"{SERVER}/api/datasets/:persistentId/"
    r = requests.get(url, params={"persistentId": f"doi:{doi}"}, headers=UA, timeout=timeout)
    r.raise_for_status()
    data = r.json()["data"]
    files = []
    for f in data["latestVersion"]["files"]:
        df = f.get("dataFile", {})
        name = df.get("originalFileName") or df.get("filename") or f.get("label", "")
        md5 = df.get("md5") or (df.get("checksum") or {}).get("value")
        files.append({"id": df.get("id"), "name": name, "label": f.get("label"),
                      "size": df.get("originalFileSize") or df.get("filesize"),
                      "md5": md5 if not df.get("originalFileFormat") else None,
                      "tabular": bool(df.get("originalFileFormat")),
                      "restricted": bool(f.get("restricted"))})
    return files


def select(files: list[dict], region: str, date_from: str | None, date_to: str | None) -> list[dict]:
    out = []
    for f in files:
        m = FILE_RE.search(f["name"] or "") or FILE_RE.search(f.get("label") or "")
        if not m or m.group(1) != region:
            continue
        d = m.group(2)
        if (date_from and d < date_from) or (date_to and d > date_to):
            continue
        out.append({**f, "date": d})
    return sorted(out, key=lambda f: f["date"])


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_file(fid: int, dest: Path, size: int | None, md5: str | None, tabular: bool,
                  retries: int = 5, log=print) -> str:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and size and dest.stat().st_size == size:
        if md5 is None or _md5(dest) == md5:
            return "skip (already present)"
    url = f"{SERVER}/api/access/datafile/{fid}"
    params = {"format": "original"} if tabular else {}
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(1, retries + 1):
        try:
            have = part.stat().st_size if part.exists() else 0
            headers = dict(UA)
            if have:
                headers["Range"] = f"bytes={have}-"
            with requests.get(url, params=params, headers=headers, stream=True, timeout=60) as r:
                if r.status_code == 416:  # already complete
                    break
                r.raise_for_status()
                mode = "ab" if have and r.status_code == 206 else "wb"
                with open(part, mode) as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
            break
        except Exception as e:  # flaky network -> retry
            log(f"    download error (attempt {attempt}/{retries}): {type(e).__name__}: {e}")
            if attempt == retries:
                raise
            time.sleep(min(30, 2 ** attempt))
    part.replace(dest)
    if md5 and _md5(dest) != md5:
        raise IOError(f"MD5 mismatch for {dest.name} - delete it and download again")
    return "ok"


def download(region: str = "mi", dest: str | Path = "data/raw/milan", date_from: str | None = None,
             date_to: str | None = None, dois: list[str] | None = None, dry_run: bool = False, log=print):
    dest = Path(dest)
    listed, errors = [], []
    for doi in dois or TELECOM_DOIS:
        try:
            fs = list_files(doi)
            log(f"DOI {doi}: {len(fs)} file")
            listed += [{**f, "doi": doi} for f in fs]
        except Exception as e:
            errors.append(f"{doi}: {type(e).__name__}: {e}")
            log(f"DOI {doi}: ERROR {type(e).__name__}: {e}")
    if not listed:
        raise ConnectionError("could not list Dataverse files: " + " | ".join(errors))
    chosen = select(listed, region, date_from, date_to)
    if not chosen:
        sample = ", ".join(sorted({f["name"] for f in listed})[:10])
        raise FileNotFoundError(f"no file matches region '{region}'. Example names seen: {sample}")
    total = sum(int(f["size"] or 0) for f in chosen)
    log(f"Selected {len(chosen)} files of region '{region}' ({chosen[0]['date']} .. {chosen[-1]['date']}), "
        f"total ~{total / 1e9:.2f} GB -> {dest}")
    if dry_run:
        for f in chosen:
            log(f"  {f['date']}  {f['name']}  {int(f['size'] or 0) / 1e6:.1f} MB  id={f['id']}")
        return {"chosen": len(chosen), "bytes": total, "dry_run": True}
    done = 0
    for k, f in enumerate(chosen, 1):
        if f["restricted"]:
            raise PermissionError(f"file {f['name']} is restricted on Dataverse")
        t0 = time.time()
        st = download_file(f["id"], dest / f["name"], f["size"], f["md5"], f["tabular"], log=log)
        done += 1
        log(f"  [{k}/{len(chosen)}] {f['name']}: {st} ({time.time() - t0:.0f}s)")
    return {"chosen": len(chosen), "downloaded": done, "bytes": total, "dest": str(dest)}
