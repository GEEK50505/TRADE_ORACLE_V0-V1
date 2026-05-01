[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$TunnelName,

    [Parameter(Mandatory = $true)]
    [string]$Hostname,

    [string]$EnvFile = ".env.n8n.production",

    [switch]$SkipLogin
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

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
    $fallback = "C:\Program Files (x86)\cloudflared\cloudflared.exe"
    if (Test-Path -LiteralPath $fallback) {
        $cloudflared = Get-Item -LiteralPath $fallback
    }
    else {
        throw "cloudflared was not found on PATH and not found at $fallback"
    }
}

$cloudflaredPath = $cloudflared.Source
if (-not $cloudflaredPath) {
    $cloudflaredPath = $cloudflared.FullName
}

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$envPath = Join-Path $repoRoot $EnvFile
$examplePath = Join-Path $repoRoot ".env.n8n.production.example"

if (-not (Test-Path -LiteralPath $envPath)) {
    if (-not (Test-Path -LiteralPath $examplePath)) {
        throw "Production env example not found at $examplePath"
    }
    Copy-Item -LiteralPath $examplePath -Destination $envPath
    Write-Host "Created $EnvFile from .env.n8n.production.example"
}

if (-not $SkipLogin) {
    Write-Host "Opening Cloudflare login flow..."
    & $cloudflaredPath tunnel login
}

Write-Host "Ensuring tunnel exists: $TunnelName"
try {
    & $cloudflaredPath tunnel create $TunnelName | Out-Host
}
catch {
    Write-Host "Tunnel create reported an error. Continuing in case the tunnel already exists."
}

Write-Host "Routing DNS hostname $Hostname to tunnel $TunnelName"
& $cloudflaredPath tunnel route dns $TunnelName $Hostname | Out-Host

Write-Host "Fetching tunnel token..."
$token = (& $cloudflaredPath tunnel token $TunnelName | Out-String).Trim()
if (-not $token) {
    throw "Failed to obtain a Cloudflare tunnel token for $TunnelName"
}

Set-Or-AppendEnvVar -Path $envPath -Name "N8N_HOST" -Value $Hostname
Set-Or-AppendEnvVar -Path $envPath -Name "N8N_PROTOCOL" -Value "https"
Set-Or-AppendEnvVar -Path $envPath -Name "WEBHOOK_URL" -Value ("https://{0}/" -f $Hostname)
Set-Or-AppendEnvVar -Path $envPath -Name "CLOUDFLARE_TUNNEL_TOKEN" -Value $token

Write-Host ""
Write-Host "Named tunnel bootstrap complete."
Write-Host "Updated env file: $envPath"
Write-Host "Next step:"
Write-Host "  docker compose -f docker-compose.n8n.production.yml up -d"
