---
title: "Missing video-list entries with empty render-task maps"
slug: missing-video-task-registration
services: [video-server, video-dge, unity]
tags: [video, recording, missing-tasks]
status: draft
last_verified:
applies_to:
  video_server: "1.6.5"
source_incidents:
  - ../../incidents/2026-11-16-uswindow-missing-room1-videos.md
---

## Symptoms

Completed experience sessions have no corresponding room video-list entries; other rooms or later sessions can work normally.

## Anti-anchoring

- Completed experience status does not establish capture or render submission.
- Current healthy recorder checks do not prove historical capture succeeded.
- An absent list entry alone does not prove there are no tasks: halfway-only tasks are hidden.
- Missing files on shared storage do not establish permanent loss or exclude alternate local copies.
- Empty task maps do not prove tasks were never created; subsequent deletion remains possible.

## Triage (read-only, in order)

Request shapes below were exercised with instance values in the linked incident. Use the toolkit's approved access path and actual deployment timezone; perform no POST requests.

1. `GET <platform>/video/holodecks/<room>/session`: convert created_at milliseconds to local dates and compare affected/unaffected rooms. Bad: a localized date gap. Good: entries exist; inspect status and client presentation instead.
2. `GET <platform>/session/holodecks/<room>/sessionBookings?dateFrom=<RFC3339>&dateTo=<RFC3339>`: compare session status/mode and IDs. Bad: completed sessions have no matching video entries. No completed sessions returned: reconcile booking expectations before assuming missing completed videos.
3. `GET <platform>/video/holodecks/<room>/session/<session>` and `GET <platform>/video/render/task/<session>`: inspect full task map, including halfway tasks. Empty map: inspect registration and inputs. Existing queued/failed tasks: follow the failure at that stage; the empty-map signature is absent.
4. `GET <platform>/video/files/<session>/` and `GET <platform>/video/files/<session>/raw/`: list names only. Compare with a successful session of the same experience. Images without recorded MP4/WAV media suggest missing capture/upload, but do not prove its cause. A generated AEPX or completed task adds evidence of downstream processing. Confirm actual static root from deployed source; do not repeat the Session directory in the URL.
5. `GET <platform>/video/holodecks/<room>/healthz`: establish current health only. Discover available retained logs with `GET <nomad>/v1/client/fs/ls/<allocation>?path=alloc/logs`; read selected files with `GET <nomad>/v1/client/fs/cat/<allocation>?path=alloc/logs/<filename>`. Filter exact sessions and print bounded, non-sensitive message fields. Validate complete reads and report retention gaps. Experience-server progress logs are not recorder or Unity coverage.
6. Inspect deployment-matched Render code: in the recorded version, default task persistence precedes queue publication. Empty maps therefore require upstream registration/deletion investigation before diagnosing queue delivery.

## Likely causes

| Cause | Evidence that confirms | Evidence that rules out or limits |
| --- | --- | --- |
| Capture/render-submission failure | Missing task maps and media, plus historical failed or absent calls with verified complete logs | Empty maps and missing media alone identify a boundary, not a trigger |
| Halfway-only visibility | Task map contains only halfway video types | Empty full task map excludes this explanation |
| Queue/render/upload failure | Existing task status and corroborating stage errors | Empty task maps do not match an ordinary queued-task backlog |
| Deletion or cleanup | Audit/deletion logs or backups establish prior records/files | Not established by current absence; older retained videos alone cannot rule it out |
| No completed sessions | Session records contain only killed/test activity | Completed session IDs establish an actual reconciliation target |

## Remediation (HUMAN executes; agent never runs)

No repair was validated. Before any reconstruction, require exact session IDs, confirmed source-media availability and task/dependency payloads, a backup of affected state, and explicit authorization. Risk: duplicate tasks/uploads or incomplete guest output. Rollback must be reviewed for the exact proposed operation; no tested generic rollback exists. Stop if source media cannot be located. Do not use queue leadership transfer or rerender as a diagnostic probe.

## Validation checklist

### Machine checks

- [ ] Reconcile completed sessions against full task maps and video-list entries in the store timezone.
- [ ] Distinguish current health from incident-time evidence.
- [ ] Verify required source recordings exist before considering reconstruction.
- [ ] After any separately approved repair, verify task completion and published output for every target.

### Human checks

- [ ] Staff confirms expected guest sessions and dates.
- [ ] Review resulting videos for completeness and correctness; completion flags alone are insufficient.

## Not yet verified

- Exact Unity/recorder trigger and historical recording configuration.
- Never-created versus subsequently deleted tasks.
- Alternate local footage, backup availability, and reconstruction procedure.
- Behavior on other server versions and any production remediation/rollback.
