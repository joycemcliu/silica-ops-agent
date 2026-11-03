#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
ENV_ROOT="${SILICA_ENVIRONMENTS_ROOT:-}"
NS="${STORES_SOCAT_NAMESPACE:-stores-socat}"
KUBECTL_BIN="${KUBECTL:-kubectl}"
GKE_PROJECT="${STORES_SOCAT_GKE_PROJECT:-infra-automate-production}"
GKE_LOCATION="${STORES_SOCAT_GKE_LOCATION:-us-west1}"
GKE_CLUSTER="${STORES_SOCAT_GKE_CLUSTER:-default-us-west1}"
KUBECTL_CONTEXT="${STORES_SOCAT_KUBECTL_CONTEXT:-gke_${GKE_PROJECT}_${GKE_LOCATION}_${GKE_CLUSTER}}"
SKIP_GKE_CONTEXT="${SKIP_GKE_CONTEXT:-0}"

usage() {
  cat <<EOF
Usage:
  $(basename "$0") --cluster <STORE_CODE|path> [--node <N>]
  $(basename "$0") <STORE_CODE> [NODE]
  $(basename "$0")                               # when run from inside silica-environments/<STORE>

Starts persistent background kubectl port-forwards for the per-node
"<store>-socat-nomad-<node>-<hash>" pod (Nomad:4646) and the
"<store>-socat-shared-<node>" pod (Consul:8500, HTTPS:443, Postgres:5432),
then prints the local addresses. The forwards remain after this script exits.
To review and stop forwards, run:
  ${SCRIPT_DIR}/store-port-forward-cleanup.sh

Options:
  -c, --cluster, --store  Store code or cluster directory path.
  --node <N>              Node ordinal to target. If omitted, probe nodes 1-3
                          in parallel and use the fastest SSH greeting (3s timeout).
                          NOMAD_NODE also overrides automatic selection.
  --env-root <path>       silica-environments root. Default: ${ENV_ROOT}
  -h, --help              Show this help.

macOS:
  brew install kubectl jq
  brew install --cask google-cloud-sdk

Environment overrides:
  SILICA_ENVIRONMENTS_ROOT, NOMAD_CLUSTER, STORE_CODE, NOMAD_NODE, STORES_SOCAT_NAMESPACE,
  STORES_SOCAT_GKE_PROJECT, STORES_SOCAT_GKE_LOCATION, STORES_SOCAT_GKE_CLUSTER,
  STORES_SOCAT_KUBECTL_CONTEXT, SKIP_GKE_CONTEXT,
  NOMAD_LOCAL_PORT, CONSUL_LOCAL_PORT, HTTPS_LOCAL_PORT, POSTGRES_LOCAL_PORT, KUBECTL.
EOF
}

die() {
  echo "ERROR: $*" >&2
  exit 1
}

warn() {
  echo "WARNING: $*" >&2
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || die "Required command not found: $1"
}

gke_location_flag() {
  [[ "$1" =~ -[a-z]$ ]] && printf -- '--zone' || printf -- '--region'
}

ensure_kubectl_context() {
  if [[ "$SKIP_GKE_CONTEXT" != "1" && "$SKIP_GKE_CONTEXT" != "true" ]]; then
    need_cmd gcloud
    gcloud container clusters get-credentials "$GKE_CLUSTER" \
      --project="$GKE_PROJECT" \
      "$(gke_location_flag "$GKE_LOCATION")=$GKE_LOCATION" >/dev/null
  fi
}

port_listening() {
  local port=$1
  nc -z -w 1 127.0.0.1 "$port" >/dev/null 2>&1
}

canonical_dir() {
  local dir=$1
  [[ -d "$dir" ]] || return 1
  (cd "$dir" && pwd -P)
}

parse_tf_string() {
  local key=$1
  local file=$2
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*" key "[[:space:]]*=" {
      if (match($0, /"[^"]+"/)) {
        print substr($0, RSTART + 1, RLENGTH - 2)
        exit
      }
    }
  ' "$file"
}

resolve_cluster_dir() {
  local requested=$1
  local env_root_real cwd_real rel first candidate upper

  cwd_real=$(pwd -P)
  if [[ -z "$requested" && -f "${cwd_real}/infra-cluster.json" ]]; then
    canonical_dir "$cwd_real"
    return
  fi

  env_root_real=$(canonical_dir "$ENV_ROOT") || die "silica-environments root not found: $ENV_ROOT"

  if [[ -n "$requested" ]]; then
    if [[ -d "$requested" ]]; then
      canonical_dir "$requested"
      return
    fi

    candidate="${env_root_real}/${requested}"
    if [[ -d "$candidate" ]]; then
      canonical_dir "$candidate"
      return
    fi

    upper=$(printf '%s' "$requested" | tr '[:lower:]' '[:upper:]')
    candidate="${env_root_real}/${upper}"
    if [[ -d "$candidate" ]]; then
      canonical_dir "$candidate"
      return
    fi

    die "Cluster directory not found for '$requested' under $env_root_real"
  fi

  if [[ "$cwd_real" == "$env_root_real"/* ]]; then
    rel=${cwd_real#"$env_root_real"/}
    first=${rel%%/*}
    candidate="${env_root_real}/${first}"
    if [[ -f "${candidate}/infra-cluster.json" ]]; then
      canonical_dir "$candidate"
      return
    fi
  fi

  die "No cluster selected. Pass --cluster <STORE_CODE> or run from inside silica-environments/<STORE>."
}

extract_forwarded_port() {
  local cmd=$1
  local remote_port=$2
  grep -Eo "[0-9]+:${remote_port}" <<<"$cmd" | head -1 | cut -d: -f1 || true
}

# Looks up the running pod (or bare replicaset/statefulset name for pods with a
# random hash suffix) whose port-forward command line references a given
# remote port, so an already-running forward can be reused.
find_existing_pod_port_forward_pid() {
  local pod_name=$1
  local remote_port=$2
  local line pid cmd

  while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ -n "$line" ]] || continue
    pid=${line%% *}
    cmd=${line#* }

    [[ "$cmd" == *"port-forward"* ]] || continue
    [[ "$cmd" == *"--context ${KUBECTL_CONTEXT}"* || "$cmd" == *"--context=${KUBECTL_CONTEXT}"* ]] || continue
    [[ "$cmd" == *"pod/${pod_name}"* ]] || continue
    [[ "$cmd" == *":${remote_port}"* ]] || continue
    [[ "$cmd" == *" -n ${NS} "* || "$cmd" == *" --namespace ${NS} "* || "$cmd" == *" --namespace=${NS} "* ]] || continue

    printf '%s\n' "$pid"
    return 0
  done < <(ps -axww -o pid= -o command= 2>/dev/null || true)

  return 1
}

resolve_nomad_pod() {
  local prefix="${STORE_DOMAIN}-socat-nomad-${NODE}-"
  local pod
  pod=$("$KUBECTL_BIN" --context "$KUBECTL_CONTEXT" -n "$NS" get pods -o name 2>/dev/null \
    | sed -n "s#^pod/\\(${prefix}[^/]*\\)\$#\\1#p" | head -1)
  [[ -n "$pod" ]] || die "No pod found matching ${prefix}* in namespace ${NS}"
  printf '%s\n' "$pod"
}

resolve_shared_pod() {
  local pod="${STORE_DOMAIN}-socat-shared-${NODE}"
  "$KUBECTL_BIN" --context "$KUBECTL_CONTEXT" -n "$NS" get pod "$pod" >/dev/null 2>&1 \
    || die "Pod ${pod} not found in namespace ${NS}"
  printf '%s\n' "$pod"
}

wait_for_port() {
  local port=$1
  local pid=${2:-}
  local retries=30
  local i

  for ((i = 0; i < retries; i++)); do
    if nc -z -w 1 127.0.0.1 "$port" >/dev/null 2>&1; then
      printf '%s\n' "$i"
      return 0
    fi

    if [[ -n "$pid" ]] && ! kill -0 "$pid" 2>/dev/null; then
      return 2
    fi

    sleep 1
  done

  return 1
}

PROBE_DIR=""
PROBE_PIDS=()
cleanup_node_probes() {
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
}
trap cleanup_node_probes EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
trap 'exit 129' HUP

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
  local pod="${STORE_DOMAIN}-socat-shared-${node}"
  local log_file="${PROBE_DIR}/${node}.log"
  local timing_file="${PROBE_DIR}/${node}.time"
  local probe_pid="" local_port="" retry latency
  local TIMEFORMAT='%R' LC_ALL=C

  # Each worker owns its tunnel, including when interrupted by parent cleanup.
  trap 'if [[ -n "$probe_pid" ]]; then kill "$probe_pid" 2>/dev/null || true; wait "$probe_pid" 2>/dev/null || true; fi' EXIT
  trap 'exit 130' INT
  trap 'exit 143' TERM
  trap 'exit 129' HUP

  # Nomad and shared forwards must both exist for the selected ordinal.
  if ! NODE="$node" resolve_nomad_pod >/dev/null; then
    printf 'Node %s: no Nomad proxy pod available\n' "$node" >&2
    return 1
  fi

  # Ephemeral local ports avoid collisions with existing forwards and invocations.
  "$KUBECTL_BIN" --context "$KUBECTL_CONTEXT" -n "$NS" port-forward \
    --address 127.0.0.1 "pod/${pod}" ":22" >"$log_file" 2>&1 &
  probe_pid=$!

  for ((retry = 0; retry < 30; retry++)); do
    kill -0 "$probe_pid" 2>/dev/null || break
    local_port=$(sed -n 's/^Forwarding from 127\.0\.0\.1:\([0-9][0-9]*\) ->.*/\1/p' "$log_file")
    [[ -n "$local_port" ]] && break
    sleep 1
  done

  if [[ -n "$local_port" ]] && { time ssh_banner_ready "$local_port"; } 2>"$timing_file"; then
    latency=$(cat "$timing_file")
    printf '%s %s\n' "$latency" "$node" >"${PROBE_DIR}/${node}.result"
    printf '%s\n' >&2 "Node ${node}: SSH response in ${latency}s"
  else
    printf '%s\n' >&2 "Node ${node}: SSH unavailable or greeting timed out"
  fi
)

select_responsive_node() {
  local node probe_pid fastest_latency
  need_cmd mktemp
  need_cmd sort
  PROBE_DIR=$(mktemp -d "${TMPDIR:-/tmp}/store-port-forward-probes.XXXXXX") || {
    warn "Could not create temporary directory for node probes."
    return 1
  }

  printf '%s\n' >&2 "Checking SSH responsiveness of nodes 1-3..."
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
    warn "No node among 1-3 returned an SSH greeting. Specify --node to target a node directly."
    return 1
  fi
  printf '%s\n' >&2 "Selected node ${NODE} (SSH response ${fastest_latency}s)."
  rm -rf -- "$PROBE_DIR"
  PROBE_DIR=""
}

CLUSTER_REQUEST="${NOMAD_CLUSTER:-${STORE_CODE:-}}"
NODE="${NOMAD_NODE:-}"
CLUSTER_EXPLICIT=0
while (($#)); do
  case "$1" in
    -c|--cluster|--store)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      CLUSTER_REQUEST=$2
      CLUSTER_EXPLICIT=1
      shift 2
      ;;
    --node)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      [[ -n "$2" ]] || die "--node requires a value"
      NODE=$2
      shift 2
      ;;
    --node=*)
      NODE=${1#*=}
      [[ -n "$NODE" ]] || die "--node requires a value"
      shift
      ;;
    --env-root)
      [[ $# -ge 2 ]] || die "$1 requires a value"
      ENV_ROOT=$2
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      break
      ;;
    *)
      if [[ -z "$CLUSTER_REQUEST" && -d "${ENV_ROOT}/${1}" && -f "${ENV_ROOT}/${1}/infra-cluster.json" ]]; then
        CLUSTER_REQUEST=$1
        shift
      elif [[ -z "$CLUSTER_REQUEST" && ( -z "$ENV_ROOT" || ! -d "$ENV_ROOT" ) && "$1" != -* ]]; then
        # No silica-environments root available — treat positional arg as a direct store code
        CLUSTER_REQUEST=$1
        CLUSTER_EXPLICIT=1
        shift
      elif [[ "$1" != -* ]]; then
        # Second positional arg is the node ordinal
        NODE=$1
        shift
      else
        break
      fi
      ;;
  esac
done

if [[ -n "$NODE" ]]; then
  [[ "$NODE" =~ ^[0-9]+$ && "$NODE" =~ [1-9] ]] || die "Node must be a positive integer, got: $NODE"
fi

# Normalise store code to lower case unless it looks like a filesystem path.
if [[ -n "$CLUSTER_REQUEST" && "$CLUSTER_REQUEST" != /* && "$CLUSTER_REQUEST" != ./* && ! -d "$CLUSTER_REQUEST" ]]; then
  CLUSTER_REQUEST=$(printf '%s' "$CLUSTER_REQUEST" | tr '[:upper:]' '[:lower:]')
fi

need_cmd nc
need_cmd "$KUBECTL_BIN"
ensure_kubectl_context

CLUSTER_DIR=""

if [[ "$CLUSTER_EXPLICIT" -eq 1 && "$CLUSTER_REQUEST" != /* && "$CLUSTER_REQUEST" != ./* ]]; then
  # --- Direct store code path: no silica-environments required ---
  STORE_DOMAIN=$(printf '%s' "$CLUSTER_REQUEST" | tr '[:upper:]' '[:lower:]')
  STORE_CODE_PARSED=$(printf '%s' "$CLUSTER_REQUEST" | tr '[:lower:]' '[:upper:]')

  _SUBNET_JSONPATH='{.spec.template.spec.containers[?(@.name=="socat-consul")].env[?(@.name=="SUBNET_ID")].value}'
  SUBNET_ID=$("$KUBECTL_BIN" --context "$KUBECTL_CONTEXT" -n "$NS" \
    get statefulset "${STORE_DOMAIN}-socat-shared" \
    -o "jsonpath=${_SUBNET_JSONPATH}" 2>/dev/null) \
    || die "Failed to query statefulset ${STORE_DOMAIN}-socat-shared. Check kubectl context and namespace."
  [[ "$SUBNET_ID" =~ ^[0-9]+$ ]] \
    || die "SUBNET_ID not found or invalid for ${STORE_DOMAIN}-socat-shared (got: '${SUBNET_ID}')."
  SECOND_OCTET="$SUBNET_ID"
else
  # --- Directory-based path: requires silica-environments or cwd store directory ---
  need_cmd jq
  CLUSTER_DIR=$(resolve_cluster_dir "$CLUSTER_REQUEST")
  [[ -f "${CLUSTER_DIR}/infra-cluster.json" ]] || die "Missing ${CLUSTER_DIR}/infra-cluster.json"
  [[ -f "${CLUSTER_DIR}/store.tf" ]] || die "Missing ${CLUSTER_DIR}/store.tf"
  [[ -f "${CLUSTER_DIR}/AGENTS.md" ]] || die "Missing ${CLUSTER_DIR}/AGENTS.md"

  STORE_CODE_PARSED=$(parse_tf_string code "${CLUSTER_DIR}/store.tf" || true)
  STORE_CODE_PARSED=${STORE_CODE_PARSED:-$(basename "$CLUSTER_DIR")}
  STORE_DOMAIN=$(parse_tf_string domain "${CLUSTER_DIR}/store.tf" || true)
  STORE_DOMAIN=${STORE_DOMAIN:-$(printf '%s' "$STORE_CODE_PARSED" | tr '[:upper:]' '[:lower:]')}

  if ! grep -q 'store_type:' "${CLUSTER_DIR}/AGENTS.md" 2>/dev/null; then
    warn "${CLUSTER_DIR}/AGENTS.md has no store_type entry; this helper still uses the production stores-socat proxy."
  fi

  CIDR=$(jq -er '.network.cidr' "${CLUSTER_DIR}/infra-cluster.json") || die "Could not read .network.cidr from ${CLUSTER_DIR}/infra-cluster.json"
  SECOND_OCTET=$(awk -F'[./]' '{print $2}' <<<"$CIDR")
  [[ "$SECOND_OCTET" =~ ^[0-9]+$ ]] || die "Could not derive second octet from CIDR: $CIDR"
fi

LOCAL_PORT="${NOMAD_LOCAL_PORT:-$((10000 + SECOND_OCTET))}"
CONSUL_PORT="${CONSUL_LOCAL_PORT:-$((20000 + SECOND_OCTET))}"
HTTPS_PORT="${HTTPS_LOCAL_PORT:-$((30000 + SECOND_OCTET))}"
PG_PORT="${POSTGRES_LOCAL_PORT:-$((40000 + SECOND_OCTET))}"

if [[ -z "$NODE" ]]; then
  select_responsive_node || exit 1
fi

NOMAD_POD=$(resolve_nomad_pod)
SHARED_POD=$(resolve_shared_pod)

LOG_DIR="${XDG_RUNTIME_DIR:-/tmp}/prod-nomad-port-forwards"
mkdir -p "$LOG_DIR"

get_nomad_local_ports() {
  local existing_pid existing_cmd found
  existing_pid=$(find_existing_pod_port_forward_pid "$NOMAD_POD" 4646 || true)
  [[ -n "$existing_pid" ]] || return 1
  existing_cmd=$(ps -p "$existing_pid" -o args= 2>/dev/null || true)
  found=$(extract_forwarded_port "$existing_cmd" 4646)
  [[ "$found" =~ ^[0-9]+$ ]] || die "Found port-forward process ${existing_pid} for pod/${NOMAD_POD}, but could not determine the local Nomad port."
  LOCAL_PORT=$found
}

get_shared_local_ports() {
  local existing_pid existing_cmd found
  existing_pid=$(find_existing_pod_port_forward_pid "$SHARED_POD" 8500 || true)
  [[ -n "$existing_pid" ]] || return 1
  existing_cmd=$(ps -p "$existing_pid" -o args= 2>/dev/null || true)

  found=$(extract_forwarded_port "$existing_cmd" 8500)
  [[ "$found" =~ ^[0-9]+$ ]] && CONSUL_PORT=$found || warn "Existing port-forward has no Consul mapping; CONSUL_ADDR may not be reachable."
  found=$(extract_forwarded_port "$existing_cmd" 443)
  [[ "$found" =~ ^[0-9]+$ ]] && HTTPS_PORT=$found || warn "Existing port-forward has no HTTPS mapping; HTTPS_ADDR may not be reachable."
  found=$(extract_forwarded_port "$existing_cmd" 5432)
  [[ "$found" =~ ^[0-9]+$ ]] && PG_PORT=$found || warn "Existing port-forward has no PostgreSQL mapping; PGADDR may not be reachable."
}

if ! get_nomad_local_ports; then
  LOG_FILE="${LOG_DIR}/${NOMAD_POD}-${LOCAL_PORT}.log"
  if port_listening "$LOCAL_PORT"; then
    die "Local port ${LOCAL_PORT} is already in use, but not by a matching ${KUBECTL_CONTEXT} pod/${NOMAD_POD} port-forward. Stop stale forwards or set NOMAD_LOCAL_PORT."
  fi

  echo "Starting port-forward for pod/${NOMAD_POD} via ${KUBECTL_CONTEXT} on Nomad:${LOCAL_PORT}..." >&2
  "$KUBECTL_BIN" --context "$KUBECTL_CONTEXT" -n "$NS" port-forward "pod/${NOMAD_POD}" \
    "${LOCAL_PORT}:4646" >"$LOG_FILE" 2>&1 &
  PF_PID=$!
  disown "$PF_PID" 2>/dev/null || true

  if WAITED=$(wait_for_port "$LOCAL_PORT" "$PF_PID"); then
    echo "Nomad port ready after ${WAITED}s." >&2
  else
    STATUS=$?
    echo "ERROR: Nomad port ${LOCAL_PORT} did not become ready." >&2
    [[ $STATUS -eq 2 ]] && echo "kubectl port-forward exited early." >&2
    echo "kubectl log: ${LOG_FILE}" >&2
    [[ -s "$LOG_FILE" ]] && tail -20 "$LOG_FILE" >&2
    exit 1
  fi
fi

if ! get_shared_local_ports; then
  LOG_FILE="${LOG_DIR}/${SHARED_POD}-${CONSUL_PORT}.log"
  if port_listening "$CONSUL_PORT" || port_listening "$HTTPS_PORT" || port_listening "$PG_PORT"; then
    die "One or more requested local ports are already in use, but not by a matching ${KUBECTL_CONTEXT} pod/${SHARED_POD} port-forward. Stop stale forwards or set CONSUL_LOCAL_PORT/HTTPS_LOCAL_PORT/POSTGRES_LOCAL_PORT."
  fi

  echo "Starting port-forward for pod/${SHARED_POD} via ${KUBECTL_CONTEXT} on Consul:${CONSUL_PORT}, HTTPS:${HTTPS_PORT}, PG:${PG_PORT}..." >&2
  "$KUBECTL_BIN" --context "$KUBECTL_CONTEXT" -n "$NS" port-forward "pod/${SHARED_POD}" \
    "${CONSUL_PORT}:8500" \
    "${HTTPS_PORT}:443" \
    "${PG_PORT}:5432" >"$LOG_FILE" 2>&1 &
  PF_PID=$!
  disown "$PF_PID" 2>/dev/null || true

  if WAITED=$(wait_for_port "$CONSUL_PORT" "$PF_PID"); then
    echo "Shared ports ready after ${WAITED}s." >&2
  else
    STATUS=$?
    echo "ERROR: Consul port ${CONSUL_PORT} did not become ready." >&2
    [[ $STATUS -eq 2 ]] && echo "kubectl port-forward exited early." >&2
    echo "kubectl log: ${LOG_FILE}" >&2
    [[ -s "$LOG_FILE" ]] && tail -20 "$LOG_FILE" >&2
    exit 1
  fi
fi

echo "Cluster: ${STORE_CODE_PARSED}${CLUSTER_DIR:+ (${CLUSTER_DIR})}" >&2
echo "Kubernetes context: ${KUBECTL_CONTEXT}" >&2
echo "Nomad pod: ${NOMAD_POD}" >&2
echo "Shared pod: ${SHARED_POD}" >&2
echo "NOMAD_ADDR=http://127.0.0.1:${LOCAL_PORT}" >&2
echo "CONSUL_ADDR=http://127.0.0.1:${CONSUL_PORT}" >&2
echo "HTTPS_ADDR=https://127.0.0.1:${HTTPS_PORT}/home/web" >&2
echo "PGADDR=postgresql://127.0.0.1:${PG_PORT}" >&2
