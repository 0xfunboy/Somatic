# SOMA PHASE 9.2 — RESOURCE GOVERNOR, METABOLIC THROTTLING, AND NON-DESTRUCTIVE AUTONOMY

Repo:

`/home/funboy/latent-somatic`

## Why this phase exists

The current runtime is functionally ahead of the earlier versions, but it is now too heavy for the host machine.

Observed live problem:

- while Soma is running, the host becomes sluggish
- terminal responsiveness drops to roughly one command per second
- Soma is supposed to preserve the machine it lives in, but it is currently consuming too much of it
- the metabolic/vector system exists, but it is not yet used aggressively enough to reduce its own cost

Current evidence from the uploaded runtime state and repo:

- `metabolic_state.json` shows Soma is in `mode: grow`
- `stability` around `0.84`
- `stress` around `0.20`
- `sensor_confidence_calibrated` around `0.72`
- `baseline_confidence` around `0.97`
- `stable_cycles` above 18k
- `bios_state.json` is over 3 MB because it persists the full internal prompt/context
- `internal_loop_state.json` is over 3 MB for the same reason
- `bios_history.jsonl` and `internal_decisions.jsonl` are already several MB
- `self_model.json` is several MB
- `server.py` calls expensive runtime logic every tick
- `tick_loop()` broadcasts a full public payload every tick
- `apply_autonomic_rate()` can push runtime toward 5Hz even if the host is struggling
- `build_snapshot()` currently performs too many heavy operations in the hot path
- `_metabolic_engine.update()` is called multiple times per snapshot
- `_cpp_bridge.run_projection_once(snapshot)` is executed from `build_snapshot()` and may be too frequent
- `_vector_interpreter.interpret(snapshot)` is in the hot path
- `_soma_mind.tick(snapshot)` is in the hot path
- `remember_somatic_trace(snapshot)` and `consolidate_memory(snapshot)` are in the hot path
- BIOS/internal prompt persistence writes huge duplicated contexts
- current `.env` does not explicitly configure the Phase 8/9 throttling vars, so many defaults are active

This violates the core survival rule:

**Soma must not degrade the host that sustains it.**

Soma needs an internal resource governor that uses host telemetry and metabolic state to slow itself down, suppress heavy operations, defer growth, pause mutation, and recover host responsiveness before continuing autonomy.

---

## Mission

Implement a real resource governor and budget system.

Soma must continuously answer:

1. how much host resource am I using?
2. how much budget do I have?
3. which tasks are safe to run now?
4. which tasks must be deferred?
5. should I lower tick rate?
6. should I pause BIOS/LLM/mutation?
7. should I enter recovery mode because I am harming my host?

The result must be:

- lower CPU pressure
- fewer file writes
- lower UI broadcast load
- no huge repeated JSON state files
- no per-tick expensive C++/vector/snapshot operations
- no autonomous growth while host is under load
- visible resource mode in UI
- clear introspection explaining throttling decisions
- safe defaults in `.env.example`
- tests proving the governor throttles under simulated load

---

## Absolute rules

Do not remove autonomy.
Do not remove BIOS.
Do not remove metabolic growth.
Do not remove C++ bridge.
Do not remove mutation sandbox.
Do not remove DeepSeek internal loop.

Instead, make all of them budget-aware.

Do not weaken survival policy.
Do not read or print `.env`.
Do not touch secrets.
Do not delete repo/home/system directories.
Do not execute `shutdown`, `poweroff`, or `halt`.
`reboot` is allowed by policy but must never be executed automatically.
Do not migrate a mutant repo into production without explicit operator approval.

---

# 1. Add ResourceGovernor

Create:

`soma_core/resource_governor.py`

Implement:

```python
class ResourceGovernor:
    def sample(snapshot: dict | None = None) -> dict
    def mode() -> str
    def budget() -> dict
    def allow(operation: str, *, estimated_cost: str = "low") -> tuple[bool, str]
    def record_operation(operation: str, duration_ms: float, ok: bool = True) -> None
    def recommended_tick_hz() -> float
    def recommended_bios_interval_sec() -> float
    def recommended_llm_timeout_sec() -> float
    def status() -> dict
```

Modes:

- `normal`
- `reduced`
- `critical`
- `recovery`

Inputs:

- CPU percent
- memory percent
- swap percent
- disk busy if available
- disk usage percent
- CPU temperature
- event loop lag
- average tick duration
- projector duration
- provider duration
- LLM calls per hour
- BIOS calls per hour
- shell calls per hour
- file write volume per minute
- UI connected clients count
- metabolic stress
- reward trend

Budget categories:

```json
{
  "tick_hz_max": 2.0,
  "ui_hz_max": 1.0,
  "projector_hz_max": 0.5,
  "vector_hz_max": 0.2,
  "cpp_bridge_hz_max": 0.05,
  "bios_interval_sec": 600,
  "internal_llm_interval_sec": 900,
  "mutation_allowed": false,
  "growth_allowed": false,
  "shell_allowed": true,
  "heavy_shell_allowed": false,
  "test_suite_allowed": false,
  "write_state_interval_sec": 30,
  "max_state_bytes": 65536
}
```

Default thresholds:

```env
SOMA_RESOURCE_GOVERNOR=1
SOMA_RESOURCE_MODE_DEFAULT=normal
SOMA_HOST_CPU_REDUCED_PERCENT=55
SOMA_HOST_CPU_CRITICAL_PERCENT=75
SOMA_HOST_MEM_REDUCED_PERCENT=70
SOMA_HOST_MEM_CRITICAL_PERCENT=85
SOMA_HOST_SWAP_CRITICAL_PERCENT=20
SOMA_HOST_TEMP_REDUCED_C=70
SOMA_HOST_TEMP_CRITICAL_C=82
SOMA_EVENT_LOOP_LAG_REDUCED_MS=250
SOMA_EVENT_LOOP_LAG_CRITICAL_MS=1000
SOMA_TICK_DURATION_REDUCED_MS=150
SOMA_TICK_DURATION_CRITICAL_MS=500
SOMA_RESOURCE_RECOVERY_STABLE_SEC=120
```

Mode logic:

- `normal`: host responsive, growth can run
- `reduced`: lower tick/UI/projector frequency, pause mutation, stretch BIOS interval
- `critical`: pause BIOS LLM, pause mutation, no tests, no heavy shell, lower UI/tick hard
- `recovery`: continue only minimal telemetry and diagnostics until stable for `SOMA_RESOURCE_RECOVERY_STABLE_SEC`

Resource pressure must feed into metabolic state:

- high resource pressure increases `stress`
- high resource pressure increases `recovery_pressure`
- `growth_allowed` becomes false in `critical` or `recovery`
- mutation is blocked in any mode except `normal`

Persist:

- `data/mind/resource_state.json`
- `data/mind/resource_history.jsonl` only on mode change or every N minutes, not every tick

---

# 2. Add BudgetedScheduler

Create:

`soma_core/scheduler.py`

Implement a small scheduler/rate limiter:

```python
class BudgetedScheduler:
    def due(name: str, interval_sec: float) -> bool
    def mark(name: str) -> None
    def allow(name: str, interval_sec: float, resource_governor: ResourceGovernor, cost: str = "low") -> tuple[bool, str]
    def status() -> dict
```

Use it for:

- projector inference
- C++ bridge smoke/projection
- vector interpretation
- metabolic history write
- BIOS maybe_run
- internal LLM call
- routines
- nightly
- journal rotation
- memory consolidation
- UI full payload broadcast
- CNS pulse

The scheduler must prevent accidental hot-loop execution of expensive functions.

---

# 3. Split tick path into fast, medium, slow lanes

Modify `server.py`.

Current problem:
`build_snapshot()` does too much every tick.

New structure:

## Fast lane, every tick

Allowed:

- read cheap sensor provider values
- update minimal live state
- broadcast lightweight tick delta
- update UI status counters

Not allowed:

- LLM calls
- C++ smoke/projection
- mutation checks
- full memory consolidation
- writing huge JSON state
- full public payload if unchanged
- full projector inference unless scheduled

## Medium lane, budgeted

Default every 2-5 seconds depending on resource mode:

- projector inference
- vector interpretation
- metabolic update
- policy update
- mind tick
- baseline aggregate update

## Slow lane, budgeted

Default every 5-15 minutes depending on resource mode:

- BIOS internal loop
- DeepSeek internal planner
- mutation proposal
- test suite
- self-improvement scan
- runtime storage report
- compaction
- nightly reflection

Implement functions:

```python
def build_fast_snapshot() -> dict

def update_medium_state(snapshot: dict) -> dict

def run_slow_maintenance(snapshot: dict) -> None
```

Or equivalent, but keep `server.py` readable.
Move heavy logic into `soma_core` modules wherever possible.

---

# 4. Stop full UI payload spam

Current:
`tick_loop()` broadcasts `{type: "tick", **public_payload(snapshot)}` every tick.

That is too much.

Implement:

- lightweight tick payload every tick
- full payload only at `SOMA_UI_FULL_PAYLOAD_HZ`
- immediate full payload on state change / user interaction / mode change

Config:

```env
SOMA_UI_FULL_PAYLOAD_HZ=0.5
SOMA_UI_LIGHT_TICK_HZ=2
SOMA_UI_MAX_BROADCAST_BYTES_PER_SEC=250000
SOMA_CNS_PULSE_INTERVAL_SEC=10
SOMA_CNS_PULSE_ENABLED=0
```

Light tick payload should include only:

```json
{
  "type": "tick_light",
  "timestamp": 0,
  "sensors": {"voltage": 12.0, "temp_si": 37.0, "az": -9.81},
  "system": {"cpu_percent": 0.0, "memory_percent": 40.0, "cpu_temp": 37.0},
  "metabolic": {"mode": "grow", "stability": 0.8, "stress": 0.2},
  "resource": {"mode": "normal", "tick_hz": 1.0}
}
```

Full payload can remain as-is but must be throttled.

UI must handle both `tick` and `tick_light`.

---

# 5. Cap tick rate and stop policy from pushing to 5Hz under load

Current:
`apply_autonomic_rate()` can push runtime toward policy target 5Hz.

Modify it:

- resource governor must cap desired Hz
- resource mode decides max Hz
- no policy can exceed resource budget

Defaults:

```env
SOMA_TICK_HZ=1
SOMA_TICK_HZ_MAX_NORMAL=2
SOMA_TICK_HZ_MAX_REDUCED=1
SOMA_TICK_HZ_MAX_CRITICAL=0.5
SOMA_TICK_HZ_MAX_RECOVERY=0.2
SOMA_AUTONOMIC_HZ=1
```

Rule:

```python
runtime["hz"] = min(policy_target, resource_governor.recommended_tick_hz())
```

If operator manually changes Hz in UI, clamp it to resource max unless `SOMA_OPERATOR_CAN_OVERRIDE_RESOURCE_HZ=1`.
Default false.

---

# 6. Throttle projector/vector/C++ bridge

The somatic vector is important, but it must not be computed every UI frame if the host suffers.

Config:

```env
SOMA_PROJECTOR_HZ_NORMAL=1
SOMA_PROJECTOR_HZ_REDUCED=0.2
SOMA_PROJECTOR_HZ_CRITICAL=0.05
SOMA_VECTOR_INTERPRETER_HZ=0.2
SOMA_CPP_PROJECTION_HZ=0.02
SOMA_CPP_SMOKE_TEST_INTERVAL_SEC=3600
```

Rules:

- reuse last projector result between scheduled projector runs
- reuse last vector interpretation between scheduled vector runs
- C++ bridge smoke only on start and then rarely
- C++ projection comparison never runs per tick
- if projector run exceeds budget, lower projector Hz automatically

Expose in UI:

- projector age
- vector age
- C++ bridge last smoke time
- resource throttle reason

---

# 7. Persist compact state, not huge prompts

Current:
`bios_state.json` and `internal_loop_state.json` are several MB because they store full prompts and full context.

Fix:

State files must be compact.

New persistence rules:

- `bios_state.json` max size target: under 64 KB
- `internal_loop_state.json` max size target: under 64 KB
- full prompts/raw LLM text go to compressed archive or JSONL with rotation
- state file stores only preview, hash, path to archive, parsed JSON, evidence summary

Add helpers:

```python
def compact_prompt(prompt: str) -> dict:
    return {
        "sha1": "...",
        "preview": prompt[:1200],
        "chars": len(prompt),
        "archive_path": "..."
    }
```

Persist full prompt in:

`data/mind/internal_prompts/YYYY-MM-DD.prompts.jsonl.gz`

or:

`data/journal/archive/...`

Do not store full metabolic/growth contexts repeatedly in state JSON.

Add state compaction migration:

- if existing `bios_state.json` or `internal_loop_state.json` > 256 KB, compact it on startup
- archive original to `data/archive/manual-pre-resource-governor/`

---

# 8. Add operation profiler

Create:

`soma_core/profiler.py`

Implement:

```python
class OperationProfiler:
    def start(name: str)
    def end(name: str)
    def measure(name: str): context manager
    def summary() -> dict
```

Track:

- provider read ms
- projector ms
- machine fusion ms
- vector interpreter ms
- metabolic update ms
- mind tick ms
- public payload ms
- websocket broadcast ms
- BIOS ms
- internal LLM ms
- file write ms
- tick total ms
- event loop lag ms

Persist compact status:

`data/mind/performance_state.json`

UI must show:

- resource mode
- tick total ms
- slowest operation
- current tick Hz
- recommended tick Hz
- throttled operations

---

# 9. Resource governor must control BIOS/internal LLM/mutation

Modify `soma_core/bios.py` and `soma_core/internal_loop.py`.

Rules:

- no internal LLM if resource mode is `critical` or `recovery`
- no mutation if resource mode is not `normal`
- no test suite if mode is `reduced`, `critical`, or `recovery`
- no heavy shell if CPU/memory pressure high
- if DeepSeek latency > threshold, lower LLM calls per hour
- if the operator is actively chatting, BIOS should yield unless task is urgent recovery

Config:

```env
SOMA_BIOS_INTERVAL_SEC_NORMAL=600
SOMA_BIOS_INTERVAL_SEC_REDUCED=1800
SOMA_BIOS_INTERVAL_SEC_CRITICAL=3600
SOMA_BIOS_INTERVAL_SEC_RECOVERY=3600
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_NORMAL=4
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_REDUCED=1
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_CRITICAL=0
SOMA_BIOS_YIELD_WHEN_USER_ACTIVE=1
SOMA_USER_ACTIVE_WINDOW_SEC=120
SOMA_INTERNAL_LLM_MAX_PROMPT_CHARS=6000
SOMA_INTERNAL_LLM_MAX_RESPONSE_CHARS=4000
```

If prompt exceeds `SOMA_INTERNAL_LLM_MAX_PROMPT_CHARS`, summarize context before calling LLM.

Do not send 100KB prompts to DeepSeek.

---

# 10. Add host preservation to metabolic engine

Modify `soma_core/metabolism.py`.

Resource pressure must be part of metabolism.

Add fields:

```json
{
  "host_pressure": 0.0,
  "resource_mode": "normal",
  "resource_throttle": true,
  "growth_suspended_by_resource": false,
  "mutation_suspended_by_resource": false
}
```

If host pressure high:

- increase stress
- increase recovery pressure
- lower growth pressure
- set mode to `stabilize` or `recover`
- mark reason: `host_resource_pressure`

Soma should not try to grow if it is making the host unusable.

---

# 11. Add resource-aware reward

Modify `soma_core/reward.py`.

Positive rewards:

- reducing CPU load
- reducing tick duration
- reducing file write size
- lowering UI payload bandwidth
- avoiding mutation during resource pressure
- yielding during user activity

Negative rewards:

- high host pressure caused by Soma
- tick duration above budget
- repeated huge state writes
- mutation/test started during reduced/critical mode
- LLM prompt too large
- UI broadcast too large

Add events:

- `resource_preserved`
- `resource_pressure_detected`
- `growth_suspended_for_host_health`
- `mutation_blocked_for_host_health`
- `state_compacted`
- `payload_throttled`

---

# 12. Add deterministic resource introspection skills

Update `soma_core/introspection.py` or skill router.

Add queries:

- `why are you slowing down?`
- `what is your resource mode?`
- `what are you throttling?`
- `what is your CPU budget?`
- `how much load are you causing?`
- `why did you pause growth?`
- `why did you pause mutation?`
- `show performance profile`
- `show resource governor status`

These must read:

- `resource_state.json`
- `performance_state.json`
- `metabolic_state.json`
- `bios_state.json`

Do not ask the LLM first.
Do not invent paths.

---

# 13. Update UI and tests UI

Update:

- `docs/simulator.html`
- `docs/tests.html` if relevant

Add topbar/status fields:

- `RESOURCE: NORMAL/REDUCED/CRITICAL/RECOVERY`
- `HOST: OK/PRESSURE`
- `TICK: 1.0Hz`
- `BUDGET: OK/THROTTLED`

Add runtime panel:

- CPU pressure
- memory pressure
- event loop lag
- tick duration
- slowest operation
- full payload Hz
- projector Hz
- BIOS interval
- internal LLM calls/hour
- throttled operations

If resource mode is reduced/critical/recovery, UI must clearly show why.

---

# 14. Update run.sh with safe mode support

Update `scripts/run.sh`.

Add modes:

```bash
bash scripts/run.sh
bash scripts/run.sh --safe
bash scripts/run.sh --debug
bash scripts/run.sh --no-bios
bash scripts/run.sh --low-power
```

Default should be safe for this machine.

Recommended default runtime env injected by run.sh if not already set:

```bash
export SOMA_RESOURCE_GOVERNOR=${SOMA_RESOURCE_GOVERNOR:-1}
export SOMA_TICK_HZ=${SOMA_TICK_HZ:-1}
export SOMA_TICK_HZ_MAX_NORMAL=${SOMA_TICK_HZ_MAX_NORMAL:-2}
export SOMA_UI_FULL_PAYLOAD_HZ=${SOMA_UI_FULL_PAYLOAD_HZ:-0.5}
export SOMA_UI_LIGHT_TICK_HZ=${SOMA_UI_LIGHT_TICK_HZ:-1}
export SOMA_PROJECTOR_HZ_NORMAL=${SOMA_PROJECTOR_HZ_NORMAL:-0.5}
export SOMA_VECTOR_INTERPRETER_HZ=${SOMA_VECTOR_INTERPRETER_HZ:-0.2}
export SOMA_CPP_PROJECTION_HZ=${SOMA_CPP_PROJECTION_HZ:-0.02}
export SOMA_BIOS_INTERVAL_SEC=${SOMA_BIOS_INTERVAL_SEC:-600}
export SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=${SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR:-4}
export SOMA_CNS_PULSE_ENABLED=${SOMA_CNS_PULSE_ENABLED:-0}
export SOMA_DISCOVERY_INTERVAL_SEC=${SOMA_DISCOVERY_INTERVAL_SEC:-600}
```

`--low-power` should set:

```bash
SOMA_TICK_HZ=0.5
SOMA_TICK_HZ_MAX_NORMAL=1
SOMA_UI_FULL_PAYLOAD_HZ=0.2
SOMA_PROJECTOR_HZ_NORMAL=0.1
SOMA_BIOS_INTERVAL_SEC=1800
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=1
SOMA_DISCOVERY=0
SOMA_CNS_PULSE_ENABLED=0
```

`--debug` can be heavier, but not default.

---

# 15. Update `.env.example`

Add all new resource governor settings.

Also include a recommended low-load block for this host:

```env
# Recommended for i7-7700K / 14GB RAM / CPU-only runtime
SOMA_RESOURCE_GOVERNOR=1
SOMA_TICK_HZ=1
SOMA_TICK_HZ_MAX_NORMAL=2
SOMA_UI_FULL_PAYLOAD_HZ=0.5
SOMA_UI_LIGHT_TICK_HZ=1
SOMA_PROJECTOR_HZ_NORMAL=0.5
SOMA_PROJECTOR_HZ_REDUCED=0.2
SOMA_PROJECTOR_HZ_CRITICAL=0.05
SOMA_VECTOR_INTERPRETER_HZ=0.2
SOMA_CPP_PROJECTION_HZ=0.02
SOMA_CPP_SMOKE_TEST_INTERVAL_SEC=3600
SOMA_BIOS_INTERVAL_SEC=600
SOMA_BIOS_MAX_TASKS_PER_HOUR=4
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=4
SOMA_INTERNAL_LLM_MAX_PROMPT_CHARS=6000
SOMA_CNS_PULSE_ENABLED=0
SOMA_DISCOVERY_INTERVAL_SEC=600
```

---

# 16. Fix existing state bloat

Add script:

`scripts/compact_mind_state.py`

It must:

- inspect `data/mind/bios_state.json`
- inspect `data/mind/internal_loop_state.json`
- inspect `data/mind/self_model.json`
- archive huge originals
- compact prompt fields
- dedupe repeated learned facts if safe
- keep current usable state
- never delete without archive

CLI:

```bash
python3 scripts/compact_mind_state.py --dry-run
python3 scripts/compact_mind_state.py --apply
```

Run automatically on startup only if:

- `SOMA_AUTO_COMPACT_MIND_STATE=1`
- file size exceeds threshold

Default:

```env
SOMA_AUTO_COMPACT_MIND_STATE=1
SOMA_MIND_STATE_MAX_BYTES=262144
```

---

# 17. Tests

Add tests:

- `scripts/test_resource_governor.py`
- `scripts/test_budgeted_scheduler.py`
- `scripts/test_tick_throttling.py`
- `scripts/test_state_compaction.py`
- `scripts/test_payload_throttling.py`
- `scripts/test_resource_metabolism.py`
- `scripts/test_resource_bios_gating.py`

Required test cases:

## Resource governor

1. CPU 20%, RAM 40%, low lag → mode normal
2. CPU 60% → mode reduced
3. CPU 80% → mode critical
4. memory 88% → mode critical
5. event loop lag 1200ms → mode critical
6. stable again for recovery window → mode normal/reduced

## Scheduler

1. expensive operation is blocked before interval
2. cheap operation allowed
3. critical resource mode blocks heavy operation
4. scheduler status exposes next due time

## Tick throttling

1. policy target 5Hz but resource max 1Hz → runtime hz <= 1
2. manual UI set_hz cannot exceed resource max by default
3. reduced mode lowers projector frequency

## State compaction

1. 3MB internal_loop_state compacts under 64KB
2. full prompt archived, hash preserved
3. parsed JSON preserved
4. dry-run changes nothing

## Payload throttling

1. full payload not sent every tick
2. light payload sent on schedule
3. full payload sent on meaningful state change

## Resource-metabolism

1. host pressure increases metabolic stress
2. host pressure disables growth_allowed
3. host pressure blocks mutation
4. reward records growth_suspended_for_host_health

## BIOS gating

1. critical mode blocks internal LLM
2. reduced mode stretches BIOS interval
3. user active window makes BIOS yield
4. recovery task can still run if urgent

Run full validation:

```bash
cd /home/funboy/latent-somatic
python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py
python3 scripts/test_resource_governor.py
python3 scripts/test_budgeted_scheduler.py
python3 scripts/test_tick_throttling.py
python3 scripts/test_state_compaction.py
python3 scripts/test_payload_throttling.py
python3 scripts/test_resource_metabolism.py
python3 scripts/test_resource_bios_gating.py
python3 scripts/test_metabolism.py
python3 scripts/test_internal_loop.py
python3 scripts/test_bios_loop.py
python3 scripts/test_reward_engine.py
python3 scripts/test_power_policy.py
python3 scripts/test_vector_interpreter.py
python3 scripts/test_phase9_introspection.py
bash -n scripts/run.sh scripts/stop.sh
```

---

# 18. Live acceptance test

After implementation:

```bash
cd /home/funboy/latent-somatic
bash scripts/stop.sh
bash scripts/run.sh --safe
```

Then verify terminal remains responsive.

Run while Soma is active:

```bash
time echo ok
uptime
free -h
ps -eo pid,ppid,cmd,%cpu,%mem --sort=-%cpu | head -20
```

Expected:

- shell commands respond immediately
- no constant CPU saturation
- Soma server not monopolizing CPU
- UI remains usable
- resource topbar visible
- BIOS still runs slowly
- internal prompts still exist, but budgeted
- no huge `bios_state.json` or `internal_loop_state.json`

Ask in UI:

```text
what is your resource mode?
what are you throttling?
why did you pause or allow growth?
show performance profile
show resource governor status
```

Expected:

- deterministic answers from state
- no invented paths
- no generic body-state filler
- clear throttle reasons

---

# 19. Definition of done

This phase is complete only when:

1. Soma no longer makes the host sluggish during normal operation.
2. Terminal remains responsive while Soma is running.
3. ResourceGovernor exists and controls tick/UI/projector/BIOS/LLM/mutation budgets.
4. Policy target Hz can no longer force 5Hz if host budget says lower.
5. Full UI payload is throttled; light tick payload exists.
6. Projector/vector/C++ bridge are scheduled, not hot-looped.
7. `bios_state.json` and `internal_loop_state.json` stay compact.
8. Full internal prompts are archived, not repeatedly written into state JSON.
9. Host pressure feeds metabolic stress and can suspend growth/mutation.
10. BIOS yields under user activity or resource pressure.
11. Mutation cannot run unless resource mode is normal.
12. Reward records resource-preservation events.
13. UI shows resource mode, budget and throttled operations.
14. Introspection can explain throttling and resource mode.
15. Safe/low-power run modes work.
16. Tests pass.
17. Existing Phase 8/9 tests still pass.
18. `scripts/run.sh` and `scripts/stop.sh` still work.

---

# 20. Final behavioral target

Soma must be able to say:

```text
I am stable, but the host is under resource pressure. I am pausing growth, lowering my tick rate, reducing UI payloads, delaying BIOS LLM calls, and preserving the machine until pressure drops.
```

And when stable:

```text
Host pressure is low. Growth is allowed. I will run one budgeted internal task, record evidence, then sleep until the next budget window.
```

The organism must not consume the body that sustains it.
