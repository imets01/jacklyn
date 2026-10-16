# Run the API (auto-reload, :8000) and the UI (Vite HMR, :5173) together. Ctrl+C stops both.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root 'backend\.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Backend venv missing - run .\scripts\setup.ps1 first.' }

$api = Start-Process -FilePath $python `
    -ArgumentList '-m', 'uvicorn', 'app.main:app', '--reload', '--port', '8000' `
    -WorkingDirectory (Join-Path $root 'backend') -NoNewWindow -PassThru

try {
    Write-Host 'API  -> http://localhost:8000/docs' -ForegroundColor Green
    Write-Host 'UI   -> http://localhost:5173' -ForegroundColor Green
    Push-Location (Join-Path $root 'frontend')
    npm run dev
}
finally {
    Pop-Location
    if (-not $api.HasExited) {
        # uvicorn --reload spawns a worker; stop the whole tree.
        taskkill /PID $api.Id /T /F | Out-Null
    }
}
