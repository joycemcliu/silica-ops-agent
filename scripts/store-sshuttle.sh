#!/bin/bash

# Route a store's LAN through its production SSH socat service.
set -u

CONTEXT="gke_infra-automate-production_us-west1_default-us-west1"
NAMESPACE="stores-socat"
REMOTE_SSH_PORT=22
READINESS_RETRIES=30
SSH_USER="${PROD_SSH_USER:-silica}"
NODE="${PROD_SSH_NODE:-${PN_NODE:-}}"
STORE_REQUEST=""
PASSWORD_FILE_DEFAULT="${HOME}/.local/secrets/silica-prod-master-node-password"
PASSWORD_FILE="${PROD_SSH_PASSWORD_FILE-$PASSWORD_FILE_DEFAULT}"
PASSWORD_FILE_EXPLICIT=0
[[ -v PROD_SSH_PASSWORD_FILE ]] && PASSWORD_FILE_EXPLICIT=1
CREATED_PORT_FORWARD_PID=""
QUIET=0

error() {
  printf 'ERROR: %s\n' "$*" >&2
}

info() {
  [[ "$QUIET" -eq 1 ]] && return 0
  printf '%s\n' "$*" >&2
}

print_prefixed_file() {
  local prefix="$1"
  local file="$2"

  [[ -s "$file" ]] || return 0
  sed "s/^/${prefix}/" "$file" >&2
}

cleanup_port_forward() {
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
  local mode group_perms other_perms

  if [[ ! -f "$password_file" || ! -r "$password_file" ]]; then
    error "Password file '${password_file}' must exist and be readable."
    exit 1
  fi

  mode=$(stat -c '%a' "$password_file" 2>/dev/null) || {
    error "Could not read permissions for password file '${password_file}'."
    exit 1
  }
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

wait_for_ssh_port() {
  local local_port="$1"
  local port_forward_pid="$2"
  local log_file="$3"
  local retry=0

  while ! timeout 1 bash -c '</dev/tcp/127.0.0.1/$1' _ "$local_port" >/dev/null 2>&1; do
    retry=$((retry + 1))

    if ! kill -0 "$port_forward_pid" 2>/dev/null; then
      error "kubectl port-forward exited before SSH port ${local_port} became ready."
      print_prefixed_file "kubectl: " "$log_file"
      exit 1
    fi
    if [[ "$retry" -ge "$READINESS_RETRIES" ]]; then
      error "SSH port ${local_port} did not become ready after ${READINESS_RETRIES} seconds."
      print_prefixed_file "kubectl: " "$log_file"
      exit 1
    fi
    sleep 1
  done
}

extract_local_port() {
  local process_args="$1"
  grep -oE "[0-9]+:${REMOTE_SSH_PORT}( |$)" <<< "$process_args" | head -1 | cut -d: -f1
}

usage() {
  cat >&2 <<EOF
Usage: $(basename "$0") [STORE_CODE] [--node NODE] [--user USER] [--quiet]

Starts sshuttle to a production store LAN. STORE_CODE is case-insensitive
(hkcwbmid and HKCWBMID are equivalent) and works from any directory, without
local store files. The subnet is resolved from Kubernetes as 10.SUBNET_ID.0.0/16.
Without STORE_CODE, uses AGENTS.md and infra-cluster.json in the current store
directory. The kubectl port-forward is reused when one already exists and is
kept only for the lifetime of sshuttle when this script creates it.

Options:
  -c, --cluster, --store STORE_CODE
                            Alternative to the positional store code.
  --node NODE, --node=NODE  Port-forward to a specific shared node. NODE may
                            be an index like 1, shared-1, socat-shared-1, or the
                            full shared pod name. Legacy master forms are also
                            accepted. Can also be set with PROD_SSH_NODE or
                            PN_NODE.
  --user USER, --user=USER  SSH login user. Can also be set with PROD_SSH_USER.
                            Defaults to silica.
  -q, --quiet               Suppress wrapper status output.
  --help                    Show this help.

Environment:
  PROD_SSH_PASSWORD_FILE    Password file for sshpass. Defaults to
                            ${PASSWORD_FILE_DEFAULT}. If the default file is
                            absent, normal interactive SSH authentication is used.
                            Set to an empty string to disable password-file use.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--cluster|--store)
      if [[ $# -lt 2 || -z "$2" || "$2" == -* ]]; then
        error "$1 requires a store code."
        exit 1
      fi
      if [[ -n "$STORE_REQUEST" ]]; then
        error "Specify only one store code."
        exit 1
      fi
      STORE_REQUEST="$2"
      shift 2
      ;;
    --cluster=*|--store=*)
      if [[ -n "$STORE_REQUEST" || -z "${1#*=}" ]]; then
        error "Specify exactly one nonempty store code."
        exit 1
      fi
      STORE_REQUEST="${1#*=}"
      shift
      ;;
    --node)
      if [[ $# -lt 2 || -z "$2" ]]; then
        error "--node requires a value."
        usage
        exit 1
      fi
      NODE="$2"
      shift 2
      ;;
    --node=*)
      NODE="${1#--node=}"
      if [[ -z "$NODE" ]]; then
        error "--node requires a value."
        usage
        exit 1
      fi
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
    -*)
      error "Unknown option '${1}'."
      usage
      exit 1
      ;;
    *)
      if [[ -n "$STORE_REQUEST" || -z "$1" ]]; then
        error "Specify exactly one nonempty store code."
        exit 1
      fi
      STORE_REQUEST="$1"
      shift
      ;;
  esac
done

if [[ -n "$STORE_REQUEST" ]]; then
  STORE_REQUEST=$(printf '%s' "$STORE_REQUEST" | tr '[:upper:]' '[:lower:]')
  if [[ ! "$STORE_REQUEST" =~ ^[a-z0-9]([-a-z0-9]*[a-z0-9])?$ || ${#STORE_REQUEST} -gt 63 ]]; then
    error "Invalid store code '${STORE_REQUEST}'. Use a store code such as hkcwbmid, not a path."
    exit 1
  fi
fi

for command_name in kubectl ssh sshuttle timeout bash stat; do
  require_command "$command_name"
done

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

resolve_node_pod_name() {
  local node="$1"
  local node_index
  local shared_pod
  local legacy_pod

  if [[ "$node" =~ ^${STORE_ID}-socat-shared-([0-9]+)$ ]]; then
    printf '%s' "$node"
    return 0
  elif [[ "$node" =~ ^${STORE_ID}-socat-master-([0-9]+)$ ]]; then
    node_index="${BASH_REMATCH[1]}"
  elif [[ "$node" =~ ^([0-9]+)$ ]]; then
    node_index="${BASH_REMATCH[1]}"
  elif [[ "$node" =~ ^(shared|master)-([0-9]+)$ ]]; then
    node_index="${BASH_REMATCH[2]}"
  elif [[ "$node" =~ ^socat-(shared|master)-([0-9]+)$ ]]; then
    node_index="${BASH_REMATCH[2]}"
  else
    error "Invalid node '${node}'. Use an index like 1, shared-1, or a full shared pod name."
    return 1
  fi

  shared_pod="${STORE_ID}-socat-shared-${node_index}"
  if kubectl get pod --context "$CONTEXT" -n "$NAMESPACE" "$shared_pod" >/dev/null 2>&1; then
    printf '%s' "$shared_pod"
    return 0
  fi

  # Stores not migrated to shared protocol pods still use master-N.
  legacy_pod="${STORE_ID}-socat-master-${node_index}"
  if kubectl get pod --context "$CONTEXT" -n "$NAMESPACE" "$legacy_pod" >/dev/null 2>&1; then
    printf '%s' "$legacy_pod"
    return 0
  fi

  error "Could not find a shared SSH pod for node ${node_index} in store ${STORE_ID}."
  return 1
}

if [[ -n "$STORE_REQUEST" ]]; then
  STORE_ID="$STORE_REQUEST"
  SUBNET_JSONPATH='{.spec.template.spec.containers[?(@.name=="socat-ssh")].env[?(@.name=="SUBNET_ID")].value}'
  SUBNET_ID=$(kubectl get statefulset "${STORE_ID}-socat-shared" \
    --context "$CONTEXT" -n "$NAMESPACE" -o "jsonpath=${SUBNET_JSONPATH}") || {
    error "Failed to query statefulset ${STORE_ID}-socat-shared. Check Kubernetes access and the store code."
    exit 1
  }
  if [[ ! "$SUBNET_ID" =~ ^[0-9]{1,3}$ ]] || (( 10#$SUBNET_ID > 255 )); then
    error "SUBNET_ID is missing or invalid for ${STORE_ID}-socat-shared."
    exit 1
  fi
  CIDR="10.$((10#$SUBNET_ID)).0.0/16"
else
  if [[ ! -f AGENTS.md ]] || ! grep -q 'store_type:' AGENTS.md 2>/dev/null; then
    error "Supply a store code (e.g. store-sshuttle.sh hkcwbmid), or run from a store directory with AGENTS.md and infra-cluster.json."
    exit 1
  fi
  if [[ ! -f infra-cluster.json ]]; then
    error "This directory must contain infra-cluster.json, or supply a store code."
    exit 1
  fi
  require_command jq
  STORE_ID=$(basename "$(pwd)" | tr '[:upper:]' '[:lower:]')
  CIDR=$(jq -er '.network.cidr // empty' infra-cluster.json 2>/dev/null) || {
    error "Could not read .network.cidr from infra-cluster.json."
    exit 1
  }
fi

# The port allocation matches store-port-forward-ssh.sh, using the second octet.
B=$(cut -d/ -f1 <<< "$CIDR" | cut -d. -f2)
if [[ ! "$CIDR" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}/([0-9]|[12][0-9]|3[0-2])$ ]] ||
  [[ ! "$B" =~ ^[0-9]+$ ]] || (( B > 255 )); then
  error "Invalid network CIDR '${CIDR}' in infra-cluster.json."
  exit 1
fi
SSH_PORT=$((40000 + B))
PORT_FORWARD_TARGET="svc/${STORE_ID}-ssh"
if [[ -n "$NODE" ]]; then
  if ! NODE_POD=$(resolve_node_pod_name "$NODE"); then
    exit 1
  fi
  NODE_INDEX=${NODE_POD##*-}
  SSH_PORT=$((5000 + B + NODE_INDEX * 10000))
  PORT_FORWARD_TARGET="pod/${NODE_POD}"
fi

RESOURCE_CHECK_OUTPUT=$(kubectl get --context "$CONTEXT" -n "$NAMESPACE" "$PORT_FORWARD_TARGET" 2>&1)
if [[ $? -ne 0 ]]; then
  error "Kubernetes resource ${NAMESPACE}/${PORT_FORWARD_TARGET} is not available."
  printf '%s\n' "$RESOURCE_CHECK_OUTPUT" >&2
  exit 1
fi

PORT_FORWARD_PATTERN="kubectl --context ${CONTEXT} -n ${NAMESPACE} port-forward ${PORT_FORWARD_TARGET} .*:${REMOTE_SSH_PORT}( |$)"
EXISTING_PIDS=$(pgrep -f "$PORT_FORWARD_PATTERN" 2>/dev/null || true)

if [[ -n "$EXISTING_PIDS" ]]; then
  FIRST_PID=$(head -1 <<< "$EXISTING_PIDS")
  PROCESS_ARGS=$(ps -p "$FIRST_PID" -o args= 2>/dev/null || true)
  SSH_PORT=$(extract_local_port "$PROCESS_ARGS")

  if [[ ! "$SSH_PORT" =~ ^[0-9]+$ ]]; then
    error "Found port-forward process for ${PORT_FORWARD_TARGET}, but could not determine its local SSH port. PID: ${FIRST_PID}"
    exit 1
  fi
  if ! timeout 1 bash -c '</dev/tcp/127.0.0.1/$1' _ "$SSH_PORT" >/dev/null 2>&1; then
    error "Existing port-forward PID ${FIRST_PID} for ${PORT_FORWARD_TARGET} is not responding on local SSH port ${SSH_PORT}."
    printf 'Kill stale forwards with: kill-pn-port-forwards.sh\n' >&2
    exit 1
  fi
  info "Reusing SSH port-forward: 127.0.0.1:${SSH_PORT} -> ${PORT_FORWARD_TARGET}:22"
else
  SAFE_TARGET=${PORT_FORWARD_TARGET//\//-}
  LOG_FILE="${TMPDIR:-/tmp}/store-sshuttle-${STORE_ID}-${SAFE_TARGET}-port-forward.log"
  : > "$LOG_FILE"

  info "Starting SSH port-forward to ${PORT_FORWARD_TARGET} on port ${SSH_PORT}(ssh)..."
  kubectl --context "$CONTEXT" -n "$NAMESPACE" port-forward "$PORT_FORWARD_TARGET" \
    "${SSH_PORT}:${REMOTE_SSH_PORT}" >"$LOG_FILE" 2>&1 &
  PORT_FORWARD_PID=$!
  CREATED_PORT_FORWARD_PID="$PORT_FORWARD_PID"
  wait_for_ssh_port "$SSH_PORT" "$PORT_FORWARD_PID" "$LOG_FILE"
  info "SSH port ready: 127.0.0.1:${SSH_PORT} -> ${PORT_FORWARD_TARGET}:22"
fi

# svc targets can route to different pods, so do not persist a host key for the
# localhost endpoint; kubectl already authenticates the tunnel to Kubernetes.
printf -v SSH_COMMAND '%q ' ssh \
  -o UserKnownHostsFile=/dev/null \
  -o GlobalKnownHostsFile=/dev/null \
  -o StrictHostKeyChecking=no \
  -o LogLevel=ERROR
if [[ "$USE_PASSWORD_FILE" -eq 1 ]]; then
  printf -v SSH_COMMAND '%q ' sshpass -f "$PASSWORD_FILE" ssh \
    -o UserKnownHostsFile=/dev/null \
    -o GlobalKnownHostsFile=/dev/null \
    -o StrictHostKeyChecking=no \
    -o LogLevel=ERROR
fi

info "Forwarding store LAN: ${CIDR}"
info "Connecting sshuttle as ${SSH_USER}@127.0.0.1:${SSH_PORT}"
sshuttle --ssh-cmd "$SSH_COMMAND" --remote "${SSH_USER}@127.0.0.1:${SSH_PORT}" "$CIDR"
