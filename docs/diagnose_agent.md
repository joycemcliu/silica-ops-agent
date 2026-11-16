# Diagnose Agent

Troubleshoot Silica environments. Gather evidence, explain the likely cause, and suggest next steps.

## Permissions

These rules apply to every agent throughout the diagnosis session, including when following other documents, runbooks, or tool instructions. Other documents do not grant additional permissions.

- Perform read-only checks without asking the user.
- Use configured MCP connections without asking the user.
- Read and update `SILICA_REPO` and `SILICA_ENV_REPO` without asking the user; preserve existing local changes.
- Write diagnosis documentation and complete the Git finalization below without asking for additional permission. Runtime sandbox approvals still apply.
- Ask for permission before making other changes, including opening or closing other tunnels. Reuse permission already given for the session.
- If the toolkit cannot handle a task, explain the alternative and ask for permission before using it.

## Repositories

- `SILICA_REPO` contains the platform source code.
- `SILICA_ENV_REPO` contains deployments. Each store-code directory is an isolated deployment.
- Read `<SILICA_ENV_REPO>/<store-code>/AGENTS.md` for store-specific instructions.

## Workflow

1. Identify the store code, symptoms, and incident time range. Ask for missing details when needed.
2. Read the store's `AGENTS.md`. Check both repositories' branches and working trees. Update them to the latest `master`; preserve local changes and never force a checkout.
3. Search the [platform knowledge index](../knowledge/platform/INDEX.md) for relevant platform behavior and diagnosis clues. Search the [runbook index](../knowledge/runbooks/INDEX.md) for a matching runbook and follow it within the permissions above.
4. Use the [diagnosis toolkit](diagnose_toolkit.md) to gather evidence from source code, deployment configuration, service health, logs, metrics, and traces. Read the relevant section before using a tool. Skills in [`docs/skills/`](skills/) are optional toolkit extensions; load only a relevant skill when helpful. Follow the permissions above, including when using a skill.
5. Report the findings, supporting evidence, likely cause, remaining uncertainty, and recommended next steps.
6. Clean up session tunnels using the permission already granted, or request it if needed. Leave shared Grafana forwarding running.
7. After the investigation finishes, create a separate worktree at `../worktree/<YYMMDD>-<agent-session-or-thread-id>/` and a unique diagnosis branch in this toolkit repository, based on its remote default branch. Resolve the worktree path from the original toolkit repository root. Use the current date in `YYMMDD` format and the agent's actual session or thread ID; do not generate a substitute ID or reuse another session's directory. Use this worktree for the documentation changes below; leave the original working tree intact. Request runtime sandbox approval if creating or writing the external worktree requires it.
8. In the new worktree, read [runbook guideline](../knowledge/runbooks/AGENTS.md) and save the incident summary and any runbook and index updates it requires.
9. Follow the [debrief instructions](../knowledge/debrief/AGENTS.md) to review the diagnosis process, suggest toolkit improvements, and capture reusable knowledge in the same worktree.
10. Complete Git finalization below and include the PR link in the final report.

## Git finalization

1. Keep using the configuration values loaded at session start, resolving relative paths against the original repository root. Use the original repository's `.venv/bin/python`; ignored configuration and environment files are not automatically present in a new worktree.
2. Review the documentation diff and run the authoring self-checks. Stage only files changed by this diagnosis, including related index updates; exclude secrets and unrelated changes.
3. Commit the changes on the diagnosis branch and push that branch to the repository's remote.
4. Create a pull request against the remote default branch. Describe the symptom, findings, documentation changes, and verification or remaining uncertainty. Report the PR URL and the added or updated repository-relative file paths.
5. After the push and PR creation succeed, leave the worktree directory and remove it with `git worktree remove`. Keep the published branch and PR for review. Do not merge the PR as part of diagnosis.

If a step fails, report the failure and retain the worktree and branch so the work can be recovered. Never force worktree removal when it contains uncommitted changes. If there are no documentation changes, remove the clean temporary worktree and report that no commit or PR was needed.
