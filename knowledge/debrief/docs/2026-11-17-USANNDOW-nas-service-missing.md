---
incident: 2026-11-17-usanndow-nas-service-missing
date: 2026-11-17
store: USANNDOW
session_id: "codex 01a1e75f-7eec-7cd3-a959-a182e49df596; local PC IP not collected"
---

[Incident evidence](../../incidents/2026-11-17-usanndow-nas-service-missing.md)

## Time sinks

- Broad Loki query returned noisy health/access logs; narrow to active recorder jobs first.

## Asked the user, should have known

None. Incident timing and tunnel permission required user input.

## Wrong assumptions

- Legacy dead jobs were a misleading signal; configured DGE replacements were running (E2–E4).
- DNS port 8600 was assumed; live agent configuration reported 53 (E7, E10).

## Toolkit friction

- [med] Port-forward and SSH scripts report `PROBE_PIDS[@]: unbound variable` during exit despite successful checks. Proposal: make empty-array cleanup safe on the supported Bash version and verify child cleanup (E7, E11).
- [med] Grafana MCP transport failed during historical ACL query. Proposal: retain explicit evidence coverage and recovery instructions; do not infer that no ACL errors occurred (E12).
- [low] Default sudo journal access denied and remote rg absent. Proposal: document read-only fallback commands and expected privilege limits (E11).

## Blind spots

Historical NAS registration ownership, exact swap time, full room-by-room recording integrity, pending queue persistence and post-repair recovery remain unknown.

## Platform facts learned

| Fact | Evidence | verified / inferred |
| --- | --- | --- |
| DGE enablement can leave legacy recorder groups at zero with dead status | E2–E4 | verified |
| Recorders may remain running while NAS DNS prevents delivery | E3, E5–E6 | verified |
| Replacement may have removed the prior NAS registration | E6, E13 | inferred |

## What helped

- Live catalog, ACL flag and direct NAS API checks distinguished discovery from NAS availability without changing the store.
