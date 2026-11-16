---
title: "USWINDOW Room 1 missing post-experience videos"
incident_date: 2026-11-16
incident_time_range: "2026-11-11 00:00:00 through 2026-11-14 00:00:00 (exclusive)"
timezone: America/New_York
store: USWINDOW
runbook: ../runbooks/docs/missing-video-task-registration.md
---

## Report, impact and scope

User reports missing Room 1 video-list entries for November 11–13, with other rooms unaffected. The referenced attachment was not available in this conversation. Live APIs confirm the list gap. Two completed Squid Game sessions on November 13 have no video tasks: guest `uswindow-261113-G1-140210` and test `uswindow-261113-T1-145940`.

The sessionBookings endpoint returns one killed test session each on November 11 and 12, with no completed guest sessions on those dates. November 13 additionally has two killed guest sessions and one killed test session. These are returned session records, not independent proof of all booking or customer activity.

## Instance details

| Item | Value |
| --- | --- |
| Configuration fixed at session start | SILICA_REPO=../silica; SILICA_ENV_REPO=../silica-environments; resolved from original toolkit root |
| Session | Codex 01a1e3ea-b416-7810-a738-4f53ac9e99eb |
| Deployment | video-server image 1.6.5; America/New_York |
| Access | User-approved store-port-forward.sh; node 3 persistent session; Nomad 10197, Consul 20197, HTTPS 30197 |
| Successful control | uswindow-261113-G2-204721, SquidGame_3.4.0 |
| Room 1 boundary | latest November 10 entry uswindow-261110-G1-164550; first November 14 entry uswindow-261114-T1-092816 |

## Evidence ledger

All API calls below were GET requests through the approved local tunnel. JSON and HTML working artifacts were stored under /tmp/uswindow-* and are not committed because session responses can contain customer information.

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E01 | observed | Root config.env; USWINDOW/AGENTS.md and store.tf; git status, fetch origin master, merge --ff-only origin/master in both configured repos | Config loaded; both repositories clean on master and already current; toolkit original working tree has unrelated local changes, preserved. |
| E02 | observed | GET /video/holodecks/{1,2,3,4}/session; explicit timestamp conversion using zoneinfo America/New_York | Room 1 has zero entries November 11–13; 2 completed November 10, 12 November 14, 4 November 15. Room 2 has 6/3/5 completed entries November 11/12/13. Rooms 3 and 4 also have entries on all three dates, including Squid Game. |
| E03 | observed | GET /session/holodecks/1/sessionBookings?dateFrom=2026-11-10T05:00:00Z&dateTo=2026-11-16T05:00:00Z | Completed guest and test sessions on November 13; no completed sessions returned for November 11–12. Local-day counts use createdAt converted to New York. |
| E04 | observed | GET /video/holodecks/1/session/{affected-session}; GET /video/render/task/{affected-session}, for both completed sessions above | Empty rendering lists and empty task maps `{}`. This also excludes hidden halfway-only tasks as the explanation for these two sessions. |
| E05 | observed | GET /video/files/{affected-session}/ and /raw/ | Both session directories contain only raw/. Guest raw directory contains 22 PNG files plus Thumbs.db; test contains 28 PNG files. Neither listing contains MP4, WAV, or AEPX files. No customer images downloaded. |
| E06 | observed | GET /video/files/uswindow-261113-G2-204721/raw/; GET /video/render/task/uswindow-261113-G2-204721 | Successful Room 2 control has in-game/webcam MP4, talk WAV, generated AEPX files and 10 completed render tasks. |
| E07 | observed | GET /video/holodecks/1/healthz; Consul catalog nodes/services; Nomad video/server job and allocations | Current Room 1 talk, in-game, and webcam checks healthy. Job image confirms 1.6.5. Current health does not establish historical capture health. |
| E08 | observed | Nomad fs ls and fs cat, alloc/logs/docker.stdout.196, both squidgame/server allocations 3a2d0013-b45f-cd1d-e5e5-f08a4176a115 and 43bd69c4-5c43-2492-ea5a-4a73dfd39f1c | Both complete files read (~10 MB each); scoped session entries show progress and result requests. No errors among extracted exact-session matches; default-settings creation warnings present. This is not Unity/recorder log coverage. |
| E09 | observed | git show video/v1.6.5:apps/video/server/cores/render/render.go; holodeck/holodeck.go; infras/postgres/task/tasks_postgres.go | Render persists a default task before dependency evaluation/queue publication. Room list derives from task records and omits halfway-only sessions. Empty task maps narrow the failure to absent task registration or subsequent deletion, rather than an ordinary retained queued task. |
| E10 | observed | Static server source default.conf and Consul service tags | /video/files/ maps directly to Session/. Initial /video/files/Session/... probes returned 404 because Session was incorrectly repeated; corrected paths succeeded. One guessed control ID also returned 404 and was excluded; final control came from actual records. |
| E11 | observed | Tool discovery and forwarding output | Production Grafana MCP tools absent. User informed connection recovery requires restart. Helper opened forwards but exit trap failed with PROBE_PIDS[@]: unbound variable; initial nonpersistent forwards disappeared. Reopened with persistent parent, verified API access. |
| E12 | inferred | E04–E09 | Likely Room 1 recording/render-submission failure upstream of queue processing. Exact trigger, whether tasks were never created versus subsequently deleted, and where recordings might survive elsewhere remain unknown. |
| E13 | not-checked | Historical Unity/recorder logs, local PC footage, backups, settings at incident time, deletion audit | Needed to establish trigger and recoverability. No reconstruction, rerender, restart, database write, or queue mutation performed. |

## Findings

Confirmed: backend task absence explains the video-list absence for the two completed sessions. Shared storage still holds generated images, but the inspected raw directories lack recorded media. Healthy control sessions and resumed Room 1 videos weaken a store-wide rendering outage explanation. Queue leadership remediation is not indicated by this evidence.

Likely boundary: recording and render-request submission for Room 1. A disabled recording setting, failed recorder calls, or Unity-side submission problem are hypotheses only. Default-settings warnings do not prove recording was disabled. Missing shared files do not establish irreversible loss or identify a person or action.

## Actions and recovery timeline

Read-only investigation after explicit tunnel approval. No production repair attempted. Documentation prepared in a separate diagnosis worktree, preserving original changes. Session-created tunnels are cleaned up at completion; shared Grafana forwarding is left untouched.

## Outcome and remaining work

Unresolved historical trigger and recoverability. Restore production Grafana MCP and restart the agent session, then inspect Room 1 Unity/recorder and video-server logs around the two completed sessions, approximately November 13 14:02–15:35 New York. Check historical recording configuration, start/stop requests and render POST failures; check alternate local footage/backups before proposing recreation. A rerender alone cannot recreate missing source recordings. Confirm expected November 11–12 bookings separately if staff expected completed guest sessions there.

The debrief-requested i-have-adhd skill was not found in available local skill paths; no use of that skill is claimed.
