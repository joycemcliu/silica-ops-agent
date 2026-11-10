# Windows PowerShell 5.1+. Not executed end-to-end against Windows/AE during implementation.
param([string]$RequestBase64, [string]$RunDirectory)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Write-Json($Value, [string]$Path) {
    $temporary = "$Path.tmp"
    $Value | ConvertTo-Json -Depth 12 | Set-Content -LiteralPath $temporary -Encoding UTF8
    Move-Item -LiteralPath $temporary -Destination $Path -Force
}

function Get-WorkerContext($Request) {
    $worker = Get-CimInstance Win32_Process -Filter "ProcessId=$($Request.worker_pid)"
    if (-not $worker -or $worker.ExecutablePath -ine $Request.worker_exe) { throw 'Worker PID/executable mismatch or inaccessible worker.' }
    if ($worker.SessionId -le 0) { throw 'Worker has no interactive desktop session; session 0 reproduction is unsupported.' }
    $owner = Invoke-CimMethod -InputObject $worker -MethodName GetOwner
    $sid = Invoke-CimMethod -InputObject $worker -MethodName GetOwnerSid
    if ($owner.ReturnValue -ne 0 -or $sid.ReturnValue -ne 0) { throw 'Cannot establish the worker account.' }
    [ordered]@{
        pid = $worker.ProcessId; executable = $worker.ExecutablePath; commandLine = $worker.CommandLine
        sessionId = $worker.SessionId; account = "$($owner.Domain)\$($owner.User)"; sid = $sid.Sid
        created = $worker.CreationDate.ToUniversalTime().ToString('o')
    }
}

function Get-AEProcesses {
    Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^(aerender[.]exe|AfterFX[.]com|AfterFX[.]exe)$' } |
        Select-Object ProcessId, Name, SessionId, ExecutablePath, CommandLine
}

function Assert-NoActiveAE {
    if (Get-AEProcesses) {
        throw 'Another AE process is active; wait for an idle diagnostic window.'
    }
}

function Get-InputPaths($Request) {
    $settings = New-Object System.Xml.XmlReaderSettings
    $settings.DtdProcessing = [System.Xml.DtdProcessing]::Prohibit
    $settings.XmlResolver = $null
    $reader = [System.Xml.XmlReader]::Create($Request.project, $settings)
    try {
        $xml = New-Object System.Xml.XmlDocument
        $xml.XmlResolver = $null
        $xml.Load($reader)
    } finally { $reader.Dispose() }
    $paths = @($Request.input_path)
    foreach ($reference in $xml.SelectNodes("//*[local-name()='fileReference']")) {
        $path = $reference.GetAttribute('fullpath')
        if ($path -notmatch '^(?:[A-Za-z]:\\|\\\\[^\\]+\\[^\\]+)') {
            throw 'Every AEPX fileReference must have an absolute fullpath before copying the project.'
        }
        $paths += $path
    }
    @($paths | Sort-Object -Unique)
}

function Get-Preflight($Request) {
    $worker = Get-WorkerContext $Request
    Assert-NoActiveAE
    foreach ($file in @($Request.aerender, $Request.project, $Request.ffprobe, $Request.ffmpeg)) {
        if (-not (Test-Path -LiteralPath $file -PathType Leaf)) { throw "Required file is unavailable in this context: $file" }
    }
    foreach ($directory in @($Request.output_root, $Request.working_directory)) {
        if (-not (Test-Path -LiteralPath $directory -PathType Container)) { throw "Required directory is unavailable: $directory" }
    }
    [ordered]@{
        hostname = [Environment]::MachineName; worker = $worker
        aerenderVersion = (Get-Item -LiteralPath $Request.aerender).VersionInfo.FileVersion
        sourceHash = (Get-FileHash -LiteralPath $Request.project -Algorithm SHA256).Hash
        inputPaths = @(Get-InputPaths $Request)
        desktopPathsChecked = $false
    }
}

function ConvertTo-NativeArgument([string]$Value) {
    # Start-Process joins its argument list; apply Windows CRT quoting to each value.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    '"' + $escaped + '"'
}

function New-RenderArguments($Request, [string]$Project, [string]$Output) {
    @('-project', $Project, '-comp', $Request.comp, '-output', $Output,
      '-mfr', $Request.mfr, [string]$Request.mfr_cpu,
      '-mem_usage', [string]$Request.memory[0], [string]$Request.memory[1])
}

function Get-DesktopContext {
    [ordered]@{
        sid = [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
        sessionId = (Get-Process -Id $PID).SessionId
    }
}

function Open-RunJob {
    # The scheduled PowerShell process joins first, so all subsequently spawned children
    # inherit the job. Closing its sole handle also ends this PowerShell process.
    if (-not ('AETestJob' -as [type])) {
        Add-Type -TypeDefinition @'
using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.InteropServices;
public static class AETestJob {
    [StructLayout(LayoutKind.Sequential)] struct Basic {
        public long ProcessTime, JobTime;
        public uint Flags;
        public UIntPtr MinWorkingSet, MaxWorkingSet;
        public uint ActiveProcesses;
        public UIntPtr Affinity;
        public uint Priority, Scheduling;
    }
    [StructLayout(LayoutKind.Sequential)] struct IO {
        public ulong ReadOps, WriteOps, OtherOps, ReadBytes, WriteBytes, OtherBytes;
    }
    [StructLayout(LayoutKind.Sequential)] struct Limits {
        public Basic Basic; public IO IO;
        public UIntPtr ProcessMemory, JobMemory, PeakProcessMemory, PeakJobMemory;
    }
    [DllImport("kernel32.dll", CharSet=CharSet.Unicode, SetLastError=true)]
    static extern IntPtr CreateJobObject(IntPtr attributes, string name);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool SetInformationJobObject(IntPtr job, int kind, ref Limits limits, uint size);
    [DllImport("kernel32.dll", SetLastError=true)]
    static extern bool AssignProcessToJobObject(IntPtr job, IntPtr process);
    [DllImport("kernel32.dll", SetLastError=true)]
    public static extern bool CloseHandle(IntPtr handle);
    public static IntPtr Open() {
        IntPtr job = CreateJobObject(IntPtr.Zero, null);
        if (job == IntPtr.Zero) throw new Win32Exception();
        var limits = new Limits();
        limits.Basic.Flags = 0x2000; // JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if (!SetInformationJobObject(job, 9, ref limits, (uint)Marshal.SizeOf(typeof(Limits))) ||
            !AssignProcessToJobObject(job, Process.GetCurrentProcess().Handle)) {
            int error = Marshal.GetLastWin32Error();
            CloseHandle(job);
            throw new Win32Exception(error);
        }
        return job;
    }
}
'@
    }
    [AETestJob]::Open()
}

function Invoke-LoggedProcess([string]$Executable, [string[]]$Arguments, [string]$Stem, [datetime]$Deadline, [string]$WorkingDirectory) {
    $milliseconds = [Math]::Min([int]::MaxValue, [Math]::Max(0, ($Deadline - [DateTime]::UtcNow).TotalMilliseconds))
    if ($milliseconds -le 0) { throw 'Diagnostic deadline exceeded.' }
    Write-Json ([ordered]@{ executable = $Executable; arguments = $Arguments; workingDirectory = $WorkingDirectory; deadlineUtc = $Deadline.ToString('o') }) "$Stem.command.json"
    $quoted = @($Arguments | ForEach-Object { ConvertTo-NativeArgument $_ })
    $process = Start-Process -FilePath $Executable -ArgumentList ($quoted -join ' ') -WorkingDirectory $WorkingDirectory -PassThru -NoNewWindow `
        -RedirectStandardOutput "$Stem.stdout.log" -RedirectStandardError "$Stem.stderr.log"
    if (-not $process.WaitForExit([int]$milliseconds)) { throw 'Diagnostic deadline exceeded.' }
    $process.ExitCode
}

function Assert-ValidOutput($Request, [string]$Directory, [datetime]$Deadline) {
    $output = Join-Path $Directory $Request.output_name
    if (-not (Test-Path -LiteralPath $output -PathType Leaf) -or (Get-Item -LiteralPath $output).Length -eq 0) { throw 'Output is missing or empty.' }
    $probeArgs = @('-v', 'error', '-count_frames', '-show_entries', 'stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames:format=duration,size', '-of', 'json', $output)
    if ((Invoke-LoggedProcess $Request.ffprobe $probeArgs "$Directory\probe" $Deadline $Request.working_directory) -ne 0) { throw 'ffprobe rejected the output.' }
    $probe = Get-Content -LiteralPath "$Directory\probe.stdout.log" -Raw | ConvertFrom-Json
    $video = @($probe.streams | Where-Object codec_type -eq video)
    if ($video.Count -ne 1 -or $video[0].nb_read_frames -notmatch '^\d+$' -or [long]$video[0].nb_read_frames -ne $Request.expected_frames) { throw 'Output has an unexpected video frame count.' }
    $decodeArgs = @('-hide_banner', '-nostdin', '-v', 'error', '-xerror', '-i', $output, '-map', '0:v?', '-map', '0:a?', '-f', 'null', 'NUL')
    if ((Invoke-LoggedProcess $Request.ffmpeg $decodeArgs "$Directory\decode" $Deadline $Request.working_directory) -ne 0) { throw 'Full output decoding failed.' }
    $probe
}

function Invoke-DesktopRender([string]$Directory) {
    $request = Get-Content -LiteralPath "$Directory\request.json" -Raw | ConvertFrom-Json
    $preflight = Get-Content -LiteralPath "$Directory\preflight.json" -Raw | ConvertFrom-Json
    $job = [IntPtr]::Zero
    $started = [DateTime]::UtcNow
    $self = Get-Process -Id $PID
    $result = [ordered]@{
        status = 'failed'; started = $started.ToString('o'); runDirectory = $Directory
        runnerPid = $PID; runnerCreated = $self.StartTime.ToUniversalTime().ToString('o')
        error = $null; copiedDumps = @()
    }
    $seenDumps = @{}
    $dumpSnapshotTaken = $false
    try {
        $context = Get-WorkerContext $request
        $desktop = Get-DesktopContext
        if ($context.created -ne $preflight.worker.created -or $context.sid -ne $preflight.worker.sid -or
            $context.sessionId -ne $preflight.worker.sessionId -or $desktop.sid -ne $context.sid -or
            $desktop.sessionId -ne $context.sessionId) { throw 'Worker identity/session changed or task context does not match.' }
        $result.context = $context
        $result.localAppData = $env:LOCALAPPDATA
        Assert-NoActiveAE
        $job = Open-RunJob
        foreach ($path in @($request.aerender, $request.project, $request.ffprobe, $request.ffmpeg) + @($preflight.inputPaths)) {
            if (-not (Test-Path -LiteralPath $path)) { throw "Path unavailable in the worker desktop context: $path" }
            if (Test-Path -LiteralPath $path -PathType Leaf) {
                $stream = [IO.File]::Open($path, 'Open', 'Read', 'ReadWrite')
                $stream.Dispose()
            } else { Get-ChildItem -LiteralPath $path -ErrorAction Stop | Select-Object -First 1 | Out-Null }
        }
        if (-not (Test-Path -LiteralPath $request.working_directory -PathType Container)) { throw 'Working directory unavailable in desktop context.' }
        $result.desktopPathsChecked = $true
        $project = Join-Path $Directory 'input.aepx'
        Copy-Item -LiteralPath $request.project -Destination $project
        if ((Get-FileHash -LiteralPath $project -Algorithm SHA256).Hash -ne $preflight.sourceHash) { throw 'Source project changed after preflight.' }
        if ($request.dump_directory) {
            if (-not (Test-Path -LiteralPath $request.dump_directory -PathType Container)) { throw 'Configured dump directory is unavailable in desktop context.' }
            foreach ($dump in Get-ChildItem -LiteralPath $request.dump_directory -Filter '*.dmp' -File) { $seenDumps[$dump.FullName] = "$($dump.Length):$($dump.LastWriteTimeUtc.Ticks)" }
            $dumpSnapshotTaken = $true
        }
        $arguments = @(New-RenderArguments $request $project (Join-Path $Directory $request.output_name))
        $deadline = $started.AddSeconds($request.timeout_seconds)
        $result.exitCode = Invoke-LoggedProcess $request.aerender $arguments "$Directory\render" $deadline $request.working_directory
        $nativeErrors = @(Get-Content -LiteralPath "$Directory\render.stdout.log", "$Directory\render.stderr.log" | Select-String 'aerender ERROR|An existing connection was forcibly closed')
        if ($result.exitCode -ne 0 -or $nativeErrors.Count -gt 0) { throw 'aerender reported a native error; inspect render logs.' }
        $result.video = Assert-ValidOutput $request $Directory $deadline
        $result.status = 'completed'
    } catch {
        $result.error = $_.Exception.Message
    } finally {
        if ($dumpSnapshotTaken -and (Test-Path -LiteralPath $request.dump_directory -PathType Container)) {
            try {
                $index = 0
                foreach ($dump in Get-ChildItem -LiteralPath $request.dump_directory -Filter '*.dmp' -File) {
                    if (-not $seenDumps.ContainsKey($dump.FullName) -or $seenDumps[$dump.FullName] -ne "$($dump.Length):$($dump.LastWriteTimeUtc.Ticks)") {
                        $destination = Join-Path $Directory "native-$index.dmp"
                        Copy-Item -LiteralPath $dump.FullName -Destination $destination
                        $result.copiedDumps += [ordered]@{ source = $dump.FullName; retained = $destination; attribution = 'time-correlated; process ownership not proven' }
                        $index++
                    }
                }
            } catch { $result.dumpCollectionError = $_.Exception.Message }
        }
        try {
            $result.sourceUnchanged = (Get-FileHash -LiteralPath $request.project -Algorithm SHA256).Hash -eq $preflight.sourceHash
            if (-not $result.sourceUnchanged) { $result.status = 'failed'; $result.error = 'Source project changed during the run.' }
        } catch { $result.status = 'failed'; $result.error = 'Cannot verify source project integrity.' }
        $result.ended = [DateTime]::UtcNow.ToString('o')
        # Write all evidence before closing the job, which also ends this task process.
        try { Write-Json $result "$Directory\result.json" } finally {
            try { Unregister-ScheduledTask -TaskName $request.task_name -Confirm:$false -ErrorAction Stop } catch {
                $_.Exception.Message | Set-Content -LiteralPath "$Directory\task-cleanup-error.log"
            }
            if ($job -ne [IntPtr]::Zero) { [AETestJob]::CloseHandle($job) | Out-Null }
        }
    }
}

function Start-DesktopTask([string]$TaskName, [int]$SessionId) {
    $scheduler = New-Object -ComObject Schedule.Service
    $scheduler.Connect()
    $task = $scheduler.GetFolder('\').GetTask($TaskName)
    # TASK_RUN_USE_SESSION_ID targets the worker's session rather than any login.
    $task.RunEx($null, 4, $SessionId, $null) | Out-Null
}

function Invoke-AETest($Request) {
    $preflight = Get-Preflight $Request
    if (-not $Request.execute) { $preflight | ConvertTo-Json -Depth 12; return }
    $id = [Guid]::NewGuid().ToString('N')
    $directory = Join-Path $Request.output_root "ae-test-$id"
    if (Test-Path -LiteralPath $directory) { throw 'Run directory already exists.' }
    New-Item -ItemType Directory -Path $directory | Out-Null
    $Request | Add-Member -NotePropertyName task_name -NotePropertyValue "Silica-AE-$id"
    $source = [Convert]::FromBase64String($Request.runner_source)
    $Request.PSObject.Properties.Remove('runner_source')
    [IO.File]::WriteAllBytes((Join-Path $directory 'runner.ps1'), $source)
    Write-Json $Request "$directory\request.json"
    Write-Json $preflight "$directory\preflight.json"
    $registered = $false
    try {
        $action = New-ScheduledTaskAction -Execute "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe" `
            -Argument ('-NoLogo -NoProfile -NonInteractive -File ' + (ConvertTo-NativeArgument "$directory\runner.ps1") + ' -RunDirectory ' + (ConvertTo-NativeArgument $directory)) `
            -WorkingDirectory $Request.working_directory
        $principal = New-ScheduledTaskPrincipal -UserId $preflight.worker.account -LogonType Interactive -RunLevel Limited
        $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Seconds ($Request.timeout_seconds + 120)) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
        Register-ScheduledTask -TaskName $Request.task_name -Action $action -Principal $principal -Settings $settings | Out-Null
        $registered = $true
        Start-DesktopTask $Request.task_name ([int]$preflight.worker.sessionId)
        [ordered]@{ status = 'started'; taskName = $Request.task_name; runDirectory = $directory } | ConvertTo-Json -Compress
        $waitStarted = [DateTime]::UtcNow
        $deadline = $waitStarted.AddSeconds($Request.timeout_seconds + 150)
        while ($true) {
            Start-Sleep -Seconds 2
            if ([DateTime]::UtcNow -gt $deadline) { throw "Task exceeded its deadline; inspect $directory" }
            if (Test-Path -LiteralPath "$directory\result.json") {
                $result = Get-Content -LiteralPath "$directory\result.json" -Raw | ConvertFrom-Json
                $runner = Get-Process -Id $result.runnerPid -ErrorAction SilentlyContinue
                if (-not $runner -or $runner.StartTime.ToUniversalTime().ToString('o') -ne $result.runnerCreated) { break }
            } elseif (([DateTime]::UtcNow - $waitStarted).TotalSeconds -gt 30) {
                $scheduled = Get-ScheduledTask -TaskName $Request.task_name -ErrorAction SilentlyContinue
                if (-not $scheduled -or $scheduled.State -notin @('Running', 'Queued')) { throw "Task ended without a result; inspect $directory" }
            }
        }
        $afterWorker = Get-WorkerContext $Request
        $workerUnchanged = $afterWorker.created -eq $preflight.worker.created -and $afterWorker.sid -eq $preflight.worker.sid -and $afterWorker.sessionId -eq $preflight.worker.sessionId
        $remainingAE = @(Get-AEProcesses)
        Write-Json ([ordered]@{ workerUnchanged = $workerUnchanged; remainingAE = $remainingAE }) "$directory\postflight.json"
        if (-not $workerUnchanged -or $remainingAE.Count) { throw "Worker changed or AE processes remain; inspect $directory before another trial." }
        $result | ConvertTo-Json -Depth 12
        if ($result.status -ne 'completed') { throw "AE diagnostic failed; inspect $directory" }
    } catch {
        $_.Exception.Message | Set-Content -LiteralPath "$directory\controller-error.log"
        throw
    } finally {
        if ($registered) {
            if (Get-ScheduledTask -TaskName $Request.task_name -ErrorAction SilentlyContinue) {
                Stop-ScheduledTask -TaskName $Request.task_name
                Unregister-ScheduledTask -TaskName $Request.task_name -Confirm:$false
            }
        }
    }
}

if ($RunDirectory) { Invoke-DesktopRender $RunDirectory }
elseif ($RequestBase64) { Invoke-AETest ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($RequestBase64)) | ConvertFrom-Json) }
