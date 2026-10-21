#!/usr/bin/env bash
# Run several experiment grids one after another for one shard (one VM).
#   bash scripts/run_grids.sh 2/5                      # shard 2 of 5: E1..E7, E9 (E0 and E8 are run separately)
#   bash scripts/run_grids.sh 2/5 E3_defenses E7_secagg
#   bash scripts/run_grids.sh 1/1 --quick E3_defenses   # pipeline check
# Re-running the same command resumes: finished jobs are skipped, failed/interrupted ones are retried.
# Start it inside tmux/screen so it survives SSH disconnects. Log: logs/run_grids_v<VERSION>_<shard>_<ts>.log
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VER="$(cat VERSION)"
SHARD="${1:-}"
[[ "$SHARD" =~ ^[0-9]+/[0-9]+$ ]] || { echo "usage: bash scripts/run_grids.sh K/N [--quick] [GRID ...]"; exit 2; }
shift
QUICK=()
if [[ "${1:-}" == "--quick" ]]; then QUICK=(--quick); shift; fi
GRIDS=("$@")
[[ ${#GRIDS[@]} -eq 0 ]] && GRIDS=(E1_clean E2_attacks E3_defenses E4_sensitivity E5_lifespan E6_adaptive E7_secagg E9_ablation)

if [[ ! -x .venv/bin/burstguard ]]; then
  echo "ERROR (burstguard v$VER): .venv missing - run: bash scripts/setup_venv.sh"; exit 2
fi
# shellcheck disable=SC1091
source .venv/bin/activate

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
LOG="logs/run_grids_v${VER}_${SHARD/\//of}_${TS}.log"
echo "[burstguard v$VER] run_grids shard=$SHARD grids=${GRIDS[*]} ${QUICK[*]:-} host=$(hostname) log=$LOG" | tee -a "$LOG"
FAILED=()
for g in "${GRIDS[@]}"; do
  f="experiments/${g%.toml}.toml"
  if [[ ! -f "$f" ]]; then echo "[burstguard v$VER] skip: $f not found" | tee -a "$LOG"; FAILED+=("$g"); continue; fi
  echo "[burstguard v$VER] $(date -Iseconds) START $g shard $SHARD" | tee -a "$LOG"
  burstguard grid run "$f" --shard "$SHARD" "${QUICK[@]}" 2>&1 | tee -a "$LOG"
  rc=${PIPESTATUS[0]}
  echo "[burstguard v$VER] $(date -Iseconds) END $g shard $SHARD exit=$rc" | tee -a "$LOG"
  [[ "$rc" -ne 0 ]] && FAILED+=("$g")
done
if [[ ${#FAILED[@]} -eq 0 ]]; then
  echo "[burstguard v$VER] ALL GRIDS OK (shard $SHARD)" | tee -a "$LOG"
else
  echo "[burstguard v$VER] grids with failed jobs: ${FAILED[*]} -> bash scripts/collect_logs.sh --grid <name>" | tee -a "$LOG"
  exit 1
fi
