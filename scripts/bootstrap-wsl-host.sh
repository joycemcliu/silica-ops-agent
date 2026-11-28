#!/usr/bin/env bash
# Prepare a long-running Linux/WSL host to serve the Slack history MCP server over HTTP.
# Idempotent: safe to re-run after `git pull`. Run from anywhere; paths resolve from this repo.
#
# Usage: scripts/bootstrap-wsl-host.sh [--harness]
#   --harness  also run `harness global` and `harness use` for this repo (needs `harness` on PATH)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SECRETS="$HOME/.local/secrets"
UNIT_DIR="$HOME/.config/systemd/user"
SERVICE=slack-history-mcp
SERVICE_DIR="$REPO/mcp-servers/$SERVICE"
PORT=60010

log() { echo "bootstrap: $*"; }
die() { echo "bootstrap: $*" >&2; exit 1; }

command -v uv >/dev/null || die "uv is required (https://docs.astral.sh/uv/)"
command -v systemctl >/dev/null || die "systemd is required; enable it in /etc/wsl.conf ([boot] systemd=true) and restart WSL"

PY="$REPO/.venv/bin/python"
[ -x "$PY" ] || uv venv "$REPO/.venv"
uv pip install --python "$PY" -r "$SERVICE_DIR/requirements.txt"

mkdir -p "$SECRETS"
chmod 700 "$SECRETS"
HTTP_TOKEN="$SECRETS/slack-history-mcp-http-token"
if [ ! -s "$HTTP_TOKEN" ]; then
  (umask 077 && "$PY" -c "import secrets; print(secrets.token_urlsafe(32))" > "$HTTP_TOKEN")
  log "generated $HTTP_TOKEN; copy it to clients as SLACK_HISTORY_MCP_TOKEN"
fi
[ -s "$SECRETS/slack-history-token" ] || die "put the read-scoped Slack token in $SECRETS/slack-history-token (chmod 600), then re-run"

# The unit assumes ~/silica-ops-agent; rewrite it for wherever this repo actually lives.
mkdir -p "$UNIT_DIR"
sed "s|%h/silica-ops-agent|$REPO|g" "$SERVICE_DIR/$SERVICE.service" > "$UNIT_DIR/$SERVICE.service"
if [[ ! -f "$SERVICE_DIR/.env" && ! -f "$REPO/scripts/$SERVICE.env" ]]; then
  log "optional: copy mcp-servers/$SERVICE/.env.example to .env in the same directory and set SLACK_HISTORY_CHANNELS, then restart the service"
fi

systemctl --user daemon-reload
systemctl --user enable "$SERVICE"
systemctl --user restart "$SERVICE"
loginctl enable-linger "$USER" || log "could not enable linger; the service stops when you log out"

for _ in 1 2 3 4 5 6 7 8 9 10; do
  code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:$PORT/mcp" || true)"
  [ "$code" = 401 ] && break
  sleep 1
done
[ "$code" = 401 ] || die "service not answering on :$PORT (got '$code'); see: journalctl --user -u $SERVICE"
log "$SERVICE is up on 127.0.0.1:$PORT (unauthenticated request correctly rejected)"

if [ "${1:-}" = --harness ]; then
  command -v harness >/dev/null || die "harness not on PATH"
  harness global
  (cd "$REPO" && harness use)
fi

log "laptop URL: http://<wsl-tailnet-name>:$PORT/mcp (install Tailscale in WSL and on the laptop; see docs/setup/slack-history-mcp.md)"
