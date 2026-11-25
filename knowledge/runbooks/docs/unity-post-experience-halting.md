---
title: "Unity post-experience flow stalls in Halting"
slug: unity-post-experience-halting
services: [unity, experience-server, session-server, video-server]
tags: [session, post-experience, video, missing-tasks]
status: draft
last_verified:
applies_to:
  unity_observed_build: "Deadwood Mansion V8.1.1.rc3"
  video_module_observed_config: "1.6.5"
  template_resource: "DeadwoodMansion_6.8.0"
source_incidents:
  - ../../incidents/2026-11-23-iedubgra-unity-post-experience-halting.md
---

## Symptoms

Guests finish gameplay and the room stays in `Halting` after pose capture. The Video tab has no corresponding entry. Unity may submit `PostExperience` again on relaunch and receive HTTP 409.

## Triage (read-only, in order)

1. Use the [session inspection guide](../../platform/docs/domains/session-inspection.md) to confirm the exact session, room, and experience. In production Loki, query the status timeline. Affected sessions remain in `Halting` until intervention. A normal completion progresses beyond `Halting`.

   ```logql
   {cluster="<cluster>",job="session/server"} |= "<session>" |= "SessionStatusChangedEvent"
   ```

2. Check the full task API with `GET /video/render/task/<session>` and inspect video-server intake logs over the incident window. An empty task map and no matching intake log point upstream of task creation when the log stream has same-window activity. Existing tasks can be inspected with the [video inspection guide](../../platform/docs/domains/video-inspection.md). A missing Video tab entry alone leaves task creation uncertain.

   ```logql
   {cluster="<cluster>",job="video/server"} |= "<session>" |~ "UpdateStatus.*Success|Render request"
   ```

3. Find the Unity host stream for the exact session and compare it with a successful same-build session. Trace pose capture, `RemoveGear` load, pauses, restarts, render submission, `PoseCapture FlowFinish` and `ReportExperienceHalted`. Look for `PoseCapture Stop` after `EndGameRestart` in the affected session logs. Successful Deadwood Mansion can submit renders before it logs `ReportExperienceHalted`. A disconnect near the transition warrants a client log check. A logged scene load establishes that the transition reached the clients observed.

   ```logql
   {cluster="<cluster>",job="unity-output-log",node_name="<experience-host>"} | filename =~ ".*<session>.*" |~ "Capture pose Success|RemoveGear|disconnect|Halting|Halted|Pause Game|Force Resume|EndGameRestart|PoseCapture|RenderItem"
   ```

4. Correlate any HTTP 409 from the progress route with the relaunch and stored status timeline. `Invalid status transition` with reported `PostExperience` and stored `Halting` explains why the relaunch cannot rewind progress. The pre-relaunch Unity timeline provides evidence for the original stall.

   ```logql
   {cluster="<cluster>",job="unity-error-log"} | filename =~ ".*<session>.*" |= "Invalid status transition"
   ```

5. If someone requests recovery, list filenames with `GET /video/files/<session>/raw/` over an approved store connection. Compare with the configured recording and rendering profiles and the exact versioned template, plus matching video-server request logs. The successful request should match experience, language, birthday variant, and player count. Confirm composition-level input needs before submitting. A successful recording status establishes the status the service received. File availability, integrity, and composition coverage need their own checks.

## Likely causes

| Cause | Evidence that supports it | Evidence that weakens it |
| --- | --- | --- |
| Unity post-experience flow interrupted before render submission | Pose capture and scene load succeeded. Completion and render calls are missing, with an interruption visible in Unity. | Matching render intake or evidence of normal completion shifts the investigation downstream. |
| Relaunch resumed at an earlier status | Relaunch reports `PostExperience` and persisted status is `Halting`, with HTTP 409. | Relaunch reports a permitted status and the update succeeds. |
| Renderer or queue stall | Registered render tasks remain queued or fail with stage evidence. | Empty task map and no intake in an active log stream support an upstream explanation. |
| Missing recording or rendering profile | Missing deployed profiles, empty loads or item lookups, with a successful comparator. [Missing registration runbook](missing-video-task-registration.md) | Successful recording submissions and a populated cache weaken a broad profile failure theory. The cache does not establish what Unity loaded. |

## Remediation (HUMAN executes; agent never runs)

If a room requires manual clearance, confirm the exact session and room, ensure guests have exited, and capture the status, logs, task map and media inventory. Use the supported operator procedure only with authorization. Killing the session ends its active state and has no validated rollback. Stop if the room or session identity is in doubt.

For video recovery, preserve the raw recordings and export the current task state. Review the exact target-specific payload and the composition's inputs before submitting. Duplicate tasks or uploads, incomplete footage and publishing to the wrong booking are possible. Establish a task and output rollback for the exact operation with the video owner before proceeding. No generic rollback or recovery execution was validated.

## Validation checklist

### Machine checks

- [ ] Verify the intended session reached a terminal status and the room can start a later session if clearance was required.
- [ ] In an authorized control, verify the Unity completion markers and video-server intake match the target session.
- [ ] For authorized video recovery, verify both planned tasks reach completion and report output URLs.

### Human checks

- [ ] Confirm the affected guests and booking before any publishing action.
- [ ] Review recovered clips for correct guests, complete footage and usable audio.

## Not yet verified

- Which pause, resume, disconnect or restart behavior interrupted the original flow.
- Unity game source and reproduction of the incident sequence.
- Whether each absent source-file reference is required by the chosen composition, whether alternate files exist, and whether recovery succeeds.
