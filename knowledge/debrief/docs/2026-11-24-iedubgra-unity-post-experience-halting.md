---
incident: 2026-11-23-iedubgra-unity-post-experience-halting
date: 2026-11-24
store: IEDUBGRA
session_id: "codex 01a20b59-6d59-79b1-bd24-7157a27dd74f"
---

[Open the incident report](../../incidents/2026-11-23-iedubgra-unity-post-experience-halting.md)

## Time sinks

- Broad Loki queries returned polling noise and truncated logs. Filtering by Unity node, filename and a short interval exposed the transition.
- Template inputs were inside a large archive. Bounded range reads isolated the relevant entries without downloading the package.

## Asked the user, should have known

None.

## Wrong assumptions

- A different Deadwood title initially served as the completion comparator. The same-build Deadwood Mansion session in E05 showed render submission occurs before `Halted`.

## Toolkit friction

- [med] [open] [video-render-recovery] The renderer-worker selector returned no matching streams in the first window. Video-server intake logs supplied the parameters [E08].\
  Proposal. Add video-server intake as an evidence fallback and record which source returned each field.\
  Status checked 2026-11-24. Intake fallback worked for this incident. Skill behavior remains unchanged.\
  Remaining. Verify the fallback on another title and consolidate it into the skill.
- [low] [open] [diagnose toolkit] The store HTTPS gateway used a private CA. The initial verified request failed, and subsequent checks used the approved loopback tunnel [E06–E07].\
  Proposal. Document obtaining the trusted store CA for read-only collectors.\
  Status checked 2026-11-24. Runtime TLS verification failed with the local trust bundle.\
  Remaining. Identify and test a supported CA path.

## Blind spots

- Unity game implementation, exact reason for the second pause or restart, and composition-level input coverage [E10].

## Platform facts learned

| Fact | Evidence | Verified or inferred |
| --- | --- | --- |
| Deadwood Mansion can submit DGE renders while a session is still `Halting`. | E05 | Verified for the observed build. |
| Relaunch can report a state the experience server rejects after `Halting`. | E03 | Verified for this session. |
| Render intake logs expose template, composition and JSON field values when worker logs are unavailable. | E08 | Verified for the selected requests. |

## What helped

- The same-build control located render submission in the Unity timeline.
- The three-player birthday control established concrete payload fields, with Dublin history corroborating the trailer.
