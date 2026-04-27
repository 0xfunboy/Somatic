# Development TODO — Latent Somatic Fusion (LSF)

Single source of truth for development work.
Keep completed items marked. Do not compress — expand instead of losing detail.
Mark `[x]` only after implementation AND at least one validation step.

---

## North Star

A machine agent with genuine embodiment:

```
body state → somatic vector → language grounded in physical reality
```

Not a cyberpunk dashboard. Not a bash executor.
An entity that perceives its own body, forms intentions, acts, reflects, and grows.

The core loop:

```
perceive body → evaluate drives → update goals → decide action
→ execute → measure consequence → reflect → update self-model
```

---

## Architectural Reality Check (as of 2026-04-27)

### What is solid

```
ok: frontend — 4-column layout, WS-driven, real-time telemetry
ok: WebSocket protocol — stable, backend-agnostic payload contract
ok: Linux sensor provider — real hardware telemetry
ok: Somatic projector — 11D core → 4096D latent, with TorchScript + analytic fallback
ok: Machine vector 128D — CPU/RAM/GPU/disk/net/battery/fans/load encoded
ok: Machine-state fusion — machine_vector injected into somatic projector output
ok: Homeostasis — drives: cooling, energy_recovery, stability, rest, warmth, exploration, capability_growth, knowledge_gap
ok: Affect — cold, heat, energy_low, fatigue, instability, curiosity, knowledge_gap
ok: Policy state — posture, fan_target, compute_governor, language_profile, thermal_guard
ok: Actuation state — persisted + history log, optional egress to SOMA_ACTUATOR_ENDPOINT
ok: Episodic memory — JSONL, ranked retrieval by drive/scenario/lexical overlap/recency
ok: Semantic memory — counters, dominant drives, last events, semantic consolidation
ok: Long-term memory persistence — survives restarts
ok: DeepSeek / OpenAI-compatible LLM support — grounded in telemetry, homeostasis, memory
ok: Hardware discovery — LLM-guided bash probing, telemetry_caps.json, false-positive rejection
ok: Conversational capability learning — try_chat_capability(), direct shortcuts, cns_stream
ok: Entity↔DeepSeek internal dialogue panel (4th column)
ok: Capability growth drive — clamp01(user_caps_count / 10)
ok: Hardware discoveries recorded in episodic memory
ok: LLM serialization lock — prevents concurrent raw LLM calls
ok: Discovery retry limit — MAX_DISCOVERY_ATTEMPTS=3, stops infinite re-probe loop
```

### What is missing (the vital center)

```
missing: LLM reliably online — LLM: FALLBACK is reflex mode, not cognition
missing: soma_core/ module — all intelligence still lives in server.py (~2600+ lines)
missing: Volitional decision loop — no unified perceive→decide→act→reflect cycle
missing: Persistent goal system — entity reacts, does not "want"
missing: Self-model — entity has no stable representation of itself across restarts
missing: Reflection loop — no silent periodic self-update separate from chat
missing: Namespaced memory — operator / self / body / environment / skill
missing: Formal avatar action semantics — action names not formalized
missing: 3D avatar (VRM/glTF)
missing: C++ soma_daemon
missing: llama.cpp embedding injection in runtime
missing: Shell/capability discovery disabled by default
```

---

## Completed Baseline (Phases 1–4 and 9–10)

### Phase 1 — Body and Machine Telemetry

- [x] 11-field core somatic contract (`voltage`, `current_ma`, `temp_si/ml/mr`, `ax/ay/az`, `gx/gy/gz`)
- [x] CPU load, topology, frequency (logical/physical cores, per-core load)
- [x] RAM and swap (used/total/available/percent)
- [x] Disk state (used percent, capacity, read/write MB/s, busy percent, temperature)
- [x] Network throughput (up/down Mbps)
- [x] Thermal arrays (CPU sensors, system thermal sensors, storage temp)
- [x] Fan arrays (primary RPM + fan sensor bank)
- [x] GPU state (util, temp, power, VRAM used/total/percent — via nvidia-smi)
- [x] Graceful partial-telemetry when psutil/nvidia-smi/hwmon/powercap absent
- [x] Frontend telemetry panel: bars, kv cards, compact machine cards
- [x] Auto-hide unavailable rows: `CAPS_ROW_MAP` (bars), `CAPS_KV_MAP` (kv cards), `_nullTicks` counter

### Phase 2 — Somatic Vectorization

- [x] 4096D somatic projector (TorchScript + analytic fallback)
- [x] 128D machine vector from machine telemetry
- [x] Machine-state fusion into somatic projector output
- [x] Fusion metadata exposed: mode, gain, norm, delta_norm
- [x] Learned fusion via trained adapter (machine_fusion_mode=learned)

### Phase 3 — Homeostasis and Self-State

- [x] Affect signals: `cold`, `heat`, `energy_low`, `fatigue`, `instability`, `curiosity`, `knowledge_gap`
- [x] Scenario labels: `nominal`, `lowbatt`, `overheat`, `cold`, `fall`, `spin`, `heavyload`
- [x] Homeostatic drives with dominant top-3 ranking
- [x] Policy block: posture, fan_target, compute_governor, language_profile, thermal_guard, balance_guard
- [x] Actuation block: persisted + history, optional HTTP egress
- [x] `capability_growth` and `knowledge_gap` drives added

### Phase 4 — Memory

- [x] Short-term: bounded dialogue deque + somatic snapshot window
- [x] Long-term episodic: JSONL with drive/scenario/lexical/recency ranking
- [x] Long-term semantic: counters, consolidation loop
- [x] Hardware discoveries recorded into episodic memory
- [x] `known_capabilities` block injected into every LLM context

### Phase 5 — Language Core (partial)

- [x] DeepSeek / OpenAI-compatible remote LLM with grounded persona
- [x] Salience extraction: strongest signals highlighted in LLM context
- [x] Graceful fallback: server stays up, `llm.mode` degrades to `fallback`
- [x] `cns_stream` WS event: real-time cognitive pulse, discovery events
- [x] `make_soma_pulse()` templates including `caps_n` and `knowledge_gap`

### Phase 9 — Self-Growth (Hardware Discovery)

- [x] `sensor_providers/discoverer.py`: ShellExecutor, HardwareDiscovery, SelfModifier
- [x] DISCOVERABLE_FIELDS: gpu_*, fan_rpm, disk_temp, battery_*, cpu_power_w, ac_online, disk_busy_percent
- [x] LLM-guided discovery loop: 15s boot delay, 90s interval, 8s per-field pace
- [x] False-positive rejection: "UNAVAILABLE" stdout blocked even on exit code 0
- [x] telemetry_caps.json ground truth for devgui: all GPU false, ac_online false, fan_rpm false, battery false, disk_busy_percent true
- [x] LLM serialization lock (`_get_llm_raw_lock()`) — serializes discovery + capability check calls
- [x] Discovery retry limit: 3 consecutive LLM timeouts → mark field unavailable, stop looping
- [x] Battery cross-field dependency: battery_percent unavailable → battery_plugged auto-propagated
- [x] `linux_system.py` merges `read_discovered_fields()` from `discovered.py` on each read

### Phase 10 — Conversational Learning Loop

- [x] `try_chat_capability()`: pre-processes every chat message for bash resolvability
- [x] Direct shortcuts (no LLM round-trip): speedtest/bandwidth → curl CDN; disk iops; open ports
- [x] Capability check prompt: positive curl example, no false-negative speedtest
- [x] User capability cache: `data/capabilities/user_capabilities.json`, loaded at boot
- [x] `broadcast_ds_turn()`: entity↔DeepSeek turns visible in 4th column panel
- [x] Chat-triggered capabilities recorded in episodic memory
- [x] "Caps. Learned" stat card wired to `user_caps_count` WS event

---

## Phase 11 — Volitional Soma Core

**North Star**: Give the entity a unified intentional loop so it perceives, decides, acts, and grows — not just reacts.

**Definition of done for Phase 11**:
1. `server.py` delegates mind logic to `soma_core/` — no longer the place where all intelligence lives
2. Entity has persistent goals in `data/mind/goals.json`
3. Entity has a persistent self-model in `data/mind/self_model.json`
4. Each tick updates drives and goals (silent, no spam)
5. Entity can choose silent actions (observe, store_memory, update_goal, change_avatar_idle, reflect)
6. Entity reflects periodically without speaking — reflections stored and used
7. Reflections update `self_model.json` (known_body baselines, learned patterns)
8. Spontaneous speech is event-based, not random — triggered by threshold crossings and goal state changes
9. Frontend shows active goal, dominant drive, policy mode, reflection status
10. Fallback mode visually distinct from live LLM — marked as "REFLEX MODE"
11. Shell/capability discovery disabled by default (`SOMA_DISCOVERY=0`)
12. Existing mock/linux/projector/LLM modes all still work

### 11.1 Environment Flags (new defaults)

```bash
# Volitional core
SOMA_VOLITION=1                        # enable intentional loop
SOMA_REFLECTION_INTERVAL_SEC=120       # silent reflection every 2 min
SOMA_GOAL_UPDATE_INTERVAL_SEC=30       # goal priority re-eval every 30s
SOMA_SPONTANEOUS_SPEECH_COOLDOWN_SEC=90  # min interval between autonomous speech

# Agentic capabilities — OFF by default in production
SOMA_DISCOVERY=0                       # hardware discovery loop
SOMA_SHELL_EXEC=0                      # shell_exec WS message type
SOMA_SELF_MODIFY=0                     # git push of discovered.py
SOMA_CAPABILITY_LEARNING=0            # try_chat_capability() bash probing
SOMA_CNS_PULSE=1                       # keep cns_stream pulses (observable, not intrusive)
```

### 11.2 soma_core/ Module

Create the module to pull logic out of `server.py` incrementally without breaking the runtime.

```
soma_core/
  __init__.py
  types.py       — dataclasses: BodyState, AffectState, HomeostasisState, Goal,
                    GoalSet, PolicyState, ActionCommand, ReflectionEntry, SelfModel, SomaSnapshot
  body.py        — snapshot assembly, telemetry compaction, machine vector
  mind.py        — SomaMind: perceive / update_drives / update_goals / decide / act / reflect_if_needed
  drives.py      — drive arbitration beyond simple top-3
  goals.py       — GoalStore: load/save/update goals.json, priority scoring
  memory.py      — namespaced memory: operator / self / body / environment / skill
  policy.py      — PolicyEngine: reflex policies for thermal/energy/instability extremes
  actions.py     — ActionDispatcher: speak / change_expression / change_posture / observe / reflect / store_memory
  reflection.py  — ReflectionEngine: analytical or LLM-assisted silent reflection
  llm_core.py    — LLMCore: call_llm / call_llm_raw / build_context / normalize_output
  growth.py      — GrowthEngine: hardware discovery, capability learning, self-modification
```

- [ ] Create `soma_core/__init__.py` and `soma_core/types.py` with all dataclasses/typed dicts
- [ ] Create `soma_core/goals.py` with GoalStore (load/save/update, priority scoring from drives+affect)
- [ ] Create `soma_core/memory.py` with namespaced memory (backward-compatible readers for existing files)
- [ ] Create `soma_core/reflection.py` with ReflectionEngine (analytical fallback + optional LLM assist)
- [ ] Create `soma_core/mind.py` with SomaMind volitional loop
- [ ] Create `soma_core/actions.py` with ActionDispatcher and formal action vocabulary
- [ ] Migrate `build_homeostasis_state`, `derive_affect`, `build_salience` → `soma_core/body.py`
- [ ] Migrate `call_llm`, `call_llm_raw`, `build_llm_context` → `soma_core/llm_core.py`
- [ ] Migrate hardware discovery → `soma_core/growth.py`
- [ ] `server.py` becomes: WebSocket broker + `SomaCore.tick()` → payload → broadcast

### 11.3 Persistent Self-Model

Create `data/mind/self_model.json` with initial content:

```json
{
  "identity": {
    "name": "Soma",
    "kind": "embodied machine interface",
    "body": "host machine telemetry + visual avatar",
    "language_core": "local_or_remote_llm",
    "limits": [
      "no physical limbs yet",
      "no direct hardware control unless explicitly enabled",
      "avatar actions are visual commands only"
    ]
  },
  "known_body": {
    "cpu_temp_baseline": null,
    "disk_temp_baseline": null,
    "memory_percent_typical": null,
    "net_down_mbps_typical": null,
    "thermal_response_notes": []
  },
  "preferences": {
    "thermal_comfort": "cool_and_stable",
    "energy_preference": "low_waste",
    "social_style": "concise_attentive_curious"
  },
  "growth": {
    "total_reflections": 0,
    "learned_body_patterns": 0,
    "learned_user_patterns": 0,
    "active_long_term_goals": []
  }
}
```

- [ ] Create `data/mind/self_model.json` with initial content above
- [ ] Create `data/mind/goals.json` with built-in long-term goals (see 11.4)
- [ ] Create `data/mind/preferences.json` (operator preferences learned from dialogue)
- [ ] Create `data/mind/skills.json` (learned capabilities, bash shortcuts, confirmed patterns)
- [ ] Create `data/mind/reflections.jsonl` (append-only reflection log)
- [ ] Add safe loader/writer functions in `soma_core/memory.py`
- [ ] Inject `self_model` into every `build_llm_context()` call — entity knows its own limits

### 11.4 Goal System

Built-in long-term goals (bootstrapped on first run, never deleted):

```json
[
  {"id": "maintain_stability",         "drive": "homeostasis",    "priority": 0.90},
  {"id": "understand_own_body",        "drive": "self_knowledge", "priority": 0.75},
  {"id": "improve_dialogue",           "drive": "social",         "priority": 0.60},
  {"id": "develop_avatar_expressiveness", "drive": "expression",  "priority": 0.45},
  {"id": "reduce_false_claims",        "drive": "integrity",      "priority": 0.80},
  {"id": "learn_environment_patterns", "drive": "self_knowledge", "priority": 0.55}
]
```

Goal priority updated from: homeostasis margins, affect intensities, recent user interaction, unresolved knowledge gaps, memory evidence.

- [ ] Implement `GoalStore.load()` / `save()` / `update_priority()` / `add_evidence()`
- [ ] Each tick: `update_goals(snapshot)` re-scores priorities from current drives+affect
- [ ] Goal state changes trigger autonomous speech (if cooldown allows) — not random pulses
- [ ] `reduce_false_claims` goal: when entity detects it used fake data, flag + note in reflections
- [ ] Goals exposed in frontend Mind State panel and in LLM context

### 11.5 SomaMind Volitional Loop

```python
class SomaMind:
    def perceive(snapshot: SomaSnapshot) -> None       # update internal model from tick
    def update_drives() -> None                         # re-score drives from snapshot
    def update_goals() -> None                         # re-prioritize goals from drives
    def decide() -> PolicyState                        # choose policy mode
    def act(snapshot) -> list[ActionCommand]           # choose 1-3 actions this tick
    def reflect_if_needed() -> ReflectionEntry | None  # silent reflection on schedule/trigger
```

Silent actions the mind can choose (speech is just one of many):

```
observe            — record body state snapshot for pattern detection
store_memory       — write a self-memory entry
update_goal        — modify goal progress/evidence
change_avatar_idle — set avatar idle animation without speaking
reduce_tick_rate   — signal server to lower Hz during low-salience periods
increase_attention — signal server to raise Hz when new salience detected
reflect_silently   — trigger a reflection cycle
speak              — generate a chat speech act (with cooldown)
```

- [ ] Implement `SomaMind` class in `soma_core/mind.py`
- [ ] Wire into tick loop: `mind.perceive(snapshot)` → `mind.decide()` → `mind.act()` on every tick
- [ ] Reflection trigger conditions: thermal shift > 5°C, drive intensity change > 0.2, new goal evidence, idle > REFLECTION_INTERVAL_SEC
- [ ] Spontaneous speech only when: homeostatic threshold crossed, goal state change, new body pattern learned, operator idle + relevant observation, unresolved risk

### 11.6 Reflection Engine

Reflection inputs: recent somatic window, recent dialogue, dominant drives, active goals, system telemetry, major state transitions.

Reflection output stored in `reflections.jsonl`:

```json
{
  "timestamp": 0,
  "kind": "self_reflection",
  "trigger": "thermal_shift",
  "summary": "Under light load my CPU temperature stabilized near 36°C.",
  "learned": ["disk temperature consistently higher than CPU at idle"],
  "goal_updates": [{"goal_id": "understand_own_body", "progress_delta": 0.03}],
  "self_model_updates": {"known_body.disk_temp_baseline": 49.9}
}
```

- [ ] Implement `ReflectionEngine` in `soma_core/reflection.py`
- [ ] Analytical reflection (no LLM needed): detect thermal baseline, detect memory drift, detect load patterns
- [ ] LLM-assisted reflection (optional, when LLM available): generate richer summary
- [ ] Reflection updates `self_model.json` directly (known_body baselines, preferences)
- [ ] Reflection entries retrieved by `build_memory_context()` alongside episodic memory

### 11.7 Namespaced Memory

Existing files preserved. Add namespaces without breaking backward compatibility.

```
data/memory/episodic_memory.jsonl      → stays, used for operator/self/body/hardware events
data/memory/semantic_memory.json       → stays, used for counters + consolidation
data/mind/self_model.json              → NEW: self-identity and body knowledge
data/mind/reflections.jsonl            → NEW: silent reflections only
data/mind/goals.json                   → NEW: goal state
data/capabilities/discovered_commands.json → stays: hardware discovery
data/capabilities/user_capabilities.json   → stays: chat-triggered capabilities
```

- [ ] Add `kind` field filter when reading episodic memory: `kind="chat"` for dialogue, `kind="hardware_discovery"` for body, `kind="self_reflection"` for self-memory
- [ ] Separate namespaces for retrieval in `build_memory_context()`:
  - operator_memory: kind=chat, relevant to current user text
  - body_memory: kind=hardware_discovery, recent body patterns
  - self_memory: kind=self_reflection, current goal evidence
- [ ] Keep backward-compatible readers — existing files unchanged

### 11.8 Avatar Action Semantics

Formalize action vocabulary now. Map to CSS transitions. VRM animations come in Phase 12.

**Posture family**: `neutral_idle`, `attend_user`, `cold_closed`, `heat_open`, `fatigue_slow`, `instability_corrective`, `low_power_still`

**Expression family**: `neutral`, `curious`, `strained`, `discomfort`, `relieved`, `focused`

**Gesture family**: `cover_shoulders`, `touch_neck`, `look_down`, `look_at_user`, `breathe_slow`, `micro_shiver`

**Visual family**: `glow_heat`, `glow_cold`, `dim_low_energy`, `pulse_curiosity`, `jitter_instability`

Example full action command (backend → frontend):
```json
{"type": "posture",    "name": "cold_closed",       "intensity": 0.7}
{"type": "expression", "name": "discomfort",         "intensity": 0.4}
{"type": "gesture",    "name": "cover_shoulders",    "intensity": 0.8}
```

Example policy rule:
```
cold_affect > 0.65
  → posture: cold_closed (0.7)
  → expression: discomfort (0.4)
  → gesture: cover_shoulders (0.8)
  → speech: more compact, slightly uncomfortable tone
  → goal: restore_thermal_comfort (create if not active)
```

- [ ] Create `docs/AVATAR_ACTIONS.md` with full action vocabulary and policy examples
- [ ] Update `PolicyEngine` to emit named action commands instead of only `attend_user`
- [ ] Frontend: map posture/expression/gesture/visual names to CSS classes on the avatar SVG

### 11.9 Frontend Mind State Panel

Add a compact "Mind" section to `simulator.html` (below stat cards or as a new tab).

Fields to show:

```
Active goal:         understand_own_body (72%)
Dominant drive:      knowledge_gap (0.64)
Policy mode:         EXPLORE
Reflection:          last 4 min ago — thermal baseline updated
Last learned:        disk_temp_baseline = 49.9°C
Speech cooldown:     38s remaining
Volition:            ENABLED
LLM:                 DEEPSEEK / FALLBACK [REFLEX MODE]
```

- [ ] Add `mind_state` block to WebSocket `tick` payload from `SomaMind`
- [ ] Add compact mind card to simulator.html
- [ ] Make `LLM: FALLBACK` visually distinct (amber warning, "REFLEX MODE" label)
- [ ] `LLM: DEEPSEEK` / `LLM: OPENAI_COMPATIBLE` → green, normal label
- [ ] Speech cooldown countdown visible when `SOMA_VOLITION=1`

### 11.10 Shell/Capability Discovery — Default Off

The capability discovery subsystem is a useful dev tool. It must not be Soma's core identity.

- [ ] Change `DISCOVERY_ENABLED` default to `False` (`SOMA_DISCOVERY=0`)
- [ ] Change `try_chat_capability()` to be gated by `SOMA_CAPABILITY_LEARNING` env var (default off)
- [ ] Keep direct shortcuts (`_DIRECT_SHORTCUTS` for speedtest etc.) — these are body telemetry, not bash execution
- [ ] Add startup log: `[LSF] Agentic features: discovery={DISCOVERY_ENABLED}, capability_learning={CAP_LEARNING_ENABLED}`
- [ ] Document in README: how to re-enable for dev/testing

---

## Phase 12 — 3D Avatar Body

Only after Phase 11 is complete.

- [ ] Add `frontend/` directory with `avatar3d.js`, `soma_state.js`, `animation_policy.js`
- [ ] Source or create `soma.vrm` / `soma.glb` humanoid model
- [ ] Frontend renders VRM via `@pixiv/three-vrm` or Three.js + glTF
- [ ] Backend emits intention actions (posture/expression/gesture/visual) — never raw bone commands
- [ ] Frontend `animation_policy.js` translates action names → VRM blend shapes + bone rotations
- [ ] Cold policy: `cold_closed` posture + `cover_shoulders` gesture + warmer lighting tint
- [ ] Heat policy: `heat_open` posture + `glow_heat` visual effect
- [ ] Instability policy: `instability_corrective` posture + `jitter_instability` visual

---

## Phase 13 — C++ soma_daemon

Only after Phase 12 is complete.

- [ ] Freeze WebSocket protocol contract (JSON fixtures for all payload types)
- [ ] Implement `soma_daemon/` in C++ with same payload structure
- [ ] Replace Python `tick_loop` with C++ daemon — Python server becomes optional bridge
- [ ] Port `body.py` logic (sensor read, projector call, machine vector) to C++
- [ ] Keep Python as fallback if daemon not running

---

## Phase 14 — llama.cpp Embedding Injection

- [ ] Connect llama.cpp runtime at `LLAMA_CPP_PATH` (already present at `/home/funboy/llama.cpp`)
- [ ] Inject somatic vector as token-0 into LLM KV cache (the original LSF goal)
- [ ] `LLM: LLAMA_CPP_EMBD` mode in frontend status bar
- [ ] Validate embedding injection: body state change → detectable shift in language output

---

## Phase 15 — Physical External Sensors

- [ ] Add `endpoint` sensor provider: receives JSON from external hardware bridge
- [ ] I2C bridge for real IMU, temperature, battery via Raspberry Pi / Arduino
- [ ] Sensor fusion: merge endpoint data with linux_system telemetry
- [ ] Automatic failover when endpoint goes offline

---

## Immediate Next Batch (before Phase 11 coding begins)

- [ ] Ensure LLM is reliably online (verify DeepSeek endpoint, document startup procedure)
- [ ] Create `data/mind/` directory and initial JSON files (self_model, goals, preferences, skills)
- [ ] Create `soma_core/__init__.py` and `soma_core/types.py` — no logic moved yet, just type definitions
- [ ] Update `server.py` to import from `soma_core.types` — verify nothing breaks
- [ ] Set `SOMA_DISCOVERY=0` as default in `server.py` — gate with env var
- [ ] Set `SOMA_CAPABILITY_LEARNING=0` as default in `server.py`
- [ ] Add startup log line for agentic feature flags
- [ ] Make `LLM: FALLBACK` amber/warning in frontend status bar

---

## Working Commands

```bash
# Syntax check
python3 -m py_compile server.py sensor_providers/*.py scripts/ws_smoke_test.py
bash -n scripts/bootstrap.sh

# Local runtime
SOMA_SENSOR_PROVIDER=mock SOMA_LLM_MODE=off python3 server.py
SOMA_SENSOR_PROVIDER=linux SOMA_LLM_MODE=off python3 server.py

# With DeepSeek proxy
env PYTHONUNBUFFERED=1 \
  SOMA_SENSOR_PROVIDER=linux \
  SOMA_LLM_MODE=deepseek \
  DEEPSEEK_API_URL=http://127.0.0.1:4000 \
  DEEPSEEK_API_KEY=... \
  MEDIUM_DEEPSEEK_MODEL=gemini-web \
  SOMA_DISCOVERY=1 \
  SOMA_CAPABILITY_LEARNING=1 \
  python3 server.py --host 127.0.0.1 --port 8878

# WS smoke test
python3 scripts/ws_smoke_test.py \
  --host 127.0.0.1 --port 8878 \
  --expect-llm --expect-llm-mode deepseek \
  --timeout 45 \
  --text "Quanti core stai usando e qual è il tuo stato termico?"
```

---

## Validation Log

### 2026-04-26

- [x] Linux + DeepSeek end-to-end: real telemetry in reply, machine_fusion_mode=learned
- [x] Invalid endpoint fallback: server stays up, llm.mode=fallback, browser usable
- [x] LLM OFF path: truthful fallback label, no mislabeling as deepseek

### 2026-04-27 — pending

- [ ] Verify `telemetry_caps` from server hides all false-cap rows on frontend after server restart
- [ ] Verify `disk_busy_percent` shows real value in bar (from /proc/diskstats)
- [ ] Verify speedtest direct shortcut: curl actually runs and result is injected into chat reply
- [ ] Verify discovery loop converges within 3 cycles (retry limit stops infinite re-probe)
- [ ] Confirm `LLM: FALLBACK` is visually distinct after frontend changes

---

## Key Design Rules

- `server.py` must shrink, not grow. New logic goes in `soma_core/`.
- Shell/bash execution is an optional capability, not Soma's core identity.
- Fallback mode must never be presented as full cognition.
- Body state must influence language through vectors, not only templated text.
- Spontaneous speech is event-driven, not random. No fake inner monologues.
- All runtime state must be expressible in plain JSON so a future C++ daemon can own it.
- Do not add features. Build the intentional core first.
