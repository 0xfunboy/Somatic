# Development Todo

This file is the single source of truth for ongoing development work.

It replaces ad-hoc plan files, but it must not become a lossy summary.
If detail starts disappearing, expand this file instead of compressing it.

## Working Rules

- Keep this file updated in the same session in which code changes land.
- Mark completed items with `[x]` only after implementation plus at least one validation step.
- Keep reference docs such as `ARCHITECTURE.md`, `RUNTIME_MODES.md`, `SENSOR_PROVIDERS.md`, and `WEBSOCKET_PROTOCOL.md` aligned with the runtime.
- Keep the frontend payload backend-agnostic so the future C++ daemon can replace Python without rewriting the browser layer.
- Do not mistake browser fallback chat for backend cognition. `CNS LINK` and `CHAT CORE` must stay truthful.

## North Star

Target direction:

- A machine agent with explicit proprioception and interoception.
- Body state must influence language through vectors, not only through templated text.
- Short-term memory must preserve conversational continuity.
- Long-term memory must preserve episodic continuity across restarts.
- Homeostatic drives must shape behavior, not just decorate the UI.
- DeepSeek is the central language core, but not the whole organism.
- The Python runtime is still a staging ground; protocol and state design must remain portable to C++.

## Reality Check

Current architecture is still an early embodied runtime, not a full autonomous agent.

What is present already:

- Sensor provider abstraction.
- Somatic projector plus fallback projector.
- Derived affect and homeostatic signals.
- Structured actions and autonomous events.
- WebSocket protocol shared by backend and frontend.
- DeepSeek/OpenAI-compatible remote language core support.
- Persistent semantic and episodic memory on disk.

What is still missing for a stronger “synthetic life” direction:

- A trained multimodal fusion path instead of only analytic fusion.
- Explicit memory consolidation and retrieval ranking beyond lexical overlap.
- Goal persistence and policy selection beyond simple homeostatic heuristics.
- Richer hardware coverage on more machines and vendors.
- Closed-loop actuation beyond UI animation suggestions.
- A backend-portability freeze with fixtures before the C++ rewrite.

## Completed Baseline

### Repository and Runtime Structure

- [x] Extracted the Python runtime into `server.py` plus modular `sensor_providers/`.
- [x] Kept the frontend/backend split through a backend-agnostic WebSocket protocol.
- [x] Preserved projector fallback behavior so the demo still runs without TorchScript or PyTorch.
- [x] Switched docs and bootstrap guidance to reuse `/home/funboy/llama.cpp` instead of cloning another checkout.

### Provider Baseline

- [x] Normalized all providers around the fixed 11-field `core` contract consumed by the projector.
- [x] Added `mock`, `linux`, and `endpoint` providers with graceful partial-telemetry behavior.
- [x] Added `cold` as a first-class scenario in the mock provider and frontend controls.
- [x] Kept provider truthfulness in the UI instead of claiming a fake “real” hardware bridge.

### Baseline Cognitive Loop

- [x] Added derived affect values.
- [x] Added structured action suggestions.
- [x] Added autonomous event emission.
- [x] Added remote LLM modes: `off`, `openai_compatible`, and `deepseek`.
- [x] Added endpoint alias support so local proxy setups can use `OPENAI_*` and `DEEPSEEK_*`.
- [x] Normalized base URLs like `http://127.0.0.1:4000` and `http://127.0.0.1:4000/v1` into chat-completions endpoints.

## Phase 1: Body and Machine Telemetry

Goal:
The entity must expose as much machine-state as the host can reliably provide, both on screen and into vectorized cognition.

### 1.1 Core Somatic Contract

- [x] Keep the mandatory 11 core projector inputs stable:
  `voltage`, `current_ma`, `temp_si`, `temp_ml`, `temp_mr`, `ax`, `ay`, `az`, `gx`, `gy`, `gz`.
- [x] Preserve neutral defaults when a provider cannot source real data.

### 1.2 Linux Machine Telemetry Expansion

- [x] Surface CPU load, topology, and frequency:
  logical cores, physical cores, per-core load, frequency.
- [x] Surface RAM and swap:
  used, total, available, percent.
- [x] Surface disk state:
  used percent, used/total/free capacity, read MB/s, write MB/s, busy percent, disk temperature when available.
- [x] Surface network throughput:
  upload Mbps and download Mbps.
- [x] Surface thermal arrays:
  CPU temperature sensors, flattened thermal sensors, storage temperature when available.
- [x] Surface fan arrays:
  primary RPM plus detailed fan sensor bank.
- [x] Surface GPU state when available:
  utilization, temperature, power, VRAM used/total/percent.
- [x] Preserve partial operation when `psutil`, `nvidia-smi`, `hwmon`, `powercap`, or battery files are absent.
- [x] Add procfs/disk-usage fallbacks so the provider still returns useful data without `psutil`.

### 1.3 Frontend Hardware Telemetry

- [x] Show the minimum machine telemetry cards from the earlier phases:
  CPU load, memory, CPU temp, CPU power, GPU temp, GPU power, battery, AC, fan RPM, source quality.
- [x] Expand the telemetry panel to include:
  swap, GPU util, VRAM, disk use, disk busy, net down, net up, disk temp.
- [x] Add compact machine cards for:
  CPU topology, RAM usage, disk usage, GPU VRAM, network throughput.
- [x] Add detailed compact cards for:
  per-core load map, thermal sensor map, fan bank map.

### 1.4 Remaining Telemetry Work

- [ ] Add optional vendor-specific enrichments when available:
  NVMe SMART temperature, motherboard voltages, pump speeds, AMD GPU metrics, Intel iGPU metrics.
- [ ] Evaluate whether BIOS-only data is realistically accessible on the target machines or whether Linux userland/hwmon is the practical ceiling.
- [ ] Decide whether to add optional dependencies such as `smartctl` or `nvme-cli` for storage telemetry enrichment.
- [ ] Add a lightweight schema note describing which fields are “best effort” versus expected on most Linux desktops.

## Phase 2: Somatic Vectorization

Goal:
Machine state must influence the latent body representation, not remain outside the main cognitive path.

### 2.1 Projector and Latent Bridge

- [x] Keep the 11D core-to-4096D projector path active when TorchScript is available.
- [x] Keep the deterministic fallback projector path active when the TorchScript model is unavailable.

### 2.2 Machine-State Vector

- [x] Add a 128D `machine_vector` derived from machine telemetry.
- [x] Include scalar telemetry in the vector:
  CPU, RAM, swap, GPU, disk, network, battery, fans, load averages, source quality.
- [x] Include array summaries and sampled structure in the vector:
  per-core load, CPU temp sensors, thermal sensors, fan sensors.
- [x] Expose vector metadata:
  dimension, norm, preview, full vector, normalized features, top features.

### 2.3 Fusion Step

- [x] Fuse the machine-state vector into the 4096D somatic projector output before heatmap/statistics generation.
- [x] Expose fusion metadata in the projector payload:
  enabled flag, gain, machine-vector norm.

### 2.4 Remaining Vectorization Work

- [x] Replace the current analytic machine-state fusion with a trained fusion network or adapter.
- [ ] Decide whether the machine vector should become a first-class tensor input to the future model instead of only a deterministic modulation.
- [ ] Add fixtures for representative fused vectors in `nominal`, `heavyload`, `cold`, and degraded-hardware states.

## Phase 3: Homeostasis and Self-State

Goal:
The runtime must have an explicit notion of internal drives, not only raw measurements.

### 3.1 Completed

- [x] Derive affect values:
  `cold`, `heat`, `energy_low`, `fatigue`, `instability`, `curiosity`.
- [x] Derive scenario labels:
  `nominal`, `lowbatt`, `overheat`, `cold`, `fall`, `spin`, `heavyload`.
- [x] Build homeostatic drives:
  `cooling`, `energy_recovery`, `stability`, `rest`, `warmth`, `exploration`.
- [x] Expose dominant homeostatic drives plus stability/thermal/energy margins.
- [x] Use homeostatic state in autonomous event generation.

### 3.2 Remaining

- [x] Add explicit drive arbitration rules beyond simple top-3 ranking.
- [ ] Add longer-lived motivational state:
  persistence, social attention, exploration budget, recovery priority.
- [x] Add structured reflex policies for extreme power, thermal, or instability states.
- [x] Decide whether the future backend should emit a separate “policy state” block distinct from `affect` and `homeostasis`.

## Phase 4: Memory

Goal:
The entity must maintain continuity across dialogue turns, sensor evolution, and process restarts.

### 4.1 Short-Term Memory

- [x] Keep recent dialogue turns in a bounded in-memory deque.
- [x] Keep a bounded recent somatic window of snapshots.
- [x] Feed both short-term structures into LLM context.

### 4.2 Long-Term Memory Persistence

- [x] Persist semantic memory in `data/memory/semantic_memory.json`.
- [x] Persist episodic events in `data/memory/episodic_memory.jsonl`.
- [x] Track durable semantic counters:
  total chat exchanges, total autonomous events, scenario counts, provider counts, last user/entity text, last event, dominant drives.

### 4.3 Long-Term Memory Retrieval

- [x] Add retrieval of recent/relevant episodic memory into the LLM context.
- [x] Rank retrieved episodes by lexical overlap, drive overlap, scenario match, provider match, and recency.
- [x] Clip retrieved episode text so context stays compact enough for the language core.

### 4.4 Remaining Memory Work

- [x] Add semantic consolidation so repeated episodes become stable higher-level facts.
- [ ] Add operator memory versus self memory as separate namespaces.
- [ ] Add environment memory:
  machine identity, host traits, known hardware quirks, recurring thermal signatures.
- [ ] Add explicit forgetting/retention rules instead of unbounded JSONL growth.
- [ ] Decide whether the future C++ daemon owns memory persistence directly or talks to a sidecar memory service.

## Phase 5: Language Core and DeepSeek

Goal:
DeepSeek must act as the central linguistic core, grounded in body state and memory instead of generic chat behavior.

### 5.1 Completed

- [x] Validate direct DeepSeek-style chat completions against the local proxy on `127.0.0.1`.
- [x] Validate a preliminary end-to-end `server.py -> WebSocket -> DeepSeek` path.
- [x] Add prompt rules that explicitly tie reply generation to body state, telemetry, homeostasis, short-term memory, and long-term memory.
- [x] Instruct the model to answer in the same language used by the user.
- [x] Add salience extraction so the LLM context highlights the strongest machine/body signals.
- [x] Lower generation temperature for less generic, less floaty replies.

### 5.2 Remaining

- [x] Re-test DeepSeek after the new memory/salience/fusion changes and record the result here.
- [x] Add an explicit negative-path test with an invalid DeepSeek endpoint and confirm graceful fallback.
- [ ] Expose parsing-recovery state in the UI when the remote model returns malformed JSON and the server falls back.
- [ ] Decide whether to maintain separate prompt variants for simulated bodies versus real Linux telemetry.
- [ ] Decide whether response JSON should later carry an explicit `reasoning_focus` or `salience_ref` field for debugging.

## Phase 6: Frontend Truthfulness and Operator Visibility

Goal:
The operator must be able to tell, at a glance, whether cognition is local fallback or backend-driven.

### 6.1 Completed

- [x] Add a dedicated `CNS LINK` badge in the top bar.
- [x] Keep truthful provider/projector/LLM state in the top bar.
- [x] Distinguish `OFF`, `FALLBACK`, and `CONNECTED`.
- [x] Show the connected LLM provider in the top bar when live, for example `LLM: CONNECTED (DEEPSEEK)`.
- [x] Add a chat-pane `CHAT CORE` banner so the operator can see whether chat is:
  local fallback, server-online/LLM-off, server-online/LLM-fallback, or remote live.
- [x] Log an explicit console line when a browser fallback reply is generated and DeepSeek was not contacted.
- [x] Resolve the WebSocket URL from the current host by default instead of hardcoding `ws://localhost:8765`.
- [x] Support query-string overrides such as `?ws=ws://host:8765` or `?ws_port=8878`.

### 6.2 Remaining

- [ ] Add a compact UI surface for top machine-vector features and dominant homeostatic drives.
- [ ] Add a visible indicator when the backend is online but the LLM recovered from malformed JSON.
- [ ] Consider exposing memory counters in the monitor pane for debugging continuity across sessions.

## Phase 6B: Backend Actuation

Goal:
The runtime must emit executable state beyond browser animation hints.

### 6B.1 Completed

- [x] Add a backend `policy` block distinct from `affect` and `homeostasis`.
- [x] Add a backend `actuation` block carried in WebSocket payloads.
- [x] Persist current actuation state in `data/runtime/actuation_state.json`.
- [x] Persist actuation history in `data/runtime/actuation_history.jsonl`.
- [x] Emit backend commands such as:
  posture, fan target, compute governor, motion gate, language profile, power request, thermal guard, balance guard.
- [x] Support optional actuation egress through `SOMA_ACTUATOR_ENDPOINT`.

### 6B.2 Remaining

- [ ] Map backend actuation channels onto real GPIO/PWM/motor drivers when the hardware interface is ready.
- [ ] Add acknowledgement/feedback from the actuator side instead of fire-and-forget transport.

## Phase 9: Self-Growth — Shell Execution, Hardware Discovery, Self-Modification

North Star for this phase:
The entity must be able to find its own hardware gaps, fill them through LLM-guided command discovery,
verify the result by running bash, update its own sensor code, and push a branch to git.
Primary objective: survive (preserve the host system). Secondary: grow (become more capable).

### Architecture

```
tick snapshot → find None fields → needs_discovery?
    yes → ask LLM: "what bash cmd gives {field} on this Linux box?"
    LLM reply → ShellExecutor.run(cmd) [timeout 8s, blocked prefixes]
    success → mark available, store cmd
    failure → mark unavailable, remove from UI
    any new discovery + SOMA_SELF_MODIFY=1
        → write sensor_providers/discovered.py
        → git add / commit / push → auto/{hostname}-sensors branch
```

### 9.1 Completed

- [x] `sensor_providers/discoverer.py`: `ShellExecutor`, `HardwareDiscovery`, `SelfModifier`.
- [x] `ShellExecutor`: sandbox with BLOCKED_PREFIXES, 8s timeout, 4KB output cap.
- [x] `HardwareDiscovery`: persists `data/capabilities/discovered_commands.json` and `telemetry_caps.json`.
- [x] `DISCOVERABLE_FIELDS` covers: `gpu_*`, `fan_rpm`, `disk_temp`, `battery_percent`, `cpu_power_w`, `ac_online`, `battery_plugged`, `disk_busy_percent`.
- [x] `SelfModifier`: generates `sensor_providers/discovered.py`, git add/commit/push to `auto/{hostname}-sensors`.
- [x] `call_llm_raw()` in `server.py`: lightweight internal LLM call (no entity persona, plain text, 15s timeout).
- [x] `hardware_discovery_loop()` async task: starts 15s after boot, runs every 90s, paces one field/8s.
- [x] `telemetry_caps` field added to every tick payload and WS `public_payload`.
- [x] `shell_exec` WebSocket message type: operator or entity can request a sandboxed shell command.
- [x] `discovery_trigger` WebSocket message type: manually trigger one-field discovery cycle.
- [x] `DISCOVERY_ENABLED` (default on) and `DISCOVERY_INTERVAL_S` (default 90s) env vars.
- [x] `SOMA_SELF_MODIFY` env var guards git operations (default off).
- [x] `sensor_providers/linux_system.py`: merges `read_discovered_fields()` from `discovered.py` on every read.
- [x] Frontend bar rows hidden (`display:none`) when `caps[field] === false`; probing state shows `···`.
- [x] Frontend KV cards (ac_online, gpu_memory) hidden when caps say unavailable — `CAPS_KV_MAP` in `applyCapsToBars()`.
- [x] Frontend auto-hides non-cap bar rows (`disk_busy_percent`) and array KV cards (Core Load Map, Thermal Map, Fan Bank) after 18 consecutive "--" readings via `_nullTicks` counter.
- [x] False-positive fix: `record_llm_reply()` rejects commands whose stdout is literal "UNAVAILABLE".
- [x] `fan_rpm` false-positive cleaned from discovered_commands.json.

### 9.2 Completed

- [x] Discovery retry limit: after `MAX_DISCOVERY_ATTEMPTS` (3) consecutive LLM timeouts,
      field is marked unavailable and removed from probe queue. Stops infinite re-probe loop.
- [x] LLM serialization lock (`_get_llm_raw_lock()`): discovery loop and capability checks
      serialized via asyncio.Lock — prevents concurrent calls on single-threaded local LLM.
- [x] Direct probed all pending fields on devgui; telemetry_caps.json updated with ground truth:
      fan_rpm=false, disk_temp=false, battery_percent=false, battery_plugged=false,
      disk_busy_percent=true (from /proc/diskstats weighted I/O time).
- [x] Direct bash shortcuts in `try_chat_capability`: speedtest/bandwidth, disk iops, ports
      bypass LLM entirely — pattern-matched and executed directly. Eliminates NONE false-negative
      for speedtest.

### 9.3 Remaining

- [ ] Frontend: add "shell" tab or console pane where operator can type a command and see `shell_result`.
- [ ] When `discovered.py` is written, validate it with `python3 -m py_compile` before git add.
- [ ] Extend DISCOVERABLE_FIELDS: NVMe SMART temp (`smartctl -A`), AMD GPU metrics (`rocm-smi`), Intel iGPU (`intel_gpu_top -J`).
- [ ] Add unit test: mock LLM returns known command → ShellExecutor runs it → verify persistence.
- [ ] Decide whether `SOMA_SELF_MODIFY` should require a `--allow-self-modify` CLI flag for safety.

### 9.3 Self-Growth Drive Integration

- [x] `capability_growth` drive added to homeostatic drives: `clamp01(user_caps_count / 10)`.
- [x] `known_capabilities` block injected into `build_llm_context()` so entity knows what it can measure.
- [ ] Add `knowledge_gap` affect signal: count of DISCOVERABLE_FIELDS with caps[field]===null → drives exploration affect.
- [ ] Include `telemetry_caps` gap summary in `build_salience()` so LLM context reads
      "N hardware channels unresolved — discovery active".

## Phase 7: Validation and Test Workflow

Goal:
Every major step must have a reproducible command or browser check.

### 7.1 Completed Validation

- [x] `python3 -m py_compile server.py sensor_providers/*.py scripts/ws_smoke_test.py`
- [x] `bash -n scripts/bootstrap.sh`
- [x] JavaScript syntax check for `docs/simulator.html` using `node --check` on the extracted script.
- [x] Mock-mode server smoke start.
- [x] Linux-mode server smoke start.
- [x] Preliminary DeepSeek WebSocket smoke test on localhost.
- [x] Expanded `scripts/ws_smoke_test.py` to validate `homeostasis` and `machine_vector` payloads.
- [x] Expanded `scripts/ws_smoke_test.py` to validate `policy` and `actuation` payloads.
- [x] `bash -n scripts/run_production.sh`

### 7.2 Remaining Validation

- [x] Run a full Linux-provider + DeepSeek smoke test after the new vector/memory changes.
- [x] Run an invalid-endpoint fallback test and confirm:
  server stays up, `llm.mode` degrades to `fallback`, browser remains usable.
- [ ] At the end of the next development session, run a manual browser test and append the observed result here before proceeding further.

## Phase 8: C++ Migration Guardrails

Goal:
Do not lose protocol/memory/body semantics when the runtime moves beyond Python.

### 8.1 Completed Guardrails

- [x] Keep frontend payloads decoupled from Python implementation details.
- [x] Avoid starting a premature `cpp_daemon/` tree before the Python contract is stable enough to freeze.

### 8.2 Remaining Guardrails

- [ ] Freeze representative JSON fixtures for `init`, `tick`, `chat_reply`, and `autonomous_event`.
- [ ] Freeze at least one machine-vector and projector-fusion fixture per major body state.
- [ ] Decide whether memory persistence remains file-based in C++ or moves behind an interface.
- [ ] Decide the exact tree layout for the eventual C++ runtime once the payload contract is considered stable.

## Phase 10: Conversational Learning Loop

North Star for this phase:
The entity must learn from every conversation. When a user asks something the entity cannot answer
from sensors, it asks DeepSeek for a bash command, executes it, answers with real data,
and stores the capability so the next time it already knows. Growth must be visible.

### Learning Flow

```
User asks X
  → try_chat_capability(X)
      → broadcast "entity" prompt to DeepSeek dialogue panel
      → call_llm_raw: "can this be answered by a bash cmd? output ONLY the cmd or NONE"
      → broadcast DeepSeek reply to panel
      if cmd returned:
          → run cmd in sandbox (ShellExecutor, 20s limit)
          → broadcast cns_stream:discovery_cmd + discovery_result
          → inject real stdout into LLM chat context: [REAL_SYSTEM_DATA: ...]
          → entity answers with actual measured data
          → broadcast final chat reply to DeepSeek dialogue panel too
      if NONE:
          → entity answers from memory/LLM persona only (no real measurement)
```

### 10.1 Completed

- [x] `broadcast_ds_turn(role, text, purpose, field)` async helper in server.py.
- [x] `try_chat_capability(user_text)` — pre-processes every chat message: asks DeepSeek
      whether it can be answered by bash, runs the command if yes, returns stdout.
- [x] Chat handler updated: `try_chat_capability` called before `call_llm`; real data
      injected into enriched context with instruction "use this real measured data".
- [x] `hardware_discovery_loop` now broadcasts `deepseek_dialogue` around every LLM call.
- [x] DeepSeek internal dialogue panel (4th column in UI): shows entity→DeepSeek and
      DeepSeek→entity turns with color-coded badges by purpose.
- [x] `deepseek_dialogue` WS event handled in browser; `appendDsEntry()` renders turns.
- [x] Unavailable telemetry rows removed from DOM (not dimmed, completely hidden).
- [x] `ac_online` and `battery_plugged` added to `DISCOVERABLE_FIELDS`.
- [x] Capability check prompt fixed: removed false-negative `speedtest → NONE` example;
      added positive curl-based network speed example and allowed pipes/curl/ss/cat.
- [x] User capability cache (`user_capabilities.json`) loaded at boot; matching intents
      reuse cached bash cmd without re-asking DeepSeek.
- [x] `known_capabilities` block injected into every LLM chat context (user_learned,
      hw_available, hw_pending, total_user_caps).
- [x] `capability_growth` homeostatic drive added.
- [x] Two new `make_soma_pulse` nominal templates that surface `caps_n` in the CNS stream.
- [x] Stat cards: "Caps. Learned" counter wired to `user_caps_count` WS event.

### 10.2 Next Steps

- [ ] Smarter intent classification: before `try_chat_capability`, classify message as
      `sensor_query | bash_request | identity | philosophical` — only probe bash for first two.
      Avoids polluting DS panel with NONE replies for clearly conversational messages.
- [ ] Entity proactive acknowledgement: when `try_chat_capability` fires and waits for DeepSeek,
      emit `cns_stream` "Probing capability for: {intent}..." so operator can see the entity is thinking.
- [ ] `deepseek_dialogue` panel: fold/expand long prompts (truncate at 3 lines, click to expand).
- [ ] `deepseek_dialogue` panel: filter buttons by purpose (discovery / capability_check / chat).
- [ ] Entity self-report: when cap_output arrives, also emit an autonomous event "Capability confirmed: {intent}".

### 10.3 Observable Growth Indicators

- [x] "Caps. Learned" stat card added and wired to `user_caps_count` WS event.
- [x] `make_soma_pulse` nominal templates surface `caps_n` in CNS cognitive stream.
- [x] Successful chat capability discoveries recorded as episodic memory events.
- [x] Hardware discovery outcomes (available + unavailable) recorded into episodic memory so the
      entity retains its hardware map across restarts in the RAG system.
- [x] Cross-field battery dependency: if `battery_percent` is confirmed unavailable, `battery_plugged`
      is propagated as unavailable immediately (same hardware path, no LLM re-probe needed).
- [x] Stale false-positive `battery_percent` entry cleaned from `discovered_commands.json`.
- [ ] Cumulative capability map visible in Monitor: "N/M telemetry fields resolved" bar or text.

## Immediate Next Batch

This is the next safe development chunk to execute before opening a wider architectural branch:

- [x] Validate Linux + DeepSeek end-to-end with the richer telemetry/memory context.
- [x] Validate forced fallback with an invalid DeepSeek endpoint.
- [ ] If both pass, move to deeper telemetry acquisition and memory consolidation.

## Validation Log

### 2026-04-26

- [x] `python3 scripts/ws_smoke_test.py --host 127.0.0.1 --port 8891 --expect-llm --expect-llm-mode deepseek --timeout 45 --text "Quanti core stai usando, quanta RAM stai consumando e qual è il tuo stato termico?"`
  Result:
  DeepSeek replied through the Linux provider path with real machine telemetry.
  Example backend reply:
  `Attualmente distribuisco i miei processi su 8 core logici... RAM 48.2% ... silicio 35.0°C.`

- [x] `python3 scripts/ws_smoke_test.py --host 127.0.0.1 --port 8892 --expect-llm-mode fallback --timeout 20 --text "Come ti senti?"`
  Result:
  With an invalid endpoint, the server stayed online and degraded to `llm.mode=fallback` without crashing.

- [x] `python3 scripts/ws_smoke_test.py --host 127.0.0.1 --port 8893 --expect-llm --expect-llm-mode deepseek --timeout 45 --text "Dimmi politica autonoma, RAM, core, e stato termico attuale."`
  Result:
  DeepSeek replied with live Linux telemetry plus the autonomous policy mode, while the projector reported `machine_fusion_mode=learned`.

- [x] `python3 scripts/ws_smoke_test.py --host 127.0.0.1 --port 8895 --expect-llm-mode off --timeout 20 --text "stato"`
  Result:
  The `LLM OFF` path now stays truthful during `chat_reply` instead of being mislabeled as fallback.

## Working Commands

Reference commands already validated locally:

```bash
python3 -m py_compile server.py sensor_providers/*.py scripts/ws_smoke_test.py
bash -n scripts/bootstrap.sh
```

Basic local runtime:

```bash
SOMA_SENSOR_PROVIDER=mock SOMA_LLM_MODE=off python3 server.py
SOMA_SENSOR_PROVIDER=linux SOMA_LLM_MODE=off python3 server.py
```

DeepSeek/proxy smoke command pattern:

```bash
env PYTHONUNBUFFERED=1 \
  SOMA_SENSOR_PROVIDER=mock \
  SOMA_LLM_MODE=deepseek \
  DEEPSEEK_API_URL=http://127.0.0.1:4000 \
  DEEPSEEK_API_KEY=... \
  MEDIUM_DEEPSEEK_MODEL=gemini-web \
  python3 server.py --host 127.0.0.1 --port 8878
```

WebSocket smoke test:

```bash
python3 scripts/ws_smoke_test.py \
  --host 127.0.0.1 \
  --port 8878 \
  --expect-llm \
  --expect-llm-mode deepseek \
  --timeout 45 \
  --text "Quanti core stai usando, quanta RAM stai consumando e qual è il tuo stato termico?"
```

Prepared browser test note for the next session:

- The manual browser check must confirm that `CNS LINK` is online and `CHAT CORE` is not in local fallback before trusting any chat response as backend cognition.
