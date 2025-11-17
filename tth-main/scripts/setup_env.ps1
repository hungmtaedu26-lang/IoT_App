param(
    [string]$EnvName = "venv"
)

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Join-Path $root ".."
$venvPath = Join-Path $projectRoot $EnvName

if (-Not (Test-Path $venvPath)) {
    Write-Host "[setup] Creating virtual environment at $venvPath"
    python -m venv $venvPath
}

$activate = Join-Path $venvPath "Scripts/Activate.ps1"
if (-Not (Test-Path $activate)) {
    throw "Activation script not found at $activate. Check Python installation."
}

Write-Host "[setup] Ensuring pip is available"
& "$venvPath\Scripts\python.exe" -m ensurepip

Write-Host "[setup] Upgrading pip"
& "$venvPath\Scripts\python.exe" -m pip install --upgrade pip

Write-Host "[setup] Installing project requirements"
& "$venvPath\Scripts\pip.exe" install -r (Join-Path $projectRoot "requirements.txt")

Write-Host "[setup] Virtual environment ready. Activate with:`n`t$activate"
