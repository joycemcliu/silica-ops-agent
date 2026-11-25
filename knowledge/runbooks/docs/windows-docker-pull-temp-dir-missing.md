---
title: "Windows Docker image pulls fail when the daemon temp directory is missing"
slug: windows-docker-pull-temp-dir-missing
services: [docker, nomad, video-dge]
tags: [windows, image-pull, prestart]
status: reviwed
last_verified: 2026-11-25
applies_to:
  docker: "24.0.6 on Windows with the windowsfilter driver"
  nomad: "1.7.3 with a Docker prestart task"
source_incidents:
  - ../../incidents/2026-11-25-sandboxca-windows-docker-pull-temp-dir-missing.md
---

## Symptoms

- A Windows Nomad job stays pending or repeatedly fails before its application task starts.
- The Docker prestart task reports `GetImageBlob…: The system cannot find the path specified` under the daemon temp directory. The default Windows path is `C:\ProgramData\docker\tmp`.
- A healthy Nomad Docker driver and running containers show the daemon is responding. A fresh image pull is the check that exercises layer staging.

## Triage (read-only, in order)

1. Open the job's latest allocations in Nomad. Confirm the node, image tag, task, and timestamps. The failing pattern is a `Driver Failure` during the Docker task and an unstarted application task. A failed container start after a successful pull needs its own diagnosis.
2. On the affected client, confirm the computer name and actual Docker root. Use the temp path in the error as `$tempPath`. An absent path while the daemon is still running confirms the staging failure. An existing directory calls for checking its ACL, target if linked, and timestamps.

   ```powershell
   $tempPath = '<directory from the pull error>'
   hostname.exe
   docker info --format '{{.DockerRootDir}}'
   Get-Process dockerd | Select-Object Id, StartTime
   Get-Item -LiteralPath $tempPath -Force
   ```

3. In the Windows Application log, inspect events from the `docker` provider during the failing pull. Match the Windows error and path to the Nomad task event. Scope any storage check to the volume that hosts the Docker root. A disk warning without a matching device or volume cannot explain the missing path on its own.
4. If the directory disappeared while the daemon was running, check whether Windows File System auditing and the retained USN journal cover the incident window. Correlate any matching delete or rename record with available Security, PowerShell, and Defender events. A rolled-over journal or disabled audit policy leaves an attribution gap.

## Likely causes

| Cause                                                                  | Evidence that confirms                                                                                                           | Evidence that rules out                                                                              |
| ---------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Daemon temp directory missing                                          | The path named in the Docker event is absent on the allocation's Windows node.                                                   | The same path exists and Docker can create a new layer file there during the failing pull.           |
| Registry access or image tag problem                                   | Docker reports an auth, manifest, or registry connection error for the requested image.                                          | The pull fails creating a local temp file and the same tag succeeds after the directory is restored. |
| Cleanup or another filesystem operation moved or removed the directory | A retained delete or rename record matches the path and time. Process attribution requires matching audit or endpoint telemetry. | The incident did not retain enough history to establish or exclude a particular cleanup process.     |

Docker 24.0.6 prepares the temp directory at daemon startup. Layer downloads create temporary files in that directory and return a Windows path error if the directory is absent. [Daemon source](https://github.com/moby/moby/blob/v24.0.6/daemon/daemon.go) · [Pull source](https://github.com/moby/moby/blob/v24.0.6/distribution/pull_v2.go)

If free space is low, compare volume free space at failure time, the exact Docker error, and any cleanup activity. Windows reports `ERROR_DISK_FULL` for capacity failures and `ERROR_PATH_NOT_FOUND` for the missing path. Low free space can trigger cleanup, but attributing the directory loss requires evidence of a matching delete or rename. [Windows error codes](https://learn.microsoft.com/windows/win32/debug/system-error-codes--0-499-)

## Remediation (HUMAN executes; agent never runs)

1. Confirm the affected host, the exact path in the error, and the expected existing parent from triage. Record the parent ACL and confirm the target is absent. The missing directory has no contents to back up. If the target already exists or the parent points somewhere unexpected, stop and investigate the live path.
2. Create only the missing directory using `New-Item -Path $tempPath -ItemType Directory`. Check the resulting path and ACL with `Get-Item` and `Get-Acl`. Verify inherited access for the Docker service account, which is typically `NT AUTHORITY\SYSTEM` when the service runs as LocalSystem.
3. Let Nomad retry and watch the next allocation. If there is no allocation or pending evaluation, confirm that the job is intended to run before using the normal deployment procedure to trigger one.

Creating the directory allows waiting pulls to start and consume disk space. Keep Docker running during this repair. A rollback would return the host to a state where pulls can fail. If reversal is required, confirm the new directory is empty and unused before removing it under the incident owner's direction.

## Validation checklist

- [ ] The expected directory exists and the Docker service account has inherited access.
- [ ] A new allocation completes the Docker prestart task with exit code `0`, and the application task reaches `running`.
- [ ] For an in-game recorder, verify a test recording if the incident requires confirmation of media output. Task startup alone verifies the startup path.

## Not yet verified

- The initiating delete, move, or other filesystem operation remains unknown.
- A link between disk pressure, cleanup, and loss of the temp directory remains unverified.
- This recovery was observed once on the versions listed above. The runbook has yet to be verified on recurrence.
- Recorder media output and behavior on other Docker versions were outside the incident validation.
