param(
    [Alias("Host")]
    [string]$ListenHost = "0.0.0.0",
    [int]$Port = 8088,
    [string]$ModelPath = "weights/best.pt",
    [string]$Device = "cpu",
    [string]$TrackerConfig = "config/bytetrack.yaml",
    [double]$InputFps = 8.0,
    [string]$DbPath = "output/db/rtipvd_laptop.db",
    [switch]$DisableDb,
    [switch]$DisableParking,
    [switch]$ShowDisplay,
    [switch]$UseMockOcr,
    [switch]$DisableZone,
    [string]$ZoneGeoJson = "data/geofencing/No_Parking_Zones.geojson",
    [switch]$EnableBackend,
    [string]$BackendUrl = "http://127.0.0.1:5000/api/violations",
    [string]$BackendApiKey = "",
    [switch]$BackendSkipSslVerify
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

$venvVersion = python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($venvVersion -ne "3.11") {
    Write-Warning "Current .venv uses Python $venvVersion. Recommended version is 3.11 for stable NumPy/PyTorch behavior."
    Write-Warning "If you see runtime issues, recreate .venv with: py -3.11 -m venv .venv"
}

python -m pip install --upgrade pip
pip install -r requirements.txt

$pythonArgs = @(
    "scripts/laptop_stream_server.py",
    "--host", $ListenHost,
    "--port", "$Port",
    "--model", $ModelPath,
    "--device", $Device,
    "--tracker-config", $TrackerConfig,
    "--input-fps", "$InputFps",
    "--db-path", $DbPath,
    "--zone-geojson", $ZoneGeoJson
)

if ($DisableDb) {
    $pythonArgs += "--disable-db"
}

if ($DisableParking) {
    $pythonArgs += "--disable-parking"
} else {
    $pythonArgs += "--enable-parking"
}

if ($ShowDisplay) {
    $pythonArgs += "--show-display"
}

if ($UseMockOcr) {
    $pythonArgs += "--use-mock-ocr"
}

if ($DisableZone) {
    $pythonArgs += "--zone-disabled"
} else {
    $pythonArgs += "--zone-enabled"
}

if ($EnableBackend) {
    $pythonArgs += "--backend-enabled"
    $pythonArgs += @("--backend-url", $BackendUrl)
}

if ($BackendApiKey) {
    $pythonArgs += @("--backend-api-key", $BackendApiKey)
}

if ($BackendSkipSslVerify) {
    $pythonArgs += "--backend-skip-ssl-verify"
}

python @pythonArgs
