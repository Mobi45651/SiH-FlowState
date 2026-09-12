# FlowState SIH demo setup for Windows PowerShell
# Run this from the project root after extracting the ZIP.

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"

Write-Host "=== FlowState SIH setup ===" -ForegroundColor Cyan

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    throw "Python is not installed or not on PATH."
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    throw "Node.js is not installed or not on PATH. Install Node.js LTS first."
}

Set-Location $Backend

if (-not (Test-Path ".\venv\Scripts\python.exe")) {
    Write-Host "Creating Python virtual environment..." -ForegroundColor Yellow
    python -m venv venv
}

Write-Host "Activating backend virtual environment..." -ForegroundColor Yellow
& ".\venv\Scripts\Activate.ps1"

Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if (-not (Test-Path ".\.env")) {
    Copy-Item ".\.env.example" ".\.env"
}

Write-Host "Initializing database..." -ForegroundColor Yellow
python -m flask --app app init-db

Write-Host "Seeding demo database..." -ForegroundColor Yellow
python -m flask --app app seed-db

Write-Host ""
Write-Host "Backend setup complete." -ForegroundColor Green
Write-Host "The trained demo model is already included."
Write-Host ""
Write-Host "Start backend in this terminal:" -ForegroundColor Cyan
Write-Host "  python app.py"
Write-Host ""
Write-Host "Then open a NEW PowerShell terminal and run:" -ForegroundColor Cyan
Write-Host "  cd `"$Frontend`""
Write-Host "  npm install"
Write-Host "  npm run dev"
Write-Host ""
Write-Host "Dashboard: http://localhost:5173"
Write-Host "Backend:   http://localhost:5000/api/health"
