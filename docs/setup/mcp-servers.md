---
title: "Render MCP server configuration"
description: "Generate Codex and Hermes MCP config for all diagnose agents from one shared registry."
tags: [mcp, codex, hermes, slack, grafana, setup]
---

# Render MCP server configuration

`config/mcp-servers.toml` is the single list of MCP servers every diagnose agent uses: local Codex or Hermes sessions and the Slack listener's dedicated Codex home. `scripts/render-mcp-config.py` renders it for each runtime, so server names and settings stay identical. Add or change a server in the registry, never in a runtime config copy.

The repository-hosted servers and their dependencies live under `mcp-servers/`.

## Prerequisites

- Complete [Repo-local Python environment](setup-python-venv.md) (Python 3.11+ for `tomllib`).
- Install `python-dotenv` in the repo venv if the MCP server dependencies are absent.

  ```bash
  uv pip install --python .venv/bin/python python-dotenv==1.2.4
  ```

- Complete the setup of each server you enable, such as [Grafana MCP forwarding](grafana-mcp-forward.md), [Slack history MCP server](slack-history-mcp.md), and [Google Drive RCA MCP server](google-drive-mcp.md).

## Setup

Copy the templates you need from `mcp-servers/env/` to `.env.slack` or `.env.gdrive` in the same directory. Keep token values in their own secret files.

From the repository root, render the section for the target runtime. The renderer reads `.env.*` files in `mcp-servers/env/` and skips examples. If a key is repeated, the later file in lexical order wins. Exported shell variables take precedence over file values. Only variables referenced by the registry are rendered.

```bash
.venv/bin/python scripts/render-mcp-config.py codex
.venv/bin/python scripts/render-mcp-config.py hermes
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

- **A variable is missing from `env`:** set it in the matching `mcp-servers/env/.env.*` file and rerender.
- **Config differs between runtimes:** rerender from the registry and merge again.
