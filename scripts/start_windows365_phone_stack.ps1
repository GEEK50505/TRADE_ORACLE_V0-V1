[CmdletBinding()]
param(
    [string]$EnvFile = ".env.n8n.local",
    [string]$ComposeFile = "docker-compose.n8n.local.yml",
    [int]$PlatformPort = 8000,
    [int]$N8NPort = 5678,
    [int]$TunnelTimeoutSeconds = 60,
    [switch]$SkipPlatform,
    [switch]$SkipN8N,
    [switch]$SkipTunnel
)

$ErrorActionPreference = "Stop"

function Set-Or-AppendEnvVar {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Path,
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Value
    )

    if (-not (Test-Path -LiteralPath $Path)) {
        throw "Env file not found: $Path"
    }

    $content = Get-Content -LiteralPath $Path -Raw
    $escapedName = [Regex]::Escape($Name)
    $pattern = "(?m)^$escapedName=.*$"
    $line = "$Name=$Value"

    if ($content -match $pattern) {
        $updated = [Regex]::Replace($content, $pattern, $line)
    }
    else {
        $separator = if ($content.EndsWith("`n") -or $content.Length -eq 0) { "" } else { "`r`n" }
        $updated = $content + $separator + $line + "`r`n"
    }

    Set-Content -LiteralPath $Path -Value $updated -NoNewline
}

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

function Wait-HttpReady {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Url,
        [int]$TimeoutSeconds = 60
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        }
        catch {
            Start-Sleep -Seconds 2
        }
    }

    return $false
}

function Get-CloudflaredPath {
    $command = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallback = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if (Test-Path -LiteralPath $fallback) {
        return $fallback
    }

    throw "cloudflared was not found on PATH and not found at $fallback"
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$resultsDir = Join-Path $repoRoot "results"
New-Item -ItemType Directory -Path $resultsDir -Force | Out-Null

$envPath = Join-Path $repoRoot $EnvFile
$envExamplePath = Join-Path $repoRoot ".env.n8n.local.example"
$composePath = Join-Path $repoRoot $ComposeFile
$pythonPath = Join-Path $repoRoot ".venv-langgraph\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $envPath)) {
    if (-not (Test-Path -LiteralPath $envExamplePath)) {
        throw "Env file not found and example missing: $envExamplePath"
    }
    Copy-Item -LiteralPath $envExamplePath -Destination $envPath
    Write-Host "Created $EnvFile from .env.n8n.local.example"
}

if (-not (Test-Path -LiteralPath $composePath)) {
    throw "Compose file not found: $composePath"
}

$tunnelUrl = $null
$tunnelPidFile = Join-Path $resultsDir "windows365_quicktunnel.pid"
$tunnelStdout = Join-Path $resultsDir "windows365_quicktunnel.out.log"
$tunnelStderr = Join-Path $resultsDir "windows365_quicktunnel.err.log"

if (-not $SkipTunnel) {
    $cloudflaredPath = Get-CloudflaredPath
    Stop-ProcessFromPidFile -PidFile $tunnelPidFile
    Remove-Item -LiteralPath $tunnelStdout, $tunnelStderr -Force -ErrorAction SilentlyContinue

    $tunnelArgs = @("tunnel", "--url", "http://127.0.0.1:$N8NPort", "--no-autoupdate")
    $tunnelProcess = Start-Process -FilePath $cloudflaredPath `
        -ArgumentList $tunnelArgs `
        -WorkingDirectory $repoRoot `
        -RedirectStandardOutput $tunnelStdout `
        -RedirectStandardError $tunnelStderr `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -LiteralPath $tunnelPidFile -Value $tunnelProcess.Id

    $deadline = (Get-Date).AddSeconds($TunnelTimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $combined = ""
        if (Test-Path -LiteralPath $tunnelStdout) {
            $combined += (Get-Content -LiteralPath $tunnelStdout -Raw)
        }
        if (Test-Path -LiteralPath $tunnelStderr) {
            $combined += "`n" + (Get-Content -LiteralPath $tunnelStderr -Raw)
        }

        $match = [Regex]::Match($combined, "https://[a-z0-9-]+\.trycloudflare\.com", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
        if ($match.Success) {
            $tunnelUrl = $match.Value.TrimEnd("/") + "/"
            break
        }

        Start-Sleep -Seconds 2
    }

    if (-not $tunnelUrl) {
        throw "Could not discover a quick tunnel URL within $TunnelTimeoutSeconds seconds. Check $tunnelStdout and $tunnelStderr."
    }

    Set-Or-AppendEnvVar -Path $envPath -Name "WEBHOOK_URL" -Value $tunnelUrl
}

$platformPidFile = Join-Path $resultsDir "windows365_platform.pid"
$platformStdout = Join-Path $resultsDir "windows365_platform.out.log"
$platformStderr = Join-Path $resultsDir "windows365_platform.err.log"

if (-not $SkipPlatform) {
    if (-not (Test-Path -LiteralPath $pythonPath)) {
        throw "LangGraph Python environment not found: $pythonPath"
    }

    $platformHealthy = Wait-HttpReady -Url "http://127.0.0.1:$PlatformPort/system/health" -TimeoutSeconds 3
    if (-not $platformHealthy) {
        Stop-ProcessFromPidFile -PidFile $platformPidFile
        Remove-Item -LiteralPath $platformStdout, $platformStderr -Force -ErrorAction SilentlyContinue

        $platformArgs = @(
            "-m",
            "uvicorn",
            "api.trade_oracle_platform_service:app",
            "--host",
            "0.0.0.0",
            "--port",
            "$PlatformPort"
        )

        $platformProcess = Start-Process -FilePath $pythonPath `
            -ArgumentList $platformArgs `
            -WorkingDirectory $repoRoot `
            -RedirectStandardOutput $platformStdout `
            -RedirectStandardError $platformStderr `
            -WindowStyle Hidden `
            -PassThru

        Set-Content -LiteralPath $platformPidFile -Value $platformProcess.Id

        if (-not (Wait-HttpReady -Url "http://127.0.0.1:$PlatformPort/system/health" -TimeoutSeconds 60)) {
            throw "Platform service did not become healthy on port $PlatformPort. Check $platformStdout and $platformStderr."
        }
    }
}

if (-not $SkipN8N) {
    & docker compose -f $composePath up -d --force-recreate | Out-Host

    if (-not (Wait-HttpReady -Url "http://127.0.0.1:$N8NPort/healthz" -TimeoutSeconds 60)) {
        throw "n8n did not become healthy on port $N8NPort."
    }
}

Write-Host ""
Write-Host "TRADE_ORACLE Windows 365 + phone stack is ready."
Write-Host "n8n editor: http://127.0.0.1:$N8NPort"
Write-Host "Platform health: http://127.0.0.1:$PlatformPort/system/health"
if ($tunnelUrl) {
    Write-Host "Telegram webhook URL: $tunnelUrl"
}
Write-Host "Cloudflare tunnel logs: $tunnelStdout"
Write-Host "Platform logs: $platformStdout"
Write-Host ""
Write-Host "Next steps:"
Write-Host "1. Open n8n and confirm the Telegram workflows are active."
Write-Host "2. On your phone, keep Telegram open for review approvals."
Write-Host "3. If the quick tunnel URL changes after a reboot, rerun this script before using the Telegram trigger workflow."
