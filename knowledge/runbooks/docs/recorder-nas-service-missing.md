---
title: Recorders running but footage uploads fail NAS discovery
slug: recorder-nas-service-missing
services: [video-dge, consul, synology]
tags: [recording, dns, service-discovery]
status: draft
last_verified:
applies_to: {video: "1.6.5", video-dge: "0.4.6"}
source_incidents: [../../incidents/2026-11-17-usanndow-nas-service-missing.md]
---

## Symptoms

Footage is unavailable after hardware replacement, and legacy recorder jobs appear dead. Active DGE recorders can still be running while uploads fail with `lookup nas.service.silica: no such host`.

A dead legacy job alone does not imply an active recorder failure. A running allocation alone does not prove footage reached storage. A DNS lookup failure alone does not prove an ACL problem.

## Triage (read-only, in order)

1. Inspect the selected store's `holodecks.tf` and `apps.tf` for `use_dge_ingame`, `use_dge_webcam` and legacy enabled flags. Query `GET <nomad>/v1/jobs` and `GET <nomad>/v1/job/<URL-encoded-legacy-job>`. Expected: active DGE allocations running; legacy group Count=0 when disabled. Bad: active jobs have no running allocation; investigate allocation events separately.
2. Query the configured Loki datasource using `{cluster="<store>",job=~"video-dge/(in-game-recorder|webcam-recorder).*"} |~ "(?i)(error|fail|denied|token)"`. Bad: recurring NAS lookup errors. Good: successful uploads; absence of errors alone is inconclusive. Use a narrow incident window and preserve room coverage.
3. Query `GET <consul>/v1/catalog/service/nas` with response headers and `GET <consul>/v1/health/service/nas`. Bad: empty catalog or only unhealthy entries. Good: intended NAS address and passing checks. Inspect ACL filtering headers before interpreting an empty response.
4. On an authorized master, query `GET <local-consul>/v1/agent/self`, selecting only `DebugConfig.ACLsEnabled` and `DebugConfig.DNSPort`, and inspect `GET <local-consul>/v1/agent/services`. ACLs disabled argues against token denial; do not assume a standard DNS port. Avoid dumping token-bearing configuration.
5. Use `findmnt -t nfs,nfs4,cifs -o TARGET,SOURCE` to identify the configured NAS target, then issue a read-only GET to `http://<verified-nas>:5000/webapi/query.cgi?api=SYNO.API.Info&method=query&query=SYNO.FileStation.Upload&version=1`. HTTP 200 with success=true distinguishes reachable NAS API from DNS failure. Mounted paths alone do not prove SMB health; API discovery does not prove authenticated uploads.

## Likely causes

| Cause | Evidence that confirms | Evidence that rules out |
| --- | --- | --- |
| Missing NAS registration | Empty unfiltered catalog plus NAS lookup failures; NAS API responds directly | Intended registration present and DNS resolves from failing recorder |
| ACL filtering or registration denial | ACLs enabled plus filtered responses or explicit deny logs | Queried agent reports ACLs disabled; corroborating successful catalog reads |
| NAS API unavailable | Verified address cannot serve the required API | Direct API discovery succeeds; authenticated upload remains a separate check |
| Active recorder scheduling failure | Active DGE job has no running allocation | All active allocations running; this does not prove capture correctness |
| Legacy job disabled by design | DGE enabled and legacy group Count=0 | Legacy recorder is actually the intended configured recorder |

## Remediation (HUMAN executes; agent never runs)

Not executed or validated in the source incident.

1. Restore the intended NAS service using its authoritative provisioning mechanism. Guard: verify store, NAS address, existing services and the registration owner first. Backup: export existing service/configuration and retain provisioning revision. Risk: wrong address or duplicate registration routes uploads incorrectly. Rollback: revert only the newly introduced change to the saved state.
2. Preserve local clips and pending upload state. Consider a targeted retry or restart only after confirming that version's retry persistence behavior and completing a backup. Risk: a restart may lose queued state. Rollback: revert configuration and restore saved state through a verified procedure; otherwise do not restart.

## Validation checklist

Machine checks, all not-checked after remediation:

- [ ] Catalog contains intended NAS and health checks pass.
- [ ] NAS DNS resolves on affected recorder hosts.
- [ ] Existing pending uploads succeed and resulting NAS files are present.
- [ ] New in-game and webcam clips reach storage in each room. Running jobs and HTTP readiness alone do not establish this.

Human checks:

- [ ] Play the test recordings and generated output to confirm content, duration and room coverage.

## Not yet verified

- Why registration disappeared; hardware replacement is a suspected trigger only.
- Which provisioning system owns the registration and the safe exact restore operation.
- Post-repair recovery, existing clip integrity and queue persistence across restarts.
- Authenticated NAS upload and SMB read/write behavior.
