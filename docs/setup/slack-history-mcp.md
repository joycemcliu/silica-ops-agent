---
title: "Set up the Slack history MCP server"
description: "Register the read-only Slack history MCP server so local diagnosis agents can read Slack threads."
tags: [slack, mcp, hermes, codex, setup]
---

# Set up the Slack history MCP server

`mcp-servers/slack-history-mcp/slack-history-mcp.py` is a read-only stdio MCP server. It gives local Codex or Hermes sessions the Slack thread reading that the Slack listener already has. It exposes `get_thread`, `get_channel_history`, and `search_messages`, and never posts.

## Prerequisites

- Complete [Repo-local Python environment](setup-python-venv.md).
- A Slack token with read-only scopes: `channels:history`, `groups:history`, `im:history`, `users:read`, and `search:read` for search. Do not grant `chat:write`. Use a user token (`xoxp-`) to read the same channels as you; `search_messages` requires it.

## Setup

From the repository root, install the pinned dependencies:

```bash
uv pip install --python .venv/bin/python -r mcp-servers/slack-history-mcp/requirements.txt
```

Add the server to the agent's MCP configuration, preserving existing servers. Use absolute paths. Hermes (`config.yaml`):

```yaml
mcp_servers:
  slack_history:
    command: /ABS/PATH/silica-ops-agent/.venv/bin/python
    args: [/ABS/PATH/silica-ops-agent/mcp-servers/slack-history-mcp/slack-history-mcp.py]
    env:
      SLACK_HISTORY_TOKEN_FILE: /ABS/PATH/.local/secrets/slack-history-token
      SLACK_HISTORY_CHANNELS: C0123456789 # optional allowlist, comma-separated
```

Codex (`~/.codex/config.toml`):

```toml
[mcp_servers.slack_history]
command = "/ABS/PATH/silica-ops-agent/.venv/bin/python"
args = ["/ABS/PATH/silica-ops-agent/mcp-servers/slack-history-mcp/slack-history-mcp.py"]
env = { SLACK_HISTORY_TOKEN_FILE = "/ABS/PATH/.local/secrets/slack-history-token", SLACK_HISTORY_CHANNELS = "C0123456789" }
```

Store the token alone in a file outside the repository, for example `install -m 600 /dev/null ~/.local/secrets/slack-history-token`, then paste it in. Keep the token out of MCP configs. `SLACK_HISTORY_TOKEN` also works but puts the secret in config. Set `SLACK_HISTORY_CHANNELS` to limit readable channels (the escalation channel at minimum).

## Run once on a long-running host (optional)

Instead of a stdio server per machine, run it as streamable HTTP on the WSL host and point other machines at it. The Slack token then lives only on that host.

Run `scripts/bootstrap-wsl-host.sh` to install or refresh the service. It needs `uv`, systemd, and `~/.local/secrets/slack-history-token`. Add `--harness` to also run `harness global` and `harness use`. For a manual install in `~/silica-ops-agent`, run the following commands.

```bash
install -m 600 /dev/null ~/.local/secrets/slack-history-mcp-http-token   # paste a long random string
mkdir -p ~/.config/systemd/user && cp mcp-servers/slack-history-mcp/slack-history-mcp.service ~/.config/systemd/user/
# Optional for new installs: copy mcp-servers/slack-history-mcp/.env.example to .env in the same directory and set SLACK_HISTORY_CHANNELS.
systemctl --user daemon-reload && systemctl --user enable --now slack-history-mcp
loginctl enable-linger "$USER"
```

On an existing WSL host, rerun the bootstrap script to install the new unit and restart the service. The unit still reads `scripts/slack-history-mcp.env`, so existing allowlists carry over. Values in `mcp-servers/slack-history-mcp/.env` take precedence when both files are present.

The unit listens on `0.0.0.0:60010/mcp` and rejects requests without `Authorization: Bearer <http token>`; the bearer token is the only application-level protection, so keep it secret. Reach the host over [Tailscale](https://tailscale.com) installed inside WSL (`curl -fsSL https://tailscale.com/install.sh | sh`, then `sudo tailscale up`), and install it on the laptop too. Traffic is then encrypted and needs no Windows port proxy or firewall rule, which WSL2's NAT mode would otherwise require. Use `http://<wsl-tailnet-name>:60010/mcp` as the URL, and restrict port 60010 to your laptop with a Tailscale ACL if wanted. For loopback only, change the unit to `--host 127.0.0.1` and use an SSH tunnel instead. On the laptop, save the token to `~/.local/secrets/slack-history-mcp-http-token` (`chmod 600`) and render `config/mcp-servers.remote.toml` with `scripts/render-mcp-config.py {codex,hermes} --registry config/mcp-servers.remote.toml`. Codex reads the file through `scripts/mcp-bearer-header.sh` (`http_headers_helper`), so no environment variable is needed; Hermes still needs `SLACK_HISTORY_MCP_TOKEN` exported.

## Verification

```bash
.venv/bin/python mcp-servers/slack-history-mcp/slack-history-mcp.py --check
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
