f#!/usr/bin/env bash
# One command for the whole Nucleus dev stack:
#   backend  → http://localhost:8800  (uvicorn, auto-reload)
#   frontend → http://localhost:3000  (vite, proxies API calls to :8800)
# Ctrl-C stops both.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

source "$ROOT/venv/bin/activate"

# Take the whole stack down together — uvicorn's reloader and vite both live
# in this script's process group.
trap 'kill 0' EXIT

(cd "$ROOT" && PYTHONPATH=. python3 backend/main.py) &
(cd "$ROOT/frontend" && npm run dev) &
wait
