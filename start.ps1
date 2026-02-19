param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$venvDir = Join-Path $backendDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $backendDir)) {
    throw "Backend directory does not exist: $backendDir"
}
if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory does not exist: $frontendDir"
}

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python was not found. Please install Python and add it to PATH."
}
if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) {
    throw "npm.cmd was not found. Please install Node.js."
}

if (-not (Test-Path $venvPython)) {
    Write-Host "Creating backend virtual environment..."
    & python -m venv $venvDir
}

if (-not $SkipInstall) {
    Write-Host "Installing backend dependencies..."
    & $venvPython -m pip install -r (Join-Path $backendDir "requirements.txt")

    Write-Host "Installing frontend dependencies..."
    Push-Location $frontendDir
    try {
        & npm.cmd install
    }
    finally {
        Pop-Location
    }
}

$backendCmd = @"
cd '$backendDir'
& '$venvPython' -m uvicorn app.main:app --reload --port 8000
"@

$frontendCmd = @"
cd '$frontendDir'
npm.cmd run dev
"@

Write-Host "Starting backend window..."
Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-Command", $backendCmd | Out-Null

Write-Host "Starting frontend window..."
Start-Process powershell -ArgumentList "-NoProfile", "-NoExit", "-Command", $frontendCmd | Out-Null

Write-Host "Started:"
Write-Host " - Backend: http://127.0.0.1:8000"
Write-Host " - Frontend: http://127.0.0.1:5173"
Write-Host ""
Write-Host "Tip: if dependencies are already installed, use .\start.ps1 -SkipInstall for faster startup."
