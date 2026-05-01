[CmdletBinding()]
param(
    [string]$TaskPrefix = "TRADE_ORACLE Local Server",
    [string]$EnvFile = ".env.n8n.local",
    [ValidateSet("daemon", "n8n")]
    [string]$RuntimeMode = "daemon"
)

$ErrorActionPreference = "Stop"

function Test-IsAdministrator {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Install-StartupLauncher {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WatchdogScript,
        [Parameter(Mandatory = $true)]
        [string]$EnvFile,
        [Parameter(Mandatory = $true)]
        [string]$RuntimeMode,
        [Parameter(Mandatory = $true)]
        [string]$TaskPrefix
    )

    $startupDir = [Environment]::GetFolderPath("Startup")
    if (-not (Test-Path -LiteralPath $startupDir)) {
        throw "Startup folder not found: $startupDir"
    }

    $launcherPath = Join-Path $startupDir "$TaskPrefix Watchdog.cmd"
    $launcherContent = "@echo off`r`npowershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$WatchdogScript`" -EnvFile `"$EnvFile`" -RuntimeMode `"$RuntimeMode`"`r`n"
    Set-Content -LiteralPath $launcherPath -Value $launcherContent
    return $launcherPath
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$watchdogScript = Join-Path $repoRoot "scripts\run_local_server_watchdog.ps1"

if (-not (Test-Path -LiteralPath $watchdogScript)) {
    throw "Watchdog script not found: $watchdogScript"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$watchdogScript`" -EnvFile `"$EnvFile`" -RuntimeMode `"$RuntimeMode`""
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable

$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$logonTaskName = "$TaskPrefix Watchdog (Logon)"
$createdLogonTask = $false
$createdStartupTask = $false
$startupLauncherPath = $null

try {
    Register-ScheduledTask -TaskName $logonTaskName -Action $action -Trigger $logonTrigger -Settings $settings -Description "Starts the TRADE_ORACLE local-server watchdog at user logon." -Force | Out-Null
    Start-ScheduledTask -TaskName $logonTaskName
    $createdLogonTask = $true
}
catch {
    Write-Warning "Could not register the logon scheduled task. Falling back to the Startup folder. $($_.Exception.Message)"
    $startupLauncherPath = Install-StartupLauncher -WatchdogScript $watchdogScript -EnvFile $EnvFile -RuntimeMode $RuntimeMode -TaskPrefix $TaskPrefix
}

if (Test-IsAdministrator) {
    try {
        $startupTrigger = New-ScheduledTaskTrigger -AtStartup
        $startupPrincipal = New-ScheduledTaskPrincipal -UserId "SYSTEM" -RunLevel Highest -LogonType ServiceAccount
        $startupTaskName = "$TaskPrefix Watchdog (Startup)"
        Register-ScheduledTask -TaskName $startupTaskName -Action $action -Trigger $startupTrigger -Principal $startupPrincipal -Settings $settings -Description "Starts the TRADE_ORACLE local-server watchdog at Windows startup." -Force | Out-Null
        $createdStartupTask = $true
    }
    catch {
        Write-Warning "Could not register the startup scheduled task. $($_.Exception.Message)"
    }
}

Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden", "-File", $watchdogScript, "-EnvFile", $EnvFile, "-RuntimeMode", $RuntimeMode -WindowStyle Hidden

Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Add TRADE_ORACLE_ALERT_TELEGRAM_BOT_TOKEN to $EnvFile so the watchdog can alert you directly."
Write-Host "2. Optional: add TRADE_ORACLE_HEARTBEAT_URL from an external heartbeat service if you want an alert when the whole laptop goes offline."
Write-Host "3. Keep Windows sleep disabled while using the PC as your server."
Write-Host "Runtime mode: $RuntimeMode"
if ($createdLogonTask) {
    Write-Host "Installed scheduled task: $logonTaskName"
}
if ($createdStartupTask) {
    Write-Host "Installed scheduled task: $TaskPrefix Watchdog (Startup)"
}
if ($startupLauncherPath) {
    Write-Host "Installed Startup-folder launcher: $startupLauncherPath"
}
