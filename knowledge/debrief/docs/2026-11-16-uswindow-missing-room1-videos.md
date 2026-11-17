---
incident: 2026-11-16-uswindow-missing-room1-videos
date: 2026-11-16
store: USWINDOW
session_id: "codex 01a1e3ea-b416-7810-a738-4f53ac9e99eb"
---

Prioritize the experience's Unity profile-load messages when completed sessions have no render tasks.

Evidence: [incident ledger and session inventory](../../incidents/2026-11-16-uswindow-missing-room1-videos.md). References below use its evidence IDs. No production repair was performed.

## Time sinks

Elapsed minutes were not recorded; no timing claims are made.

- Access setup: forwarding exit-trap errors, a local sudo prompt and repeated connection timeouts delayed Windows logs. Check actual tunnel readiness once before retrying WinRM (E11; follow-up access messages).
- Wrong evidence layer: experience-server progress logs confirmed gameplay but could not explain missing game-side submissions. Empty task maps should have led earlier to Unity logs and profile files (E04, E08, E16–E17).
- Incorrect static path and a guessed control ID produced avoidable 404s. Resolve the route root from service tags/source and choose controls from returned session IDs (E10).

## Asked the user, should have known

- Repeated tunnel-connected questions added friction. Check processes and bounded reachability before asking for a specific missing action. The user's consent and local sudo authentication were still required; never request their password in chat.

## Wrong assumptions

- Other games' Room 1 videos resuming was initially treated too broadly as recovery. Squid Game still failed through November 15; compare the same experience before declaring recovery (E19–E20).
- A missing registry-path warning looked relevant, but successful controls also logged it. The discriminating evidence was empty profiles plus missing files (E16–E20).
- Task counts and MP4 counts could be mistaken for request totals or final outputs. Persisted tasks, failed local lookups, HTTP attempts and raw/debug files need separate labels (E25–E27).

## Toolkit friction

1. **High — tunnel lifecycle:** helpers reported `PROBE_PIDS[@]: unbound variable`; one-shot background forwards also disappeared. Add regression coverage for empty-array exit cleanup and a documented persistent-session invocation; report actual connectivity separately from helper exit status (E11).
2. **High — fragmented evidence:** propose one read-only session inventory joining status/mode, experience, local-day timestamp, full task map, shared/local media presence and log coverage. Keep unavailable distinct from zero (E25–E27).
3. **High — incomplete health:** recorder health passed while game profiles were absent. Propose a per-experience profile-file/parse preflight so missing profiles are visible before a guest session starts (E07, E16–E17).
4. **Medium — source discovery:** the earlier skill search did not follow symlinks. This debrief located and read `.agents/skills/i-have-adhd/SKILL.md` with symlink-aware discovery. Earlier availability is not established; record discovery failure rather than claiming absence.
5. **Medium — observability access:** Grafana MCP tools were unavailable. Report the limitation once, keep supported retained-log checks available, and leave Grafana recovery to the user (E11, E14–E16).

## Blind spots

- What removed or failed to restore the profiles between the observed last-good and first-bad loads remains unknown (E19, E23–E24).
- Historical HTTP request/retry totals, exhaustive backup footage and the outcome of a future profile redeployment are unverified (E24, E27).

## Platform facts learned

| Fact | Evidence | verified / inferred |
| --- | --- | --- |
| Missing game-side profiles can stop capture/render submission while gameplay and image uploads continue. | E16–E18 | verified in this incident |
| Full task maps are needed: the room video list omits halfway-only sessions. | E04, E09 | verified from matched source/API |
| Recorder liveness does not establish that a specific experience has usable profiles. | E07, E16–E17 | verified in this incident |
| Cached archives can remain valid while deployed profiles are absent; archive availability alone does not prove successful deployment. | E21–E23 | verified in this incident |

## What helped

- A successful same-game Room 2 control separated a room-specific file problem from shared rendering/version hypotheses (E06, E17, E20).
- Exact-session Unity logs plus file presence established the missing-profile mechanism; last-good/first-bad logs expanded scope beyond the reported dates (E16–E19).
- In-memory ZIP/JSON checks established a repair candidate without extracting files or claiming historical footage recovery (E21).
