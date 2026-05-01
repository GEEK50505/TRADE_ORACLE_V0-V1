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

$outPath = Join-Path $resultsDir "trade_oracle_daemon.log"
$errPath = Join-Path $resultsDir "trade_oracle_daemon.err.log"
$pidPath = Join-Path $resultsDir "trade_oracle_daemon.pid"

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

$args = @($script)
if ($Once) {
    $args += "--once"
}
elseif ($PollOnce) {
    $args += "--poll-once"
}

$process = Start-Process -FilePath $python -ArgumentList $args -WorkingDirectory $repoRoot -RedirectStandardOutput $outPath -RedirectStandardError $errPath -PassThru -WindowStyle Hidden
Set-Content -LiteralPath $pidPath -Value $process.Id

Write-Output ("PID=" + $process.Id)
Write-Output ("LOG=" + $outPath)
Write-Output ("ERR=" + $errPath)
