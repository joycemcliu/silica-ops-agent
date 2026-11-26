---
title: Diagnose short After Effects exports and low disk space
slug: ae-short-export
services: [video-dge-renderer, after-effects]
tags: [after-effects, disk-space, duration, partial-export]
status: reviewed
last_verified: 2026-11-26
applies_to:
  observed_after_effects: "22.2.0.120"
source_incidents:
  - ../../incidents/2026-11-26-staging-ae-short-export.md
---

## Symptoms

- A DGE item reports `rendered video length not match (got … want …)`, with the measured duration materially shorter.
- Retries can stop at different progress values. Related errors can include an output-module write failure or a closed After Effects connection.

## Triage (read-only, in order)

1. Check progress and failure logs by session and item. Compare the highest reported progress on each attempt with the measured duration as a fraction of the expected duration. Matching partial progress and duration across retries supports early export termination. A completed export with a duration mismatch calls for checking the declared range and output metadata.

   ```logql
   {cluster="<cluster>",job="video/server"} |= "<session-id>" |= "<item>" |~ "updating task|rendered video length not match"
   ```

2. Confirm the assigned Windows renderer. Check free space on the Windows system drive and the render output drive. Check After Effects crash events in the same time window. An almost-full system drive or an explicit low-space error supports disk pressure. A crash event confirms a process failure for its matching attempt.

   ```powershell
   Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=3' | Select-Object DeviceID,FreeSpace,Size
   Get-WinEvent -FilterHashtable @{LogName='Application'; StartTime=[datetime]'<local-start>'; EndTime=[datetime]'<local-end>'; Id=1000,1001} -ErrorAction SilentlyContinue |
     Where-Object { $_.Message -match 'AfterFX|aerender' } |
     Select-Object TimeCreated,Id,Message
   ```

3. Check the generated project or its retained template. Compare the named composition's work-area frame count and frame rate with the validator's expected duration. A match confirms how the renderer obtained the target. If native logs and the partial output are retained, use their final frame and the container duration to narrow the failure.

## Likely causes

| Cause                                  | Evidence that supports it                                                                  | Evidence that weakens it                                                                                    |
| -------------------------------------- | ------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| Disk pressure during export            | Low system-drive space, explicit space or write errors, and successful retry after cleanup | Adequate free space on the system and output drives throughout a comparable failed attempt                  |
| After Effects process failure          | A crash event and native connection error during the same attempt                          | Native completion and a full set of rendered frames for that attempt                                        |
| Expected range or duration discrepancy | Parsed work area differs from the intended render range or the output metadata             | Work-area duration matches the expected value and progress stops near the same fraction as the short output |

## Remediation (HUMAN executes; agent never runs)

1. Free space on the constrained volume using approved cleanup. Verify the target volume and preserve active render inputs, retained diagnostics, and outputs. Move only identified, inactive files to approved storage if recovery might be needed. Restore moved files from that location if needed and sufficient capacity remains.
2. Retry the affected item once space is available. A retry consumes renderer capacity and can replace the delivered output. Confirm the item and preserve any prior valid output before retrying. Restore that copy if the retry produces an unusable replacement.

## Validation checklist

Machine checks

- [ ] The retry reaches completion, passes duration validation, and uploads.
- [ ] The system and output drives retain free space through the retry.

Human checks

- [ ] The downloaded trailer plays through its expected ending.

## Not yet verified

- The direct cause of the final short export and whether low disk space contributed to the separate heap-corruption crash.
- The free-space threshold needed by this workload and the scope across other After Effects builds.
