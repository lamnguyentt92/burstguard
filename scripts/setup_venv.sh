#!/usr/bin/env bash
# =============================================================================
# BurstGuard — tạo môi trường ảo .venv trong thư mục dự án (không cần sudo,
# không đụng tới Python hệ thống hay thư viện của dịch vụ khác).
#
#   bash scripts/setup_venv.sh            # cài đặt / cập nhật
#   bash scripts/setup_venv.sh --recreate # xoá .venv cũ rồi cài lại
#
# Mọi thứ được đặt trong dự án:
#   .venv/            môi trường ảo Python
#   .tools/uv/        công cụ uv (cài Python 3.12 riêng nếu máy chỉ có Python < 3.11)
#   .tools/python/    Python do uv quản lý (chỉ khi cần)
#   .cache/           cache pip/uv/huggingface
#   logs/setup_*.log  nhật ký cài đặt (gửi kèm khi báo lỗi)
# =============================================================================
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
mkdir -p logs .tools .cache
TS="$(date +%Y%m%d-%H%M%S)"
LOG="logs/setup_${TS}.log"
STATUS="logs/setup_${TS}.status"
exec > >(tee -a "$LOG") 2>&1

RECREATE=0
for a in "$@"; do
  case "$a" in
    --recreate) RECREATE=1 ;;
    -h|--help) sed -n '2,16p' "$0"; exit 0 ;;
    *) echo "Tham số không hỗ trợ: $a"; exit 2 ;;
  esac
done

TORCH_VERSION="2.11.0"
TORCH_CPU_INDEX="https://download.pytorch.org/whl/cpu"
export UV_CACHE_DIR="$ROOT/.cache/uv"
export PIP_CACHE_DIR="$ROOT/.cache/pip"
export UV_PYTHON_INSTALL_DIR="$ROOT/.tools/python"
export UV_NO_MODIFY_PATH=1
export UV_LINK_MODE=copy

step() { echo; echo "==================== [$(date +%H:%M:%S)] $*"; }
fail() {
  echo; echo "!!!!! CÀI ĐẶT THẤT BẠI: $*"
  echo "status=failed" > "$STATUS"; echo "reason=$*" >> "$STATUS"
  echo "Gửi nhật ký để phân tích:  bash scripts/collect_logs.sh --setup"
  exit 1
}
trap 'fail "lệnh lỗi ở dòng $LINENO: $BASH_COMMAND"' ERR

step "BurstGuard $(cat VERSION 2>/dev/null) — cài đặt môi trường tại $ROOT"
echo "host=$(hostname)  user=$(id -un)  os=$(uname -srm)"
[ -r /etc/os-release ] && . /etc/os-release && echo "distro=${PRETTY_NAME:-?}"
echo "cpu=$(nproc)  mem=$(awk '/MemTotal/{printf "%.1f GiB", $2/1048576}' /proc/meminfo)  disk_free=$(df -h . | awk 'NR==2{print $4}')"
if [ "$(id -u)" = "0" ]; then echo "CẢNH BÁO: đang chạy bằng root — không bắt buộc, nên dùng user thường."; fi

# ---------------------------------------------------------------- 1. chọn Python
step "1/5 Tìm Python 3.11–3.13"
py_ok() { "$1" -c 'import sys; sys.exit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)' 2>/dev/null; }
PY=""
for c in "${BG_PYTHON:-}" python3.12 python3.11 python3.13 python3; do
  [ -n "$c" ] || continue
  if command -v "$c" >/dev/null 2>&1 && py_ok "$c" && "$c" -c 'import venv, ensurepip' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done

UV=""
ensure_uv() {
  if [ -x "$ROOT/.tools/uv/uv" ]; then UV="$ROOT/.tools/uv/uv"; return 0; fi
  echo "Cài uv cục bộ vào .tools/uv (không sửa PATH, không cần sudo)..."
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$ROOT/.tools/uv" INSTALLER_NO_MODIFY_PATH=1 UV_NO_MODIFY_PATH=1 sh || true
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$ROOT/.tools/uv" INSTALLER_NO_MODIFY_PATH=1 UV_NO_MODIFY_PATH=1 sh || true
  fi
  if [ ! -x "$ROOT/.tools/uv/uv" ] && command -v python3 >/dev/null 2>&1; then
    echo "Thử cài uv bằng pip vào .tools/uv-pip ..."
    python3 -m pip install --target "$ROOT/.tools/uv-pip" uv >/dev/null 2>&1 || true
    [ -x "$ROOT/.tools/uv-pip/bin/uv" ] && mkdir -p "$ROOT/.tools/uv" && ln -sf "$ROOT/.tools/uv-pip/bin/uv" "$ROOT/.tools/uv/uv"
  fi
  [ -x "$ROOT/.tools/uv/uv" ] || return 1
  UV="$ROOT/.tools/uv/uv"
}

if [ -z "$PY" ]; then
  echo "Không có Python 3.11–3.13 dùng được (kèm module venv) trên máy."
  echo "-> Dùng uv để tải Python 3.12 riêng cho dự án vào .tools/python (không ảnh hưởng hệ thống)."
  ensure_uv || fail "không cài được uv; hãy cài python3.12 + python3.12-venv rồi chạy lại (hoặc đặt BG_PYTHON=/đường/dẫn/python3.12)"
  "$UV" python install 3.12 --no-bin || "$UV" python install 3.12 || fail "uv không tải được Python 3.12"
  PY="$("$UV" python find 3.12 --managed-python 2>/dev/null || "$UV" python find 3.12)"
fi
echo "Python: $PY ($("$PY" -V 2>&1))"

# ---------------------------------------------------------------- 2. tạo venv
step "2/5 Tạo môi trường ảo .venv"
if [ "$RECREATE" = "1" ] && [ -d .venv ]; then echo "Xoá .venv cũ"; rm -rf .venv; fi
if [ -x .venv/bin/python ] && ! py_ok .venv/bin/python; then
  echo ".venv hiện có dùng Python không hợp lệ -> tạo lại"; rm -rf .venv
fi
if [ ! -x .venv/bin/python ]; then
  "$PY" -m venv .venv || { ensure_uv && "$UV" venv --python "$PY" --seed .venv; } || fail "không tạo được .venv"
fi
VPY="$ROOT/.venv/bin/python"
"$VPY" -m pip --version >/dev/null 2>&1 || "$VPY" -m ensurepip --upgrade || fail "venv không có pip"
"$VPY" -m pip install --upgrade "pip>=24" wheel "setuptools>=68,<82" >/dev/null
echo "venv: $("$VPY" -V) tại $ROOT/.venv"

# ---------------------------------------------------------------- 3. torch (CPU)
step "3/5 Cài torch==$TORCH_VERSION (bản CPU)"
if "$VPY" -c "import torch,sys; sys.exit(0 if torch.__version__.split('+')[0]=='$TORCH_VERSION' else 1)" 2>/dev/null; then
  echo "torch $("$VPY" -c 'import torch;print(torch.__version__)') đã có — bỏ qua"
else
  if "$VPY" -m pip install --retries 1 --timeout 20 "torch==$TORCH_VERSION" --index-url "$TORCH_CPU_INDEX"; then
    echo "Đã cài torch CPU từ $TORCH_CPU_INDEX"
  else
    echo "CẢNH BÁO: không tải được từ $TORCH_CPU_INDEX -> dùng PyPI (bản kèm CUDA, nặng vài GB nhưng vẫn chạy trên CPU)"
    "$VPY" -m pip install "torch==$TORCH_VERSION" || fail "không cài được torch"
  fi
fi

# ---------------------------------------------------------------- 4. thư viện + dự án
step "4/5 Cài thư viện đã ghim (requirements.txt) và dự án (editable)"
"$VPY" -m pip install -r requirements.txt || fail "pip install -r requirements.txt lỗi"
"$VPY" -m pip install --no-deps -e . || fail "pip install -e . lỗi"
"$VPY" -m pip check || echo "CẢNH BÁO: pip check báo xung đột (xem trên) — thường vẫn chạy được"
"$VPY" -m pip freeze > "logs/pip_freeze_${TS}.txt"

# ---------------------------------------------------------------- 5. kiểm tra
step "5/5 Kiểm tra nhanh (burstguard doctor --no-net)"
set +e
"$ROOT/.venv/bin/burstguard" doctor --no-net
DOC=$?
set -e
trap - ERR
if [ "$DOC" = "0" ]; then
  echo "status=success" > "$STATUS"
  echo; echo "CÀI ĐẶT XONG. Bước tiếp theo:"
  echo "  source .venv/bin/activate"
  echo "  burstguard doctor        # kiểm tra đầy đủ, kể cả mạng"
  echo "  burstguard smoke         # kiểm thử đầu-cuối (~2–5 phút)"
else
  echo "status=doctor_failed" > "$STATUS"
  echo; echo "Cài xong nhưng doctor báo FAIL. Gửi log: bash scripts/collect_logs.sh --setup"
  exit 1
fi
