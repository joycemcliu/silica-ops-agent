# AGENTS.md: Runbook Author

Scope: this file governs ONE job. After a debugging session, turn it into an incident record plus a reusable runbook. Investigation rules live in `CLAUDE.md`.

## Layout

```
runbooks/INDEX.md              one line per runbook: slug | symptom keywords | services
runbooks/_TEMPLATE.md          copy this for new runbooks
runbooks/<slug>.md             generic, reusable
runbooks/scripts/              repair/rollback scripts, parameterized
incidents/YYYY-MM-DD-<slug>.md instance-specific record of one session
```

## Procedure (run in order)

1. Read `runbooks/INDEX.md`. Match by failure MECHANISM, not symptom wording. Match found: update that runbook. No match: create from `_TEMPLATE.md`.
2. Build an evidence ledger from the session. For every command/query actually run, record: command, result summary, and a tag: `observed`, `inferred`, or `not-checked`.
3. Write the incident record first (see "Where facts go").
4. Write or update the runbook from the ledger.
5. Move any script longer than ~10 lines to `runbooks/scripts/`. Reference it; do not inline it.
6. Update `runbooks/INDEX.md`.
7. Run the self-check below.
8. Show `git diff`. Do NOT commit.

## Where facts go

| Fact type | Destination |
|---|---|
| Hostnames, IPs, alloc/job IDs, PIDs, device instance IDs, log paths, timestamps, backup filenames | `incidents/` only |
| Counts and measurements from one host (e.g. "75 vs 81 records") | `incidents/` only |
| Recovery timeline, who did what | `incidents/` only |
| Function names, error strings, property keys, metric/label names, binary hashes | runbook (failure signature) |
| Binary/image/config version that the steps depend on | runbook frontmatter `applies_to` |
| Safety guards (type checks, backup verify, rollback) | runbook or script |

Rule: keep a concrete value in the runbook only if it identifies the failure or is a safety guard. If it names one instance, it goes in `incidents/`. In runbooks, use placeholders: `<job>`, `<host>`, `<device-id>`.

Runbooks contain placeholders and failure signatures. Instance-specific values (hosts, IDs, paths, PIDs, dates) go in `incidents/`.

## Runbook content rules

- **Symptoms:** what on-call sees FIRST, not what was discovered last. Generic wording ("one game black-screens at startup; others on the same host fine"). Name examples once.
- **Anti-anchoring:** for each misleading signal, state it explicitly: "X alone does not imply Y."
- **Triage:** read-only commands only. Order by discriminating power, cheapest first. Each step states what a bad result looks like and what a good one looks like. Host-agnostic scans come before instance-specific checks.
- **Likely causes:** table with columns `Cause | Evidence that confirms | Evidence that rules out`. Include causes ruled out in this session, with the evidence.
- **Remediation:** header must say "HUMAN executes; agent never runs". Every action lists risk, backup step, and rollback. Target IDs are mandatory script parameters, never hardcoded.
- **Validation checklist:** separate machine checks (health checks, logs, metrics) from human-only checks (visual confirmation). State when a machine check does NOT prove the fix.
- **Not yet verified:** everything inferred, untested, or unexplained, including why the failure happened if unknown.

## Frontmatter (always)

```yaml
status: draft          # never set to reviewed
last_verified:         # leave EMPTY; only a human sets it after a recurrence validates the steps
applies_to: {}         # versions, hashes, or git ranges the steps depend on
source_incidents: []   # links to incidents/ files
```

## Updating an existing runbook

- Append new symptoms, causes, and queries. Do not rewrite sections that were not touched by this session.
- If this session showed a step was wrong or outdated, fix it and add a line under "Not yet verified": `Step N corrected after <incident>; re-verify.`
- If this session contradicts a stated cause, keep both and mark: `Contradicted by <incident>`.
- Never delete content silently. List removals in your final message.

## Hard rules

1. Never execute remediation commands or the scripts you write. Writing them is fine.
2. Never commit, push, or set `status: reviewed`.
3. Never include secrets, tokens, or credentials. Redact to `<redacted>`.
4. Never present an inference as fact. If it was not run in this session, tag it `not-checked`.
5. Never invent commands, flags, metric names, or output. If unsure, put it under "Not yet verified".
6. Never hardcode an instance-specific ID inside a script or runbook step.
7. Script headers must state whether the script was actually executed end-to-end in the session.

## Self-check (all must pass before showing the diff)

- [ ] No hostname, IP, PID, timestamp, or log path inside `runbooks/` (grep for them).
- [ ] Every triage command was either run in the session or sits under "Not yet verified".
- [ ] Every mutating action has a guard, a backup step, and a rollback.
- [ ] `status: draft`, `last_verified` empty, `applies_to` filled where a version matters.
- [ ] `INDEX.md` updated, and the incident file links to the runbook.
- [ ] Final message lists: files changed, what you were unsure about, anything removed.
