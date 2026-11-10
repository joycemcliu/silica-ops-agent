#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
STATE="$ROOT/.tools/grafana-mcp-forward"
BIN="${KUBECTL_BIN:-kubectl}"
PLATFORM=$(uname -s)
DEV=gke_sandboxvr-ops-development_us-west1-a_default-us-west1-a
PROD=gke_sandboxvr-ops-production_us-west1_default-us-west1
DEV_IP=127.0.0.1
PROD_IP=127.0.0.1
DEV_PORT=60007
PROD_PORT=60008
mkdir -p "$STATE"

alive() {
  [[ -f "$STATE/pid" ]] && kill -0 "$(cat "$STATE/pid")" 2>/dev/null
}

check_ports() {
  local listeners
  # Wildcard listeners also occupy the loopback ports used by these forwards.
  if [[ "$PLATFORM" == Darwin ]]; then
    # lsof exits 1 when no sockets match the requested ports.
    listeners=$(lsof -nP -iTCP:"$DEV_PORT" -iTCP:"$PROD_PORT" -sTCP:LISTEN -Fn || [[ $? -eq 1 ]])
    listeners=$(printf '%s\n' "$listeners" |
      awk '/^n(127\.0\.0\.1|0\.0\.0\.0|\*|\[::\]):/ { print substr($0, 2) }')
  else
    listeners=$(ss -H -ltn "( sport = :$DEV_PORT or sport = :$PROD_PORT )" |
      awk '$4 ~ /^(127\.0\.0\.1|0\.0\.0\.0|\*|\[::\]):/ { print }')
  fi
  if [[ -n "$listeners" ]]; then
    echo 'Cannot start: a required local port is already listening:' >&2
    printf '%s\n' "$listeners" >&2
    return 1
  fi
}

endpoint_reachable() {
  # Any HTTP response proves the tunnel works, even a 404 for an absent route.
  # This checks transport connectivity, not application health.
  curl --noproxy '*' -sS -o /dev/null --max-time 2 \
    -H "Host: localhost:$2" "http://$1:$2/"
}

forwards_reachable() {
  endpoint_reachable "$DEV_IP" "$DEV_PORT" && endpoint_reachable "$PROD_IP" "$PROD_PORT"
}

report_forward() {
  local name=$1 ip=$2 port=$3
  if endpoint_reachable "$ip" "$port" 2>/dev/null; then
    echo "$name: reachable at http://$ip:$port/mcp"
  else
    echo "$name: not reachable at $ip:$port (starting or reconnecting)"
    return 1
  fi
}

forward() {
  local context=$1 ip=$2 local_port=$3 child='' failures
  stop_child() {
    if [[ -n "$child" ]]; then
      kill -TERM "$child" 2>/dev/null || true
      wait "$child" || true
      child=''
    fi
  }
  trap stop_child EXIT
  trap 'exit 0' INT TERM
  while true; do
    echo "Starting kubectl port-forward for $context on $ip:$local_port"
    "$BIN" --context="$context" --namespace=monitoring \
      port-forward --address="$ip" service/grafana-mcp "$local_port:8000" 9>&- &
    child=$!
    failures=0
    while kill -0 "$child" 2>/dev/null; do
      sleep 5 9>&-
      kill -0 "$child" 2>/dev/null || break
      if endpoint_reachable "$ip" "$local_port" 2>/dev/null; then
        failures=0
      else
        failures=$((failures + 1))
        if (( failures >= 3 )); then
          echo "Connectivity checks failed for $context; restarting forward."
          break
        fi
      fi
    done
    stop_child
    echo "Forward for $context disconnected; retrying in 3 seconds."
    sleep 3 9>&-
  done
}

case "${1:-start}" in
  start)
    # Serialize the PID check and readiness wait across simultaneous callers.
    command -v flock >/dev/null || { echo 'Missing required command: flock' >&2; exit 1; }
    exec 8>"$STATE/start.lock"
    flock 8
    if alive; then
      echo "Already running (PID $(cat "$STATE/pid"))."
      report_forward grafana_mcp_ops_dev "$DEV_IP" "$DEV_PORT" || true
      report_forward grafana_mcp_ops_prod "$PROD_IP" "$PROD_PORT" || true
      echo "Log: $STATE/forward.log"
      exit 0
    fi
    echo 'Checking kubectl and required shell tools...'
    command -v "$BIN" >/dev/null || { echo "Install kubectl on PATH or set KUBECTL_BIN to its executable path." >&2; exit 1; }
    tools=(bash curl flock awk tail wc)
    if [[ "$PLATFORM" == Darwin ]]; then
      tools+=(lsof)
      [[ -x "$ROOT/.venv/bin/python" ]] || {
        echo 'Missing repo-local .venv/bin/python; follow docs/setup/setup-python-venv.md.' >&2
        exit 1
      }
    else
      tools+=(setsid ss)
    fi
    for tool in "${tools[@]}"; do
      command -v "$tool" >/dev/null || { echo "Missing required command: $tool" >&2; exit 1; }
    done
    echo "kubectl: $(command -v "$BIN")"
    echo "Dev:  $DEV_IP:$DEV_PORT -> monitoring/service/grafana-mcp:8000 ($DEV)"
    echo "Prod: $PROD_IP:$PROD_PORT -> monitoring/service/grafana-mcp:8000 ($PROD)"
    echo "Log: $STATE/forward.log"
    rm -f "$STATE/ready"
    touch "$STATE/forward.log"
    first_log_line=$(( $(wc -l < "$STATE/forward.log") + 1 ))
    # macOS has no setsid command; use the repo Python for the same syscall.
    if [[ "$PLATFORM" == Darwin ]]; then
      "$ROOT/.venv/bin/python" -c 'import os, sys; os.setsid(); os.execvp("bash", ["bash", sys.argv[1], "run"])' "$0" \
        8>&- </dev/null >>"$STATE/forward.log" 2>&1 &
    else
      setsid bash "$0" run 8>&- </dev/null >>"$STATE/forward.log" 2>&1 &
    fi
    child_pid=$!
    echo "Supervisor started (PID $child_pid). Waiting for both tunnels; kubectl output follows."
    tail -n "+$first_log_line" -f "$STATE/forward.log" &
    log_pid=$!
    cleanup_start() {
      kill -TERM "$log_pid" 2>/dev/null || true
      wait "$log_pid" 2>/dev/null || true
    }
    trap cleanup_start EXIT
    trap 'kill -TERM "$child_pid" 2>/dev/null || true; exit 130' INT
    trap 'kill -TERM "$child_pid" 2>/dev/null || true; exit 143' TERM
    for ((i=0; i<100; i++)); do
      if [[ -f "$STATE/ready" ]] && alive; then
        cleanup_start
        trap - EXIT INT TERM
        echo 'Both tunnels are reachable. Forwarding continues in the background with automatic reconnection.'
        echo "grafana_mcp_ops_dev:  http://$DEV_IP:$DEV_PORT/mcp   (HTTP Host: localhost:$DEV_PORT)"
        echo "grafana_mcp_ops_prod: http://$PROD_IP:$PROD_PORT/mcp  (HTTP Host: localhost:$PROD_PORT)"
        echo "Log: $STATE/forward.log"
        exit 0
      fi
      kill -0 "$child_pid" 2>/dev/null || break
      if (( i % 5 == 0 )); then
        echo "Waiting for tunnel readiness (poll $((i + 1))/100)..."
        report_forward grafana_mcp_ops_dev "$DEV_IP" "$DEV_PORT" || true
        report_forward grafana_mcp_ops_prod "$PROD_IP" "$PROD_PORT" || true
      fi
      sleep 1
    done
    kill -TERM "$child_pid" 2>/dev/null || true
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
      echo "Supervisor running (PID $(cat "$STATE/pid"))."
      result=0
      report_forward grafana_mcp_ops_dev "$DEV_IP" "$DEV_PORT" || result=1
      report_forward grafana_mcp_ops_prod "$PROD_IP" "$PROD_PORT" || result=1
      exit "$result"
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
    dev_pid='' prod_pid=''
    cleanup() {
      trap - EXIT INT TERM
      for pid in "$dev_pid" "$prod_pid"; do
        [[ -z "$pid" ]] || kill -TERM "$pid" 2>/dev/null || true
      done
      for pid in "$dev_pid" "$prod_pid"; do
        [[ -z "$pid" ]] || wait "$pid" || true
      done
      rm -f "$STATE/pid" "$STATE/ready"
    }
    trap cleanup EXIT
    trap 'exit 0' INT TERM
    check_ports
    # Run as the caller so GKE credential plugins retain their normal environment.
    forward "$DEV" "$DEV_IP" "$DEV_PORT" &
    dev_pid=$!
    forward "$PROD" "$PROD_IP" "$PROD_PORT" &
    prod_pid=$!
    for ((i=0; i<90; i++)); do
      if forwards_reachable 2>/dev/null; then
        touch "$STATE/ready"
        # Bash 3.2 on macOS has no wait -n; stop if either worker exits.
        while kill -0 "$dev_pid" 2>/dev/null && kill -0 "$prod_pid" 2>/dev/null; do
          sleep 1 9>&-
        done
        echo 'A forwarding worker exited unexpectedly.' >&2
        exit 1
      fi
      sleep 1
    done
    echo 'Timed out waiting for both forwards.' >&2
    exit 1
    ;;
  *) echo "Usage: $0 [start|stop|status]" >&2; exit 2 ;;
esac
