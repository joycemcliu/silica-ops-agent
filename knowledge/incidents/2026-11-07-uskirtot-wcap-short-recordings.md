---
title: USKIRTOT birthday selfie contains black sections from incomplete recordings
incident_date: 2026-11-07
incident_time_range: "14:35:40 to 14:48:42"
timezone: America/Los_Angeles
store: USKIRTOT
runbook: ../runbooks/docs/wcap-short-recordings.md
---

## Report, impact and scope

- Session `uskirtot-261107-G4-135631`, Stranger Things, Holodeck 4: rendered birthday selfie contains black sections. The first two raw in-game clips were reported as approximately 114 KB and 115 KB.
- Direct inspection confirmed both clips contain only one nonblack gameplay frame. The third clip also falls short of its requested duration.
- Diagnosis completed; no recovery or production change was performed. Capture initialization delay is the leading explanation; its precise cause remains unconfirmed.

## Instance details

| Item | Value |
| --- | --- |
| Configured repositories | SILICA_REPO=../silica; SILICA_ENV_REPO=../silica-environments, resolved from ops-agent root; values held fixed |
| Repository state | Both external repositories clean on master at inspection; source c6d2e0a7d, environments c134a585; neither updated |
| Store / environment / host | USKIRTOT / prod / r4-exp; observed caller address 10.15.4.11 |
| Recorder / release | video-dge/in-game-recorder-4; job version 10; video-dge 0.4.6; release Dockerfile packages WCap v1.0.1, runtime binary not independently attested |
| Incident allocation | 0c772671-4f2d-94d8-9905-b3ba19135a00; historical node ID 68cdd21e-388b-dc30-3f2e-7048602a9a0b |
| Later allocation | 791424ff-def0-6e4a-eb07-278529737f1c, started 2026-11-08T02:40:26.7882805Z; why it replaced the original was not investigated |
| Render | STC_selfie; StrangerThings_1.4.0; BirthdaySelfie_en.aepx.tmpl; composition cctv_5p; retry=1, completed |
| NAS evidence | /silica-modules-data/video/Session/uskirtot-261107-G4-135631/ |
| Historical log file | C:\silica-infra\nomad\data\alloc\0c772671-4f2d-94d8-9905-b3ba19135a00\alloc\logs\execute.stderr.0 |
| Local scratch | /private/tmp/uskirtot-*; diagnostic downloads, metadata, extracted frames; not durable archival storage |
| Grafana | sandbox_prod_grafana, silica-loki; user restored the connection after earlier MCP handshake failures |

## Evidence ledger

Grouped entries cover repeated invocations and retries of the same command/query family. Only successful observations support conclusions; no credentials are reproduced.

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E01 | observed | Read root config.env, RTK.md, docs/diagnose_agent.md, store AGENTS.md, toolkit, platform/runbook indexes and authoring/debrief instructions; git status/log in configured repositories | Applied store timezone and read-only diagnosis workflow; no matching recording-duration runbook existed |
| E02 | observed | scripts/grafana-mcp-forward.sh status/start; tool discovery; list_mcp_resources/list_mcp_resource_templates for sandbox_prod_grafana; lsof on port 60008; targeted rg of MCP URL | Helper lacked flock; MCP initialization initially failed despite a later listener. User restored MCP; datasource listing and Loki queries subsequently succeeded. Missing shared diagnose Python prevented an optional settings parser; no alternative Python or configuration edit used |
| E03 | observed | scripts/store-port-forward.sh --cluster USKIRTOT --env-root <resolved SILICA_ENV_REPO>; later --node 2 inside a held terminal | Authenticated with approved escalation; forwarded Nomad/Consul/HTTPS/Postgres. Bash reported PROBE_PIDS[@]: unbound variable. A held terminal kept background tunnels available; no helper edits made |
| E04 | observed | Read-only curl of /video/holodecks/4/session/uskirtot-261107-G4-135631 and /video/render/task/uskirtot-261107-G4-135631 through printed HTTPS address | Birthday selfie completed without a reported render/upload error; final render ended 22:48:37.536355Z |
| E05 | observed | Read-only Nomad jobs/job/allocations/node-allocations APIs; job allocations also queried with all=true | Current recorder release/config confirmed; only later recorder allocation listed. Absence from Nomad did not imply historical logs were unavailable in Loki |
| E06 | observed | Source inspection of static-web/default.conf; read-only curl /video/files/uskirtot-261107-G4-135631/ and /raw/; download three in-game clips, three webcam clips, rendered selfie and resolved AEPX | NAS sizes matched downloaded files; resolved template referenced affected files. Initial extra Session path returned 404; GCS URL returned 403; successful NAS reads supplied evidence |
| E07 | observed | rtk proxy ffprobe -v error -show_entries format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,duration,nb_frames,bit_rate -of json <downloaded-clip>; analogous webcam and format_tags probes | See measurements below. Both one-frame in-game files declare 25 fps, 1920x1080 H.264 and AAC |
| E08 | observed | Local FFmpeg extraction of one frame from each in-game clip; image inspection | First two sole frames show normal gameplay; sampled third frame also normal. These are not all-black source frames |
| E09 | observed | rtk proxy ffmpeg -hide_banner -i <rendered-selfie> -vf blackdetect=d=0.2:pix_th=0.1 -an -f null - | Rendered duration 38.44 s; black spans include 2.04–3.48, 5–7.2, 9.36–11.96 and 24.76–28.36 s, plus shorter ending spans. Not every span independently attributed to one input or distinguished from intentional transitions |
| E10 | observed | git show video-dge/v0.4.6:apps/video-dge/in-game/internal/adapters/recorders/wcap/{cmd.go,wcap.go}; corresponding media/verify_audio_video.go and Dockerfile; upload/service.go | Timer begins immediately after cmd.Start(), without capture-readiness handshake. Validator checks dimensions/fps but not requested duration/frame count. Source notes WCap can return zero even on failure; no runtime binary attestation |
| E11 | observed | MCP list_datasources(type=loki), list_loki_label_names/values; query_loki_stats for {cluster=~"(?i)uskirtot"} | Discovered silica-loki and cluster label; confirmed retained data before narrowing queries |
| E12 | observed | Loki {cluster="USKIRTOT"} filtered by session and birthday; then {cluster="USKIRTOT",job="video-dge/in-game-recorder-4"}, 22:35:40–22:37:10Z, forward, limit 100 | Broad search truncated; narrowed recorder query returned all 44 lines without truncation. Requested durations, timeout stops, normal exits, uploads and Success reports confirmed |
| E13 | observed | Loki {cluster="USKIRTOT",job="unity-output-log",node_name="r4-exp"} filtered for birthday/recording/errors, 22:35:40–22:36:50Z | Unity requested 4/7/30 s; explicit Unity stop calls occurred about two seconds after those windows. Recorder timers, rather than those later calls, initiated the observed stops |
| E14 | observed | Loki recorder query filtered filename=~".*stdout.*"; node query for WCap/capture/encoder; node query for device_removed, device_hung, DXGI_ERROR, nvenc, hardware errors, display-driver errors and WCap stop timeout | No WCap stdout entries or matching device/force-kill errors returned in the bounded interval. Does not rule out all driver faults or prove capture readiness |
| E15 | observed | Loki recorder starting-recording entries for session, 22:10–22:38Z; generate_deeplink | Twelve AudioVideo requests found, including earlier gameplay and three birthday shots. Earlier request logs alone do not establish earlier media completeness |
| E16 | observed | scripts/store-port-forward-cleanup.sh --store USKIRTOT --node 2, elevated process discovery; select two session-created forwards; exit held terminal; repeat cleanup during closeout | Both created forwards killed; closeout found none. Shared Grafana forwarding left running. A sandbox-only process listing had initially failed to see the forwards |
| E17 | inferred | E07/E10/E12 and MP4 creation timestamps | Roughly eight seconds of initialization before useful capture is the leading explanation; first-frame readiness was not logged |
| E18 | not-checked | WCap internal startup timing, GPU/audio/encoder initialization, resource metrics, controlled short-shot reproduction and a candidate fix | Exact initialization bottleneck and remediation effectiveness not established |

### Media measurements

| Clip | Bytes | Requested in-game duration | In-game frames / duration | Webcam duration | In-game MP4 creation_time (UTC) |
| --- | ---: | ---: | --- | ---: | --- |
| birthday_1 | 116100 | 4 s | 1 / 0.040000 s | 4.999989 s | 2026-11-07T22:35:56Z |
| birthday_2 | 117263 | 7 s | 1 / 0.040000 s | 7.999989 s | 2026-11-07T22:36:04Z |
| birthday_3 | 22486566 | 30 s | 544 / 21.763400 s | 30.999956 s | 2026-11-07T22:36:19Z |

Creation metadata supports the timing hypothesis but does not measure first-frame readiness directly. The third request is short by 8.2366 seconds.

## Findings

- Confirmed: incomplete in-game footage predates rendering. The first two files cannot supply the expected moving footage; the third is also short.
- Confirmed: requests were not mistakenly set to one frame. Unity and recorder logs agree on 4, 7 and 30 seconds.
- Confirmed: the duration timer measures process lifetime without waiting for capture readiness. Successful exit, upload and recording status did not detect missing footage.
- Inferred: slow WCap initialization consumed the two short windows and part of the third. MP4 creation times are roughly eight seconds after process launch; the longer clip loses a similar interval.
- Unknown: why initialization was slow. No direct WCap readiness/stdout diagnostics or controlled reproduction were available.
- Rerendering unchanged inputs cannot recover absent motion. No attempt to replace, extend or fabricate footage was made.

## Actions and recovery timeline

Log timestamps below are PST on the incident date; investigation/cleanup happened later in this chat.

| Timestamp | Action actually taken | Result | Backup / rollback reference |
| --- | --- | --- | --- |
| 14:35:48.124–14:35:52.130 | Recorder launched first WCap process; timer sent stop after 4 s | Process exited at 14:35:56.486; one-frame file uploaded and reported Success | Historical observation |
| 14:35:56.154 | Second request found first process still active; repeated stop | Closed stdin warning; first process then exited normally | Historical observation; no evidence of force-kill |
| 14:35:56.587–14:36:03.593 | Recorder launched second WCap process; timer stopped after 7 s | Exited 14:36:04.944; one-frame file uploaded and reported Success | Historical observation |
| 14:36:11.534–14:36:41.539 | Recorder launched third WCap process; timer stopped after 30 s | 21.7634 s of media; exit without reported error | Historical observation |
| 14:48:37.536 | Birthday selfie rerender finished | Completed status despite incomplete inputs | Historical observation; agent did not trigger it |
| Investigation and closeout; exact wall-clock not separately recorded | Read-only source/API/log/media checks; closed own store forwards | Diagnosis complete; no service, deployment, recorder or production-file changes | No production rollback needed |

## Outcome and remaining work

- Diagnostic investigation closed; affected guest footage was not repaired. Both technical and short non-developer reports were delivered.
- Engineering follow-up: instrument WCap initialization/first-frame readiness, pre-initialize before short shots and synchronize scene/capture timing, and validate duration/frame count against the requested shot.
- Moving the timer alone would not recover the intended scene beginning if capture is still starting late; readiness coordination needs testing.
- Controlled reproduction and a reviewed fix remain unperformed. Do not describe the startup bottleneck as a confirmed GPU/driver defect.
- Local scratch media remains subject to normal temporary-file cleanup; production originals were not changed. Draft knowledge records are not committed or pushed.
