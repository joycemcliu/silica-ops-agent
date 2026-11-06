---
title:
incident_date:       # YYYY-MM-DD
incident_time_range: # HH:mm:ss to HH:mm:ss, use timezone below
timezone:            # e.g. Asia/Hong_Kong
store:               # store-code eg. HKCWBMID
runbook:             # relative path to reusable procedure, if available
---
## Report, impact and scope
- What was reported, who/what was affected, and any scope corrections or unknowns

## Instance details
| Item | Value |
| --- | --- |
| Environment / service | |
| Host / job / task / allocation | |
| Relevant logs / artifacts | |

## Evidence ledger
- Investigation scope: repository inspection, live diagnostics, or retained session records
- Use `observed`, `inferred`, or `not-checked`; identify missing invocations and omit secrets

| Tag | Command/query or evidence source | Result summary |
| --- | --- | --- |

## Findings
- Confirmed mechanism or suspected cause → supporting evidence and remaining uncertainty
- The agent may use a table instead when it makes the findings clearer
- The agent may combine this section and the actions and recovery timeline into one timeline table when clearer; include findings, supporting evidence, actions and results as applicable

## Actions and recovery timeline
| Timestamp | Action actually taken | Result | Backup / rollback reference (if relevant) |
| --- | --- | --- | --- |

## Outcome and remaining work
- Recovery confirmed and its scope, or current unresolved status
- Checks not performed, unanswered questions, and follow-up work
