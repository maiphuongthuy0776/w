#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "[railway_start] python=$(command -v python || command -v python3)"
python -m pip install --no-cache-dir -r requirements.txt
python -m playwright install chromium || python -m playwright install --with-deps chromium || true
exec python bot.py
