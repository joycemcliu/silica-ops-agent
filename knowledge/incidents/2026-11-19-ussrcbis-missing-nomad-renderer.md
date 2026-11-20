---
title: Bishop Ranch video renders stalled after the Nomad renderer job disappeared
incident_date: 2026-11-19
incident_time_range: "2026-11-19 22:15 to 2026-11-20 03:43"
timezone: UTC
store: USSRCBIS
runbook: ../runbooks/docs/missing-nomad-renderer.md
---

## Report, impact and scope

Support reported videos failing to render in all four rooms after rerenders and restarts. The four sampled sessions had nine runnable tasks at zero render progress and three tasks waiting on dependencies. Some Room 3 and Room 4 renders had completed earlier. The total number of affected sessions is unknown. [Incident thread](https://sandboxvr.slack.com/archives/C046N4EMYRY/p1795134412985369)

## Instance details

| Item | Value |
| --- | --- |
| Store and services | Bishop Ranch, San Ramon production. Nomad, Consul, video-server, DGE renderer, and guest video storage |
| Jobs | `video-dge/renderer` and `video-dge/renderer-reboot` |
| Video nodes | `R1-VIDEO`, `R2-VIDEO`, `R3-VIDEO` |
| Sample sessions | `ussrcbis-261119-G1-150538`, `ussrcbis-261119-G2-142529`, `ussrcbis-261119-G3-140236`, `ussrcbis-261119-T4-102121` |
| Deployment declaration | Video DGE module 0.4.6 enables the renderer by default. [Store declaration](https://github.com/SandboxVR/silica-environments/blob/ec28f21459bf3bc5e23bf52a3e00bd560f4d3115/USSRCBIS/module-video-dge.tf#L30) |

## Evidence ledger

| ID | Tag | Command, query, or evidence source | Result summary |
| --- | --- | --- | --- |
| E01 | observed | Slack issue and attachment metadata | Support reported complete raw files and attempted rerenders and restarts. Attachment contents were unavailable to the agent. |
| E02 | observed | Git status and worktree checks, store configuration, tagged module source, and read-only Git history fetched in a disposable bare repository | The current deployment config still declared the renderer. The Nov 19 store change updated Vest. Recent infra and NATS changes did not alter the renderer declaration. |
| E03 | observed | Store task API `GET /video/render/task/<session>`, initial and repeat snapshots | Room 1 had 3 queuing. Room 2 had 3 queuing and 2 pending. Room 3 had 2 queuing, 1 pending and 1 completed. Room 4 had 1 queuing and 27 completed. All nine queued items showed zero progress and no recorded render start. The sampled Room 3 split-screen render finished at 22:15 UTC and Room 2 tasks had queued by 23:28 UTC. |
| E04 | observed | Nomad job list, exact job read, allocations and evaluations | The exact renderer job returned HTTP 404. Allocations and evaluations were empty. The renderer reboot controller was absent from the job list. |
| E05 | observed | Nomad node list and node details, Consul renderer, video-server and NATS health | Consul returned no renderer registrations. Three video nodes were ready, eligible for scheduling, marked for rendering and reported healthy Docker drivers. The video-server and two NATS registrations passed their Consul checks. |
| E06 | observed | Nomad filtered job event stream, available Grafana tools, and video-server allocation log directory listing | Nomad returned permission denied. The production Grafana MCP connection was unavailable in this session. Allocation log files were listed. Their contents were not collected. |
| E07 | observed | GitHub Actions run and store job listings, PR plan and production apply logs | The Nov 19 production apply finished at 08:39 UTC. Its sole planned destroy was a Vest analytics job. The renderer had no planned change. Later inspected runs before recovery showed no Bishop Ranch deploy job. [Production apply log](https://github.com/SandboxVR/silica-environments/actions/runs/44488790896/job/135440701949) |
| E08 | observed | GitHub Actions store dispatch and Terraform apply log | The existing store dispatch planned creation of the renderer and the reboot controller. Both creation steps completed at 03:28:36 UTC. The apply reported 4 added, 14 changed, and 0 destroyed. The agent did not initiate it. [Recovery apply log](https://github.com/SandboxVR/silica-environments/actions/runs/44667820277/job/136061406040) |
| E09 | observed | Nomad exact renderer job and allocation reads, store task API at 03:42–03:43 UTC | The new job was version 0, submitted at 03:28:36 UTC, with three running allocations. Room 2 advanced to two completed, two rendering, and one pending. The sampled queued tasks in Rooms 1, 3, and 4 had not advanced. |
| E10 | observed | Published output URLs from the task API and bounded media probes | The API reported eight URLs, including a new Room 2 upload. Cloud Storage denied direct read access to all eight. Playback was unverified. |
| E11 | observed | Toolkit tunnel, bounded foreground port forwards, and scoped cleanup process checks | Background forwarding timed out on nodes 1 and 3 during follow-up. Foreground forwarding to the approved proxy pods enabled the post-apply checks. The final process check found no active store forwards. |
| E12 | inferred | E02–E09 | The absent Nomad job explains the lack of available DGE render workers. The 22:15–23:28 UTC interval is a starting point for audit searches. The task timestamps do not establish when Nomad lost the job. |
| E13 | not-checked | Nomad administrative audit logs, Terraform backend history, private attachments, JetStream retention, and playback | No record identified the removal mechanism or actor. The backend metadata read was declined. Eligibility and progress after restoration do not prove the disposition of all queued events. |

## Actions and recovery timeline

| Timestamp UTC | Action or observation | Result |
| --- | --- | --- |
| Nov 19 08:39 | Production Terraform apply | Renderer declaration reconciled without a planned renderer change. |
| Nov 19 22:15–23:28 | Application task timestamps | Room 3 recorded a completed render. Room 2 later recorded jobs reaching `queuing` with no render start. |
| Nov 20 03:03 | Agent repeated read-only checks | Renderer job absent and all nine sampled queued tasks still at zero progress. |
| Nov 20 03:28 | Existing `USSRCBIS` dispatch applied Terraform | Recreated both renderer jobs. |
| Nov 20 03:42–03:43 | Agent verified Nomad allocations and task status | Three workers running, partial Room 2 recovery, and eight reported output URLs. Playback remained unverified. |

## Outcome and remaining work

Renderer registration and partial processing recovery were confirmed. Validate the remaining tasks and check playback through an authorized viewer. Obtain Nomad audit records for `video-dge/renderer`, starting with the 22:15–23:28 UTC window on Nov 19. Expand the window if necessary and correlate any deregistration with deployment records.

[Runbook for a missing DGE renderer job](../runbooks/docs/missing-nomad-renderer.md)
