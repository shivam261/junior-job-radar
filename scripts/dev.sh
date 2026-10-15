#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
if [[ ! -x "$PROJECT_ROOT/.venv/bin/python" ]]; then
  echo "Run the setup commands in README.md first." >&2
  exit 1
fi
cleanup() {
  kill "$API_PID" "$WEB_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
(cd "$PROJECT_ROOT/backend" && "$PROJECT_ROOT/.venv/bin/python" -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
API_PID=$!
(cd "$PROJECT_ROOT/frontend" && npm run dev) &
WEB_PID=$!
echo "Launchpad: http://127.0.0.1:5173 | API docs: http://127.0.0.1:8000/docs"
wait "$API_PID" "$WEB_PID"
