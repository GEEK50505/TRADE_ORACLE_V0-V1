$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$logPath = Join-Path $PSScriptRoot "push_watch.log"

function Write-Log {
    param([string]$Message)
    "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message |
        Out-File -FilePath $logPath -Encoding utf8 -Append
}

Set-Location $repoRoot
Write-Log "watcher started"

while ($true) {
    $procs = Get-Process -ErrorAction SilentlyContinue |
        Where-Object { $_.ProcessName -match '^(git|git-lfs|sh)$' } |
        Sort-Object ProcessName, Id

    if ($procs) {
        Write-Log "active processes:"
        foreach ($proc in $procs) {
            Write-Log ("  {0} pid={1} cpu={2}" -f $proc.ProcessName, $proc.Id, $proc.CPU)
        }
        Start-Sleep -Seconds 20
        continue
    }

    Write-Log "no git/git-lfs/sh processes found; checking remote tip"
    $tip = & git `
        -c credential.username=GEEK50505 `
        -c credential.interactive=false `
        -c credential.guiPrompt=false `
        -c http.proxy= `
        -c https.proxy= `
        ls-remote origin refs/heads/main 2>&1
    foreach ($line in $tip) {
        Write-Log $line
    }
    Write-Log "watcher finished"
    break
}
