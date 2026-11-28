#!/usr/bin/env bash
# Prepare a long-running Linux/WSL host to serve Slack History and Google Drive RCA MCP over HTTP.
# Idempotent: safe to re-run after `git pull`. Run from anywhere; paths resolve from this repo.
#
# Usage: scripts/bootstrap-wsl-host.sh [--harness]
#   --harness  also run `harness global` and `harness use` for this repo (needs `harness` on PATH)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS="$HOME/.local/secrets"
UNIT_DIR="$HOME/.config/systemd/user"
SLACK_SERVICE=slack-history-mcp
GOOGLE_DRIVE_SERVICE=google-drive-mcp
SLACK_PORT=60010
GOOGLE_DRIVE_PORT=60011

log() { echo "bootstrap: $*"; }
die() { echo "bootstrap: $*" >&2; exit 1; }

ensure_http_token() {
  local token_file=$1
  if [[ ! -e "$token_file" && ! -L "$token_file" ]]; then
    (umask 077 && mkdir -p "$(dirname "$token_file")" && set -o noclobber &&
      "$PY" -c "import secrets; print(secrets.token_urlsafe(32))" > "$token_file")
    log "generated $token_file"
  fi
  [[ -f "$token_file" && -s "$token_file" ]] || die "expected a nonempty HTTP token file at $token_file"
  chmod 600 "$token_file"
}

check_http() {
  local service=$1 port=$2 code
  for _ in {1..10}; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$port/mcp" || true)"
    [[ "$code" == 401 ]] && break
    sleep 1
  done
  [[ "$code" == 401 ]] || die "$service not answering on :$port (got '$code'); see: journalctl --user -u $service"
  log "$service is up on 127.0.0.1:$port (unauthenticated request correctly rejected)"
}

command -v uv >/dev/null || die "uv is required (https://docs.astral.sh/uv/)"
command -v systemctl >/dev/null || die "systemd is required; enable it in /etc/wsl.conf ([boot] systemd=true) and restart WSL"

PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || uv venv "$REPO/.venv"
uv pip install --python "$PY" \
  -r "$REPO/mcp-servers/$SLACK_SERVICE/requirements.txt" \
  -r "$REPO/mcp-servers/$GOOGLE_DRIVE_SERVICE/requirements.txt"

mkdir -p "$SECRETS"
chmod 700 "$SECRETS"
SLACK_HTTP_TOKEN="$SECRETS/slack-history-mcp-http-token"
GOOGLE_DRIVE_HTTP_TOKEN="$("$PY" - "$REPO" "$SECRETS/google-drive-rca-mcp-http-token" <<'PYTHON'
from pathlib import Path
import sys

from dotenv import dotenv_values

repo = Path(sys.argv[1])
settings = dotenv_values(repo / "mcp-servers/env/.env.gdrive", interpolate=False)
configured = settings.get("RCA_MCP_HTTP_TOKEN_FILE", sys.argv[2])
if not configured:
    sys.exit("Remove the empty RCA_MCP_HTTP_TOKEN_FILE override or set it to a token file path.")
if configured == "/absolute/path/to/google-drive-rca-mcp-http-token":
    sys.exit("Replace the RCA_MCP_HTTP_TOKEN_FILE example path in mcp-servers/env/.env.gdrive or remove the line to use the default token path.")
print(repo / Path(configured).expanduser())
PYTHON
)"
ensure_http_token "$SLACK_HTTP_TOKEN"
ensure_http_token "$GOOGLE_DRIVE_HTTP_TOKEN"
[ -s "$SECRETS/slack-history-token" ] || die "put the read-scoped Slack token in $SECRETS/slack-history-token (chmod 600), then re-run"

# The unit assumes ~/silica-ops-agent; rewrite it for wherever this repo actually lives.
mkdir -p "$UNIT_DIR"
for service in "$SLACK_SERVICE" "$GOOGLE_DRIVE_SERVICE"; do
  sed "s|%h/silica-ops-agent|$REPO|g" "$REPO/mcp-servers/$service/$service.service" > "$UNIT_DIR/$service.service"
done
if [[ ! -f "$REPO/mcp-servers/env/.env.slack" && ! -f "$REPO/mcp-servers/$SLACK_SERVICE/.env" ]]; then
  log "optional: copy mcp-servers/env/.env.slack.example to mcp-servers/env/.env.slack, replace the sample SLACK_HISTORY_CHANNELS value with your channel IDs, then restart the service"
fi

systemctl --user daemon-reload
systemctl --user enable "$SLACK_SERVICE" "$GOOGLE_DRIVE_SERVICE"
systemctl --user restart "$SLACK_SERVICE" "$GOOGLE_DRIVE_SERVICE"
loginctl enable-linger "$USER" || log "could not enable linger; the services stop when you log out"

check_http "$SLACK_SERVICE" "$SLACK_PORT"
check_http "$GOOGLE_DRIVE_SERVICE" "$GOOGLE_DRIVE_PORT"

if [ "${1:-}" = --harness ]; then
  command -v harness >/dev/null || die "harness not on PATH"
  harness global
  (cd "$REPO" && harness use)
fi

log "Slack History client: http://<wsl-tailnet-name>:$SLACK_PORT/mcp"
log "Google Drive RCA client: forward port $GOOGLE_DRIVE_PORT over SSH and use http://127.0.0.1:$GOOGLE_DRIVE_PORT/mcp"
log "copy $SLACK_HTTP_TOKEN to ~/.local/secrets/slack-history-mcp-http-token on the client (Hermes: SLACK_HISTORY_MCP_TOKEN)"
log "copy $GOOGLE_DRIVE_HTTP_TOKEN to ~/.local/secrets/google-drive-rca-mcp-http-token on the client (Hermes: GOOGLE_DRIVE_RCA_MCP_TOKEN)"
