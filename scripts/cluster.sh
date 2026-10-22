#!/usr/bin/env bash
# =============================================================================
# BurstGuard - drive the 5-VM campaign from ONE machine (the VM that has the data, e.g. vm-e) over ssh.
#
# 1) list the OTHER VMs, one ssh target per line, in  ~/burstguard-shared/cluster.hosts
#        root@10.0.0.12
#        root@10.0.0.13          (or ssh aliases from ~/.ssh/config, e.g. vm2)
# 2) bash scripts/cluster.sh keys        # ssh key + ssh-copy-id to every VM (type each VM's password once)
#    bash scripts/cluster.sh check       # ssh, git, python3, tmux, rsync, CPU/RAM/disk on every VM
#    bash scripts/cluster.sh push-data   # copy milan_d1.npz + Hugging Face model cache to every VM
#    bash scripts/cluster.sh install     # clone release/v<VERSION> + setup_venv.sh on every VM (in parallel)
#    bash scripts/cluster.sh smoke       # burstguard smoke on every VM (in parallel)
#    bash scripts/cluster.sh start "--tier pilot,calibration" "E1_clean"
#                                        # every VM (this one = shard 1) runs, in a detached tmux session "bg":
#                                        #   run_grids.sh k/N --tier pilot,calibration ; run_grids.sh k/N E1_clean
#    bash scripts/cluster.sh status      # progress on every VM
#    bash scripts/cluster.sh stop        # stop the tmux session "bg" everywhere (start again = resume)
# Options (before the command): --hosts FILE, --no-local (this machine does not run a shard), --force
# Logs: logs/cluster_<command>_<host>_<time>.log
# =============================================================================
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VER="$(cat VERSION)"
SHARED="${BURSTGUARD_SHARED:-$HOME/burstguard-shared}"
HOSTS_FILE="$SHARED/cluster.hosts"
REPO="https://github.com/lamnguyentt92/burstguard.git"
RDIR="burstguard-v$VER"                     # remote checkout, relative to the remote home
LOCAL=1; FORCE=0
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)

while [ $# -gt 0 ]; do
  case "$1" in
    --hosts) HOSTS_FILE="$2"; shift 2 ;;
    --no-local) LOCAL=0; shift ;;
    --force) FORCE=1; shift ;;
    *) break ;;
  esac
done
CMD="${1:-}"; shift || true
mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
say() { echo "[burstguard v$VER cluster] $*"; }

if [ -z "$CMD" ] || [ "$CMD" = "-h" ] || [ "$CMD" = "--help" ]; then sed -n '2,24p' "$0"; exit 0; fi
if [ ! -f "$HOSTS_FILE" ]; then
  mkdir -p "$(dirname "$HOSTS_FILE")"
  cat > "$HOSTS_FILE" <<'EOF'
# One ssh target per line for the OTHER VMs (not this one). Examples:
# root@10.0.0.12
# root@10.0.0.13
# vm4            (an alias defined in ~/.ssh/config)
EOF
  say "created $HOSTS_FILE - put the other VMs in it (one per line), then run this command again"; exit 2
fi
mapfile -t HOSTS < <(grep -vE '^\s*(#|$)' "$HOSTS_FILE" | awk '{print $1}')
[ ${#HOSTS[@]} -ge 1 ] || { say "no hosts in $HOSTS_FILE"; exit 2; }
N=$(( ${#HOSTS[@]} + LOCAL ))
hlog() { echo "logs/cluster_${CMD}_$(echo "$1" | tr '@/:' '___')_${TS}.log"; }
rsh() { local h="$1"; shift; ssh "${SSH_OPTS[@]}" "$h" "$@"; }

case "$CMD" in
# -----------------------------------------------------------------------------------------------------------
keys)
  KEY="$HOME/.ssh/id_ed25519"
  if [ ! -f "$KEY" ]; then say "creating ssh key $KEY"; ssh-keygen -t ed25519 -N "" -f "$KEY" -q; fi
  for h in "${HOSTS[@]}"; do
    if rsh "$h" true 2>/dev/null; then say "$h: key login already works"; continue; fi
    say "$h: copying the key (type the password of $h once)"
    if ! ssh-copy-id -o StrictHostKeyChecking=accept-new -i "$KEY.pub" "$h"; then
      say "$h: ssh-copy-id failed (password login disabled?). Do it by hand ON $h:"
      echo "    mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo '$(cat "$KEY.pub")' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys"
    fi
  done
  for h in "${HOSTS[@]}"; do
    if rsh "$h" true 2>/dev/null; then say "$h: OK"; else say "$h: STILL NO KEY LOGIN"; fi
  done ;;
# -----------------------------------------------------------------------------------------------------------
check)
  rc=0
  for h in "${HOSTS[@]}"; do
    out=$(rsh "$h" 'printf "host=%s cpu=%s mem_avail=%sGiB disk_free=%s " "$(hostname)" "$(nproc)" \
      "$(awk "/MemAvailable/{printf \"%.1f\", \$2/1048576}" /proc/meminfo)" "$(df -h ~ | awk "NR==2{print \$4}")";
      for t in git python3 tmux rsync curl; do command -v $t >/dev/null && printf "%s=ok " $t || printf "%s=MISSING " $t; done;
      test -f ~/burstguard-shared/data/processed/milan_d1.npz && printf "data=ok " || printf "data=missing ";
      test -d ~/'"$RDIR"'/.venv && printf "venv=ok" || printf "venv=missing"' 2>&1) || { rc=1; out="UNREACHABLE: $out"; }
    echo "  $h: $out"
  done
  echo "  (missing tools on Ubuntu: sudo apt-get install -y git tmux rsync curl)"
  exit $rc ;;
# -----------------------------------------------------------------------------------------------------------
push-data)
  NPZ="$SHARED/data/processed/milan_d1.npz"; HF="$SHARED/hf"
  [ -f "$NPZ" ] || { say "missing $NPZ - run burstguard data download && burstguard data prepare here first"; exit 2; }
  [ -d "$HF/hub" ] || say "WARNING: no model cache in $HF (run burstguard model-download here first)"
  rc=0
  for h in "${HOSTS[@]}"; do
    say "$h: copying milan_d1.npz and the model cache"
    rsh "$h" 'mkdir -p ~/burstguard-shared/data/processed ~/burstguard-shared/hf' || { say "$h: unreachable"; rc=1; continue; }
    scp -q "${SSH_OPTS[@]}" "$NPZ" "$h:burstguard-shared/data/processed/" || rc=1
    if command -v rsync >/dev/null && rsh "$h" 'command -v rsync >/dev/null'; then
      rsync -a -e "ssh ${SSH_OPTS[*]}" "$HF/" "$h:burstguard-shared/hf/" || rc=1
    else
      scp -q -r "${SSH_OPTS[@]}" "$HF/." "$h:burstguard-shared/hf/" || rc=1
    fi
    rsh "$h" 'ls -l ~/burstguard-shared/data/processed/milan_d1.npz | awk "{print \"    \" \$5 \" bytes \" \$9}"'
  done
  exit $rc ;;
# -----------------------------------------------------------------------------------------------------------
install)
  for h in "${HOSTS[@]}"; do
    L="$(hlog "$h")"
    say "$h: clone release/v$VER into ~/$RDIR and run setup_venv.sh (log: $L)"
    rsh "$h" "set -e; if [ -d ~/$RDIR/.git ]; then echo 'checkout exists'; else git clone -q -b release/v$VER $REPO ~/$RDIR; fi;
      cd ~/$RDIR; git config core.fileMode false; cat VERSION; bash scripts/setup_venv.sh" > "$L" 2>&1 &
  done
  wait
  rc=0
  for h in "${HOSTS[@]}"; do
    L="$(hlog "$h")"
    if grep -q "SETUP COMPLETE" "$L"; then say "$h: setup OK"; else say "$h: setup FAILED - see $L (last lines below)"; tail -n 8 "$L"; rc=1; fi
  done
  exit $rc ;;
# -----------------------------------------------------------------------------------------------------------
smoke)
  for h in "${HOSTS[@]}"; do
    rsh "$h" "cd ~/$RDIR && .venv/bin/burstguard smoke" > "$(hlog "$h")" 2>&1 &
  done
  wait
  rc=0
  for h in "${HOSTS[@]}"; do
    L="$(hlog "$h")"
    if grep -q "RUN OK" "$L"; then say "$h: smoke OK ($(grep -c '\[PASS\]' "$L") PASS)"; else say "$h: smoke FAILED - $L"; tail -n 15 "$L"; rc=1; fi
  done
  exit $rc ;;
# -----------------------------------------------------------------------------------------------------------
start)
  [ $# -ge 1 ] || { say 'usage: cluster.sh start "--tier pilot,calibration" ["E1_clean" ...]'; exit 2; }
  start_one() {  # $1 = host or "local", $2 = shard k, rest = run_grids argument groups
    local h="$1" k="$2"; shift 2
    local chain="cd ~/$RDIR"
    [ "$h" = "local" ] && chain="cd $ROOT"
    for a in "$@"; do chain="$chain; bash scripts/run_grids.sh $k/$N $a"; done
    if [ "$h" = "local" ]; then
      if tmux has-session -t bg 2>/dev/null && [ $FORCE = 0 ]; then say "local: tmux session 'bg' already running (use --force after 'stop')"; return 1; fi
      if tmux new-session -d -s bg "$chain"; then say "local (shard $k/$N): started -> tmux attach -t bg"
      else say "local: FAILED to start tmux"; return 1; fi
    else
      if rsh "$h" 'tmux has-session -t bg 2>/dev/null' && [ $FORCE = 0 ]; then say "$h: tmux session 'bg' already running"; return 1; fi
      if rsh "$h" "tmux new-session -d -s bg '$chain'"; then say "$h (shard $k/$N): started -> ssh -t $h tmux attach -t bg"
      else say "$h: FAILED to start (is tmux installed? bash scripts/cluster.sh check)"; return 1; fi
    fi
  }
  k=1; rc=0
  if [ $LOCAL = 1 ]; then start_one local 1 "$@" || rc=1; k=2; fi
  for h in "${HOSTS[@]}"; do start_one "$h" "$k" "$@" || rc=1; k=$((k + 1)); done
  say "each machine runs its own shard (1..$N). Check: bash scripts/cluster.sh status"
  exit $rc ;;
# -----------------------------------------------------------------------------------------------------------
status)
  show() {
    echo "  tmux: $(tmux has-session -t bg 2>/dev/null && echo running || echo 'not running')"
    local f; f=$(ls -1t logs/run_grids_v*.log 2>/dev/null | head -n1)
    [ -n "$f" ] && { echo "  $f:"; grep -E 'START|END|ALL GRIDS|failed jobs' "$f" | tail -n 4 | sed 's/^/    /'; tail -n 1 "$f" | cut -c1-160 | sed 's/^/    /'; }
    for g in results/v*/*/; do [ -d "$g" ] || continue; case "$(basename "$g")" in _*) continue ;; esac
      echo "  $(basename "$g"): ok=$(grep -l '"status": "success"' "$g"*/result.json 2>/dev/null | wc -l) failed=$(grep -l '"status": "failed"' "$g"*/result.json 2>/dev/null | wc -l) running=$(ls "$g"*/started 2>/dev/null | wc -l)"
    done
  }
  if [ $LOCAL = 1 ]; then echo "== local ($(hostname))"; show; fi
  for h in "${HOSTS[@]}"; do
    echo "== $h"
    rsh "$h" "cd ~/$RDIR 2>/dev/null || { echo '  no checkout'; exit 0; }; $(declare -f show); show" 2>&1 || echo "  unreachable"
  done ;;
# -----------------------------------------------------------------------------------------------------------
stop)
  [ $LOCAL = 1 ] && { tmux kill-session -t bg 2>/dev/null && say "local: stopped" || say "local: not running"; }
  for h in "${HOSTS[@]}"; do rsh "$h" 'tmux kill-session -t bg 2>/dev/null' && say "$h: stopped" || say "$h: not running"; done
  say "unfinished jobs resume with the same start command" ;;
*)
  say "unknown command: $CMD (bash scripts/cluster.sh --help)"; exit 2 ;;
esac
