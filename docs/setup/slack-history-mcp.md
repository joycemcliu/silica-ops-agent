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
      SLACK_HISTORY_CHANNELS: C0123456789 # optional allowlist, comma-separated
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.slack_history]
command = "/ABS/PATH/silica-ops-agent/.venv/bin/python"
args = ["/ABS/PATH/silica-ops-agent/scripts/slack-history-mcp.py"]
env = { SLACK_HISTORY_TOKEN_FILE = "/ABS/PATH/.local/secrets/slack-history-token", SLACK_HISTORY_CHANNELS = "C0123456789" }
```

Store the token alone in a file outside the repository, for example `install -m 600 /dev/null ~/.local/secrets/slack-history-token`, then paste it in. Keep the token out of MCP configs. `SLACK_HISTORY_TOKEN` also works but puts the secret in config. Set `SLACK_HISTORY_CHANNELS` to limit readable channels (the escalation channel at minimum).

## Run once on a long-running host (optional)

Instead of a stdio server per machine, run it as streamable HTTP on the WSL host and point other machines at it. The Slack token then lives only on that host.

Run `scripts/bootstrap-wsl-host.sh` to do all of this in one step (needs `uv` and systemd; it stops and tells you if `~/.local/secrets/slack-history-token` is missing). Add `--harness` to also run `harness global` and `harness use`. The manual steps are:

```bash
install -m 600 /dev/null ~/.local/secrets/slack-history-mcp-http-token   # paste a long random string
mkdir -p ~/.config/systemd/user && cp scripts/slack-history-mcp.service ~/.config/systemd/user/
# set SLACK_HISTORY_CHANNELS in scripts/slack-history-mcp.env (KEY=value), then:
systemctl --user daemon-reload && systemctl --user enable --now slack-history-mcp
loginctl enable-linger "$USER"
```

The unit listens on `0.0.0.0:60010/mcp` and rejects requests without `Authorization: Bearer <http token>`; the bearer token is the only protection, so keep it secret and the port off the public internet. Plain HTTP also sends the token unencrypted, so use it only on the VPN. For loopback only, change the unit to `--host 127.0.0.1` and use `ssh -N -L 60010:127.0.0.1:60010 <wsl-host>`. WSL2 in NAT mode does not expose WSL ports to the VPN: set `networkingMode=mirrored` in `%UserProfile%\.wslconfig` (then `wsl --shutdown`) and allow TCP 60010 in Windows Firewall, or add a `netsh interface portproxy` rule on Windows. On the laptop, export `SLACK_HISTORY_MCP_TOKEN` and render `config/mcp-servers.remote.toml` with `scripts/render-mcp-config.py {codex,hermes} --registry config/mcp-servers.remote.toml`.

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
