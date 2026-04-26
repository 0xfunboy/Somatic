# Architecture

## Today

The repository currently has two runtime lines.

### 1. C++ latent-somatic core

Main files:

- `src/main.cpp`
- `src/hw_interface.cpp`
- `src/somatic_projector.cpp`
- `src/llm_bridge.cpp`
- `include/*.h`

This is the long-term direction. It already contains the core research path:

```text
physical state -> somatic projector -> latent vector -> llama.cpp embedding injection
```

### 2. Python orchestration prototype

Main files:

- `server.py`
- `sensor_providers/`
- `docs/simulator.html`

This layer exists to validate:

- browser interaction
- telemetry ingestion
- WebSocket protocol
- structured LLM replies
- affect + action output

It is intentionally backend-agnostic so it can be replaced later by a C++ daemon.

## Current Python Runtime

Current data flow:

```text
SensorProvider
  -> normalized sensor packet
  -> projector input (11 core values)
  -> TorchScript projector or fallback projector
  -> derived state + affect + actions
  -> optional LLM endpoint
  -> WebSocket payload
  -> browser UI
```

## Projector Input Contract

The projector input order is fixed:

```text
voltage
current_ma
temp_si
temp_ml
temp_mr
ax
ay
az
gx
gy
gz
```

This ordering must remain consistent across:

- Python prototype
- C++ runtime
- training pipeline

## Projector Modes

`server.py` supports two projector modes:

- `torchscript`: real `weights/somatic_projector.pt` or `weights/somatic_projector_scripted.pt`
- `fallback`: local synthetic projection if TorchScript is unavailable

This keeps the demo runnable even when the scripted projector is missing.

## LLM Modes

Current prototype modes:

- `off`
- `openai_compatible`
- `deepseek`

These modes are useful for validating UX and protocol, but they do not replace the real long-term architecture.

## Final Direction

Target runtime:

```text
Frontend Three.js / VRM
        ↓ WebSocket
C++ soma-daemon
        ↓
C++ sensor providers
        ↓
LibTorch somatic projector
        ↓
llama.cpp embedding injection
        ↓
JSON: speech + affect + actions
```

Important:

- use `/home/funboy/llama.cpp`
- do not clone another `llama.cpp`
- keep the frontend protocol stable while swapping backend implementations
