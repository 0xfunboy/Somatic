# Runtime Modes

## Default Safe Mode

```bash
SOMA_SENSOR_PROVIDER=mock \
SOMA_LLM_MODE=off \
python3 server.py
```

Use this when you want the demo to run on any Linux machine with no extra services.

## Real Linux Telemetry, No External LLM

```bash
SOMA_SENSOR_PROVIDER=linux \
SOMA_LLM_MODE=off \
python3 server.py
```

Expected:

- real CPU / memory telemetry
- partial thermal / battery / fan telemetry when available
- browser stays usable if some fields are missing

## OpenAI-Compatible Endpoint

```bash
SOMA_SENSOR_PROVIDER=linux \
SOMA_LLM_MODE=openai_compatible \
SOMA_LLM_ENDPOINT=http://127.0.0.1:8081/v1/chat/completions \
SOMA_LLM_MODEL=local \
python3 server.py
```

Use this with:

- local `llama.cpp` server
- Ollama-compatible bridges
- LM Studio
- any OpenAI-style `/v1/chat/completions` endpoint

Alias support:

- `OPENAI_API_URL`
- `OPENAI_API_KEY`
- `MEDIUM_OPENAI_MODEL`

## DeepSeek Endpoint

```bash
SOMA_SENSOR_PROVIDER=linux \
SOMA_LLM_MODE=deepseek \
SOMA_DEEPSEEK_API_KEY=your_key \
SOMA_DEEPSEEK_MODEL=deepseek-v4-flash \
python3 server.py
```

Optional overrides:

```bash
SOMA_DEEPSEEK_ENDPOINT=https://api.deepseek.com/chat/completions
SOMA_LLM_TIMEOUT_SEC=30
```

Alias support:

- `DEEPSEEK_API_URL`
- `DEEPSEEK_API_KEY`
- `MEDIUM_DEEPSEEK_MODEL`

If you pass a base URL such as `http://127.0.0.1:4000`, the runtime will expand it automatically to `/chat/completions`.

## Autonomy Controls

```bash
SOMA_AUTONOMY=1
SOMA_AUTONOMY_COOLDOWN_SEC=20
SOMA_TICK_HZ=2
```

Defaults are chosen to keep the prototype stable on normal machines.

## NVIDIA Telemetry Toggle

```bash
SOMA_ENABLE_NVIDIA=1
```

If disabled, the Linux provider will skip `nvidia-smi`.

## Future C++ Mode

Planned direction:

```bash
./build/soma_daemon --model models/model.gguf --frontend docs
```

This is not implemented yet, but the frontend protocol should stay compatible with it.
