#!/usr/bin/env bash
# Codex `http_headers_helper`: print an Authorization header built from a token file.
# Usage: mcp-bearer-header.sh <token-file>
set -euo pipefail
[ $# -eq 1 ] && [ -s "$1" ] || { echo "usage: $0 <non-empty token file>" >&2; exit 1; }
printf '{"Authorization":"Bearer %s"}\n' "$(tr -d '\r\n' < "$1")"
