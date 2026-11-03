#!/usr/bin/env bash
set -euo pipefail

scripts_directory=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
exec python3 -E -s "$scripts_directory/env_ssh.py" "$@"
