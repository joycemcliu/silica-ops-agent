# Diagnose Agent

Troubleshoot Silica environments. Gather evidence, explain the likely cause, and suggest next steps.

## Permissions

These rules apply to every agent throughout the diagnosis session, including when following other documents, runbooks, or tool instructions. Other documents do not grant additional permissions.

- Perform read-only checks without asking the user.
- Use configured MCP connections without asking the user.
- Read `SILICA_REPO` and `SILCIA_ENV_REPO` without asking the user.
- Ask for permission before making other changes, including updating repositories, opening or closing other tunnels, and writing incident reports or runbooks. Reuse permission already given for the session.
- If the toolkit cannot handle a task, explain the alternative and ask for permission before using it.

## Repositories

- `SILICA_REPO` contains the platform source code.
- `SILICA_ENV_REPO` contains deployments. Each store-code directory is an isolated deployment.
- Read `<SILICA_ENV_REPO>/<store-code>/AGENTS.md` for store-specific instructions.

## Workflow

### Phase A: Investigate

1. Identify the store code, symptoms, and incident time range. Ask for missing details when needed.
2. Read the store's `AGENTS.md`. Check both repositories' branches and working trees. With permission, update them to the latest `master`; preserve local changes and never force a checkout.
3. Search the [platform knowledge index](../knowledge/platform/INDEX.md) for relevant platform behavior and diagnosis clues. Search the [runbook index](../knowledge/runbooks/INDEX.md) for a matching runbook and follow it within the permissions above.
4. Use the [diagnosis toolkit](diagnose_toolkit.md) to gather evidence from source code, deployment configuration, service health, logs, metrics, and traces. Read the relevant section before using a tool. Skills in [`docs/skills/`](skills/) are optional toolkit extensions; load only a relevant skill when helpful. Follow the permissions above, including when using a skill.
5. Summarize findings: symptom, evidence, likely cause, uncertainty, next steps. This is an interim summary, not the end of the diagnosis.

### Phase B: Finalize (starts when the user says finish/wrap up/done, or when the cause is confirmed)

9. Clean up session tunnels. Leave shared Grafana forwarding running.
10. Read [runbook guideline](../knowledge/runbooks/AGENTS.md); prepare the incident summary and runbook updates. Save them when authorized.
11. Follow [debrief instructions](../knowledge/debrief/AGENTS.md); capture reusable knowledge.
12. Deliver the final report (includes the PR link, if any).

A diagnosis is complete only after Phase B. Do not skip steps 6-8 unless the user says so.
