---
title: "Set up the shared Python environment"
description: "Create or reuse the shared Python venv for repository tools and install the pinned WinRM dependency."
tags: [python, venv, uv, winrm, setup]
---

# Set up the shared Python environment

This guide sets up the [shared Python environment](../../AGENTS.md#shared-python-environment) for all Python commands and tools in this repository, including development and diagnosis. Reuse the venv at `${HOME}/.local/share/silica-ops-agent/venvs/diagnose` across tasks and sessions.

## Prerequisites

- Python 3.10+ and `uv` must be available.
- Run commands from this repository's root so the dependency and script paths resolve correctly.
- Ensure you can write to `${HOME}/.local/share/silica-ops-agent/venvs/diagnose` and access the configured package source.

Local venv creation and dependency installation follow the permissions applicable to the current task; reuse existing authorization. Once authorized, using `uv` as documented here needs no separate approval.

## Setup

Create the venv if missing and install the pinned WinRM dependency. An existing usable venv is reused.

```bash
SHARED_PYTHON_VENV="${HOME}/.local/share/silica-ops-agent/venvs/diagnose"
if [[ ! -f "${SHARED_PYTHON_VENV}/pyvenv.cfg" || ! -x "${SHARED_PYTHON_VENV}/bin/python" ]]; then
  uv venv --python python3 "${SHARED_PYTHON_VENV}"
fi
uv pip install --python "${SHARED_PYTHON_VENV}/bin/python" -r scripts/requirements-windows-winrm.txt
```

## Verification

Check the Python version, dependency consistency, and WinRM client startup:

```bash
SHARED_PYTHON_VENV="${HOME}/.local/share/silica-ops-agent/venvs/diagnose"
"${SHARED_PYTHON_VENV}/bin/python" --version
uv pip check --python "${SHARED_PYTHON_VENV}/bin/python"
"${SHARED_PYTHON_VENV}/bin/python" scripts/windows-winrm-session.py --help
```

Expect Python 3.10 or later, no dependency errors, and the WinRM client's help output. The help command does not open a remote session.

## Usage

Run Python commands and tools with this venv's explicit `bin/python` path; activation is optional.

```bash
"${HOME}/.local/share/silica-ops-agent/venvs/diagnose/bin/python" scripts/windows-winrm-session.py --help
```

Use `uv pip` commands with `--python` pointing to this interpreter when managing dependencies. See [Windows WinRM usage](windows-winrm.md) for client instructions.

## Troubleshooting

- **Missing `uv` or Python 3.10+:** report the missing prerequisite before attempting system changes. If `python3` selects an older version, select an installed Python 3.10+ interpreter for `uv venv --python`.
- **Missing venv or interpreter:** rerun the setup steps to create the shared environment.
- **`ModuleNotFoundError` or WinRM import errors:** confirm the tool uses the shared interpreter, then rerun the dependency installation and verification steps.
- **Missing `pip` or `ensurepip`:** `uv` manages packages directly, so their absence does not mean the venv is missing or unusable.
- **Using a different WinRM venv:** use this shared environment instead of `scripts/setup-windows-winrm.sh`, which manages the separate `winrm` venv.

## Cleanup

Keep the shared venv for future tasks and sessions. Do not remove it during routine cleanup; other repository tools may depend on it.
