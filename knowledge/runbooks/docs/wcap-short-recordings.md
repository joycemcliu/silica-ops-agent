---
title: Short WCap recordings pass validation and leave black render sections
slug: wcap-short-recordings
services: [video-dge, video-server, unity]
tags: [recording, duration, black-frame, wcap]
status: reviewed
last_verified: 2026-11-09
applies_to:
  video_dge_source: "0.4.6"
  capture_path: Windows AudioVideo via WCap
  bundled_wcap_source: "v1.0.1; runtime binary not independently attested"
source_incidents:
  - ../../incidents/2026-11-07-uskirtot-wcap-short-recordings.md
---

## Symptoms

- Rendered selfie has black sections; some raw in-game MP4s are much smaller than neighboring shots.
- Short raw files can decode successfully and report the configured frame rate while containing only one frame. An apparently normal longer clip can also be shorter than requested.
- Recording and rendering can both be marked Success/completed.

## Safety and anti-anchoring

- Use the diagnosis toolkit and existing access authorization; all triage below inspects existing recordings or historical logs.
- Small size alone does not establish black imagery, corruption or incomplete upload. Measure duration/frame count and inspect available frames.
- A valid container, configured fps, zero exit status or completed render alone does not prove complete capture.
- A later Nomad allocation does not imply original logs have disappeared from Loki.
- MP4 creation metadata alone does not establish exact first-frame readiness. Separate observed timer/exit events from inferred initialization delay.

## Triage (read-only, in order)

These are parameterized equivalents of checks executed in the source incident. Replace placeholders with observed values. Run Loki queries through the configured MCP connection, with explicit incident start/end times and forward direction. Discover the datasource and labels first; verify queries are not truncated.

1. Inspect each affected existing file with the same probe options used in diagnosis:

   ```bash
   ffprobe -v error -show_entries format=duration,size,bit_rate:stream=index,codec_name,codec_type,width,height,r_frame_rate,avg_frame_rate,duration,nb_frames,bit_rate -of json '<raw-clip>'
   ```

   Good: usable frame count and duration match the intended shot within an explained tolerance. Bad: one frame, near-zero duration, absent stream or substantial shortfall. Compare related webcam footage and the actual requested duration; webcam padding is not itself the recording contract.

2. Inspect request, timer, exit and upload records for the recorder identified by store configuration:

   ```logql
   {cluster="<STORE>",job="<recorder-job>"}
   ```

   Good: requested duration, useful capture duration and lifecycle agree. Bad: `Recording duration reached, stopping wcap` occurs before evidence of useful capture, or another request finds the old recording still stopping. `failed to send 'q' to wcap: write |1: file already closed` after an earlier stop is not by itself proof of the initial failure.

3. Confirm the scene requested the intended duration:

   ```logql
   {cluster="<STORE>",job="unity-output-log",node_name="<host>"} |~ "(?i)birthday|recording|record.*video|wcap|error|exception"
   ```

   Good: Unity and recorder durations agree. Bad: wrong duration/type, duplicate requests or an earlier explicit stop. Compare the timer stop with Unity stop timing before attributing interruption to a user or the game.

4. Inspect existing capture diagnostics and candidate device/timeout errors:

   ```logql
   {cluster="<STORE>",job="<recorder-job>"} | filename=~".*stdout.*"
   ```

   ```logql
   {cluster="<STORE>",node_name="<host>"} |~ "(?i)device_removed|device_hung|DXGI_ERROR|nvenc|hardware error|display.*driver|wcap stop timeout"
   ```

   Good: diagnostic output identifies first-frame readiness and any exit cause. Bad: errors, force-kill or missing startup diagnostics. An empty bounded query rules out only its matching log signature, not all device faults.

5. Compare the pinned release source and render dependencies. Under `SILICA_REPO/apps/video-dge/in-game/internal/`, inspect `adapters/recorders/wcap/cmd.go`, `adapters/recorders/wcap/wcap.go`, `adapters/media/verify_audio_video.go` and `applications/upload/service.go`, plus the resolved render template.

   Good: readiness coordination and duration checks exist, and template inputs are complete. Bad: timer starts at process launch; validation accepts dimensions/fps without checking duration/frame count; the template uses already-incomplete footage. Confirm source version against deployed configuration.

## Likely causes

| Cause                                           | Evidence that confirms                                                                                                        | Evidence that rules out                                                                                                                                                                   |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Initialization consumes short recording windows | Delayed capture readiness, timer starts at launch, short requests yield a frame while longer requests lose a similar interval | Timely first-frame capture and complete media over the requested interval                                                                                                                 |
| Early or overlapping stop                       | Explicit earlier stop, replacement request or force-kill tied to affected recording                                           | In source incident, timer expired at requested deadlines and no matching force-kill was observed; overlap happened during first clip shutdown, not before its timer                       |
| Wrong request duration                          | Scene and recorder request a shorter interval than intended                                                                   | In source incident, both requested the intended shot durations                                                                                                                            |
| Validation gap hides incomplete capture         | Files contain too few frames but pass fps/dimension checks and receive Success                                                | Validation compares actual duration/frame count to request and rejects incomplete footage                                                                                                 |
| Downstream rendering alone                      | Complete, visually valid raw footage but missing render sections                                                              | Source incident raw media was already incomplete; rendering was not the origin of the missing motion                                                                                      |
| Transfer corruption                             | Original local media complete but stored copy differs or fails probing                                                        | Not independently excluded by byte/hash comparison in source incident; successful container decoding and normal upload/exit support a capture-time problem but are not an integrity proof |
| GPU, audio or encoder initialization defect     | Direct startup diagnostics or controlled reproduction identify bottleneck                                                     | Not established or ruled out by absence of selected error strings                                                                                                                         |

## Remediation (HUMAN executes; agent never runs)

No remediation was implemented or tested in the source incident.

- **Coordinate capture readiness with short scenes.** Guard: identify target release/rooms and reproduce during an approved idle window; do not merely extend timers into unrelated scenes. Backup: preserve deployed revision/configuration and original evidence. Action: pre-initialize capture, expose readiness/first-frame timing and coordinate scene start before measuring duration. Risk: shifted scene timing, extra resource use and altered recorder lifecycle. Rollback: redeploy the recorded prior revision/configuration and verify intended timing.
- **Reject incomplete recordings.** Guard: define expected duration/frame tolerance from the shot request and preserve original files; do not silently fabricate frames. Backup: preserve current validator behavior/revision and representative media. Action: add duration/frame-count validation and an actionable failure status. Risk: legitimate short clips could be rejected; existing weak checks can mask failures, so test both cases. Rollback: restore the prior validator revision through reviewed deployment and retain evidence.
- **Handle affected guest output through an approved recovery workflow.** Guard: identify the exact session/items and obtain approval before modifying media. Backup: retain original raw and rendered files. Action: use verified complete alternative footage if available or escalate the incomplete recording; rerender unchanged inputs cannot recover missing motion. Risk: wrong-scene substitution or altered guest output. Rollback: restore original files/output references. No alternative in-game recording was verified in the source incident.

## Validation checklist

Machine checks:

- [ ] Logs show scene request, capture readiness, first useful frame, timer stop and exit in the intended order.
- [ ] Actual frame count and duration agree with requested shot duration within documented tolerance.
- [ ] One-frame/truncated files receive an actionable failure instead of Success.
- [ ] Complete short and long recordings still pass validation and upload.
- [ ] Reviewed fix is exercised on the affected capture path; service health alone does not prove media correctness.

Human-only checks:

- [ ] Raw footage contains the intended scene beginning and ending with visible motion.
- [ ] Rendered output uses the expected scenes without unintended black sections.
- [ ] Any intentional black transitions are distinguished from missing footage.

## Not yet verified

- Inferred: initialization delay is the leading mechanism; source incident had no direct first-frame/readiness log.
- not-checked: underlying GPU/audio/encoder/resource bottleneck, runtime WCap binary attestation, controlled reproduction and proposed remediation.
- not-checked: durable media integrity comparison between original local output and NAS.
- not-checked: effective fix, sustained recording performance and recurrence-based human verification.
