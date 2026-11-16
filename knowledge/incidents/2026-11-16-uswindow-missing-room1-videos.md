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

## Continued investigation: confirmed missing profiles

The follow-up used the user-authorized LAN tunnel and read-only WinRM, after confirming `hostname` as `r1-exp` at Consul-discovered `10.197.1.11`. The comparison PC was `r2-exp`, `10.197.2.11`, also confirmed by hostname and Consul. No files were extracted or repaired.

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E14 | observed | Nomad fs cat of in-game allocation 72d55384-3c57-b729-492a-eee27fd397a0 execute.stderr.0 and execute.stdout.0; complete files saved locally, stderr parsed as JSON | In-game stderr covers November 5–15 with no invalid JSON records. No received recording POSTs on logged November 13, while November 10 and 14 have recording POSTs. Session-launched events are present November 13. This is corroboration, not sole proof of request absence across all processes. |
| E15 | observed | Nomad fs cat of talk allocation 073dbaf3-008b-7d9d-41c4-f22c772a7c27 docker.stderr.137 and .138; filtered messages | Talk health DNS failures and a connection-refused address occur near setup times. No recording POSTs found in the sampled November 13 records. File .137 has 21 non-JSON lines; these do not support exhaustive absence claims. These health failures do not explain Unity's local missing-profile errors. |
| E16 | observed | WinRM Select-String on C:\log\20261113\output_log_uswindow-261113-G1-140210.txt and output_log_uswindow-261113-T1-145940.txt | At 14:07:26 and 14:59:53 New York respectively, both logs show RecordingManager.LoadProfile: Loaded []. Both subsequently report RecordingHelper.Record: No item found for profileName, RenderingHelper.Render: No item found for profile name, and RenderingHelper.RenderRaw: No raw item found. Examples: TrainingRoom, BunkRoom_Intro, PortraitOpener_3P/6P, SquidGame:01_RLGL. |
| E17 | observed | WinRM Get-ChildItem on C:\silica\experiences\squidgame, recursive profile-name scan; Room 2 equivalent | Room 1's parent directory contains only squidgame/; recording-profile.json and rendering-profile.json are absent throughout the inspected game tree. Room 2 parent has recording-profile.json (24,018 bytes) and rendering-profile.json (19,316 bytes); its successful November 13 control log loads nonempty profiles. |
| E18 | observed | WinRM Group-Object Extension on local C:\videos\20261113\<affected-session>; no images downloaded | Guest directory has only 22 PNG files; test only 28 PNG files. No recorded video/audio in either inspected local session tree. This narrows recovery options beyond the earlier shared-storage inspection. |
| E19 | observed | WinRM Select-String for RecordingManager.LoadProfile and SquidGame version across retained C:\log output logs | Last observed nonempty profile load: November 3, 15:49:42, uswindow-261103-T1-154922. First observed empty load: November 4, 10:55:08, uswindow-261104-T1-105445. Both report SquidGame V3.7.2.rc1. Subsequent inspected Squid Game logs continue empty through November 15. Not an exhaustive booking-impact count. |
| E20 | observed | WinRM later Room 1 logs, registry presence, and successful Room 2 control log | Missing HKLM\SOFTWARE\SandboxOS\Path warning also occurs in successful nonempty profile loads. It is not sufficient to explain this incident. Room 1 Squid Game guest sessions uswindow-261114-G1-154657 and uswindow-261114-G1-191950 still load [] and fail profile lookups, despite other games generating videos that day. |
| E21 | observed | WinRM System.IO.Compression.ZipFile.OpenRead and in-memory ConvertFrom-Json on C:\silica\gcp-cache\squidgame-profile ZIPs | Cached SquidGameRecording_2.3.0.zip contains recording-profile.json (24,018 bytes); SquidGameRendering_3.4.0.zip contains rendering-profile.json (19,316 bytes). Both parse as JSON. No extraction performed; file equality to Room 2 was not hash-verified. |
| E22 | observed | USWINDOW/module-squidgame.tf profiler-deployer and exp-squidgame.tf | Deployment intends those two ZIPs to be extracted into the game parent directory with no_cleanup=true, constrained to experience-server player 0. Current profile files are absent despite cached archives. This establishes intended destination, not historical execution. |
| E23 | observed | Nomad profile deploy/transfer job and allocation reads | Parent profile-deploy and profile-transfer triggers return no allocations. One recent transfer dispatch complete; another already 404. These do not establish a historical deletion or successful target extraction on Room 1. |
| E24 | not-checked | Historical deletion/deployment audit, exhaustive backup/alternate recording locations, production repair | The actor/action that removed or failed to restore files remains unidentified. No production mutation performed. |

### Confirmed cause and corrected scope

For the two completed November 13 sessions, the game-side recording and rendering profile lookups fail before the recorder/render-server handoff. The empty task maps are explained by these local lookup failures; this is not an ordinary queued render backlog. Current disk evidence identifies the two missing profile files, corroborated by a successful same-game Room 2 control.

The condition predates the originally reported dates and persists afterward. Retained logs bound the observed transition between the last-good November 3 load and first-bad November 4 load. Later successful Room 1 videos belong to other experiences and do not prove Squid Game recovered. The missing registry-path warning was investigated and contradicted as a sufficient cause by successful controls. The game version string is unchanged across the last-good/first-bad pair; this does not identify or exclude deployment activity.

Recommended future repair: an authorized operator should redeploy the matching recording/rendering profiles to the Room 1 Squid Game parent directory through the supported deployment path, after preserving directory/file-state evidence and checking current expected versions. Cached archives are available and parse, but no repair or end-to-end validation has been performed. This restores configuration for future sessions; it does not recreate historical unrecorded footage. Validate a controlled new session with explicit authorization, nonempty profile loading, actual capture, task creation/completion, and visual review. Do not restart queue infrastructure for this signature.

## Initial findings (superseded where corrected above)

Confirmed: backend task absence explains the video-list absence for the two completed sessions. Shared storage still holds generated images, but the inspected raw directories lack recorded media. Healthy control sessions and resumed Room 1 videos weaken a store-wide rendering outage explanation. Queue leadership remediation is not indicated by this evidence.

Likely boundary: recording and render-request submission for Room 1. A disabled recording setting, failed recorder calls, or Unity-side submission problem are hypotheses only. Default-settings warnings do not prove recording was disabled. Missing shared files do not establish irreversible loss or identify a person or action.

## Actions and recovery timeline

Read-only investigation after explicit tunnel approval. No production repair attempted. Documentation prepared in a separate diagnosis worktree, preserving original changes. Session-created tunnels are cleaned up at completion; shared Grafana forwarding is left untouched.

## Outcome and remaining work

Follow-up E16–E22 establishes missing game-side profiles as the immediate cause. The earlier recommendation below remains relevant only for identifying the historical removal/deployment action and alternate footage; the immediate task-registration failure is no longer unexplained.

Initial investigation: unresolved historical trigger and recoverability. Restore production Grafana MCP and restart the agent session, then inspect Room 1 Unity/recorder and video-server logs around the two completed sessions, approximately November 13 14:02–15:35 New York. Check historical recording configuration, start/stop requests and render POST failures; check alternate local footage/backups before proposing recreation. A rerender alone cannot recreate missing source recordings. Confirm expected November 11–12 bookings separately if staff expected completed guest sessions there.

The debrief-requested i-have-adhd skill was not found in available local skill paths; no use of that skill is claimed.

Follow-up tunnel handling: the user started a LAN tunnel after local sudo blocked the agent-owned attempt. Do not close the shared SSH backing forward used by that user tunnel. Close the agent-only API and scoped WinRM forwards at completion; preserve the user LAN connection.
