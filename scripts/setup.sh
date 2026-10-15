#!/usr/bin/env bash
# One-time local setup: Python venv + backend deps, frontend node_modules.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-$(command -v python3.12 || command -v python3)}"
echo "→ backend venv ($("$PYTHON" --version))"
[ -d backend/.venv ] || "$PYTHON" -m venv backend/.venv
backend/.venv/bin/pip install -q --upgrade pip
backend/.venv/bin/pip install -q -r backend/requirements-dev.txt

echo "→ frontend deps"
(cd frontend && npm install --no-fund --no-audit)
echo "✓ setup complete — run scripts/dev.sh"
