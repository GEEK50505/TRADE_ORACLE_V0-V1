# Enable shell integration for TRADE_ORACLE
# This script appends a small snippet to the user's PowerShell profile
# which attempts to auto-activate a `.venv` located in the current
# directory (or any parent directory) when a shell starts in the repo.

$profilePath = $PROFILE
if (-not $profilePath) {
    Write-Error "Cannot determine PowerShell profile path."
    exit 1
}

$marker = "# TRADE_ORACLE auto-activate venv"

# Ensure profile directory exists
$profileDir = Split-Path -Parent $profilePath
if (-not (Test-Path $profileDir)) {
    New-Item -ItemType Directory -Path $profileDir -Force | Out-Null
}

# Backup existing profile if present
$backup = "$profilePath.bak.$((Get-Date).ToString('yyyyMMddHHmmss'))"
if (Test-Path $profilePath) {
    Copy-Item -Path $profilePath -Destination $backup -Force
}

# Do not duplicate the snippet
$already = $false
if (Test-Path $profilePath) {
    try {
        $already = Select-String -Path $profilePath -Pattern $marker -Quiet
    } catch {
        $already = $false
    }
}

if ($already) {
    Write-Output "TRADE_ORACLE snippet already present in profile: $profilePath"
    Write-Output "No changes made. Backup: $backup"
    exit 0
}

$snippet = @'
# TRADE_ORACLE auto-activate venv
function Invoke-TradeOracleAutoActivate {
    $cur = (Get-Location).Path
    while ($cur -and ($cur -ne [System.IO.Path]::GetPathRoot($cur))) {
        $venv = Join-Path $cur '.venv\Scripts\Activate.ps1'
        if (Test-Path $venv) {
            try {
                . $venv
                return
            } catch {
                Write-Verbose "Failed to activate venv: $_"
            }
        }
        $cur = Split-Path $cur -Parent
    }
}
try { Invoke-TradeOracleAutoActivate } catch {}
# End TRADE_ORACLE auto-activate venv
'@

# Append snippet to profile
Add-Content -Path $profilePath -Value $snippet
Write-Output "Appended TRADE_ORACLE shell integration to: $profilePath"
if (Test-Path $backup) { Write-Output "Backup of previous profile: $backup" }
Write-Output "To apply immediately, start a new PowerShell session in your workspace or run: . $profilePath"
