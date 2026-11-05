#!/bin/bash

set -u

CONTEXT="gke_infra-automate-production_us-west1_default-us-west1"
NAMESPACE="stores-socat"
REMOTE_SSH_PORT=22
READINESS_RETRIES=30
NODE="${PROD_SSH_NODE:-${PN_NODE:-}}"
NODE_EXPLICIT=0
NODE_POSITIONAL_CONSUMED=0
SSH_USER="${PROD_SSH_USER:-silica}"
CLUSTER_REQUEST="${PROD_SSH_CLUSTER:-}"
CLUSTER_EXPLICIT=0
PASSWORD_FILE_DEFAULT="${HOME}/.local/secrets/silica-prod-master-node-password"
PASSWORD_FILE="${PROD_SSH_PASSWORD_FILE-$PASSWORD_FILE_DEFAULT}"
PASSWORD_FILE_EXPLICIT=0
[[ -n "${PROD_SSH_PASSWORD_FILE+x}" ]] && PASSWORD_FILE_EXPLICIT=1
CREATED_PORT_FORWARD_PID=""
PROBE_DIR=""
PROBE_PIDS=()

error() {
  printf 'ERROR: %s\n' "$*" >&2
}

info() {
  # Informational output from the wrapper, written to stderr so it never
  # mixes with ssh's stdout. Suppressed with --quiet.
  [[ "${QUIET:-0}" -eq 1 ]] && return 0
  printf '%s\n' "$*" >&2
}

print_prefixed_file() {
  local prefix="$1"
  local file="$2"

  [[ -s "$file" ]] || return 0
  sed "s/^/${prefix}/" "$file" >&2
}

cleanup_port_forward() {
  local probe_pid
  for probe_pid in "${PROBE_PIDS[@]}"; do
    kill "$probe_pid" 2>/dev/null || true
  done
  for probe_pid in "${PROBE_PIDS[@]}"; do
    wait "$probe_pid" 2>/dev/null || true
  done
  PROBE_PIDS=()
  if [[ -n "$PROBE_DIR" ]]; then
    rm -rf -- "$PROBE_DIR"
    PROBE_DIR=""
  fi

  [[ -n "${CREATED_PORT_FORWARD_PID:-}" ]] || return 0

  if kill -0 "$CREATED_PORT_FORWARD_PID" 2>/dev/null; then
    kill "$CREATED_PORT_FORWARD_PID" 2>/dev/null || true
    wait "$CREATED_PORT_FORWARD_PID" 2>/dev/null || true
  fi
}

trap cleanup_port_forward EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

require_command() {
  local command_name="$1"

  if ! command -v "$command_name" >/dev/null 2>&1; then
    error "Required command '${command_name}' was not found in PATH."
    exit 1
  fi
}

validate_password_file() {
  local password_file="$1"
  local mode
  local group_perms
  local other_perms

  if [[ ! -f "$password_file" ]]; then
    error "Password file '${password_file}' does not exist."
    exit 1
  fi

  if [[ ! -r "$password_file" ]]; then
    error "Password file '${password_file}' is not readable."
    exit 1
  fi

  require_command stat
  if [[ "$(uname -s)" == "Darwin" ]]; then
    mode=$(stat -f '%Lp' "$password_file" 2>/dev/null)
  else
    mode=$(stat -c '%a' "$password_file" 2>/dev/null)
  fi
  if [[ $? -ne 0 ]]; then
    error "Could not read permissions for password file '${password_file}'."
    exit 1
  fi

  if [[ ! "$mode" =~ ^[0-7]{3,4}$ ]]; then
    error "Unexpected permission format '${mode}' for password file '${password_file}'."
    exit 1
  fi

  group_perms=${mode: -2:1}
  other_perms=${mode: -1}
  if (( group_perms != 0 || other_perms != 0 )); then
    error "Password file '${password_file}' must not be accessible by group or others. Run: chmod 600 '${password_file}'"
    exit 1
  fi
}

port_listening() {
  local local_port="$1"
  nc -z -w 1 127.0.0.1 "$local_port" >/dev/null 2>&1
}

wait_for_ssh_port() {
  local local_port="$1"
  local port_forward_pid="${2:-}"
  local log_file="${3:-}"
  local retry=0

  while ! port_listening "$local_port"; do
    retry=$((retry + 1))

    if [[ -n "$port_forward_pid" ]] && ! kill -0 "$port_forward_pid" 2>/dev/null; then
      error "kubectl port-forward exited before SSH port ${local_port} became ready."
      print_prefixed_file "kubectl: " "$log_file"
      exit 1
    fi

    if [[ $retry -ge $READINESS_RETRIES ]]; then
      error "SSH port ${local_port} did not become ready after ${READINESS_RETRIES} seconds."
      [[ -n "$log_file" ]] && print_prefixed_file "kubectl: " "$log_file"
      exit 1
    fi

    sleep 1
  done

  printf '%s' "$retry"
}

extract_local_port() {
  local process_args="$1"
  local remote_port="$2"

  grep -oE "[0-9]+:${remote_port}( |$)" <<< "$process_args" | head -1 | cut -d: -f1
}

# Measure the remote SSH greeting, rather than only the local kubectl listener.
ssh_banner_ready() {
  local local_port="$1" banner
  local SECONDS=0

  { exec 3<>/dev/tcp/127.0.0.1/"$local_port"; } 2>/dev/null || return 1
  while (( SECONDS < 3 )); do
    if ! IFS= read -r -t "$((3 - SECONDS))" banner <&3; then
      break
    fi
    case "$banner" in
      SSH-2.0-*|SSH-1.99-*)
        exec 3<&- 3>&-
        return 0
        ;;
    esac
  done
  exec 3<&- 3>&-
  return 1
}

probe_node() (
  local node="$1"
  local pod="${STORE_ID}-socat-shared-${node}"
  local log_file="${PROBE_DIR}/${node}.log"
  local timing_file="${PROBE_DIR}/${node}.time"
  local probe_pid="" local_port="" retry latency
  local TIMEFORMAT='%R' LC_ALL=C

  # Each worker owns its tunnel, including when interrupted by parent cleanup.
  trap 'if [[ -n "$probe_pid" ]]; then kill "$probe_pid" 2>/dev/null || true; wait "$probe_pid" 2>/dev/null || true; fi' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP

  # Ephemeral local ports avoid collisions with existing forwards and invocations.
  kubectl --context "$CONTEXT" -n "$NAMESPACE" port-forward \
    --address 127.0.0.1 "pod/${pod}" ":${REMOTE_SSH_PORT}" >"$log_file" 2>&1 &
  probe_pid=$!

  for ((retry = 0; retry < READINESS_RETRIES; retry++)); do
    kill -0 "$probe_pid" 2>/dev/null || break
    local_port=$(sed -n 's/^Forwarding from 127\.0\.0\.1:\([0-9][0-9]*\) ->.*/\1/p' "$log_file")
    [[ -n "$local_port" ]] && break
    sleep 1
  done

  if [[ -n "$local_port" ]] && { time ssh_banner_ready "$local_port"; } 2>"$timing_file"; then
    latency=$(cat "$timing_file")
    printf '%s %s\n' "$latency" "$node" >"${PROBE_DIR}/${node}.result"
    info "Node ${node}: SSH response in ${latency}s"
  else
    info "Node ${node}: SSH unavailable or greeting timed out"
  fi
)

select_responsive_node() {
  local node probe_pid fastest_latency
  require_command mktemp
  require_command sort
  PROBE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/prod-ssh-probes.XXXXXX") || {
    error "Could not create temporary directory for node probes."
    return 1
  }

  info "Checking SSH responsiveness of nodes 1-3..."
  for node in 1 2 3; do
    probe_node "$node" &
    PROBE_PIDS+=("$!")
  done
  for probe_pid in "${PROBE_PIDS[@]}"; do
    wait "$probe_pid" || true
  done
  PROBE_PIDS=()

  # Failed probes leave no result, so unavailable nodes cannot be selected.
  : >"${PROBE_DIR}/results"
  for node in 1 2 3; do
    [[ ! -s "${PROBE_DIR}/${node}.result" ]] || cat "${PROBE_DIR}/${node}.result" >>"${PROBE_DIR}/results"
  done
  if ! read -r fastest_latency NODE < <(LC_ALL=C sort -n "${PROBE_DIR}/results"); then
    error "No node among 1-3 returned an SSH greeting. Specify --node to target a node directly."
    return 1
  fi
  info "Selected node ${NODE} (SSH response ${fastest_latency}s)."
  rm -rf -- "$PROBE_DIR"
  PROBE_DIR=""
}

usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") [-c STORE_CODE] [--node NODE] [--user USER] [--] [remote command...]
       $(basename "$0") <STORE_CODE> [NODE] [--] [remote command...]

Options:
  -c, --cluster STORE_CODE  Store code (e.g. hkcwbmid). Case-insensitive. When
  --store STORE_CODE        provided, skips AGENTS.md and infra-cluster.json and
                            resolves the subnet from Kubernetes directly. Can also
                            be set with PROD_SSH_CLUSTER. May also be given as the
                            first positional argument.
  --node NODE, --node=NODE  Port-forward to a specific shared pod. NODE may be
                            an index like 1, shared-1, socat-shared-1, or the
                            full pod name. Can also be set with PROD_SSH_NODE
                            or PN_NODE, or given as the second positional
                            argument. If omitted, probes nodes 1-3 in parallel
                            and selects the fastest SSH greeting (3s timeout
                            after each probe tunnel becomes ready).
  --user USER, --user=USER  SSH login user. Can also be set with PROD_SSH_USER.
                            Defaults to silica.
  -q, --quiet               Suppress output from this wrapper; show only output
                            from ssh itself.
  --help                    Show this help.

Environment:
  PROD_SSH_CLUSTER          Default store code (same as --cluster).
  PROD_SSH_PASSWORD_FILE    Password file for sshpass. Defaults to
                            ${PASSWORD_FILE_DEFAULT}. If the default file is
                            absent, normal interactive ssh auth is used.
                            Set to an empty string to disable password-file use.

Any remaining arguments are passed to ssh as the remote command after the
127.0.0.1 destination. Examples:
  $(basename "$0") -c hkcwbmid --node 1 -- uptime
  $(basename "$0") hkcwbmid 1 -- uptime
  $(basename "$0") hkcwbmid -- uptime  # Automatically select a responsive node
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--cluster|--store)
      if [[ $# -lt 2 || -z "$2" ]]; then
        error "$1 requires a value."
        usage
        exit 1
      fi
      CLUSTER_REQUEST="$2"
      CLUSTER_EXPLICIT=1
      shift 2
      ;;
    --cluster=*|--store=*)
      CLUSTER_REQUEST="${1#*=}"
      if [[ -z "$CLUSTER_REQUEST" ]]; then
        error "--cluster requires a value."
        usage
        exit 1
      fi
      CLUSTER_EXPLICIT=1
      shift
      ;;
    --node)
      if [[ $# -lt 2 || -z "$2" ]]; then
        error "--node requires a value."
        usage
        exit 1
      fi
      NODE="$2"
      NODE_EXPLICIT=1
      shift 2
      ;;
    --node=*)
      NODE="${1#--node=}"
      if [[ -z "$NODE" ]]; then
        error "--node requires a value."
        usage
        exit 1
      fi
      NODE_EXPLICIT=1
      shift
      ;;
    --user)
      if [[ $# -lt 2 || -z "$2" ]]; then
        error "--user requires a value."
        usage
        exit 1
      fi
      SSH_USER="$2"
      shift 2
      ;;
    --user=*)
      SSH_USER="${1#--user=}"
      if [[ -z "$SSH_USER" ]]; then
        error "--user requires a value."
        usage
        exit 1
      fi
      shift
      ;;
    -q|--quiet)
      QUIET=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      if [[ -z "$CLUSTER_REQUEST" ]]; then
        CLUSTER_REQUEST="$1"
        CLUSTER_EXPLICIT=1
        shift
      elif [[ "$NODE_EXPLICIT" -eq 0 && "$NODE_POSITIONAL_CONSUMED" -eq 0 ]]; then
        NODE="$1"
        NODE_POSITIONAL_CONSUMED=1
        shift
      else
        break
      fi
      ;;
  esac
done

resolve_node_pod_name() {
  local node="$1"

  if [[ "$node" =~ ^[0-9]+$ ]]; then
    printf '%s-socat-shared-%s' "$STORE_ID" "$node"
  elif [[ "$node" =~ ^shared-[0-9]+$ ]]; then
    printf '%s-socat-%s' "$STORE_ID" "$node"
  elif [[ "$node" =~ ^socat-shared-[0-9]+$ ]]; then
    printf '%s-%s' "$STORE_ID" "$node"
  elif [[ "$node" =~ ^${STORE_ID}-socat-shared-[0-9]+$ ]]; then
    printf '%s' "$node"
  else
    error "Invalid node '${node}'. Use a shared index like 1 or a pod name like ${STORE_ID}-socat-shared-1."
    exit 1
  fi
}

# Normalise cluster code to lowercase (bare store code, not a path).
if [[ -n "$CLUSTER_REQUEST" && "$CLUSTER_REQUEST" != /* && "$CLUSTER_REQUEST" != ./* ]]; then
  CLUSTER_REQUEST=$(printf '%s' "$CLUSTER_REQUEST" | tr '[:upper:]' '[:lower:]')
fi

# --- Pre-flight checks ---
if [[ "$CLUSTER_EXPLICIT" -eq 1 ]]; then
  # Direct store code path: resolve subnet from Kubernetes, no local files needed.
  for command_name in kubectl ssh nc bash; do
    require_command "$command_name"
  done

  STORE_ID="$CLUSTER_REQUEST"

  _SUBNET_JSONPATH='{.spec.template.spec.containers[?(@.name=="socat-ssh")].env[?(@.name=="SUBNET_ID")].value}'
  SUBNET_ID=$(kubectl get statefulset "${STORE_ID}-socat-shared" \
    --context "$CONTEXT" -n "$NAMESPACE" \
    -o "jsonpath=${_SUBNET_JSONPATH}" 2>/dev/null) \
    || { error "Failed to query statefulset ${STORE_ID}-socat-shared."; exit 1; }
  [[ "$SUBNET_ID" =~ ^[0-9]+$ ]] \
    || { error "SUBNET_ID not found or invalid for ${STORE_ID}-socat-shared (got: '${SUBNET_ID}')."; exit 1; }
  B="$SUBNET_ID"
else
  # Directory-based path: requires AGENTS.md and infra-cluster.json in CWD.
  for command_name in jq kubectl ssh nc bash; do
    require_command "$command_name"
  done

  if [[ ! -f AGENTS.md ]] || ! grep -q 'store_type:' AGENTS.md 2>/dev/null; then
    error "This directory must contain an AGENTS.md with a 'store_type:' entry."
    exit 1
  fi

  if [[ ! -f infra-cluster.json ]]; then
    error "This directory must contain infra-cluster.json."
    exit 1
  fi

  STORE_ID=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')

  CIDR=$(jq -er '.network.cidr // empty' infra-cluster.json 2>/dev/null) || {
    error "Could not read .network.cidr from infra-cluster.json."
    exit 1
  }

  B=$(echo "$CIDR" | cut -d'/' -f1 | cut -d'.' -f2)
  if [[ ! "$B" =~ ^[0-9]+$ ]] || (( B < 0 || B > 255 )); then
    error "Invalid network CIDR '${CIDR}' in infra-cluster.json."
    exit 1
  fi
fi

USE_PASSWORD_FILE=0
if [[ -n "$PASSWORD_FILE" ]]; then
  if [[ -e "$PASSWORD_FILE" ]]; then
    validate_password_file "$PASSWORD_FILE"
    require_command sshpass
    USE_PASSWORD_FILE=1
  elif [[ "$PASSWORD_FILE_EXPLICIT" -eq 1 ]]; then
    error "Password file '${PASSWORD_FILE}' does not exist."
    exit 1
  fi
fi

SSH_PORT=$((40000 + B))

if [[ -z "$NODE" ]]; then
  select_responsive_node || exit 1
fi

if ! NODE_POD=$(resolve_node_pod_name "$NODE"); then
  exit 1
fi
PORT_FORWARD_TARGET="pod/${NODE_POD}"
[[ "$NODE" =~ ^[0-9]+$ ]] && SSH_PORT=$((5000 + B + NODE * 10000))

# Fail early with the real kubectl error instead of hiding it in a background process.
RESOURCE_CHECK_OUTPUT=$(kubectl get --context "$CONTEXT" -n "$NAMESPACE" "$PORT_FORWARD_TARGET" 2>&1)
if [[ $? -ne 0 ]]; then
  error "Kubernetes resource ${NAMESPACE}/${PORT_FORWARD_TARGET} is not available."
  printf '%s\n' "$RESOURCE_CHECK_OUTPUT" >&2
  exit 1
fi

# --- Check for an existing SSH port-forward process, including one created by pn.sh. ---
PORT_FORWARD_PATTERN="kubectl --context ${CONTEXT} -n ${NAMESPACE} port-forward ${PORT_FORWARD_TARGET} .*:${REMOTE_SSH_PORT}( |$)"
EXISTING_PIDS=$(pgrep -f "$PORT_FORWARD_PATTERN" 2>/dev/null || true)

if [[ -n "$EXISTING_PIDS" ]]; then
  FIRST_PID=$(echo "$EXISTING_PIDS" | head -1)
  PROCESS_ARGS=$(ps -p "$FIRST_PID" -o args= 2>/dev/null || true)

  SSH_PORT=$(extract_local_port "$PROCESS_ARGS" "$REMOTE_SSH_PORT")
  if [[ ! "$SSH_PORT" =~ ^[0-9]+$ ]]; then
    error "Found port-forward process for ${PORT_FORWARD_TARGET}, but could not determine local SSH port. PID: ${FIRST_PID}"
    exit 1
  fi

  if ! port_listening "$SSH_PORT"; then
    error "Existing port-forward PID ${FIRST_PID} for ${PORT_FORWARD_TARGET} is not responding on local SSH port ${SSH_PORT}."
    printf 'Kill stale forwards with: kill-pn-port-forwards.sh\n' >&2
    exit 1
  fi
else
  SAFE_TARGET=${PORT_FORWARD_TARGET//\//-}
  LOG_FILE="${TMPDIR:-/tmp}/prod-ssh-${STORE_ID}-${SAFE_TARGET}-port-forward.log"
  : > "$LOG_FILE"

  info "Starting SSH port-forward to ${PORT_FORWARD_TARGET} on port ${SSH_PORT}(ssh)..."
  kubectl --context ${CONTEXT} -n "$NAMESPACE" port-forward "$PORT_FORWARD_TARGET" \
    "${SSH_PORT}:${REMOTE_SSH_PORT}" >"$LOG_FILE" 2>&1 &
  PORT_FORWARD_PID=$!
  CREATED_PORT_FORWARD_PID="$PORT_FORWARD_PID"

  if ! READY_WAIT=$(wait_for_ssh_port "$SSH_PORT" "$PORT_FORWARD_PID" "$LOG_FILE"); then
    exit 1
  fi

  info "SSH port ready: 127.0.0.1:${SSH_PORT} -> ${PORT_FORWARD_TARGET}:22 (waited ${READY_WAIT}s)"
fi

SSH_DESTINATION="127.0.0.1"
if [[ -n "$SSH_USER" ]]; then
  SSH_DESTINATION="${SSH_USER}@${SSH_DESTINATION}"
fi

info "Connecting to ${SSH_DESTINATION} via local port ${SSH_PORT}"
[[ "${QUIET:-0}" -eq 1 ]] || printf '\n' >&2

# Host keys are disabled for this localhost tunnel because svc/ targets can route
# to different pods over time while kubectl already authenticates the connection.
# Use /dev/null so localhost tunnel keys are never saved to known_hosts.
SSH_COMMAND=(
  env TERM=xterm-256color
  ssh
  -p "$SSH_PORT"
  -o UserKnownHostsFile=/dev/null
  -o GlobalKnownHostsFile=/dev/null
  -o StrictHostKeyChecking=no
  -o LogLevel=ERROR
  "$SSH_DESTINATION"
)
SSH_COMMAND+=("$@")

if [[ "$USE_PASSWORD_FILE" -eq 1 ]]; then
  info "Using password file ${PASSWORD_FILE}"
  sshpass -f "$PASSWORD_FILE" "${SSH_COMMAND[@]}"
else
  "${SSH_COMMAND[@]}"
fi
SSH_EXIT_CODE=$?
exit "$SSH_EXIT_CODE"
