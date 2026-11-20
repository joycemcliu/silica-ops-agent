---
title: "Set up the Slack history MCP server"
description: "Register the read-only Slack history MCP server so local diagnosis agents can read Slack threads."
tags: [slack, mcp, hermes, codex, setup]
---

# Set up the Slack history MCP server

`scripts/slack-history-mcp.py` is a read-only stdio MCP server. It gives local Codex or Hermes sessions the Slack thread reading that the Slack listener already has. It exposes `get_thread`, `get_channel_history`, and `search_messages`, and never posts.

## Prerequisites

- Complete [Repo-local Python environment](setup-python-venv.md).
- A Slack token with read-only scopes: `channels:history`, `groups:history`, `im:history`, `users:read`, and `search:read` for search. Do not grant `chat:write`. Use a user token (`xoxp-`) to read the same channels as you; `search_messages` requires it.

## Setup

From the repository root, install the pinned dependencies:

```bash
uv pip install --python .venv/bin/python -r scripts/requirements-slack-history-mcp.txt
```

Add the server to the agent's MCP configuration, preserving existing servers. Use absolute paths. Hermes (`config.yaml`):

```yaml
mcp_servers:
  slack_history:
    command: /ABS/PATH/silica-ops-agent/.venv/bin/python
    args: [/ABS/PATH/silica-ops-agent/scripts/slack-history-mcp.py]
    env:
      SLACK_HISTORY_TOKEN_FILE: /ABS/PATH/.local/secrets/slack-history-token
      SLACK_HISTORY_CHANNELS: C0123456789   # optional allowlist, comma-separated
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.slack_history]
command = "/ABS/PATH/silica-ops-agent/.venv/bin/python"
args = ["/ABS/PATH/silica-ops-agent/scripts/slack-history-mcp.py"]
env = { SLACK_HISTORY_TOKEN_FILE = "/ABS/PATH/.local/secrets/slack-history-token", SLACK_HISTORY_CHANNELS = "C0123456789" }
```

Store the token alone in a file outside the repository, for example `install -m 600 /dev/null ~/.local/secrets/slack-history-token`, then paste it in. Keep the token out of MCP configs. `SLACK_HISTORY_TOKEN` also works but puts the secret in config. Set `SLACK_HISTORY_CHANNELS` to limit readable channels (the escalation channel at minimum).

## Verification

```bash
.venv/bin/python scripts/slack-history-mcp.py --check
.venv/bin/python -m unittest scripts/tests/test_slack_history_mcp.py
```

Expect `ok` and passing tests. Then start a new agent session (Hermes: `/reload-mcp`) and read a known thread permalink with `get_thread`.

## Usage

Agents use it as described in the [diagnosis toolkit](../diagnose_toolkit.md#slack-history).

## Troubleshooting

- **`set SLACK_HISTORY_TOKEN_FILE`:** add `SLACK_HISTORY_TOKEN_FILE` to the server's `env`, check the file exists, and reload the session.
- **`missing_scope` or `not_in_channel`:** add the missing read scope, or use a user token belonging to a member of the channel.
- **`channel is not in SLACK_HISTORY_CHANNELS`:** add the channel ID to the allowlist.
- **Tools absent:** confirm the absolute paths, that the dependencies are installed in `.venv`, and that the session's tool selection enables the server.

## Cleanup

Remove the `slack_history` entry from the agent's MCP configuration and revoke the token if no longer needed.
