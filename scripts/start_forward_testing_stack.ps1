param(
    [string]$EnvFile = ".env.n8n.local",
    [string]$PythonPath = ".venv-langgraph\Scripts\python.exe",
    [string]$Mt5PreflightSymbols = "SOL/USDT",
    [switch]$SkipMt5Preflight,
    [switch]$SkipPollOnce,
    [switch]$SkipWatchdog
)

$ErrorActionPreference = "Stop"

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }

    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $name = $parts[0].Trim()
        $value = $parts[1].Trim()
        if (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'"))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        [Environment]::SetEnvironmentVariable($name, $value, "Process")
    }
}

function Test-RunningProcessFromPidFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidFile
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $false
    }

    try {
        $targetProcessId = [int]((Get-Content -LiteralPath $PidFile -Raw).Trim())
        return $null -ne (Get-Process -Id $targetProcessId -ErrorAction SilentlyContinue)
    }
    catch {
        return $false
    }
}

function Enter-StartupLock {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    $lockDirectory = Split-Path -Path $Path -Parent
    if (-not (Test-Path -LiteralPath $lockDirectory)) {
        New-Item -ItemType Directory -Path $lockDirectory -Force | Out-Null
    }

    try {
        $fileStream = [System.IO.File]::Open($Path, [System.IO.FileMode]::OpenOrCreate, [System.IO.FileAccess]::ReadWrite, [System.IO.FileShare]::None)
        $fileStream.SetLength(0)
        $writer = New-Object System.IO.StreamWriter($fileStream)
        $writer.AutoFlush = $true
        $writer.WriteLine(("pid={0}" -f $PID))
        $writer.WriteLine(("started_at_utc={0}" -f (Get-Date).ToUniversalTime().ToString("o")))
        return [pscustomobject]@{
            Stream = $fileStream
            Writer = $writer
            Path = $Path
        }
    }
    catch {
        return $null
    }
}

function Exit-StartupLock {
    param(
        [Parameter(Mandatory = $true)]
        [object]$LockHandle
    )

    if ($null -eq $LockHandle) {
        return
    }

    try {
        if ($LockHandle.Writer) {
            $LockHandle.Writer.Dispose()
        }
    }
    catch {
    }

    try {
        if ($LockHandle.Stream) {
            $LockHandle.Stream.Dispose()
        }
    }
    catch {
    }

    Remove-Item -LiteralPath $LockHandle.Path -Force -ErrorAction SilentlyContinue
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null
$startupLockPath = Join-Path $resultsDir "forward_testing_start.lock"
$startupLock = Enter-StartupLock -Path $startupLockPath

if ($null -eq $startupLock) {
    Write-Output "FORWARD_TESTING_START_SKIPPED=lock_held"
    Write-Output ("LOCK=" + $startupLockPath)
    exit 0
}

$envPath = Join-Path $repoRoot $EnvFile
$python = Join-Path $repoRoot $PythonPath
$daemonStartScript = Join-Path $repoRoot "scripts\start_trade_oracle_daemon.ps1"
$daemonPidPath = Join-Path $resultsDir "trade_oracle_daemon.pid"
$watchdogScript = Join-Path $repoRoot "scripts\run_local_server_watchdog.ps1"
$watchdogPidPath = Join-Path $resultsDir "trade_oracle_watchdog.pid"
$statusPath = Join-Path $resultsDir "forward_testing_stack_status.json"
$mt5PreflightOutputPath = Join-Path $resultsDir "forward_testing_mt5_preflight.json"
$watchdogLogPath = Join-Path $resultsDir "local_server_watchdog.log"
$daemonLogPath = Join-Path $resultsDir "trade_oracle_daemon.log"
$daemonErrPath = Join-Path $resultsDir "trade_oracle_daemon.err.log"

Import-DotEnvFile -Path $envPath

try {
    if (-not (Test-Path -LiteralPath $python)) {
        throw "Python interpreter not found: $python"
    }

    $daemonAlreadyRunning = Test-RunningProcessFromPidFile -PidFile $daemonPidPath
    $watchdogAlreadyRunning = Test-RunningProcessFromPidFile -PidFile $watchdogPidPath
    if ($daemonAlreadyRunning -and ($SkipWatchdog -or $watchdogAlreadyRunning)) {
        Write-Output "FORWARD_TESTING_ALREADY_RUNNING=True"
        if (Test-Path -LiteralPath $statusPath) {
            Write-Output ("STATUS=" + $statusPath)
        }
        Write-Output ("DAEMON_LOG=" + $daemonLogPath)
        if ($watchdogAlreadyRunning) {
            Write-Output ("WATCHDOG_PID=" + (Get-Content -LiteralPath $watchdogPidPath -Raw).Trim())
        }
        return
    }

    $mt5TerminalPath = [Environment]::GetEnvironmentVariable("MT5_TERMINAL_PATH", "Process")
    if (-not [string]::IsNullOrWhiteSpace($mt5TerminalPath) -and (Test-Path -LiteralPath $mt5TerminalPath)) {
        $terminalProcesses = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
        if ($null -eq $terminalProcesses -or $terminalProcesses.Count -eq 0) {
            Start-Process -FilePath $mt5TerminalPath -WorkingDirectory (Split-Path -Path $mt5TerminalPath -Parent) | Out-Null
            Start-Sleep -Seconds 5
        }
    }

    $readinessJson = & $python "scripts\check_forward_test_readiness.py" "--env-file" $EnvFile "--check-supabase"
    if ($LASTEXITCODE -ne 0) {
        throw "Forward-test readiness check failed."
    }
    $readiness = $readinessJson | ConvertFrom-Json
    if (-not $readiness.ready_for_forward_testing_start) {
        $blockers = @($readiness.blockers)
        $blockerText = if ($blockers.Count -gt 0) { $blockers -join ", " } else { "unknown_blocker" }
        throw ("Readiness check did not pass for forward-testing start. Blockers: " + $blockerText)
    }

    if (-not $SkipMt5Preflight) {
        & $python "scripts\validate_mt5_demo_profile.py" "--env-file" $EnvFile "--symbols" $Mt5PreflightSymbols "--output" $mt5PreflightOutputPath
        if ($LASTEXITCODE -ne 0) {
            throw "MT5 preflight failed."
        }
    }

    if (-not $SkipPollOnce) {
        & $python "scripts\run_trade_oracle_daemon.py" "--poll-once"
        if ($LASTEXITCODE -ne 0) {
            throw "Daemon poll-once check failed."
        }
    }

    $daemonOutput = & $daemonStartScript -EnvFile $EnvFile
    if ($LASTEXITCODE -ne 0) {
        throw "Failed to start TRADE_ORACLE daemon."
    }

    $watchdogPid = ""
    if (-not $SkipWatchdog) {
        if (-not (Test-RunningProcessFromPidFile -PidFile $watchdogPidPath)) {
            $watchdogArgs = @(
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                $watchdogScript,
                "-EnvFile",
                $EnvFile,
                "-RuntimeMode",
                "daemon"
            )
            $watchdogProcess = Start-Process -FilePath "powershell.exe" -ArgumentList $watchdogArgs -WorkingDirectory $repoRoot -PassThru -WindowStyle Hidden
            Set-Content -LiteralPath $watchdogPidPath -Value $watchdogProcess.Id
            $watchdogPid = [string]$watchdogProcess.Id
        }
        elseif (Test-Path -LiteralPath $watchdogPidPath) {
            $watchdogPid = (Get-Content -LiteralPath $watchdogPidPath -Raw).Trim()
        }
    }

    $status = [ordered]@{
        started_at_utc = (Get-Date).ToUniversalTime().ToString("o")
        env_file = $EnvFile
        mt5_terminal_path = $mt5TerminalPath
        readiness = $readiness
        mt5_preflight_output = $mt5PreflightOutputPath
        daemon_start_output = $daemonOutput
        daemon_log = $daemonLogPath
        daemon_err_log = $daemonErrPath
        watchdog_pid = $watchdogPid
        watchdog_log = $watchdogLogPath
        forward_testing_started = $true
    }
    $status | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statusPath

    Write-Output "FORWARD_TESTING_STARTED=True"
    Write-Output "STATUS=$statusPath"
    Write-Output ("DAEMON_LOG=" + $daemonLogPath)
    foreach ($line in $daemonOutput) {
        Write-Output $line
    }
    if ($watchdogPid) {
        Write-Output ("WATCHDOG_PID=" + $watchdogPid)
    }
}
finally {
    Exit-StartupLock -LockHandle $startupLock
}
