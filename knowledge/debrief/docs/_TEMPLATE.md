---
incident: <incident file name without .md>
date: YYYY-MM-DD
store: <code>
# Example: "codex 019abcde-1234-7000-8000-123456789abc 192.168.1.10"
session_id: "<AI agent, e.g. codex/hermes> <session ID/thread ID/conversation ID> <PC IP>"
---

## Time sinks

- <step> | <est./measured minutes> | <what would have removed it>

## Asked the user, should have known

- <question>

## Wrong assumptions

- Assumed X, actually Y. Evidence: <command/query>

## Toolkit friction

- [high|med|low] [<path or tool>] <what you saw> [evidence refs]\
  Proposal: <one line action>

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
