param(
    [string]$VenvPath = ".venv-langgraph"
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvRoot = Join-Path $repoRoot $VenvPath
$venvPython = Join-Path $venvRoot "Scripts\\python.exe"
$requirementsPath = Join-Path $repoRoot "requirements.langgraph.txt"

Write-Host "TRADE_ORACLE LangGraph environment bootstrap"
Write-Host "Repository root: $repoRoot"
Write-Host "Virtual environment: $venvRoot"

if (-not (Test-Path -LiteralPath $venvRoot)) {
    Write-Host "Creating virtual environment..."
    python -m venv $venvRoot
} else {
    Write-Host "Virtual environment already exists."
}

if (-not (Test-Path -LiteralPath $venvPython)) {
    throw "LangGraph venv python was not created successfully: $venvPython"
}

Write-Host "Upgrading pip inside the LangGraph environment..."
python -m pip --python $venvPython install --upgrade pip

Write-Host "Installing LangGraph requirements from $requirementsPath ..."
python -m pip --python $venvPython install -r $requirementsPath

Write-Host ""
Write-Host "Bootstrap complete."
Write-Host "Activate with:"
Write-Host "  $venvRoot\\Scripts\\Activate.ps1"
Write-Host ""
Write-Host "Service command:"
Write-Host "  $venvPython -m uvicorn api.trade_oracle_mcp_service:app --host 127.0.0.1 --port 8000"
Write-Host ""
Write-Host "Graph demo command:"
Write-Host "  $venvPython -c `"from ai.trade_oracle_langgraph_phase1 import run_phase1_demo; first, final = run_phase1_demo(); print('__interrupt__' in first); print(final['final_decision'])`""
