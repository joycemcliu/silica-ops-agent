# Runbook authoring instructions

These instructions govern authoring and updating reusable runbooks in this directory and their associated incident records. After a debugging session, follow [author-incident-runbook](skills/author-incident-runbook.md) to create or update both artifacts.

For troubleshooting and diagnosis, follow the [Diagnose Agent instructions](../../docs/diagnose_agent.md).

## Layout

Paths below are relative to `knowledge/`.

```text
runbooks/INDEX.md                           one line per runbook: slug | symptom keywords | services
runbooks/skills/author-incident-runbook.md  authoring workflow
runbooks/docs/_TEMPLATE.md                  copy this for new runbooks
runbooks/docs/<slug>.md                     generic, reusable
runbooks/scripts/                           repair/rollback scripts, parameterized
incidents/YYYY-MM-DD-<slug>.md              instance-specific record of one session
```

## Hard rules

1. Never execute remediation commands or the scripts you write. Writing them is fine.
2. Never commit, push, or set `status: reviewed`.
3. Never include secrets, tokens, or credentials. Redact to `<redacted>`.
4. Never present an inference as fact. If it was not run in this session, tag it `not-checked`.
5. Never invent commands, flags, metric names, or output. If unsure, put it under "Not yet verified".
6. Never hardcode an instance-specific ID inside a script or runbook step.
7. Script headers must state whether the script was actually executed end-to-end in the session.
