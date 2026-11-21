---
title: "Experience countdown at zero from host clock skew"
slug: experience-timer-host-clock-skew
services: [unity, experience-server, session-ui, windows-time]
tags: [timer, clock-skew, ntp, winrm]
status: draft
last_verified:
applies_to: {}
source_incidents:
  - ../../incidents/2026-11-20-usforcro-experience-timer-host-clock-skew.md
---

## Symptoms

- The Silica timer displays `00:00` when the tutorial starts. Gameplay continues and adding time can restore the visible countdown.
- Several titles fail in the same room. A shared experience host is a candidate.
- A correct time zone and a running Windows Time service can coexist with an incorrect UTC clock.

## Triage (read-only, in order)

1. Find the first timed progress update in production Grafana. Substitute the store and full session ID in this LogQL query. Compare the payload's `startTime` and `endTime` in UTC with the experience server's receipt time. A healthy initial window ends roughly one configured duration in the future. A full-duration window that arrives expired points to a timestamp problem.

   ```logql
   {cluster="<store-code>",job=~"[^/]+/server"} |= "<session-id>" |~ "(?i)sync(progress|experienceprogress) with sessionid" |= "startTime"
   ```

2. Identify the affected experience host and a healthy comparison room. Use an approved WinRM path to sample both hosts. Record UTC immediately before and after each call from the collector. Confirm each returned hostname before using its readings.

   ```powershell
   $env:COMPUTERNAME
   [DateTime]::UtcNow.ToString("o")
   [DateTimeOffset]::Now.ToString("o")
   Get-TimeZone
   Get-Service w32time
   w32tm /query /source
   w32tm /query /status
   ```

   A healthy host's UTC falls within the sampling window, allowing for network latency, and its sync status names the expected upstream time source. Clock skew near the payload skew, `Local CMOS Clock`, and `Leap Indicator: 3(not synchronized)` support a host-time fault.

## Likely causes

| Cause | Evidence that confirms | Evidence that rules out |
| --- | --- | --- |
| Slow or unsynchronized experience host clock | UTC is behind the collector and the healthy room. The timer payload shows the same skew. | The experience host's UTC agrees with the collector while the server still receives stale timestamps. |
| Incorrect time-zone conversion in the experience | Host UTC is accurate, but the payload represents the wrong UTC instant after applying its offset. | The UTC skew is already present on the host and persists with the correct local offset. |
| Missing timer initialization | The application never sends a valid timed progress update at tutorial start. | A successful progress update contains start and end times one expected duration apart. |

## Remediation (HUMAN executes; agent never runs)

1. Confirm the hostname, approved time source, and that the affected room is idle. Save the effective Windows Time configuration and its policy or management source before making changes.
2. Restore the host's approved Windows Time configuration and synchronization through the team's Windows management procedure. A one-hour correction can disrupt active sessions and change event ordering. If a configuration change fails, restore the saved configuration through the same management path and check the sync status again.

## Validation checklist

- [ ] Compare host UTC with a trusted clock. Confirm the expected time source and a recent successful sync.
- [ ] Check the next tutorial's initial progress payload. Its end time should be roughly one configured duration after initialization.
- [ ] Have a store operator start a fresh test session and visually verify the countdown starts near the configured duration without manual time adjustment.

## Not yet verified

- The incident did not establish why the affected host lost synchronization.
- The Windows configuration change and post-fix validation were untested during diagnosis.
