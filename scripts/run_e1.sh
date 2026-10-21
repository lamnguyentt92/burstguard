#!/usr/bin/env bash
# =============================================================================
# BurstGuard v0.1.0 — chạy trọn bộ E1 (baseline SẠCH) trên dữ liệu Milan thật:
#   model-check -> zeroshot -> FL head / decoder / lora / full
#
#   bash scripts/run_e1.sh                 # 30 vòng, seed 0
#   bash scripts/run_e1.sh --quick         # 3 vòng, ít cửa sổ (kiểm tra nhanh ~10–20 phút)
#   bash scripts/run_e1.sh --seed 1
# Mỗi bước là một thư mục trong runs/. Cuối cùng tự gom log: reports/bg_report_*.txt
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$ROOT"
if [ -z "${VIRTUAL_ENV:-}" ] || [ "$(cd "$VIRTUAL_ENV" && pwd)" != "$ROOT/.venv" ]; then
  if [ -f .venv/bin/activate ]; then . .venv/bin/activate; else echo "Chưa có .venv — chạy: bash scripts/setup_venv.sh"; exit 2; fi
fi
EXTRA=(); SEED=0; QUICK=0
while [ $# -gt 0 ]; do
  case "$1" in
    --quick) QUICK=1 ;;
    --seed) SEED="$2"; shift ;;
    *) EXTRA+=("$1") ;;
  esac; shift
done
if [ "$QUICK" = 1 ]; then
  EXTRA+=(--set fl.rounds=3 --set fl.eval_every=1 --set data.max_train_windows=400 --set data.max_eval_windows=100)
fi
declare -a NAMES STATUS
run() { local name="$1"; shift
  echo; echo "########## $name: burstguard $*"
  burstguard "$@"; local rc=$?
  NAMES+=("$name"); STATUS+=("$([ $rc = 0 ] && echo OK || echo "FAIL($rc)")")
}
N0=$(ls -1d runs/*/ 2>/dev/null | wc -l)
run model-check model-check -c configs/e1_clean_head.toml "${EXTRA[@]}"
run zeroshot    zeroshot    -c configs/e1_clean_head.toml "${EXTRA[@]}"
for m in head decoder lora full; do
  run "fl-$m" fl -c "configs/e1_clean_$m.toml" --seed "$SEED" "${EXTRA[@]}"
done
echo; echo "########## TÓM TẮT E1"
for i in "${!NAMES[@]}"; do printf "  %-12s %s\n" "${NAMES[$i]}" "${STATUS[$i]}"; done
N1=$(ls -1d runs/*/ 2>/dev/null | wc -l)
bash scripts/collect_logs.sh --last $((N1 - N0)) | tail -n 3
