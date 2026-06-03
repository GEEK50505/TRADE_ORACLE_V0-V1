[CmdletBinding()]
param(
    [switch]$DcToo
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null
$statusPath = Join-Path $resultsDir "wake_timer_policy_status.json"

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

$isAdmin = Test-IsAdmin
$status = [ordered]@{
    checked_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    is_admin = $isAdmin
    ok = $false
    actions = @()
    notes = @()
}

try {
    $availableSleepStates = & powercfg /a 2>&1
    $status.available_sleep_states = @($availableSleepStates | ForEach-Object { [string]$_ })
}
catch {
    $status.available_sleep_states_error = $_.Exception.Message
}

if (-not $isAdmin) {
    $status.notes += "Run this script from an Administrator PowerShell window to change wake-timer policy."
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Output "WAKE_TIMER_POLICY_UPDATED=False"
    Write-Output "REASON=administrator_required"
    Write-Output "STATUS=$statusPath"
    exit 1
}

try {
    & powercfg /setacvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 | Out-Null
    $status.actions += "enabled_ac_wake_timers"
    if ($DcToo) {
        & powercfg /setdcvalueindex SCHEME_CURRENT SUB_SLEEP RTCWAKE 1 | Out-Null
        $status.actions += "enabled_dc_wake_timers"
    }
    & powercfg /S SCHEME_CURRENT | Out-Null
    $wakeTimers = & powercfg /waketimers 2>&1
    $status.wake_timers = @($wakeTimers | ForEach-Object { [string]$_ })
    $status.ok = $true
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8
    Write-Output "WAKE_TIMER_POLICY_UPDATED=True"
    Write-Output "STATUS=$statusPath"
}
catch {
    $status.ok = $false
    $status.error = $_.Exception.Message
    $status | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statusPath -Encoding UTF8
    throw
}
