---
incident: 2026-11-23-dwo-highlight-missing-shot-aliases
date: 2026-11-24
store: HKCWBMID
session_id: "codex 01a20b59-d6fd-7571-87e0-491a2c96d6d5"
---

[Incident report](../../incidents/2026-11-23-dwo-highlight-missing-shot-aliases.md)

## Time sinks

- Evidence download | Unmeasured | Comparing the original and historical alias maps earlier would have narrowed the file retrieval to a player-shot project, a highlight project and one webcam pair.

## Asked the user, should have known

- None.

## Wrong assumptions

- The label `webcam_debug` and the support description first suggested checking for missing capture. The recorder logged normal and debug variants, and the highlight request aliases identified the downstream failure.

## Toolkit friction

- [med] [open] [Video Render Recovery skill] The workflow reconstructs requests using representative historical logs. Per-player shot selections varied across the historical records, and the affected task already exposed the exact template, composition and missing aliases.\
  Proposal — Prefer the affected task when available and label any replacement selections that differ from or substitute for unknown original choices.\
  Status checked 2026-11-24 — Repository instructions and incident telemetry reviewed. The recovery payload was prepared in chat.\
  Remaining — Update the skill and validate it on a recurrence.
- [low] [open] [Slack evidence attachments] The listener supplied attachment metadata. Artifact inspection required separate retrieval of a small subset from the transfer.\
  Proposal — Add a documented path for retrieving selected authorized evidence files with isolated storage and cleanup.\
  Status checked 2026-11-24 — Selected download and cleanup were completed for this incident.\
  Remaining — Document a reusable workflow.

## Blind spots

- Original shot selections, reason for Unity exit, effect of resume on selection state, and guest playback after recovery. The requester relayed a Unity bug confirmation and supplied Eric’s reply. Eric expects a new build may be needed. The exact defect and fix build remain unverified.

## Platform facts learned

| Fact | Evidence | Status |
| --- | --- | --- |
| The three DWO highlight aliases select already rendered per-player shot MP4s. | Same-store historical render events and affected project XML. | Verified |
| An ordinary rerender reuses the stored alias map. | Original and rerender events and video-server source. | Verified |

## What helped

- Same-store historical alias maps showed the expected binding format.
- Generated project XML exposed the actual file paths used after template resolution.
