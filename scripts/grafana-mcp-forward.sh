#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
STATE="$ROOT/.tools/grafana-mcp-forward"
BIN="${KUBEFWD_BIN:-$ROOT/.tools/bin/kubefwd}"
DEV=gke_sandboxvr-ops-development_us-west1-a_default-us-west1-a
PROD=gke_sandboxvr-ops-production_us-west1_default-us-west1
mkdir -p "$STATE"

alive() {
  [[ -f "$STATE/pid" ]] && kill -0 "$(cat "$STATE/pid")" 2>/dev/null
}

case "${1:-start}" in
  start)
    if alive; then
      echo "Already running (PID $(cat "$STATE/pid"))."
      exit 0
    fi
    [[ -x "$BIN" ]] || { echo "Install kubefwd or set KUBEFWD_BIN." >&2; exit 1; }
    sudo -n true
    rm -f "$STATE/ready"
    # A separate session keeps forwarding alive after the calling terminal exits.
    python3 - "$0" "$STATE" <<'PY'
import pathlib, subprocess, sys
script, state = sys.argv[1:]
with open(pathlib.Path(state) / 'forward.log', 'ab', buffering=0) as log:
    subprocess.Popen(['bash', script, 'run'], stdin=subprocess.DEVNULL,
                     stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
PY
    for ((i=0; i<60; i++)); do
      if [[ -f "$STATE/ready" ]] && alive; then
        echo 'Dev:  http://grafana_mcp_ops_dev:8000/mcp   (HTTP Host: localhost:60007)'
        echo 'Prod: http://grafana_mcp_ops_prod:8000/mcp  (HTTP Host: localhost:60008)'
        echo "Log: $STATE/forward.log"
        exit 0
      fi
      sleep 1
    done
    echo "Startup failed or timed out; inspect $STATE/forward.log" >&2
    exit 1
    ;;
  stop)
    if alive; then
      kill -TERM "$(cat "$STATE/pid")"
      for ((i=0; i<30; i++)); do
        [[ -f "$STATE/pid" ]] || { echo 'Stopped.'; exit 0; }
        sleep 1
      done
      echo "Still stopping; inspect $STATE/forward.log" >&2
      exit 1
    fi
    echo 'Not running.'
    ;;
  status)
    if alive; then
      echo "Running (PID $(cat "$STATE/pid"))."
      getent hosts grafana_mcp_ops_dev grafana_mcp_ops_prod
    else
      echo 'Not running.'
      exit 1
    fi
    ;;
  run)
    exec 9>"$STATE/lock"
    flock -n 9 || exit 1
    echo $$ > "$STATE/pid"
    rm -f "$STATE/ready"
    fwd_pid=''
    cleanup() {
      trap - EXIT INT TERM
      if [[ -n "$fwd_pid" ]]; then
        sudo -n kill -INT "$fwd_pid" 2>/dev/null || true
        wait "$fwd_pid" || true
      fi
      sudo -n python3 - <<'PY'
from pathlib import Path
p = Path('/etc/hosts')
lines = p.read_text().splitlines(keepends=True)
p.write_text(''.join(l for l in lines if '# ops-agent-grafana-mcp' not in l))
PY
      rm -f "$STATE/pid" "$STATE/ready"
    }
    trap cleanup EXIT
    trap 'exit 0' INT TERM
    sudo -n env HOME="$HOME" CLOUDSDK_CONFIG="${CLOUDSDK_CONFIG:-$HOME/.config/gcloud}" \
      PATH="$PATH" "$BIN" svc --kubeconfig="${KUBECONFIG:-$HOME/.kube/config}" \
      --context="$DEV,$PROD" --namespace=monitoring \
      --field-selector=metadata.name=grafana-mcp --auto-reconnect &
    fwd_pid=$!
    for ((i=0; i<50; i++)); do
      kill -0 "$fwd_pid" 2>/dev/null || { wait "$fwd_pid"; exit 1; }
      # Read context-qualified entries instead of assuming allocated IPs.
      dev_ip=$(getent ahostsv4 "grafana-mcp.monitoring.$DEV" | awk 'NR==1 {print $1}' || true)
      prod_ip=$(getent ahostsv4 "grafana-mcp.monitoring.$PROD" | awk 'NR==1 {print $1}' || true)
      if [[ "$dev_ip" == 127.* && "$prod_ip" == 127.* && "$dev_ip" != "$prod_ip" ]] && \
         curl --noproxy '*' -s -o /dev/null --max-time 2 -H 'Host: localhost:60007' "http://$dev_ip:8000/health" && \
         curl --noproxy '*' -s -o /dev/null --max-time 2 -H 'Host: localhost:60008' "http://$prod_ip:8000/health"; then
        sudo -n python3 - "$dev_ip" "$prod_ip" <<'PY'
import sys
from pathlib import Path
p = Path('/etc/hosts')
s = ''.join(l for l in p.read_text().splitlines(keepends=True)
            if '# ops-agent-grafana-mcp' not in l)
s += f'\n{sys.argv[1]} grafana_mcp_ops_dev # ops-agent-grafana-mcp\n'
s += f'{sys.argv[2]} grafana_mcp_ops_prod # ops-agent-grafana-mcp\n'
p.write_text(s)
PY
        touch "$STATE/ready"
        wait "$fwd_pid"
        exit $?
      fi
      sleep 1
    done
    echo 'Timed out waiting for both forwards.' >&2
    exit 1
    ;;
  *) echo "Usage: $0 [start|stop|status]" >&2; exit 2 ;;
esac
