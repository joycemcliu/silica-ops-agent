---
title: "Artisan Circle Room 5 countdown at zero"
incident_date: 2026-11-20
incident_time_range: "09:37 to 18:57 CST"
timezone: America/Chicago
store: USFORCRO
runbook: ../runbooks/docs/experience-timer-host-clock-skew.md
---

## Report, impact and scope

Room 5 at Artisan Circle displayed `00:00` at tutorial start while the game ran. Staff manually added time to recover the display. Production logs confirm expired timer updates in several titles, including Dragonfire, Deadwood Mansion, Age of Dinosaurs, and Squid Game. Room 2 served as the healthy comparison during the live clock check.

[Slack issue](https://sandboxvr.slack.com/archives/C046N4EMYRY/p1795221140470869) · [Freshdesk 347519](https://sandboxvr.freshdesk.com/a/tickets/347519) · [Production Loki evidence](https://monitoring.silicaos.com/explore?left=%7B%22datasource%22%3A%22silica-loki%22%2C%22queries%22%3A%5B%7B%22expr%22%3A%22%7Bcluster%3D%5C%22USFORCRO%5C%22%2Cjob%3D~%5C%22%5B%5E%2F%5D%2B%2Fserver%5C%22%7D+%7C~+%5C%22261120-%5BTG%5D5-%5C%22+%7C~+%5C%22%28%3Fi%29sync%28progress%7Cexperienceprogress%29+with+sessionid%7C%3AaddDuration%5C%22%22%2C%22refId%22%3A%22A%22%7D%5D%2C%22range%22%3A%7B%22from%22%3A%221795188600000%22%2C%22to%22%3A%221795221300000%22%7D%7D)

## Instance details

| Item | Value |
| --- | --- |
| Environment and services | Production, Unity experience host, experience servers and Silica session UI |
| Affected and comparison hosts | Room 5 `R5-EXP` (`10.17.5.11`), Room 2 `R2-EXP` (`10.17.2.11`) |
| Guest session | Dragonfire `261120-G5-173536` |
| Comparison test sessions | Deadwood Mansion `261120-T5-172232` and `261120-T5-182710`, Squid Game `261120-T5-171023` |

## Evidence ledger

| ID | Tag | Command, query or evidence source | Result summary |
| --- | --- | --- | --- |
| E01 | observed | Supplied Slack thread | Staff reported zero at tutorial start across Room 5 titles. They reported recreating a test session, rebooting the experience server, running a content check and checking server time zones. |
| E02 | observed | Git status in both Silica repositories, store `AGENTS.md`, `store.tf` and `infra-cluster.json` | Inspected clean local `master` checkouts. The store uses `America/Chicago`. Deployment inventory identified the experience hosts for Rooms 5 and 2. |
| E03 | observed | Production Grafana Loki datasource and label discovery, then session, experience server and Unity queries scoped to the store and session | Unity logged the tutorial and gameplay progression on `r5-exp`. The first timed Dragonfire progress update arrived at 17:51:21.894 CST with a start at 16:51:09.580 CST and end at 17:21:09.580 CST. The session-server progress request returned HTTP 200. |
| E04 | observed | Production Loki Room 5 progress and `:addDuration` queries | Multiple titles sent 30-minute windows already expired at arrival. The skew persisted on payloads with `-05:00` and `-06:00`. In the Squid Game test, two `:addDuration` requests returned HTTP 200 and the subsequent end times were in the future. |
| E05 | observed | Read local Silica source | `libs/ts/react-exp-ui/src/hooks/useTimer.ts` computes remaining time from the supplied end time and browser time. `libs/ts/react-exp-ui/src/components/Timer/index.tsx` floors the display at zero. |
| E06 | observed | Production Loki System event query for `r5-exp` | The returned events did not identify the cause of lost synchronization. The Slack attachment ZIP and video were unreviewed. |
| E07 | observed | `scripts/store-sshuttle.sh USFORCRO`, followed by approved SSH forwarding scoped to the two WinRM ports | The standard route reached the store SSH proxy and stopped at a local sudo prompt. The first forward was stopped. The scoped alternative connected to both hosts and closed at the end of the check. |
| E08 | observed | WinRM `[DateTime]::UtcNow`, `[DateTimeOffset]::Now`, `Get-TimeZone`, `Get-Service w32time`, `w32tm /query /source` and `w32tm /query /status`, bracketed by collector UTC readings | At about 18:57 CST on Nov 20, `R5-EXP` was roughly 1 hour 12 seconds slow and unsynchronized. It reported `Local CMOS Clock`, stratum 0, and an unspecified last successful sync. `R2-EXP` matched the collector window and reported `time.google.com`, stratum 2, and a last sync at 18:17:28 CST. Both had a running Windows Time service and used `Central Standard Time` at `UTC−06:00`. |
| E09 | not-checked | Windows Time policy, NTP reachability, clock correction and post-fix test | The reason Room 5 fell out of sync and the outcome of any later remediation remain open. |

## Findings

The slow host clock explains the symptom. Room 5 supplied a full 30-minute countdown whose end fell about 30 minutes before Silica received it. The live comparison confirmed that Room 5's UTC clock was slow even while both rooms reported the same time zone. Windows Time was running in Room 5 with no active synchronization.

## Actions and recovery timeline

All times are local CST on Nov 20.

| Time | Action or observation | Result |
| --- | --- | --- |
| 09:37 | Age of Dinosaurs test sent its first timed update | Timer end arrived about 30 minutes in the past. |
| 09:39 and 17:11 | Staff manually added time on Room 5 test sessions | End times moved into the future in the Age of Dinosaurs and Squid Game test logs. |
| 17:51 | Dragonfire guest session entered timed tutorial progress | Its 30-minute window arrived already expired. |
| 18:29 | Deadwood Mansion test sent timed progress | The hour of skew persisted after the payload switched to the store's `-06:00` offset. |
| 18:57 | Compared Windows clocks and time-sync status over WinRM | Confirmed Room 5 skew and unsynchronized state. Both remote sessions and the temporary forward were closed. |

## Outcome and remaining work

Diagnosis complete. Production remediation and recovery validation are pending. Restore synchronization to the approved time source for the affected host, then verify a fresh Room 5 session starts near `30:00` without a manual adjustment.
