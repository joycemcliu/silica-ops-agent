---
title: AmberSky trailer MFR failures and inherited footage timestamps
incident_date: 2026-11-09
incident_time_range: "11:53:33 to 14:56:21 (retained controlled trials through cleanup; earlier investigation start not retained)"
timezone: Asia/Hong_Kong
store: staging
runbook: ../runbooks/docs/ae-mfr-footage-mtime.md
---

## Report, impact and scope

- `ambersky_trailer` in AmberSky was reported as repeatedly failing with `AE log timeout`. Diagnosis is complete; production recovery is not confirmed. The user deferred further fix testing and rollout.
- Reproduced on staging using two independent sessions on the same renderer. Timestamp-only diagnostic repairs succeeded with MFR ON 60; the implementation PR has not been deployed or rendered end-to-end as part of this closeout.
- Production history was a bounded sample, not a fleet-wide failure rate: the latest 20 terminal attempts in the five-day search contained 6 successes and 14 failures. Successful commands used AE2023 and MFR ON 60. A successful store also had failures; one session on one node failed and later succeeded.

## Instance details

| Item | Value |
| --- | --- |
| Environment / service | Staging / video-dge renderer |
| Renderer | `r4-video`, `10.250.0.54`; worker PID `15188` remained running |
| Primary session | `sbvrdev-261109-T4-083300` |
| Independent validation session | `sbvrdev-261108-T4-112602` |
| Engines | AE23 `23.4.0.53`; AE22 `22.2.0.120` |
| Source template | `C:\silica\video-dge\renderer\Experiences\AmberSky_6.2.0\AmberSky_DGE_Trailer.aepx.tmpl` |
| Primary generated project | `C:\silica\video-dge\renderer\Session\sbvrdev-261109-T4-083300\raw\ambersky_trailer-AmberSky_DGE_Trailer.aepx` |
| Initial nine-run results | `/private/tmp/ambersky-nine-runs-results.json`; logs `/private/tmp/ambersky-render-logs.zip` |
| AE22 results | `/private/tmp/ambersky-ae22-test/result.json` |
| Intermediate investigation | `/private/tmp/ambersky-investigation-logs.zip` |
| Final evidence bundle | `/Users/7am/Downloads/Ambersky-metadata-tests-20261109/logs-and-results.zip` |
| Final result table | `/Users/7am/Downloads/Ambersky-metadata-tests-20261109/results.csv` |
| Local project copies | `/Users/7am/Downloads/Ambersky-sbvrdev-261109-T4-083300/` |
| Fix handoff | [SandboxVR/silica PR #4751](https://github.com/SandboxVR/silica/pull/4751), branch `fix/video-dge-ae-footage-mtime`, commit `0853bbd620e89e2275faeccf1e45a821534b159b` |

Windows experiment roots are under `C:\silica\video-dge\renderer\AEOutput\`:

- `sbvrdev-261109-T4-083300\experiment-20261109-1148`
- `sbvrdev-261109-T4-083300\ae22-test-20261109\ae22-mfr-on-1`
- `sbvrdev-261109-T4-083300\investigation-20261109-1248`
- `sbvrdev-261109-T4-083300\metadata-split-20261109-1354`
- `sbvrdev-261108-T4-112602\metadata-validation-20261109-1356`

Native AE crash reports were collected from `%LOCALAPPDATA%\Temp\Adobe\After Effects\23.0\SentryIO-db\reports`; preserved experiment copies are named `AfterFX-crash.dmp`. AE22 uses the corresponding `22.0` directory. Per-run `stdout.log`, `stderr.log`, and `result.json` retain the actual commands and outcomes. AE23 MC preferences were restored/verified against their pre-experiment bytes; diagnostic outputs were retained for review.

## Evidence ledger

Scope: source inspection, staging render experiments, capped production log queries, local artifact inspection, implementation review, and final read-only cleanup. Repeated render invocations are grouped below; their complete argument arrays and results are in the linked bundles. The exact earliest Nomad and production LogQL invocations are not retained, so no query text is reconstructed here.

| ID | Tag | Command/query or evidence source | Result summary |
| --- | --- | --- | --- |
| E1 | observed | Production Grafana datasource `silica-loki`; search window 2026-11-04 03:32:38Z through 2026-11-09 03:32:38Z; latest 20 terminal attempts | 6 successes / 14 failures across 7 sessions and 6 stores. Successful attempts were matched to start commands by trace/node. Intermittent success contradicts universal failure of this item or MFR. |
| E2 | observed | `scripts/windows-winrm-session.py --host 10.250.0.54 --command <script>`; temporary interactive scheduled tasks invoking AE23 `aerender.exe -project <copy> -comp cctv -output <unique-output> -mfr ON 60 -mem_usage 50 80` | Nomad execution was denied. User authorized direct staging WinRM. Actual render trials used the renderer's interactive desktop context rather than WinRM session 0. NAS material was read through the existing staging HTTP file endpoint because mapped M: was unavailable in WinRM. |
| E3 | observed | Nine-run `rows` and per-run native logs | Original ON 60: 0/3; original OFF: 3/3; Lumetri, Set Matte, and Color Key disabled together with ON 60: 0/3. OFF successes took 188.37, 143.20, and 188.17 seconds. |
| E4 | observed | AE22 `result.json`, stdout and output inspection | Opened the project, selected QuickTime output, then stalled at frame 974/1848. Stopped the owned render after 320 seconds without progress; total 398.42 seconds. No native dump established a crash. |
| E5 | observed | Intermediate investigation `results.json`, preference backups, transcode logs | Disabling hardware decoding alone failed. Converting the seven referenced session in-game clips from H.264 4:4:4 to 4:2:0 alone failed. Native AE23 binary save passed with CUDA and with software rendering; resaved XML passed 3/3. The unchanged original and a relocated byte-identical original still failed. |
| E6 | observed | Source `render.go`, `ae_template_data.go`; byte comparison of the deployed template and generated project | Replacing only the 43 literal `.Path` actions reproduced the original generated project byte-for-byte. Generation preserved GUIDs and serialized import records. No missing path substitution was found. |
| E7 | observed | Native-save comparison and filesystem mtimes for 43 external references | The examined 222-byte `Item.Pin.sspc` record stores a four-byte big-endian modification time at bytes 118–121, represented by hex-string slice `[236:244]`. Values matched whole seconds since 1904-01-01 UTC. Template example `e109dae8` is 2023-08-22 03:24:24Z; native value `e716e9d0` matched the referenced file at 2026-11-09 03:09:04Z. |
| E8 | observed | `first-session/field-audit.json` and strict variant hashes in the final bundle | Correction: the earlier successful “GUID + timestamp” copy also changed other import-record fields on 25 of 43 external references. The final split tests changed only GUIDs, or only the four timestamp bytes, and preserved all remaining XML. |
| E9 | observed | Final first-session results; `aerender` arguments as E2 | GUID-only: 0/3, all native crashes. Timestamp-only: 3/3, 105.76 / 101.76 / 101.61 seconds. |
| E10 | observed | Final second-session generation verification and results | Rebuilt from the deployed template and matched its archived Go-generated project exactly. Unchanged ON 60 failed in 46.66 seconds; OFF passed in 183.65 seconds; timestamp-only ON 60 passed 3/3 in 103.23 / 101.30 / 105.52 seconds. |
| E11 | observed | `ffprobe -count_frames`, full `ffmpeg` decoding, `ssim`, decoded PCM SHA256, frame contact sheet | All final successful outputs had 1,848 frames. Timestamp-only versus OFF video SSIM: 0.997574 / 0.997579. Decoded audio hashes matched exactly for both sessions. Sampled first-session frames showed consistent content. Video is not pixel-identical. |
| E12 | observed | Preserved minidumps; local LLDB with matching PE modules | Access violations in PIN, PluginSupport, VideoRenderer, and ImporterHost appeared across trials. A new GUID-only dump faulted in ImporterHost; export-derived unwinding included footage render-GUID work and an MFR worker. Private Adobe symbols were unavailable; large nearest-export offsets are not exact function identification. |
| E13 | inferred | E3–E12 | A footage-change/import-state refresh path under MFR is the strongest explanation. Matching stored mtimes removes the tested trigger. The exact internal race/object-lifetime defect and every production timeout's native cause are not proven. |
| E14 | observed | PR #4751 and local review | Added opt-in `AEFootageMTime`, conversion CLI, tests and rollout guide. Focused tests, race checks, vet, and Windows all-package cross-build passed. Real-template conversion changed exactly 43 timestamp expressions; all other bytes were preserved. Repeat conversion was byte-identical; overwrite was refused. |
| E15 | observed | Final read-only WinRM inventory at 14:56:21; local process inventory filtered for diagnostic clients | No `Silica-AE-*` scheduled tasks or AE processes remained. Worker PID 15188 was running. Source/deployed template hashes remained unchanged. No active diagnostic WinRM/sshuttle/forwarding process was identified locally. No shared Grafana forwarding was stopped. |
| E16 | not-checked | Deferred by user | Post-implementation end-to-end AE renders, production deployment/recovery, broader fleet/version validation, and final CI state. The latest retained CI snapshot had the main workflow still running. |

## Findings

**Confirmed:** timestamp-only changes succeeded in six of six trials across two sessions on the same staging renderer, while GUID-only changes failed in all three trials. The unmodified second session reproduced the failure. Timestamps are therefore an effective discriminating change in these projects; old timestamps alone are not a universal template-invalidity test.

`AE log timeout` is the renderer watchdog's symptom. Controlled runs exposed native crashes, unexpected AE connection closure, and an AE22 stall. Some `aerender` failures returned exit code zero with an invalid/empty output. Exit status alone is insufficient to classify success.

Disabling the three suspected effects, disabling hardware decoding, or normalizing the tested in-game media was insufficient on its own. The AE22 test did not establish that a version downgrade fixes this problem. Remaining codecs, GPUs, effects, and other AE versions were not universally ruled out.

The fix belongs at session-project preparation time because `.Path` selects different files per session. A fixed timestamp edited into the external template can become mismatched again. The opt-in helper uses the resolved file's actual mtime, not the render start time, and leaves other templates unchanged until converted.

## Actions and recovery timeline

| Timestamp (HKT) | Action actually taken | Result | Backup / rollback reference |
| --- | --- | --- | --- |
| Before 11:53; exact start not retained | Copied session materials, established an interactive diagnostic runner, preserved originals | Local reproduction possible | Original source retained; separate output directories |
| 11:53–12:10 | Nine controlled MFR/effect trials | E3 | Per-run results and preserved dumps |
| 12:26–12:33 approximately | AE22 trial; stopped only the owned stalled process tree | E4 | Source unchanged; task removed |
| 12:48–13:23 approximately | Decoder/media/save-format/metadata comparisons | E5–E8 | Preference backup and hashes; separate variant files |
| 13:54–14:16 approximately | Strict field split and independent-session validation | E9–E11 | Final bundle, field audits and source hashes |
| 14:42–14:44 | Implementation committed, pushed and PR created | E14; no deployment | Branch/commit above; external content unchanged |
| 14:56:21 | Final read-only closeout inventory | E15 | Artifacts retained; no cleanup mutation needed |

Integrity references:

- Original primary project SHA256: `d3fb7d6a4f24d1057fdf415def46c114f90bd00a487227ba968834b7a714cc87`.
- Deployed template SHA256: `4df230df23593cc600654475e67f950abf45123f3d66a562a6e825c19d51682b`.
- AE23 MC preferences verified unchanged at experiment cleanup: `0493b700adb3fc095dd83be2fd914cdef45d41c364dca9d60f6c0d6d780ebedc` (also retained in `final-verification.json`).

## Outcome and remaining work

1. **Diagnosis complete.** Reproduction, field isolation, artifact preservation, implementation handoff, and diagnostic resource cleanup are complete.
2. **Staging workaround validated; production recovery unverified.** The diagnostic edits are not a deployed remediation. Further implementation testing was deferred by the user.
3. PR #4751 is the handoff. An upgraded renderer must precede publication of converted external templates; incompatible consumers need unconverted content. Full native Mac module tests encounter the pre-existing Darwin `setProcAttrFor` build gap; Windows builds were cross-compiled, not Windows tests executed.
4. Exact Adobe internals, the minimal triggering reference subset, other record layouts, other hosts/builds, and production effectiveness remain unverified. No further experiments, CI monitoring, merge, or rollout is scheduled by this diagnosis closeout.

