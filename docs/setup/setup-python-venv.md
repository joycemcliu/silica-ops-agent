---
title: "Set up the repo-local Python environment"
description: "Create or reuse .venv for repository tools and install the pinned WinRM dependency."
tags: [python, venv, uv, winrm, setup]
---

# Set up the repo-local Python environment

This guide sets up the [repository's Python environment](../../AGENTS.md#shared-python-environment) for all Python commands and tools, including development and diagnosis. Reuse `.venv` in this repository across tasks and sessions. macOS Grafana MCP forwarding uses this interpreter to detach its supervisor.

## Prerequisites

- Python 3.10+ and `uv` must be available.
- Run commands from this repository's root so the dependency and script paths resolve correctly.
- Ensure you can write to `.venv` and access the configured package source.

Local venv creation and dependency installation follow the permissions applicable to the current task; reuse existing authorization. Once authorized, using `uv` as documented here needs no separate approval.

## Setup

Create the venv if missing and install the pinned WinRM dependency. An existing usable venv is reused.

```bash
if [[ ! -f .venv/pyvenv.cfg || ! -x .venv/bin/python ]]; then
  uv venv --python python3 .venv
fi
uv pip install --python .venv/bin/python -r scripts/requirements-windows-winrm.txt
```

Keep `/.venv/` in `.gitignore` so the environment stays local to the checkout.

## Verification

Check the Python version, dependency consistency, and WinRM client startup:

```bash
.venv/bin/python --version
uv pip check --python .venv/bin/python
.venv/bin/python scripts/windows-winrm-session.py --help
```

Expect Python 3.10 or later, no dependency errors, and the WinRM client's help output. The help command does not open a remote session.

## Usage

Run Python commands and tools with this venv's explicit `bin/python` path; activation is optional.

```bash
.venv/bin/python scripts/windows-winrm-session.py --help
```

Use `uv pip` commands with `--python` pointing to this interpreter when managing dependencies. See [Windows WinRM usage](windows-winrm.md) for client instructions.

## Troubleshooting

- **Missing `uv` or Python 3.10+:** report the missing prerequisite before attempting system changes. If `python3` selects an older version, select an installed Python 3.10+ interpreter for `uv venv --python`.
- **Missing venv or interpreter:** rerun the setup steps to create the repo-local environment.
- **`ModuleNotFoundError` or WinRM import errors:** confirm the tool uses `.venv/bin/python`, then rerun the dependency installation and verification steps.
- **Missing `pip` or `ensurepip`:** `uv` manages packages directly, so their absence does not mean the venv is missing or unusable.
- **Using a different WinRM venv:** use `.venv` instead of `scripts/setup-windows-winrm.sh`, which manages the separate `winrm` venv.

## Cleanup

Keep `.venv` for future tasks and sessions. Do not remove it during routine cleanup; other repository tools may depend on it.
