---
title: "Render MCP server configuration"
description: "Generate Codex and Hermes MCP config for all diagnose agents from one shared registry."
tags: [mcp, codex, hermes, slack, grafana, setup]
---

# Render MCP server configuration

`config/mcp-servers.toml` is the single list of MCP servers every diagnose agent uses: local Codex or Hermes sessions and the Slack listener's dedicated Codex home. `scripts/render-mcp-config.py` renders it for each runtime, so server names and settings stay identical. Add or change a server in the registry, never in a runtime config copy.

The repository-hosted servers and their dependencies live under `mcp-servers/`. After updating from the previous layout, rerender the registry and replace the existing server entries in each runtime config.

## Prerequisites

- Complete [Repo-local Python environment](setup-python-venv.md) (Python 3.11+ for `tomllib`).
- Complete the setup of each server you enable, such as [Grafana MCP forwarding](grafana-mcp-forward.md), [Slack history MCP server](slack-history-mcp.md), and [Google Drive RCA MCP server](google-drive-mcp.md).

## Setup

From the repository root, render the section for the target runtime. `SLACK_HISTORY_CHANNELS` is optional; unset variables are omitted.

```bash
SLACK_HISTORY_CHANNELS=C0123456789 .venv/bin/python scripts/render-mcp-config.py codex
SLACK_HISTORY_CHANNELS=C0123456789 .venv/bin/python scripts/render-mcp-config.py hermes
```

Merge the output into the runtime's config, preserving unrelated settings, and remove obsolete `sandbox_dev_grafana` and `sandbox_prod_grafana` entries:

- **Local Codex:** the profile's `config.toml`.
- **Slack listener Codex home:** `$HOME/.local/share/slack-debug-codex/config.toml`, after copying `slack-debug-agent/deploy/codex.config.toml`.
- **Hermes:** the `mcp_servers` mapping, as in [Hermes Grafana MCP configuration](hermes-grafana-mcp.md).

The registry references the Slack token by file path (`~/.local/secrets/slack-history-token`); it never contains secrets.

## Verification

```bash
.venv/bin/python -m unittest scripts/tests/test_render_mcp_config.py
```

Then start a new agent session (Hermes: `/reload-mcp`) and confirm the same server names appear in each runtime.

## Usage

Edit `config/mcp-servers.toml` to add a server (`type = "http"` or `"stdio"`), rerun the renderer, and merge the result into every runtime.

## Troubleshooting

- **A variable is missing from `env`:** its `{env:NAME}` placeholder was unset at render time; export it and rerender.
- **Config differs between runtimes:** rerender from the registry and merge again.
