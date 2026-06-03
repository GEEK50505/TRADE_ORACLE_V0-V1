[CmdletBinding()]
param(
    [string]$TaskName = "TRADE_ORACLE Hourly Wake Cycle"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null
$statusPath = Join-Path $resultsDir "wake_cycle_task_probe.json"

$task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
$info = Get-ScheduledTaskInfo -TaskName $TaskName -ErrorAction SilentlyContinue
$xml = if ($task) { [xml](Export-ScheduledTask -TaskName $TaskName) } else { $null }

$actionText = ""
if ($task -and $task.Actions.Count -gt 0) {
    $actionText = (($task.Actions | ForEach-Object { "$($_.Execute) $($_.Arguments)" }) -join "`n")
}

$probe = [ordered]@{
    checked_at_utc = (Get-Date).ToUniversalTime().ToString("o")
    task_name = $TaskName
    exists = [bool]$task
    state = if ($task) { [string]$task.State } else { "" }
    next_run_time = if ($info) { [string]$info.NextRunTime } else { "" }
    last_run_time = if ($info) { [string]$info.LastRunTime } else { "" }
    last_task_result = if ($info) { [int]$info.LastTaskResult } else { $null }
    wake_to_run = if ($xml) { [bool]::Parse([string]$xml.Task.Settings.WakeToRun) } else { $false }
    start_when_available = if ($xml) { [bool]::Parse([string]$xml.Task.Settings.StartWhenAvailable) } else { $false }
    multiple_instances_policy = if ($xml) { [string]$xml.Task.Settings.MultipleInstancesPolicy } else { "" }
    action_mentions_wake_runner = $actionText -like "*run_forward_test_wake_cycle.ps1*"
    action_mentions_env_file = $actionText -like "*.env.n8n.local*"
    action = $actionText
}

$probe.ok = $probe.exists -and $probe.wake_to_run -and $probe.start_when_available -and $probe.action_mentions_wake_runner
$probe | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $statusPath -Encoding UTF8

if ($probe.ok) {
    Write-Output "WAKE_CYCLE_TASK_OK=True"
}
else {
    Write-Output "WAKE_CYCLE_TASK_OK=False"
}
Write-Output "STATUS=$statusPath"

if (-not $probe.ok) {
    exit 1
}
