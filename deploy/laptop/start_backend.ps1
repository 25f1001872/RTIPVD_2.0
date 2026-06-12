param(
    [string]$DbPath = "output/db/rtipvd_laptop.db",
    [string]$ApiKey = "",
    [int]$Port = 5000
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

if (-not (Test-Path ".venv")) {
    $venvCreated = $false

    if (Get-Command python -ErrorAction SilentlyContinue) {
        python -m venv .venv
        if (Test-Path ".venv\Scripts\Activate.ps1") {
            $venvCreated = $true
        }
    }

    if (-not $venvCreated -and (Get-Command py -ErrorAction SilentlyContinue)) {
        py -3.11 -m venv .venv
        if (Test-Path ".venv\Scripts\Activate.ps1") {
            $venvCreated = $true
        }
    }

    if (-not $venvCreated) {
        throw "Python 3.11+ was not found. Install Python and retry."
    }
}

if (-not (Test-Path ".venv\Scripts\Activate.ps1")) {
    throw "Virtual environment activation script not found at .venv\\Scripts\\Activate.ps1"
}

. .\.venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt
pip install -r dashboard/backend/requirements.txt

$env:RTIPVD_DB_ENABLED = "true"
$env:RTIPVD_DB_PATH = $DbPath
$env:RTIPVD_DASHBOARD_HOST = "0.0.0.0"
$env:RTIPVD_DASHBOARD_PORT = "$Port"
$env:RTIPVD_BACKEND_API_KEY = $ApiKey

python dashboard/backend/app.py
