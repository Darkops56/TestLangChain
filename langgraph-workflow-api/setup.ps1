$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

Write-Host "Creating virtual environment..." -ForegroundColor Green
python -m venv "$ProjectRoot\.venv"

Write-Host "Installing dependencies..." -ForegroundColor Green
& "$ProjectRoot\.venv\Scripts\pip" install -r "$ProjectRoot\requirements.txt"

Write-Host "Starting server..." -ForegroundColor Green
& "$ProjectRoot\.venv\Scripts\uvicorn" app.main:app --reload --host 0.0.0.0 --port 8000
