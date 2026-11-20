---
title: SATA I/O stalls disrupt JetStream and Unity launch
slug: sata-io-jetstream-launch-failure
services: [nats, experience-conductor, session-server, unity]
tags: [sata, storage, jetstream, quorum, unity, launch]
status: reviwed
last_verified: 2026-11-18
applies_to: { nats: "2.15.2 for the health-check and Raft behavior" }
source_incidents:
  - ../../incidents/2026-11-14-atwiecol-sata-io-unity-launch.md
  - ../../incidents/2026-11-17-atwiecol-jetstream-quorum-loss.md
---

## Symptoms

Unity fails to appear across rooms or player/server PCs. Silica remains Checking and later reports Error. Launch services may restart repeatedly while Nomad jobs appear running.

A single player job can also be missing while the same launch creates the other room jobs. An earlier termination can legitimately purge the old job. Trace what prevented the new job from being created.

Running allocations and SSH access alone do not imply useful command delivery. Healthy NAS status does not establish health of a local disk backing NATS. A SMART PASSED result alone does not exclude host-observed command timeouts. `WRITE FPDMA QUEUED` identifies an affected queued-write path; it does not prove NCQ is the root defect.

## Triage (read-only, in order)

The query/command shapes below were executed with incident-specific substitutions. Discover actual datasource, labels and device/mount identities first; use explicit UTC bounds. See the [launch flow](../../platform/docs/flows/unity-launch-command-delivery.md) for source boundaries.

1. **Correlate launch-service and queue failures.** Query Loki:

   ```logql
   {cluster="<CLUSTER>",job=~"experience-conductor.*"} |~ "panic:|leadership change|failed to start queue"
   {cluster="<CLUSTER>",job="infra/nats"} |~ "input/output error|NO quorum|WriteFullState"
   ```

   Bad: repeated queue-recovery panics plus persistence errors or quorum loss. Good: launch commands are handled and queue progress continues; leadership changes alone are insufficient. Missing/truncated logs are inconclusive, not a healthy result. In the inspected broker version, WriteFullState warnings time state preparation before the file write; they are not direct write-duration measurements. A repeated stream-not-current warning can retain an earlier Raft write error and does not prove a new sync attempt.

2. **Check the storage layer at the same time.** Query `{cluster="<CLUSTER>",job="systemd-journal"} |~ "DID_TIME_OUT|I/O error|failed command|hard resetting link"`. On each confirmed relevant host, inspect `journalctl -k --since '<UTC-START>' --utc --no-pager --grep='failed command|hard resetting|exception Emask|DID_TIME_OUT|SError|AER:' -n 100`. Bad: write timeouts, frozen command queues and SATA resets aligned with application failures. Good: no such errors in sufficiently retained logs and normal completion latency; limited log coverage remains inconclusive.

3. **Identify the actual backing device before blaming hardware.** Use `hostname`, `lsblk -o NAME,TYPE,SIZE,FSTYPE,MOUNTPOINT,MODEL,TRAN`, `findmnt -T <nats-host-directory>` and `df -h /`. Inspect only the running NATS container's mounts with `docker inspect --format '{{.Name}} {{json .Mounts}}' <confirmed-container-id>`. Bad: NATS persistence maps to a device with corroborating timeouts, or free space is exhausted. Good: storage mapping is known and capacity/latency are healthy. Device names are host-local; do not assume identically named devices share a physical disk.

4. **Read drive and controller diagnostics.** With approved authenticated access, use `smartctl -a /dev/<disk>`, `smartctl -x /dev/<disk>`, `lspci -nnk`, and read the confirmed device's sysfs queue depth and host link-power policy. Bad: host timeouts remain even if SMART passes; media/CRC/PHY counters may further discriminate. Good: consistent host and drive evidence of normal completion. Zero CRC counters do not eliminate every connection/power fault. Unknown vendor-specific SMART fields must not be interpreted as remaining life without vendor documentation.

5. **Compare latency, completion throughput and I/O wait.** Discover metrics/labels first, then query:

   ```promql
   rate(node_disk_write_time_seconds_total{cluster="<CLUSTER>",instance="<HOST>",device="<DEVICE>"}[1m])
     / clamp_min(rate(node_disk_writes_completed_total{cluster="<CLUSTER>",instance="<HOST>",device="<DEVICE>"}[1m]), 0.001)
   rate(node_disk_written_bytes_total{cluster="<CLUSTER>",instance="<HOST>",device="<DEVICE>"}[1m])
   avg by(instance) (rate(node_cpu_seconds_total{cluster="<CLUSTER>",instance="<HOST>",mode="iowait"}[1m]))
   ```

   Bad: multi-second estimated mean completion time, high I/O wait and collapsing completed throughput. Good: stable low latency and advancing application work. These are sampled aggregate estimates, not request traces or proof of low submitted workload. Inspect peers and events before/after the report, not only submission time.

6. **Distinguish a single consumer stall from stream quorum loss.** Correlate the same launch across conductor event and command logs. Then filter NATS logs for the exact durable name and inspect each broker's `/jsz?accounts=true&streams=true&consumers=true&raft=true`. A command published and handled by adjacent players, plus an affected consumer without quorum, places the failure before Nomad submission. A current leader showing caught-up peers and recorded delivery establishes recovery at observation time. Follower snapshots can disagree with the leader. A backlog warning from an unmapped Raft group does not identify the failing consumer. If retained, use the consumer quorum-loss advisory to inspect the peers present at onset.

7. **Compare broker memory at onset with a working window.** Plot the NATS main task's `nomad_client_allocs_memory_usage` and `nomad_client_allocs_memory_max_allocated` in Grafana. Sustained near-limit usage warrants checking the task's cgroup event counters when collected. Use a single container lifetime to compare deltas. Total task usage alone does not establish Go heap growth, reclamation stalls, an OOM kill, or a causal link to the election. Correlate storage and broker lifecycle logs independently.

## Likely causes

| Cause                                           | Evidence that confirms                                                                                         | Evidence that rules out                                                                         |
| ----------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Storage timeouts disrupt queue persistence      | Kernel timeout/reset plus broker sync errors, quorum loss and launch-consumer failures at matching times       | Queue/storage progress remains normal while a specific game blocks elsewhere                    |
| SSD, firmware, controller or driver interaction | Repeatable controlled comparison that changes one component or setting                                         | Similar errors survive that change; no component was isolated in the source incident            |
| Disk exhaustion                                 | Filesystem capacity at exhaustion and matching no-space failures                                               | Adequate capacity weakens current exhaustion; historic state still needs evidence               |
| SATA transmission corruption                    | Growing CRC/PHY errors and matching kernel diagnostics                                                         | Zero counters weaken this mechanism but do not eliminate every physical/power fault             |
| Individual launch consumer lacks quorum         | Other handlers receive the same launch while the exact consumer reports lost quorum and has no handled command | Affected handler receives and processes that command, after which submission or execution fails |
| Memory pressure affects replication             | Task memory event or stall counters increase alongside lag on the affected replicas                            | Stable task headroom and pressure counters through the episode weaken this cause                |
| Game-specific initialization hang               | Launched process blocked in a confirmed game/native path while shared launch delivery works                    | Widespread queue failures with independent kernel/broker storage errors support a shared cause  |

## Remediation (HUMAN executes; agent never runs)

No repair was executed or validated in the source incident. The following are **not-checked maintenance options**, not copy-paste repair instructions.

- **Isolate hardware on one explicitly identified host.** Guard: confirm current cluster health/quorum and a maintenance window before taking any member out of service. Risk: service interruption and loss of local state. Backup: preserve a verified recoverable system/data backup and relevant diagnostics; retain the original device. Rollback: restore the original device/system state through the approved recovery procedure. Revalidate quorum before touching another member. A known-good alternative SSD can discriminate the drive side from the remaining stack; this is not proof of a vendor defect in advance.
- **Test one software/queue setting only with a reviewed procedure.** Guard: exact host/device, matched kernel support, current settings and maintenance authorization required. Risk: reduced performance, reboot or service interruption. Backup: preserve current boot/runtime configuration and recovery access. Rollback: restore the captured setting/configuration and validate service recovery. An NCQ-disabled comparison was discussed but not run; queued-write errors alone do not justify changing production boot settings.

Do not clear JetStream data or recreate consumers as a substitute for fixing failed persistent writes. A service restart may restore access without resolving storage faults.

## Validation checklist

Machine checks:

- [ ] No new kernel write timeouts, filesystem I/O errors or reset storms over a representative workload period.
- [ ] Broker persistence and quorum remain stable; launch services consume commands without repeated queue-recovery panics.
- [ ] Completion latency and I/O wait normalize; observed throughput alone is insufficient.
- [ ] Expected server/player connectivity becomes healthy for a fresh authorized session.

Human-only checks:

- [ ] Unity appears on the intended server and SPCs, with correct visuals and interaction.
- [ ] Affected experiences and rooms complete the operator launch workflow.

Machine health checks alone do not establish visual correctness or permanent hardware repair.

### Monitoring recommendation (not-checked deployment change)

Add independent full `/healthz?details=true` monitoring/alerts before changing restart policy or readiness routing. Keep liveness/restart decisions separate initially. A full check can report failed follower copies whose leaders remain available elsewhere; compare the affected consumer's leader state and storage faults before recovery. Do not automatically restart every broker or remove every broker from service discovery after simultaneous full-check failures. A sustained-failure threshold, readiness policy and serial recovery safeguards require deployment review and validation; no monitoring configuration was changed in the source incident.

For I/O attribution, distinguish completed bytes/operations from submitted workload and time spent waiting. High I/O wait alone does not mean excessive traffic. Inspect memory pressure/swap and discard activity alongside completion latency. If historical per-process/cgroup I/O telemetry is missing, say so; a current process sample cannot identify the historic initiating workload.

## Not yet verified

- Exact component/firmware/driver defect, why the shared hardware/software combination stalled, and an effective permanent repair.
- Hardware substitution, NCQ-disabled comparison, firmware/BIOS changes, self-tests and end-to-end remediation validation.
- Universality across every attempted session and causality of missing session-setup experiences.
- A broker replication/health preflight and backup/restore procedure for maintenance; specify and verify these before implementation.
- Effectiveness and operational tradeoffs of a stronger health check were not tested. Enabled-only checks skip stream/consumer state; this setting was confirmed in the source incident's retained Nomad job version. For each new incident, compare actual deployment and version-matched health implementation. Distinguish a setup-task retry from a broker-main restart using task identity and lifecycle events.

- Live advisory ingestion, diagnostic sampler records, exporter discovery and Grafana alert delivery are not-checked. The monitoring code and local rendering, fixture and compatibility checks are recorded in the follow-up incident.
- The exact voting peers and initiating cause of the isolated launch consumer's quorum loss are unverified. A Raft group observed after recovery does not establish its identity during the outage.
