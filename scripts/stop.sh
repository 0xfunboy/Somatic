#!/usr/bin/env bash
set -euo pipefail

echo "[SOMA] stopping backend/frontend..."
WS_PORT="${SOMA_WS_PORT:-8765}"
HTTP_PORT="${SOMA_HTTP_PORT:-8080}"
pkill -f "python3 server.py" 2>/dev/null || true
pkill -f "python3 -m http.server ${HTTP_PORT}" 2>/dev/null || true

echo "[SOMA] stopped"
