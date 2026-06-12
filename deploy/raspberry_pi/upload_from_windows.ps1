param(
    [string]$PiUser = "pi",
    [string]$PiHost = "raspberrypi.local",
    [string]$PiPath = "~/RTIPVD"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $repoRoot

$itemsToCopy = @(
    "main.py",
    "requirements.txt",
    ".env.example",
    "config",
    "src",
    "scripts",
    "dashboard",
    "deploy/raspberry_pi",
    "weights",
    "data"
)

ssh "$PiUser@$PiHost" "mkdir -p $PiPath"

foreach ($item in $itemsToCopy) {
    if (Test-Path $item) {
        Write-Host "Uploading $item ..."
        scp -r $item "$PiUser@$PiHost`:$PiPath/"
    }
}

Write-Host "Upload complete. SSH into Pi and run:"
Write-Host "cd $PiPath"
Write-Host "bash deploy/raspberry_pi/setup.sh"
Write-Host "bash deploy/raspberry_pi/run_pi.sh"
Write-Host "# OR for new network mode: bash deploy/raspberry_pi/send_stream.sh"
