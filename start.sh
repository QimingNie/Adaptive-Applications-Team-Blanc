#!/usr/bin/env bash
# Run from Git Bash / WSL / macOS/Linux. Starts backend (8010) and Vite frontend.
# PowerShell users: use .\start.ps1 instead (.\ does not work in bash).

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

pick_python() {
  if [[ -x "$BACKEND/venv/Scripts/python.exe" ]]; then
    echo "$BACKEND/venv/Scripts/python.exe"
  elif [[ -x "$BACKEND/.venv/Scripts/python.exe" ]]; then
    echo "$BACKEND/.venv/Scripts/python.exe"
  elif [[ -x "$BACKEND/venv/bin/python" ]]; then
    echo "$BACKEND/venv/bin/python"
  elif [[ -x "$BACKEND/.venv/bin/python" ]]; then
    echo "$BACKEND/.venv/bin/python"
  else
    echo ""
  fi
}

PY="$(pick_python)"
if [[ -z "$PY" ]]; then
  echo "No backend venv found. Create one, then install deps:"
  echo "  cd backend && python -m venv venv && venv/Scripts/python -m pip install -r requirements.txt"
  exit 1
fi

echo "Using: $PY"
echo "Backend: http://127.0.0.1:8010  |  Frontend: http://127.0.0.1:5173"
echo "Press Ctrl+C to stop both."

cleanup() {
  kill 0
}
trap cleanup EXIT INT TERM

(cd "$BACKEND" && "$PY" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8010) &
(cd "$FRONTEND" && npm run dev) &
wait
