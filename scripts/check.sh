#!/usr/bin/env bash
# Everything CI should run: lint, types, tests, production build.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "→ backend: ruff";   backend/.venv/bin/ruff check backend && backend/.venv/bin/ruff format --check backend
echo "→ backend: mypy";   (cd backend && .venv/bin/mypy app tests)
echo "→ backend: pytest"; (cd backend && .venv/bin/python -m pytest -q)
echo "→ frontend: tsc + vite build"; (cd frontend && npm run build)
echo "✓ all checks passed"
