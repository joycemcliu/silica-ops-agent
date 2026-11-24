---
title: Deadwood Origins highlights omitted webcam shots after a gameplay resume
incident_date: 2026-11-23
incident_time_range: "10:26:40 to 13:26:51"
timezone: Asia/Hong_Kong
store: HKCWBMID
runbook: ../runbooks/docs/dwo-highlight-missing-shot-aliases.md
---

## Report, impact and scope

Both guest highlights in Room 1 session `hkcwbmid-261123-G1-102640` were reported missing webcam footage. Support reported that rerendering and restarting video and experience servers did not restore the footage. The investigation covered this session and historical mapping records from the same store. Broader impact and customer playback after recovery were unverified. [Slack escalation](https://sandboxvr.slack.com/archives/C046N4EMYRY/p1795413467216909) · [Support ticket](https://sandboxvr.freshdesk.com/a/tickets/348417)

## Instance details

| Item | Value |
| --- | --- |
| Experience and template | `DeadwoodOrigins_1.1.1`, `DWO_Highlight.aepx.tmpl` |
| Highlight items | `P1_Highlight` used `cctv_b`. `P2_Highlight` used `cctv_a`. |
| Relevant jobs | `unity-output-log` on `r1-exp`, `video-dge/webcam-recorder-windows-1`, `video-dge/renderer`, `video/server` |
| Deployment source | HKCWBMID Terraform enables MediaMTX webcam capture and pins the video DGE module to 0.4.6. Runtime binary version was unverified. |
| Evidence | Production `silica-loki`, a selected raw clip pair and generated After Effects projects from the support transfer. Temporary local copies were removed. |

## Evidence ledger

Times below are Hong Kong time unless otherwise stated. Queries ran through the read-only production Grafana connection.

| ID | Tag | Command, query or evidence source | Result |
| --- | --- | --- | --- |
| E1 | observed | Slack escalation, session logs and store configuration | Room and session were identified. Session creation logged at 10:26:40. DGE webcam capture and MediaMTX were configured. |
| E2 | observed | Webcam recorder logs filtered by session and `starting recording`, `recording result`, or `reported recording status` | 18 starts, 18 recording results and 18 reports of `Success`. The transfer manifest listed 18 normal webcam clips and 18 matching debug clips. |
| E3 | observed | `ffprobe` and FFmpeg black and freeze detection on the Wave2-1 normal and debug MP4s | The normal clip decoded 434 H.264 frames over 14.00 s. The debug clip decoded 393 over 13.10 s. Neither triggered the configured black or freeze detector. Unity stopped this shot at about 13.6 s. |
| E4 | observed | Renderer completion and NAS upload logs for items matching `P[12]_Shot[0-9]+`; inspection of both generated Shot 1 projects | Ten shot MP4s per player were logged as uploaded. Both Shot 1 projects referenced the same normal Wave2-1 webcam MP4. Playback of the rendered Shot MP4s remains unverified. |
| E5 | observed | Room 1 Unity output around the exit, resume and `SafetyNetRenderCalls` | Unity logged `OnApplicationQuit` at 11:00:41, resumed at `Wave5_4` at 11:00:56 and invoked the highlight safety net for both players at 11:04:40. |
| E6 | observed | Video-server original request logs and renderer completion logs for both highlight items | Both original requests and all three observed rerender completions carried only the player info and portrait aliases. All omitted `highlight_1_ig_video.mp4`, `highlight_2_ig_video.mp4` and `highlight_3_ig_video.mp4`. |
| E7 | observed | Generated `P2_Highlight-DWO_Highlight_1795403879.aepx` XML | The three video file references resolved to the experience folder. The project contained no player shot or webcam file references. The renderer source shows how alias lookup and experience-folder fallback can produce this result. |
| E8 | observed | Same-store, same-version original highlight completion logs from Nov 19–22 | All 11 returned historical records included all three video aliases. For session `hkcwbmid-261122-G1-194638`, the ordered shots were P1 2, 9, 8 and P2 5, 2, 1. |
| E9 | observed | Local video-server source, render request data and store gateway documentation | The regular rerender path reuses the saved task data. The render endpoint accepts an updated alias object and resets the task for the existing session and item. |
| E10 | not-checked | Live NAS playback and replacement render | The six proposed shot outputs were not played back and recovery requests were not submitted by the agent. A later bounded log search found no additional highlight completions through Nov 24 at 10:30 HKT. |

## Findings

The immediate failure was in highlight assembly. Unity submitted both safety-net requests without aliases for the rendered player shots. After Effects completed the renders with experience-folder media references for the three P2 slots inspected. The raw webcam sample and the upstream shot renders demonstrate that capture and shot assembly ran, with scope limited to the files and logs inspected.

The resume preceded the fallback and is a plausible trigger. The cause of the Unity exit, why normal shot selection did not finish, and whether the selection was lost or had never been committed remain open.

## Actions and recovery timeline

| Timestamp | Action or event | Result |
| --- | --- | --- |
| 10:40:05–11:00:19 | Renderer completed and uploaded intermediate player shots | Ten outputs per player recorded in NAS upload logs. |
| 11:00:41–11:00:56 | Unity exited and resumed | Gameplay resumed at `Wave5_4`. |
| 11:04:40 | Unity submitted both highlights via safety net | Requests omitted all three player-shot aliases. |
| 11:06:43 and 11:08:30 | Original P1 and P2 renders completed | Support reported missing webcam footage. |
| 11:19:19 and 11:19:29 | P1 and P2 rerenders completed | Requests still lacked the aliases. |
| 13:26:50 | Additional P2 rerender completed | Request still lacked the aliases. |
| Diagnosis follow-up | Prepared two replacement JSON bodies for the operator | Proposed shots 1, 5 and 9 for each player span three waves and had upload records. The original intended order was unknown. |

## Outcome and remaining work

Recovery is unverified. An authorized DGE operator can preview the proposed or otherwise selected shot MP4s, preserve the existing highlight outputs, submit two corrected render requests, and verify both resulting videos. Investigate DWO shot selection across gameplay resume and ensure the safety net can rebuild the aliases or report an incomplete highlight.
