#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export SOMA_SENSOR_PROVIDER=linux
export SOMA_LLM_MODE=off
export SOMA_VOLITION=1
export SOMA_COGNITIVE_TRACE=1
export SOMA_DISCOVERY=0
export SOMA_CAPABILITY_LEARNING=0
export SOMA_SHELL_EXEC=0
export SOMA_SELF_MODIFY=0
export SOMA_CNS_PULSE=0
export SOMA_SPONTANEOUS_SPEECH_COOLDOWN_SEC=90
export SOMA_REFLECTION_INTERVAL_SEC=120

echo "[SOMA] Starting: real Linux provider, LLM off, volition on, all agentic features off"
python3 server.py
