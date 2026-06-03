[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$pidPath = Join-Path $repoRoot "results\trade_oracle_daemon.pid"
$runtimeLockPath = Join-Path $repoRoot "results\trade_oracle_daemon_runtime.lock"

if (-not (Test-Path -LiteralPath $pidPath)) {
    Write-Output "No TRADE_ORACLE daemon pid file found."
    exit 0
}

try {
    $daemonProcessId = [int]((Get-Content -LiteralPath $pidPath -Raw).Trim())
}
catch {
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    Write-Output "Removed invalid daemon pid file."
    exit 0
}

$process = Get-Process -Id $daemonProcessId -ErrorAction SilentlyContinue
if ($null -eq $process) {
    Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
    Write-Output "Daemon process was not running. Removed stale pid file."
    exit 0
}

Stop-Process -Id $daemonProcessId -Force
Remove-Item -LiteralPath $pidPath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $runtimeLockPath -Force -ErrorAction SilentlyContinue
Write-Output "Stopped TRADE_ORACLE daemon PID $daemonProcessId."
