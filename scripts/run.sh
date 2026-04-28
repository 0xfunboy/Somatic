#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/funboy/latent-somatic"
DOCS="$ROOT/docs"
LOGS="$ROOT/logs"
ENV_FILE="$ROOT/.env"

WS_PORT="${SOMA_WS_PORT:-8765}"
HTTP_PORT="${SOMA_HTTP_PORT:-8080}"

mkdir -p "$LOGS"

echo "[SOMA] root: $ROOT"

if [ ! -f "$ENV_FILE" ]; then
  echo "[SOMA] WARN: missing .env at $ENV_FILE, using current environment only"
fi

echo "[SOMA] stopping old instances..."
pkill -f "python3 server.py" 2>/dev/null || true
pkill -f "python3 -m http.server ${HTTP_PORT}" 2>/dev/null || true
sleep 1

echo "[SOMA] starting backend websocket on :$WS_PORT..."
cd "$ROOT"

nohup bash -lc "
  cd '$ROOT'
  if [ -f '$ENV_FILE' ]; then
    set -a
    source '$ENV_FILE'
    set +a
  fi
  python3 server.py
" > "$LOGS/soma-ws.log" 2>&1 &

WS_PID=$!
echo "$WS_PID" > "$LOGS/soma-ws.pid"

echo "[SOMA] waiting for backend..."
for i in $(seq 1 20); do
  if ss -ltn | grep -q ":${WS_PORT} "; then
    echo "[SOMA] backend online"
    break
  fi

  if ! kill -0 "$WS_PID" 2>/dev/null; then
    echo "[SOMA] ERROR: backend died during startup"
    echo "[SOMA] last backend log:"
    tail -80 "$LOGS/soma-ws.log" || true
    exit 1
  fi

  sleep 1
done

if ! ss -ltn | grep -q ":${WS_PORT} "; then
  echo "[SOMA] ERROR: backend did not bind port $WS_PORT"
  echo "[SOMA] last backend log:"
  tail -80 "$LOGS/soma-ws.log" || true
  exit 1
fi

echo "[SOMA] starting frontend HTTP on :$HTTP_PORT..."
cd "$DOCS"

nohup python3 -m http.server "$HTTP_PORT" --bind 0.0.0.0 \
  > "$LOGS/soma-http.log" 2>&1 &

HTTP_PID=$!
echo "$HTTP_PID" > "$LOGS/soma-http.pid"

sleep 1

if ! ss -ltn | grep -q ":${HTTP_PORT} "; then
  echo "[SOMA] ERROR: frontend did not bind port $HTTP_PORT"
  echo "[SOMA] last frontend log:"
  tail -80 "$LOGS/soma-http.log" || true
  exit 1
fi

echo
echo "[SOMA] READY"
echo "backend websocket: ws://127.0.0.1:$WS_PORT"
echo "frontend:          http://127.0.0.1:$HTTP_PORT/simulator.html"
echo
echo "logs:"
echo "tail -f $LOGS/soma-ws.log"
echo "tail -f $LOGS/soma-http.log"
echo
echo "ports:"
ss -ltnp | grep -E ":(${WS_PORT}|${HTTP_PORT})" || true
