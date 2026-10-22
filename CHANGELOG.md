# Changelog

Versioning follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. Every version has a
`release/vX.Y.Z` branch on GitHub and a Vietnamese guide `docs/README_vX.Y.Z.md`. Fixes made after a log report bump PATCH.

## [0.3.2] — 2026-10-22

Operations release; experiment code identical to 0.3.0.

### Changed
- `scripts/cluster.sh` no longer needs tmux: `start` runs each machine's chain of `run_grids.sh` calls with
  `nohup setsid` (own process group, survives logout), PID in `logs/cluster_<name>.pid`, output in
  `logs/cluster_<name>.out`; `status` and `stop` use the PID (stop kills the whole process group).
- New options `--local-only`, `--name NAME` (e.g. E8 on this machine only), `--bg` (detach the command itself).

### Added
- `cluster.sh collect [GRID ...]`: waits until the grids have no pending/running jobs on any machine (pulls results
  every `WAIT_MIN`=10 minutes), then runs `analyze all`, `calibrate` (if E0 exists), `plan` and
  `collect_logs.sh --campaign`. Typically `cluster.sh --bg collect P0_pilot E0_calibration`.

## [0.3.1] — 2026-10-22

Operations release; experiment code identical to 0.3.0.

### Added
- `scripts/cluster.sh` to drive all VMs from one machine over ssh, hosts listed in `$BURSTGUARD_SHARED/cluster.hosts`:
  `keys` (ssh key + ssh-copy-id, or a one-line manual fallback), `check` (reachability, git/python3/tmux/rsync/curl,
  CPU/RAM/disk, data/venv), `push-data` (milan_d1.npz + model cache), `install` (clone release branch + setup, in
  parallel), `smoke`, `start "<run_grids args>" ...` (detached tmux session `bg`, shard k/N per machine, this machine
  = shard 1), `status`, `stop`.
- `sync_results.sh` reads the same hosts file when called without arguments; failures are now reported (pipefail).

## [0.3.0] — 2026-10-22

Campaign release: everything needed to produce the paper's numbers in 7 days on 5 VMs. Algorithms unchanged.

### Added
- `experiments/P0_pilot.toml`: 10-job pilot (head/LoRA x 4 attack settings + a stronger scale attacker, BurstGuard in monitor mode, 20 rounds)
  to check backdoor success, detection scores and round times on the real data before the campaign.
- `burstguard plan`: per-round cost model fitted on finished jobs (falls back to model-check ratios and priors),
  remaining hours per grid and per shard, total wall time for N VMs.
- `burstguard paper`: LaTeX tables (dataset, clean accuracy, vulnerability, defenses head/LoRA, ablation, system),
  figures (lifespan, secure-aggregation groups, sensitivity heatmaps, ROC, screening cost, qualitative forecast from
  saved models) and `numbers.json`, with `index.md` listing missing artefacts.
- `burstguard analyze all`; `scripts/run_grids.sh --tier pilot|calibration|1|2|system`;
  `scripts/sync_results.sh HOST...` (rsync results from the other VMs);
  `collect_logs.sh --grid a,b` and `--campaign` (all grids + plan + paper artefacts, compact results in the bundle).
- BurstGuard `on_flag = regroup` (default): a flagged aggregate is not discarded; the round's updates are re-aggregated
  in `regroup_groups` (5) random secure groups, each group is screened, and the clean groups are averaged (adaptive
  group testing; extra leakage only in flagged rounds). `reject` keeps the previous behaviour (discard the round),
  which stalls learning when an attacker participates in every round. Regrouping metrics: `regroup_rounds`,
  `regroup_tpr_groups`, `regroup_fpr_groups`, `regroup_kept_malicious_rate`. E7 adds the `reject` policy (6 jobs).
  Not available in the Flower engine with real SecAgg+ (would need a second SecAgg+ pass); there it rejects.
- Defense baseline `probe_screen`: rejects the (secure) aggregate when the clean error on public probe windows grows
  by more than `defense.probe_tol` (5 %); reported with the same detection metrics as BurstGuard. Added to E3.
- Client training CPU per round (`client_train_cpu_s_mean`) and job wall time in the analysis.
- Testing-only grid options `--extra KEY=VALUE`, `--tag`, `--seeds`.

### Changed
- E2 uses 3 seeds (was 5); E2 and E3 save final models (`fl.save_model`) for the qualitative figure.
- Analysis refactored into `build_rows()` (shared by `analyze`, `paper`).

## [0.2.2] — 2026-10-22

Fix for the v0.2.1 report from vm-e (`data download`: HTTP 400 on datafile 2674255).

### Fixed
- Harvard Dataverse (>= 6.10) requires a guestbook response for the Telecom Italia files (guestbook 96); a plain GET
  returns HTTP 400. Downloads now follow the documented flow: POST the guestbook response to
  `/api/access/datafile/{id}` -> `signedUrl` -> GET (with Range resume and MD5 check).
- Client errors (4xx except 408/429) are no longer retried five times, and the server's message is shown.

### Added
- `burstguard data guestbook`: detects the guestbook, prints its required fields and custom questions
  (`GET /api/guestbooks/{id}`), and writes `$BURSTGUARD_SHARED/dataverse_guestbook.toml` (mode 600) to fill in.
- Optional API token via `DATAVERSE_API_TOKEN` or `api_token` in that file (never via the command line, which is logged).
- Hints for guestbook and 401/403 download errors; `tests/test_dataverse.py` (fake server: guestbook flow, resume,
  no retries on 4xx, template).

## [0.2.1] — 2026-10-22

Bug-fix release after the v0.2.0 report from vm-e. No change to experiments, configs or dependencies.

### Fixed
- `model-check` no longer requires the processed Milan dataset (falls back to synthetic windows for timings;
  parameter counts and update sizes do not depend on the data).
- Permission-only changes (e.g. `chmod -R 777`) no longer mark the checkout as modified: `setup_venv.sh` sets
  `core.fileMode=false`, and run summaries / `collect_logs.sh` use `git -c core.fileMode=false`.
- Flower SecAgg+ DEBUG lines from every Ray actor (granite-tsfm's `logging.basicConfig()` root handler) are silenced in
  all worker processes (`burstguard.logutil.quiet_logging`).
- The granite-tsfm `get_model` warning (`prediction_length (36) is not exactly equal ...`) is silenced; the previous code
  imported the re-exported *function* instead of the module, so the logger was never reached.
- `setup_venv.sh` failed when run with the old `.venv` activated (it picked the venv's own interpreter and then deleted
  it); it now always resolves the base interpreter.

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
