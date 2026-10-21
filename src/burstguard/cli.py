"""Giao diện dòng lệnh `burstguard` (hoặc `python -m burstguard`)."""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from burstguard.paths import isolate_environment

isolate_environment()  # phải chạy trước khi import torch/transformers/ray

from burstguard import __version__  # noqa: E402
from burstguard.paths import PROCESSED_DIR, RAW_DIR, in_virtualenv, resolve  # noqa: E402
from burstguard.runctx import RunContext  # noqa: E402


def _quiet_libs() -> None:
    import logging
    import warnings
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    # Một handler gốc ở mức WARNING (cài trước khi tsfm_public gọi logging.basicConfig -> lệnh đó thành no-op)
    root = logging.getLogger()
    if not root.handlers:
        h = logging.StreamHandler()
        h.setLevel(logging.WARNING)
        h.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
        root.addHandler(h)
    root.setLevel(logging.WARNING)
    for name in ("transformers", "tsfm_public", "urllib3", "filelock", "ray"):
        logging.getLogger(name).setLevel(logging.WARNING)
    logging.getLogger("flwr").propagate = False  # Flower đã có handler riêng -> tránh in trùng
    try:
        from transformers.utils import logging as hl
        hl.set_verbosity_error()
    except Exception:
        pass


# ---------------------------------------------------------------- lệnh

def cmd_doctor(a, ctx):
    from burstguard import doctor
    res = doctor.run(check_net=not a.no_net)
    ctx.save_json("doctor.json", res)
    ctx.set(n_fail=res["n_fail"], n_warn=res["n_warn"])
    if res["n_fail"]:
        raise SystemExit(f"doctor: {res['n_fail']} mục FAIL — sửa trước khi chạy thí nghiệm")


def cmd_data_synthetic(a, ctx):
    from burstguard.data.store import describe, load_dataset, save_dataset
    from burstguard.data.synthetic import generate
    s, p, meta, b = generate(a.sites, a.probe, seed=a.seed)
    out = save_dataset(resolve(a.out), s, p, meta, b)
    d = describe(load_dataset(out))
    ctx.save_json("dataset_info.json", d)
    ctx.set(out=str(out), num_sites=d["num_sites"], T=d["T"])
    print(f"Đã tạo dữ liệu tổng hợp: {out} ({d['num_sites']} site, {d['T']} khe, {d['num_probe']} probe)")


def cmd_data_download(a, ctx):
    from burstguard.data import dataverse
    res = dataverse.download(region=a.region, dest=resolve(a.dest), date_from=a.date_from, date_to=a.date_to,
                             dois=a.doi or None, dry_run=a.dry_run)
    ctx.set(**{k: v for k, v in res.items() if not isinstance(v, (list, dict))})


def cmd_data_prepare(a, ctx):
    from burstguard.data import milan
    from burstguard.data.store import describe, load_dataset, save_dataset
    t0 = time.time()
    s, p, meta, b = milan.prepare(resolve(a.raw), a.sites, a.probe, a.block, days=a.days)
    out = save_dataset(resolve(a.out), s, p, meta, b)
    d = describe(load_dataset(out))
    ctx.save_json("dataset_info.json", d)
    ctx.set(out=str(out), num_sites=d["num_sites"], T=d["T"], seconds=round(time.time() - t0, 1),
            raw_stats=meta["raw_stats"])
    print(f"Đã xử lý: {out}  ({d['num_sites']} site × {d['T']} khe; khe mất toàn bộ: "
          f"{meta['raw_stats']['slots_missing_all_squares']})")
    for r in d["per_site"]:
        print(f"  site {r['site']:2d}: TB={r['mean']:10.1f}  std(train)={r['std_train']:9.1f}  tỉ lệ 0={r['zero_frac']:.3f}")


def cmd_data_info(a, ctx):
    from burstguard.data.store import describe, load_dataset
    d = describe(load_dataset(resolve(a.path)))
    ctx.save_json("dataset_info.json", d)
    print(json.dumps({k: v for k, v in d.items() if k != "per_site"}, indent=2, ensure_ascii=False))


def _cfg(a, ctx=None, need_data: bool = True):
    """Đọc cấu hình, lưu bản đã hợp nhất vào run dir, kiểm tra dữ liệu TRƯỚC khi nạp mô hình (báo lỗi sớm)."""
    from burstguard.config import dump_toml, load_config
    cfg = load_config(a.config, a.set)
    if getattr(a, "seed", None) is not None:
        cfg["run"]["seed"] = a.seed
    txt = dump_toml(cfg)
    if ctx is not None:
        (ctx.dir / "config.toml").write_text(txt)
        ctx.set(config_file=cfg.get("_config_file"), peft=cfg["train"]["peft"], model_source=cfg["model"]["source"],
                data_path=cfg["data"]["path"], seed=cfg["run"]["seed"])
    if need_data:
        from burstguard.sitedata import dataset_from_cfg
        ds = dataset_from_cfg(cfg)
        print(f"Dữ liệu: {cfg['data']['path']} ({ds.meta.get('source')}, {ds.num_sites} site, {ds.T} khe)")
    return cfg, txt


def cmd_model_check(a, ctx):
    import numpy as np
    import torch
    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg, site_windows
    cfg, txt = _cfg(a, ctx)
    t0 = time.time()
    model, info = M.load_model(cfg)
    print(f"Nạp mô hình: {info} ({time.time() - t0:.1f}s)")
    ds = dataset_from_cfg(cfg)
    X, Y, _ = site_windows(ds, 0, "train", cfg)
    print(f"Site 0: {len(X)} cửa sổ train, X{X.shape} Y{Y.shape}")
    torch.set_num_threads(int(cfg["sim"]["torch_threads"]))
    report = {"model": info.__dict__, "modes": {}}
    for mode in ("head", "decoder", "lora", "full"):
        m2, _ = M.load_model(cfg)
        c2 = {**cfg, "train": {**cfg["train"], "peft": mode}}
        m2 = M.configure_peft(m2, c2)
        from burstguard.train import local_train
        n = min(len(X), 512)
        cache = None
        rel = None
        if mode == "head":
            rel = M.check_head_cache(m2, X, int(cfg["data"]["horizon"]), cfg["model"]["freq"])
            cache = M.build_head_cache(m2, X[:n], freq=cfg["model"]["freq"])
        st = local_train(m2, X[:n], Y[:n], ds.site_scale(0), c2, cache=cache)
        arrs = M.get_trainable(m2)
        nbytes = int(sum(x.nbytes for x in arrs))
        report["modes"][mode] = {"n_trainable": M.n_trainable(m2), "update_bytes": nbytes,
                                 "cpu_s_per_512_windows": round(st["train_cpu_s"], 3),
                                 "head_cache_rel_err": rel}
        print(f"  {mode:8s}: {M.n_trainable(m2):>9,} tham số train, {nbytes / 1024:8.1f} KiB/cập nhật, "
              f"{st['train_cpu_s']:.2f}s CPU / 512 cửa sổ" + (f", sai lệch cache={rel:.1e}" if rel is not None else ""))
        if mode == "head" and rel is not None and rel > 1e-3:
            print("  CẢNH BÁO: head cache lệch so với forward đầy đủ — FL sẽ tự tắt cache (chậm hơn).")
    ctx.save_json("model_check.json", report)
    ctx.set(model=info.revision, n_params=info.n_params)


def cmd_model_download(a, ctx):
    """Tải trước trọng số TTM-R2 vào cache của dự án (.cache/huggingface) rồi thử nạp ở chế độ offline."""
    import importlib.resources as ir
    import yaml
    from huggingface_hub import snapshot_download
    from burstguard import model as M
    cfg, _ = _cfg(a, ctx, need_data=False)
    path, L, H = cfg["model"]["path"], int(cfg["data"]["context"]), int(cfg["data"]["horizon"])
    rev = cfg["model"]["revision"]
    if rev == "auto":
        from tsfm_public.toolkit.get_model import get_model
        key = get_model(path, context_length=L, prediction_length=H, return_model_key=True)
        conf = yaml.safe_load((ir.files("tsfm_public") / "resources/model_paths_config/ttm.yaml").read_text())
        rev = conf["ibm-granite-models"][key]["revision"]
        print(f"get_model chọn biến thể {key} -> nhánh '{rev}'")
    t0 = time.time()
    local = snapshot_download(repo_id=path, revision=rev)
    print(f"Đã tải {path}@{rev} vào {local} ({time.time() - t0:.0f}s)")
    os.environ["HF_HUB_OFFLINE"] = "1"
    model, info = M.load_model(cfg)
    print(f"Nạp offline OK: {info}")
    ctx.set(repo=path, revision=rev, local_path=local, n_params=info.n_params)
    print("Nếu VM khác không có mạng tới huggingface.co: chép nguyên thư mục .cache/huggingface của dự án sang đó.")


def cmd_zeroshot(a, ctx):
    from burstguard import baselines
    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg
    cfg, txt = _cfg(a, ctx)
    ds = dataset_from_cfg(cfg)
    model, info = M.load_model(cfg)
    print(f"Mô hình {info.revision}; dữ liệu {ds.meta.get('source')} ({cfg['data']['num_sites']} site)")
    nv = {sp: baselines.naive_table(ds, cfg, sp) for sp in ("val", "test")}
    for sp, t in nv.items():
        print(f"  seasonal-naive tuần so với ngày ({sp}): MASE={t['weekly_vs_daily_mean']}")
    zs = baselines.zeroshot(model, ds, cfg)
    ctx.save_json("zeroshot.json", {"model": info.__dict__, "naive": nv, "zeroshot": zs})
    ctx.set(model=info.revision, **{f"{sp}_mase_daily_mean": v.get("mase_daily_mean") for sp, v in zs.items()})


def cmd_local(a, ctx):
    from burstguard import baselines
    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg
    cfg, txt = _cfg(a, ctx)
    ds = dataset_from_cfg(cfg)
    res = baselines.local_only(cfg, ds, lambda: M.load_model(cfg))
    ctx.save_json("local_only.json", res)
    ctx.set(test_mase_daily_mean=res["mase_daily_mean"])


def cmd_fl(a, ctx):
    from burstguard.fl.sim import run_fl
    cfg, txt = _cfg(a, ctx)
    print(f"FL: {cfg['run']['name']} | peft={cfg['train']['peft']} | {cfg['fl']['rounds']} vòng | "
          f"{cfg['data']['num_sites']} site | seed={cfg['run']['seed']} | dữ liệu={cfg['data']['path']}")
    res = run_fl(cfg, ctx.dir)
    ctx.save_json("fl_result.json", res)
    ctx.set(**{"rounds_done": res["rounds_done"], "wall_s": res["wall_s"],
               "update_bytes_per_client": res["update_bytes_per_client"],
               **{f"final_{sp}_mase_daily_mean": v.get("mase_daily_mean") for sp, v in res["final"].items()}})
    print(json.dumps(res, indent=2, ensure_ascii=False))


def cmd_smoke(a, ctx):
    """Kiểm thử đầu-cuối không cần mạng/dữ liệu thật: dữ liệu tổng hợp + TTM khởi tạo ngẫu nhiên."""
    from burstguard import baselines
    from burstguard import model as M
    from burstguard.config import load_config
    from burstguard.data.store import save_dataset
    from burstguard.data.synthetic import generate
    from burstguard.fl.sim import run_fl
    from burstguard.sitedata import dataset_from_cfg

    steps = []

    def step(name, fn):
        t0 = time.time()
        print(f"\n===== SMOKE: {name}", flush=True)
        try:
            out = fn()
            steps.append({"step": name, "status": "PASS", "s": round(time.time() - t0, 1)})
            print(f"===== PASS: {name} ({time.time() - t0:.1f}s)", flush=True)
            return out
        except Exception as e:
            steps.append({"step": name, "status": "FAIL", "s": round(time.time() - t0, 1),
                          "error": f"{type(e).__name__}: {e}"})
            print(f"===== FAIL: {name}: {type(e).__name__}: {e}", flush=True)
            raise

    data_path = PROCESSED_DIR / "smoke_synthetic.npz"
    ov = [f'data.path="{data_path}"', 'model.source="random"', "data.num_sites=4",
          "data.max_train_windows=256", "data.max_eval_windows=64", "fl.rounds=2", "fl.eval_every=1",
          f"sim.num_cpus={a.cpus}"]
    try:
        step("dữ liệu tổng hợp", lambda: save_dataset(data_path, *generate(4, 2, seed=0)[:3]))
        cfg = load_config(None, ov)
        step("nạp mô hình + head cache", lambda: _smoke_model(cfg))
        step("zero-shot", lambda: baselines.zeroshot(M.load_model(cfg)[0], dataset_from_cfg(cfg), cfg))
        for mode in ("head", "lora"):
            c = load_config(None, ov + [f'train.peft="{mode}"', f'run.name="smoke_{mode}"'])
            sub = ctx.dir / f"fl_{mode}"; sub.mkdir()
            res = step(f"FL 2 vòng × 4 site ({mode})", lambda c=c, sub=sub: run_fl(c, sub))
            ctx.save_json(f"fl_{mode}.json", res)
    finally:
        ctx.save_json("smoke_report.json", steps)
        ctx.set(steps=steps, passed=sum(s["status"] == "PASS" for s in steps), total=len(steps))
        print("\n===== TÓM TẮT SMOKE")
        for s in steps:
            print(f"  [{s['status']}] {s['step']} ({s['s']}s){'  ' + s.get('error', '') if s['status'] != 'PASS' else ''}")


def _smoke_model(cfg):
    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg, site_windows
    m, info = M.load_model(cfg)
    ds = dataset_from_cfg(cfg)
    X, _, _ = site_windows(ds, 0, "train", cfg)
    rel = M.check_head_cache(M.configure_peft(m, cfg), X, int(cfg["data"]["horizon"]), cfg["model"]["freq"])
    print(f"  {info.revision}: {info.n_params:,} tham số; freq_prefix={info.freq_prefix}; sai lệch head cache={rel:.1e}")
    if rel > 1e-3:
        raise AssertionError(f"head cache lệch {rel}")


# ---------------------------------------------------------------- parser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="burstguard", description=f"BurstGuard {__version__}")
    p.add_argument("--version", action="version", version=f"burstguard {__version__}")
    p.add_argument("--nice", type=int, default=10,
                   help="hạ độ ưu tiên CPU của tiến trình (và worker Ray) để không ảnh hưởng dịch vụ khác; 0 = tắt")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("doctor", help="kiểm tra môi trường"); s.add_argument("--no-net", action="store_true")
    s.set_defaults(fn=cmd_doctor)

    d = sub.add_parser("data", help="dữ liệu").add_subparsers(dest="dcmd", required=True)
    s = d.add_parser("synthetic", help="tạo dữ liệu tổng hợp để thử pipeline")
    s.add_argument("--out", default=str(PROCESSED_DIR / "synthetic.npz"))
    s.add_argument("--sites", type=int, default=20); s.add_argument("--probe", type=int, default=8)
    s.add_argument("--seed", type=int, default=0); s.set_defaults(fn=cmd_data_synthetic, name="synthetic")
    s = d.add_parser("download", help="tải dữ liệu Milan từ Harvard Dataverse")
    s.add_argument("--region", default="mi", choices=["mi", "tn"])
    s.add_argument("--dest", default=str(RAW_DIR / "milan"))
    s.add_argument("--from", dest="date_from", default=None, help="YYYY-MM-DD")
    s.add_argument("--to", dest="date_to", default=None, help="YYYY-MM-DD")
    s.add_argument("--doi", action="append", help="ghi đè DOI (có thể lặp)")
    s.add_argument("--dry-run", action="store_true", help="chỉ liệt kê, không tải")
    s.set_defaults(fn=cmd_data_download, name="download")
    s = d.add_parser("prepare", help="xử lý file Milan thô -> data/processed/milan.npz")
    s.add_argument("--raw", default=str(RAW_DIR / "milan")); s.add_argument("--out", default=str(PROCESSED_DIR / "milan.npz"))
    s.add_argument("--sites", type=int, default=20); s.add_argument("--probe", type=int, default=8)
    s.add_argument("--block", type=int, default=5); s.add_argument("--days", type=int, default=62)
    s.set_defaults(fn=cmd_data_prepare, name="prepare")
    s = d.add_parser("info", help="mô tả một file .npz"); s.add_argument("--path", default=str(PROCESSED_DIR / "milan.npz"))
    s.set_defaults(fn=cmd_data_info, name="info")

    for name, fn, hlp in (("model-download", cmd_model_download, "tải trước trọng số TTM-R2 vào .cache/huggingface"),
                          ("model-check", cmd_model_check, "nạp mô hình, đo tốc độ từng chế độ PEFT"),
                          ("zeroshot", cmd_zeroshot, "baseline seasonal-naive + TTM zero-shot"),
                          ("local", cmd_local, "baseline fine-tune cục bộ từng site"),
                          ("fl", cmd_fl, "chạy học liên kết (Flower simulation)")):
        s = sub.add_parser(name, help=hlp)
        s.add_argument("--config", "-c", default=None, help="file TOML trong configs/")
        s.add_argument("--set", action="append", default=[], help="ghi đè, vd --set train.peft=lora")
        s.add_argument("--seed", type=int, default=None)
        s.set_defaults(fn=fn)

    s = sub.add_parser("smoke", help="kiểm thử đầu-cuối nhanh (không cần mạng/dữ liệu thật)")
    s.add_argument("--cpus", type=int, default=2, help="số CPU cho Ray trong smoke test")
    s.set_defaults(fn=cmd_smoke)
    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)
    if not in_virtualenv() and os.environ.get("BURSTGUARD_ALLOW_NO_VENV") != "1":
        print("LỖI: burstguard phải chạy trong môi trường ảo của dự án.\n"
              "  source .venv/bin/activate   # rồi chạy lại lệnh\n"
              "(Nếu chưa có .venv: bash scripts/setup_venv.sh)", file=sys.stderr)
        return 2
    if args.nice:
        try:
            os.nice(args.nice)
        except Exception:
            pass
    _quiet_libs()
    cmd = args.cmd if args.cmd != "data" else f"data-{args.dcmd}"
    name = getattr(args, "name", None)
    if hasattr(args, "config") and args.config:
        name = os.path.splitext(os.path.basename(args.config))[0]
    try:
        with RunContext(cmd, name, ["burstguard", *argv]) as ctx:
            args.fn(args, ctx)
    except SystemExit as e:
        return int(e.code) if isinstance(e.code, int) else 1
    except KeyboardInterrupt:
        return 130
    except Exception:
        return 1
    return 0
