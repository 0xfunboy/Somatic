#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${HOST:-127.0.0.1}"
WS_PORT="${WS_PORT:-8765}"
UI_PORT="${UI_PORT:-8080}"

export SOMA_SENSOR_PROVIDER="${SOMA_SENSOR_PROVIDER:-linux}"
export SOMA_LLM_MODE="${SOMA_LLM_MODE:-deepseek}"
export DEEPSEEK_API_URL="${DEEPSEEK_API_URL:-http://127.0.0.1:4000}"
export MEDIUM_DEEPSEEK_MODEL="${MEDIUM_DEEPSEEK_MODEL:-gemini-web}"
export DEEPSEEK_API_KEY="${DEEPSEEK_API_KEY:-${OPENAI_API_KEY:-}}"

cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then kill "${SERVER_PID}" 2>/dev/null || true; fi
  if [[ -n "${UI_PID:-}" ]]; then kill "${UI_PID}" 2>/dev/null || true; fi
}
trap cleanup EXIT INT TERM

echo "[prod] root=${ROOT_DIR}"
echo "[prod] provider=${SOMA_SENSOR_PROVIDER} llm=${SOMA_LLM_MODE} ws=${HOST}:${WS_PORT} ui=${HOST}:${UI_PORT}"

python3 "${ROOT_DIR}/server.py" --host "${HOST}" --port "${WS_PORT}" &
SERVER_PID=$!

(
  cd "${ROOT_DIR}/docs"
  python3 -m http.server "${UI_PORT}" --bind "${HOST}"
) &
UI_PID=$!

echo "[prod] open http://127.0.0.1:${UI_PORT}/simulator.html?ws_port=${WS_PORT}"
wait -n "${SERVER_PID}" "${UI_PID}"
