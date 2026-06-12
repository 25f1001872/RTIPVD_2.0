param(
    [string]$VideoPath = "data/videos/d1.mp4",
    [switch]$UseMockOcr = $false
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
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121
pip install -r requirements.txt

if (-not (Test-Path "data/videos")) {
    New-Item -ItemType Directory -Path "data/videos" | Out-Null
}

if (-not (Test-Path "weights/best.pt")) {
    Write-Warning "weights/best.pt is missing. Copy your trained model before running."
}

if (-not (Test-Path $VideoPath)) {
    Write-Warning "Video file not found at $VideoPath"
} else {
    $resolvedVideo = (Resolve-Path $VideoPath).Path
    $env:RTIPVD_VIDEO_SOURCE = $resolvedVideo
}

$env:RTIPVD_DEVICE = "cuda:0"
$env:RTIPVD_DB_ENABLED = "true"
$env:RTIPVD_DB_PATH = "output/db/rtipvd_laptop.db"
$env:RTIPVD_GPS_ENABLED = "true"
$env:RTIPVD_GPS_SOURCE = "mock"
$env:RTIPVD_BACKEND_ENABLED = "false"
$env:RTIPVD_OCR_USE_GPU = "true"
$env:RTIPVD_SHOW_DISPLAY = "true"

if ($UseMockOcr) {
    $env:RTIPVD_USE_MOCK_OCR = "true"
} else {
    $env:RTIPVD_USE_MOCK_OCR = "false"
}

python main.py
