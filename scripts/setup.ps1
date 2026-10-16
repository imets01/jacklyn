# One-time local setup on Windows: Python 3.12 venv + backend deps, frontend deps.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

Write-Host '==> Backend (Python 3.12 venv)' -ForegroundColor Green
Push-Location (Join-Path $root 'backend')
try {
    if (-not (Test-Path '.venv')) {
        if (Get-Command py -ErrorAction SilentlyContinue) { py -3.12 -m venv .venv }
        else { python -m venv .venv }
    }
    & .\.venv\Scripts\python.exe -m pip install --upgrade pip
    & .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
}
finally { Pop-Location }

Write-Host '==> Frontend (npm ci)' -ForegroundColor Green
Push-Location (Join-Path $root 'frontend')
try { npm ci }
finally { Pop-Location }

if (-not (Test-Path (Join-Path $root '.env'))) {
    Copy-Item (Join-Path $root '.env.example') (Join-Path $root '.env')
    Write-Host 'Created .env from .env.example'
}
Write-Host 'Done. Start everything with: .\scripts\dev.ps1' -ForegroundColor Green
