---
title: ATWIECOL JetStream quorum loss prevented the room 3 player 1 launch
incident_date: 2026-11-17
incident_time_range: "15:19:03–21:38:25 UTC sustained consumer stall; reported around 20:14 UTC"
timezone: UTC
store: ATWIECOL
runbook: ../runbooks/docs/sata-io-jetstream-launch-failure.md
closure_date: 2026-11-18
---

## Report, impact and scope

Nomad job `experience/h3-p1` was missing around 20:14 UTC. The preceding launch created the room server and players 2 through 6. The room 3 player 1 launch was missing. Broader analysis covered recurring broker warnings around the version changes and separate storage failures.

## Instance details

| Item              | Value                                                                                               |
| ----------------- | --------------------------------------------------------------------------------------------------- |
| Broker cluster    | `infra/nats`, NATS 2.15.2 on `master-1`, `master-2`, and `master-3`                                 |
| Affected consumer | `experience_dot_launch_dot_command_dot_h3-p1__experience_dot_launch_dot_command` on stream `silica` |
| Sources           | Production Grafana `silica-loki` and `silica-mimir`, broker monitoring endpoints, and SILICA_REPO   |
| Related incident  | [Nov 14 ATWIECOL SATA and Unity launch incident](2026-11-14-atwiecol-sata-io-unity-launch.md)       |

## Evidence ledger

| ID  | Tag         | Command/query or evidence source                                                                                                                         | Result summary                                                                                                                                                                                                                                                                                              |
| --- | ----------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E01 | observed    | Loki `{cluster="ATWIECOL",job="experience-conductor/commands"}` filtered for the job and consumer context                                                | At 13:12:54 the conductor deleted the preceding job while terminating `atwiecol-261117-T3-132619`. Source `infras/nomad/service.go` uses `purge=true`. Later lookups returned 404.                                                                                                                          |
| E02 | observed    | Loki conductor events and commands correlated by launch message ID `50a444af-7f8b-4332-a77b-d8907860210f`                                                | Launch for `atwiecol-261117-T3-205148` published at 19:52:08.767. Nomad created p0 and p2–p6 within the same second. p1 logged subscription attempts without launch handling or creation through 20:20.                                                                                                     |
| E03 | observed    | Loki `{cluster="ATWIECOL",job="infra/nats"}` filtered for the exact p1 launch consumer                                                                   | Short quorum-loss warnings preceded the sustained episode. At 12:03:38 `master-2` reported the replica not current with `monitor goroutine not running`. Sustained warnings began at 15:19:03 and continued through 21:37:36. `master-3` logged a leader at 21:38:25.                                       |
| E04 | observed    | Loki NATS Raft group search around 13:32 and 15:19                                                                                                       | `master-2` and `master-1` paused quorum participation about 100,000 entries behind for group `C-R3F-sfZW0uEu`. The recovered p1 consumer reported a different group, `C-R3F-WSGewCJJ`. The retained logs did not establish a historical mapping.                                                            |
| E05 | observed    | Per-broker read-only `/jsz?accounts=true&streams=true&consumers=true&raft=true`, `/healthz?details=true`, and `/varz`                                    | At about 02:37 on Nov 18, leader `master-3` showed both p1 replicas current and no pending messages or acks. Full health still reported other local consumer errors across the brokers.                                                                                                                     |
| E06 | observed    | Loki conductor commands and `{cluster="ATWIECOL",job="experience/h3-p1"}`                                                                                | The p1-only launch for `atwiecol-261117-T3-223409` created the job at 21:41:28. The allocation logged a Unity start attempt on `spc31`. The conductor deleted the job at 22:04:27 while terminating the session.                                                                                            |
| E07 | observed    | Loki kernel and NATS write-error/stream quorum queries                                                                                                   | At 23:19:57 Nov 16 and 01:28:48 Nov 17, `master-1` disk timeouts and Raft write failures coincided. Stream quorum warnings followed about 33 seconds and under one second later. The overnight NATS tasks stayed below 381 MiB. Nov 12 also had Raft write errors during the 2.14.9 window.                 |
| E08 | observed    | Loki counts of `has NO quorum` over UTC days, broker startup version logs                                                                                | Nov 10–11 had 166–300 lines per day. Nov 12–17 had 3,907–14,244 per day. Of Nov 17's 3,907 warnings, 3,900 named consumers and 7 named the stream. Repeated lines can describe one stall. Broker logs place 2.14.9 at roughly 00:08–02:20 Nov 12 and 2.15.2 afterward.                                      |
| E09 | observed    | Mimir `nomad_client_allocs_memory_usage`, `nomad_client_allocs_memory_max_allocated`, and `nomad_client_allocs_cpu_total_percent` for the NATS main task | Matched Tuesday windows compared Nov 10 with Nov 17. Per-broker memory medians rose from 175–216 MiB to 416–500 MiB. CPU medians moved in different directions. At 15:19, masters 1 and 2 were about 499.6–499.7 MiB of 500 MiB.                                                                            |
| E10 | observed    | Mimir sampled disk completion latency and host CPU; Loki `systemd-journal`, broker lifecycle and route queries near onset                                | Mean disk write latency at 15:19 was roughly 0.7–1.2 ms across the masters. The queried onset window showed no matching storage error, broker restart, or route close. A brief earlier I/O wait spike on `master-2` had subsided.                                                                           |
| E11 | observed    | SILICA_REPO commit `027a7e43a`, Terraform/Nomad render check, replica fixture, and disposable three-broker NATS compatibility test                       | JSON advisories and opt-in per-broker replica and cgroup sampling are implemented. The interval defaults to 60 seconds and accepts positive whole seconds. The health check that controls Nomad restarts remains enabled-only.                                                                              |
| E12 | not-checked | Live deployment and operational validation                                                                                                               | No retained per-replica advisory was found for the affected election. The later SSH attempt to map the Raft group failed authentication. Exporter series were absent in the ATWIECOL Grafana query. Live cgroup records, exporter ingestion, Grafana alert delivery, and Unity readiness remain unverified. |

## Findings

- **Confirmed launch failure.** The prior job was removed during termination. The p1 consumer stalled and the next launch did not reach its job creation handler. Other room participants received the same command and their jobs were created.
- **Storage disruption observed elsewhere in the store.** Disk timeouts and Raft write errors repeatedly occurred together. The timing strongly supports storage as a contributor to the overnight stream quorum incidents. The affected voting peers for each event and the failing device component were not isolated.
- **Afternoon trigger unresolved.** Elevated memory usage is a plausible contributor. The evidence does not establish memory pressure, a version regression, or which two replicas stopped participating in the affected consumer.

## Actions and recovery timeline

| UTC                       | Action or event                                                  | Result                                                                                               |
| ------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Nov 17, 21:38:25          | JetStream elected the consumer leader                            | Launch consumer could make progress again. What enabled the election is unknown.                     |
| Nov 17, 21:41:28–22:04:27 | Conductor handled a later room 3 p1 launch and terminate command | Nomad created the job and later removed it during termination.                                       |
| Nov 18                    | Read-only broker checks and monitoring implementation            | Replica state verified after recovery. Code and local tests completed. Temporary SSH helpers exited. |

## Outcome and remaining work

Diagnosis closed. Delivery and Nomad job creation recovered for a later launch. The exact trigger for the Nov 17 afternoon quorum loss remains open. Prioritize the recurring storage errors on `master-1` and review the ATWIECOL monitoring rollout. Verify Alloy exporter discovery, Loki advisories and replica/cgroup samples, and Grafana alert delivery after rollout. No remediation, production deployment, or alert creation was performed in this diagnosis.
