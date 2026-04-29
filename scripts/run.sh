#!/usr/bin/env bash
set -euo pipefail

ROOT="/home/funboy/latent-somatic"
DOCS="$ROOT/docs"
LOGS="$ROOT/logs"
ENV_FILE="$ROOT/.env"

WS_PORT="${SOMA_WS_PORT:-8765}"
HTTP_PORT="${SOMA_HTTP_PORT:-8080}"

MODE="safe"
NO_BIOS=0

while (($#)); do
  case "$1" in
    --safe)
      MODE="safe"
      ;;
    --low-power)
      MODE="low-power"
      ;;
    --debug)
      MODE="debug"
      ;;
    --no-bios)
      NO_BIOS=1
      ;;
    *)
      echo "[SOMA] unknown option: $1" >&2
      exit 1
      ;;
  esac
  shift
done

mkdir -p "$LOGS"

echo "[SOMA] root: $ROOT"
echo "[SOMA] mode: $MODE${NO_BIOS:+}$( [ "$NO_BIOS" -eq 1 ] && printf ' + no-bios' || true )"

if [ ! -f "$ENV_FILE" ]; then
  echo "[SOMA] WARN: missing .env at $ENV_FILE, using current environment only"
fi

echo "[SOMA] stopping old instances..."
pkill -f "python3 server.py" 2>/dev/null || true
pkill -f "python3 -m http.server ${HTTP_PORT}" 2>/dev/null || true
sleep 1

export SOMA_RUN_MODE="$MODE"
export SOMA_RUN_NO_BIOS="$NO_BIOS"

echo "[SOMA] starting backend websocket on :$WS_PORT..."
cd "$ROOT"

nohup bash -lc "
  cd '$ROOT'
  if [ -f '$ENV_FILE' ]; then
    set -a
    source '$ENV_FILE'
    set +a
  fi

  export SOMA_RESOURCE_GOVERNOR=\${SOMA_RESOURCE_GOVERNOR:-1}
  export SOMA_SENSOR_PROVIDER=\${SOMA_SENSOR_PROVIDER:-linux}
  export SOMA_LLM_MODE=\${SOMA_LLM_MODE:-off}
  export SOMA_VOLITION=\${SOMA_VOLITION:-1}
  export SOMA_COGNITIVE_TRACE=\${SOMA_COGNITIVE_TRACE:-1}
  export SOMA_TICK_HZ=\${SOMA_TICK_HZ:-1}
  export SOMA_TICK_HZ_MAX_NORMAL=\${SOMA_TICK_HZ_MAX_NORMAL:-2}
  export SOMA_TICK_HZ_MAX_REDUCED=\${SOMA_TICK_HZ_MAX_REDUCED:-1}
  export SOMA_TICK_HZ_MAX_CRITICAL=\${SOMA_TICK_HZ_MAX_CRITICAL:-0.5}
  export SOMA_TICK_HZ_MAX_RECOVERY=\${SOMA_TICK_HZ_MAX_RECOVERY:-0.2}
  export SOMA_UI_FULL_PAYLOAD_HZ=\${SOMA_UI_FULL_PAYLOAD_HZ:-0.5}
  export SOMA_UI_LIGHT_TICK_HZ=\${SOMA_UI_LIGHT_TICK_HZ:-1}
  export SOMA_UI_MAX_BROADCAST_BYTES_PER_SEC=\${SOMA_UI_MAX_BROADCAST_BYTES_PER_SEC:-250000}
  export SOMA_PROJECTOR_HZ_NORMAL=\${SOMA_PROJECTOR_HZ_NORMAL:-0.5}
  export SOMA_PROJECTOR_HZ_REDUCED=\${SOMA_PROJECTOR_HZ_REDUCED:-0.2}
  export SOMA_PROJECTOR_HZ_CRITICAL=\${SOMA_PROJECTOR_HZ_CRITICAL:-0.05}
  export SOMA_VECTOR_INTERPRETER_HZ=\${SOMA_VECTOR_INTERPRETER_HZ:-0.2}
  export SOMA_CPP_PROJECTION_HZ=\${SOMA_CPP_PROJECTION_HZ:-0.02}
  export SOMA_CPP_SMOKE_TEST_INTERVAL_SEC=\${SOMA_CPP_SMOKE_TEST_INTERVAL_SEC:-3600}
  export SOMA_BIOS_INTERVAL_SEC=\${SOMA_BIOS_INTERVAL_SEC:-600}
  export SOMA_BIOS_INTERVAL_SEC_NORMAL=\${SOMA_BIOS_INTERVAL_SEC_NORMAL:-600}
  export SOMA_BIOS_INTERVAL_SEC_REDUCED=\${SOMA_BIOS_INTERVAL_SEC_REDUCED:-1800}
  export SOMA_BIOS_INTERVAL_SEC_CRITICAL=\${SOMA_BIOS_INTERVAL_SEC_CRITICAL:-3600}
  export SOMA_BIOS_INTERVAL_SEC_RECOVERY=\${SOMA_BIOS_INTERVAL_SEC_RECOVERY:-3600}
  export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=\${SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR:-4}
  export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_NORMAL=\${SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_NORMAL:-4}
  export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_REDUCED=\${SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_REDUCED:-1}
  export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_CRITICAL=\${SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_CRITICAL:-0}
  export SOMA_BIOS_YIELD_WHEN_USER_ACTIVE=\${SOMA_BIOS_YIELD_WHEN_USER_ACTIVE:-1}
  export SOMA_USER_ACTIVE_WINDOW_SEC=\${SOMA_USER_ACTIVE_WINDOW_SEC:-120}
  export SOMA_INTERNAL_LLM_MAX_PROMPT_CHARS=\${SOMA_INTERNAL_LLM_MAX_PROMPT_CHARS:-6000}
  export SOMA_INTERNAL_LLM_MAX_RESPONSE_CHARS=\${SOMA_INTERNAL_LLM_MAX_RESPONSE_CHARS:-4000}
  export SOMA_CNS_PULSE_ENABLED=\${SOMA_CNS_PULSE_ENABLED:-0}
  export SOMA_DISCOVERY=\${SOMA_DISCOVERY:-0}
  export SOMA_DISCOVERY_INTERVAL_SEC=\${SOMA_DISCOVERY_INTERVAL_SEC:-600}
  export SOMA_AUTO_COMPACT_MIND_STATE=\${SOMA_AUTO_COMPACT_MIND_STATE:-1}
  export SOMA_MIND_STATE_MAX_BYTES=\${SOMA_MIND_STATE_MAX_BYTES:-262144}

  case \"\${SOMA_RUN_MODE:-safe}\" in
    low-power)
      export SOMA_TICK_HZ=0.5
      export SOMA_TICK_HZ_MAX_NORMAL=1
      export SOMA_UI_FULL_PAYLOAD_HZ=0.2
      export SOMA_UI_LIGHT_TICK_HZ=0.5
      export SOMA_PROJECTOR_HZ_NORMAL=0.1
      export SOMA_BIOS_INTERVAL_SEC=1800
      export SOMA_BIOS_INTERVAL_SEC_NORMAL=1800
      export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=1
      export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_NORMAL=1
      export SOMA_DISCOVERY=0
      export SOMA_CNS_PULSE_ENABLED=0
      ;;
    debug)
      export SOMA_UI_LIGHT_TICK_HZ=\${SOMA_UI_LIGHT_TICK_HZ:-2}
      export SOMA_UI_FULL_PAYLOAD_HZ=\${SOMA_UI_FULL_PAYLOAD_HZ:-1}
      ;;
    safe)
      :
      ;;
  esac

  if [ \"\${SOMA_RUN_NO_BIOS:-0}\" = \"1\" ]; then
    export SOMA_BIOS_LOOP=0
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
