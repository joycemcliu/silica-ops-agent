---
title: "Set up Codex and Hermes session hooks"
description: "Run diagnosis startup for Codex diagnose subagents, dedicated diagnose sessions, or Hermes sessions."
tags: [codex, hermes, agent, subagent, diagnosis, session, hooks, startup, setup]
---

# Set up agent session hooks

Connect `scripts/diagnose-agent-session-start.sh` to Codex diagnose workers or Hermes. The Codex setup runs for each newly spawned diagnose subagent and, optionally, a main session launched with the diagnose profile. These examples do not repeat startup on every message or resume.

## Prerequisites

- Configure `config.env`, Git remote access, the production SSH and [Windows password files](windows-winrm.md#windows-credentials) on the host where the agent executes commands.
- Use an agent version supporting the hooks below. The agent process needs the same PATH and Kubernetes credentials as a successful manual startup.
- Hermes additionally needs `jq` to read the hook payload.
- Save tracked changes in both configured repositories before enabling automatic startup: the script runs `git checkout master -f`.

## Setup

### Codex

Use a custom subagent with `name = "diagnose"`. If it does not exist, create `<repo>/.codex/agents/diagnose.toml`:

```toml
name = "diagnose"
description = "Diagnose Silica environment issues using this repository's diagnosis workflow."
developer_instructions = "Read and follow AGENTS.md and docs/diagnose_agent.md before diagnosing."
```

If your existing custom agent has another name, use that exact name in the matcher below. A CLI configuration profile and a custom subagent role are separate settings; `--profile diagnose` does not define a subagent role. See [custom agent configuration](https://learn.chatgpt.com/docs/agent-configuration/subagents#custom-agents).

Create `<repo>/.codex/hooks.json`, merging this event into any existing configuration. Remove any earlier repository-wide `SessionStart` entry for this script so ordinary sessions do not run it; retain unrelated hooks:

```json
{
  "hooks": {
    "SubagentStart": [
      {
        "matcher": "^diagnose$",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"$(git rev-parse --show-toplevel)/scripts/diagnose-agent-session-start.sh\"",
            "timeout": 600,
            "statusMessage": "Preparing Silica repositories"
          }
        ]
      }
    ]
  }
}
```

Trust the project and review the hook using `/hooks` in the CLI, or Settings > Hooks in the desktop app. Start a new session after approval. Keep one definition; matching hooks from multiple sources all run. See the [official OpenAI documentation](https://learn.chatgpt.com/docs/hooks).

`SubagentStart` filters `agent_type`, so `^diagnose$` matches only the diagnose role. Each matching spawn runs the script, including when the parent uses an ordinary profile. Other subagent types do not run it. The parent must load and trust this repository's hook; adding it only to a diagnose CLI profile would miss workers spawned by other profiles.

The command resolves the Git root so starting inside a repository subdirectory works. `.codex/` is ignored by this repository; configure each checkout separately.

#### Optional: main diagnose sessions

For a main CLI diagnosis session too, add this separate hook to `~/.codex/diagnose.config.toml`:

```toml
[[hooks.SessionStart]]
matcher = "^startup$"

[[hooks.SessionStart.hooks]]
type = "command"
command = 'bash "$(git rev-parse --show-toplevel)/scripts/diagnose-agent-session-start.sh"'
timeout = 600
statusMessage = "Preparing Silica repositories"
```

Launch from this repository with `codex --profile diagnose`, then review the profile hook. Profile files use top-level keys, not `[profiles.diagnose]`. See [Codex configuration profiles](https://learn.chatgpt.com/docs/config-file/config-advanced#profiles).

`SessionStart` filters `source`. The `^startup$` matcher runs on fresh startup; omitting it also includes resume, clear, compaction, and fork. This profile hook prepares the main session, while the repository's `SubagentStart` hook prepares each diagnose worker. Both run if that main session later spawns a diagnose worker; each invocation repeats the Git updates. The hook does not start Grafana MCP forwards or check MCP connections.

### Hermes

Hermes shell hooks live in the active profile's `config.yaml`. Its [hooks documentation](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#shell-hooks) defines the JSON stdin payload, consent, and timeout behavior.

1. Create `~/.hermes/agent-hooks/silica-session-start.sh` on the execution host. Replace `OPS_ROOT` with the absolute ops-agent repository path there. The wrapper checks the payload's `cwd` to avoid changing repositories when another project opens a session:

   ```bash
   #!/usr/bin/env bash
   set -Eeuo pipefail

   OPS_ROOT="/absolute/path/to/silica-ops-agent"
   session_cwd=$(jq -er '.cwd | select(type == "string" and length > 0)')
   session_root=$(git -C "$session_cwd" rev-parse --show-toplevel 2>/dev/null) || exit 0
   session_root=$(cd "$session_root" && pwd -P)
   ops_root=$(cd "$OPS_ROOT" && pwd -P)
   [[ "$session_root" == "$ops_root" ]] || exit 0

   mkdir -p "$ops_root/.tools"
   log="$ops_root/.tools/session-start.log"
   if bash "$ops_root/scripts/diagnose-agent-session-start.sh" >>"$log" 2>&1; then
     printf '{}\n'
   else
     echo "Session startup failed; inspect $log" >&2
     exit 1
   fi
   ```

   Make the wrapper executable:

   ```bash
   chmod +x ~/.hermes/agent-hooks/silica-session-start.sh
   ```

2. Merge this into `~/.hermes/config.yaml`, or `~/.hermes/profiles/<profile>/config.yaml` for a named profile. For a custom Hermes home, use that profile's actual configuration and wrapper paths:

   ```yaml
   hooks:
     on_session_start:
       - command: "~/.hermes/agent-hooks/silica-session-start.sh"
         timeout: 300
   ```

3. Launch the profile's foreground CLI and approve the hook when prompted, then start a new chat in this repository and send its first message. `on_session_start` runs on the first turn, not on resume. Approve in the same profile used by Desktop or the gateway.

The wrapper logs startup output and returns JSON. The 300-second timeout accommodates Git updates; it is Hermes's maximum shell-hook timeout. Missing consent skips the hook on surfaces that cannot prompt.

## Verification

1. Check the script manually before enabling either integration:

   ```bash
   bash scripts/diagnose-agent-session-start.sh
   ```

2. In Codex, start an ordinary session in this repository and ask it to spawn the custom `diagnose` agent. Check its `SubagentStart` hook result for `Session startup complete.`. An ordinary main session and other subagent types should not run this script. If you configured the optional diagnose profile, also check a fresh `codex --profile diagnose` session. In Hermes, send the first message and inspect `.tools/session-start.log` for the completion line.
3. For Hermes, open a new chat in an unrelated repository and send a message. The ops-agent startup log should not change.

## Usage

These hooks take no script arguments. Keep the Codex subagent matcher set to the exact diagnose role name. To include resume for the optional main-session hook, change only its `SessionStart` matcher to `^(startup|resume)$`. This repeats both repository updates, including forced checkout.

Hermes `on_session_open` covers local creation and reopen, while `on_session_start` covers the first turn, including messaging sessions. To run on local reopen, replace the event instead of registering both. Open callbacks can continue after the next turn's wait limit, so check readiness before diagnosis. See [Hermes session-open behavior](https://hermes-agent.nousresearch.com/docs/user-guide/features/hooks#on_session_open).

The hook does not start forwards or register or refresh MCP clients. Use [Hermes MCP configuration](hermes-grafana-mcp.md) and the [diagnosis toolkit](../diagnose_toolkit.md#logs-metrics-and-traces) for connection setup and recovery.

## Troubleshooting

- **Codex hook missing or skipped:** verify project trust, hook approval, and that hooks are enabled. For subagents, match the exact custom agent `name`, not a task label or the parent's CLI profile. Check for duplicate hook definitions if one event runs startup twice; a main diagnose startup followed by a diagnose subagent spawn intentionally runs it once for each event.
- **Hermes hook missing:** verify the active profile, event spelling, and consent. An unsupported event requires an agent version supporting it; `on_session_start` and `on_session_open` have different timing.
- **Hermes runs nothing in this repo:** check the payload's working directory and replace the wrapper's `OPS_ROOT` placeholder. Both must identify this checkout on the execution host.
- **Timeout or startup failure:** inspect the hook error or Hermes startup log, resolve the reported configuration, password-file, or Git error, then rerun manually before diagnosis. Concurrent sessions can consume hook timeout while waiting on the startup lock.
- **Desktop or remote session lacks tools:** configure PATH, and repository paths on its execution host. On macOS, include Homebrew's bin directory so the hook can find `flock`.

## Cleanup

Remove only this hook entry from the agent configuration, or disable it in Codex's hook browser. Remove the Hermes wrapper when no profile references it. Preserve unrelated hooks and existing Grafana forwards; disabling startup does not stop them or undo repository updates.
