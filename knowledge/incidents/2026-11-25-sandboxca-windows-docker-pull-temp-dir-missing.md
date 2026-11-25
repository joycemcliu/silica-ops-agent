---
title: "SANDBOXCA in-game recorder pull blocked by a missing Docker temp directory"
incident_date: 2026-11-25
incident_time_range: "04:24 to 06:34"
timezone: UTC
store: SANDBOXCA
runbook: ../runbooks/docs/windows-docker-pull-temp-dir-missing.md
---

## Report, impact and scope

The SANDBOXCA office reported that the room 1 in-game recorder could not start after the job changed to image tag `0.4.7-rc.8`. The Docker prestart task repeatedly failed to pull the image, so the recorder executable never started in the affected allocations. The office uses the dev environment. Recording continuity during the incident was not measured.

## Instance details

| Item                 | Value                                                                                                                                               |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| Nomad API            | `10.253.0.101–10.253.0.103:4646`                                                                                                                    |
| Windows client       | `r1-exp` at `10.253.1.11`, Docker 24.0.6 with `windowsfilter`, Nomad 1.7.3                                                                          |
| Job and tasks        | `video-dge/in-game-recorder-1` in `default`. The Docker `download` prestart task stages the executable for the `raw_exec` task `execute`.           |
| Image                | `us-docker.pkg.dev/silica-development/images/video-dge-in-game:0.4.7-rc.8`                                                                          |
| Affected allocation  | `f743b600-1411-e7ee-6f18-a0315dcf86f2` logged the reported `GetImageBlob3222584214` error.                                                          |
| Recovered allocation | `9ce48f27-e883-1b43-4d10-0f6ed33ce00e` on `r1-exp`. [Nomad allocation](http://10.253.0.103:4646/v1/allocation/9ce48f27-e883-1b43-4d10-0f6ed33ce00e) |

## Evidence ledger

| ID  | Tag         | Command, query or evidence source                                                                                                                     | Result summary                                                                                                                                                                                                                                                                                                    |
| --- | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| E01 | observed    | Reporter message, Nomad job and Consul inventory via `scripts/store-nodes.py`                                                                         | The job targets the room 1 experience client. Consul identified it as `r1-exp`. Nomad reported its Docker driver healthy while the job was pending.                                                                                                                                                               |
| E02 | observed    | Nomad job, allocation history and evaluations APIs                                                                                                    | Job version 35 ran `0.4.1-rc.1` after a retry for a missing path under `image\windowsfilter\imagedb\content\sha256`. On version 36 and later, `0.4.7-rc.8` repeatedly failed at `C:\ProgramData\docker\tmp\GetImageBlob…`. Affected allocations exhausted their task retries while `execute` was still unstarted. |
| E03 | observed    | WinRM `Get-Item`, `Get-CimInstance Win32_Service`, `Get-Process dockerd`, `docker info`, `docker ps` and Docker events in the Windows Application log | `C:\ProgramData\docker\tmp` was absent. The Docker data root and image metadata directories existed. The same daemon process had run as LocalSystem since October 20, and other containers were running. Docker logged matching temporary-file creation errors.                                                   |
| E04 | observed    | Moby 24.0.6 daemon initialization and image pull source                                                                                               | Startup creates the daemon temp directory. The pull path calls `os.CreateTemp("", "GetImageBlob")` against the configured temp directory. [Daemon source](https://github.com/moby/moby/blob/v24.0.6/daemon/daemon.go) · [Pull source](https://github.com/moby/moby/blob/v24.0.6/distribution/pull_v2.go)          |
| E05 | observed    | `auditpol`, Security file-access event query, NTFS USN journal, PowerShell and Defender event queries                                                 | File System auditing was off when checked. No matching audit, PowerShell or Defender event surfaced, and the retained USN records started after the incident window. Task Scheduler Operational history was disabled when checked.                                                                                |
| E06 | observed    | Windows System disk events and `Get-Partition -DriveLetter C \| Get-Disk`                                                                             | Sampled Event ID 51 warnings named `Harddisk2`. At inspection, `C:` mapped to disk 1 and reported healthy. No causal link between these warnings and the directory loss was established.                                                                                                                          |
| E07 | observed    | Authorized WinRM `New-Item`, `Get-Item` and `Get-Acl`                                                                                                 | A filesystem-only retry created the missing directory after the initial WinRM command timed out. The new directory inherited Full Control for `NT AUTHORITY\SYSTEM`. Docker was left running.                                                                                                                     |
| E08 | observed    | Reporter confirmation and final Nomad job and allocation API checks                                                                                   | The reporter confirmed recovery. Nomad showed the job and allocation running, `download` terminated with exit code `0`, and `execute` started at `06:34:41 UTC`.                                                                                                                                                  |
| E09 | not-checked | Recorder media output and process responsible for the directory loss                                                                                  | Recovery was checked at task startup. No test recording or attribution of the directory loss was available.                                                                                                                                                                                                       |
| E10 | observed    | WinRM `Get-Volume -DriveLetter C` at about 04:50 UTC                                                                                                  | `C:` had 11,450,400,768 bytes free out of 511,749,459,968 bytes, about 10.7 GiB or 2.2%. Free space at the time the directory disappeared is unknown.                                                                                                                                                             |
| E11 | observed    | Follow-up report relayed from a teammate                                                                                                              | A second PC reportedly had a similar issue and insufficient storage. Its exact error, directory state, free-space readings, cleanup history, and recovery steps were not checked.                                                                                                                                 |
| E12 | observed    | Silica source, `apps/infra/terraform-module/templates/docker_gc.ps1`                                                                                  | The Windows cleanup script can run `docker system prune -af` at or below its free-space threshold. Its documented targets are unused Docker objects. No run was tied to the directory loss. [Docker prune reference](https://docs.docker.com/reference/cli/docker/system/prune/)                                  |

## Findings

The missing Docker temp directory prevented layer staging. It was absent while the Docker daemon was still running, so retries kept targeting the same missing directory. Recreating it allowed the same image tag to pull and the recorder to start (E02–E04, E07–E08).

The earlier metadata-path failure establishes that another Docker path error preceded the sustained pull failure. The evidence does not link those errors to one operation or identify what removed the temp directory (E02, E05–E06).

Low disk space is a **suspected indirect contributor**. It could have triggered a cleanup, but there is no evidence of a cleanup deleting or moving the directory. Windows reported `ERROR_PATH_NOT_FOUND` during the failed pulls, which is distinct from `ERROR_DISK_FULL`. The second PC is a lead for comparison (E10–E12). [Windows error codes](https://learn.microsoft.com/windows/win32/debug/system-error-codes--0-499-)

## Actions and recovery timeline

| UTC timestamp      | Action or observation                                                                | Result                                                                                 |
| ------------------ | ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Nov 24 22:08–22:13 | Earlier recorder allocation retried a pull after a Windows image metadata path error | `0.4.1-rc.1` recovered on retry and the recorder started at 22:13:40.                  |
| Nov 25 04:24:54    | First retained allocation failure on the new tag                                     | Layer staging failed under `C:\ProgramData\docker\tmp`.                                |
| Nov 25 04:50       | Inspected the Windows host over WinRM                                                | Confirmed the directory was missing while Docker was running.                          |
| Nov 25 06:30:07    | Recreated the absent directory after user authorization                              | Verified directory creation and inherited SYSTEM access.                               |
| Nov 25 06:34:41    | Recorder started on the recovered allocation                                         | Final Nomad check confirmed the prestart task exited `0` and the recorder was running. |

## Outcome and remaining work

Recorder startup recovered. The process that removed or moved the directory and the exact time of that change remain unknown. A recurrence could be attributed with targeted Windows delete and rename auditing on the temp directory and its parent. See the [diagnosis debrief](../debrief/docs/2026-11-25-sandboxca-windows-docker-pull-temp-dir-missing.md).
