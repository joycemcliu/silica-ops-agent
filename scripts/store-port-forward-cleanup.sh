#!/bin/bash

# Kill kubectl port-forward processes created by silica-portforward-nomad.sh, silica-portforward-ssh.sh, and the Grafana troubleshooting helper.
# Examples matched:
#   kubectl port-forward -n stores-socat pod/<store_id>-socat-nomad-<node>-<hash> <nomad_port>:4646
#   kubectl port-forward -n stores-socat pod/<store_id>-socat-shared-<node> <consul_port>:8500 <https_port>:443 <pg_port>:5432
#   kubectl port-forward -n stores-socat pod/<store_id>-socat-shared-<node> <ssh_port>:22
#   kubectl -n monitoring port-forward svc/grafana-alloy <local_port>:12345
#   kubectl -n monitoring port-forward svc/grafana-mcp <local_port>:8000

usage() {
  cat <<EOF
Usage: $(basename "$0") [--store STORE_CODE] [--node NODE]

Lists existing tunnels, including tunnels to automatically selected nodes.
Without --node, discovers tunnels on all nodes; no node defaults to 1.
Press Enter to stop listed store tunnels, or select individual row IDs.
Grafana tunnels are only stopped when their IDs are explicitly selected.

  -c, --cluster, --store STORE_CODE  Limit cleanup to one store (case-insensitive).
  --node NODE                      Limit cleanup to one node ordinal.
  -h, --help                       Show this help.

Cleanup uses local process discovery and does not open tunnels or query Kubernetes.
EOF
}

STORE_FILTER=""
NODE_FILTER=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -c|--cluster|--store|--node)
      if [[ $# -lt 2 || -z "$2" ]]; then
        printf 'ERROR: %s requires a value.\n' "$1" >&2
        exit 1
      fi
      if [[ "$1" == --node ]]; then NODE_FILTER="$2"; else STORE_FILTER="$2"; fi
      shift 2
      ;;
    --node=*) NODE_FILTER="${1#*=}"; [[ -n "$NODE_FILTER" ]] || exit 1; shift ;;
    --store=*|--cluster=*) STORE_FILTER="${1#*=}"; [[ -n "$STORE_FILTER" ]] || exit 1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'ERROR: Unknown argument: %s\n' "$1" >&2; usage >&2; exit 1 ;;
  esac
done
if [[ -n "$NODE_FILTER" && ! "$NODE_FILTER" =~ ^[1-9][0-9]*$ ]]; then
  printf 'ERROR: Node must be a positive integer.\n' >&2
  exit 1
fi
if [[ -n "$STORE_FILTER" && ! "$STORE_FILTER" =~ ^[a-zA-Z0-9_-]+$ ]]; then
  printf 'ERROR: Invalid store code.\n' >&2
  exit 1
fi
STORE_FILTER=$(printf '%s' "$STORE_FILTER" | tr '[:upper:]' '[:lower:]')

cancel() {
  echo -e "\nCancelled."
  exit 130
}

trap cancel INT

read_choice() {
  local prompt="$1"
  local output_var="$2"
  local choice=""
  local char

  # In an interactive terminal, read one key at a time so ESC can cancel immediately.
  if [[ -t 0 ]]; then
    printf '%s' "$prompt"
    while IFS= read -rsn1 char; do
      case "$char" in
        $'\e')
          cancel
          ;;
        '')
          printf '\n'
          printf -v "$output_var" '%s' "$choice"
          return 0
          ;;
        $'\177'|$'\b')
          if [[ -n "$choice" ]]; then
            choice="${choice%?}"
            printf '\b \b'
          fi
          ;;
        *)
          choice+="$char"
          printf '%s' "$char"
          ;;
      esac
    done

    cancel
  fi

  if ! IFS= read -r -p "$prompt" choice; then
    cancel
  fi

  if [[ "$choice" == *$'\e'* ]]; then
    cancel
  fi

  printf -v "$output_var" '%s' "$choice"
}

PROCESS_REGEX='kubectl.*port-forward'

extract_port() {
  local cmd="$1"
  local remote_port="$2"
  local match
  match=$(grep -oE "[0-9]+:${remote_port}( |$)" <<< "$cmd" | head -1 | cut -d: -f1)
  [[ -n "$match" ]] && printf '%s' "$match" || printf '-'
}

extract_port_pairs() {
  local cmd="$1"
  local pairs
  pairs=$(grep -oE '[0-9]+:[0-9]+' <<< "$cmd" | tr '\n' ',' | sed 's/,$//')
  [[ -n "$pairs" ]] && printf '%s' "$pairs" || printf '-'
}

contains_pid() {
  local candidate=$1
  local existing

  for existing in "${TARGET_PIDS[@]}"; do
    [[ "$existing" == "$candidate" ]] && return 0
  done

  return 1
}

# macOS ships Bash 3.2, which does not provide mapfile.
declare -a ALL_PIDS=()
while IFS= read -r PID; do
  [[ -n "$PID" ]] && ALL_PIDS+=("$PID")
done < <(pgrep -f "$PROCESS_REGEX" 2>/dev/null || true)

if [[ ${#ALL_PIDS[@]} -eq 0 ]]; then
  echo "No active kubectl port-forwards found."
  exit 0
fi

declare -a PID_LIST
# Pressing Enter should only kill cluster/store forwards; Grafana forwards remain selectable by ID.
declare -a DEFAULT_PID_LIST
# Tab-separated rows so `column -t` can size each column to its widest value (pod names vary a lot in length).
declare -a TABLE_ROWS=("ID	TYPE	NODE	TARGET	NOMAD	CONSUL	HTTPS/AUX	SSH	PORTS	PID")
COUNT=0

for PID in "${ALL_PIDS[@]}"; do
  CMD=$(ps -p "$PID" -o args= 2>/dev/null || true)
  [[ -z "$CMD" ]] && continue

  FIRST_ARG=${CMD%% *}
  FIRST_BASENAME=${FIRST_ARG##*/}
  [[ "$FIRST_BASENAME" != "kubectl" ]] && continue

  TYPE=""
  TARGET=""
  NODE="-"
  NOMAD_PORT="-"
  CONSUL_PORT="-"
  HTTPS_OR_ALLOY_PORT="-"
  SSH_PORT="-"

  if [[ "$CMD" == *"stores-socat"* && "$CMD" =~ (svc|pod)/([^[:space:]]+) && ( "$CMD" == *":4646"* || "$CMD" == *":22"* || "$CMD" == *":8500"* || "$CMD" == *":443"* || "$CMD" == *":5432"* ) ]]; then
    TYPE="store"
    TARGET="${BASH_REMATCH[1]}/${BASH_REMATCH[2]}"
    NOMAD_PORT=$(extract_port "$CMD" 4646)
    CONSUL_PORT=$(extract_port "$CMD" 8500)
    HTTPS_OR_ALLOY_PORT=$(extract_port "$CMD" 443)
    SSH_PORT=$(extract_port "$CMD" 22)
  elif [[ "$CMD" == *"monitoring"* && "$CMD" == *"svc/grafana-alloy"* && "$CMD" == *":12345"* ]]; then
    TYPE="grafana-alloy"
    TARGET="monitoring/grafana-alloy"
    HTTPS_OR_ALLOY_PORT=$(extract_port "$CMD" 12345)
  elif [[ "$CMD" == *"monitoring"* && "$CMD" == *"svc/grafana-mcp"* && "$CMD" == *":8000"* ]]; then
    TYPE="grafana-mcp"
    TARGET="monitoring/grafana-mcp"
    HTTPS_OR_ALLOY_PORT=$(extract_port "$CMD" 8000)
  else
    continue
  fi

  if [[ "$TYPE" == store ]]; then
    # Probe tunnels use ephemeral local ports (:22) and are owned by their
    # probing wrapper. Only offer established, explicitly mapped forwards.
    [[ "$CMD" =~ [[:space:]][0-9]+:[0-9]+([[:space:]]|$) ]] || continue
    if [[ "$TARGET" =~ ^pod/(.+)-socat-(shared|nomad)-([0-9]+)(-|$) ]]; then
      TARGET_STORE="${BASH_REMATCH[1]}"
      NODE="${BASH_REMATCH[3]}"
      [[ -z "$STORE_FILTER" || "$TARGET_STORE" == "$STORE_FILTER" ]] || continue
      [[ -z "$NODE_FILTER" || "$NODE" == "$NODE_FILTER" ]] || continue
    elif [[ -n "$STORE_FILTER" || -n "$NODE_FILTER" ]]; then
      continue
    fi
  elif [[ -n "$STORE_FILTER" || -n "$NODE_FILTER" ]]; then
    continue
  fi

  PORTS=$(extract_port_pairs "$CMD")
  ((COUNT++))
  TABLE_ROWS+=("$(printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s' \
    "$COUNT" "$TYPE" "$NODE" "$TARGET" "$NOMAD_PORT" "$CONSUL_PORT" "$HTTPS_OR_ALLOY_PORT" "$SSH_PORT" "$PORTS" "$PID")")
  PID_LIST+=("$PID")
  if [[ "$TYPE" == "store" ]]; then
    DEFAULT_PID_LIST+=("$PID")
  fi
done

if [[ ${#PID_LIST[@]} -eq 0 ]]; then
  echo "No matching store or Grafana port-forward processes found for the requested filters."
  exit 0
fi

declare -a FORMATTED_ROWS=()
while IFS= read -r LINE; do
  FORMATTED_ROWS+=("$LINE")
done < <(printf '%s\n' "${TABLE_ROWS[@]}" | column -t -s $'\t')

BORDER=$(printf '%*s' "${#FORMATTED_ROWS[0]}" '' | tr ' ' '-')

printf "Active store / Grafana troubleshooting kubectl port-forwards:\n"
echo "$BORDER"
printf '%s\n' "${FORMATTED_ROWS[0]}"
echo "$BORDER"
printf '%s\n' "${FORMATTED_ROWS[@]:1}"
echo "$BORDER"

read_choice "Enter ID(s) to kill (comma/space separated), press Enter to kill cluster forwards only, or ESC to cancel: " CHOICE

declare -a TARGET_PIDS
DEFAULT_SELECTION=0

if [[ -z ${CHOICE//[[:space:]]/} ]]; then
  DEFAULT_SELECTION=1
  TARGET_PIDS=("${DEFAULT_PID_LIST[@]}")
else
  CHOICE=${CHOICE//,/ }
  read -ra INPUT_IDS <<< "$CHOICE"

  for ID in "${INPUT_IDS[@]}"; do
    if [[ ! "$ID" =~ ^[0-9]+$ ]]; then
      echo "Warning: Invalid ID '$ID', skipping." >&2
      continue
    fi
    if [[ ${#ID} -gt 10 ]]; then
      echo "Warning: ID '$ID' is too large, skipping." >&2
      continue
    fi
    if (( ID < 1 || ID > ${#PID_LIST[@]} )); then
      echo "Warning: ID '$ID' is out of range (1-${#PID_LIST[@]}), skipping." >&2
      continue
    fi

    PID="${PID_LIST[$((ID-1))]}"
    if ! contains_pid "$PID"; then
      TARGET_PIDS+=("$PID")
    fi
  done
fi

if [[ ${#TARGET_PIDS[@]} -eq 0 ]]; then
  if (( DEFAULT_SELECTION )); then
    echo "No cluster port-forward processes selected by default; Grafana port-forwards were left running."
    exit 0
  fi

  echo "No valid IDs selected." >&2
  exit 1
fi

echo "Killing PIDs: ${TARGET_PIDS[*]}"
for PID in "${TARGET_PIDS[@]}"; do
  if kill "$PID" 2>/dev/null; then
    echo "Killed $PID"
  else
    echo "Warning: Failed to kill $PID" >&2
  fi
done
