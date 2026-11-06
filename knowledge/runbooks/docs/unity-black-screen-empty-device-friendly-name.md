---
title: Unity black screen caused by an empty Windows device friendly name
slug: unity-black-screen-empty-device-friendly-name
services: [unity, experience]
tags: [windows, unity, nomad, ravingbots, multiinput]
status: draft
last_verified: 2026-11-06
applies_to:
  dll_sha256: 5EF7E3F251B171ACEEF91A573366F611FE4EA2C33045C260F046AF0597A2E253
source_incidents: [../../incidents/2026-11-02-holodeck-3.md]
---

## Symptoms

- One or more Unity games black-screen at startup; other games on the same host work. Both the operator display and game-server monitor may be black. Reported examples: AmberSky, DWM, CODJ and UFL.
- The last Photon connection log line alone does not prove a network failure. An unresponsive process alone does not identify this mechanism either.
- Failure signature: Unity's main thread is in RavingBots MultiInput's `rb_minput_create`, repeatedly enumerating devices through `SetupDiGetDeviceRegistryPropertyW`.

The binary hash in `applies_to` identifies the inspected `rb-minput.dll`. With a different hash, treat this mechanism as a hint only and re-confirm the native behavior before repair. Matching hashes do not prove that every game takes the same initialization path.

## Triage (read-only, in order)

Run on the affected Windows server. These steps require no API credentials. The new script invocations are collected under **Not yet verified**, because they have not been executed end-to-end; the incident used native diagnostics. Do not equate proposed commands with historical evidence.

1. **Scan all present device classes**, using [find-empty-friendlyname.ps1](../scripts/find-empty-friendlyname.ps1) and the proposed command below. MultiInput scans beyond USB/input devices. Bad: an existing string-valued `DEVPKEY_Device_FriendlyName` is empty. Good: no candidates and no query failures. A scan failure is inconclusive; candidates alone do not prove the cause. Never bulk-repair results.
2. **Confirm the blocked native path.** Capture a hang dump/thread stack with the site's approved Windows debugging tools. Bad: the Unity main thread stays in `rb_minput_create` and repeated SetupAPI enumeration; confirm the empty-name branch revisits the same record without advancing the index. Good: enumeration finishes, or the thread is elsewhere—investigate that path. No exact dump command is prescribed because the original capture invocation was not retained.
3. **Inspect one confirmed candidate**, passing its full `InstanceId` to the read-only `Inspect` action in [fix-empty-friendlyname.ps1](../scripts/fix-empty-friendlyname.ps1). Bad: property `12` (`SPDRP_FRIENDLYNAME`), type `REG_SZ` (`1`), bytes `00 00` / Base64 `AAA=`. Good for this failure mode: the property is absent or contains a nonempty name. Other types/bytes require investigation, not weaker guards.
4. **Map the candidate to a human-visible device.** Run `devmgmt.msc`; open the candidate's class, then **Properties → Details → Device instance path**. Match the ID from the scan. Inspect **Friendly name** and **Device description**. The description must provide a nonempty fallback. A zero-size disk was one incident's trigger, not a required symptom. A blank GUI field alone does not distinguish an absent property from an existing empty one.

An **absent override** permits fallback to `DEVPKEY_Device_DeviceDesc` / `SPDRP_DEVICEDESC` (property `0`). An **existing empty override** reaches the defective branch. Preserve that distinction throughout diagnosis and validation.

## Likely causes

| Cause                                              | Evidence that confirms                                                                                                | Evidence that rules out                                                                                                |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| MultiInput infinite loop on an existing empty name | Empty selected name plus blocked native enumeration; non-advancing empty-name branch; removal releases initialization | Enumeration finishes normally or the main thread blocks elsewhere                                                      |
| Attached USB device problem                        | Repeatable change with a specific attached device and matching blocked driver call                                    | Recorded incident persisted with USB disconnected and no Raw Input devices; trigger belonged to another device class   |
| Photon/network failure                             | Independent endpoint failures and connection errors while Unity continues processing                                  | Recorded hang was in MultiInput; Photon progressed after the metadata repair. A final Photon log alone is insufficient |
| Display/capture problem                            | Game initializes and renders locally while the operator feed alone is black                                           | Recorded case affected both displays and had a blocked game main thread                                                |

The [source incident](../../incidents/2026-11-02-holodeck-3.md) contains the observations behind this table. The library is RavingBots MultiInput, not Rewired.

## Remediation (HUMAN executes; agent never runs)

Use [fix-empty-friendlyname.ps1](../scripts/fix-empty-friendlyname.ps1) in elevated PowerShell only after triage confirms the device and native mechanism. `-Id` is mandatory and must come from the current scan. Both mutation modes request confirmation; `-WhatIf` permits a read-only preview.

1. **Stop the affected game through the normal operator workflow.** Risk: interrupts the current game. First preserve its logs/dump; rollback for this operational action is a normal relaunch. Live metadata removal previously caused a native input exception, so prefer a stopped game.
2. **Repair one device.** Choose a new backup file in an existing writable directory. The script verifies exact type/bytes, a usable description fallback, and a new backup's contents; re-reads the property; then removes only the empty override using `SetupDiSetDeviceRegistryPropertyW(..., 12, NULL, 0)`. Risk: changes device metadata. Backup: original identity/type/bytes in the selected file. Rollback: the command below. Do not disable/uninstall the device or modify storage.

   ```powershell
   $id = Read-Host 'Paste the confirmed InstanceId from triage step 1'
   $backup = Read-Host 'New backup file path in an existing directory'
   & .\runbooks\scripts\fix-empty-friendlyname.ps1 -Id $id -Action Repair -BackupPath $backup
   ```

3. **Relaunch and validate.** Risk: a failed launch can affect the next session. Preserve the device backup and new game logs. If validation fails, stop the game and reassess the cause; restore metadata only when deliberately rolling back the workaround.

**Metadata rollback:** restores the empty property and can reintroduce the hang. Stop affected games first. The script verifies the backup belongs to the supplied ID and that the override is still absent. It saves and verifies that absent state in a new companion backup before restoring. It refuses to overwrite either backup or a changed live property. These scripts consume their own backup schema; do not assume compatibility with an old incident's backup.

```powershell
& .\runbooks\scripts\fix-empty-friendlyname.ps1 -Id $id -Action Rollback -BackupPath $backup
```

To undo rollback, repeat Repair with a new backup path and the same confirmed ID. Never recreate the empty property merely to test production. A permanent software fix must advance/skip the record on the empty-name branch in the native library; locate that source rather than patching deployed binaries speculatively.

## Validation checklist

Machine checks:

- [ ] Inspect reports the override absent; the existing description remains available.
- [ ] Native enumeration finishes without an empty selected name; fresh MultiInput initialization completes through input-source setup.
- [ ] A fresh game launch stays responsive and logs progress; expected network/player connections establish.
- [ ] Allocation and service checks pass. Process/network/health success does **not** prove pictures render.

Human-only checks:

- [ ] Confirm game pictures on both the operator display and game-server monitor.
- [ ] Launch each affected game separately and check a previously working game.
- [ ] Only after a recurrence validates these steps, a human updates `last_verified`; keep `status: draft`.

## Not yet verified

- Neither reusable script has been executed end-to-end on Windows, including rollback, confirmation/preview behavior and the new fallback/concurrent-change guards. The historical repair used the same native deletion operation, not this extracted script.
- Triage steps 1 and 3 were rewritten after the linked incident to remove instance-specific targeting; re-verify. These **proposed read-only commands** belong here until actually validated. Run from the repository root on the Windows server:

  ```powershell
  & .\runbooks\scripts\find-empty-friendlyname.ps1 | Format-List
  $id = Read-Host 'Paste one candidate InstanceId from the scan'
  & .\runbooks\scripts\fix-empty-friendlyname.ps1 -Id $id -Action Inspect
  ```

- The high-level PnP scan's coverage relative to the native library's exact SetupAPI flags needs verification. No candidates does not exclude other enumeration defects.
- The original dump-capture command was not retained. Select and validate a local capture procedure before adding a copy-paste command.
- Origin of the empty property, recurrence after reboot/device rediscovery, and why some games avoid the failing path remain unexplained.
- Full-game relaunches and visual checks were not established by the original process recovery or standalone DLL test; incident-specific gaps are retained in the source incident.
- A permanent native-library source fix and regression test remain outstanding.
