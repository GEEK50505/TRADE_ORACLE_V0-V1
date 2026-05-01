[CmdletBinding()]
param(
    [string]$TaskName = "TRADE_ORACLE 4H Wake Cycle",
    [string]$EnvFile = ".env.n8n.local",
    [string]$ComposeFile = "docker-compose.n8n.local.yml",
    [string]$StartTime = "00:00"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$bootstrapScript = Join-Path $repoRoot "scripts\start_windows365_phone_stack.ps1"

if (-not (Test-Path -LiteralPath $bootstrapScript)) {
    throw "Bootstrap script not found: $bootstrapScript"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$bootstrapScript`" -EnvFile `"$EnvFile`" -ComposeFile `"$ComposeFile`""

$triggerTime = [DateTime]::Today.Add([TimeSpan]::Parse($StartTime))
$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At $triggerTime `
    -RepetitionInterval (New-TimeSpan -Hours 4) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -WakeToRun `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Wakes the PC and refreshes the TRADE_ORACLE local server stack every 4 hours." `
    -Force | Out-Null

Write-Host "Installed scheduled task: $TaskName"
Write-Host "Start time: $StartTime local time"
Write-Host "Repeats every 4 hours and requests WakeToRun."
Write-Host ""
Write-Host "Important:"
Write-Host "- Wake from sleep/hibernate is usually possible."
Write-Host "- Power-on from full shutdown depends on BIOS/UEFI RTC alarm support, not Windows alone."
Write-Host "- Keep the laptop on AC power and enable Windows wake timers."
