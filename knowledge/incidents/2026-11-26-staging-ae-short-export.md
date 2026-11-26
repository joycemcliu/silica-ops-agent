---
title: Staging Wonderland trailer exported only part of the composition
incident_date: 2026-11-26
incident_time_range: 15:04:30 to 15:52:09
timezone: Asia/Hong_Kong
store: staging
runbook: ../runbooks/docs/ae-short-export.md
---

## Report, impact and scope

`WL_Trailer` for staging room 4 session `sbvrdev-261126-T4-143627` failed duration validation. The affected trailer later rendered, uploaded, and was downloaded. The investigation covered this item and one nearby error for comparison.

## Instance details

| Item              | Value                                                                      |
| ----------------- | -------------------------------------------------------------------------- |
| Renderer          | `r4-video` (`10.250.0.54`), `video-dge/renderer`, After Effects 22.2.0.120 |
| Project           | `Wonderland_DEV/WL_Trailer.aepx.tmpl`, composition `cctv`                  |
| Original request  | `38092d14-0068-4614-9cd9-41e5dade3a1b`                                     |
| Recovered request | `9b5649ed-8c45-4005-bfd6-92a3cfa4170a`                                     |

## Evidence ledger

| ID  | Tag      | Command/query or evidence source                                                                                                                                 | Result                                                                                                                                                                                                                                                                |
| --- | -------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E1  | observed | Dev Grafana `silica-loki`, `{cluster="hk-staging",job="video/server"} \|= "updating task(sbvrdev-261126-T4-143627, WL_Trailer"`, 15:04:45–15:08:40 HKT           | Highest reported progress was 48%, 79%, and 51% across the three export attempts. The server recorded durations of 31.763021 s and 34.083229 s on the first and third attempts. Two earlier attempts had returned `recording not ready for rendering`.                |
| E2  | observed | Local `extract_info.go` and `ffprobe.go`, read-only WinRM inspection of the staged template's `cdta` metadata                                                    | The `cctv` work area has 1,617 frames at 24.998 fps, yielding 64.685175 s. The validator compares this with `ffprobe` container duration.                                                                                                                             |
| E3  | observed | Staging Consul inventory, then WinRM on `r4-video`, Windows Application events 1000 and 1001                                                                     | At 15:07:15, `AfterFX.com` crashed with exception `0xc0000374` (heap corruption). The render reported a forcibly closed connection on the same attempt.                                                                                                               |
| E4  | observed | WinRM `Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3'` and Grafana search for `Photoshop Library operation failed because the device has no free space` | At inspection, `C:` had 246,231,040 bytes free and `E:` had roughly 3.92 TB free. A different staging room 4 render, `01_Shard_Opener`, logged the explicit no-space error at 14:36 HKT. Incident-time free space was unavailable from the queried Prometheus series. |
| E5  | observed | Read-only WinRM inspection of session output and renderer allocation logs                                                                                        | No partial file or native log for the 34-second attempt was available in the checked paths.                                                                                                                                                                           |
| E6  | observed | Operator confirmation and staging Grafana `analytics/server` and `video/server` filtered by session and item                                                     | The operator freed space and retried. Logs show a later output-module write failure at 15:49:14, render success at 15:51:00, upload completion, and successful downloads at 15:51:04 and 15:52:09. The exact time of cleanup is unavailable.                          |

## Findings

- **Observed.** The two short exports stopped around halfway through the expected composition. The varying lengths and reported progress support an interrupted export.
- **Inferred.** Low system-drive space was the likely contributing cause. Freeing space followed by a retry restored service. The exact mechanism behind the 34-second stop and any connection between disk pressure and the separate heap-corruption crash remain unverified.

## Actions and recovery timeline

| Time (HKT)                                      | Action or event                                        | Result                                                                               |
| ----------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| 15:04–15:08                                     | Renderer retried `WL_Trailer`                          | Two short outputs and one After Effects crash                                        |
| 15:49:14                                        | Later rerender reported an output-module write failure | After Effects error 9988 while writing the temporary MOV                             |
| Before successful retry, exact time unavailable | Operator freed disk space and retried                  | Render succeeded at 15:51:00                                                         |
| 15:51–15:52                                     | Upload and client downloads                            | Server logged upload completion and client telemetry logged two successful downloads |

## Outcome and remaining work

Closed for the reported session and item. Recovery is supported by the operator report and render, upload, and download telemetry. Independent probing or playback of the recovered file was not performed.
