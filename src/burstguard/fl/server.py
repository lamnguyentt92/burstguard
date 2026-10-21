"""ServerApp: FedAvg (lối legacy của Flower, tương thích SecAgg+ ở v0.2) + đánh giá tập trung để đo lường."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import numpy as np


def _writer(path: Path):
    def write(kind: str, **data):
        with open(path, "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "kind": kind, **data}, default=str) + "\n")
    return write


def make_server_app(cfg: dict[str, Any], run_dir: Path):
    from flwr.common import ndarrays_to_parameters, parameters_to_ndarrays
    from flwr.server import LegacyContext, ServerApp, ServerConfig
    from flwr.server.strategy import FedAvg
    from flwr.server.workflow import DefaultWorkflow

    from burstguard import model as M
    from burstguard.sitedata import dataset_from_cfg, evaluate

    write = _writer(run_dir / "metrics.jsonl")
    R = int(cfg["fl"]["rounds"])
    every = max(1, int(cfg["fl"]["eval_every"]))
    n_sites = int(cfg["data"]["num_sites"])
    strict = bool(cfg["fl"].get("strict", True))

    class LoggedFedAvg(FedAvg):
        def __init__(self, eval_model, **kw):
            super().__init__(**kw)
            self.eval_model = eval_model
            self.t_round = time.time()

        def configure_fit(self, server_round, parameters, client_manager):
            self.t_round = time.time()
            return super().configure_fit(server_round, parameters, client_manager)

        def aggregate_fit(self, server_round, results, failures):
            if failures:
                msgs = [repr(f)[:2000] for f in failures]
                write("client_failures", round=server_round, n=len(failures), details=msgs)
                print(f"[server] vòng {server_round}: {len(failures)} client lỗi:\n  " + "\n  ".join(msgs), flush=True)
                if strict or not results:
                    raise RuntimeError(f"{len(failures)} client lỗi ở vòng {server_round} (fl.strict=true). "
                                       f"Lỗi đầu tiên: {msgs[0]}")
            params, _ = super().aggregate_fit(server_round, results, failures)
            mets = [r.metrics for _, r in results]
            nbytes = int(sum(a.nbytes for a in parameters_to_ndarrays(results[0][1].parameters))) if results else 0
            rec = {"round": server_round, "n_results": len(results), "n_failures": len(failures),
                   "train_loss_mean": float(np.mean([m["train_loss"] for m in mets])) if mets else None,
                   "client_train_cpu_s_mean": float(np.mean([m["train_cpu_s"] for m in mets])) if mets else None,
                   "update_bytes_per_client": nbytes, "round_wall_s": round(time.time() - self.t_round, 2)}
            write("round", **rec)
            print(f"[server] vòng {server_round}/{R}: {len(results)} client, loss={rec['train_loss_mean']:.4f}, "
                  f"{nbytes / 1024:.1f} KiB/cập nhật, {rec['round_wall_s']}s", flush=True)
            return params, {}

    def evaluate_fn(server_round, parameters, config):
        if not (server_round == 0 or server_round % every == 0 or server_round == R):
            return None
        ds = dataset_from_cfg(cfg)
        M.set_trainable(eval_model, parameters)
        t0 = time.time()
        splits = [cfg["fl"]["eval_split"]] + (["test", "holiday"] if server_round == R else [])
        out = {}
        for sp in splits:
            if ds.bounds.get(sp, [0, 0])[1] <= ds.bounds.get(sp, [0, 0])[0]:
                continue
            ev = evaluate(eval_model, ds, cfg, sp)
            out[sp] = {k: v for k, v in ev.items() if k not in ("sites", "split")}
            write("eval", round=server_round, split=sp, **out[sp], per_site=ev["sites"])
        msg = "  ".join(f"{sp}: MASE={v.get('mase_daily_mean', float('nan')):.3f}" for sp, v in out.items())
        print(f"[server] đánh giá vòng {server_round}: {msg} ({time.time() - t0:.1f}s)", flush=True)
        first = out[splits[0]]
        return float(first.get("mae_mean", 0.0)), {"mase_daily_mean": float(first.get("mase_daily_mean", 0.0))}

    base, info = M.load_model(cfg, seed=int(cfg["run"]["seed"]))
    eval_model = M.configure_peft(base, cfg)
    init = M.get_trainable(eval_model)
    write("setup", model=info.__dict__, n_trainable=M.n_trainable(eval_model),
          n_arrays=len(init), peft=cfg["train"]["peft"], rounds=R, num_sites=n_sites)
    print(f"[server] mô hình {info.revision} ({info.n_params:,} tham số), chế độ {cfg['train']['peft']}: "
          f"{M.n_trainable(eval_model):,} tham số train được", flush=True)

    app = ServerApp()

    @app.main()
    def main(grid, context):
        strategy = LoggedFedAvg(
            eval_model=eval_model,
            fraction_fit=float(cfg["fl"]["fraction_fit"]), fraction_evaluate=0.0,
            min_fit_clients=max(1, int(round(n_sites * float(cfg["fl"]["fraction_fit"])))),
            min_available_clients=n_sites,
            initial_parameters=ndarrays_to_parameters(init),
            evaluate_fn=evaluate_fn,
            on_fit_config_fn=lambda r: {"server_round": r},
            accept_failures=True,
        )
        ctx = LegacyContext(context=context, config=ServerConfig(num_rounds=R), strategy=strategy)
        DefaultWorkflow()(grid, ctx)
        write("finished", rounds=R)
        (run_dir / "server_finished").write_text("ok\n")

    return app, info
