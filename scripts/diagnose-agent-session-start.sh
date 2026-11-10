#!/usr/bin/env bash
set -Eeuo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
hook_event=''

report_to_agent() {
  local message=$1
  if [[ -n "$hook_event" ]]; then
    jq -n --arg event "$hook_event" --arg message "$message" \
      '{systemMessage: $message, hookSpecificOutput: {hookEventName: $event, additionalContext: $message}}' >&3
  else
    printf '%s\n' "$message"
  fi
}

die() {
  echo "ERROR: $*" >&2
  report_to_agent "Diagnosis startup failed: $*. Inform the user of this reason before diagnosis. For password-file failures, ask the user to configure the indicated file; never ask them to paste passwords into chat. Do not claim unavailable services are usable."
  # Codex consumes additionalContext on success; a failed check must still reach the model.
  [[ -z "$hook_event" ]] || exit 0
  exit 1
}

validate_password_file() {
  local label=$1 file=$2 mode
  [[ -f "$file" && -r "$file" ]] || die "$label password file '$file' must exist and be readable."
  if [[ "$OSTYPE" == darwin* ]]; then
    mode=$(stat -f '%Lp' "$file") || die "Could not read permissions for $label password file '$file'."
  else
    mode=$(stat -c '%a' "$file") || die "Could not read permissions for $label password file '$file'."
  fi
  [[ "$mode" =~ ^[0-7]{3,4}$ ]] || die "Unexpected permissions for $label password file '$file'."
  (( (8#$mode & 077) == 0 )) || die "$label password file '$file' must not be accessible by group or others; use chmod 600."
}

case "${1:-}" in
  -h|--help)
    echo "Usage: $0"
    echo 'Checks production SSH and Windows password files before updating repositories.'
    echo 'Updates both config.env repositories with fetch --prune, checkout master -f, and pull.'
    echo 'Discards tracked local changes, then starts both Grafana MCP forwards and checks MCP handshakes.'
    exit 0
    ;;
  '') ;;
  *) die "Unexpected argument: $1. Run with --help for usage." ;;
esac
[[ $# -eq 0 ]] || die 'No arguments expected.'

for tool in git flock stat jq curl; do
  command -v "$tool" >/dev/null || die "Missing required command: $tool"
done

# Manual runs keep normal exit codes; Codex hooks receive structured model context.
if [[ ! -t 0 ]]; then
  hook_event=$(jq -r '.hook_event_name // empty' 2>/dev/null) || hook_event=''
fi
case "$hook_event" in
  SessionStart|SubagentStart) exec 3>&1 1>&2 ;;
  *) hook_event='' ;;
esac

cd "$ROOT"
[[ -f config.env ]] || die 'Copy config.example.env to config.env and configure it before starting a session.'
# Configuration is required; inherited variables must not fill missing values.
unset SILICA_REPO SILICA_ENV_REPO
source "$ROOT/config.env"
[[ -n "${SILICA_REPO:-}" ]] || die 'Set SILICA_REPO in config.env and start a new session.'
[[ -n "${SILICA_ENV_REPO:-}" ]] || die 'Set SILICA_ENV_REPO in config.env and start a new session.'

# Both store-port-forward-ssh.sh and store-sshuttle.sh use this same file.
password_file=${PROD_SSH_PASSWORD_FILE-"${HOME}/.local/secrets/silica-prod-master-node-password"}
[[ -n "$password_file" ]] || die 'PROD_SSH_PASSWORD_FILE must not be empty for diagnose startup.'
validate_password_file SSH "$password_file"
password=''
IFS= read -r password < "$password_file" || true
[[ -n "$password" ]] || die "SSH password file '$password_file' must contain a nonempty first line."
unset password

windows_password_file=${WINRM_CREDENTIALS_FILE:-"${HOME}/.local/secrets/silica-prod-windows-password"}
validate_password_file Windows "$windows_password_file"
jq -e 'type == "object" and (.username | type == "string") and (.password | type == "string")' \
  "$windows_password_file" >/dev/null 2>&1 ||
  die "Windows password file '$windows_password_file' must contain valid JSON with username and password strings."

repos=()
for name in SILICA_REPO SILICA_ENV_REPO; do
  repo=${!name}
  repo=$(cd "$repo" && pwd -P) || die "$name is not a directory. Correct config.env and start a new session."
  top=$(git -C "$repo" rev-parse --show-toplevel) || die "$name is not a Git working tree. Correct config.env and start a new session."
  [[ "$repo" == "$top" ]] || die "$name must point to a Git repository root. Correct config.env and start a new session."
  repos+=("$repo")
done

mkdir -p "$ROOT/.tools"
exec 9>"$ROOT/.tools/session-start.lock"
flock 9

for repo in "${repos[@]}"; do
  echo "Updating $repo..."
  git -C "$repo" fetch --prune &&
    git -C "$repo" checkout master -f &&
    git -C "$repo" pull || die "Could not update $repo; session startup stopped."
done

# Background forwards must not inherit the startup lock or hook output pipe.
if output=$(bash "$ROOT/scripts/grafana-mcp-forward.sh" start 9>&- 3>&- 2>&1); then
  printf '%s\n' "$output"
else
  die "Cannot use Grafana MCP servers: forwarding startup failed. $output"
fi
if output=$(bash "$ROOT/scripts/grafana-mcp-forward.sh" status 9>&- 3>&- 2>&1); then
  printf '%s\n' "$output"
else
  die "Cannot use Grafana MCP servers: forwarding connectivity check failed. $output"
fi

check_grafana_mcp() {
  local name=$1 port=$2 response error
  # Unlike the forwarding status check, require a valid MCP initialize response.
  if response=$(curl --noproxy '*' --silent --show-error --fail --max-time 10 \
    -H "Host: localhost:$port" -H 'Content-Type: application/json' \
    -H 'Accept: application/json, text/event-stream' \
    --data '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"diagnose-startup-check","version":"1"}}}' \
    "http://127.0.0.1:$port/mcp" 2>&1); then
    # Streamable HTTP can return JSON or an SSE message containing JSON.
    response=$(printf '%s' "$response" | jq -Rrs '
      fromjson? // (split("\n") | map(select(startswith("data:")) | ltrimstr("data:") | fromjson?) | map(select(.id == 1)) | .[0])
    ') || response=''
    if [[ -n "$response" ]] && printf '%s' "$response" | jq -e '
      .jsonrpc == "2.0" and .id == 1 and .error == null and
      (.result.protocolVersion | type == "string" and length > 0) and
      (.result.capabilities.tools | type == "object")
    ' >/dev/null 2>&1; then
      echo "$name: MCP handshake succeeded."
      return 0
    fi
    error=$(printf '%s' "$response" | jq -r '.error.message // "invalid MCP initialize response or missing tools capability"' 2>/dev/null)
    response=${error:-invalid MCP initialize response}
  fi
  echo "Cannot use Grafana MCP server $name at 127.0.0.1:$port: $response" >&2
  return 1
}

failures=''
for entry in sandbox_dev_grafana:60007 sandbox_prod_grafana:60008; do
  if output=$(check_grafana_mcp "${entry%:*}" "${entry##*:}" 2>&1); then
    printf '%s\n' "$output"
  else
    failures+="$output"$'\n'
  fi
done
[[ -z "$failures" ]] || die "$failures"
report_to_agent 'Session startup complete. Both Grafana MCP endpoints passed an MCP handshake. This does not verify the agent runtime connections: check that its Grafana MCP tools are available before use. If they are unavailable, inform the user that Grafana MCP cannot be used and include the runtime connection error; do not infer availability from this endpoint check.'
