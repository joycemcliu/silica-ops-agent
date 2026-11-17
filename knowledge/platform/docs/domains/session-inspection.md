---
title: Session inspection
type: debug
domain: session
services: [session-server]
symptoms:
  - Session timing or status is unclear
last_verified: 2026-11-17
status: draft
---

# Session inspection

> **Read when:** you need a session's identity, room, timing, mode, or current status.

## Run

Use an existing approved connection. Confirm that the platform URL belongs to the selected store; environment/store flags label the report, not discover or verify the deployment.

From the repository root:

```bash
.venv/bin/python knowledge/platform/scripts/gather-session-info.py \
  --environment <ENVIRONMENT> --store <STORE_CODE> --base-url http://<PLATFORM_HOST>:<PORT> \
  --room <ROOM> --session <SESSION_ID> --timezone <IANA_TIMEZONE>
```

Replace `<ENVIRONMENT>` with `dev` or `prod` and `<STORE_CODE>` with the selected store's code.

Add `--json` for structured output. For HTTPS with a private CA, use `--ca-file <CA_BUNDLE>`. The script only makes GET requests; it does not create tunnels.

## Read the result

- Session info includes experience ID, room, mode, latest reported status, and local times with UTC offsets.
- Start/end times come from `experienceProgress.startTime/endTime`. Creation time is separate. Missing times remain unknown; booking times are not substitutes.
- Each request reports its path, collection time, HTTP status, and `retrieved`, `not_found` (HTTP 404), or `could_not_retrieve` state. A 404 may also mean a wrong route; confirm the base URL before concluding the record is absent.
- Missing fields are listed under `issues`. Exit 1 means at least one request failed or its response was invalid; successful evidence is still retained. Exit 0 means requests were collected, not that the session is healthy or all fields exist.

The script omits player/customer fields. Keep reports with restricted incident evidence.

## Symptom: session timing or status is unclear

Healthy behavior: the returned identity and room match the target, and the reported mode, status, and timing fit the expected session lifecycle.

1. Confirm the session ID, experience ID, and room before comparing sessions.
2. Check mode/status and reported start/end times. Missing progress times alone do not establish that gameplay never occurred.
3. Compare times in the store's timezone. Creation and booking times describe different events from experience start/end times.

If requests failed, restore access or confirm the deployed route first. Failed retrieval is not evidence that a session does not exist.

## Validation and sources

Field mappings were checked against local application source on the date above. Offline tests cover timezone conversion and partial failure. Live deployment behavior remains unverified.

- [Session API routes](../../../../../silica/apps/session/server/src/ports/rest/session/controller.go)
- [Session fields and timing](../../../../../silica/apps/session/server/src/ports/rest/session/response.go)
