[CmdletBinding()]
param(
    [string]$EnvFile = ".env.n8n.local",
    [string]$PythonPath = ".venv-langgraph\Scripts\python.exe",
    [string]$Mt5PreflightSymbols = "SOL/USDT",
    [int]$NetworkWaitSeconds = 180,
    [switch]$SkipCycle,
    [switch]$SkipMt5Preflight,
    [switch]$SkipStackStart
)

$ErrorActionPreference = "Stop"

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Data
    )

    $Data | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $Path -Encoding UTF8
}

function Add-LogLine {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Message
    )

    Add-Content -LiteralPath $Path -Value ("{0} {1}" -f (Get-Date).ToUniversalTime().ToString("o"), $Message)
}

function Invoke-Captured {
    param(
        [Parameter(Mandatory = $true)]
        [string]$FilePath,
        [Parameter(Mandatory = $true)]
        [string[]]$Arguments,
        [Parameter(Mandatory = $true)]
        [string]$WorkingDirectory
    )

    $previousErrorActionPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & $FilePath @Arguments 2>&1
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }
    return [ordered]@{
        file = $FilePath
        arguments = $Arguments
        exit_code = $exitCode
        output = @($output | ForEach-Object { [string]$_ })
    }
}

function Enable-ProcessAwakeGuard {
    try {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class TradeOraclePowerGuard {
    [DllImport("kernel32.dll")]
    public static extern uint SetThreadExecutionState(uint esFlags);
}
"@
        $ES_CONTINUOUS = [uint32]0x80000000
        $ES_SYSTEM_REQUIRED = [uint32]0x00000001
        $ES_AWAYMODE_REQUIRED = [uint32]0x00000040
        [TradeOraclePowerGuard]::SetThreadExecutionState($ES_CONTINUOUS -bor $ES_SYSTEM_REQUIRED -bor $ES_AWAYMODE_REQUIRED) | Out-Null
        return $true
    }
    catch {
        return $false
    }
}

function Disable-ProcessAwakeGuard {
    try {
        $ES_CONTINUOUS = [uint32]0x80000000
        [TradeOraclePowerGuard]::SetThreadExecutionState($ES_CONTINUOUS) | Out-Null
    }
    catch {
    }
}

function Wait-Readiness {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Python,
        [Parameter(Mandatory = $true)]
        [string]$EnvFile,
        [Parameter(Mandatory = $true)]
        [int]$TimeoutSeconds,
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $attempts = New-Object System.Collections.Generic.List[object]
    while ((Get-Date) -lt $deadline) {
        $result = Invoke-Captured -FilePath $Python -Arguments @("scripts\check_forward_test_readiness.py", "--env-file", $EnvFile, "--check-supabase") -WorkingDirectory $RepoRoot
        $attempts.Add($result)
        if ($result.exit_code -eq 0) {
            try {
                $payload = ($result.output -join "`n") | ConvertFrom-Json
                if ($payload.ready_for_forward_testing_start) {
                    return [ordered]@{
                        ok = $true
                        attempts = $attempts
                        readiness = $payload
                    }
                }
            }
            catch {
            }
        }
        Start-Sleep -Seconds 10
    }

    return [ordered]@{
        ok = $false
        attempts = $attempts
        readiness = $null
    }
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

$statusPath = Join-Path $resultsDir "wake_cycle_status.json"
$logPath = Join-Path $resultsDir "wake_cycle.log"
$python = Join-Path $repoRoot $PythonPath
$startedAtUtc = (Get-Date).ToUniversalTime()
$awakeGuardEnabled = Enable-ProcessAwakeGuard

$status = [ordered]@{
    started_at_utc = $startedAtUtc.ToString("o")
    completed_at_utc = ""
    ok = $false
    env_file = $EnvFile
    skip_cycle = [bool]$SkipCycle
    skip_mt5_preflight = [bool]$SkipMt5Preflight
    skip_stack_start = [bool]$SkipStackStart
    awake_guard_enabled = $awakeGuardEnabled
    steps = [ordered]@{}
}

try {
    Add-LogLine -Path $logPath -Message "wake_cycle_start skip_cycle=$([bool]$SkipCycle)"

    if (-not (Test-Path -LiteralPath $python)) {
        throw "Python interpreter not found: $python"
    }

    $status.steps.initial_readiness = Wait-Readiness -Python $python -EnvFile $EnvFile -TimeoutSeconds $NetworkWaitSeconds -RepoRoot $repoRoot
    if (-not $status.steps.initial_readiness.ok) {
        throw "Readiness did not become green within $NetworkWaitSeconds seconds."
    }

    if (-not $SkipStackStart) {
        $startArgs = @(
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            "scripts\start_forward_testing_stack.ps1",
            "-EnvFile",
            $EnvFile,
            "-Mt5PreflightSymbols",
            $Mt5PreflightSymbols
        )
        if ($SkipMt5Preflight) {
            $startArgs += "-SkipMt5Preflight"
        }
        $status.steps.stack_start = Invoke-Captured -FilePath "powershell.exe" -Arguments $startArgs -WorkingDirectory $repoRoot
        if ($status.steps.stack_start.exit_code -ne 0) {
            throw "Forward-testing stack startup failed."
        }
    }

    $status.steps.poll_once = Invoke-Captured -FilePath $python -Arguments @("scripts\run_trade_oracle_daemon.py", "--poll-once") -WorkingDirectory $repoRoot
    if ($status.steps.poll_once.exit_code -ne 0) {
        throw "Telegram poll-once failed."
    }

    if (-not $SkipCycle) {
        $status.steps.cycle_once = Invoke-Captured -FilePath $python -Arguments @("scripts\run_trade_oracle_daemon.py", "--once") -WorkingDirectory $repoRoot
        if ($status.steps.cycle_once.exit_code -ne 0) {
            throw "Wake-triggered daemon cycle failed."
        }
    }

    $status.steps.final_readiness = Wait-Readiness -Python $python -EnvFile $EnvFile -TimeoutSeconds 60 -RepoRoot $repoRoot
    $status.ok = [bool]$status.steps.final_readiness.ok
    if (-not $status.ok) {
        throw "Final readiness check did not pass after wake cycle."
    }
    Add-LogLine -Path $logPath -Message "wake_cycle_complete ok=True"
}
catch {
    $status.ok = $false
    $status.error = [ordered]@{
        type = $_.Exception.GetType().FullName
        message = $_.Exception.Message
    }
    Add-LogLine -Path $logPath -Message ("wake_cycle_failed " + $_.Exception.Message)
    Write-Output ("WAKE_CYCLE_FAILED=" + $_.Exception.Message)
    exit 1
}
finally {
    Disable-ProcessAwakeGuard
    $status.completed_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    Write-JsonFile -Path $statusPath -Data $status
}
