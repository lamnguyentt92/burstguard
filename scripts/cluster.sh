#!/usr/bin/env bash
# =============================================================================
# BurstGuard - drive the 5-VM campaign from ONE machine (the VM that has the data, e.g. vm-e) over ssh.
# No tmux needed: jobs run in the background with nohup (they keep running when you log out).
#
# 1) list the OTHER VMs, one ssh target per line, in  ~/burstguard-shared/cluster.hosts
#        root@10.0.0.12
#        root@10.0.0.13          (or ssh aliases from ~/.ssh/config, e.g. vm2)
# 2) bash scripts/cluster.sh keys        # ssh key + ssh-copy-id to every VM (type each VM's password once)
#    bash scripts/cluster.sh check       # ssh, git, python3, rsync, CPU/RAM/disk on every VM
#    bash scripts/cluster.sh push-data   # copy milan_d1.npz + Hugging Face model cache to every VM
#    bash scripts/cluster.sh install     # clone release/v<VERSION> + setup_venv.sh on every VM (in parallel)
#    bash scripts/cluster.sh smoke       # burstguard smoke on every VM (in parallel)
#    bash scripts/cluster.sh start "--tier pilot,calibration" "E1_clean"
#                                        # every machine (this one = shard 1) runs in the background:
#                                        #   run_grids.sh k/N --tier pilot,calibration ; run_grids.sh k/N E1_clean
#    bash scripts/cluster.sh status      # progress on every machine
#    bash scripts/cluster.sh --bg collect P0_pilot E0_calibration
#                                        # in the background: wait until these grids are finished on all machines
#                                        # (pull results every 10 min), then analyze all, calibrate, plan and
#                                        # collect_logs --campaign. Follow it: tail -f logs/cluster_collect_*.log
#    bash scripts/cluster.sh stop        # stop the background run everywhere (start again = resume)
# Options (before the command):
#   --hosts FILE   other hosts file          --no-local   this machine does not run a shard
#   --local-only   only this machine (e.g. E8: --local-only --name e8 start "--tier system")
#   --name NAME    name of the background run (default bg)      --force   start even if one is running
#   --bg           run the command itself in the background (for collect)
# Logs: logs/cluster_<command>_<host>_<time>.log, background output logs/cluster_<name>.out (on each machine)
# =============================================================================
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
VER="$(cat VERSION)"
SHARED="${BURSTGUARD_SHARED:-$HOME/burstguard-shared}"
HOSTS_FILE="$SHARED/cluster.hosts"
REPO="https://github.com/lamnguyentt92/burstguard.git"
RDIR="burstguard-v$VER"                     # remote checkout, relative to the remote home
LOCAL=1; REMOTE=1; FORCE=0; NAME="bg"; BG=0
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new)
ORIG_ARGS=("$@")

while [ $# -gt 0 ]; do
  case "$1" in
    --hosts) HOSTS_FILE="$2"; shift 2 ;;
    --no-local) LOCAL=0; shift ;;
    --local-only) REMOTE=0; shift ;;
    --name) NAME="$2"; shift 2 ;;
    --force) FORCE=1; shift ;;
    --bg) BG=1; shift ;;
    *) break ;;
  esac
done
CMD="${1:-}"; shift || true
mkdir -p logs
TS="$(date +%Y%m%d-%H%M%S)"
say() { echo "[burstguard v$VER cluster $(date +%H:%M:%S)] $*"; }

if [ -z "$CMD" ] || [ "$CMD" = "-h" ] || [ "$CMD" = "--help" ]; then sed -n '2,31p' "$0"; exit 0; fi

# --bg: re-run this very command detached from the terminal (survives logout), output in a log file
if [ $BG = 1 ]; then
  OUT="logs/cluster_${CMD}_${TS}.log"
  ARGS=(); for a in "${ORIG_ARGS[@]}"; do [ "$a" = "--bg" ] || ARGS+=("$a"); done
  nohup setsid bash "$0" "${ARGS[@]}" > "$OUT" 2>&1 < /dev/null &
  say "running '$CMD' in the background (pid $!). Follow it: tail -f $ROOT/$OUT  (Ctrl-C only stops tail)"
  exit 0
fi

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
N=$(( ${#HOSTS[@]} + 1 ))                   # shard count: this machine + the hosts (fixed by the hosts file)
[ $REMOTE = 1 ] || HOSTS=()
hlog() { echo "logs/cluster_${CMD}_$(echo "$1" | tr '@/:' '___')_${TS}.log"; }
rsh() { local h="$1"; shift; ssh "${SSH_OPTS[@]}" "$h" "$@"; }

# background-run helpers (executed locally, or sent to a remote shell with declare -f)
bg_alive() { [ -f "logs/cluster_$1.pid" ] && kill -0 "$(cat "logs/cluster_$1.pid")" 2>/dev/null; }
bg_start() {  # $1 = name, $2 = command chain
  mkdir -p logs
  nohup setsid bash -c "$2" > "logs/cluster_$1.out" 2>&1 < /dev/null &
  echo $! > "logs/cluster_$1.pid"
}
bg_stop() {
  if bg_alive "$1"; then local p; p=$(cat "logs/cluster_$1.pid")
    kill -TERM -- "-$p" 2>/dev/null || kill -TERM "$p"; sleep 2; kill -KILL -- "-$p" 2>/dev/null; echo stopped
  else echo "not running"; fi
}
FUNCS="$(declare -f bg_alive bg_start bg_stop)"

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
      for t in git python3 rsync curl setsid; do command -v $t >/dev/null && printf "%s=ok " $t || printf "%s=MISSING " $t; done;
      test -f ~/burstguard-shared/data/processed/milan_d1.npz && printf "data=ok " || printf "data=missing ";
      test -d ~/'"$RDIR"'/.venv && printf "venv=ok" || printf "venv=missing"' 2>&1) || { rc=1; out="UNREACHABLE: $out"; }
    echo "  $h: $out"
  done
  echo "  (missing tools on Ubuntu: sudo apt-get install -y git rsync curl)"
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
  chain_for() {  # $1 = checkout dir, $2 = shard spec, rest = run_grids argument groups
    local dir="$1" spec="$2"; shift 2
    local c="cd $dir"
    for a in "$@"; do c="$c; bash scripts/run_grids.sh $spec $a"; done
    echo "$c"
  }
  rc=0
  if [ $LOCAL = 1 ]; then
    spec="1/$N"; [ $REMOTE = 0 ] && spec="1/1"
    if bg_alive "$NAME" && [ $FORCE = 0 ]; then say "local: '$NAME' is already running (stop it first)"; rc=1
    else bg_start "$NAME" "$(chain_for "$ROOT" "$spec" "$@")"
         say "local (shard $spec): started - output: $ROOT/logs/cluster_$NAME.out"; fi
  fi
  k=2
  for h in "${HOSTS[@]}"; do
    chain="$(chain_for "~/$RDIR" "$k/$N" "$@")"
    res=$(rsh "$h" "cd ~/$RDIR || exit 4; $FUNCS; if bg_alive $NAME && [ $FORCE = 0 ]; then echo RUNNING; else bg_start $NAME '$chain'; echo STARTED; fi" 2>&1)
    case "$res" in
      *STARTED*) say "$h (shard $k/$N): started - output: ~/$RDIR/logs/cluster_$NAME.out on $h" ;;
      *RUNNING*) say "$h: '$NAME' is already running (stop it first)"; rc=1 ;;
      *) say "$h: FAILED to start: $res"; rc=1 ;;
    esac
    k=$((k + 1))
  done
  say "each machine runs its own shard. Check: bash scripts/cluster.sh status"
  exit $rc ;;
# -----------------------------------------------------------------------------------------------------------
status)
  show() {
    if bg_alive "$1"; then echo "  run '$1': RUNNING (pid $(cat "logs/cluster_$1.pid"))"; else echo "  run '$1': not running"; fi
    local f; f=$(ls -1t logs/run_grids_v*.log 2>/dev/null | head -n1)
    [ -n "$f" ] && { echo "  $f:"; grep -E 'START|END|ALL GRIDS|failed jobs' "$f" | tail -n 4 | sed 's/^/    /'; }
    for g in results/v*/*/; do [ -d "$g" ] || continue; case "$(basename "$g")" in _*) continue ;; esac
      echo "  $(basename "$g"): ok=$(grep -l '"status": "success"' "$g"*/result.json 2>/dev/null | wc -l) failed=$(grep -l '"status": "failed"' "$g"*/result.json 2>/dev/null | wc -l) running=$(ls "$g"*/started 2>/dev/null | wc -l)"
    done
  }
  if [ $LOCAL = 1 ]; then echo "== local ($(hostname))"; show "$NAME"; fi
  for h in "${HOSTS[@]}"; do
    echo "== $h"
    rsh "$h" "cd ~/$RDIR 2>/dev/null || { echo '  no checkout'; exit 0; }; $FUNCS; $(declare -f show); show $NAME" 2>&1 || echo "  unreachable"
  done ;;
# -----------------------------------------------------------------------------------------------------------
stop)
  [ $LOCAL = 1 ] && say "local: $(bg_stop "$NAME")"
  for h in "${HOSTS[@]}"; do say "$h: $(rsh "$h" "cd ~/$RDIR 2>/dev/null || exit 0; $FUNCS; bg_stop $NAME" 2>&1)"; done
  say "unfinished jobs resume with the same start command" ;;
# -----------------------------------------------------------------------------------------------------------
collect)
  GRIDS=("$@"); [ ${#GRIDS[@]} -ge 1 ] || GRIDS=(P0_pilot E0_calibration)
  BG_BIN="$ROOT/.venv/bin/burstguard"
  [ -x "$BG_BIN" ] || { say "missing $BG_BIN - run bash scripts/setup_venv.sh"; exit 2; }
  pending() { local g; for g in "${GRIDS[@]}"; do
      "$BG_BIN" grid status "experiments/$g.toml" 2>/dev/null | grep -qE '"(pending|running)"' && return 0; done; return 1; }
  say "waiting for ${GRIDS[*]} on all machines (results pulled every ${WAIT_MIN:-10} min)"
  while true; do
    bash scripts/sync_results.sh > "logs/cluster_collect_sync.log" 2>&1 || say "warning: some machines could not be synced (logs/cluster_collect_sync.log)"
    pending || break
    say "not finished yet: $(for g in "${GRIDS[@]}"; do printf '%s ' "$g:$(ls results/v$VER/$g/*/result.json 2>/dev/null | wc -l)/$("$BG_BIN" grid list "experiments/$g.toml" 2>/dev/null | grep -oE '^[0-9]+ jobs' | cut -d' ' -f1)"; done)"
    sleep $(( ${WAIT_MIN:-10} * 60 ))
  done
  say "all finished - analysing"
  "$BG_BIN" analyze all
  [ -d "results/v$VER/E0_calibration" ] && "$BG_BIN" calibrate experiments/E0_calibration.toml
  "$BG_BIN" plan
  bash scripts/collect_logs.sh --campaign
  say "DONE - send the two newest files in $ROOT/reports/ (.txt and .tar.gz)" ;;
# -----------------------------------------------------------------------------------------------------------
*)
  say "unknown command: $CMD (bash scripts/cluster.sh --help)"; exit 2 ;;
esac
