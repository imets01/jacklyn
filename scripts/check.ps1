# Everything CI should run: lint, strict type checks, tests, production build.
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot

function Step($name, [scriptblock]$block) {
    Write-Host "==> $name" -ForegroundColor Green
    & $block
    if ($LASTEXITCODE -ne 0) { throw "$name failed" }
}

Push-Location (Join-Path $root 'backend')
try {
    $bin = '.\.venv\Scripts'
    Step 'ruff' { & "$bin\ruff.exe" check app tests }
    Step 'ruff format --check' { & "$bin\ruff.exe" format --check app tests }
    Step 'mypy --strict' { & "$bin\mypy.exe" }
    Step 'pytest' { & "$bin\python.exe" -m pytest -q }
}
finally { Pop-Location }

Push-Location (Join-Path $root 'frontend')
try {
    Step 'oxlint' { npm run lint }
    Step 'tsc + vite build' { npm run build }
}
finally { Pop-Location }

Write-Host 'All checks passed.' -ForegroundColor Green
