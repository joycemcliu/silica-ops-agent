---
title: "JetStream consumer does not deliver retained matching work"
slug: jetstream-consumer-delivery-stalled
services: [video-server, video-dge-renderer, nats]
tags: [jetstream, consumer, rendering, queuing, delivery, leadership]
status: draft
last_verified: 2026-11-06
applies_to:
  nats_server: "2.10.28"
  video_server: "1.6.5"
  video_dge_renderer: "0.4.6"
source_incidents:
  - ../../incidents/2026-11-03-usbaymkt-render-consumer-stalled.md
---

## Symptoms

- Video clips stay Queuing at zero progress; dependent highlights can remain Pending.
- Workers and server processes are available, but useful task receipt/rendering does not advance.
- Successful publication logs coexist with a consumer reporting zero pending work.
- Retained messages match the consumer filter and include sequences beyond its delivery/acknowledgment position.
- A preceding `Received jetstream.consumer error: nats: leadership change` may be present; it is a correlation to investigate, not a sufficient diagnosis.

Platform explanation: [video render queue delivery](../../platform/docs/nats-video-render-queue-delivery.md). Instance-specific identifiers, counts, times and recovery evidence are in the linked incident, not in this reusable procedure.

Repository paths use `SILICA_REPO=../silica` and `SILICA_ENV_REPO=../silica-environments`, relative to the ops-agent repository root. Follow the current root configuration if a future session has different configured values; do not silently substitute defaults.

## Anti-anchoring

- A running worker, subscription startup log or passing liveness check alone does not prove useful delivery.
- `num_pending: 0` alone does not prove an empty stream or an empty application workload.
- Retained matching-message count alone does not prove eligibility; inspect positions and configuration.
- Outstanding pulls count requests, not uniquely identified healthy workers.
- A large in-flight acknowledgment count after recovery can reflect normal prefetch and processing, not a new fault.
- Follower reports of lag do not override the exact object's leader without further evidence.
- Leadership-change errors plus reconnect code do not prove a reconnect deadlock.
- Restart timestamps do not identify a person or prove a power outage. Embedded event time can differ from log ingestion time.

## Triage (read-only, in order)

Obtain the current store's instructions, incident scope and required approvals first. Use the documented production access helpers and private service addresses. Resolve actual addresses/ports from forwarding output or Consul; placeholders below are not commands to execute unchanged. Do not install packages, expose monitoring publicly, recreate failures, or restart services as a diagnostic probe.

The endpoint/API templates below generalize requests exercised in the source incident. Read-only does not override an operator requirement to approve every exact command.

### 1. Establish application impact and dependencies

- Request `GET <platform-https>/video/holodecks/<room>/session`, sort explicitly by timestamp, and use the deployment timezone for any local-day counts.
- Request `GET <platform-https>/video/holodecks/<room>/session/<session>` for representative affected and completed records.
- **Bad:** runnable children remain Queuing without progress; parent Pending statuses reflect waiting children.
- **Good:** child progress and useful completion advance. A parent dependency wait alone does not identify a queue fault.

### 2. Compare retained work and consumer state before broad log searches

Use `GET http://<monitoring-address>:<monitoring-port>/jsz?accounts=true&streams=true&consumers=true&config=true` and identify the exact stream and consumer, including their own leaders.

Inspect `account_details[].stream_detail[]` and `consumer_detail[]`: filter, delivery policy, delivery/acknowledgment positions, retry limit, pending/in-flight counters, waiting pulls, retention and stream limits.

Read state from the exact stream/consumer leader, which need not be the metadata leader. Refresh snapshots after access interruptions or prolonged investigation.

- **Bad:** the delivery position remains unchanged despite application work and live requests; independently verify message eligibility in the next step.
- **Good:** positions and application work advance, or counters are consistent with normal queued/in-flight processing.
- **Do not conclude:** a follower's stale replication report proves cluster-wide failure.

### 3. Verify matching-message eligibility through read-only JetStream APIs

Use an approved authenticated NATS client in the correct store/account. If the remote CLI is absent, an explicitly approved standard-library request/reply client through the documented SSH helper was exercised in the source incident. Do not install a client or bypass authorization automatically.

| API subject                                 | JSON request                                                                         | Required interpretation                                                                                                                    |
| ------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `$JS.API.STREAM.INFO.<stream>`              | `{"subjects_filter":"<exact-subject>"}`                                              | Inspect `state.subjects[<exact-subject>]`; stream-wide totals and HTTP pending counters are not equivalent.                                |
| `$JS.API.STREAM.MSG.GET.<stream>`           | `{"seq":<last-delivered-stream-sequence-plus-one>,"next_by_subj":"<exact-subject>"}` | Compute the starting sequence in code. Inspect only returned subject, sequence, timestamp and error; do not print/decode the message body. |
| `$JS.API.STREAM.MSG.GET.<stream>`           | `{"last_by_subj":"<exact-subject>"}`                                                 | Establish the newest retained matching message independently.                                                                              |
| `$JS.API.CONSUMER.INFO.<stream>.<consumer>` | `{}`                                                                                 | Cross-check the exact filter, positions, counters and current leader against monitoring.                                                   |

These are non-consuming reads. A consumer fetch or acknowledgment is not a substitute.

- **Bad:** messages match the filter and lie beyond the stalled position, while the consumer reports no pending work and other exclusion conditions do not explain it.
- **Good:** no eligible retained messages exist, or the consumer is delivering them. Follow publication/retention or normal processing instead of this recovery path when appropriate.
- **Limit:** this establishes a delivery/accounting inconsistency, not a particular broker defect or storage-corruption cause.

### 4. Corroborate useful workers, publication and version-matched behavior

The following were exercised:

- `GET <consul>/v1/health/service/<service>` and `GET <nomad>/v1/job/<url-encoded-job>/allocations` for current processes, not historical summary totals.
- `GET http://<monitoring-address>:<monitoring-port>/connz?subs=true&limit=1024` for known worker IPs and recent activity. Inspect pagination before claiming complete coverage; omit authentication details.
- Retained publisher logs for `Published event ... topic=...` and `queueTask err`; publisher source at the deployed tag establishes what success means.
- Versioned `git show <deployed-tag>:libs/go/event/subscribe_nats.go`, `simplequeue/queue.go` and `simplequeue/queue_start.go` for intended subscription/reconnect behavior. Do not substitute the current checkout for deployed source.

**Bad:** broker delivery is not advancing despite working publication, eligible retained messages and requesting workers. **Good:** actual receipt and application progress advance. A later connection does not prove that an earlier reconnect worked continuously.

### 5. Use scoped retained logs to investigate the trigger

Discover the Loki datasource and actual label names/values first. Prefer the affected store, exact jobs/nodes and a narrow interval around the last good delivery/error before expanding the window. Report query truncation and timeouts explicitly.

The exercised searches filtered worker logs for queue/subscription errors and NATS logs for `ERR`, `WRN`, `quorum`, `snapshot` and `leader`. If one noisy node fills the limit, isolate other nodes or the exact consumer instead of treating the sample as complete.

When local log tails are dominated by metrics or polling:

- List files with `GET <nomad>/v1/client/fs/ls/<allocation>?path=alloc/logs`.
- Read the selected file through `GET <nomad>/v1/client/fs/cat/<allocation>?path=alloc/logs/<filename>` and filter before displaying output.
- Re-list if a file disappeared. Validate producer exit status, response type and parsed-record count: a missing-file error can appear as plain text even when curl treats the HTTP response as successful.
- Positive entries from a timed-out download support only those observations, not complete counts or absence claims.
- Exclude configuration dumps and sensitive values even inside a `message` field; bound both record counts and line lengths.

## Likely causes

| Cause                                                | Evidence that confirms                                                                                                                                    | Evidence that rules out or limits it                                                                                                        |
| ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Stalled/inconsistent durable-consumer delivery state | Eligible retained messages beyond a fixed delivery/ack position, independent consumer-info corroboration, waiting requests, no ordinary limit explanation | Delivery advances normally or apparent mismatch disappears when querying the actual leader/account                                          |
| Publishing or subject-routing failure                | Publish errors, no retained eligible messages, or producer/consumer filter mismatch                                                                       | Version-matched successful publish logs plus retained matching-message metadata; this combination was observed in the source incident       |
| Workers disconnected or unavailable                  | No requesting connections or useful worker activity                                                                                                       | Corroborated live worker connections and outstanding pulls weaken this explanation; availability alone is not useful work                   |
| Application dependency wait or rendering failure     | Child task errors, missing inputs, or normal progress explains parent Pending                                                                             | Runnable queued children remain undelivered before rendering; dependency waits alone do not explain that boundary                           |
| Normal prefetch / processing backlog                 | Delivery advances and `num_ack_pending` represents work already sent to clients                                                                           | Consumer reports no work despite eligible retained messages and a fixed position                                                            |
| Purge, consumer deletion, full cleanup or data loss  | Identifying operation records plus corresponding stream/message evidence                                                                                  | Retained eligible messages rule out an entirely empty subject, not every historical deletion; absence of logs is not proof no operation ran |
| Specific NATS bug or corrupted storage               | Matched upstream defect/reproduction or discriminating storage evidence                                                                                   | Leadership-change correlation and successful transfer alone do not prove this cause                                                         |

## Remediation (HUMAN executes; agent never runs)

Do not execute this section during read-only diagnosis. Obtain separate production-change authorization for the exact target, action, preconditions and verification. The linked incident records an explicitly authorized recovery that occurred before this runbook was authored; it is not permission to execute this document.

### Consumer-only leader transfer: bounded first recovery option

**Scope:** one existing replicated consumer. Not a stream-leader transfer, broker restart, consumer deletion/rebuild, purge or bulk application replay.

**Backup step:** capture fresh full consumer configuration/state and stream state, including per-subject retention and object leaders, into approved restricted incident evidence. This metadata is **not a restorable stream backup**. Follow the production backup policy; if it requires a restorable stream backup before this operation, obtain and verify it with an approved procedure first. No backup-creation procedure was tested in the source incident.

**Guards:** assert the exact target/filter, expected stalled delivered and acknowledgment positions, no unexpected in-flight acknowledgments, retained matching work, and current replicas. Abort if the failure no longer matches or preconditions changed. Do not hardcode the source incident's targets or sequence positions in a reusable script.

**Action exercised on the listed NATS version:** send one empty-body request to `$JS.API.CONSUMER.LEADER.STEPDOWN.<stream>.<consumer>` and require the returned `success: true`. Do not add placement/body options or automatic retries without separate version-specific verification. A timeout or broken connection can leave the mutation outcome ambiguous: read state back before considering another change.

**Risk:** temporary consumer interruption and client reconnection; at-least-once processing can produce retries. Existing error-handling behavior can amplify a transition. Leadership transfer is not guaranteed to cure the underlying defect.

**Rollback/stop condition:** there is no configuration edit to undo, and normal acknowledgments after resumed processing cannot be reversed by another election. If progress does not resume or errors worsen, preserve observations and escalate; do not delete/recreate the consumer, purge the stream or blindly repeat the step-down as a rollback. An intentional return to a preferred leader or restoration from backup was not exercised and needs a separately approved, version-specific procedure.

**Readback:** sample the exact consumer through the API or its new leader after approved bounded waits. Verify leader/state, delivery and acknowledgment progress, current replicas, unchanged configuration and unaffected stream leadership. Then inspect the affected application tasks.

### Stop before destructive alternatives

Consumer deletion under interest retention can remove the interest preserving queued messages. Do not label deletion/recreation as message-preserving. Any reconstruction/replay requires verified preservation/backup, application-state reconciliation, duplicate-processing safeguards, rollback planning and a new approval. Full data-directory cleanup is not the scoped recovery for this failure signature.

## Validation checklist

### Machine-verifiable

- [ ] Recovery API response and exact target readback captured; no success claim from response alone.
- [ ] Consumer delivery and acknowledgment positions advance beyond the stalled state.
- [ ] Matching retained/in-flight counts change consistently with useful processing; zero pending is not mistaken for zero remaining work.
- [ ] Configuration unchanged and replicas current; no unintended stream or broker change reported.
- [ ] An affected application child is rendering or completed; inspect errors separately.
- [ ] Remaining backlog/in-flight work and final upload coverage are reported honestly.
- [ ] Only session-created diagnostic tunnels are cleaned up with approval; user/pre-existing tunnels remain untouched.

### Human confirmation

- [ ] Operator confirms the application no longer presents a store-wide delivery stall.
- [ ] Representative finished videos are visually correct and available where expected.
- [ ] All affected sessions/uploads are reconciled before claiming complete content recovery.

Queue delivery and one completed child do not prove completion or visual correctness of all videos.

## Not yet verified

- The precise broker defect or why the suspected leadership transition produced the inconsistent consumer state.
- Whether this recovery works for other versions, filters, retention modes or failure signatures; recurrence validation is required before human review.
- Final completion/upload and visual correctness of every affected video in the source incident.
- Any consumer rebuild, message replay, deletion, broker upgrade, preferred-leader rollback or restorable backup/restore procedure.
- Executable embedded build metadata as independent proof of the library/NATS client actually compiled into a deployed renderer.
- Operator attribution or electrical power loss without identifying audit/host evidence.
- Dedicated automated alerting and a reusable collector for the failure signature; these remain proposals in the [diagnosis debrief](../../debrief/docs/2026-11-03-usbaymkt-render-consumer-stalled.md).
