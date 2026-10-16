#!/usr/bin/env bash
# Run the API (auto-reload, :8000) and the UI (Vite HMR, :5173) together. Ctrl+C stops both.
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
python="$root/backend/.venv/bin/python"
[ -x "$python" ] || python="$root/backend/.venv/Scripts/python.exe"  # Git Bash on Windows
[ -x "$python" ] || { echo "Backend venv missing - run ./scripts/setup.sh first." >&2; exit 1; }

(cd "$root/backend" && exec "$python" -m uvicorn app.main:app --reload --port 8000) &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT INT TERM

echo "API  -> http://localhost:8000/docs"
echo "UI   -> http://localhost:5173"
cd "$root/frontend"
npm run dev
