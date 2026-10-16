#!/usr/bin/env bash
# One-time local setup (macOS / Linux / WSL): Python 3.12 venv + backend deps, frontend deps.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"

echo "==> Backend (Python 3.12 venv)"
cd "$root/backend"
if [ ! -d .venv ]; then
  "$(command -v python3.12 || command -v python3)" -m venv .venv
fi
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt

echo "==> Frontend (npm ci)"
cd "$root/frontend"
npm ci

if [ ! -f "$root/.env" ]; then
  cp "$root/.env.example" "$root/.env"
  echo "Created .env from .env.example"
fi
echo "Done. Start everything with: ./scripts/dev.sh"
