---
name: ae-render-test-launch
description: Preflight or launch a controlled AE diagnostic render on an idle Windows renderer using the worker's desktop account and session. Use when investigating native AE failures or comparing diagnostic project variants.
metadata:
  type: SKILL
---

# AE diagnostic test launch

Use `scripts/windows-ae-test.py` to reproduce AE render failures or compare AEPX variants in the worker's desktop session. Find the renderer through the [diagnosis toolkit](../../diagnose_toolkit.md#discover-pcs-and-their-roles), then follow the procedure below from the repository root.

Windows/AE end-to-end execution remains unverified.

## Procedure

1. Identify the actual worker PID and full executable path from the deployment and live process inventory. Record its configured working directory, AE executable, composition, MFR/memory settings, expected output frame count, and output format. Do not select a PID from its name alone.

   A read-only process inventory through the existing WinRM client is:

   ```bash
   .venv/bin/python scripts/windows-winrm-session.py --host '<renderer-ip>' \
     --command 'Get-CimInstance Win32_Process | Select-Object ProcessId,Name,SessionId,ExecutablePath,CommandLine | ConvertTo-Json -Depth 3'
   ```

2. Choose an idle diagnostic window and coordinate queue activity with the operator. The runner refuses an already active AE process, but does not reserve the renderer or pause its worker. Use a generated AEPX project with absolute `fileReference.fullpath` values. The runner checks every serialized reference, including directory references, and renders a byte-identical copy in a new directory. Relative references must be resolved before use; binary AEP files and output image sequences are unsupported.

3. Prepare the command below with values verified on the target. All Windows paths refer to the renderer. `--output-root` must already exist on a local drive and be writable only by the diagnostic operator and worker account, because staged scripts execute as the worker. The defaults `--mfr ON --mfr-cpu 60 --memory 50 80` reproduce the source incident's settings; change them to match the worker under investigation.

   ```bash
   ae_test_args=(
     --host '<renderer-ip>'
     --worker-pid '<live-worker-pid>'
     --worker-exe 'C:\<worker-directory>\<worker>.exe'
     --working-directory 'C:\<worker-working-directory>'
     --aerender 'C:\<AE-support-files>\aerender.exe'
     --project 'C:\<session>\<generated-project>.aepx'
     --comp '<composition>'
     --output-root 'C:\<diagnostic-output-directory>'
     --output-name 'output.mp4'
     --ffprobe 'C:\<tools>\ffprobe.exe'
     --ffmpeg 'C:\<tools>\ffmpeg.exe'
     --expected-frames '<expected-frame-count>'
     --timeout-seconds 720
   )
   .venv/bin/python scripts/windows-ae-test.py "${ae_test_args[@]}"
   ```

   Add `--input-path '<absolute-input-path>'` for inputs not serialized as AEPX file references. Add `--dump-directory '<absolute-AE-reports-directory>'` to retain new or changed `.dmp` files. The source incident used the worker profile's `%LOCALAPPDATA%\Temp\Adobe\After Effects\23.0\SentryIO-db\reports`; resolve the actual profile and AE version rather than using the WinRM account's profile. Without this option, dump collection is skipped.

4. Review the read-only preflight JSON. It verifies worker PID/executable, account, session greater than zero, project hash, local tools/directories, and extracts input paths. **`desktopPathsChecked: false` is expected here:** WinRM cannot establish mapped-drive access in another desktop session. No task, output directory, or test process is created by this preflight.

5. Once the render experiment is authorized, execute the same command with `--execute`:

   ```bash
   .venv/bin/python scripts/windows-ae-test.py "${ae_test_args[@]}" --execute
   ```

   It creates `ae-test-<UUID>` under the output root and a temporary `Silica-AE-<UUID>` task. The task runs with the worker account's interactive token, targets its recorded session ID, and verifies the live worker identity/session again. It opens each input from that desktop context before rendering and tests output-directory access by writing its evidence there. Missing paths fail the test rather than prompting for drive remapping or changing credentials.

   The task joins a private Windows job before starting AE or validation tools. An ordinary child process inherits that job; closing its handle terminates the run's remaining processes. The worker is outside the job. A total render/validation deadline and a Task Scheduler execution limit bound the task. No process-name-wide kill is used.

6. Inspect the retained evidence and output. A result is `completed` only when AE returns zero without a recognized native error, the output is nonempty, ffprobe finds exactly the expected number of video frames, full video/audio decoding succeeds, and the source project hash remains unchanged. The controller also checks the worker identity and inventories remaining AE processes before returning success.

   | Artifact                                                        | Purpose                                                                                                              |
   | --------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
   | `preflight.json`, `request.json`, `runner.ps1`, `input.aepx`    | Worker/input context, requested settings, exact runner source, and unchanged project copy. Credentials are excluded. |
   | `render.command.json`, `render.stdout.log`, `render.stderr.log` | AE executable, argument array, working directory, deadline, and native output.                                       |
   | `probe.*`, `decode.*`                                           | Validation command arrays and stdout/stderr.                                                                         |
   | `result.json`                                                   | Task context, outcome, source integrity, validation, and collected dumps.                                            |
   | `postflight.json`                                               | Worker identity comparison and remaining AE process inventory, when the controller reaches postflight.               |
   | `native-*.dmp`                                                  | New/changed reports from the specified directory; time correlation alone does not establish process ownership.       |
   | `controller-error.log`, `task-cleanup-error.log`                | Controller failure or failed self-removal of the task, when present.                                                 |

7. Verify that the named task is gone and inspect any residual AE process before the next trial. The task attempts to remove itself; the connected controller also stops/removes only that generated task. Keep evidence until reviewed. An interrupted WinRM connection does not mean the remote run stopped: use the printed run directory and task name to inspect its state; its own deadline remains active.

## Interpreting the result

Matching the worker's account/session and checking its paths improves comparability. It does not establish identical environment variables, elevation, plugin state, preferences, GPU state, or output-module configuration. The task uses a limited interactive token and the explicitly supplied working directory. A mapped drive visible only to a different token can still fail its desktop check.

Windows job containment covers inherited child processes. Processes launched indirectly by another service may not belong to that job; the controller reports remaining AE processes and refuses success without killing them. If the controller disconnects, inspect these manually after the task's deadline. A restrictive script policy or incompatible existing job can prevent startup; investigate the retained error rather than weakening policy.

Frame count and decoding establish basic file validity. Compare picture/audio content separately before treating a diagnostic variant as correct. For MFR/footage-metadata experiments, follow the [AE investigation runbook](../../../knowledge/runbooks/docs/ae-mfr-footage-mtime.md).
