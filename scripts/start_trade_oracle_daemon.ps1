[CmdletBinding()]
param(
    [string]$EnvFile = ".env.n8n.local",
    [string]$PythonPath = ".venv-langgraph\Scripts\python.exe",
    [string]$ScriptPath = "scripts\run_trade_oracle_daemon.py",
    [switch]$Once,
    [switch]$PollOnce
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

function Import-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return
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

function Test-RunningProcessId {
    param(
        [int]$ProcessId
    )

    if ($ProcessId -le 0) {
        return $false
    }

    return $null -ne (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue)
}

function Get-RuntimeLockProcessId {
    param(
        [Parameter(Mandatory = $true)]
        [string]$LockFile
    )

    if (-not (Test-Path -LiteralPath $LockFile)) {
        return 0
    }

    try {
        $payload = Get-Content -LiteralPath $LockFile -Raw | ConvertFrom-Json
        return [int]($payload.pid | ForEach-Object { $_ })
    }
    catch {
        return 0
    }
}

$outPath = Join-Path $resultsDir "trade_oracle_daemon.log"
$errPath = Join-Path $resultsDir "trade_oracle_daemon.err.log"
$pidPath = Join-Path $resultsDir "trade_oracle_daemon.pid"
$runtimeLockPath = Join-Path $resultsDir "trade_oracle_daemon_runtime.lock"

$python = Join-Path $repoRoot $PythonPath
$script = Join-Path $repoRoot $ScriptPath
$envPath = Join-Path $repoRoot $EnvFile

Import-DotEnvFile -Path $envPath

if (-not (Test-Path -LiteralPath $python)) {
    throw "Python interpreter not found: $python"
}

if (-not (Test-Path -LiteralPath $script)) {
    throw "Daemon script not found: $script"
}

if (Test-Path -LiteralPath $pidPath) {
    try {
        $existingPid = [int]((Get-Content -LiteralPath $pidPath -Raw).Trim())
        $existingProcess = Get-Process -Id $existingPid -ErrorAction SilentlyContinue
        if ($null -ne $existingProcess) {
            Write-Output "TRADE_ORACLE daemon is already running with PID $existingPid"
            Write-Output "LOG=$outPath"
            Write-Output "ERR=$errPath"
            exit 0
        }
    }
    catch {
    }
}

$runtimeLockPid = Get-RuntimeLockProcessId -LockFile $runtimeLockPath
if (Test-RunningProcessId -ProcessId $runtimeLockPid) {
    Set-Content -LiteralPath $pidPath -Value $runtimeLockPid
    Write-Output "TRADE_ORACLE daemon is already running with PID $runtimeLockPid"
    Write-Output "LOG=$outPath"
    Write-Output "ERR=$errPath"
    exit 0
}

if (Test-Path -LiteralPath $runtimeLockPath) {
    Remove-Item -LiteralPath $runtimeLockPath -Force -ErrorAction SilentlyContinue
}

$daemonArgs = @()
if ($Once) {
    $daemonArgs += "--once"
}
elseif ($PollOnce) {
    $daemonArgs += "--poll-once"
}

# Build a self-contained launcher wrapper that loads the env file itself.
# This ensures the background child process always has all required env vars
# (MT5 credentials, Supabase keys, Telegram token, etc.) regardless of
# whether Windows Start-Process forwards the parent process's env vars when
# file-redirection handles are also in play.
$launcherPath = Join-Path $resultsDir "trade_oracle_daemon_launcher.ps1"
$argLine = if ($daemonArgs.Count -gt 0) { " " + ($daemonArgs -join " ") } else { "" }
$launcherContent = @"
# Auto-generated launcher - do not edit manually.
param()
`$ErrorActionPreference = 'Stop'
foreach (`$line in Get-Content -LiteralPath '$($envPath.Replace("'", "''"))') {
    `$trimmed = `$line.Trim()
    if (-not `$trimmed -or `$trimmed.StartsWith('#')) { continue }
    `$parts = `$trimmed -split '=', 2
    if (`$parts.Count -ne 2) { continue }
    `$name = `$parts[0].Trim()
    `$value = `$parts[1].Trim()
    if ((`$value.StartsWith('"') -and `$value.EndsWith('"')) -or (`$value.StartsWith("'") -and `$value.EndsWith("'"))) {
        `$value = `$value.Substring(1, `$value.Length - 2)
    }
    [System.Environment]::SetEnvironmentVariable(`$name, `$value, 'Process')
}
& '$($python.Replace("'", "''"))' -u '$($script.Replace("'", "''"))'$argLine
"@
Set-Content -LiteralPath $launcherPath -Value $launcherContent -Encoding UTF8

$launcherArgs = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $launcherPath
)
$process = Start-Process -FilePath "powershell.exe" -ArgumentList $launcherArgs -WorkingDirectory $repoRoot -RedirectStandardOutput $outPath -RedirectStandardError $errPath -PassThru -WindowStyle Hidden

Start-Sleep -Seconds 8

$runtimeLockPid = Get-RuntimeLockProcessId -LockFile $runtimeLockPath
if ($runtimeLockPid -gt 0 -and (Get-Process -Id $runtimeLockPid -ErrorAction SilentlyContinue)) {
    Set-Content -LiteralPath $pidPath -Value $runtimeLockPid
    Write-Output ("PID=" + $runtimeLockPid)
}
else {
    $confirmedProcess = Get-Process -Id $process.Id -ErrorAction SilentlyContinue
    if ($null -eq $confirmedProcess) {
        Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
        throw "TRADE_ORACLE daemon exited during startup. Check $errPath"
    }
    Set-Content -LiteralPath $pidPath -Value $process.Id
    Write-Output ("PID=" + $process.Id)
}
Write-Output ("LOG=" + $outPath)
Write-Output ("ERR=" + $errPath)
