#!/usr/bin/env bash
# Run experiment grids one after another for one shard (one VM). Re-running the same command resumes:
# finished jobs are skipped, failed/interrupted ones are retried. To survive SSH drops start it with nohup
# (nohup bash scripts/run_grids.sh ... > logs/run.out 2>&1 &) or let scripts/cluster.sh start it.
#
#   bash scripts/run_grids.sh 2/5 --tier pilot          # P0_pilot (day 1)
#   bash scripts/run_grids.sh 2/5 --tier calibration    # E0_calibration (day 1)
#   bash scripts/run_grids.sh 2/5 --tier 1              # core paper grids: E1 E2 E3 E7 E9
#   bash scripts/run_grids.sh 2/5 --tier 2              # extended: E4 E5 E6
#   bash scripts/run_grids.sh 2/5 --tier 1,2            # both, in order
#   bash scripts/run_grids.sh 2/5 E3_defenses E7_secagg # explicit grids
#   bash scripts/run_grids.sh 1/1 --quick E3_defenses   # pipeline check
#   bash scripts/run_grids.sh 2/5@4,1,3,1,3 --tier 1    # weighted shard (scripts/cluster.sh does this for you)
# E8_system (timings) runs on ONE idle VM: bash scripts/run_grids.sh 1/1 --tier system
# Log: logs/run_grids_v<VERSION>_<shard>_<ts>.log
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VER="$(cat VERSION)"
SHARD="${1:-}"
[[ "$SHARD" =~ ^[0-9]+/[0-9]+(@[0-9.]+(,[0-9.]+)*)?$ ]] || {
  echo "usage: bash scripts/run_grids.sh K/N[@w1,...,wN] [--quick] [--tier T] [GRID ...]"; exit 2; }
shift
QUICK=(); TIERS=""; GRIDS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) QUICK=(--quick) ;;
    --tier) TIERS="${2:-}"; shift ;;
    *) GRIDS+=("$1") ;;
  esac
  shift
done
tier_grids() {
  case "$1" in
    pilot) echo "P0_pilot" ;;
    calibration) echo "E0_calibration" ;;
    1) echo "E1_clean E2_attacks E3_defenses E7_secagg E9_ablation" ;;
    2) echo "E4_sensitivity E5_lifespan E6_adaptive" ;;
    system) echo "E8_system" ;;
    *) echo "" ;;
  esac
}
if [ -n "$TIERS" ]; then
  IFS=',' read -ra _T <<< "$TIERS"
  for t in "${_T[@]}"; do
    gs="$(tier_grids "$t")"; [ -n "$gs" ] || { echo "unknown tier: $t"; exit 2; }
    for g in $gs; do GRIDS+=("$g"); done
  done
fi
[[ ${#GRIDS[@]} -eq 0 ]] && GRIDS=(E1_clean E2_attacks E3_defenses E7_secagg E9_ablation E4_sensitivity E5_lifespan E6_adaptive)

if [[ ! -x .venv/bin/burstguard ]]; then
  echo "ERROR (burstguard v$VER): .venv missing - run: bash scripts/setup_venv.sh"; exit 2
fi
# shellcheck disable=SC1091
source .venv/bin/activate

mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
SH_NAME="${SHARD%%@*}"                     # log name without the weights (they are printed inside the log)
LOG="logs/run_grids_v${VER}_${SH_NAME/\//of}_${TS}.log"
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
