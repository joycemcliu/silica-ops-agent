---
title: Video inspection
type: debug
domain: video
services: [video-server, video-dge-renderer]
symptoms:
  - Video processing is pending or stalled
  - Video output is missing
last_verified: 2026-11-17
status: draft
---

# Video inspection

> **Read when:** you need to locate the reported processing stage of a session's videos.

## Run

Use an existing approved connection and confirm the platform URL belongs to the selected store. Environment/store flags label the report; they do not verify the deployment.

```bash
.venv/bin/python knowledge/platform/scripts/gather-video-info.py \
  --environment <ENVIRONMENT> --store <STORE_CODE> --base-url http://<PLATFORM_HOST>:<PORT> \
  --room <ROOM> --session <SESSION_ID>
```

Replace `<ENVIRONMENT>` with `dev` or `prod` and `<STORE_CODE>` with the selected store's code.

Add `--json` for individual task details. For HTTPS with a private CA, use `--ca-file <CA_BUNDLE>`. Only the application's task API is queried; there are no log, NATS, or storage checks.

## Read the result

- Every registered task remains separate, including child/halfway tasks. Inspect dependencies, status, render/upload progress, errors, and reported output URL.
- A successful empty map means zero tasks returned now. Failed retrieval leaves the count unknown. Neither proves whether tasks existed historically.
- `not_found` means HTTP 404; confirm the route before treating it as record absence. `could_not_retrieve` includes access errors, timeouts, malformed responses, and target mismatches.
- `issues` lists missing fields and dependencies absent from the returned map. Null means not reported; it is not a zero progress value.
- Output availability is URL metadata only. A URL or completed task does not establish file reachability, complete footage, or valid playback.

Each request includes its path, collection time, and HTTP status. Exit 1 means collection failed or the response was invalid. Exit 0 means collection succeeded, even if tasks report errors. JSON reports may contain internal URLs and error text; keep them with restricted incident evidence.

## Symptom: parent stays Pending

Healthy behavior: dependencies advance and complete before their parent can progress. Pending can be normal while dependencies are unfinished. One snapshot cannot establish a stall.

1. Inspect each dependency's status and progress. A parent Pending with a child Queuing identifies different reported stages; preserve both.
2. Collect another snapshot after a relevant processing interval. Compare task IDs, timestamps, and progress; the collector does not infer a cause or automatically poll.
3. For unchanged runnable children in Queuing, follow the [video render queue delivery flow](../flows/nats-video-render-queue-delivery.md). Confirm delivery with the flow's broker checks; worker health alone is insufficient.

## Symptom: output is missing

Healthy completed output normally has completed tasks and a reported video URL. Verify actual availability and playback separately when the diagnosis requires it.

- No tasks: use [session inspection](session-inspection.md), then the [missing-task runbook](../../../runbooks/docs/missing-video-task-registration.md).
- Task errors: use the individual task's error and stage to select the next checks. Do not infer the cause from the parent alone.
- Short or incomplete footage despite completion: follow [short recordings](../../../runbooks/docs/wcap-short-recordings.md).

## Validation and sources

Fields were checked against local source on the date above. Offline tests cover parent/child preservation, empty maps, and failed retrieval. Live deployment behavior remains unverified.

- [Task API contract](../../../../../silica/apps/video/server/ports/rest/openapi.yaml)
- [Task response fields](../../../../../silica/apps/video/server/cores/tasks/data.go)
- [Task API response examples](../../../../../silica/apps/video/server/ports/rest/render/render_test.go)
- [Queue delivery flow](../flows/nats-video-render-queue-delivery.md)
