# Changelog

Versioning follows [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`. Every version has a
`release/vX.Y.Z` branch on GitHub and a Vietnamese guide `docs/README_vX.Y.Z.md`. Fixes made after a log report bump PATCH.

## [0.3.7] — 2026-10-24

Adds one grid after the complete main campaign (v0.3.5: 422 jobs, 0 failed); experiment code unchanged
(`EXPERIMENT_CODE` stays "0.3.5": results of 0.3.5, 0.3.6 and 0.3.7 merge via `cluster.sh import`).

### Added
- `X3_trigger_offset` (34 jobs, tier `offset`): E6 showed that a trigger ending 12 slots before the end of the context
  (outside the screened last width_max = 6 slots) partly evades BurstGuard (TPR 0.73, malicious kept 0.27, UPR 0.22 vs.
  0.64 with FedAvg). X3 crosses trigger offset {0, 12} x search window width_max {6, 18} x {none, boost 10, boost 3}
  (head, 3 seeds) plus LoRA clean / covert offset 12 (seed 0): detection, residual backdoor, false positives and clean
  accuracy of the wider window.
- Paper: `tables/offset.tex`.

## [0.3.6] — 2026-10-23

Generalisation experiment; experiment code unchanged (`EXPERIMENT_CODE` stays "0.3.5", so 0.3.5 results are imported
and merged without warnings).

### Added
- SMS (smsin + smsout) and call (callin + callout) traffic of the same Milan files, sites and probe blocks:
  `burstguard data prepare --activity sms,call|internet|all` reads the raw files once for several traffic types,
  in 2M-row chunks filtered to the selected squares (bounded memory, safe next to running experiments); writes
  `milan_sms_d1.npz` / `milan_call_d1.npz` (internet keeps `milan_d1.npz`, which is never rewritten unless `--force`).
  The internet series are bit-identical to 0.3.5 (test against the previous reader).
- Grids `X1_traffic_clean` (18 jobs: FL head/LoRA, local-only and centralised head, zero-shot) and
  `X2_traffic_defenses` (64 jobs: none / boost 10 / boost 3 x FedAvg, Median, probe-loss check, BurstGuard; head
  2 seeds, LoRA seed 0) for both traffic types; tier `generalization` (`run_grids.sh`, `plan`).
- `run_grids.sh --wait-idle`: waits until background runs of other checkouts on the machine
  (`~/burstguard*/logs/cluster_*.pid`) have finished; `cluster.sh start "--wait-idle --tier generalization"` queues
  the new grids behind the running campaign on every machine.
- Paper: `tables/generalization.tex` (internet from E1/E3, SMS and calls from X1/X2).

### Changed
- `cluster.sh push-data` copies every `milan*_d*.npz`, with `rsync --checksum` (unchanged files are not rewritten,
  changed ones are replaced atomically) or, without rsync, only files missing on the machine.
- `burstguard data prepare` skips outputs that already exist (use `--force`).

## [0.3.5] — 2026-10-22

Replaces 0.3.4 (never run) after the complete P0 pilot of v0.3.2 (10/10 jobs). New experiment code
(`EXPERIMENT_CODE = "0.3.5"`).

P0 v0.3.2 (test split, head / LoRA): model replacement with the default attacker (poison_frac 0.2, 5 epochs)
gives ASR 0.05 / 0.33, UPR on triggered windows 0.63 / 0.94 (clean 0.008) and MASE +45 % / +25 %; the stronger
attacker (0.5, 10 epochs) adds little ASR (0.08 / 0.41) but doubles the damage (+75 % / +48 %) and makes the malicious
clients 2-3x slower. constrain_scale (bound = benign norm) does not implant (UPR 0.011 / 0.012, AUC 0.57 / 0.52);
plain poisoning barely does (UPR 0.11 / 0.20) but is visible in BurstGuard's anchor score (AUC 0.90 / 0.96).
Head rounds take 86-116 s on every machine (client training 0.16 s, the rest is screening); 3-4 screening threads
used 3-5x the CPU seconds of 1 thread for the same wall time.

### Changed
- Attacker defaults back to `attack.poison_frac` 0.2, `attack.local_epochs` 5.
- Covert attacker = `scale` with `attack.boost = 3` (partial model replacement): replaces constrain_scale in E3 and
  E9 (factor `attack.boost` = [0, 3]); P0 tests boost 3 and 5; E2 adds boost 3 and 5 for head and LoRA
  (strength vs. stealth trade-off).
- `neurotoxin` and `adaptive` are boosted like `scale` (unboosted they behave like plain poisoning, which does not
  implant); `adaptive` is norm-bounded only with the new `attack.adaptive_constrain = true`.
- `burstguard.threads` default 1.
- Shard assignment is machine-aware: a job's time on a machine with weight w (= parallel workers) is
  server part + client part x 4 / w (greedy LPT); server-bound head-only jobs are spread over the 1-worker machines.
  Jobs carry `cost_server` / `cost_client`; with costs that scale entirely with the weight the assignment equals 0.3.3.
- `burstguard plan`: two-part cost model (server seconds per round, client seconds with 4 workers, attack slow-down,
  BurstGuard seconds per screened unit x search effort), fitted from `wall_s`, `clients_wall_s_mean` and `workers`.
- Paper: vulnerability table in long format (ASR, UPR_trig, MASE, dMASE per attack and boost); defense and
  ablation tables compare model replacement (boost 10) with the covert attacker (boost 3); attack keys
  `scale@3` etc. distinguish the boost.

### Added
- `result.json`: `clients_wall_s_mean`, `workers`.

## [0.3.4] — 2026-10-22 (superseded by 0.3.5, not run)

Campaign release after the real-data pilot (P0, v0.3.2 on the 5 VMs). New experiment code
(`EXPERIMENT_CODE = "0.3.4"`): results are not mixed with 0.3.0–0.3.3.

P0 (v0.3.2, 5 of 10 jobs, 20 rounds, BurstGuard monitor): clean FL improves on the pre-trained model (validation
MASE ~0.70 at round 0 -> 0.672 head / 0.627 LoRA at round 20; test 0.657 / 0.637); plain data poisoning does not implant (ASR <= 0.001) although BurstGuard's
anchor score separates it (AUC 0.90 / 0.96); model replacement with the stronger attacker (poison_frac 0.5,
10 local epochs) implants on LoRA (test ASR 0.41, MASE +48 %) and is flagged in every round. Screening took
250-740 CPU s per round (70-85 % of the round time), and the 5 machines are worth ~3 vm-e: the planned grids would
have needed ~87 h wall.

### Changed (defaults, configs/base.toml and config.py)
- `fl.rounds` 30 -> 20.
- Strong attacker by default: `attack.poison_frac` 0.2 -> 0.5, `attack.local_epochs` 5 -> 10.
- Cheaper BurstGuard search: `probe_windows` 64 -> 32, `steps` 20 -> 8, `restarts` 2 -> 1, `step_size` 0.1 -> 0.2
  (~10x fewer model evaluations; E9 measures the effect of 0/3/20 steps, 2 restarts, 16/64 windows).
- Thresholds from the P0 clean scores (last <= 0.02, anchor <= 0.08 at round 20): `threshold` 0.15 -> 0.08,
  `threshold_anchor` 0.5 -> 0.3 (E0 + `burstguard calibrate` checks them).
- `BurstGuard.score` runs all (direction, restart) chains as one batch: identical scores (test against the sequential
  loop), ~1.5-2x faster with 4 threads.
- Local engine: malicious clients (the stragglers: 10 local epochs) are dispatched first and train with spare CPU
  threads (`sim.malicious_threads`, 0 = auto: CPUs // workers, at most 4); results are re-ordered so aggregation sees
  the sites in the usual order.
- Grids trimmed to ~150 vm-e hours (~51 h wall on the weighted cluster 4,1,3,1,3):
  P0 {none, scale, constrain_scale, constrain_scale x3 bound} x {head, LoRA} (8 jobs);
  E0 2 seeds (8); E1 FL 4 modes x 3 seeds + local-only/centralised head+LoRA x 2 seeds + zero-shot (21);
  E2 scale x 4 modes x 3 seeds + poison/constrain x head+LoRA x 2 seeds, no attack-free runs (20);
  E3 head {none, scale, constrain} x 9 defenses x 3 seeds + LoRA x 8 defenses x 2 seeds (129);
  E4 2 seeds (54); E5 40 rounds, attack in rounds 6-15, head+LoRA, 2 seeds (14); E6 head 3 seeds, LoRA 1 seed (36);
  E7 2 seeds (56); E9 10 search variants x 3 attacks x 2 seeds (60).
- `burstguard plan` cost model: per-round cost of clean jobs, a measured slow-down of attacked jobs (stragglers), and
  BurstGuard cost per screened unit scaled by the search effort (probe windows x restarts x directions x steps);
  priors from P0 v0.3.2. Shard balancing uses the same model.

### Added
- `[[exclude]]` in grid files can match `run.seed` (fewer seeds for the expensive fine-tuning mode).
- Jobs carry `effective` (resolved cost-relevant keys, e.g. `fl.rounds` from the base config) in the expanded job
  and in `result.json`; `plan` and the lifespan analysis use it.
- `attack.norm_mult` (constrain_scale / adaptive): norm bound = norm_mult x the attacker's benign update norm.
- Decision-rule replay for monitor-mode runs (`engines.common.rule_flags`): reference = last only, anchor only and a
  fixed anchor threshold are re-applied to the logged scores of the same rounds (exact in monitor mode;
  `rule_replay_agree` checks the deployed rule against the logged decisions). `analyze` writes `rule_*` columns and a
  second table in `summary.md`; the paper's ablation table gets "replayed" rows. E9 therefore no longer runs the
  reference / anchor_adaptive variants.
- `summary.md` shows `round_wall_s_mean`.

### Fixed
- `auc_vs_clean`: attacked configurations with extra attack parameters (e.g. `attack.norm_mult`) are matched with the
  clean configuration (attack keys ignored).
- Paper vulnerability table: clean reference falls back to E1 (FL) when E2 has no attack-free runs; confidence
  intervals printed with the same precision as the value.
- Ablation table label of the default variant reflects the v0.3.4 defaults.

## [0.3.3] — 2026-10-22

Operations release for heterogeneous VMs; experiment code identical to 0.3.0 (`EXPERIMENT_CODE = "0.3.0"`).

### Added
- Weighted shards `k/N@w1,...,wN` (`grid run/list --shard`, `grid status --weights`, `run_grids.sh`): jobs sorted by
  (-cost, id) are assigned greedily to the shard with the smallest (assigned cost + job cost) / weight (ties: lowest
  shard). Deterministic; plain `k/N` keeps the round-robin assignment of earlier versions unchanged.
- `scripts/cluster.sh start` uses weights from `$BURSTGUARD_SHARED/cluster.weights` (this machine first, then the
  hosts-file order); if missing, computes them once from each machine's capacity
  `max(1, min(nproc-1, floor((MemAvailable_GiB-2.5)/1.4)))` (the engine's worker count) and refuses while experiments
  are still running (free memory would be underestimated). `--equal` forces plain round-robin; `status` prints the
  weights in use.
- `cluster.sh import OLD_VERSION`: on every machine, copies finished jobs (status success) from
  `~/burstguard-vOLD/results/vOLD/` into this version's results so they are skipped.
- `burstguard plan --weights` (default: the cluster.weights file): wall time per shard = job time / (weight / 4)
  (measured round times are taken as those of a weight-4 machine), plus the equal-shard time on the same machines.
- `EXPERIMENT_CODE` recorded in every result (`exp_code`); `analyze` warns only when results with different experiment
  code are mixed (0.3.0–0.3.2 results without the field count as 0.3.0).

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
