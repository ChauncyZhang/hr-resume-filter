#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

: "${HR_RESUME_HOST:=127.0.0.1}"
: "${HR_RESUME_PORT:=8765}"

exec "${PYTHON_BIN:-python3}" web_app.py --host "$HR_RESUME_HOST" --port "$HR_RESUME_PORT" --no-browser
