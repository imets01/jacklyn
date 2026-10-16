#!/usr/bin/env bash
# Everything CI should run: lint, strict type checks, tests, production build.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
bin="$root/backend/.venv/bin"
[ -d "$bin" ] || bin="$root/backend/.venv/Scripts"

cd "$root/backend"
echo "==> ruff";        "$bin/ruff" check app tests
echo "==> ruff format"; "$bin/ruff" format --check app tests
echo "==> mypy";        "$bin/mypy"
echo "==> pytest";      "$bin/python" -m pytest -q

cd "$root/frontend"
echo "==> oxlint";      npm run lint
echo "==> build";       npm run build
echo "All checks passed."
