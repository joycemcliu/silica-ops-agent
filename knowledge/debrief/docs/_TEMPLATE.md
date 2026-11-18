---
incident: <incident file name without .md>
date: YYYY-MM-DD
store: <code>
# Example: "codex 019abcde-1234-7000-8000-123456789abc 192.168.1.10"
session_id: "<AI agent, e.g. codex/hermes> <session ID/thread ID/conversation ID> <PC IP>"
---

<!-- Writing instructions:
- Keep it short and avoid repeating the incident report. Write none for empty sections instead of padding.
- Record what helped, what slowed progress, wrong assumptions and missing information.
- Suggest specific toolkit improvements based on observed problems.
- Capture reusable platform/diagnosis knowledge with evidence; distinguish confirmed facts from inferences.
-->

## Time sinks

- <step> | <est./measured minutes> | <what would have removed it>

## Asked the user, should have known

- <question>

## Wrong assumptions

- Assumed X, actually Y. Evidence: <command/query>

## Toolkit friction

- [high|med|low] [open|partial|improved|unchecked] [<path or tool>] <what you saw> [evidence refs]\
  Proposal: <one line action>\
  Status checked: YYYY-MM-DD — <what changed or remains outstanding; supporting evidence; scope/validation performed>.\
  Remaining: <unfinished work or validation; none when complete>.

<!-- Toolkit-friction instructions:
- Label every item with severity (high, med, low) and improvement status, separately.
- open: checked and still outstanding.
- partial: some friction is addressed, with a specific implementation or validation gap.
- improved: implemented and validated for the stated scope.
- unchecked: current improvement status has not been verified; use when evidence is insufficient.
- Add a dated status check with supporting evidence and the scope checked. Distinguish repository inspection
  from runtime validation. Name remaining work or validation; write none when complete.
- A proposal or documentation alone does not establish a working implementation. Documentation-only improvements
  may be marked improved when the documentation itself meets the proposal; state that scope explicitly.
- Preserve original incident observations, evidence and proposals when updating statuses. Reassess only when
  requested or new evidence is available; do not treat an old status as a fresh check.
-->

## Blind spots

- <what could not be observed: missing logs, labels, metrics>

## Platform facts learned

<!-- No evidence means mark it `inferred`. -->

| Fact | Evidence | verified / inferred |
| ---- | -------- | ------------------- |

## Platform knowledge proposals

Optional. Omit this section when there is no useful proposal. Follow the [platform guidelines](../../platform/AGENTS.md).

### <Proposal title>

- Action: <create / update>
- Document: <platform/docs/<slug>.md>
- Proposed knowledge: <What to add or correct>
- Evidence: <Source or observed result>

## What helped

- <tool/query/doc> | <time saved or why it worked>
