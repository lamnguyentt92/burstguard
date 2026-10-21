"""Remediation hints by failure type (printed on failure and stored in summary.json)."""
from __future__ import annotations

import traceback


def hint_for(exc: BaseException) -> str | None:
    chain = []
    e: BaseException | None = exc
    while e is not None and len(chain) < 8:
        chain.append(e)
        e = e.__cause__ or e.__context__
    tb = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    low = (" ".join(type(x).__name__ for x in chain) + " " + " ".join(str(x) for x in chain) + " " + tb).lower()

    if "huggingface" in low and any(k in low for k in ("proxyerror", "connecterror", "connectionerror", "timeout",
                                                         "403", "offline", "localentrynotfound", "name resolution")):
        return ("Could not fetch the model from Hugging Face. Check `burstguard doctor` (net:huggingface). "
                "Run `burstguard model-download` on a machine with access and copy $BURSTGUARD_SHARED/hf, "
                "or use --set model.source=random to test the pipeline.")
    if "dataset not found" in low or ("filenotfounderror" in low and ".npz" in low):
        return ("Processed dataset missing. Quick test: `burstguard data synthetic` and "
                "--set data.path=\"shared:data/processed/synthetic_d1.npz\". Real data: `burstguard data download` "
                "then `burstguard data prepare` (or copy milan_d1.npz from another VM into $BURSTGUARD_SHARED/data/processed).")
    if "dataverse" in low and any(k in low for k in ("connection", "proxy", "timeout", "403", "ssl")):
        return ("Harvard Dataverse is unreachable from this machine. Download sms-call-internet-mi-*.txt manually "
                "into $BURSTGUARD_SHARED/data/raw/milan/ and run `burstguard data prepare`.")
    if any(k in low for k in ("out of memory", "outofmemory", "memoryerror", "brokenprocesspool", "killed",
                              "worker crashed", "actor died", "raylet")):
        return ("Looks like a worker ran out of memory. Lower parallelism: --set engine.workers=2 "
                "(local engine) or --set sim.num_cpus=2 (flower engine); check `free -h`.")
    if "incompatible with secure aggregation" in low or "needs individual updates" in low:
        return "This defense cannot see individual updates under secure aggregation; use secagg.groups>1 or another defense."
    if "client(s) failed" in low:
        return "One or more clients failed - search console.log for '[client' error lines."
    if "modulenotfounderror" in low or "importerror" in low:
        return "Missing package - rerun `bash scripts/setup_venv.sh` and make sure `.venv` of this checkout is active."
    return None
