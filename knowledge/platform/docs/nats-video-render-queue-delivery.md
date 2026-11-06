---
title: "Video rendering: queue delivery and application progress"
description: "Use when: video tasks stay Queuing despite healthy workers or zero consumer pending; distinguish publication, retention, delivery and useful rendering progress."
tags: [consumer-lag, stream-stall]
components: [nats, video-dge, video-server]
last_verified: null # Retained incident evidence only; checks were not rerun during authoring.
applies_to:
  video_server: "1.6.5"
  video_dge_renderer: "0.4.6"
  nats_server: "2.10.28"
  renderer_source_commit: "51d77473cb32c5dae3e66e49efa0e9856b3c87cd"
source_incidents:
  - 2026-11-03-usbaymkt-render-consumer-stalled
---

# Video rendering: queue delivery and application progress

## When to use

- Runnable clips stay Queuing while dependent highlights remain Pending; healthy processes do not establish useful delivery. Evidence: incident E03/E04. Status: verified in the retained incident, not rechecked during authoring.
- Scope: versions above and one observed recovery; verification statuses below refer to the linked incident, not fresh production checks. Repository paths resolve from configured `SILICA_REPO`; source claims refer to deployed tags, not the current working tree.

## Platform behavior

- Application creation, publication, consumer delivery, rendering and upload are separate boundaries. `queueTask` publishes before setting Queuing; `PublishMsg` success precedes `Published event ... topic=...`. Successful publishing does not prove retention, delivery or completion. Evidence: E03/E06/E15; `video/v1.6.5:apps/video/server/cores/render/render.go` and `libs/go/event/publish_nats.go`. Status: verified.
- Stream totals describe all retained subjects; `state.subjects[<subject>]` describes matching retained work, not eligibility relative to consumer positions. Inspect filter, policy, delivery limit, `delivered` and `ack_floor` together. Evidence: E09/E11/E12. Status: verified.
- `num_pending` reports undelivered work, but was zero despite eligible retained messages in this incident. `num_ack_pending` describes delivered unacknowledged work, not active renders; `num_waiting` counts pulls, not unique healthy workers. Zero pending after recovery coexisted with in-flight work. Evidence: E09–E12 and recovery readbacks. Status: verified.
- Consumer-only leadership transfer restored delivery and child progress without changing configuration or stream leadership. This establishes one recovery, not a specific broker defect or a universally effective fix. Evidence: incident recovery timeline. Status: verified.
- Metadata, stream and consumer leaders can differ. Followers reported lag while the object's leader reported current replicas; compare against the exact object's leader. Evidence: E08/E09. Status: verified.
- The event error handler stops consumption, closes the connection and relies on reconnect; source code does not prove a reconnect deadlock. Evidence: E06/E17; `video-dge/v0.4.6:libs/go/event/subscribe_nats.go`, `simplequeue/queue.go` and `simplequeue/queue_start.go`. Status: verified for intended behavior; deadlock remains inferred and unproven.
- The stream used interest retention. Removing consumer interest may remove queued messages; deletion/rebuild is not equivalent to leadership transfer. Evidence: E09 configuration; deletion was not tested. Status: verified configuration; inferred deletion risk.
- Renderer builds copy `libs/go` into a local Go workspace; the event library is bundled from that checkout. Its declared NATS dependency does not attest the deployed executable's compiled dependencies. Evidence: E07; tagged renderer Dockerfile and event `go.mod`. Status: verified source behavior; executable metadata not checked.
- Monitoring was reachable through its registered LAN address after loopback refusal. An access failure alone does not prove a service restart or outage. Evidence: E24. Status: verified.
- A retained-count decrease after recovery can follow normal acknowledgment under interest retention; it does not prove an explicit purge. Evidence: E09 and recovery readbacks. Status: verified for observed processing; broader attribution is inferred.

## Diagnosis clues

Templates below require approved access and actual target values. These request shapes were exercised in the incident; they were not rerun during authoring.

| Observation | What it suggests | How to verify (exact request → expected result) | Next step | Status |
| --- | --- | --- | --- | --- |
| Parent Pending; children Queuing | Dependency waits can hide runnable work | `GET <platform-https>/video/holodecks/<room>/session/<session>` → inspect child statuses/progress separately from the parent (E03) | Trace publication and delivery for runnable children | verified |
| Zero pending despite retained work | Possible consumer delivery/accounting inconsistency | `$JS.API.STREAM.INFO.<stream>` with `{"subjects_filter":"<exact-subject>"}`; `$JS.API.STREAM.MSG.GET.<stream>` with `{"seq":<last-delivered-plus-one>,"next_by_subj":"<exact-subject>"}` and `{"last_by_subj":"<exact-subject>"}` → matching retained sequences beyond delivery (E11/E12); inspect metadata only | Cross-check consumer state and ordinary exclusions | verified |
| Follower lag or conflicting counters | Object leadership or stale snapshots matter | `GET http://<monitoring-address>:<monitoring-port>/jsz?accounts=true&streams=true&consumers=true&config=true`; `$JS.API.CONSUMER.INFO.<stream>.<consumer>` with `{}` → identify object leaders, configuration and positions (E08/E09) | Read the object's leader and refresh snapshots | verified |
| Healthy workers but no progress | Liveness is weaker than useful delivery | `GET http://<monitoring-address>:<monitoring-port>/connz?subs=true&limit=1024` → known worker connections (E10; inspect pagination); repeat the application request above → advancing child progress after recovery | Follow the runbook's eligibility and recovery guards | verified |

## Unknowns

- Exact broker defect, causal role of the leadership transition, and effectiveness on other versions remain unproven. Evidence: E18 and one recovery. Status: inferred; further verification required.
- Final completion/upload and visual correctness of all affected videos, compiled binary provenance, and deletion/rebuild/backup restoration were not checked. Evidence: incident outcome and E07/E22. Status: inferred; untested.
- Process restarts and replayed startup logs do not establish electrical power loss or an operator's identity. Evidence: E19–E22. Status: verified evidence limitation; attribution remains inferred.

## Related docs

- [Source incident and evidence ledger](../../incidents/2026-11-03-usbaymkt-render-consumer-stalled.md)
- Source debrief: [diagnosis lessons and toolkit improvements](../../debrief/docs/2026-11-03-usbaymkt-render-consumer-stalled.md)
- [Consumer delivery stall runbook](../../runbooks/docs/jetstream-consumer-delivery-stalled.md)
- [Diagnosis workflow](../../../docs/diagnose_agent.md)
