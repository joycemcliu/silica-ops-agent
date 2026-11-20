---
incident: 2026-11-17-atwiecol-jetstream-quorum-loss
date: 2026-11-18
store: ATWIECOL
session_id: "codex 01a1ec74-824c-7543-b8b6-945d6f693ad7"
---

[Incident record and evidence ledger](../../incidents/2026-11-17-atwiecol-jetstream-quorum-loss.md)

## Time sinks

- Broad Loki searches returned unrelated player logs. Filtering by the exact consumer, conductor context and Nomad job made the timeline clear.
- The initial SSH probe used loopback. The broker monitoring port was available on the LAN interface.

## Asked the user, should have known

- None.

## Wrong assumptions

- The first warning in the narrow incident window was not the first loss. A wider search found earlier short elections and the sustained stall beginning at 15:19 UTC.
- The Raft backlog near onset looked related. The historical group ID could not be mapped to the p1 consumer.

## Toolkit friction

- [high] [partial] [production Grafana] No retained advisory with affected replica state was found. [E03–E05, E11–E12]\
  Proposal: Ingest JSON advisories and sample per-broker replica and cgroup state.\
  Status checked: 2026-11-18. SILICA_REPO contains the implementation. Rendering, replica fixture and Docker compatibility checks passed.\
  Remaining: Verify ATWIECOL ingestion, live memory events and alert delivery after rollout.
- [med] [open] [service monitoring] Expected exporter metrics were absent in the ATWIECOL Grafana query. [E12]\
  Proposal: Verify discovery, target health and metric labels before writing exporter alerts.\
  Status checked: 2026-11-18. Repository config inspected and Grafana queried.\
  Remaining: Identify the scrape or labeling gap in production.

## Blind spots

- Historical per-replica voting state and task cgroup pressure at onset.
- The election recovery trigger and Unity readiness.

## Platform facts learned

| Fact                                                                          | Evidence                                                                                                                | verified / inferred |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ------------------- |
| A healthy stream can publish a launch that only one consumer fails to handle. | E02–E03 correlate one command with all room jobs except p1.                                                             | verified            |
| The NATS monitor warning reflects a local internal health flag.               | E03 and the [NATS health check](https://github.com/nats-io/nats-server/blob/v2.15.2/server/jetstream_cluster.go#L1106). | verified            |

## What helped

- Comparing the same launch across players isolated the failing hop.
- Comparing broker memory and kernel logs at two separate onsets distinguished the overnight storage episode from the afternoon stall.
