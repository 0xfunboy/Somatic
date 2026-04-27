#!/usr/bin/env bash
set -euo pipefail

echo "[SOMA] stopping backend/frontend..."
pkill -f "python3 server.py" 2>/dev/null || true
pkill -f "python3 -m http.server 8080" 2>/dev/null || true

echo "[SOMA] stopped"