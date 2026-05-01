[CmdletBinding()]
param(
    [string]$EnvFile = ".env.n8n.local",
    [string]$ComposeFile = "docker-compose.n8n.local.yml",
    [ValidateSet("daemon", "n8n")]
    [string]$RuntimeMode = "daemon",
    [int]$PlatformPort = 8000,
    [int]$N8NPort = 5678,
    [switch]$RunOnce
)

$ErrorActionPreference = "Stop"

function Read-DotEnvFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }

    $values = @{}
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) {
            continue
        }

        $parts = $trimmed -split "=", 2
        if ($parts.Count -ne 2) {
            continue
        }

        $values[$parts[0].Trim()] = $parts[1]
    }

    return $values
}

function Get-EnvValue {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$EnvMap,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [string]$DefaultValue = ""
    )

    if ($EnvMap.ContainsKey($Name)) {
        return [string]$EnvMap[$Name]
    }

    return $DefaultValue
}

function Test-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
        return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500)
    }
    catch {
        return $false
    }
}

function Test-RunningProcessFromPidFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$PidFile
    )

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $false
    }

    try {
        $pid = [int]((Get-Content -LiteralPath $PidFile -Raw).Trim())
        return $null -ne (Get-Process -Id $pid -ErrorAction SilentlyContinue)
    }
    catch {
        return $false
    }
}

function Write-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [object]$Data
    )

    $json = $Data | ConvertTo-Json -Depth 8
    Set-Content -LiteralPath $Path -Value $json
}

function Read-JsonFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        return $null
    }

    try {
        return Get-Content -LiteralPath $Path -Raw | ConvertFrom-Json
    }
    catch {
        return $null
    }
}

function Send-TelegramMessage {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$EnvMap,
        [Parameter(Mandatory = $true)]
        [string]$Text
    )

    $token = Get-EnvValue -EnvMap $EnvMap -Name "TRADE_ORACLE_ALERT_TELEGRAM_BOT_TOKEN"
    $chatId = Get-EnvValue -EnvMap $EnvMap -Name "TRADE_ORACLE_ALERT_TELEGRAM_CHAT_ID" -DefaultValue (Get-EnvValue -EnvMap $EnvMap -Name "TRADE_ORACLE_TELEGRAM_CHAT_ID")

    if ([string]::IsNullOrWhiteSpace($token) -or [string]::IsNullOrWhiteSpace($chatId)) {
        return $false
    }

    $uri = "https://api.telegram.org/bot$token/sendMessage"
    $body = @{
        chat_id = $chatId
        text = $Text
        disable_notification = "false"
    }

    try {
        Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType "application/x-www-form-urlencoded" | Out-Null
        return $true
    }
    catch {
        Write-Warning "Telegram alert failed: $($_.Exception.Message)"
        return $false
    }
}

function Invoke-Heartbeat {
    param(
        [Parameter(Mandatory = $true)]
        [hashtable]$EnvMap
    )

    $heartbeatUrl = Get-EnvValue -EnvMap $EnvMap -Name "TRADE_ORACLE_HEARTBEAT_URL"
    if ([string]::IsNullOrWhiteSpace($heartbeatUrl)) {
        return
    }

    try {
        Invoke-WebRequest -Uri $heartbeatUrl -UseBasicParsing -TimeoutSec 8 | Out-Null
    }
    catch {
        Write-Warning "Heartbeat ping failed: $($_.Exception.Message)"
    }
}

function Invoke-LocalBootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$EnvFile,
        [Parameter(Mandatory = $true)]
        [string]$ComposeFile
    )

    $scriptPath = Join-Path $RepoRoot "scripts\start_windows365_phone_stack.ps1"
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $scriptPath,
        "-EnvFile",
        $EnvFile,
        "-ComposeFile",
        $ComposeFile
    )

    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WorkingDirectory $RepoRoot -PassThru -Wait -WindowStyle Hidden
    return $process.ExitCode
}

function Invoke-DaemonBootstrap {
    param(
        [Parameter(Mandatory = $true)]
        [string]$RepoRoot,
        [Parameter(Mandatory = $true)]
        [string]$EnvFile
    )

    $scriptPath = Join-Path $RepoRoot "scripts\start_trade_oracle_daemon.ps1"
    $args = @(
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        $scriptPath,
        "-EnvFile",
        $EnvFile
    )

    $process = Start-Process -FilePath "powershell.exe" -ArgumentList $args -WorkingDirectory $RepoRoot -PassThru -Wait -WindowStyle Hidden
    return $process.ExitCode
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

$envPath = Join-Path $repoRoot $EnvFile
$statePath = Join-Path $resultsDir "local_server_watchdog_state.json"
$heartbeatStatePath = Join-Path $resultsDir "local_server_watchdog_heartbeat.json"
$composePath = Join-Path $repoRoot $ComposeFile
$tunnelPidFile = Join-Path $resultsDir "windows365_quicktunnel.pid"
$daemonPidFile = Join-Path $resultsDir "trade_oracle_daemon.pid"
$watchdogLogPath = Join-Path $resultsDir "local_server_watchdog.log"

$previousState = Read-JsonFile -Path $statePath

while ($true) {
    $envMap = Read-DotEnvFile -Path $envPath
    $intervalSeconds = [Math]::Max(15, [int](Get-EnvValue -EnvMap $envMap -Name "TRADE_ORACLE_WATCHDOG_INTERVAL_SECONDS" -DefaultValue "60"))
    $cooldownMinutes = [Math]::Max(1, [int](Get-EnvValue -EnvMap $envMap -Name "TRADE_ORACLE_WATCHDOG_COOLDOWN_MINUTES" -DefaultValue "15"))

    $daemonHealthy = Test-RunningProcessFromPidFile -PidFile $daemonPidFile
    $n8nHealthy = if ($RuntimeMode -eq "n8n") { Test-HttpReady -Url "http://127.0.0.1:$N8NPort/healthz" } else { $true }
    $platformHealthy = if ($RuntimeMode -eq "n8n") { Test-HttpReady -Url "http://127.0.0.1:$PlatformPort/system/health" } else { $true }

    $webhookUrl = Get-EnvValue -EnvMap $envMap -Name "WEBHOOK_URL"
    $requiresTunnel = $RuntimeMode -eq "n8n" -and $webhookUrl -match "^https://.+"
    $tunnelHealthy = if ($requiresTunnel) { Test-RunningProcessFromPidFile -PidFile $tunnelPidFile } else { $true }

    $reasons = New-Object System.Collections.Generic.List[string]
    if ($RuntimeMode -eq "daemon" -and -not $daemonHealthy) { $reasons.Add("TRADE_ORACLE daemon is not running") }
    if (-not $n8nHealthy) { $reasons.Add("n8n health check failed on port $N8NPort") }
    if (-not $platformHealthy) { $reasons.Add("platform health check failed on port $PlatformPort") }
    if (-not $tunnelHealthy) { $reasons.Add("Telegram webhook tunnel is not running") }

    $healthy = $reasons.Count -eq 0
    $nowUtc = (Get-Date).ToUniversalTime()
    $status = if ($healthy) { "healthy" } else { "degraded" }

    Write-JsonFile -Path $heartbeatStatePath -Data @{
        observed_at_utc = $nowUtc.ToString("o")
        status = $status
        runtime_mode = $RuntimeMode
        daemon_healthy = $daemonHealthy
        n8n_healthy = $n8nHealthy
        platform_healthy = $platformHealthy
        tunnel_healthy = $tunnelHealthy
        webhook_url = $webhookUrl
    }

    Add-Content -LiteralPath $watchdogLogPath -Value ("{0} mode={1} status={2} daemon={3} n8n={4} platform={5} tunnel={6}" -f $nowUtc.ToString("o"), $RuntimeMode, $status, $daemonHealthy, $n8nHealthy, $platformHealthy, $tunnelHealthy)

    if ($healthy) {
        Invoke-Heartbeat -EnvMap $envMap
    }

    $shouldAlertDegraded = $false
    $shouldAlertRecovered = $false
    if ($null -eq $previousState) {
        $shouldAlertDegraded = -not $healthy
    }
    else {
        if ($previousState.status -ne "degraded" -and -not $healthy) {
            $shouldAlertDegraded = $true
        }
        elseif ($previousState.status -eq "degraded" -and $healthy) {
            $shouldAlertRecovered = $true
        }
    }

    if ($shouldAlertDegraded) {
        $text = "TRADE_ORACLE local server degraded`nHost: $env:COMPUTERNAME`nTime UTC: $($nowUtc.ToString("o"))`nIssues:`n- $($reasons -join "`n- ")"
        Send-TelegramMessage -EnvMap $envMap -Text $text | Out-Null
    }

    if (-not $healthy) {
        $canBootstrap = $true
        if ($previousState -and $previousState.last_bootstrap_attempt_utc) {
            try {
                $lastBootstrap = [DateTime]::Parse($previousState.last_bootstrap_attempt_utc)
                if ($lastBootstrap.ToUniversalTime().AddMinutes($cooldownMinutes) -gt $nowUtc) {
                    $canBootstrap = $false
                }
            }
            catch {
                $canBootstrap = $true
            }
        }

        if ($canBootstrap) {
            $bootstrapExitCode = $null
            try {
                if ($RuntimeMode -eq "daemon") {
                    $bootstrapExitCode = Invoke-DaemonBootstrap -RepoRoot $repoRoot -EnvFile $EnvFile
                }
                else {
                    $bootstrapExitCode = Invoke-LocalBootstrap -RepoRoot $repoRoot -EnvFile $EnvFile -ComposeFile $ComposeFile
                }
            }
            catch {
                $bootstrapExitCode = 1
                Write-Warning "Bootstrap attempt failed: $($_.Exception.Message)"
            }

            $recheckDaemon = Test-RunningProcessFromPidFile -PidFile $daemonPidFile
            $recheckN8N = if ($RuntimeMode -eq "n8n") { Test-HttpReady -Url "http://127.0.0.1:$N8NPort/healthz" } else { $true }
            $recheckPlatform = if ($RuntimeMode -eq "n8n") { Test-HttpReady -Url "http://127.0.0.1:$PlatformPort/system/health" } else { $true }
            $recheckTunnel = if ($requiresTunnel) { Test-RunningProcessFromPidFile -PidFile $tunnelPidFile } else { $true }
            $recovered = if ($RuntimeMode -eq "daemon") { $recheckDaemon } else { $recheckN8N -and $recheckPlatform -and $recheckTunnel }

            if ($recovered) {
                $healthy = $true
                $status = "healthy"
                Send-TelegramMessage -EnvMap $envMap -Text ("TRADE_ORACLE local server recovered automatically`nHost: {0}`nTime UTC: {1}" -f $env:COMPUTERNAME, $nowUtc.ToString("o")) | Out-Null
            }
            else {
                Send-TelegramMessage -EnvMap $envMap -Text ("TRADE_ORACLE auto-restart attempted but stack is still degraded`nHost: {0}`nBootstrap exit: {1}`nTime UTC: {2}" -f $env:COMPUTERNAME, $bootstrapExitCode, $nowUtc.ToString("o")) | Out-Null
            }

            $previousState = [pscustomobject]@{
                status = if ($healthy) { "healthy" } else { "degraded" }
                observed_at_utc = $nowUtc.ToString("o")
                last_bootstrap_attempt_utc = $nowUtc.ToString("o")
                runtime_mode = $RuntimeMode
                reasons = $reasons
            }
            Write-JsonFile -Path $statePath -Data $previousState

            if ($RunOnce) {
                break
            }

            Start-Sleep -Seconds $intervalSeconds
            continue
        }
    }

    if ($shouldAlertRecovered) {
        $text = "TRADE_ORACLE local server recovered`nHost: $env:COMPUTERNAME`nTime UTC: $($nowUtc.ToString("o"))"
        Send-TelegramMessage -EnvMap $envMap -Text $text | Out-Null
    }

    $previousState = [pscustomobject]@{
        status = $status
        observed_at_utc = $nowUtc.ToString("o")
        last_bootstrap_attempt_utc = if ($previousState) { $previousState.last_bootstrap_attempt_utc } else { $null }
        runtime_mode = $RuntimeMode
        reasons = $reasons
    }
    Write-JsonFile -Path $statePath -Data $previousState

    if ($RunOnce) {
        break
    }

    Start-Sleep -Seconds $intervalSeconds
}
