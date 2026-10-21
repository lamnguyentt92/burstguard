# Changelog

Versioning follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. Every version has a
`release/vX.Y.Z` branch on GitHub and a Vietnamese guide `docs/README_vX.Y.Z.md`. Fixes made after a log report bump PATCH.

## [0.2.0] — 2026-10-22

### Changed (requested after the v0.1.1 VM report)
- All code output (logs, errors, hints, comments) is in English; only README files are in Vietnamese.
- Version in every output: run dirs `runs/<ts>_v0.2.0_<cmd>_<name>/`, grid results `results/v0.2.0/<grid>/`,
  setup logs `logs/setup_v0.2.0_<ts>.log`, reports `reports/bg_report_v0.2.0_<host>_<ts>.txt`, a `"v"` field in every
  JSONL record, and `[burstguard v0.2.0]` prefixes on console lines.
- Side-by-side installs: one checkout per version (`~/burstguard-vX.Y.Z`), a version-stamped `.venv`
  (`.venv/burstguard_version`), and the CLI refuses to run when the active venv does not belong to the checkout or was
  built for another version (override: `BURSTGUARD_SKIP_VENV_CHECK=1`).
- Large assets moved to a shared, versioned-by-format directory `~/burstguard-shared` (`BURSTGUARD_SHARED`):
  raw Milan files, `milan_d1.npz` / `synthetic_d1.npz` (data format 1, checked on load), Hugging Face cache.
- Replaced the `fl/` package with `fedcore.py` (shared client/server logic) and two engines:
  `local` (deterministic process pool, fast) and `flower` (Flower simulation, real SecAgg+ via `SecAggPlusWorkflow`).
- Removed `scripts/run_e1.sh` and `configs/e*_*.toml`; experiments are now grid files in `experiments/`.

### Added
- Attacks (simulated compromised clients): `poison`, `scale` (model replacement, boost n/m), `constrain_scale`
  (norm-matched), `neurotoxin` (low-change coordinates), `adaptive` (random clean-label burst decoys). Burst trigger with
  amplitude in units of the site std; target ρ·y.
- Defenses: `clip_noise` (norm clipping + weak DP), `krum`, `multikrum`, `trimmed`, `median`, `flame`, `fltrust`,
  `lora_reset` (periodic LoRA reset), and `burstguard`.
- BurstGuard: aggregate-level screening that is compatible with secure aggregation. Worst-case bounded burst search
  (projected sign-gradient ascent, both directions, restarts) on server-held probe windows; relative forecast shift against
  the last accepted model (`threshold`, adaptive median + k·MAD) and the initial model (`threshold_anchor`);
  `enforce` / `monitor` modes; per-group screening under grouped secure aggregation; adaptive anchor threshold
  (`anchor_adaptive`) so smooth benign drift over long runs is not flagged; multi-threaded screening while clients idle.
- `burstguard calibrate`: clean-score percentiles, anchor drift per round, and offline replay of the decision rule
  (false-positive rate) for the current and suggested thresholds.
- Secure aggregation: real SecAgg+ (Flower engine); emulated SecAgg with Flower's clipping and 2^22-level stochastic
  quantization; grouped SecAgg (`secagg.groups > 1`).
- Metrics: MASE (daily/weekly), MAE, sMAPE, ASR, strict ASR, target error, attack effect, under-prediction rate,
  backdoor lifespan (L50), detection TPR/FPR, malicious-kept rate, server defense CPU time, update size.
- Baselines: zero-shot, local-only, centralized (`burstguard zeroshot|local|central`).
- Experiment grids `experiments/E0_calibration` … `E9_ablation` (697 jobs): deterministic job ids, `--shard k/n`
  (cost-balanced), resume after interruption, retry of failed jobs, `--quick` mode, `grid status|list`,
  `[[variants]]` for one-factor-at-a-time ablations.
- Analysis: `burstguard analyze` → `summary.csv|md|tex` with stratified bootstrap 95% CIs (seeds × sites),
  paired Wilcoxon tests with Holm correction (`tests.csv`), PNG/PDF figures; unit-level BurstGuard TPR/FPR, ROC AUC
  (in-run and against the matching clean configuration) and ROC curves; `burstguard calibrate` for thresholds.
- `burstguard equivalence`: compares the local and Flower engines on the same configuration.
- `collect_logs.sh --grid NAME`: grid progress and failed-job tracebacks; reports include other checkouts on the machine
  and shared-data status.
- Tests: 15 (unit + tiny federations covering every attack/defense family).

### Fixed
- Noisy third-party output (TSFM `get_model` warnings, weight-loading progress bars, HF Hub token warnings).
- Default scale boost is n/m (not n), so two colluding attackers no longer destroy the global model.
- BurstGuard anchor-only reference produced false positives on clean runs; replaced by the two-reference rule.
- setuptools pinned `<82` (torch compatibility); numpy 2.4.6 / scipy 1.17.1 (wheels for Python 3.11).

## [0.1.1] — 2026-10-21

### Fixed
- Flower telemetry disabled by default (`FLWR_TELEMETRY_ENABLED=0`).
- Guide checks out `release/vX.Y.Z` branches (tags cannot be pushed from the development session).

## [0.1.0] — 2026-10-21

### Added
- Isolated project venv (`scripts/setup_venv.sh`), log collector (`scripts/collect_logs.sh`).
- CLI: `doctor`, `smoke`, `data synthetic|download|prepare|info`, `model-download`, `model-check`, `zeroshot`, `local`, `fl`.
- Milan pipeline (Dataverse download with resume/MD5, reader, 20 sites + 8 probe blocks), TTM-R2 loading with four
  fine-tuning modes, clean FedAvg on the Flower legacy path, per-run directories with `console.log` / `summary.json`.
