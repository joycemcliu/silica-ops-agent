---
title: USANNDOW footage uploads blocked by missing NAS service registration
incident_date: 2026-11-17
incident_time_range: "21:41 to 21:44 on 2026-11-16; approximate live investigation window"
timezone: America/Detroit
store: USANNDOW
runbook: ../runbooks/docs/recorder-nas-service-missing.md
---

## Report, impact and scope

Staff reported no in-game or webcam footage across four rooms after replacing all masters, webcam Beelinks and MAAS. User estimates the swap was yesterday and recording worked previously; exact onset is unconfirmed. Dead legacy recorder jobs initially suggested a scheduling or ACL issue.

## Instance details

| Item | Value |
| --- | --- |
| Environment | Production; deployment timezone America/Detroit |
| Active jobs | video-dge/in-game-recorder-1 through -4; video-dge/webcam-recorder-linux-1 through -4 |
| Master checked | master-3, 10.185.0.103 |
| NAS target | 10.185.0.20, derived from existing CIFS mounts |
| Session | codex 01a1e75f-7eec-7cd3-a959-a182e49df596 |
| Source snapshot | silica master; silica-environments master updated to f5d85b16 |

## Evidence ledger

Investigation used live read-only checks, source inspection and Grafana logs. Commands below omit wrapper boilerplate; no credentials are recorded.

| ID | Tag | Command/query or source | Result summary |
| --- | --- | --- | --- |
| E1 | observed | Both repositories: git status --short --branch; git pull --ff-only | Both on master; platform current, deployment fast-forwarded; no pre-existing changes in either. Toolkit original tree retained unrelated slack-debug-agent directory. |
| E2 | observed | USANNDOW holodecks.tf, apps.tf, module-video.tf, module-video-dge.tf; platform video recorder Terraform | DGE in-game and Linux webcam enabled; legacy recorder enabled flags false. Modules video 1.6.5, video-dge 0.4.6. |
| E3 | observed | GET Nomad /v1/jobs | Each of eight active DGE recorder jobs running with one running allocation. Legacy video recorder jobs dead with zero allocations. |
| E4 | observed | GET Nomad /v1/job/video%2Fin-game-recorder-1 | Legacy app group Count=0. |
| E5 | observed | silica-loki LogQL: {cluster="USANNDOW",job=~"video-dge/(in-game-recorder|webcam-recorder).*"} followed by case-insensitive error/fail/denied/token filter; Nov 16–17 UTC | At 21:41 EST, in-game rooms 1 and 2 and webcam room 1 repeatedly failed uploads with lookup nas.service.silica: no such host. Logs name MP4 files for sessions usanndow-261116-T1-190321 and usanndow-261116-T2-200435. Capture completeness and file integrity not checked. |
| E6 | observed | GET Consul /v1/health/service/nas; GET /v1/catalog/service/nas with response headers | Both empty arrays. Catalog HTTP 200, known leader true, default ACL policy allow; no ACL-filtered-results header. |
| E7 | observed | master-3: hostname; date -Is; local GET /v1/catalog/service/nas; dig on ports 8600 and 53; GET /v1/agent/services | Local catalog empty; no NAS agent service. DNS port 8600 refused; subsequent agent/self confirms actual DNS port 53, where query returned no answer. |
| E8 | observed | master-3: findmnt -t nfs,nfs4,cifs -o TARGET,SOURCE | Existing infra-data and modules-data mounts target 10.185.0.20. This alone does not verify current SMB I/O. |
| E9 | observed | master-3: GET http://10.185.0.20:5000/webapi/query.cgi?api=SYNO.API.Info&method=query&query=SYNO.FileStation.Upload&version=1 | HTTP 200, success true, FileStation.Upload API metadata returned. Authentication and upload writes not tested. |
| E10 | observed | master-3: GET /v1/agent/self; select DebugConfig.ACLsEnabled and DNSPort | ACLsEnabled=false; DNSPort=53. Strong evidence against ACL denial explaining the observed missing service. |
| E11 | observed | master-3: journalctl -u consul; sudo -n journalctl; sudo -n find config | No accessible journal entries; sudo requires password. Configuration directory lists common/server/override files, contents not inspected. Remote rg unavailable. |
| E12 | observed | Broad ACL-error Loki query | MCP transport failed. No conclusion about absence of historical ACL messages; no Grafana repair or HTTP fallback attempted. |
| E13 | inferred | E5–E10 plus reported master replacement | Missing NAS service discovery blocks footage delivery. Registration may have been lost during replacement; historical registration owner and exact trigger unknown. |
| E14 | not-checked | Restore registration; upload retry; fresh test session; local filesystem and pending queues | No remediation or recovery validation performed. |

## Findings

1. Dead video/... recorder jobs are intentionally disabled legacy jobs. Active video-dge/... jobs run in all rooms; restarting legacy jobs does not address this configuration.
2. Confirmed delivery blocker: NAS service is absent from Consul and upload workers fail DNS lookup before contacting the NAS API. The NAS API itself responds by IP.
3. ACL token failure is not supported: queried master reports ACLs disabled. Historical ACL failures were not exhaustively checked.
4. Logs indicate local recording files awaiting uploads, but do not prove complete playable recordings or recoverability for every room/session. Do not delete local footage while investigating.

## Actions and recovery timeline

| Timestamp | Action actually taken | Result | Backup / rollback |
| --- | --- | --- | --- |
| Investigation window | Read-only Nomad, Consul, NAS API and source checks | Missing NAS registration isolated | No store changes |
| End of investigation | Closed session USANNDOW node-3 forwards | Cleanup reported both remaining store forwards stopped; SSH wrappers ended | Shared Grafana forwarding untouched |

## Outcome and remaining work

Unresolved; diagnosis only. Operator should restore the NAS Consul registration through the authoritative provisioning mechanism after verifying the intended address and registration owner. Back up current registration/configuration first; avoid broad recorder restarts or deleting queues. Then validate DNS on recorder hosts, upload success and NAS files, followed by one fresh session in each room. Registration restoration, retry behavior across process restarts, historical service ownership and complete recording integrity remain not-checked.
