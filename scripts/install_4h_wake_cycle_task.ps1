[CmdletBinding()]
param(
    [string]$TaskName = "TRADE_ORACLE Hourly Wake Cycle",
    [string]$EnvFile = ".env.n8n.local",
    [string]$ComposeFile = "docker-compose.n8n.local.yml",
    [string]$StartTime = "00:00",
    [string]$Mt5PreflightSymbols = "SOL/USDT",
    [int]$IntervalHours = 1,
    [ValidateSet("daemon", "n8n")]
    [string]$RuntimeMode = "daemon"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$bootstrapScript = if ($RuntimeMode -eq "daemon") {
    Join-Path $repoRoot "scripts\run_forward_test_wake_cycle.ps1"
}
else {
    Join-Path $repoRoot "scripts\start_windows365_phone_stack.ps1"
}

if (-not (Test-Path -LiteralPath $bootstrapScript)) {
    throw "Bootstrap script not found: $bootstrapScript"
}

if ($RuntimeMode -eq "daemon") {
    $actionArguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$bootstrapScript`" -EnvFile `"$EnvFile`" -Mt5PreflightSymbols `"$Mt5PreflightSymbols`""
}
else {
    $actionArguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$bootstrapScript`" -EnvFile `"$EnvFile`" -ComposeFile `"$ComposeFile`""
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $actionArguments -WorkingDirectory $repoRoot

$resolvedIntervalHours = [Math]::Max(1, $IntervalHours)
$triggerTime = [DateTime]::Today.Add([TimeSpan]::Parse($StartTime))
while ($triggerTime -le (Get-Date).AddMinutes(2)) {
    $triggerTime = $triggerTime.AddHours($resolvedIntervalHours)
}
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $triggerTime `
    -RepetitionInterval (New-TimeSpan -Hours $resolvedIntervalHours) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Wakes the PC and refreshes the TRADE_ORACLE local server stack every $resolvedIntervalHours hour(s)." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Next start time: $($triggerTime.ToString('s')) local time"
Write-Host "Repeats every $resolvedIntervalHours hour(s) and requests WakeToRun."
Write-Host "Runtime mode: $RuntimeMode"
Write-Host "Action script: $bootstrapScript"
Write-Host ""
Write-Host "Important:"
Write-Host "- Wake from sleep/hibernate is usually possible."
Write-Host "- Power-on from full shutdown depends on BIOS/UEFI RTC alarm support, not Windows alone."
Write-Host "- Keep the laptop on AC power and enable Windows wake timers."
