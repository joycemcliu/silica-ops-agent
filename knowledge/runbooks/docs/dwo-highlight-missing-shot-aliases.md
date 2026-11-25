---
title: Deadwood Origins highlights omit rendered player shots
slug: dwo-highlight-missing-shot-aliases
services: [unity, video-server, video-dge-renderer]
tags: [highlight, webcam, alias, resume]
status: reviewed
last_verified: 2026-11-25
applies_to:
  experience: DeadwoodOrigins_1.1.1
  template: DWO_Highlight.aepx.tmpl
source_incidents:
  - ../../incidents/2026-11-23-dwo-highlight-missing-shot-aliases.md
---

## Symptoms

Player highlights render and upload, but the expected real-world footage is missing. A regular rerender can repeat the symptom when it reuses the saved request. Both recording and rendering success describe processing stages and provide limited evidence about visible content.

## Triage (read-only, in order)

1. Inspect original and rerender completion records in the configured production Grafana datasource. Use the incident time range and compare with earlier records for the same experience, template and store. Good records bind all three video slots to per-player shot files. Affected records contain only the info and portrait aliases.

   ```logql
   {cluster="<STORE>",job="video-dge/renderer"} |= "<SESSION>" |= "render completed" |~ "Item:P[12]_Highlight "
   ```

   Check `Alias:map[...]` for `highlight_1_ig_video.mp4`, `highlight_2_ig_video.mp4` and `highlight_3_ig_video.mp4`. Each value should point to a corresponding `P<N>_Shot<M>.mp4`. Historical orders vary by session.

2. Check the matching Room Unity logs for the fallback and any exit or resume. The observed failure signature was `Render Highlight P1 by safety net` and its P2 equivalent, followed by requests with missing video aliases. A resume alone establishes only event ordering.

   ```logql
   {cluster="<STORE>",node_name="<ROOM_EXP_HOST>",job="unity-output-log"} |~ "OnApplicationQuit|SafetyNetRenderCalls|Render Highlight P[12] by safety net"
   ```

3. Confirm upstream shot inputs and outputs. Review player-shot renderer completions, NAS upload records and the selected camera recorder's status for the session. Good records show shot projects resolving `SplitScreenPlayerShot_webcam.mp4` to normal raw webcam media and the matching shot MP4s uploaded. Absent upload records, unresolved project inputs, or failed or unusable raw footage warrant checking upstream capture and storage.

   ```logql
   {cluster="<STORE>",job="video-dge/renderer"} |= "<SESSION>" |= "uploaded file" |~ "P[12]_Shot[0-9]+\\.mp4" != ".aepx"
   ```

4. Compare the generated highlight project and a matching player-shot project when available. The desired highlight binds the slots to session shot MP4s. References for the slots under the experience template folder confirm fallback resolution in the inspected project. Probe a normal webcam sample if needed and use its observed start and stop to interpret duration. The recorder can emit a separate `_debug` stream-copy clip for the same shot.

## Likely causes

| Cause                                       | Evidence that confirms                                                                                                                           | Evidence that rules out                                                                                                         |
| ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- |
| Safety-net request omitted shot aliases     | Unity fallback warnings and original requests missing all three aliases. Generated highlight references experience-folder files for those slots. | The generated highlight references all selected session shot outputs.                                                           |
| Shot media missing or unusable              | Missing NAS upload, failed playback, or missing webcam content in the selected shot.                                                             | The selected stored shot MP4s play with the expected footage. A historical upload alone establishes file delivery at that time. |
| A late-game resume disrupted shot selection | A controlled reproduction or saved state comparison shows selection was lost or skipped on resume.                                               | Selection state is preserved and produces valid aliases on the same resume path.                                                |

## Remediation (HUMAN executes; agent never runs)

- Confirm the session and both highlight item names. Save the original task requests and existing published outputs using the store's approved process. Verify which inputs contain webcam footage and recover the original shot selection if available. With approval for replacement selections, choose three verified outputs per player and confirm their order.
- Use the documented video-server manual render request flow. Preserve the original request metadata, template, composition, and info and portrait aliases. Populate the three slot aliases with that player's selected filenames. Using existing item names updates the existing tasks and can replace guest-facing outputs. If rollback is needed, use the preserved prior outputs and the approved publishing process. The rollback was not exercised in the source incident.

## Validation checklist

- [ ] Both updated tasks have new request IDs, the three intended aliases and completed render and upload status.
- [ ] The generated projects resolve the selected slots to session shot files.
- [ ] Both published videos play and show the intended webcam footage in the selected segments.

## Not yet verified

- not-checked: Whether resume caused selection state to be lost or prevented its generation.
- not-checked: Live playback of the proposed six shot outputs, submission of the replacement requests, published playback and rollback.
- not-checked: Recurrence validation on other DWO experience versions.
