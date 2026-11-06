---
title: Webcam MJPEG 720p capture truncates the field of view
slug: webcam-mjpeg-720p-top-left-crop
services: [video-dge, webcam]
tags: [windows, directshow, mjpeg, webcam, fov]
status: draft
last_verified: 2026-11-06
applies_to:
  camera_family: Logitech Webcam C930e; verify actual device capabilities
  capture: Windows DirectShow MJPEG
  ffmpeg_observed: 5.1.2 essentials build
  windows_observed: Windows 11 Pro build 22621
  driver_package_observed: Logitech 1.1.135.0 using usbvideo
  video_dge_override_contract: 0.4.6
source_incidents:
  - ../../incidents/2026-11-05-ussanval-webcam-mjpeg-fov.md
---

## Symptoms

- Raw webcam recordings or previews appear zoomed/cropped in some rooms while other rooms look normal.
- Windows Camera can appear normal while an unfiltered FFmpeg DirectShow frame has a narrower field of view.
- In the observed failure signature, 1280x720 MJPEG loses the right and bottom portions of the scene; 1920x1080 MJPEG preserves a wider view. Do not assume that every FOV report has this mechanism.

## Safety and anti-anchoring

- Follow the current diagnosis instructions and store instructions before access. Use the documented diagnosis venv and tunnel workflow; do not copy credentials into commands or reports.
- Read-only inspection is allowed by diagnosis policy. Capture opens the device, can contend with production, and creates evidence files: obtain an idle-room window and authorization first. Do not stop services or reset camera controls to make a test possible.
- A normal Windows Camera image alone does not prove equivalent video mode or controls. Photo mode is not an equivalent comparison.
- Default or disabled Zoom controls alone do not prove identical effective capture behavior.
- Matching friendly names, USB vendor/product IDs, or driver package labels alone do not prove identical hardware, firmware, advertised modes, or per-device settings.
- No crop filter alone does not exclude decoding effects. An already-cropped MJPEG stream-copy frame excludes decoding/encoding as necessary causes, but not DirectShow negotiation.
- `-f mjpeg` after `-i` selects an output format; use input `-vcodec mjpeg` before `-i` to request MJPEG capture.
- `-video_pin_name 0` means a driver's alternative pin name, not camera number. Do not hardcode a mapping across PCs without verification.
- Do not infer counterfeit hardware or a firmware defect from descriptor/capability differences alone.

## Triage (read-only, in order)

Commands below are parameterized equivalents of operations executed in the source incident. Run the PowerShell checks through the documented WinRM client. Supply `<ffmpeg>`, `<camera-name>`, and other placeholders from observed configuration, not assumptions. Snippets use variables for readability; assign them in the same noninteractive command invocation.

### 1. Establish host identity, presence, and competing clients

```powershell
hostname
Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress
Get-PnpDevice -PresentOnly | Where-Object {$_.Class -in @('Camera','Image')} | Select-Object Status,FriendlyName,InstanceId
Get-CimInstance Win32_Process | Where-Object {$_.Name -match '^(ffmpeg|webcam|WindowsCamera|Logi.*)\.exe$'} | Select-Object Name,ProcessId,ExecutablePath,CommandLine
```

- Good: correct store/host, camera present and healthy. For capture approval, no competing capture client at the check time; this does not guarantee room/session idleness.
- Bad: absent camera or incorrect host. Stop capture testing; an old retained PnP record is not a present device. Active capture clients require coordination, not automatic termination.

### 2. Establish negotiated input and actual configuration

- Inspect existing capture logs for `Input #0`, video codec, dimensions, frame rate, and stream mapping. Use incident-specific paths, not broad config/log dumps that might contain secrets.
- Read only the generated `video_config.json` associated with the actual running webcam process allocation. Compare recording, standalone preview, and RTSP independently with the pinned module release.
- Good: recorded effective arguments explain the input/output contract and match intended deployment.
- Bad: generated config differs from checked-in intent, or only one output path has the workaround. Repository defaults alone do not prove runtime state.

### 3. Compare capabilities and physical identity

```powershell
$ErrorActionPreference='Continue'
& '<ffmpeg>' -hide_banner -list_options true -f dshow -i 'video=<camera-name>' 2>&1 | ForEach-Object {"$_"}
```

- Good: requested codec/size/rate is advertised. Compare the entire mode list and pin layout with a known-good device.
- Bad: unsupported requested mode, differing capabilities, or wrong device selected. Device-listing commands normally exit after printing options; an exit/error footer alone is not evidence of failed recording.
- Execute the binary directly in PowerShell. An extra `cmd.exe` quoting layer caused a false device-name error in the source investigation.

Select the actual camera instance and inspect metadata:

```powershell
$camera=Get-PnpDevice | Where-Object {$_.InstanceId -eq '<device-id>'}
$camera | Get-PnpDeviceProperty | Where-Object {$_.KeyName -match 'IsPresent|DriverVersion|DriverProvider|HardwareIds|BusReportedDeviceDesc|Parent|Service'} | Select-Object KeyName,Data
```

- Good: camera is present and its metadata/capabilities are recorded for comparison.
- Bad: `IsPresent=false` blocks live camera tests. Different bus descriptions, pin layouts, or MJPEG chroma are evidence of different behavior, not proof of a particular defect.
- Retained metadata can help identify an absent camera, but current signed-driver queries may omit it.

### 4. Compare actual software, not only labels

```powershell
& '<ffmpeg>' -version | Select-Object -First 2
Get-FileHash -LiteralPath '<ffmpeg>','<usbvideo.sys>','<ksproxy.ax>' -Algorithm SHA256
Get-CimInstance Win32_OperatingSystem | Select-Object Caption,Version,BuildNumber
```

- Good: exact hashes and OS/driver versions available on affected and comparison hosts.
- Bad: different executable/driver binaries are a remaining variable. Equal binaries rule out a simple binary-version difference, not all host/per-device state.

## Likely causes

| Cause                                                         | Evidence that confirms                                                                                                                 | Evidence that rules out                                                                                   |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| MJPEG mode-specific truncation at the capture boundary        | Direct-copy 720p packet renders as a top-left crop of 1080p; repeat at supported rates                                                 | Direct-copy packet has full FOV and only processed output is cropped                                      |
| Frame-rate-dependent capture behavior                         | Same resolution/codec is cropped only at one advertised rate                                                                           | Source incident reproduced the same crop at both tested rates                                             |
| FFmpeg decoding, filtering, encoding, or downstream rendering | Direct-copy frame normal, processed result cropped                                                                                     | Source incident's stream-copy JPEG was already cropped; these stages were not necessary to reproduce it   |
| Different FFmpeg/UVC/proxy binary versions                    | Behavior tracks differing binaries in a controlled test                                                                                | Source incident comparison binaries matched by SHA-256                                                    |
| Device firmware/hardware variant or device-persisted state    | Separately authorized cross-swap makes symptom follow the physical camera; firmware/descriptor evidence further distinguishes variants | Symptom stays with host under a controlled cross-swap; exact cause still requires investigation           |
| Host/per-device DirectShow negotiation or configuration       | Cross-swap makes symptom stay with PC, or equivalent-mode alternate-API test separates negotiation paths                               | Symptom follows device across controlled hosts; matching package labels alone do not rule it out          |
| Effective camera zoom/pan/tilt                                | Read effective controls and demonstrate a controlled relationship to framing                                                           | Property dialog default/disabled status alone is insufficient; not confirmed or ruled out by this session |

## Remediation (HUMAN executes; agent never runs)

### A. Obtain approved diagnostic evidence before changing settings

These capture commands were executed with explicit permission in the source incident; they are not read-only triage steps. Do not execute this section automatically.

- Guard: verify target identity, advertised modes, idle-room authorization, no competing capture, stable scene, and sufficient disk space. Do not collect customer footage without appropriate operational authorization.
- Backup: preserve existing configuration and evidence; choose a new evidence directory and unused filenames. `-n` prevents overwrite. Directory creation and image retrieval require authorization too.
- Risk: temporary camera contention and storage of room imagery. Run sequentially and stop if recording starts or capture fails.
- Rollback: no camera controls are changed. Confirm each capture exits; retain images under evidence policy. Delete only specifically authorized diagnostic files, never broad camera-output directories.

```powershell
& '<ffmpeg>' -hide_banner -n -f dshow -vcodec mjpeg -video_size 1280x720 -framerate 30 -i 'video=<camera-name>' -map 0:v:0 -frames:v 1 -c:v copy -f mjpeg '<new-evidence-dir>\720p30-direct.jpg'
& '<ffmpeg>' -hide_banner -n -f dshow -vcodec mjpeg -video_size 1280x720 -framerate 10 -i 'video=<camera-name>' -map 0:v:0 -frames:v 1 -c:v copy -f mjpeg '<new-evidence-dir>\720p10-direct.jpg'
& '<ffmpeg>' -hide_banner -n -f dshow -vcodec mjpeg -video_size 1920x1080 -framerate 30 -i 'video=<camera-name>' -map 0:v:0 -frames:v 1 -c:v copy -f mjpeg '<new-evidence-dir>\1080p30-direct.jpg'
```

Use the lower rate only if advertised. Check native exit codes explicitly through WinRM. Preserve stdout as binary when retrieving image streams; base64 file retrieval through encrypted WinRM with remote/local SHA-256 comparison was used in the source incident.

Inspect images visually and compare lower-resolution frames against both top-left and centered crops and a full-frame downscale of the higher-resolution frame. Brightness-normalized image correlation can support the comparison but is not a universal threshold or firmware diagnosis. Dark scenes limit visual confidence.

### B. Work around the affected MJPEG capture mode

- Guard: first verify advertised 1920x1080 MJPEG/30 fps has correct FOV on each target. Scope to explicitly confirmed rooms; preserve unrelated rooms and output paths. Require reviewed GitOps deployment and an idle-room window.
- Backup: record the current module version, effective JSON, and reviewed revision before changing configuration. Preserve dynamic device and output placeholders rather than incident filenames.
- Action: explicitly request 1080p MJPEG input; software-downscale to 1280x720. The verified output structure for recording plus cached preview was:

```text
-f dshow -vcodec mjpeg -video_size 1920x1080 -framerate 30 -rtbufsize 100M -use_wallclock_as_timestamps 1 -i video=<camera-name> -filter_complex "[0:v]scale=1280:720,split=2[main_s][p];[p]fps=1/5[p_s]" -map "[main_s]" -c:v libx264 -pix_fmt yuv420p -r 30 -preset ultrafast <output.mp4> -map "[p_s]" -update 1 -q:v 18 -f mjpeg pipe:1
```

Standalone preview must also use 1080p input and scale before single-frame output:

```text
-f dshow -vcodec mjpeg -video_size 1920x1080 -framerate 30 -i video=<camera-name> -vf scale=1280:720 -vframes 1 -f mjpeg pipe:1
```

Preserve the caller's existing logging/overwrite options. In an application's argument array, the device expression and filter graph are single arguments without literal shell quotes.

- For video-dge's verified override contract, `webcam_recorders` accepts `video_config_json`; an empty string retains module defaults. A complete JSON override must preserve all required sections. Use explicit room IDs and a store-local file, not a global template change.
- RTSP is a separate path: review its scope explicitly. Leaving its input at the failing mode can retain cropped live view even when recording and standalone preview are corrected.
- Risk: 1080p input increases decode/scaling and possible USB load; applying job configuration can restart recorders. Synthetic validation does not establish sustained hardware performance.
- Rollback: revert the reviewed room-scoped override through the normal deployment process during an idle period; verify effective configuration. This can reintroduce the original crop. Do not reset controls or replace drivers as part of rollback.

## Validation checklist

Machine checks:

- [ ] Each required capture mode is advertised and effective input logs match requested codec, size, and rate.
- [ ] Direct-copy capture logs say `Stream ... (copy)`; remote/local evidence hashes match after retrieval.
- [ ] Recording and both preview paths preserve their required output contracts; any excluded RTSP path is stated explicitly.
- [ ] Formatting, JSON integrity, pinned-module comparison, and isolated per-room selection checks pass.
- [ ] Synthetic output test checks codec/dimensions/frame rate and preview frame count over a known duration. Raw MJPEG's inferred stream frame rate does not prove preview cadence.
- [ ] Effective deployed JSON matches approved intent; full-store plan/CI checked separately.
- [ ] No diagnostic capture processes remain; close only session-created tunnels and panes. Leave pre-existing/unrelated tunnels untouched.
- [ ] Long-session dropped-frame/resource checks completed before claiming sustained recovery; not established by brief captures or service health alone.

Human-only checks:

- [ ] Visible room boundaries/FOV are correct in recording, recording-time cached preview, and standalone preview.
- [ ] Compare Windows Camera in known video mode rather than an unspecified photo view.
- [ ] Confirm unchanged rooms and explicitly scoped live-view paths behave as expected.

## Not yet verified

- `not-checked`: exact underlying defective component. DirectShow negotiation, driver/per-device state, and camera firmware/hardware remain distinct possibilities.
- `not-checked`: controlled physical camera/PC cross-swap. HUMAN-only follow-up requiring separate maintenance permission, target identification, recorded original connections/settings, and rollback to those connections; do not execute automatically.
- `not-checked`: equivalent-mode alternate-API capture, raw USB/UVC descriptor inspection, and camera firmware version comparison.
- `not-checked`: cause of `EOI missing, emulating` warnings on the comparison camera.
- `not-checked`: sustained Windows recording performance, full-store Terraform plan/CI, and recurrence-based human validation of this runbook.
- Do not present the validated 1080p workaround as proof of a firmware defect or as a universal requirement for this camera family.
