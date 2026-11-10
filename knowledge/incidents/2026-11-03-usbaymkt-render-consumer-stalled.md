---
title: "USBAYMKT render consumer stalled despite retained video messages"
incident_date: 2026-11-03
incident_time_range: null # Exact onset unknown; delivery recovery was verified on November 5 store-local.
timezone: America/Los_Angeles
store: USBAYMKT
runbook: ../runbooks/docs/jetstream-consumer-delivery-stalled.md
platform_notes:
  - ../platform/docs/flows/nats-video-render-queue-delivery.md
debrief: ../debrief/docs/2026-11-03-usbaymkt-render-consumer-stalled.md
---

## Report, impact and scope

The operator reported videos stuck in **Queuing** across USBAYMKT Rooms 1–4. Application inspection confirmed runnable child tasks at zero progress; dependent highlights showed **Pending** while waiting for those children.

The initial application enumeration found 17 November 4 sessions affected: Room 1 had 3 pending; Room 2 had 4 pending and 3 queuing; Room 3 had 3 pending and 1 queuing; Room 4 had 3 pending. These were session aggregate statuses, not individual message counts. A November 3 Room 3 session was also affected. The initial count used a UTC timestamp cutoff; the enumerated results identify November 4 store-local session IDs, but a separate calendar-day-boundary recount was not performed. Do not reuse that cutoff as a general local-day query.

A completed session followed by a pending session initially bounded affected session starts, not the exact failure time. Later broker and worker evidence established a delivery stall while publication continued.

## Instance details

| Item | Observed value |
| --- | --- |
| Store / environment | USBAYMKT / prod; San Francisco; `America/Los_Angeles` |
| Fixed session configuration | `SILICA_REPO=../silica`; `SILICA_ENV_REPO=../silica-environments`, relative to the ops-agent root |
| Stream / subject | `silica` / `silica.video` |
| Affected consumer | `render_dot_start__video` |
| Broker addresses | `10.4.0.101`–`10.4.0.103`; monitoring port `8222`; client port `4222` |
| Broker version | NATS `2.10.28` |
| Renderer image | `us-docker.pkg.dev/silica-production/images/video-dge-render:0.4.6` |
| Renderer source tag / commit | `video-dge/v0.4.6` / `51d77473cb32c5dae3e66e49efa0e9856b3c87cd` |
| Event module | `silica-libs/event`, copied from `libs/go/event` in the source checkout and built through a Go workspace |
| Last event-library change at that tag | `50c60838e2a9775617cf3c0a8cf6708ec23ce183`, `refactor(dge): use simplequeue for remaining components (#4334)` |
| Declared NATS Go dependency | `github.com/nats-io/nats.go v1.31.0` in that library's `go.mod`; compiled binary dependency metadata was not inspected |
| Video-server image | `us-docker.pkg.dev/silica-production/images/video-server:1.6.5` |
| Consumer / stream leader before recovery | Both `master-3`; metadata-cluster leader was separately reported as `master-2` |
| Consumer / stream leader after recovery | Consumer `master-1`; stream remained `master-3` |
| Recovery validation session | `usbaymkt-261103-G3-212454`, Room 3 |
| Other sampled affected sessions | `usbaymkt-261104-G1-184252`, `usbaymkt-261104-G2-153520`, `usbaymkt-261104-G3-175543`, `usbaymkt-261104-G4-205623` |
| Main live access | `scripts/store-port-forward.sh`, `scripts/store-port-forward-ssh.sh`, and approved `scripts/store-sshuttle.sh` access |
| Retained logs | Production Grafana MCP, datasource `silica-loki`, labels `cluster="USBAYMKT"`, `job`, `node_name` |

## Evidence ledger

Scope: live application, Nomad, Consul, NATS and retained Grafana/Loki diagnostics, plus local versioned source inspection. Repeated commands and failed retries are grouped by their exact endpoint or command family. Long inline Python clients are described by their protocol and exact requested API; their full payloads and approvals remain in the conversation. No credential contents are included.

### Application, deployment and source

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E01 | observed | Read `config.env`, diagnosis instructions, `USBAYMKT/AGENTS.md`, store timezone and video deployment configuration | Established prod scope, fixed repository paths, store-local timezone, and required access workflow. |
| E02 | observed | `git status --short`, `git branch --show-current`, and both configured repositories' `git status --short --branch` | Ops-agent had existing unrelated changes; source was on `master`, environments on a separate webcam-fix branch. No checkout, fetch, commit or repository update was performed. Locally recorded refs do not prove remote freshness. |
| E03 | observed | `GET /video/holodecks/{1,2,3,4}/session`; explicit sorting/counting in Python; selected `GET /video/holodecks/<room>/session/<session>` | Confirmed affected sessions in every room, queuing child tasks at 0%, and parent dependency waits. Completed records existed before the stall. |
| E04 | observed | `GET /v1/jobs`, `/v1/nodes`, `/v1/job/video-dge%2Frenderer/allocations`, `/v1/job/video%2Fserver/allocations`; Consul `/v1/health/service/{video-server,video-dge-renderer,nats}` | Four running renderer allocations and two passing video-server liveness checks; historical down node registrations coexisted with ready registrations. Running processes did not establish useful rendering progress. |
| E05 | observed | `GET /v1/job/video-dge%2Frenderer` and `/v1/job/video%2Fserver`, projecting images/version and selected non-sensitive configuration fields | Established renderer `0.4.6` and video-server `1.6.5` image tags. Queue template selected NATS at `nats.service.silica`. |
| E06 | observed | `git tag --list '*0.4.6*'`, `git tag --list '*1.6.5*'`; `git show` for publisher/backend selection at `video/v1.6.5` and event subscription/reconnect source at `video-dge/v0.4.6` | Publisher waits for `PublishMsg` success on `silica.video`; renderer uses the matching durable/filter. Its consumer error handler closes consumption/connection and relies on a simplequeue reconnect loop. Intended reconnect behavior alone does not prove a failed reconnect or deadlock. |
| E07 | observed | `git rev-parse 'video-dge/v0.4.6^{commit}'`; `git log -1 --format='%H %s' video-dge/v0.4.6 -- libs/go/event`; tagged renderer Dockerfile and event `go.mod` | Established release/library commits and local-workspace bundling listed above. No independent attestation of the deployed executable's embedded dependency metadata. |

### Queue state, message provenance and retained logs

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E08 | observed | `GET http://<broker>:8222/jsz?accounts=true&streams=true&consumers=true`, compared across all three brokers | Follower snapshots reported lag/non-current peers; the actual stream/consumer leader reported current replicas. Follower disagreement was not accepted as proof of a cluster-wide replication failure. |
| E09 | observed | Leader `/jsz?...&config=true`; direct `$JS.API.CONSUMER.INFO.silica.render_dot_start__video` | Consumer filter `silica.video`, deliver policy `new`, explicit acknowledgments, max delivery count 6. Last delivery/ack stream sequence `177924`, last delivery `2026-11-04T04:52:44Z`, last acknowledgment `04:53:57Z`; zero pending and zero unacknowledged, with four outstanding pulls. Stream used interest retention, file storage, three replicas, and finite message age. |
| E10 | observed | `/connz?subs=true&limit=1024` on each broker, projecting known worker/master IPs and non-authentication fields | Live connections from all four renderer PCs with recent activity. Requests are not a unique worker-health count, so this separately corroborated connection presence. |
| E11 | observed | `$JS.API.STREAM.INFO.silica` with `{"subjects_filter":"silica.video"}` through a Python standard-library request/reply client on master-2 | Found 390 retained `silica.video` messages while the consumer reported no pending messages. No application message was consumed or acknowledged by this query. |
| E12 | observed | `$JS.API.STREAM.MSG.GET.silica` with `{"seq":177925,"next_by_subj":"silica.video"}` and `{"last_by_subj":"silica.video"}`; output restricted to metadata | First retained video message after the consumer position: sequence `177984`, stored `2026-11-04T05:49:13.738002485Z`. Latest sampled: sequence `186144`, stored `2026-11-06T01:59:44.660666956Z`. These matched the subject and lay beyond the stuck delivery position. Message bodies were not printed or decoded. |
| E13 | observed | Nomad `/v1/client/fs/logs/<allocation>?task=execute&type=stderr&origin=start...` and bounded recent stdout/stderr reads | Established renderer subscription logs and current-process activity. Some recent tails were dominated by metrics; startup logs alone did not prove delivery. Configuration-dump records were excluded from later filtered reads because message fields can contain secrets. |
| E14 | observed | `/v1/client/fs/ls/<allocation>?path=alloc/logs`; `/v1/client/fs/cat/<allocation>?path=alloc/logs/docker.stderr.<rotation>` with structured filtering | Located retained publisher files. One old file rotated away and returned a plain-text missing-file response despite curl treating the response as successful; empty JSON-filter results were therefore not evidence of no publishing. Two later downloads timed out after partial transfer; positive entries were usable, not complete counts or negative findings. |
| E15 | observed | Retained publisher samples and Loki `{cluster="USBAYMKT",job="video/server"}` filtered for successful video publishing/queue errors | Successful publishes continued after the consumer's last delivery, including Room 1 session `usbaymkt-261104-G1-184252` at store-local `2026-11-04T18:59:27-08:00`. Loki also showed successful publication at `2026-11-03T21:49:13.741-08:00`, matching E12's stored message time. |
| E16 | observed | Loki `{cluster="USBAYMKT",job="infra/nats"}` around `2026-11-04T04:30Z` | Master-1 repeatedly logged `NO quorum, stalled` for the stream and many consumers. The broad query hit its 100-entry limit within its first short interval; it did not describe all nodes or the whole requested window. |
| E17 | observed | Narrowed Loki query for `infra/nats` on master-2/master-3 and `video-dge/renderer`, `2026-11-04T04:45:00Z`–`05:30:00Z` | All four renderers logged `Received jetstream.consumer error: nats: leadership change` around `05:16Z`. Before that, logs showed actual video receipt and processing. Other broker nodes' narrowed results did not establish the cause of the transition. |
| E18 | inferred | E09–E12, E15 and E17 together | Isolated an inconsistent/stalled consumer delivery path, not an empty queue or merely powered-off workers. Leadership transition is a suspected trigger; a particular NATS defect, storage corruption, or reconnect deadlock was not proven. |

### Restart, force-clean and access checks

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E19 | observed | `/varz` on all brokers; `/v1/job/infra%2Fnats/allocations`; Loki lifecycle search | Master-1 stopped on `2026-11-05T07:00:25Z` and replacement started at `07:08:21Z`. Master-2/master-3 process starts remained October 10. This later restart could not by itself explain the earlier onset. |
| E20 | observed | Focused Nomad agent/event-streamer Loki search, `2026-11-05T06:55:00Z`–`07:15:00Z`, for `infra/nats` and affected allocation IDs | Nomad sent an interrupt to master-1's old tasks; logs showed termination and new task setup. Old allocation `64b163f5-a42a-7b0c-bab8-a51cbef12420`, replacement `d7ca0e63-27a0-940b-153d-0274b9f3f6ee`. No identifying actor evidence was found. |
| E21 | observed | `GET /v1/jobs?prefix=infra%2Fnats%2Fforce-clean`; source `nats-force-clean.nomad.hcl.tftpl`; Loki job-label and Nomad reference searches for November 3–5 | Parent summary recorded three historical dead children; live listing returned only the parent. No incident-window force-clean/repair references were found in the completed narrowed log query. One broader query timed out. Historical executions' times and operators were not established. The source deletes data directories; it is not an ordinary restart. |
| E22 | not-checked | Completed retained-allocation lookup for force-clean; operator-identifying audit records; host/power evidence | The retained-allocation lookup failed when the LAN route reset. No proof of a power outage or proof that no cleanup ever happened. |
| E23 | observed | Production MCP `initialize`, `notifications/initialized`, `tools/list`, `list_datasources`, `list_loki_label_names`, `list_loki_label_values`, `query_loki_logs` through approved HTTP requests | `silica-loki`, `cluster="USBAYMKT"`, and actual job labels were discovered rather than assumed. Queries were bounded; truncated, empty and timed-out results were distinguished. |
| E24 | observed | Documented access helpers; `kubectl get pods/events` for store socat resources; approved local dependency, route, tunnel and Herdr checks | Access failures included Kubernetes proxy replacement, missing forwarding dependencies, SSH authentication/prerequisites, local elevation prompts, tunnel disconnects, a refused loopback monitoring address, and an IPv6-only forwarding/readiness mismatch. These were access failures, not evidence of production restarts. Later SSH through master-2 worked. No package or sudo installation was performed. |
| E25 | observed | Approved `chmod 600` of the configured local SSH password file; authentication handled by helper without printing contents | Restricted local credential-file permissions. Credential contents were never intentionally requested or included in this record. |
| E26 | observed | `command -v nats`; `nats stream info --help`; `nats request --help`; direct workstation `nats ... stream info silica --json`; remote `command -v nats; command -v python3` | Workstation CLI existed but LAN request timed out. Remote master had Python and no NATS CLI; approved standard-library API requests through the documented SSH helper supplied decisive evidence without installing a client. |

## Findings

1. **Confirmed failing boundary:** the durable render consumer reported no eligible pending work despite retained matching messages beyond its delivered and acknowledged position, with workers requesting work. Independent JetStream API reads corroborated the HTTP monitoring state.
2. **Confirmed recovery behavior:** one consumer-only leader step-down restored delivery, acknowledgment progress and application-level child rendering without resetting consumer configuration or explicitly deleting stream data.
3. **Suspected trigger:** concurrent renderer leadership-change errors near the onset. Their existence and deployed error/reconnect code do not establish the exact failure mechanism.
4. **Not established:** a particular NATS bug, storage corruption, power outage, incident-window force-clean, or the person responsible for master-1's later replacement.
5. **Evidence corrections:** zero pending did not mean no stored video work; follower replication views were not accepted over leader state; missing rotated files invalidated negative log-filter conclusions; October startup messages re-ingested in November were not new process starts.

## Actions and recovery timeline

All timestamps in this table are UTC. Exact remote mutation and readback payloads were shown to the operator and explicitly approved before execution.

| Timestamp | Action actually taken | Result | Backup / rollback reference |
| --- | --- | --- | --- |
| 2026-11-04 04:52:44 | Last delivery recorded before stall | Consumer delivered through stream sequence `177924`. | Read-only observation. |
| 2026-11-04 04:53:57 | Last acknowledgment recorded before stall | Acknowledgment floor at the same stream sequence. | Read-only observation. |
| Around 2026-11-04 05:16 | Leadership-change errors appeared on all renderer PCs | Suspected trigger, not independently proven causal mechanism. | Retained worker logs. |
| 2026-11-06 02:47:34 | Fresh leader/configuration preflight | Consumer still stuck; replicas current; no in-flight acknowledgments. | Metadata captured in session; not a restorable stream backup. |
| Around 2026-11-06 02:52:05 | Issued one empty-body request to `$JS.API.CONSUMER.LEADER.STEPDOWN.silica.render_dot_start__video` after asserting expected state | API returned `success: true`; consumer leadership transferred from master-3 to master-1. Stream leadership remained master-3. | No stream backup was taken. Scope was leadership only; consumer deletion, rebuild, purge and replay were not performed. No rollback was required. |
| 2026-11-06 02:52:10–02:52:35 | Three approved readbacks following bounded waits | Delivery advanced to and beyond the newest previously sampled message; retained video count began decreasing through normal processing/acknowledgments. Consumer configuration unchanged; replicas current. | No additional mutation or automatic remediation retry. |
| 2026-11-06 02:55:28 and following application read | Verified current consumer and affected Room 3 session | Delivered stream position `186229`; acknowledgment floor advanced to `178070`; `377` messages in flight. `P2_Shot1` completed at 100%; `P3_Shot1` rendering. Other children/parents still queued/pending. | Confirms useful processing, not completion of all sessions or uploads. |
| After recovery verification | Ran approved `bash scripts/grafana-mcp-forward.sh stop` and `status` | `Stopped.` then `Not running.` Temporary SSH helpers cleaned up their own tunnels. | Did not stop the user's separate sshuttle pane. |

The recorded recovery was executed by the agent after explicit operator approval. The reusable runbook is authoring guidance for future human execution; no remediation script has been written or executed as part of documenting this incident.

## Outcome and remaining work

**Recovered consumer delivery and verified rendering progress.** No broker or render-PC restart, full NATS cleanup, consumer recreation, explicit message purge or application-message republish was performed. Normal acknowledgments can remove messages under interest retention; that is not an explicit purge.

At the last verification, 377 messages remained delivered/in flight. Do not interpret zero pending as an empty workload or claim every affected video finished. Final backlog drain, final render/upload success across all rooms, and visual confirmation were not checked after that snapshot.

Remaining follow-up:

- Monitor application tasks and in-flight acknowledgments until backlog processing completes; review render/footage/upload failures separately.
- Investigate the precise broker/consumer mechanism associated with the leadership transition, without labeling a known upstream defect until matched evidence exists.
- Decide whether to inspect compiled executable build metadata; source-tag association and declared dependencies do not attest exact deployed binary provenance.
- Historical force-clean actor/timing and a power-loss explanation remain unverified, not confirmed negative facts.

## Related documentation

- [Diagnosis debrief and toolkit improvements](../debrief/docs/2026-11-03-usbaymkt-render-consumer-stalled.md)
- [Platform knowledge: video render queue delivery](../platform/docs/flows/nats-video-render-queue-delivery.md)
