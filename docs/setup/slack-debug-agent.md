---
title: "Set up the Slack debug agent"
description: "Run a private Socket Mode diagnosis listener with Codex approvals on the Ubuntu office PC."
tags: [slack, codex, diagnosis, ubuntu, systemd, approvals]
---

# Set up the Slack debug agent

Run one listener for one authorized Slack user and one escalation channel. It reads issues with a user token and communicates only in the bot's private DM thread. It follows the [shared diagnosis workflow](../diagnose_agent.md) and [Slack behavior](../diagnose_agent_in_slack.md), including documentation branches, PR creation, and worktree cleanup.

## Prerequisites

- An Ubuntu host with Python 3.11 or newer, `uv`, Git, GitHub CLI (`gh`), `rtk`, and **Codex CLI 0.169.0**. The listener rejects other Codex versions until the protocol is verified and the pin is updated.
- The repository's shared `.venv/bin/python`, created using the [Python environment guide](setup-python-venv.md). All listener and test commands below use it.
- A configured root `config.env`. Configure `SILICA_REPO` and `SILICA_ENV_REPO` for this host, using absolute paths or paths relative to this toolkit root. The listener snapshots and resolves these values once; restart after changes. Missing or invalid values stop startup.
- Existing diagnosis access, including **read-only production credentials**. Do not give this service credentials capable of applying production fixes. The listener removes Slack variables from the Codex child environment; host filesystem permissions must also prevent the service user from reading the root-owned token file.
- Git remote push access, a configured Git author, and `gh auth status` passing as the service user. The sibling `../worktree/` directory must be writable by that user. Published branches and PRs remain for human review.
- A dedicated Codex home outside the repository, with Codex login and read-only Grafana MCP connections. Do not reuse the normal interactive Codex home or its execpolicy rules. Grafana MCP servers are already running; connection recovery belongs to the user.

## Setup

### Slack app and tokens

1. Create an internal app using `slack-debug-agent/slack-app-manifest.json`. Socket Mode, interactivity, the Messages tab, and `message.im` are configured there; no public URL is required.
2. For a public escalation channel, keep user scopes `channels:history` and `channels:read`. For a private channel, replace them with `groups:history` and `groups:read`, and ensure the authorized human can read it. Never add write scopes to the user token or invite the bot into the escalation channel.
3. Install the app and obtain its `xoxb-` bot token and the authorized human's `xoxp-` user token. Generate an app-level `xapp-` token with `connections:write`. Token rotation is not implemented in v1.
4. Record the authorized user's ID, escalation channel ID, and workspace hostname (for example `your-workspace.slack.com`). Startup checks that the bot and user tokens belong to the same team and that the user token belongs to the configured user.

### Python and Codex

From the toolkit root:

```bash
uv pip install --python .venv/bin/python -r slack-debug-agent/requirements.txt
codex --version
```

As the eventual service user, create a dedicated Codex home, copy `slack-debug-agent/deploy/codex.config.toml` into its `config.toml`, and authenticate with `CODEX_HOME` pointing to that directory:

```bash
install -d -m 700 "$HOME/.local/share/slack-debug-codex"
cp slack-debug-agent/deploy/codex.config.toml "$HOME/.local/share/slack-debug-codex/config.toml"
CODEX_HOME="$HOME/.local/share/slack-debug-codex" codex login
```

Configure `grafana_mcp_ops_dev` and `grafana_mcp_ops_prod` in that dedicated config. Use the endpoint URLs supplied by the existing environment owner. Do not start another forwarding supervisor. See [Grafana connection preparation](grafana-mcp-forward.md) for the existing host configuration.

The listener forces `workspace-write`, `on-request`, user-reviewed approvals, disabled sandbox networking, and no writable temporary directories outside the workspace. It disables hooks and agent delegation for these sessions so the existing force-checkout startup hook cannot run. Existing execpolicy rule files in the dedicated home or toolkit `.codex/rules/` cause startup to fail. Keep parent-directory project configuration and installed plugins free of approval rules or automatic hooks for this service.

The investigation starts in the original toolkit root. The agent is instructed to leave that working tree intact and write documentation only in the post-investigation worktree. That instruction is separate from the sandbox: `workspace-write` technically allows writes in the original root. Repository worktrees share Git metadata; Git and writes to the external documentation worktree can require explicit sandbox approval.

### External environment file and systemd

1. As root, create `/etc/slack-debug-agent/` with mode `700`, and copy `slack-debug-agent/deploy/service.env.example` to `/etc/slack-debug-agent/service.env`. Set ownership to `root:root` and mode `600`; replace every placeholder. Do not source or copy this file into the repository or a worktree. systemd reads it before dropping to the service user.
2. Set `SLACK_DEBUG_CODEX_HOME` to the dedicated absolute path. Set `PATH` to include the actual Codex, Git, `gh`, `rtk`, and diagnosis commands available to the service user. Add `TZ=Asia/Hong_Kong` if the host uses another timezone and worktree dates should follow Hong Kong time.
3. Copy `slack-debug-agent/deploy/slack-debug-agent.service` to `/etc/systemd/system/`. Edit `User`, `Group`, `WorkingDirectory`, and `ExecStart` for the existing host account and toolkit location. The example assumes account `ops` and toolkit `/opt/silica-ops-agent`; these are deployment placeholders, not runtime defaults.
4. Start the service:

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable --now slack-debug-agent
   sudo systemctl status slack-debug-agent
   ```

`KillMode=control-group` stops Codex processes and descendants on a service restart. State is intentionally in memory; sessions cannot resume after the listener restarts. Codex threads are ephemeral. Git branches and PRs are persistent review artifacts, not listener state.

The Linux listener disables process dumpability before starting Codex, protecting its environment and memory from same-user child inspection through procfs or ptrace. Startup fails if this protection cannot be enabled. Local tests and `--check` can run on macOS; the listener itself requires Linux. See [PR_SET_DUMPABLE](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html) and [procfs environment access](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html).

## Verification

### Automated local checks

From the toolkit root:

```bash
PYTHONPATH=slack-debug-agent .venv/bin/python -m unittest discover -s slack-debug-agent/tests -v
```

This exercises authorization, permalink validation and pagination, duplicate events, follow-ups, approval identity and expiry, full command delivery across message limits, clarification replies, timeout cleanup, an actual JSON-lines subprocess, and schema generation from the installed Codex. The two HTTP tests skip unless a local simulation URL is supplied.

To exercise the real Slack SDK over HTTP without Slack credentials, start the repository's local Postman simulation in another terminal (Postman CLI 1.73.0 was used during development):

```bash
postman simulation run postman/simulations/slack-debug/slack-debug.sim.yaml --port 4091 --no-history --output ndjson
```

Then run:

```bash
SLACK_DEBUG_SIM_URL=http://127.0.0.1:4091/slack PYTHONPATH=slack-debug-agent .venv/bin/python -m unittest discover -s slack-debug-agent/tests -v
```

Stop the simulation with Ctrl-C. It models reply-to-root resolution, DM report delivery, Slack API errors, and HTTP failures. It does not validate real Slack tokens, Socket Mode, or real reply permalink behavior. The fixture is authored from the official method documentation, not an owner-published mock; Postman owner discovery was unavailable because this installed CLI does not implement `postman status`.

### Host acceptance checks

Before operational use, test these with the actual configured user and Ubuntu Codex version:

1. In a service environment with the external variables loaded securely, run `.venv/bin/python slack-debug-agent/main.py --check`. This checks local paths, token prefixes, the dedicated profile, and the pinned Codex version without connecting to Slack. A missing service environment is a startup error, not a fallback to interactive credentials.
2. Send `help debugging on <issue-permalink>` in a bot DM. Try both a top-level message and a reply permalink, including a reply link without a `thread_ts` query. Confirm that the whole parent thread is read. If Slack rejects a reply-only timestamp, use its full link with `thread_ts`; the listener reports the error rather than silently investigating incomplete evidence.
3. Ask for a harmless command requiring sandbox escalation. Confirm Codex emits the approval request instead of stalling, the DM shows the complete command, working directory, and reason, and execution waits for **Approve**. Check **Deny**, a ten-minute expiry, and rejection of other users' actions. The known escalation-delivery issue is not established as fixed by the generated schema or mock tests.
4. Confirm a harmless network command is blocked inside the sandbox and routed to approval when escalated. An approval is one request only; no allowlist or session-wide grant is saved. File approvals require a complete diff; root-wide grants and unsupported permission requests fail closed.
5. Complete a diagnosis and confirm `../worktree/<YYMMDD>-<actual-agent-session-or-thread-id>/`, a pushed documentation branch, an open PR, and removal of the clean worktree. Confirm no production remediation ran. The Git workflow is executed by Codex following the shared instructions; the listener does not independently validate the PR or execute Git on the agent's behalf.
6. Send a follow-up in the same DM thread. Confirm it uses the same Codex session and can update the same PR after recreating the documentation worktree.
7. Restart the listener and reply in the old thread. Expect `session not found, start a new one`. Check that the original toolkit working tree and other sessions' shared forwards are intact.

No live Slack, production diagnosis, remote push/PR, or Ubuntu systemd acceptance check was performed during local implementation.

## Usage

DM the bot:

```text
help debugging on https://your-workspace.slack.com/archives/CHANNEL_ID/pMESSAGE_TIMESTAMP
```

Use replies in that DM thread for follow-up information and **Approve**/**Deny** for sandbox decisions. Ordinary messages never approve commands. The final report includes symptom, suspected cause, evidence, added or updated repository-relative file paths, and a PR URL.

There is no concurrency cap. Each session gets its own Codex process and runs at most two hours from creation, including follow-up and idle time. A session that exceeds the limit reports `failed: timed out after 2h`. Failed sessions are closed; start a new request to retry. The user-token client only reads threads; the bot client only writes to DM IDs. File contents and arbitrary attachment URLs are not downloaded.

## Troubleshooting

- **Startup fails:** correct `config.env` or the external service environment as indicated, then restart. Check the service user's `PATH`, Codex version, and dedicated home. Do not log tokens or enable verbose SDK logging.
- **Issue read fails:** check the user token's scopes and channel access. Slack rate limits and permission errors produce a private failure report; they do not trigger writes or joins in the escalation channel.
- **No approval appears:** stop the affected session, inspect the host's Codex version and protocol, and complete the escalation acceptance check before retrying. The two-hour deadline is a backstop, not proof that escalation delivery works.
- **Git or PR step fails:** preserve the worktree and branch for recovery, as the shared workflow requires. Restore Git/`gh` access as the service user and start a new request if the old session has ended.
- **Grafana MCP is unavailable:** the user fixes the connection and restarts the Codex session; use a new DM request for a fresh listener-managed session. In an ordinary Hermes session, use `/reload-mcp` instead.
- **Host load is high:** the v1 listener has unbounded concurrency. Stop the service to terminate its sessions if necessary; pending approvals and in-memory state are lost.

## Cleanup

Stop and disable the service before removing its unit or external token file. Remove only diagnosis worktrees you have reviewed and no longer need, using `git worktree remove`; retain failed worktrees until their contents are recovered. Published branches and PRs require separate human review or closure. Preserve shared Grafana forwarding and tunnels not owned by this service.

Protocol references: [Codex app-server](https://developers.openai.com/codex/app-server), [Slack Socket Mode for Python](https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/), [conversations.replies](https://docs.slack.dev/reference/methods/conversations.replies/), [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/), and [chat.update](https://docs.slack.dev/reference/methods/chat.update/).
