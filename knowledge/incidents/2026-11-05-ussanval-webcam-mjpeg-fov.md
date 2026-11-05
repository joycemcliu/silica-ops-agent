---
title: USSANVAL webcam MJPEG 720p top-left crop
incident_date: 2026-11-05
timezone: America/Los_Angeles
runbook: ../runbooks/docs/webcam-mjpeg-720p-top-left-crop.md
---

## Report, impact and scope

- Rooms 2 and 4 were reported to produce zoomed-in raw webcam recordings. Windows Camera reportedly showed the expected FOV, while an unfiltered FFmpeg DirectShow capture did not.
- The failing resolution was clarified as 1280x720, not 180x720 or 1080x720.
- The operator reported that 1920x1080 MJPEG/30 fps input with software downscaling worked in both affected rooms. This report is distinct from the agent's subsequent direct-copy frame inspection.
- Investigation moved from R2 to R4 because the R2 camera was absent during live inspection. R1 was inspected as a comparison, including separately approved captures.
- Investigation completed with a confirmed capture-boundary mechanism and a validated workaround, not a confirmed firmware/driver root cause. Original onset and affected recording interval remain unknown.

## Instance details

| Item | Value |
| --- | --- |
| Store / environment | USSANVAL / prod; America/Los_Angeles |
| Forwarded LAN | 10.164.0.0/16 |
| R2 | r2-exp / 10.164.2.11; no camera present during inspection |
| R4 | r4-exp / 10.164.4.11; affected camera connected |
| R1 | r1-exp / 10.164.1.11; comparison camera connected |
| R2 allocation | f0362bc2-f40b-b861-f2da-7da91b6cc3ca |
| R4 allocation | 11a3d061-3dc8-ac04-4659-44329b3e516b |
| Runtime video config | C:\silica-infra\nomad\data\alloc\<allocation>\execute\local\video_config.json |
| FFmpeg | C:\silica\video-dge\bin\webcam\ffmpeg\ffmpeg.exe; 5.1.2 essentials build |
| Windows / driver | Windows 11 Pro build 22621; Logitech package 1.1.135.0; service usbvideo |
| R2 retained / R4 present USB parent | USB\VID_046D&PID_0843\391D2B7E; matching reported identity does not prove a physical swap |
| R1 USB parent | USB\VID_046D&PID_0843\7549E63E |
| Physical diagnostic frames | On each tested PC: C:\silica\video-dge\webcam-fov-diagnostics\ |
| Local R4 copies | /home/sandbox/.hermes/profiles/diagnose/cache/scratch/r4-webcam-fov/ |
| Local R1 copies | /home/sandbox/.hermes/profiles/diagnose/cache/scratch/r1-webcam-fov/ |
| Store change | SandboxVR/silica-environments branch fix/ussanval-r2-r4-webcam-fov; commits 2ca6db75 and 2faf07f0 |
| PR status | Branch push verified; agent did not create a PR because GitHub API authentication was unavailable. Subsequent PR/merge state not checked. |

## Evidence ledger

All commands were performed through the documented toolkit after authorization where needed. Credential contents are intentionally omitted. Grouped entries cover repeated checks/retries of the same command family; only successful observations support incident findings.

| Tag | Command/query or evidence source | Result summary |
| --- | --- | --- |
| observed | Read root config.env, docs/diagnose_agent.md, store AGENTS.md, runbook index, module and templates | Resolved ../silica and ../silica-environments; store uses video-dge 0.4.6 and Windows default capture path. Updated diagnosis instructions were re-read during the session. |
| observed | git status --short --branch; git branch --show-current; git remote -v; git fetch origin; git log -1 --oneline origin/master | Store worktree was initially clean; fix branch started from fetched origin/master. Unrelated ops-agent edits were preserved. Source repo was not updated. |
| observed | gcloud storage cat gs://silica-production-terraform-modules/apps/video-dge/0.4.6/variables.tf and templates/webcam-config-windows.json | Pinned release supports per-recorder video_config_json; default recording, preview, and RTSP request 1280x720 input. |
| observed | terraform fmt -check; git diff --check; isolated terraform validate and console evaluation of exact webcam_recorders expression | Formatting passed; only string room IDs 2 and 4 selected the override. This was not a full-store plan. |
| observed | Synthetic ffmpeg test of actual recording/preview output arguments and ffprobe -count_frames | Eleven-second 1080p/30 source produced 330 H.264 720p/30 frames and two cached 720p JPEGs. Separate preview test produced one 720p JPEG. Physical DirectShow/FOV not exercised by synthetic test. |
| observed | git add of the two explicit store files; git commit; git push; git ls-remote --heads; git rev-parse HEAD | Remote branch matched commit 2faf07f0f04941e53ef84ecb8084963a443b4887 after standalone preview correction. No production apply was run by the agent. |
| observed | gh auth status; browser startup attempt | gh was absent; no API token was available; browser could not start due to missing native dependency. No PR creation was claimed. |
| observed | command-guard-client.py submit | Gateway socket unavailable. User subsequently explicitly authorized direct tools instead. |
| observed | bash scripts/store-sshuttle.sh USSANVAL; Herdr pane inspection and move | Initial noninteractive attempt failed at sudo and cleaned up its forward. User entered sudo in a dedicated pane. Stale inherited pane context initially placed it in another tab; the created pane was moved beside the user's chat. |
| observed | windows-winrm-session.py retries using the separate winrm venv | Local validation initially rejected credential permissions/structure; operator corrected them. Authentication was not attempted while validation failed. No secrets displayed. |
| observed | bash scripts/setup-windows-winrm.sh | Separate winrm venv lacked pip/ensurepip; setup failed. No system-package changes performed. |
| observed | Updated documented diagnose venv: uv pip install -r scripts/requirements-windows-winrm.txt; uv pip check | Dedicated diagnose venv usable; pypsrp==0.9.1 dependency check passed. Subsequent WinRM commands used its explicit Python. |
| observed | WinRM hostname; Get-NetIPAddress; Get-CimInstance Win32_OperatingSystem; Get-CimInstance Win32_Process | Verified target identities/IPs and process state. No ffmpeg/WindowsCamera process detected immediately before approved capture batches; webcam service remained running. |
| observed | Get-PnpDevice -PresentOnly; Get-PnpDeviceProperty; Get-CimInstance Win32_PnPSignedDriver | R2 retained C930e record had IsPresent=false; R4 and R1 cameras were present. Present-only driver query alone missed the disconnected R2 record. |
| observed | Selected camera driver registry fields via Get-ItemProperty / Get-ChildItem; selected DEVPKEY properties | No explicit zoom/crop value found in inspected driver fields. This does not establish effective UVC controls or camera state. |
| observed | Get-Content of the exact R2 and R4 allocation video_config.json files | Runtime recording and standalone preview both contained the 1080p-input/downscale workaround. RTSP remained at 720p. Who deployed it and full deployment history were not established. |
| observed | ffmpeg.exe -version; Get-FileHash -Algorithm SHA256 for ffmpeg.exe, usbvideo.sys, ksproxy.ax on R1 and R4 | All three files matched byte-for-byte across comparison hosts; values below. |
| observed | ffmpeg.exe -hide_banner -list_options true -f dshow -i 'video=Logitech Webcam C930e' | R1 advertises one capture pin, R4 two including H.264. Supported sizes/rates differ. Initial cmd.exe quoting attempts failed; direct PowerShell invocation succeeded. Listing exits after printing options and is not a failed capture. |
| observed | Approved direct-copy captures: ffmpeg.exe -hide_banner -n -f dshow -vcodec mjpeg -video_size <size> -framerate <rate> -i 'video=Logitech Webcam C930e' -map 0:v:0 -frames:v 1 -c:v copy -f mjpeg <new-file> | Captured 720p/30, 720p/10, and 1080p/30 on both R4 and R1. Logs show stream mapping copy. All six captures completed. |
| observed | WinRM ReadAllBytes/Base64 retrieval; remote Get-FileHash and local hashlib.sha256 | Retrieved all six images; local and remote SHA-256 matched for each. |
| observed | Native image inspection; Pillow grayscale Pearson correlation at 128x72 | R4 720p matches top-left crop; R1 matches full-frame downscale. Measurements below; R1 scene dark. Correlation is supporting evidence, not a universal pass threshold. |
| observed | Get-Process -Name ffmpeg after each capture batch | No remaining ffmpeg capture processes. |
| observed | Final Herdr pane read/process-info; local process and socket checks; herdr pane close w1:p7 | Session tunnel had already exited; its SSH port 40164 was closed. Closed only the created idle diagnostic pane. An unrelated USBAYMKT tunnel wrapper was left untouched. WinRM clients close runspaces/connections after each command. |
| inferred | Combined direct-copy, geometry, and host comparison | R4 delivers a top-left-truncated 720p MJPEG frame at the DirectShow boundary. Device-specific firmware/hardware/state or negotiation is the leading unresolved class. |
| not-checked | Physical camera swap; raw USB descriptor/firmware readout; alternate capture API at equivalent mode | Not performed. Cannot distinguish camera-internal defect from per-device host negotiation/configuration. |
| not-checked | Full-store Terraform plan; GitHub CI; sustained Windows recording; CPU/USB performance | Not performed. Brief captures do not establish long-session stability. |

### Captured artifacts and integrity

| Host | Filename | Bytes | SHA-256 |
| --- | --- | ---: | --- |
| R4 | 720p30-direct.jpg | 46888 | fbf422c61733859cf7f05d1defb0501e914e80850b35ed1b31d498fafe58bd50 |
| R4 | 720p10-direct.jpg | 46944 | a6f0ad6a35886e33f45dcbaf08f2a07c3185334acda19892626240d2a3d4ff06 |
| R4 | 1080p30-direct.jpg | 139480 | 69a1eed443d5189093e456644ab4c1edb57256fa101924ad44231c3af47593e1 |
| R1 | 720p30-direct.jpg | 21120 | b5b1a51693cda2ec7a976358903664e80d4a7f0d4925865f54a47c021c278359 |
| R1 | 720p10-direct.jpg | 21152 | b16a2d1b6297489fc32f8791a6cccfc6a2324174ae08958a88d317c8f1a1aa9c |
| R1 | 1080p30-direct.jpg | 45544 | b2beda4867a7f6f8fdb3835e52b58cc79c2c4c873596a1871fc5cfbf6ee89355 |

### Software identity

| File | SHA-256, identical on R1 and R4 |
| --- | --- |
| ffmpeg.exe | 98094b9736637916bd98cc8ee7546d9d3638763545f153c6daa9dcf87b43d10e |
| usbvideo.sys (10.0.22621.608) | 33903f359e42eaaef0b1d3f365e0034312096cdd8fd82e208ba366de13830cc0 |
| ksproxy.ax (10.0.22621.1) | 598a3c648de2b983cfdb2ac599b1254d77fec868282083e03d65fdcf24847719 |

## Findings

| Comparison against each host's 720p/30 image | R4 correlation | R1 correlation |
| --- | ---: | ---: |
| Top-left 1280x720 crop of 1080p | 0.99141 | 0.12247 |
| Centered 1280x720 crop of 1080p | 0.49459 | 0.44026 |
| Full-frame downscale of 1080p | 0.33687 | 0.99830 |
| 720p/10 capture | 0.99980 | 0.99825 |

- R4's apparent zoom is consistent with top-left truncation, not ordinary centered zoom. Wider scene includes the right doorway and more floor in 1080p.
- R4 delivered yuvj420p MJPEG; R1 delivered yuvj422p. R1 emitted `EOI missing, emulating` warnings but captures completed and framing comparison remained usable; warning cause not established.
- Equal FFmpeg/UVC/DirectShow proxy binaries and equal package labels do not imply equal device capabilities. Different bus descriptions and advertised modes support investigating device identity/firmware or per-device negotiation. No claim of counterfeit hardware is justified by these observations alone.
- Stream-copy reproduction excludes FFmpeg image decoding, output encoding, and downstream Silica rendering as necessary causes of this observed crop. It does not exclude FFmpeg's DirectShow mode negotiation.
- Lower-rate MJPEG reproduced the crop; 30 fps alone is not the explanation.

## Actions and recovery timeline

| Timestamp (America/Los_Angeles) | Action actually taken | Result | Backup / rollback reference |
| --- | --- | --- | --- |
| Earlier in session; exact timestamp not recorded | Prepared and pushed room-scoped store workaround; later added standalone preview | Published module comparison and synthetic tests passed; no agent apply | Revert store commits through reviewed GitOps process; reintroduces original FOV risk |
| 2026-11-05 01:14:15-08:00 | R2 PnP inspection | Camera absent; investigation redirected to R4 | Read-only |
| 2026-11-05 01:23:33–01:23:37-08:00 | Approved R4 direct-copy captures | Both 720p rates cropped; 1080p wider | New files only; -n protected existing files; no settings changed |
| 2026-11-05 01:27:16–01:27:19-08:00 | Approved R1 comparison captures | 720p retained full-frame geometry | New files only; no settings changed |
| At documentation close; exact timestamp not separately recorded | Verified exited session tunnel and closed created idle pane | Session forward absent; unrelated tunnel preserved | No remote configuration to roll back |

## Outcome and remaining work

- Diagnostic session finished. Preserve the 1080p MJPEG/software-downscale workaround for recording and standalone preview pending normal operational validation.
- Runtime workaround presence was observed on R2 and R4. Operator reported correct FOV in both rooms; agent independently inspected brief R4 frames. Sustained production recovery was not measured.
- Underlying component root cause remains unconfirmed. A separately authorized camera/PC cross-swap is the next strong discriminator; not executed.
- Physical and local diagnostic frames remain in place as evidence; no deletion authorized or performed. Local scratch copies are subject to normal cache pruning and are not durable archival storage.
- No driver changes, firmware updates, camera-control resets, service restarts, or reboot were performed.
- Runbook is draft; no recurrence-based human verification, incident/runbook commit, or push performed.
