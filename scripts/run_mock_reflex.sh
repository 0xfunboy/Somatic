#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export SOMA_SENSOR_PROVIDER=mock
export SOMA_LLM_MODE=off
export SOMA_VOLITION=1
export SOMA_COGNITIVE_TRACE=1
export SOMA_DISCOVERY=0
export SOMA_CAPABILITY_LEARNING=0
export SOMA_SHELL_EXEC=0
export SOMA_SELF_MODIFY=0
export SOMA_CNS_PULSE=0

echo "[SOMA] Starting: mock provider, LLM off, volition on"
python3 server.py
