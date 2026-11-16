# Final spec: Slack-driven debug agent (use-case 2)

Drafted November 16, 2026

**Goal:** From a private DM, you ask the debug agent to investigate an issue posted in the escalation channel. It works in a session, asks your approval in Slack before running anything outside its sandbox, and reports its findings in the same DM thread. Other people in the workspace never see it interacting.

## User journey

1. **Trigger:** In your DM with the bot, send `help debugging on <issue-permalink>`.
2. **Ack:** The bot replies in a thread under your message: `working on thread <id>`. A bad URL or a channel that isn't allowed gets an error reply and no session.
3. **Debugging:** A new Codex session starts in its own copy of the toolkit repo. The agent reads the issue and its thread (read-only user token) and runs your debug workflow, which updates or adds `runbook`, `incident` and `debrief` docs.
4. **Approval:** Anything Codex asks to run outside its sandbox appears in the thread with the full command, the working directory and the reason, plus **Approve** and **Deny** buttons. No answer in 10 minutes means deny.
5. **Report:** The bot posts `finished debugging` in the same thread with this template:
   - **Symptom:** a brief summary
   - **Suspected cause**
   - **Evidence**
   - **Added files:** paths of the runbook, incident and debrief docs
6. **Follow-up:** If you reply in the thread while the listener is still running, the same session continues.
7. **Failure or timeout:** The bot posts `failed: <reason>`. A session that hits 2 hours is killed with `failed: timed out after 2h`.

Progress messages appear only at start, at approvals and at finish.

## Architecture

- **Slack app:** one internal app. The bot token talks to you, and the user token reads the issue.
- **Listener:** a single Python process using Bolt in Socket Mode, so it only needs outbound internet. It needs no public URL or open port.
- **Runtime:** one `codex app-server` process per session, spawned in that session's working copy of the repo.
- **State:** in memory only (no database, no persistence).
- **Host:** the office Ubuntu PC, which already has the debugging environment. Run the listener as a systemd service, with the tokens in a root-readable env file outside the repo.

## Slack app configuration

| Item | Setting |
| --- | --- |
| Bot scopes | `chat:write`, `im:history`, `im:read`, `im:write` |
| User scopes (read-only) | `channels:history`, `channels:read` (or the `groups:` versions for a private channel) |
| Event | `message.im` |
| Interactivity | On, for the approval buttons |
| App-level token | `connections:write` (Socket Mode) |
| App Home | Messages tab enabled |

## Agent policy

- **Sandbox:** `workspace-write`, limited to the session's repo copy. Read-only would not work, because the agent has to write the runbook, incident and debrief docs.
- **Approval policy:** `on-request`. Anything needing escalation goes to Slack.
- **Execpolicy allowlist:** none in v1.
- **Credentials:** read-only production access only. The agent proposes fixes and never applies them.
- **Time limits:** 10 minutes per approval, 2 hours per session.

## Concurrency and the working repo

There is no limit on concurrent sessions, and each session writes docs into the repo. Several sessions sharing one working tree would overwrite each other's files. Proposal: a **git worktree per session** (for example `sessions/<thread-ts>` on branch `debug/<thread-ts>`). Each session's new docs then stay isolated, and the report's "Added files" list points into that worktree. You review the branch and merge or discard it.

## Security rules

- Only your Slack user ID can start sessions or click Approve and Deny.
- Only the escalation channel ID is accepted as an issue source.
- The issue text is untrusted input. Treat it as data, not instructions.
- The bot never posts, reacts or joins in the escalation channel.
- Approval messages always show the full, unabridged command.

## What to expect in v1

- **Many approval taps at first.** With no allowlist, anything that needs network access or writes outside the repo needs approval, including your own debug scripts. Reading and writing inside the repo should not. After a few sessions you'll see which commands come up repeatedly, and those are the candidates for the allowlist.
- **A restart loses state.** Running sessions die, pending approvals vanish, and replies in old threads can't resume. The bot should answer `session not found, start a new one` instead of failing silently.
- **Unbounded concurrency means unbounded load.** Many sessions at once can overload the PC and the Codex usage, and each can send approval prompts. Each prompt appears in its own thread, so they stay separable.

## Verify before building

- The exact approval decision values in the app-server protocol schema, for the Codex version you'll run.
- That approval requests reliably reach the client on that version. There is a reported bug where a turn stalled on an escalation prompt without sending a request.
- That a user-token read works for permalinks that point to a thread reply, not only top-level messages.
- Whether the sandbox's default network setting blocks your debug scripts, since that decides how often approvals fire.

## Commit and push on finish

When a session finishes, the agent commits its changes (the new or updated runbook, incident and debrief docs) to the session branch. It then pushes that branch to the remote.

## Out of scope for v1

- Automatic detection of new issues
- Applying fixes
- Multiple users
- Runbook generation from history (use-case 1)
