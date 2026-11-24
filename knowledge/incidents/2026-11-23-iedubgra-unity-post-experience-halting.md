---
title: "Dublin Deadwood Mansion session stalled after pose capture"
incident_date: 2026-11-23
incident_time_range: "13:25:05 to 14:16:39"
timezone: Europe/Dublin
store: IEDUBGRA
runbook: ../runbooks/docs/unity-post-experience-halting.md
---

## Report, impact and scope

Dublin Room 3 staff reported that guests finished Deadwood Mansion, but Silica would not end the session and the Video tab showed no guest videos. Evidence covers one birthday session. The live session record was later `Killed` and the live render task map was empty. [Slack issue](https://sandboxvr.slack.com/archives/C046N4EMYRY/p1795446583675769) · [Freshdesk ticket 348496](https://sandboxvr.freshdesk.com/a/tickets/348496)

## Instance details

| Item | Value |
| --- | --- |
| Session | `iedubgra-261123-G3-132505`, Room 3, three player records, birthday event |
| Runtime | Deadwood Mansion `V8.1.1.rc3`, host `r3-exp`, with player 1 on `spc31` |
| Video | `video/server`, configured video module `1.6.5`, static resource `DeadwoodMansion_6.8.0` |
| Access | Production Grafana and approved Dublin store forwards for read-only API and archive inspection. Session forwards were closed. |

## Evidence ledger

| ID | Tag | Command, query or evidence source | Result |
| --- | --- | --- | --- |
| E01 | observed | Loki `unity-output-log` on `r3-exp`, exact session file, 13:59:50–14:05:40 UTC | Unity logged victory and game over, successful pose capture, `RemoveGear` load, pause during `Halting`, `Force Resume`, and `PoseCapture Stop` after `EndGameRestart`. No `PoseCapture FlowFinish` or `ReportExperienceHalted` appeared in the retained host logs. [Grafana · Unity timeline](https://monitoring.silicaos.com/explore?left=%7B%22datasource%22%3A%22silica-loki%22%2C%22queries%22%3A%5B%7B%22expr%22%3A%22%7Bcluster%3D%5C%22IEDUBGRA%5C%22%2Cjob%3D%5C%22unity-output-log%5C%22%2Cnode_name%3D%5C%22r3-exp%5C%22%7D%20%7C%20filename%20%3D~%20%5C%22.*G3-132505.*%5C%22%20%7C~%20%5C%22Game%20Over%7CCapture%20pose%20Success%7CRemoveGear%7Cdisconnect%7CHalting%7CHalted%7CPause%20Game%7CForce%20Resume%7CEndGameRestart%7CPoseCapture%5C%22%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221795442390000%22%2C%22to%22%3A%221795442740000%22%7D%7D) |
| E02 | observed | Loki `experience/h3-p1` and `unity-output-log` on `spc31`, exact session, 14:01:25–14:02:10 UTC | Mocap no-frame messages preceded the player 1 process relaunch. Photon later logged a player 1 departure. The host and three player PCs subsequently logged `RemoveGear` loaded. |
| E03 | observed | Loki `session/server`, `deadwoodmansion/server`, `unity-error-log`, and gateway access logs | Status advanced to `Halting` at 14:02:04. Unity relaunches reported `PostExperience`, and Deadwood Mansion rejected the regression with HTTP 409 `Invalid status transition`. A later `:kill` returned 200. The local Deadwood Mansion `syncProgress` implementation rejects transitions to a status earlier than the stored status. [Grafana · Status changes and conflicts](https://monitoring.silicaos.com/explore?left=%7B%22datasource%22%3A%22silica-loki%22%2C%22queries%22%3A%5B%7B%22expr%22%3A%22%7Bcluster%3D%5C%22IEDUBGRA%5C%22%2Cjob%3D%5C%22session%2Fserver%5C%22%7D%20%7C%3D%20%5C%22G3-132505%5C%22%20%7C%3D%20%5C%22SessionStatusChangedEvent%5C%22%22%2C%22refId%22%3A%22A%22%7D%2C%7B%22expr%22%3A%22%7Bcluster%3D%5C%22IEDUBGRA%5C%22%2Cjob%3D%5C%22unity-error-log%5C%22%7D%20%7C%20filename%20%3D~%20%5C%22.*G3-132505.*%5C%22%20%7C%3D%20%5C%22Invalid%20status%20transition%5C%22%22%2C%22refId%22%3A%22B%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221795442510000%22%2C%22to%22%3A%221795443420000%22%7D%7D) |
| E04 | observed | Loki `video/server`, exact session, Nov 23 from 13:15 to 23:59 UTC | 31 successful recording status updates in the incident window. Zero `Render request` matches across the checked range. Other sessions logged render requests in the same store. [Grafana · Target video logs](https://monitoring.silicaos.com/explore?left=%7B%22datasource%22%3A%22silica-loki%22%2C%22queries%22%3A%5B%7B%22expr%22%3A%22%7Bcluster%3D%5C%22IEDUBGRA%5C%22%2Cjob%3D%5C%22video%2Fserver%5C%22%7D%20%7C%3D%20%5C%22G3-132505%5C%22%20%7C~%20%5C%22UpdateStatus.*Success%7CRender%20request%5C%22%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221795439700000%22%2C%22to%22%3A%221795478399000%22%7D%7D) |
| E05 | observed | Same-build Oberhausen control `deobhcen-261123-G2-143247`, Unity and video server | Video server received selfie and trailer requests about 32–33 seconds after `RemoveGear` loaded and before `PoseCapture FlowFinish` and `Halted`. This control used the standard selfie template. [Grafana · Same-build control](https://monitoring.silicaos.com/explore?left=%7B%22datasource%22%3A%22silica-loki%22%2C%22queries%22%3A%5B%7B%22expr%22%3A%22%7Bcluster%3D%5C%22DEOBHCEN%5C%22%2Cjob%3D%5C%22unity-output-log%5C%22%7D%20%7C%20filename%20%3D~%20%5C%22.*G2-143247.*%5C%22%20%7C~%20%5C%22RemoveGear%7CRenderItem%7CPoseCapture%20FlowFinish%7CReportExperienceHalted%5C%22%22%2C%22refId%22%3A%22A%22%7D%2C%7B%22expr%22%3A%22%7Bcluster%3D%5C%22DEOBHCEN%5C%22%2Cjob%3D%5C%22video%2Fserver%5C%22%7D%20%7C%3D%20%5C%22G2-143247%5C%22%20%7C%3D%20%5C%22Render%20request%5C%22%22%2C%22refId%22%3A%22B%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221795443104000%22%2C%22to%22%3A%221795443147000%22%7D%7D) |
| E06 | observed | Live GETs for the session, room video details, render tasks and raw directory | HTTP 200 on each relevant route. Session was `Killed`, room video detail had `rendering_list: null`, and the task API returned an empty map. Raw listing held 16 MP4s and 15 WAVs. Room history across all five holodecks yielded `deadwood_selfie` and `deadwood_trailer` for this experience. |
| E07 | observed | Deployment configuration and Dublin gateway cache GETs for recording, rendering and After Effects packages | Rendering profile matched the English birthday selfie and trailer templates. Bounded ZIP range reads found references to portrait PNGs and `birthday_*_ig_audio.wav` for the birthday template and `deadwood_1_webcam.mp4` for the trailer. Those names were absent from the live raw directory. |
| E08 | observed | Loki `video/server` request logs across stores and Dublin history | `usnewtim-261122-G6-153759` used `BirthdaySelfie_en.aepx.tmpl`, `cctv_3p`, frame 750, and `Deadwood_DGE_Trailer_en.aepx.tmpl`, `cctv`, frame 100. Both requests used `normal` and empty dependencies, content and alias. Dublin history corroborated the trailer. [Grafana · Three-player birthday control](https://monitoring.silicaos.com/explore?left=%7B%22datasource%22%3A%22silica-loki%22%2C%22queries%22%3A%5B%7B%22expr%22%3A%22%7Bcluster%3D%5C%22USNEWTIM%5C%22%2Cjob%3D%5C%22video%2Fserver%5C%22%7D%20%7C%3D%20%5C%22usnewtim-261122-G6-153759%5C%22%20%7C%3D%20%5C%22Render%20request%5C%22%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221795379400000%22%2C%22to%22%3A%221795382700000%22%7D%7D) |
| E09 | inferred | Compare E01, E04 and E05 | Dublin's post-experience flow stopped before normal render submission. The pause during `Halting` and subsequent restart are the leading sequence to investigate. |
| E10 | not-checked | Unity game implementation and media recovery | Exact cause of the stall, contribution of the player disconnect, composition-level need for each missing file, alternate file copies, footage integrity, and recovery execution remain unverified. No store changes or render requests were made during the diagnosis. |

## Actions and recovery timeline

| Time (UTC, Nov 23) | Action or event | Result |
| --- | --- | --- |
| 13:59:51 | Unity logged victory and game over | Session advanced to post-experience. |
| 14:01:56–14:02:05 | Pose capture succeeded, Photon logged a player departure, and `RemoveGear` loaded | Silica recorded `Halting`. |
| 14:02:08–14:02:34 | Pause, force-resume and end-game restart commands appeared in Unity | Unity emitted `PoseCapture Stop` about 29 seconds after `RemoveGear` loaded. |
| 14:05:40–14:11:31 | Room host relaunched Unity for the same session | Repeated `PostExperience` updates returned HTTP 409 while the stored status was `Halting`. |
| 14:16:39 | Session kill request recorded | Session moved to `Killed`. The request log does not identify the operator. |
| Follow-up | Drafted two recovery requests against `POST /video/render` and validated their JSON | The requests use the three-player English birthday selfie and English trailer. Input completeness and recovery remain open. |

## Outcome and remaining work

The session was cleared. Guest video recovery remains open. Deadwood Mansion engineering can inspect pause and resume handling during `RemoveGear` and the effect of `EndGameRestart` on pose-flow completion and render submission. Before an authorized recovery attempt, resolve the composition input gaps and check for alternate copies. No production render POST was issued.
