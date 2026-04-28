# Runtime Modes

## Default Safe Mode

```bash
SOMA_SENSOR_PROVIDER=mock \
SOMA_LLM_MODE=off \
python3 server.py
```

Use this when you want the demo to run on any Linux machine with no extra services.

Operator pages once the backend is up:

- `http://127.0.0.1:8080/simulator.html`
- `http://127.0.0.1:8080/tests.html`

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
- the operator test console can still run the curated validation suites

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

## Preferred Operator Flow

If you want the web frontend and runtime lifecycle handled by the repo scripts:

```bash
bash scripts/run.sh
```

Then open:

- `docs/simulator.html` for the embodied runtime view
- `docs/tests.html` for curated smoke / validation suites with readable step results

Stop with:

```bash
bash scripts/stop.sh
```

The test console does not expose every raw script in `scripts/`. It groups the meaningful ones into curated suites and runs them through the live WebSocket runtime.

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
