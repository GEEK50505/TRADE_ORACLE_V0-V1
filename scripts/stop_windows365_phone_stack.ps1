[CmdletBinding()]
param(
    [string]$ComposeFile = "docker-compose.n8n.local.yml",
    [switch]$LeaveN8NUp
)

$ErrorActionPreference = "Stop"

function Stop-ProcessFromPidFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidFile
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return
    }

    try {
        $pidValue = Get-Content -LiteralPath $PidFile -Raw
        $targetProcessId = [int]($pidValue.Trim())
        $process = Get-Process -Id $targetProcessId -ErrorAction SilentlyContinue
        if ($process) {
            $process | Stop-Process -Force
        }
    }
    catch {
        Write-Warning "Could not stop process from pid file ${PidFile}: $($_.Exception.Message)"
    }
    finally {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
$composePath = Join-Path $repoRoot $ComposeFile

Stop-ProcessFromPidFile -PidFile (Join-Path $resultsDir "windows365_quicktunnel.pid")
Stop-ProcessFromPidFile -PidFile (Join-Path $resultsDir "windows365_platform.pid")

if (-not $LeaveN8NUp) {
    & docker compose -f $composePath down | Out-Host
}

Write-Host "Stopped TRADE_ORACLE Windows 365 helper processes."
