---
incident: 2026-11-03-usbaymkt-render-consumer-stalled
date: 2026-11-06
store: USBAYMKT
session_id: null # Original diagnosis harness session ID was not retained in the incident.
---

Source: [incident and evidence ledger](../../incidents/2026-11-03-usbaymkt-render-consumer-stalled.md). This debrief reorganizes retained evidence; no production checks were rerun during authoring. Dates follow the recorded incident/recovery, not this prose edit.

## Time sinks

- Access retries, broad log searches, rotated files and client discovery slowed diagnosis (E14/E16/E24/E26). Duration was not measured; use documented access, fresh file listings and targeted queue APIs earlier.

## Asked the user, should have known

- None established by the retained record; do not invent avoidable questions.

## Wrong assumptions

- Zero pending and healthy workers did not establish an empty workload or useful delivery (E03/E04/E09–E12).
- Follower lag did not establish cluster-wide failure; reconnect code and leadership-change logs did not prove deadlock (E08/E09/E17).
- Empty filtered output could reflect a missing rotated file; replayed startup logs did not establish a new restart, power loss or actor identity (E14/E19–E22).

## Toolkit friction

- [high] [queue diagnostics] Videos stayed queued while workers looked healthy and the consumer reported zero pending; several manual API checks were needed to find the mismatch. [E03/E04/E09–E12]\
  Proposal: Add one read-only command under `scripts/` that compares video task progress, retained matching messages and consumer delivery positions, and flags disagreements.

- [high] [SILICA_REPO/apps/monitoring/terraform-module] Video tasks stopped progressing while sampled service health checks still passed. [E03/E04]\
  Proposal: Add an alert for queued tasks that stop progressing, using verified task/exporter data and checking that healthy backlogs do not trigger it.

- [med] [callers of scripts/store-port-forward-ssh.sh] A missing rotated log returned plain text and other downloads timed out; empty filtered output could be mistaken for no matching logs. [E14]\
  Proposal: Report missing files, failed downloads, invalid responses and partial results explicitly; only report no matching entries after a successful, complete read.

- [med] [scripts/store-port-forward-ssh.sh] SSH readiness timed out when kubectl advertised an IPv6 listener but SSH expected IPv4. [E24]\
  Proposal: Make forwarding and readiness checks use the same IPv4 address as SSH, and verify occupied-port and IPv6-only cases without changing pre-existing tunnels.

## Blind spots

- Exact broker defect, historical cleanup actor/timing, power evidence, deployed binary metadata, and final completion/upload/visual correctness remain unchecked or unresolved (E07/E18/E22 and incident outcome).
- Full inline request clients and approvals remain in the original conversation; the incident groups command families. Original session ID and time spent were not retained.

## Platform facts learned

Statuses refer to evidence recorded in the source incident, not checks run during this edit.

| Fact                                                                                                                                  | Evidence          | verified / inferred                                      |
| ------------------------------------------------------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------- |
| Runnable queued children can hide behind aggregate Pending; retained subject sequences can contradict zero pending                    | E03/E09–E12/E15   | verified                                                 |
| Metadata, stream and consumer leaders can differ; use the object's leader                                                             | E08/E09           | verified                                                 |
| One consumer-only transfer restored delivery and child progress without configuration reset                                           | Recovery timeline | verified; applicability to other incidents inferred      |
| Embedded event time distinguishes replayed startup lines from new starts; Nomad interruption does not identify a person or power loss | E19–E22           | verified limitation; attribution inferred                |
| Shared event source is bundled from the renderer checkout, without independent binary attestation                                     | E07               | verified source behavior; executable provenance inferred |

## Platform knowledge proposals

- Created [video render queue delivery](../../platform/docs/flows/nats-video-render-queue-delivery.md) from E03/E06–E12/E15/E17 and recovery evidence; it covers delivery boundaries, leadership interpretation and evidence limits. No additional live verification was performed.

## What helped

- Per-subject stream APIs and independent consumer-info reads discriminated the failure (E09/E11/E12).
- Version-matched source inspection separated intended reconnect behavior from speculation (E06/E07).
- `scripts/grafana-mcp-forward.sh` used kubectl, automatic reconnect and readiness checks; start/status reachability and stop/status cleanup were observed. Bounded Loki queries used discovered labels (E23/E24 and recovery timeline). No broad reliability or measured time-saving claim was established.
- The prior session reported saving diagnosis-skill guidance on leaders, per-subject APIs and evidence interpretation; this was procedural memory, not a new repository feature or recovery script.

Future Python commands must use the shared interpreter specified by the root `AGENTS.md`. The incident preserves historical `python3` invocations rather than rewriting what ran.
