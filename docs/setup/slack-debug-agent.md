---
title: "Set up the Slack debug agent"
description: "Test the private diagnosis listener on macOS or deploy it on the Ubuntu office PC."
tags: [slack, codex, diagnosis, macos, ubuntu, systemd, approvals]
---

# Set up the Slack debug agent

Run one listener for one authorized Slack user. The bot handles general conversations in private DM threads. For incident requests, it reads issues from the configured escalation channel with a user token and follows the [shared diagnosis workflow](../diagnose_agent.md) and [Slack behavior](../diagnose_agent_in_slack.md), including documentation branches, PR creation, and worktree cleanup.

## Prerequisites

- A macOS or Ubuntu host with Python 3.11 or newer, `uv`, Git, GitHub CLI (`gh`), `rtk`, and Codex CLI with a compatible `app-server`. systemd deployment is Ubuntu-only.
- The repository's shared `.venv/bin/python`, created using the [Python environment guide](setup-python-venv.md). All listener and test commands below use it.
- A configured root `config.env`. Configure `SILICA_REPO` and `SILICA_ENV_REPO` for this host, using absolute paths or paths relative to this toolkit root. The listener snapshots and resolves these values once; restart after changes. Missing or invalid values stop startup.
- Existing diagnosis access, including **read-only production credentials**. Do not give this service credentials capable of applying production fixes. The listener removes Slack variables from the Codex child environment. The repo-local `service.env` file is owned by your account: mode `600` protects it from other users, but the agent runs as your account and can read it. Git ignore does not isolate credentials from the agent.
- Git remote push access, a configured Git author, and `gh auth status` passing as the service user. The sibling `../worktree/` directory must be writable by that user. Published branches and PRs remain for human review.
- For deployment, a dedicated Codex home outside the repository, with Codex login and read-only Grafana MCP connections. For explicit local `--profile` testing, the normal `~/.codex` home is supported and its existing execpolicy rules are inherited. Grafana MCP servers are already running; connection recovery belongs to the user.

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

For deployment, as the eventual service user, create a dedicated Codex home, copy `slack-debug-agent/deploy/codex.config.toml` into its `config.toml`, and authenticate with `CODEX_HOME` pointing to that directory. For local testing with your existing profile, skip this dedicated-home setup and use the macOS section below.

```bash
install -d -m 700 "$HOME/.local/share/slack-debug-codex"
cp slack-debug-agent/deploy/codex.config.toml "$HOME/.local/share/slack-debug-codex/config.toml"
CODEX_HOME="$HOME/.local/share/slack-debug-codex" codex login
```

Configure `grafana_mcp_ops_dev` and `grafana_mcp_ops_prod` in that dedicated config. Use the endpoint URLs supplied by the existing environment owner. Do not start another forwarding supervisor. See [Grafana connection preparation](grafana-mcp-forward.md) for the existing host configuration.

The listener forces `workspace-write`, `on-request`, user-reviewed approvals, disabled sandbox networking, and no additional writable roots or writable temporary directories outside the workspace. It disables hooks and agent delegation for these sessions so the existing force-checkout startup hook cannot run. Without `--profile`, existing execpolicy rule files in the dedicated home or toolkit `.codex/rules/` cause startup to fail. Explicit `--profile` testing inherits the chosen home's existing command rules, so matching commands may run without a new Slack prompt. Keep deployment configuration free of approval rules or automatic hooks.

The investigation starts in the original toolkit root. The agent is instructed to leave that working tree intact and write documentation only in the post-investigation worktree. That instruction is separate from the sandbox: `workspace-write` technically allows writes in the original root. Repository worktrees share Git metadata; Git and writes to the external documentation worktree can require explicit sandbox approval.

### Repo-local environment file and systemd user service

1. From the original toolkit root, create the local environment file:

   ```bash
   install -m 600 slack-debug-agent/deploy/service.env.example slack-debug-agent/deploy/service.env
   ```

   Replace every placeholder in `slack-debug-agent/deploy/service.env`. This file is ignored by Git; do not force-add it or copy it into documentation worktrees. Re-running the install command overwrites it, so use it only for initial setup.

2. Set `SLACK_DEBUG_CODEX_HOME` to the dedicated absolute path. Set `PATH` to include the actual Codex, Git, `gh`, `rtk`, and diagnosis commands available to your account. Environment file values do not expand `$HOME` or `%h`; use actual absolute paths. Add `TZ=Asia/Hong_Kong` if the host uses another timezone and worktree dates should follow Hong Kong time.
   For foreground testing, complete steps 1–2, then follow the next section. For managed deployment, continue with steps 3–5:

3. Install the user service template:

   ```bash
   install -d "$HOME/.config/systemd/user"
   cp slack-debug-agent/deploy/slack-debug-agent.service "$HOME/.config/systemd/user/slack-debug-agent.service"
   ```

   Edit the installed unit's `WorkingDirectory`, `EnvironmentFile`, and both paths in `ExecStart` to match the original toolkit root. The template assumes `%h/silica-ops-agent` as an example; `%h` expands to your home directory in the unit. `EnvironmentFile` must point to that repo's `slack-debug-agent/deploy/service.env`. A user service runs as your account and does not need `User` or `Group` settings.

4. Start the user service:

   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now slack-debug-agent
   systemctl --user status slack-debug-agent
   ```

   Use `systemctl --user restart slack-debug-agent` after configuration changes. To view logs, use `journalctl --user -u slack-debug-agent -n 50 --no-pager`.

5. To start at boot and keep running after logout, enable lingering for your account with `loginctl enable-linger "$USER"`. This may require administrator authorization under the host's policy. See [loginctl](https://www.freedesktop.org/software/systemd/man/latest/loginctl.html).

`KillMode=control-group` stops Codex processes and descendants on a service restart. New Codex threads persist in the configured Codex home. The listener keeps their Slack DM mappings in `./slack-debug-agent/state/sessions.sqlite3`. Reply in the original DM thread after restarting to resume saved context. Running commands, pending approvals, questions, and queued replies are interrupted rather than automatically replayed; old buttons cannot authorize a new process. Git branches, documentation worktrees, and PRs also remain available for recovery.

On Linux, the listener disables process dumpability before starting Codex, protecting its environment and memory from same-user child inspection through procfs or ptrace. On macOS it disables core dumps; it does not apply Linux's process-inspection protection. Neither prevents filesystem access to the repo-local token file. See [PR_SET_DUMPABLE](https://man7.org/linux/man-pages/man2/PR_SET_DUMPABLE.2const.html) and [procfs environment access](https://man7.org/linux/man-pages/man5/proc_pid_environ.5.html).

### macOS testing with an existing Codex profile

Use the repository's existing `.venv/bin/python`. From the toolkit root, install the listener dependencies if needed:

```bash
uv pip install --python .venv/bin/python -r slack-debug-agent/requirements.txt
```

Create and fill in `slack-debug-agent/deploy/service.env` from the template if it does not already exist. Keep the Slack tokens, user/channel IDs, and workspace hostname configured there. Set the Codex home and your macOS tool search path, for example on this Apple Silicon host:

```dotenv
SLACK_DEBUG_CODEX_HOME=~/.codex
PATH=/opt/homebrew/bin:/Users/7am/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin
```

The listener explicitly expands `~` in the Codex home setting. For another account or Homebrew installation, adjust `PATH` to the actual directories containing your tools. Do not leave the Ubuntu `/home/ops/...` example path in the local environment file.

The profile filename is `~/.codex/diagnose.config.toml` (`.toml`, not `.tmol`). The selected home must also contain its base `config.toml` and your existing Codex login. Run:

```bash
.venv/bin/python slack-debug-agent/main.py --env-file slack-debug-agent/deploy/service.env --profile diagnose --check
.venv/bin/python slack-debug-agent/main.py --env-file slack-debug-agent/deploy/service.env --profile diagnose
```

Leave the second command running and DM the bot `help debugging on <issue-permalink>`. Press Ctrl-C to stop it. No systemd service is needed for this test. Do not run a second listener for the same app at the same time.

`--profile diagnose` is a listener option. The listener reads `<CODEX_HOME>/diagnose.config.toml` once and overlays it through the app-server's thread configuration. The existing home supplies base configuration, authentication, and command rules. Use absolute paths for file references in an imported profile, since thread overrides do not preserve native profile-file path metadata. The listener does not edit your profile. Its forced sandbox, network, approval, hook, and delegation settings take precedence over profile values. The agent receives the profile's MCP server names so it can use the matching available dev/prod Grafana connections.

Profile reference: [Codex configuration profiles](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles). The adapter's profile overlay and effective sandbox are checked against a real local app-server without starting a model turn.

### Foreground testing with Python

On macOS or Ubuntu, from the original toolkit root, validate configuration without connecting to Slack. For the existing-profile setup above, also pass `--profile diagnose`:

```bash
.venv/bin/python slack-debug-agent/main.py --env-file slack-debug-agent/deploy/service.env --check
```

Then start the listener in the foreground:

```bash
.venv/bin/python slack-debug-agent/main.py --env-file slack-debug-agent/deploy/service.env
```

`--env-file` reads the file once before configuration validation, overrides matching inherited variables, and does not expand variable references or execute shell commands. Relative file paths resolve from the toolkit root. A missing or empty file stops startup. Without this option, the listener uses the environment supplied by systemd or its parent process.

Keep the terminal open and DM the bot `help debugging on <issue-permalink>`. Confirm the acknowledgement, compact activity updates, approval buttons, report, and same-thread follow-up. Activity should use a new message after each approval or answer. Set `SLACK_DEBUG_ACTIVITY=off` and restart to verify that activity disappears. Press Ctrl-C to stop the listener and its Codex sessions. After restarting, reply in the same DM thread to resume saved context; pending approvals, questions, and queued replies are not restored. A quiet terminal while the listener waits for messages is normal; it does not log issue content or tokens. Do not run a foreground listener and the systemd service simultaneously.

### Persistent conversations

Persistence is enabled for new sessions automatically. Keep `SLACK_DEBUG_CODEX_HOME` stable: Codex stores the conversation history there, and the listener stores thread mappings and event IDs in `./slack-debug-agent/state/sessions.sqlite3`. The database path resolves from the toolkit root, independently of the listener’s working directory. The database is created with mode `600` inside a directory created with mode `700`; the entire state directory is ignored by Git. If the local database does not exist, startup imports an existing `<CODEX_HOME>/slack-debug/sessions.sqlite3` using SQLite backup and keeps the old file intact. An existing local database is never overwritten by that import. Stop any older listener before upgrading. It does not store Slack tokens, issue bodies, or reply text. Native Codex history can contain investigation data and command output; protect and back up both the local state directory and the Codex home. No new packages or Slack permissions are required for persistence.

After a listener restart, send `continue` or your next question in the original DM thread. Resumption is on demand; the listener does not automatically replay operations. Pending approvals, questions, and queued replies must be reissued. Saved mappings are scoped to workspace, authorized user, escalation channel, toolkit and repository paths, Codex home, and profile name, so changing those settings may make earlier mappings unavailable. If native history is missing, resumption reports failure and retains the mapping; it does not silently start a new conversation. Sessions created before this feature used ephemeral history and cannot be recovered by this update.

### MCP input requests

The listener handles `mcpServer/elicitation/request` for `form`, `openai/form`, `openaiForm`, and `url` modes. Form requests show the server name, message, and JSON schema in the originating DM thread. Reply with a matching JSON object (`{}` for an empty form), or `decline` or `cancel`. Invalid replies are rejected and can be retried. URL requests display an HTTPS URL for you to open manually; complete the browser interaction and reply `accept`, or decline/cancel. Never put credentials in DM replies.

Only the configured user can answer. Requests are serialized per session so each reply answers one question. An unanswered request cancels after ten minutes, allowing Codex to continue. Invalid, unsupported, referenced, oversized, and explicitly secret-input schemas are declined with an explanation instead of an unsupported-request session failure.

After updating, rerun `uv pip install --python .venv/bin/python -r slack-debug-agent/requirements.txt` to install the new JSON Schema validator, then restart the listener. No additional Slack permissions are needed.

### Approval display

Short approvals show `Approve? [short-id]`, the command after `$` in a native Slack code block, with the absolute working directory and `why:` outside the block and buttons directly below. Multiline scripts retain indentation, line breaks, and literal backticks. Plain shell `-c`/`-lc` wrappers and redundant protocol metadata are omitted; unknown request fields and file-change details remain visible. Commands are split into code blocks of at most 2,800 characters without truncation. Up to ten detail blocks share one message; larger requests span messages, with buttons only after all details have been delivered. Full request IDs are retained in button values, and the command and reason remain after approval or denial. Raw approval payloads are not logged because commands and diffs can contain secrets.

### Findings delivery

Final answers arrive as one Slack rich-text message with bullets, emphasis, labeled links, and code blocks where useful. The listener converts local file citations in the configured repositories to commit-pinned GitHub links when the cited file matches a published revision known to the checkout. Citations to unpublished files use repository-relative paths. The agent is instructed to keep diagnosis reports under 6,000 characters and put extended findings in the diagnosis PR. The listener repairs JSON-encoded report strings and escaped prose newlines and preserves code escapes. Replies exceeding 12,000 characters receive a visible shortening notice and retain reference links within the reply limit. Ask a follow-up for omitted details. Approval commands are rendered in full in native Slack code blocks. Restart the listener after updating the code.

### Activity feed

Each visible activity line has its own Slack section on both the initial post and subsequent updates, so commands remain visually separated. The message displays up to 20 sections, with an omission notice when older lines are dropped.

Set `SLACK_DEBUG_ACTIVITY=summary` (default) or `off` in the listener environment and restart it. Summary mode edits a bounded activity message in the originating DM thread about every two seconds. Process entries use Slack quote blocks with emoji labels such as `🔎 Explored` and `💻 Ran`. Command text appears in a bordered code block beneath `💻 Ran`. Agent commentary appears as plain prose. The listener flushes and starts a fresh activity message around approvals, questions, final answers, and failures. Commands may contain sensitive arguments; activity excludes command output, diffs, tool results, and reasoning. Slack update failures are best effort and do not fail the diagnosis. Activity does not add Slack permissions.

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

1. Run `.venv/bin/python slack-debug-agent/main.py --env-file slack-debug-agent/deploy/service.env --check`. This checks local paths, token prefixes, the dedicated profile, and that `codex` is on the service `PATH`, without connecting to Slack. Run the automated local checks above to verify the installed binary's app-server protocol. The listener loads the file only when `--env-file` is supplied; systemd uses the unit's `EnvironmentFile` setting instead. A missing service environment is a startup error, not a fallback to interactive credentials.
2. Send `help debugging on <issue-permalink>` in a bot DM. Try both a top-level message and a reply permalink, including a reply link without a `thread_ts` query. Confirm that the whole parent thread is read. If Slack rejects a reply-only timestamp, use its full link with `thread_ts`; the listener reports the error rather than silently investigating incomplete evidence.
3. Ask for a harmless command requiring sandbox escalation. Confirm Codex emits the approval request instead of stalling, the DM shows the complete command, absolute working directory, and reason, and execution waits for **✅ Approve**. Check **❌ Deny**, **💬 Others**, a ten-minute expiry, and rejection of other users' actions. The known escalation-delivery issue is not established as fixed by the generated schema or mock tests.
4. Confirm a harmless network command is blocked inside the sandbox and routed to approval when escalated. An approval is one request only; no allowlist or session-wide grant is saved. File approvals require a complete diff; root-wide grants and unsupported permission requests fail closed.
5. Complete a diagnosis and confirm `../worktree/<YYMMDD>-<actual-agent-session-or-thread-id>/`, a pushed documentation branch, an open PR, and removal of the clean worktree. Confirm no production remediation ran. The Git workflow is executed by Codex following the shared instructions; the listener does not independently validate the PR or execute Git on the agent's behalf.
6. Send a follow-up in the same DM thread. Confirm it uses the same Codex session and can update the same PR after recreating the documentation worktree.
7. Create a new session with this persistence-capable listener, let it run a turn, restart, and reply in the same DM thread. Expect a resuming acknowledgement and continued context. Confirm that old approval buttons do nothing, new approvals are required, and interrupted operations are verified before retrying. Confirm duplicate Slack events do not start duplicate work. Threads created by older ephemeral versions remain unavailable. Check that the original toolkit working tree and other sessions' shared forwards are intact.

No live Slack, production diagnosis, remote push/PR, or Ubuntu systemd acceptance check was performed during local implementation.

## Usage

Start a general conversation by sending a top-level DM to the bot, such as `Explain how Slack threads work`. Reply in that message's thread to keep the conversation context. Send another top-level DM to start a separate conversation.

To investigate an issue, send a top-level DM with the escalation message's permalink:

```text
help debugging on https://your-workspace.slack.com/archives/CHANNEL_ID/pMESSAGE_TIMESTAMP
```

Shorthand such as `debug <issue-permalink>` or `please debug <issue-permalink>` also starts an investigation. The bot validates links submitted through these commands. The final diagnosis report includes symptom, suspected cause, evidence, added or updated repository-relative file paths, and a PR URL.

In either kind of thread, use **✅ Approve** or **❌ Deny** for sandbox decisions. Use **💬 Others** to enter instructions in a Slack form. Submitting declines the operation and queues your instructions for the agent's next turn. The listener applies the same Codex profile and approval policy to both kinds of conversation. Ordinary messages never approve commands.

An unanswered approval expires after ten minutes and pauses the session. Reply in the same DM thread to resume. The agent will ask for fresh approval if needed.

There is no concurrency cap. Each active session gets its own Codex process and runs at most two hours from attachment, including follow-up and idle time. At that limit, a session awaiting approval pauses and other sessions report `failed: timed out after 2h`. An explicit reply after a pause, restart, failure, or timeout resumes the saved Codex conversation in a new process with a new two-hour window. The listener uses the user-token client to read issue threads and the bot client to reply in private DMs. It does not download attachments.

## Troubleshooting

- **Startup fails:** correct `config.env` or `slack-debug-agent/deploy/service.env` as indicated, then restart the user service. Check the unit's absolute paths, your account's `PATH`, Codex version, and dedicated home. Do not log tokens or enable verbose SDK logging.
- **Issue read fails:** check the user token's scopes and channel access. Slack rate limits and permission errors produce a private failure report; they do not trigger writes or joins in the escalation channel.
- **No approval appears:** stop the affected session, inspect the host's Codex version and protocol, and complete the escalation acceptance check before retrying. The two-hour deadline is a backstop, not proof that escalation delivery works.
- **Git or PR step fails:** preserve the worktree and branch for recovery, as the shared workflow requires. Restore Git/`gh` access as the service user and start a new request if the old session has ended.
- **Grafana MCP is unavailable:** the user fixes the connection and restarts the Codex session; use a new DM request for a fresh listener-managed session. In an ordinary Hermes session, use `/reload-mcp` instead.
- **Host load is high:** the v1 listener has unbounded concurrency. Stop the service to terminate its sessions if necessary; pending approvals, questions, and queued replies are lost; saved conversations can be resumed later.

## Cleanup

Run `systemctl --user disable --now slack-debug-agent` before removing the installed user unit or repo-local `service.env`. After removing the unit from `~/.config/systemd/user/`, run `systemctl --user daemon-reload`. Remove only diagnosis worktrees you have reviewed and no longer need, using `git worktree remove`; retain failed worktrees until their contents are recovered. Published branches and PRs require separate human review or closure. Preserve shared Grafana forwarding and tunnels not owned by this service.

Protocol references: [Codex app-server](https://developers.openai.com/codex/app-server), [Slack Socket Mode for Python](https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/), [conversations.replies](https://docs.slack.dev/reference/methods/conversations.replies/), [chat.postMessage](https://docs.slack.dev/reference/methods/chat.postMessage/), and [chat.update](https://docs.slack.dev/reference/methods/chat.update/).
