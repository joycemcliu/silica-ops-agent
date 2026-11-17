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

- [med] [open] [Store forwarding/SSH] Port-forward and SSH scripts report `PROBE_PIDS[@]: unbound variable` during exit despite successful checks.
  Proposal: make empty-array cleanup safe on the supported Bash version and verify child cleanup (E7, E11).\
  Status checked: 2026-11-17 — Both [forwarding](../../../scripts/store-port-forward.sh) and [SSH](../../../scripts/store-port-forward-ssh.sh) helpers still expand empty `PROBE_PIDS` arrays under `set -u`. Repository inspection only; no child-cleanup runtime check.\
  Remaining: Fix supported-shell empty-array cleanup and verify session-owned child cleanup.

- [med] [improved] [Grafana MCP] Grafana MCP transport failed during historical ACL query.
  Proposal: retain explicit evidence coverage and recovery instructions; do not infer that no ACL errors occurred (E12).\
  Status checked: 2026-11-17 — Rechecked [store forwarding](../../../scripts/store-port-forward.sh): detached workers retry disconnects every 3 seconds and rediscover replacement Nomad pods. All 4 forwarding regression tests passed using fake tools and loopback connections. The [toolkit](../../../docs/diagnose_toolkit.md#logs-metrics-and-traces) documents recovery and reporting persistent MCP failure. Per user direction, improved covers store reconnection and explicit evidence limitations, not repair of Grafana MCP transport. Historical ACL coverage and live MCP queries were not revalidated.\
  Remaining: None in the accepted scope. MCP failures remain unresolved and are excluded from this follow-up; the historical ACL coverage gap remains.

- [low] [unchecked] [Remote Linux commands] Default sudo journal access denied and remote rg absent.
  Proposal: document read-only fallback commands and expected privilege limits (E11).\
  Status checked: 2026-11-17 — The original incident establishes the denied journal access and absent remote `rg`; a complete current fallback-command/privilege reference was not verified.\
  Remaining: Verify and document read-only fallback commands and privilege limits without assuming remote tools exist.

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
