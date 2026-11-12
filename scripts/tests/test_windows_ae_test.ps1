# Local-only checks with fake processes/scheduler. Never starts AE or a scheduled task.
$ErrorActionPreference = 'Stop'
$scriptPath = Join-Path (Split-Path $PSScriptRoot -Parent) 'windows-ae-test.ps1'
$tokens = $null
$parseErrors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile($scriptPath, [ref]$tokens, [ref]$parseErrors)
if ($parseErrors.Count) { throw ($parseErrors | Out-String) }
. $scriptPath

function Assert($Condition, [string]$Message) { if (-not $Condition) { throw $Message } }
function Assert-Throws([scriptblock]$Body, [string]$Pattern) {
    try { & $Body } catch { Assert ($_.Exception.Message -match $Pattern) "Unexpected error: $_"; return }
    throw "Expected an error matching $Pattern"
}
function Test([string]$Name, [scriptblock]$Body) { & $Body; "PASS $Name" }

$temporary = Join-Path ([IO.Path]::GetTempPath()) ('ae-runner-tests-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    Test 'Windows job helper compiles' {
        $literal = $ast.Find({ param($node) $node -is [System.Management.Automation.Language.StringConstantExpressionAst] -and $node.Value.Contains('public static class AETestJob') }, $true)
        Add-Type -TypeDefinition $literal.Value.Replace('AETestJob', 'AETestJobCompileCheck')
    }
    # A fake native helper makes the render-finally checks safe on any OS.
    Add-Type 'public static class AETestJob { public static bool Closed; public static bool CloseHandle(System.IntPtr h) { Closed = true; return true; } }'

    Test 'argument quoting preserves spaces, quotes and trailing slashes' {
        Assert ((ConvertTo-NativeArgument 'C:\with spaces\') -ceq '"C:\with spaces\\"') 'Trailing slash quoting failed'
        Assert ((ConvertTo-NativeArgument 'say "hello"') -ceq '"say \"hello\""') 'Embedded quote escaping failed'
        $r = [pscustomobject]@{ comp = 'main comp'; mfr = 'ON'; mfr_cpu = 60; memory = @(50, 80) }
        $arguments = @(New-RenderArguments $r 'C:\input.aepx' 'C:\output.mp4')
        Assert (($arguments -join '|') -eq '-project|C:\input.aepx|-comp|main comp|-output|C:\output.mp4|-mfr|ON|60|-mem_usage|50|80') 'Render arguments differ'
    }

    Test 'AEPX discovery handles namespaces and rejects relative paths and DTDs' {
        $path = Join-Path $temporary 'project.aepx'
        '<AfterEffectsProject xmlns="urn:ae"><fileReference fullpath="C:\media\one.mp4"/><fileReference fullpath="C:\media\one.mp4"/></AfterEffectsProject>' | Set-Content -LiteralPath $path
        $request = [pscustomobject]@{ project = $path; input_path = @('C:\media\extra') }
        $paths = @(Get-InputPaths $request)
        Assert ($paths.Count -eq 2 -and 'C:\media\extra' -in $paths) 'Missing or duplicated inputs'
        '<project><fileReference fullpath="relative.mp4"/></project>' | Set-Content -LiteralPath $path
        Assert-Throws { Get-InputPaths $request } 'absolute'
        '<!DOCTYPE project [<!ENTITY secret SYSTEM "file:///no-such-file">]><project>&secret;</project>' | Set-Content -LiteralPath $path
        Assert-Throws { Get-InputPaths $request } 'DTD'
    }

    Test 'worker PID, executable, account and desktop session are checked' {
        $worker = [pscustomobject]@{ ProcessId = 123; ExecutablePath = 'C:\worker.exe'; CommandLine = 'worker'; SessionId = 4; CreationDate = [DateTime]::UtcNow }
        function Get-CimInstance { $worker }
        function Invoke-CimMethod { [pscustomobject]@{ ReturnValue = 0; Domain = 'PC'; User = 'render'; Sid = 'S-1-5-21-test' } }
        $request = [pscustomobject]@{ worker_pid = 123; worker_exe = 'C:\worker.exe' }
        $context = Get-WorkerContext $request
        Assert ($context.account -eq 'PC\render' -and $context.sessionId -eq 4) 'Wrong worker context'
        $request.worker_exe = 'C:\other.exe'
        Assert-Throws { Get-WorkerContext $request } 'mismatch'
        $request.worker_exe = 'C:\worker.exe'
        $worker.SessionId = 0
        Assert-Throws { Get-WorkerContext $request } 'session 0'
    }

    Test 'preflight does not create a directory or task' {
        function Get-Preflight { [ordered]@{ worker = @{ sessionId = 4 }; desktopPathsChecked = $false } }
        function Register-ScheduledTask { throw 'Preflight attempted task registration' }
        $before = @(Get-ChildItem -LiteralPath $temporary).Count
        $result = Invoke-AETest ([pscustomobject]@{ execute = $false }) | ConvertFrom-Json
        Assert (-not $result.desktopPathsChecked) 'Preflight falsely claimed desktop verification'
        Assert (@(Get-ChildItem -LiteralPath $temporary).Count -eq $before) 'Preflight wrote files'
    }

    Test 'zero exit is insufficient: frame counts and full decoding must pass' {
        $directory = Join-Path $temporary 'validation'
        New-Item -ItemType Directory -Path $directory | Out-Null
        'video' | Set-Content -LiteralPath (Join-Path $directory 'output.mp4')
        $state = @{ frames = '100'; decodeExit = 0; calls = 0 }
        function Invoke-LoggedProcess($Executable, $Arguments, $Stem) {
            $state.calls++
            if ($Executable -eq 'probe') {
                @{ streams = @(@{ codec_type = 'video'; nb_read_frames = $state.frames }) } | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath "$Stem.stdout.log"
                return 0
            }
            return $state.decodeExit
        }
        $request = [pscustomobject]@{ output_name = 'output.mp4'; ffprobe = 'probe'; ffmpeg = 'decode'; expected_frames = 100; working_directory = $directory }
        Assert-ValidOutput $request $directory ([DateTime]::UtcNow.AddMinutes(1)) | Out-Null
        Assert ($state.calls -eq 2) 'Full decoding was skipped'
        $state.frames = '99'
        Assert-Throws { Assert-ValidOutput $request $directory ([DateTime]::UtcNow.AddMinutes(1)) } 'frame count'
        $state.frames = 'N/A'
        Assert-Throws { Assert-ValidOutput $request $directory ([DateTime]::UtcNow.AddMinutes(1)) } 'frame count'
        $state.frames = '100'; $state.decodeExit = 1
        Assert-Throws { Assert-ValidOutput $request $directory ([DateTime]::UtcNow.AddMinutes(1)) } 'decoding failed'
    }

    Test 'process timeout is bounded' {
        function Start-Process {
            $process = [pscustomobject]@{ Id = 42; ExitCode = 0 }
            $process | Add-Member ScriptMethod WaitForExit { param($Milliseconds) return $false }
            $process
        }
        Assert-Throws { Invoke-LoggedProcess 'fake' @('argument') (Join-Path $temporary 'timeout') ([DateTime]::UtcNow.AddMinutes(1)) $temporary } 'deadline'
        $outcome = Get-Content -LiteralPath (Join-Path $temporary 'timeout.result.json') -Raw | ConvertFrom-Json
        Assert ($outcome.timedOut -and $null -eq $outcome.exitCode -and $outcome.pid -eq 42) 'Timeout was confused with a successful exit'
    }

    Test 'process exit and startup errors are retained separately from deadline failures' {
        function Start-Process {
            $process = [pscustomobject]@{ Id = 43; ExitCode = 7 }
            $process | Add-Member ScriptMethod WaitForExit { param($Milliseconds) return $true }
            $process
        }
        $stem = Join-Path $temporary 'process-exit'
        Assert ((Invoke-LoggedProcess 'fake' @() $stem ([DateTime]::UtcNow.AddMinutes(1)) $temporary) -eq 7) 'Exit code lost'
        $outcome = Get-Content -LiteralPath "$stem.result.json" -Raw | ConvertFrom-Json
        Assert ($outcome.exitCode -eq 7 -and -not $outcome.timedOut) 'Nonzero exit confused with timeout'
        function Start-Process { throw 'start denied' }
        Assert-Throws { Invoke-LoggedProcess 'fake' @() $stem ([DateTime]::UtcNow.AddMinutes(1)) $temporary } 'start denied'
        $outcome = Get-Content -LiteralPath "$stem.result.json" -Raw | ConvertFrom-Json
        Assert ($null -eq $outcome.pid -and $null -eq $outcome.exitCode -and $outcome.error -eq 'start denied' -and -not $outcome.timedOut) 'Startup error evidence lost'
    }

    foreach ($condition in @('completed', 'wrong-context', 'native-error', 'nonzero-exit', 'invalid-output', 'validation-timeout', 'timeout', 'timeout-native-error')) {
        Test "desktop render $condition preserves evidence and cleans its own job/task" {
            $directory = Join-Path $temporary $condition
            New-Item -ItemType Directory -Path $directory | Out-Null
            $project = Join-Path $directory 'source.aepx'
            '<project/>' | Set-Content -LiteralPath $project
            $dumps = Join-Path $directory 'reports'
            New-Item -ItemType Directory -Path $dumps | Out-Null
            'old' | Set-Content -LiteralPath (Join-Path $dumps 'old.dmp')
            $context = [pscustomobject]@{ created = 'worker-start'; sid = 'worker-sid'; sessionId = 4 }
            $request = [pscustomobject]@{
                project = $project; aerender = $project; ffprobe = $project; ffmpeg = $project
                working_directory = $directory; dump_directory = $dumps; output_name = 'output.mp4'
                comp = 'main'; mfr = 'ON'; mfr_cpu = 60; memory = @(50, 80); timeout_seconds = 30
                task_name = 'Silica-AE-test-owned'
            }
            Write-Json $request "$directory\request.json"
            Write-Json ([ordered]@{ worker = $context; sourceHash = (Get-FileHash $project).Hash; inputPaths = @() }) "$directory\preflight.json"
            $state = @{ launched = $false; cleanedTask = $null; openedJob = $false; validated = $false; grace = $false }
            [AETestJob]::Closed = $false
            function Get-WorkerContext { $context }
            function Get-DesktopContext {
                @{ sid = $(if ($condition -eq 'wrong-context') { 'wrong-user' } else { $context.sid }); sessionId = $context.sessionId }
            }
            function Assert-NoActiveAE {}
            function Open-RunJob { $state.openedJob = $true; [IntPtr]99 }
            function Unregister-ScheduledTask { param($TaskName, $Confirm, $ErrorAction) $state.cleanedTask = $TaskName }
            function Start-Sleep {
                param($Seconds)
                Assert ($Seconds -eq 5) 'Unexpected dump grace period'
                $state.grace = $true
                'delayed report' | Set-Content -LiteralPath (Join-Path $dumps 'delayed.dmp')
            }
            function Invoke-LoggedProcess($Executable, $Arguments, $Stem) {
                $state.launched = $true
                Write-Json @{ executable = $Executable; arguments = $Arguments } "$Stem.command.json"
                'new' | Set-Content -LiteralPath (Join-Path $dumps 'new.dmp')
                $(if ($condition -eq 'native-error') { 'aerender ERROR: native connection closed' } else { 'finished' }) | Set-Content -LiteralPath "$Stem.stdout.log"
                $(if ($condition -eq 'timeout-native-error') { 'aerender ERROR: native connection closed' } else { '' }) | Set-Content -LiteralPath "$Stem.stderr.log"
                if ($condition -in @('timeout', 'timeout-native-error')) { throw [TimeoutException]::new('Diagnostic deadline exceeded.') }
                if ($condition -eq 'nonzero-exit') { return 7 }
                return 0
            }
            function Assert-ValidOutput {
                $state.validated = $true
                if ($condition -eq 'invalid-output') { throw 'Output is missing or empty.' }
                if ($condition -eq 'validation-timeout') { throw [TimeoutException]::new('Diagnostic deadline exceeded.') }
                @{ streams = @(@{ nb_read_frames = '100' }) }
            }
            Invoke-DesktopRender $directory
            $result = Get-Content -LiteralPath "$directory\result.json" -Raw | ConvertFrom-Json
            Assert ($result.sourceUnchanged) 'Original project changed'
            Assert ($state.cleanedTask -eq 'Silica-AE-test-owned') 'Wrong task cleanup'
            if ($condition -eq 'wrong-context') {
                Assert (-not $state.launched -and -not $state.openedJob) 'Started AE in the wrong desktop'
                Assert ($result.status -eq 'failed') 'Wrong-context failure was hidden'
            } else {
                Assert ($state.launched -and [AETestJob]::Closed) 'Owned job was not closed'
                Assert ($state.grace -and @($result.copiedDumps).Count -eq 2) 'Old dump included or new/delayed dump lost'
                Assert ($result.dumpCollection.status -eq 'collected') 'Dump collection outcome missing'
                Assert ($result.status -eq $(if ($condition -eq 'completed') { 'completed' } else { 'failed' })) 'Wrong outcome'
                Assert (Test-Path -LiteralPath "$directory\render.command.json") 'Exact command was not retained'
                Assert ($state.validated -eq ($condition -notin @('timeout', 'timeout-native-error'))) 'Output validation incorrectly skipped or attempted after render timeout'
                Assert ($result.deadline.exceeded -eq ($condition -in @('timeout', 'timeout-native-error', 'validation-timeout'))) 'Deadline outcome incorrect'
                if ($condition -in @('timeout', 'timeout-native-error')) {
                    Assert ($result.render.timedOut -and $null -eq $result.exitCode -and $result.deadline.phase -eq 'render') 'Render timeout evidence lost'
                    if ($condition -eq 'timeout-native-error') { Assert ($result.render.nativeErrors.Count -eq 1) 'Timeout hid native error in stderr' }
                } elseif ($condition -eq 'validation-timeout') {
                    Assert ($result.render.status -eq 'completed' -and $result.validation.timedOut -and $result.deadline.phase -eq 'validation') 'Validation timeout misclassified'
                } elseif ($condition -eq 'native-error') {
                    Assert ($result.exitCode -eq 0 -and $result.render.nativeErrors.Count -eq 1 -and $result.validation.status -eq 'passed') 'Zero-exit native error hidden'
                } elseif ($condition -eq 'nonzero-exit') {
                    Assert ($result.exitCode -eq 7 -and $result.validation.status -eq 'passed') 'Failed render output was not validated'
                } elseif ($condition -eq 'invalid-output') {
                    Assert ($result.render.status -eq 'completed' -and $result.validation.error -match 'empty') 'Output failure misclassified'
                }
            }
        }
    }

    Test 'dump collection retains changed reports and continues after a copy failure' {
        $directory = Join-Path $temporary 'dump-errors'
        $reports = Join-Path $directory 'reports'
        New-Item -ItemType Directory -Path $reports -Force | Out-Null
        $changed = Join-Path $reports 'changed.dmp'
        'old' | Set-Content -LiteralPath $changed
        $unchanged = Join-Path $reports 'unchanged.dmp'
        'old' | Set-Content -LiteralPath $unchanged
        $seen = @{}
        foreach ($dump in Get-ChildItem -LiteralPath $reports) { $seen[$dump.FullName] = "$($dump.Length):$($dump.LastWriteTimeUtc.Ticks)" }
        function Start-Sleep {
            param($Seconds)
            'updated dump content' | Set-Content -LiteralPath $changed
            'locked report' | Set-Content -LiteralPath (Join-Path $reports 'broken.dmp')
        }
        function Copy-Item {
            param($LiteralPath, $Destination, $ErrorAction)
            if ($LiteralPath.EndsWith('broken.dmp')) { throw 'report locked' }
            Microsoft.PowerShell.Management\Copy-Item -LiteralPath $LiteralPath -Destination $Destination -ErrorAction Stop
        }
        $result = @{ copiedDumps = @(); dumpCollection = @{ status = 'not_started'; errors = @() } }
        Copy-NativeDumps ([pscustomobject]@{ dump_directory = $reports }) $directory $seen $result
        Assert ($result.dumpCollection.status -eq 'partial' -and $result.dumpCollection.errors.Count -eq 1) 'Copy error hidden'
        Assert ($result.copiedDumps.Count -eq 1 -and $result.copiedDumps[0].source -eq $changed) 'Changed dump lost or old dump copied'
        Assert ((Get-Content -LiteralPath $result.copiedDumps[0].retained -Raw) -match 'updated dump') 'Retained dump is stale'
    }

    Test 'controller targets the worker session and removes only its generated task' {
        $outputRoot = Join-Path $temporary 'controller'
        New-Item -ItemType Directory -Path $outputRoot | Out-Null
        $state = @{ registered = $null; removed = $null; session = $null }
        $context = @{ account = 'PC\render'; sessionId = 7; created = 'original-worker'; sid = 'worker-sid' }
        function Get-Preflight { @{ worker = $context } }
        function Get-WorkerContext { $context }
        function Get-AEProcesses { @() }
        function New-ScheduledTaskAction { param($Execute, $Argument, $WorkingDirectory) @{ argument = $Argument } }
        function New-ScheduledTaskPrincipal { param($UserId, $LogonType, $RunLevel) Assert ($LogonType -eq 'Interactive') 'Wrong logon type'; @{ account = $UserId } }
        function New-ScheduledTaskSettingsSet { param($ExecutionTimeLimit, [switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries) @{} }
        function Register-ScheduledTask { param($TaskName, $Action, $Principal, $Settings) $state.registered = $TaskName }
        function Start-DesktopTask($TaskName, $SessionId) {
            $state.session = $SessionId
            $directory = @(Get-ChildItem -LiteralPath $outputRoot -Directory)[0].FullName
            Write-Json @{ status = 'completed'; runnerPid = 999; runnerCreated = 'finished' } "$directory\result.json"
        }
        function Start-Sleep {}
        function Get-Process { $null }
        function Get-ScheduledTask { [pscustomobject]@{ State = 'Ready' } }
        function Stop-ScheduledTask { param($TaskName) Assert ($TaskName -eq $state.registered) 'Stopped another task' }
        function Unregister-ScheduledTask { param($TaskName, $Confirm) $state.removed = $TaskName }
        $request = [pscustomobject]@{ execute = $true; output_root = $outputRoot; working_directory = $outputRoot; timeout_seconds = 30; runner_source = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('# fake runner')) }
        Invoke-AETest $request | Out-Null
        Assert ($state.session -eq 7) 'Wrong target session'
        Assert ($state.registered -match '^Silica-AE-[a-f0-9]{32}$' -and $state.registered -eq $state.removed) 'Task cleanup escaped ownership'
        $directory = @(Get-ChildItem -LiteralPath $outputRoot -Directory)[0].FullName
        Assert (Test-Path -LiteralPath "$directory\runner.ps1") 'Runner source not retained'
        function Start-DesktopTask { throw 'start denied' }
        $request = [pscustomobject]@{ execute = $true; output_root = $outputRoot; working_directory = $outputRoot; timeout_seconds = 30; runner_source = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes('# fake runner')) }
        Assert-Throws { Invoke-AETest $request } 'start denied'
        Assert ($state.registered -eq $state.removed) 'Start failure leaked its registered task'
        $failedDirectory = Join-Path $outputRoot ('ae-test-' + $state.registered.Substring('Silica-AE-'.Length))
        Assert (Test-Path -LiteralPath "$failedDirectory\controller-error.log") 'Start failure lost its evidence'
    }
} finally {
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
'All local AE runner checks passed.'
