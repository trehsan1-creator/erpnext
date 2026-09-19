#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/project"
exec gunicorn ui.app:app \
  --worker-class uvicorn_worker.UvicornWorker \
  --workers 1 \
  --bind "0.0.0.0:${PORT:-8000}" \
  --timeout 180 \
  --access-logfile - \
  --error-logfile -
