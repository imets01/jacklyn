#!/usr/bin/env bash
# Run backend (uvicorn --reload, :8000) and frontend (vite, :5173) together.
set -euo pipefail
cd "$(dirname "$0")/.."
[ -d backend/.venv ] && [ -d frontend/node_modules ] || scripts/setup.sh

trap 'kill 0' EXIT INT TERM
(cd backend && .venv/bin/uvicorn app.main:app --reload --port "${JACKLYN_API_PORT:-8000}") &
(cd frontend && npm run dev -- --port "${JACKLYN_WEB_PORT:-5173}") &
wait
