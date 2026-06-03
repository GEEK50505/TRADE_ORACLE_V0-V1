[CmdletBinding()]
param(
    [switch]$StopMt5
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
$watchdogPidPath = Join-Path $resultsDir "trade_oracle_watchdog.pid"
$statusPath = Join-Path $resultsDir "forward_testing_stack_status.json"
$stopDaemonScript = Join-Path $repoRoot "scripts\stop_trade_oracle_daemon.ps1"

& $stopDaemonScript

if (Test-Path -LiteralPath $watchdogPidPath) {
    try {
        $watchdogPid = [int]((Get-Content -LiteralPath $watchdogPidPath -Raw).Trim())
        $watchdogProcess = Get-Process -Id $watchdogPid -ErrorAction SilentlyContinue
        if ($null -ne $watchdogProcess) {
            Stop-Process -Id $watchdogPid -Force
        }
        Remove-Item -LiteralPath $watchdogPidPath -Force -ErrorAction SilentlyContinue
        Write-Output ("Stopped watchdog PID " + $watchdogPid + ".")
    }
    catch {
        Remove-Item -LiteralPath $watchdogPidPath -Force -ErrorAction SilentlyContinue
        Write-Output "Removed stale watchdog pid file."
    }
}
else {
    Write-Output "No watchdog pid file found."
}

if ($StopMt5) {
    $mt5Processes = Get-Process -Name "terminal64" -ErrorAction SilentlyContinue
    if ($mt5Processes) {
        $mt5Processes | Stop-Process -Force
        Write-Output "Stopped MetaTrader 5 terminal process(es)."
    }
}

if (Test-Path -LiteralPath $statusPath) {
    Remove-Item -LiteralPath $statusPath -Force -ErrorAction SilentlyContinue
}
