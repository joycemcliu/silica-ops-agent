---
title: "Google Drive RCA MCP server"
description: "Configure Google Drive publishing for Phase C of a diagnosis."
tags: [mcp, google-drive, google-docs, rca, setup]
---

# Set up the Google Drive RCA MCP server

The `google_drive_rca` server publishes approved Phase C reports as native Google Docs in the [RCA folder](https://drive.google.com/drive/u/0/folders/0ACoH-lkKZePWUk9PVA). With `RCA_GOOGLE_CREDENTIALS_FILE` unset, the server runs in local mode and saves an HTML draft on the MCP host.

## Prerequisites

- Set up the [repo-local Python environment](setup-python-venv.md) on the MCP host.
- To publish to Drive, enable the Drive API in a Google Cloud project. Give a dedicated service account access to create and edit files in the target shared drive, using the Contributor role where allowed. The server requests the `drive.file` OAuth scope. [Shared drive roles](https://developers.google.com/workspace/drive/api/guides/about-shareddrives)
- For Drive publishing, store the service account JSON on the MCP host with mode `600`, readable by the account running the client or Slack listener.

## Setup

1. To enable Drive publishing or customize the HTTP token path, copy `mcp-servers/env/.env.gdrive.example` to `mcp-servers/env/.env.gdrive` if needed. Replace the `RCA_GOOGLE_CREDENTIALS_FILE` sample value with your JSON file path or remove the assignment for local mode.
2. Install the server requirements from the repository root.

   ```bash
   uv pip install --python .venv/bin/python -r mcp-servers/google-drive-mcp/requirements.txt
   ```

3. Follow [Render MCP server configuration](mcp-servers.md). For Slack, merge the rendered entry into the listener's dedicated Codex home or the profile it uses, then start a fresh session.

   ```bash
   .venv/bin/python scripts/render-mcp-config.py codex
   ```

## Run in the background with systemd

To set up both Slack History and Google Drive RCA on a WSL host, run `scripts/bootstrap-wsl-host.sh`. It installs the requirements, creates missing HTTP token files, and enables and starts both user services. It prints the token file paths to copy to clients. The bootstrap also requires the [Slack read token](slack-history-mcp.md).

### Manual setup

On the Linux host, use the same account that will run the service. These commands create a dedicated random bearer token at the default path with mode `600`.

```bash
install -d -m 700 "$HOME/.local/secrets"
if [[ ! -e "$HOME/.local/secrets/google-drive-rca-mcp-http-token" ]]; then
  (umask 077 && set -o noclobber && openssl rand -hex 32 > "$HOME/.local/secrets/google-drive-rca-mcp-http-token")
fi
install -d "$HOME/.config/systemd/user"
sed "s|%h/silica-ops-agent|$PWD|g" mcp-servers/google-drive-mcp/google-drive-mcp.service \
  > "$HOME/.config/systemd/user/google-drive-mcp.service"
systemctl --user daemon-reload
systemctl --user enable --now google-drive-mcp
systemctl --user status google-drive-mcp
```

Run these commands from the toolkit root. After editing `.env.gdrive`, run `systemctl --user restart google-drive-mcp`. View logs with `journalctl --user -u google-drive-mcp -n 30 --no-pager`.

The service listens on `127.0.0.1:60011/mcp`. Forward port `60011` over SSH to use that URL from a remote client. For a direct tailnet connection, bind the server to the host's Tailscale IP with `--host <Tailscale IP>` and update the URL in `config/mcp-servers.remote.toml`.

On the client, copy the host's HTTP token to `~/.local/secrets/google-drive-rca-mcp-http-token` with mode `600`. If the host uses `RCA_MCP_HTTP_TOKEN_FILE`, copy from that path. Render the remote registry and merge its `google_drive_rca` entry into the client config.

```bash
.venv/bin/python scripts/render-mcp-config.py codex --registry config/mcp-servers.remote.toml
```

Codex uses the bearer token file through the shared header helper. For Hermes, render with `hermes` and export `GOOGLE_DRIVE_RCA_MCP_TOKEN` in the client's environment. Google Drive credentials and any local draft files stay on the MCP host.

## Verification

Confirm `google_drive_rca` exposes `create_rca_doc` in a fresh diagnosis session. Run the local tests from the repository root.

```bash
.venv/bin/python -m unittest scripts/tests/test_google_drive_mcp.py scripts/tests/test_render_mcp_config.py
```

For the first approved report, open the returned Drive URL or local HTML file and verify the headings and tables.

## Usage

Use `create_rca_doc` during Phase C after the user reviews the draft. Codex prompts for each call. In Hermes, obtain explicit approval in the conversation before the call. Use the same credential file for all local sessions so they share the write lock.

Local mode saves `knowledge/rca/drafts/<slack_thread_id>.html` under the toolkit root, where Git ignores it. The tool returns the absolute file path. In Slack sessions, the file is on the listener host. An approved call with `replace_existing=true` replaces an existing HTML draft.

The tool uses the original Slack root timestamp to find reports it published. A repeated create returns the existing Google Docs URL. An approved call with `replace_existing=true` replaces the full report body and keeps the URL. [Drive upload and conversion behavior](https://developers.google.com/workspace/drive/api/guides/manage-uploads)

## Troubleshooting

- If a configured credential path is invalid, correct `mcp-servers/env/.env.gdrive`, rerender the MCP configuration, and start a new session.
- For Drive `403` or `404` responses, check the API is enabled and the client runs with the service account that has access to the RCA folder.
- If a create times out, check the folder for the report before retrying, especially when clients run on separate hosts. Drive does not support pre-generated IDs for Google Docs imports. [Drive upload and conversion behavior](https://developers.google.com/workspace/drive/api/guides/manage-uploads)

## Cleanup

Stop and disable the unit with `systemctl --user disable --now google-drive-mcp` before removing the installed unit. Remove `google_drive_rca` from the runtime config and start a new session. Remove the service account key and revoke folder access when no other runtime uses it.
