param(
    [switch]$SkipInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"

function Resolve-BackendVenvDir {
    param([string]$BackendDir)
    $ordered = @(
        (Join-Path $BackendDir "venv"),
        (Join-Path $BackendDir ".venv")
    )
    foreach ($dir in $ordered) {
        $py = Join-Path $dir "Scripts\python.exe"
        if (Test-Path $py) {
            return $dir
        }
    }
    return (Join-Path $BackendDir ".venv")
}

$venvDir = Resolve-BackendVenvDir -BackendDir $backendDir
$venvPython = Join-Path $venvDir "Scripts\python.exe"
$venvActivate = Join-Path $venvDir "Scripts\Activate.ps1"

function Test-VenvHasPip {
    param(
        [string]$PythonPath
    )

    if (-not (Test-Path $PythonPath)) {
        return $false
    }

    try {
        & $PythonPath -m pip --version *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

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

if ((-not (Test-Path $venvPython)) -or (-not (Test-VenvHasPip -PythonPath $venvPython))) {
    if (Test-Path $venvDir) {
        Write-Host "Rebuilding backend virtual environment because the existing one is incomplete..."
        & python -m venv --clear $venvDir
    }
    else {
        Write-Host "Creating backend virtual environment..."
        & python -m venv $venvDir
    }
}

if (-not (Test-VenvHasPip -PythonPath $venvPython)) {
    Write-Host "Bootstrapping pip in the backend virtual environment..."
    & $venvPython -m ensurepip --upgrade
}

if (-not (Test-VenvHasPip -PythonPath $venvPython)) {
    throw "Backend virtual environment is missing pip. Remove backend\venv or backend\.venv and rerun .\start.ps1."
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
& '$venvPython' -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010
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
Write-Host " - Backend: http://127.0.0.1:8010"
Write-Host " - Frontend: http://127.0.0.1:5173"
Write-Host ""
Write-Host "Tip: if dependencies are already installed, use .\start.ps1 -SkipInstall for faster startup."
Write-Host "Manual backend activation (optional): & '$venvActivate'"
