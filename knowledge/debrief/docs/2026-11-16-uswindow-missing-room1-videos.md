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

- [high] [improved] [tunnel lifecycle] helpers reported `PROBE_PIDS[@]: unbound variable`; one-shot background forwards also disappeared.
  Proposal: Add regression coverage for empty-array exit cleanup and a documented persistent-session invocation; report actual connectivity separately from helper exit status (E11).\
  Status checked: 2026-11-18 — Commit `a9d95a8` fixes cleanup in both helpers. Commit `de0a7b3` detaches the store forwards and documents the invocation in the [toolkit](../../../docs/diagnose_toolkit.md#prod-stores). The [regression suite](../../../scripts/tests/test_store_port_forward.py) passed on Linux Bash 5.2 with test doubles and loopback connections. It checked launcher exit status and subsequent reachability independently.\
  Remaining: None for the recorded cleanup and persistence issues.

- [high] [improved] [fragmented evidence] Session evidence required separate task, media and log checks.
  Proposal: Add one read-only session inventory joining status/mode, experience, local-day timestamp, full task map, shared/local media presence and log coverage. Keep unavailable distinct from zero (E25–E27).\
  Status checked: 2026-11-17 — Rechecked the [platform index](../../platform/INDEX.md) and linked session/video guides and collectors. They expose identity, mode/status, local times and full individual task/dependency details, distinguishing unavailable evidence from zero tasks. All 10 offline collector tests passed. Per user direction, indexed inspection addresses this friction instead of requiring one joined command. Storage presence and log coverage remain separate checks; live deployment behavior was not validated.\
  Remaining: None for the accepted indexed-inspection scope; a joined storage/log inventory is not required for closeout.

- [high] [unchecked] [incomplete health] recorder health passed while game profiles were absent.
  Proposal: Add a per-experience profile-file/parse preflight so missing profiles are visible before a guest session starts (E07, E16–E17).\
  Status checked: 2026-11-17 — The [runbook](../../runbooks/docs/missing-video-task-registration.md) documents manual profile checks; game/deployment implementations and live health checks were not inspected.\
  Remaining: Check whether an automated per-experience profile preflight exists and validate its file/parse failure cases.

- [med] [unchecked] [source discovery] the earlier skill search did not follow symlinks. This debrief located and read `.agents/skills/i-have-adhd/SKILL.md` with symlink-aware discovery. Earlier availability is not established; record discovery failure rather than claiming absence.
  Proposal: Use symlink-aware discovery and report lookup failure rather than assuming a skill is absent.\
  Status checked: 2026-11-17 — The original debrief records a successful symlink-aware lookup, but the earlier failing discovery path and any general fix were not verified.\
  Remaining: Identify the discovery path and verify symlink handling before marking the toolkit improved.

- [med] [improved] [observability access] Grafana MCP tools were unavailable.
  Proposal: Report the limitation once, keep supported retained-log checks available, and leave Grafana recovery to the user (E11, E14–E16).\
  Status checked: 2026-11-17 — Rechecked [store forwarding](../../../scripts/store-port-forward.sh): detached workers retry disconnects every 3 seconds and rediscover replacement Nomad pods. All 4 forwarding regression tests passed using fake tools and loopback connections, including launcher-exit survival, reconnect, reuse and cleanup. The [toolkit](../../../docs/diagnose_toolkit.md#logs-metrics-and-traces) documents reporting persistent MCP failures. Per user direction, improved covers store-connection resilience and failure handling; store forwarding does not repair Grafana MCP transport or tool exposure. No live MCP query was validated.\
  Remaining: None in the accepted scope. MCP failures remain unresolved and are excluded from this follow-up; unavailable historical evidence remains explicit.

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
