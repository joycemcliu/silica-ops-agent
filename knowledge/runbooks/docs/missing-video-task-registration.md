---
title: "Missing video-list entries with empty render-task maps"
slug: missing-video-task-registration
services: [video-server, video-dge, unity]
tags: [video, recording, missing-tasks]
status: reviewed
last_verified: 2026-11-17
applies_to:
  video_server: "1.6.5"
  unity_observed_build: "SquidGame V3.7.2.rc1"
source_incidents:
  - ../../incidents/2026-11-16-uswindow-missing-room1-videos.md
---

## Symptoms

Completed experience sessions have no corresponding room video-list entries; other rooms or later sessions can work normally.

## Confirmed profile-failure signature

- `RecordingManager.LoadProfile: Loaded []`
- `RecordingHelper.Record: No item found for profileName`
- `RenderingHelper.Render: No item found for profile name`
- `RenderingHelper.RenderRaw: No raw item found`

Combined with absent `recording-profile.json` and `rendering-profile.json` in the deployed experience parent directory, and a successful same-game control that has both files and nonempty loads, this identifies game-side profile failure before recording/render submission.

## Anti-anchoring

- Completed experience status does not establish capture or render submission.
- Current healthy recorder checks do not prove historical capture succeeded.
- An absent list entry alone does not prove there are no tasks: halfway-only tasks are hidden.
- Missing files on shared storage do not establish permanent loss or exclude alternate local copies.
- Videos from other games resuming does not prove the affected experience recovered.
- The warning for missing `HKLM\SOFTWARE\SandboxOS\Path` also occurred in successful controls; do not treat it as the cause without discriminating evidence.
- Empty task maps do not prove tasks were never created; subsequent deletion remains possible.

## Triage (read-only, in order)

Request shapes below were exercised with instance values in the linked incident. Use the toolkit's approved access path and actual deployment timezone; perform no POST requests.

1. `GET <platform>/video/holodecks/<room>/session`: convert created_at milliseconds to local dates and compare affected/unaffected rooms. Bad: a localized date gap. Good: entries exist; inspect status and client presentation instead.
2. `GET <platform>/session/holodecks/<room>/sessionBookings?dateFrom=<RFC3339>&dateTo=<RFC3339>`: compare session status/mode and IDs. Bad: completed sessions have no matching video entries. No completed sessions returned: reconcile booking expectations before assuming missing completed videos.
3. `GET <platform>/video/holodecks/<room>/session/<session>` and `GET <platform>/video/render/task/<session>`: inspect full task map, including halfway tasks. Empty map: inspect registration and inputs. Existing queued/failed tasks: follow the failure at that stage; the empty-map signature is absent.
4. `GET <platform>/video/files/<session>/` and `GET <platform>/video/files/<session>/raw/`: list names only. Compare with a successful session of the same experience. Images without recorded MP4/WAV media suggest missing capture/upload, but do not prove its cause. A generated AEPX or completed task adds evidence of downstream processing. Confirm actual static root from deployed source; do not repeat the Session directory in the URL.
5. `GET <platform>/video/holodecks/<room>/healthz`: establish current health only. Discover available retained logs with `GET <nomad>/v1/client/fs/ls/<allocation>?path=alloc/logs`; read selected files with `GET <nomad>/v1/client/fs/cat/<allocation>?path=alloc/logs/<filename>`. Filter exact sessions and print bounded, non-sensitive message fields. Validate complete reads and report retention gaps. Experience-server progress logs are not recorder or Unity coverage.
6. Inspect deployment-matched Render code: in the recorded version, default task persistence precedes queue publication. Empty maps therefore require upstream registration/deletion investigation before diagnosing queue delivery.

### Follow-up after an empty task map

Through approved read-only Windows access, use `hostname` to confirm the target, then `Get-ChildItem` to locate exact-session Unity logs. `Select-String -Path <session-output-log> -Pattern "RecordingManager.LoadProfile|RecordingHelper.Record: No item|RenderingHelper.Render|RenderingHelper.RenderRaw"` was exercised. Bad: empty profile load and repeated missing-item errors. Good: nonempty loads and successful requests; inspect the later handoff instead.

Use `Get-ChildItem <experience-parent> -Force` and a recursive profile-name scan to establish actual file presence, then compare with a successful same-experience room. Check local session directories by extension without opening customer media. List cached ZIP entries with `System.IO.Compression.ZipFile.OpenRead` and parse JSON in memory, without extraction. Bad: deployed profiles absent despite valid cached source archives. Good: profiles present and loaded; do not infer historical presence from current files alone. Determine the intended destination and versions from deployment configuration.

Compare retained last-good/first-bad exact-game logs and later logs before declaring an incident boundary or recovery. These steps were exercised using the toolkit Windows helper; target addresses, log paths and counts stay in the incident.

## Likely causes

| Cause | Evidence that confirms | Evidence that rules out or limits |
| --- | --- | --- |
| Missing deployed profiles | Empty profile loads, repeated named lookup failures, missing profile files, and successful same-game control | Files present now do not establish historical state; absence alone does not identify the deletion mechanism |
| Capture/render-submission failure | Missing task maps and media, plus historical failed or absent calls with verified complete logs | Empty maps and missing media alone identify a boundary, not a trigger |
| Halfway-only visibility | Task map contains only halfway video types | Empty full task map excludes this explanation |
| Queue/render/upload failure | Existing task status and corroborating stage errors | Empty task maps do not match an ordinary queued-task backlog |
| Deletion or cleanup | Audit/deletion logs or backups establish prior records/files | Not established by current absence; older retained videos alone cannot rule it out |
| No completed sessions | Session records contain only killed/test activity | Completed session IDs establish an actual reconciliation target |

## Remediation (HUMAN executes; agent never runs)

No repair was validated. For a confirmed missing-profile condition, an authorized operator may redeploy the expected profile archives to the verified experience parent directory using the supported deployment workflow. Guard: confirm host, game, current expected versions, destination, archive JSON validity and absence of active sessions that could be affected. Backup: preserve existing file inventory, any profile files and deployment metadata. Risk: wrong profiles or versions can break future capture/rendering. Rollback: restore the pre-change file state and stop launches if validation fails; profile restoration does not recreate historical footage. No executable repair command or tested rollback is supplied.

Before any reconstruction, require exact session IDs, confirmed source-media availability and task/dependency payloads, a backup of affected state, and explicit authorization. Risk: duplicate tasks/uploads or incomplete guest output. Rollback must be reviewed for the exact proposed operation; no tested generic rollback exists. Stop if source media cannot be located. Do not use queue leadership transfer or rerender as a diagnostic probe.

## Validation checklist

### Machine checks

- [ ] Reconcile completed sessions against full task maps and video-list entries in the store timezone.
- [ ] Distinguish current health from incident-time evidence.
- [ ] Verify required source recordings exist before considering reconstruction.
- [ ] For profile repair, verify expected files and nonempty profile load, then actual recording and task creation in a separately authorized controlled session.
- [ ] After any separately approved repair, verify task completion and published output for every target.

### Human checks

- [ ] Staff confirms expected guest sessions and dates.
- [ ] Review resulting videos for completeness and correctness; completion flags alone are insufficient.

## Not yet verified

- The action that removed or failed to restore profiles; absence and file timestamps do not identify an operator.
- Exact Unity/recorder trigger for other empty-map signatures; the linked incident confirms a missing-profile mechanism.
- Deleted-task scenarios remain unverified; the linked follow-up now corroborates missing submission through local profile errors.
- Alternate local footage, backup availability, and reconstruction procedure.
- Behavior on other server versions and any production remediation/rollback.
