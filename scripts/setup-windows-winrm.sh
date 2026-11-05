#!/usr/bin/env bash
# Install the WSL WinRM client without uv, activation, sudo, or system pip.
set -euo pipefail

if [[ "${1:-}" == "--help" && $# -eq 1 ]]; then
  echo "Usage: bash setup-windows-winrm.sh"
  echo 'Creates/reuses ${HOME}/.local/share/silica-ops-agent/venvs/winrm and installs pinned requirements.'
  exit 0
fi
if [[ $# -ne 0 ]]; then
  echo 'ERROR: No arguments supported. Use --help.' >&2
  exit 2
fi

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
WINRM_VENV="${HOME}/.local/share/silica-ops-agent/venvs/winrm"
command -v python3 >/dev/null || { echo 'ERROR: Install Python 3.10+ first.' >&2; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 10))' || {
  echo 'ERROR: Python 3.10+ is required.' >&2
  exit 1
}

if [[ ! -f "${WINRM_VENV}/pyvenv.cfg" || ! -x "${WINRM_VENV}/bin/python" ]]; then
  if ! python3 -m venv "$WINRM_VENV"; then
    echo 'ERROR: Could not create venv. On Ubuntu, install python3-venv (sudo apt-get install python3-venv), then rerun.' >&2
    exit 1
  fi
fi
if ! "${WINRM_VENV}/bin/python" -m pip --version >/dev/null 2>&1; then
  if ! "${WINRM_VENV}/bin/python" -m ensurepip --upgrade; then
    echo 'ERROR: Could not bootstrap pip. On Ubuntu, install python3-venv (sudo apt-get install python3-venv), then rerun.' >&2
    exit 1
  fi
fi
"${WINRM_VENV}/bin/python" -m pip install -r "${SCRIPT_DIR}/requirements-windows-winrm.txt"
"${WINRM_VENV}/bin/python" -m pip check
printf 'Ready. Run: "%s/bin/python" "%s/windows-winrm-session.py" --help\n' "$WINRM_VENV" "$SCRIPT_DIR"
