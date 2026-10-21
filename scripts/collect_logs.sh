#!/usr/bin/env bash
# =============================================================================
# BurstGuard — gom log để gửi phân tích (dùng được cả khi .venv hỏng).
#
#   bash scripts/collect_logs.sh                # lần chạy gần nhất (runs/LATEST) + cài đặt gần nhất
#   bash scripts/collect_logs.sh --last 3       # 3 lần chạy gần nhất
#   bash scripts/collect_logs.sh --failed       # mọi lần chạy có status != success
#   bash scripts/collect_logs.sh --run runs/<thư_mục>
#   bash scripts/collect_logs.sh --setup        # chỉ nhật ký cài đặt (khi setup_venv.sh lỗi)
#
# Kết quả:
#   reports/bg_report_<host>_<thời_gian>.txt     -> DÁN NỘI DUNG FILE NÀY (hoặc đính kèm) khi báo lỗi
#   reports/bg_report_<host>_<thời_gian>.tar.gz  -> bản đầy đủ (đính kèm nếu được yêu cầu)
# =============================================================================
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="latest"; N=1; RUNSEL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --last) MODE="last"; N="${2:-1}"; shift ;;
    --failed) MODE="failed" ;;
    --run) MODE="run"; RUNSEL="${2:-}"; shift ;;
    --setup) MODE="setup" ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Tham số không hỗ trợ: $1"; exit 2 ;;
  esac
  shift
done

mkdir -p reports
TS="$(date +%Y%m%d-%H%M%S)"; HOST="$(hostname -s 2>/dev/null || hostname)"
BASE="reports/bg_report_${HOST}_${TS}"
TXT="${BASE}.txt"; TMP="$(mktemp -d)"; PKG="$TMP/bg_report_${HOST}_${TS}"; mkdir -p "$PKG"

sec() { echo; echo "################ $*"; }
clip() { # clip <file> <max_lines>
  local f="$1" n="${2:-80}"
  [ -f "$f" ] || { echo "(không có $f)"; return; }
  local total; total=$(wc -l < "$f" 2>/dev/null || echo 0)
  if [ "$total" -gt "$n" ]; then echo "... ($total dòng, hiện $n dòng cuối)"; tail -n "$n" "$f"; else cat "$f"; fi
}
strip() { sed -r 's/\x1B\[[0-9;]*[mK]//g'; }   # bỏ mã màu ANSI

# ---- chọn các run
RUNS=()
case "$MODE" in
  latest) [ -f runs/LATEST ] && RUNS+=("$(cat runs/LATEST)") ;;
  last)   while IFS= read -r d; do RUNS+=("$d"); done < <(ls -1dt runs/*/ 2>/dev/null | head -n "$N") ;;
  failed) for d in runs/*/; do s="$d/summary.json"
            if [ ! -f "$s" ] || ! grep -q '"status": "success"' "$s"; then RUNS+=("${d%/}"); fi; done ;;
  run)    RUNS+=("$RUNSEL") ;;
  setup)  ;;
esac

{
echo "BURSTGUARD REPORT  $(date -Iseconds)"
sec "HỆ THỐNG"
echo "version=$(cat VERSION 2>/dev/null)  git=$(git describe --tags --always --dirty 2>/dev/null) ($(git rev-parse --abbrev-ref HEAD 2>/dev/null))"
echo "host=$HOST  os=$(uname -srm)  $( [ -r /etc/os-release ] && . /etc/os-release && echo "${PRETTY_NAME:-}")"
echo "cpu=$(nproc)  mem_total=$(awk '/MemTotal/{printf "%.1fGiB",$2/1048576}' /proc/meminfo)  mem_avail=$(awk '/MemAvailable/{printf "%.1fGiB",$2/1048576}' /proc/meminfo)  disk_free=$(df -h . | awk 'NR==2{print $4}')"
echo "shm=$(df -h /dev/shm 2>/dev/null | awk 'NR==2{print $2}')  ulimit_n=$(ulimit -n)  user=$(id -un)"
echo "system_python=$(command -v python3) $(python3 -V 2>&1)"
if [ -x .venv/bin/python ]; then
  echo "venv_python=$(.venv/bin/python -V 2>&1)"
  .venv/bin/python -m pip list 2>/dev/null | grep -Ei '^(flwr|ray|torch|granite-tsfm|transformers|peft|numpy|pandas|scikit-learn|burstguard) ' | sed 's/^/  /'
else
  echo "venv: CHƯA CÓ (.venv/bin/python không tồn tại)"
fi

sec "CÀI ĐẶT GẦN NHẤT"
SL="$(ls -1t logs/setup_*.log 2>/dev/null | head -n1)"
if [ -n "$SL" ]; then
  echo "file=$SL"; cat "${SL%.log}.status" 2>/dev/null || echo "status=(không có — có thể bị ngắt giữa chừng)"
  if [ "$MODE" = "setup" ] || ! grep -q success "${SL%.log}.status" 2>/dev/null; then clip "$SL" 120 | strip; else echo "(cài đặt thành công — bỏ qua chi tiết)"; fi
else echo "(chưa chạy scripts/setup_venv.sh)"; fi

for R in "${RUNS[@]:-}"; do
  [ -n "$R" ] || continue
  R="${R%/}"
  sec "RUN $(basename "$R")"
  if [ ! -d "$R" ]; then echo "(không tồn tại: $R)"; continue; fi
  echo "-- lệnh:"; cat "$R/command.txt" 2>/dev/null
  echo "-- summary.json:"; { cat "$R/summary.json" && echo; } 2>/dev/null || echo "(chưa có summary.json — tiến trình có thể bị kill, ví dụ hết RAM/OOM)"
  if [ -f "$R/error.txt" ]; then
    EL=$(wc -l < "$R/error.txt")
    echo "-- error.txt ($EL dòng; 15 đầu + 70 cuối):"
    if [ "$EL" -gt 90 ]; then head -n 15 "$R/error.txt"; echo "   [...]"; tail -n 70 "$R/error.txt"; else cat "$R/error.txt"; fi
  fi
  if grep -q '"status": "success"' "$R/summary.json" 2>/dev/null; then OKRUN=1; else OKRUN=0; fi
  if [ "$OKRUN" = 0 ]; then
    echo "-- dòng nghi lỗi trong console.log (tối đa 60):"
    grep -nEi 'traceback|error|exception|lỗi|fail|killed|oom|out of memory|raylet|segmentation' "$R/console.log" 2>/dev/null | strip | grep -v 'RUN OK' | head -n 60
    echo "-- console.log (cuối):"; clip "$R/console.log" 80 | strip
  else
    echo "-- console.log (thành công — 25 dòng cuối):"; clip "$R/console.log" 25 | strip
  fi
  for m in "$R/metrics.jsonl" "$R"/fl_*/metrics.jsonl; do
    [ -f "$m" ] || continue
    echo "-- $(basename "$(dirname "$m")")/metrics.jsonl (6 dòng cuối, cắt 400 ký tự):"; tail -n 6 "$m" | cut -c1-400
  done
  for j in "$R"/smoke_report.json "$R"/doctor.json; do [ -f "$j" ] && { echo "-- $(basename "$j"):"; head -c 6000 "$j"; echo; }; done
done

RL="/tmp/ray/session_latest/logs"
if [ -d "$RL" ]; then
  sec "RAY (session_latest) — lỗi worker"
  ls -1t "$RL"/*.err 2>/dev/null | head -n 6 | while read -r f; do
    if [ -s "$f" ] && grep -qEi 'error|traceback|exception' "$f"; then echo "-- $(basename "$f")"; tail -n 25 "$f" | strip; fi
  done
  grep -hEi 'oom|out of memory|killed' "$RL"/raylet.* 2>/dev/null | tail -n 10
fi
echo; echo "################ HẾT BÁO CÁO"
} > "$TXT" 2>&1

# ---- gói tar.gz đầy đủ
cp "$TXT" "$PKG/"
for R in "${RUNS[@]:-}"; do
  [ -n "$R" ] && [ -d "$R" ] || continue
  mkdir -p "$PKG/runs"; rsync -a --max-size=20m "$R" "$PKG/runs/" 2>/dev/null || cp -r "$R" "$PKG/runs/"
done
ls -1t logs/setup_*.log logs/setup_*.status logs/pip_freeze_*.txt 2>/dev/null | head -n 3 | xargs -r -I{} cp {} "$PKG/" 2>/dev/null
[ -d "$RL" ] && { mkdir -p "$PKG/ray_logs"; find "$RL" -maxdepth 1 -type f \( -name '*.err' -o -name 'raylet.*' -o -name 'gcs_server.*' \) -size -5M -exec cp {} "$PKG/ray_logs/" \; 2>/dev/null; }
tar -czf "${BASE}.tar.gz" -C "$TMP" "$(basename "$PKG")" 2>/dev/null
rm -rf "$TMP"

LINES=$(wc -l < "$TXT")
if [ "$LINES" -le 400 ]; then cat "$TXT"; else head -n 200 "$TXT"; echo "... (rút gọn, xem đủ trong $TXT)"; tail -n 150 "$TXT"; fi
echo
echo "==> Báo cáo văn bản : $TXT  ($LINES dòng)  <- dán nội dung hoặc đính kèm file này"
echo "==> Gói đầy đủ      : ${BASE}.tar.gz ($(du -h "${BASE}.tar.gz" | cut -f1))"
