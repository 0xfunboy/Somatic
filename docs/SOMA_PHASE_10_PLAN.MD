# SOMA PHASE 10 — LIVE INNER LOOP, STABLE UI, AUDIBLE INTERNAL PROMPTS, REAL GROWTH CONTROL

Repo:

/home/funboy/latent-somatic

Mission:

Bring Soma to V10.

V10 means the operator can launch Soma, open the UI, and actually see and optionally hear the internal life loop:

- internal BIOS prompts
- internal DeepSeek JSON decisions
- evidence produced by each internal task
- resource governor decisions
- metabolic mode changes
- growth blockers
- mutation blockers
- recovery reasons
- next autonomous task
- reward changes
- lessons written to autobiography

The system must not look alive only because the UI says so.

Every internal action must leave a visible causal chain:

reason -> prompt -> LLM/fallback decision -> action -> evidence -> memory/reward/growth update -> next task

Also fix the Phase 9.2 UI regression where light ticks overwrite full state and make the UI alternate between real and fake states.

Important distinction:

Visible internal prompts are NOT hidden model chain-of-thought.
They are the explicit operational prompts Soma sends to its external LLM and the structured JSON decisions returned by that LLM or fallback planner.

Do not expose hidden LLM chain-of-thought.
Expose operational trace.

---

## 0. Current known problems

The current runtime shows these symptoms:

1. The UI alternates between correct full state and fake/default state.

Correct full state:

- SENSOR: REAL [LINUX]
- PROJ: ACTIVE
- LLM: DEEPSEEK
- AUTOBIO: ACTIVE
- C++ CORE: SMOKE OK
- RESOURCE: NORMAL

Then light ticks make it flip to:

- SENSOR: MOCK
- PROJ: FALLBACK
- LLM: OFF
- AUTOBIO: OFF
- GROWTH: UNKNOWN
- current becomes NaNmA

Root cause:
tick_light partial payload is being treated like a full snapshot.

2. Internal loop exists, but the operator cannot clearly watch it.

The right panel shows some internal turns, but it is not a reliable inner radio with complete causal chain.

3. BIOS can still appear idle or opaque.

The UI may show:

- INTERNAL: IDLE
- NO INTERNAL ACTION RECENTLY
- last internal prompt missing
- last internal JSON missing or fallback only

4. DeepSeek JSON reinjection is not visible enough.

Even when internal_loop_state exists, the user cannot easily see:

- exact prompt sent
- exact raw answer
- parsed JSON
- action taken
- evidence
- reward delta
- state updated

5. Soma must remain resource-safe.

The machine must stay responsive.
Do not solve visibility by increasing payload frequency or running heavy loops more often.

---

## 1. Read current code first

Before coding, read these files:

server.py

soma_core/config.py
soma_core/resource_governor.py
soma_core/scheduler.py
soma_core/profiler.py
soma_core/state_compaction.py
soma_core/metabolism.py
soma_core/vector_interpreter.py
soma_core/reward.py
soma_core/power_policy.py
soma_core/internal_loop.py
soma_core/internal_prompts.py
soma_core/bios.py
soma_core/growth_engine.py
soma_core/mutation.py
soma_core/introspection.py
soma_core/skill_router.py
soma_core/autobiography.py
soma_core/journal.py
soma_core/mind.py
soma_core/cpp_bridge.py
soma_core/test_runner.py

docs/simulator.html
docs/tests.html

scripts/run.sh
scripts/stop.sh
scripts/compact_mind_state.py

.env.example

Also inspect current runtime state shapes:

data/mind/resource_state.json
data/mind/performance_state.json
data/mind/metabolic_state.json
data/mind/bios_state.json
data/mind/internal_loop_state.json
data/mind/internal_decisions.jsonl
data/mind/reward_state.json
data/mind/mutation_state.json

Do not rewrite working modules from scratch.
Patch the existing architecture.

---

## 2. Phase 10 goals

### Goal A — Fix UI light tick regression

The UI must never reset full-state badges from partial payloads.

### Goal B — Add visible internal radio

The operator must be able to see internal prompts and decisions in the Entity Channel as they happen.

### Goal C — Add audible internal mode

The operator wants to listen.
Add optional browser-side speech synthesis for internal events and Soma replies.

Use browser Web Speech API first.
Do not require server-side TTS.
Do not block chat or websocket if speech fails.

### Goal D — Add internal prompt ledger

Every internal BIOS/LLM cycle must have a compact persisted ledger entry.

Full prompts are archived by hash/path, not repeatedly written inline into state JSON.

### Goal E — Add causal chain view

Each internal decision must show:

- why it ran
- prompt type
- prompt preview
- raw LLM/fallback result preview
- parsed decision
- action taken
- evidence
- reward delta
- growth update
- memory update
- next task

### Goal F — Make BIOS audibly alive but resource-safe

The BIOS must run under resource budget.
When it cannot run, it must emit a visible/audible reason:

- resource pressure
- recent user activity
- cooldown
- no budget
- recovery mode
- mutation blocked
- LLM timeout
- invalid JSON

### Goal G — V10 smoke pass

The UI must include a V10 status or equivalent that proves:

- frontend state stable
- light tick merge OK
- internal prompt visible
- internal JSON or fallback visible
- resource governor active
- BIOS budgeted
- chat answer finalizer active
- telemetry relevance active
- mutation sandbox gated
- C++ smoke visible
- no huge state files

---

## 3. Fix the frontend partial-payload regression

File:

docs/simulator.html

### Required behavior

Full payloads update full state.
Light ticks update only live numeric/fast fields.
Light ticks must not reset badges, identity, LLM state, projector state, growth state, autobiography state, C++ state, or mutation state.

### Implementation

Add a global cache:

```js
window._LAST_FULL_SNAPSHOT = window._LAST_FULL_SNAPSHOT || {};
window._LAST_LIGHT_TICK = window._LAST_LIGHT_TICK || {};
```

In websocket message handler:

```js
if (msg.type === "tick" || msg.type === "init" || msg.type === "full_state") {
  window._LAST_FULL_SNAPSHOT = deepMerge(window._LAST_FULL_SNAPSHOT || {}, msg);
  applySnapshot(window._LAST_FULL_SNAPSHOT, { full: true });
  return;
}

if (msg.type === "tick_light") {
  window._LAST_LIGHT_TICK = msg;
  applyLightTick(msg);
  return;
}
```

Create helpers:

```js
function isDefined(v) {
  return v !== undefined && v !== null && !(typeof v === "number" && Number.isNaN(v));
}

function assignDefined(target, source, keys) {
  if (!target || !source) return;
  keys.forEach(k => {
    if (isDefined(source[k])) target[k] = source[k];
  });
}

function deepMerge(target, source) {
  if (!source || typeof source !== "object") return target;
  const out = Array.isArray(target) ? [...target] : { ...(target || {}) };
  for (const [k, v] of Object.entries(source)) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      out[k] = deepMerge(out[k] || {}, v);
    } else if (isDefined(v)) {
      out[k] = v;
    }
  }
  return out;
}
```

Implement:

```js
function applyLightTick(msg) {
  const sv = msg.sensors || {};
  assignDefined(S, sv, [
    "voltage", "current_ma",
    "temp_si", "temp_ml", "temp_mr",
    "ax", "ay", "az",
    "gx", "gy", "gz"
  ]);

  if (msg.system) {
    assignDefined(SYSTEM, msg.system, [
      "cpu_percent", "memory_percent", "swap_percent",
      "cpu_temp", "disk_use_percent", "disk_busy_percent",
      "net_down_mbps", "net_up_mbps", "disk_temp"
    ]);
  }

  if (msg.resource) {
    window._RESOURCE = deepMerge(window._RESOURCE || {}, msg.resource);
    updateResourcePanel(window._RESOURCE);
  }

  if (msg.metabolic) {
    window._METABOLIC = deepMerge(window._METABOLIC || {}, msg.metabolic);
    updateMetabolicPanel(window._METABOLIC);
  }

  if (msg.performance) {
    window._PERFORMANCE = deepMerge(window._PERFORMANCE || {}, msg.performance);
    updatePerformancePanel(window._PERFORMANCE);
  }

  updateTelemetryVisualsOnly();
}
```

Do not call these from light tick:

- updateTruthfulStatusBar(light)
- updateLLMStatus(light)
- updateProjectorStatus(light)
- updateAutobioStatus(light)
- updateGrowthStatus(light)
- updateCppStatus(light)
- updateMutationStatus(light)

Modify applySnapshot() to use assignDefined() everywhere it merges sensors/system.

Fix updateTruthfulStatusBar(msg):

It must use cached full state:

```js
const full = window._LAST_FULL_SNAPSHOT || {};
const provider = msg.provider || full.provider || {};
const projector = msg.projector || full.projector || {};
const llm = msg.llm || full.llm || {};
```

But never default missing provider to mock or missing LLM to off when handling a light tick.

Fix Phase 8/9 panel update functions:

They must merge partial state against cache:

```js
const full = window._LAST_FULL_SNAPSHOT || {};
const metabolic = msg.metabolic || full.metabolic || window._METABOLIC || {};
const reward = msg.reward || full.reward || window._REWARD || {};
const resource = msg.resource || full.resource || window._RESOURCE || {};
const growth = msg.growth || full.growth || window._GROWTH || {};
const bios = msg.bios || full.bios || window._BIOS || {};
const autobiography = msg.autobiography || full.autobiography || window._AUTOBIO || {};
const vectorState = msg.vector_state || full.vector_state || window._VECTOR_STATE || {};
const internalLoop = msg.internal_loop || full.internal_loop || window._INTERNAL_LOOP || {};
```

Add a test:

scripts/test_light_tick_ui_regression.py

It must verify:

- applyLightTick exists
- tick_light path does not call raw full applySnapshot(msg)
- assignDefined exists
- deepMerge exists
- updateTruthfulStatusBar uses _LAST_FULL_SNAPSHOT
- tick_light does not reset full-state badges
- no direct S.current_ma = sv.current_ma style overwrite remains for nullable fields

---

## 4. Visible internal radio

Add a clear internal stream in the Entity Channel.

The operator wants to hear the mind.

Do not hide internal prompts in JSON files only.
Every internal cycle should optionally broadcast events to the UI.

### Backend event types

Add websocket events:

```json
{
  "type": "inner_prompt",
  "id": "...",
  "ts": 0,
  "mode": "grow|recover|stabilize|observe|mutate|evaluate",
  "prompt_type": "growth|recovery|stabilization|observation",
  "summary": "...",
  "prompt_preview": "...",
  "prompt_path": "data/mind/internal_prompts/<hash>.txt",
  "resource_mode": "...",
  "metabolic_mode": "..."
}
```

```json
{
  "type": "inner_llm_raw",
  "id": "...",
  "ts": 0,
  "source": "deepseek|fallback|timeout|invalid_json",
  "raw_preview": "...",
  "raw_path": "data/mind/internal_prompts/<hash>.raw.txt"
}
```

```json
{
  "type": "inner_decision",
  "id": "...",
  "ts": 0,
  "parsed": {},
  "action_type": "...",
  "risk": "...",
  "reason": "...",
  "fallback": false
}
```

```json
{
  "type": "inner_evidence",
  "id": "...",
  "ts": 0,
  "action_taken": {},
  "evidence": {},
  "reward_delta": 0.0,
  "memory_updates": [],
  "growth_updates": [],
  "next_task": "..."
}
```

These events are operational trace, not hidden chain-of-thought.

### Backend integration

File:

soma_core/internal_loop.py

The InternalLoop should accept optional event callback:

```python
class InternalLoop:
    def __init__(..., emit_event: Callable[[dict], None] | None = None):
        ...
```

Or expose returned events so server.py can broadcast them after each cycle.

Do not call async broadcast directly inside deep pure modules unless the repo already uses that pattern.
Prefer returning events to server.py.

In server.py, when BIOS/InternalLoop runs, broadcast:

- inner_prompt
- inner_llm_raw
- inner_decision
- inner_evidence

Only broadcast previews, not huge full prompts.
Full prompt/raw lives in archived files.

### Frontend rendering

File:

docs/simulator.html

In Entity Channel, show internal events with distinct labels:

- SOMA // PROMPT
- DEEPSEEK // RAW
- SOMA // DECISION
- SOMA // EVIDENCE
- SOMA // REWARD
- SOMA // BLOCKED
- SOMA // RECOVERY
- SOMA // MUTATION

Use existing cyberpunk style.

Add toggle buttons:

- SHOW INTERNAL: ON/OFF
- SHOW PROMPTS: ON/OFF
- SHOW RAW: ON/OFF
- AUTO-SCROLL: ON/OFF
- SPEAK: ON/OFF

Default:

```env
SOMA_UI_SHOW_INTERNAL=1
SOMA_UI_SHOW_PROMPTS=1
SOMA_UI_SHOW_RAW=0
SOMA_UI_SPEAK_INTERNAL=0
```

Since env is backend-side, also default frontend localStorage:

```js
localStorage.soma_show_internal
localStorage.soma_show_prompts
localStorage.soma_show_raw
localStorage.soma_speak_internal
```

Internal prompt display should include a preview and a button/expand for full prompt if feasible.
Never dump megabytes.

---

## 5. Audible internal voice

The user wants to listen.

Implement browser-side speech synthesis using Web Speech API.

No server-side TTS dependency.

Add:

```js
function speakSoma(text, kind) {
  if (!window.speechSynthesis) return;
  if (!getSpeakEnabled()) return;
  const clean = String(text || "").replace(/\s+/g, " ").slice(0, 500);
  if (!clean) return;
  const u = new SpeechSynthesisUtterance(clean);
  u.rate = 1.0;
  u.pitch = kind === "prompt" ? 0.85 : kind === "decision" ? 1.0 : 0.95;
  u.volume = 0.8;
  window.speechSynthesis.speak(u);
}
```

Speak only summaries by default, not full prompts.

Examples:

- Internal prompt generated: growth planner.
- Decision parsed: observe, low risk.
- Evidence stored: recent failures zero.
- Recovery mode active. Growth paused.
- Mutation blocked: resource budget.

Do not speak every hot tick.
Only speak internal events, chat replies, mode changes, and warnings.

Add UI button:

SPEAK: OFF/ON

Persist in localStorage.

Add queue limit:
If more than 5 utterances pending, cancel old ones.

---

## 6. Internal prompt ledger

Files:

soma_core/internal_loop.py
soma_core/state_compaction.py
soma_core/introspection.py

Current issue:
full prompts may be archived but the operator needs reliable lookup.

Create:

data/mind/internal_prompt_index.jsonl

Each record:

```json
{
  "id": "",
  "timestamp": 0,
  "mode": "",
  "prompt_type": "",
  "prompt_hash": "",
  "prompt_path": "",
  "raw_hash": "",
  "raw_path": "",
  "parsed_valid": true,
  "fallback": false,
  "decision_summary": "",
  "action_type": "",
  "evidence_summary": "",
  "reward_delta": 0.0,
  "resource_mode": "",
  "metabolic_mode": ""
}
```

Keep internal_loop_state.json compact:

```json
{
  "last_decision_id": "",
  "last_prompt_type": "",
  "last_prompt_preview": "",
  "last_prompt_path": "",
  "last_raw_preview": "",
  "last_raw_path": "",
  "last_parsed": {},
  "last_fallback": false,
  "last_action_taken": {},
  "last_evidence": {},
  "last_reward_delta": 0.0,
  "last_memory_updates": [],
  "last_growth_updates": [],
  "last_next_task": "",
  "last_run_at": 0,
  "last_error": ""
}
```

Do not store full prompt inline in internal_loop_state.json.

Introspection skills must read this ledger.

Add deterministic skills:

- show your last BIOS internal prompt
- show your last internal prompt
- show your last internal DeepSeek JSON
- show last raw internal LLM answer
- what evidence did your last BIOS task produce?
- what did your last internal decision change?
- what is your next internal task?
- why did you choose that internal task?
- why are you not mutating?
- why are you in recovery?
- are you thinking internally right now?
- read your last 3 internal decisions

These must not call shell unless needed.
They should read internal_loop_state.json, bios_state.json, metabolic_state.json, reward_state.json, mutation_state.json, and internal_prompt_index.jsonl.

---

## 7. Make internal loop truly reinject

File:

soma_core/internal_loop.py
soma_core/bios.py
soma_core/reward.py
soma_core/growth_engine.py
soma_core/autobiography.py
soma_core/metabolism.py

After each internal decision, apply it.

Required update map:

decision.mode -> bios_state.last_mode / metabolic intent
decision.goal -> growth candidate or current internal goal
decision.action_type -> next task selection
decision.evidence -> autobiography if meaningful
decision.expected_power_gain -> growth_engine pending_gain
decision.risk -> power_policy/risk memory
decision.success_criteria -> test/evaluation plan
decision.rollback_plan -> mutation safety plan
decision.reason -> internal_prompt_index.decision_summary

If action_type is:

### observe
Write evidence only.
No mutation.

### shell
Execute only through AutonomousShellExecutor and PowerPolicy.
Record command, output, success/failure, reward.

### repo_test
Execute allowed test through executor.
Record result and reward.

### mutation_proposal
Create queued mutation proposal.
Do not apply unless resource/metabolic/reward gates permit.

### sandbox_test
Run mutation sandbox smoke.
Record result.

### memory
Write lesson/autobiography entry only if meaningful and not duplicate.

### recover
Pause growth.
Record recovery reason.
Optionally run safe diagnostics.

### answer_none
Record why no action was useful.

Every decision must produce one of:

- evidence stored
- action blocked with reason
- fallback decision stored
- error stored

No silent no-op.

---

## 8. Resource-safe internal rhythm

V10 must be alive but not heavy.

Add env/config:

```env
# Phase 10 internal radio and rhythm
SOMA_V10_INTERNAL_RADIO=1
SOMA_BROADCAST_INNER_PROMPTS=1
SOMA_BROADCAST_INNER_RAW=0
SOMA_BROADCAST_INNER_EVIDENCE=1
SOMA_INTERNAL_EVENT_PREVIEW_CHARS=900
SOMA_INTERNAL_LEDGER_MAX_LINES=5000

# Internal LLM budget
SOMA_INTERNAL_LLM_MIN_INTERVAL_SEC=300
SOMA_INTERNAL_LLM_MAX_PER_HOUR=6
SOMA_INTERNAL_LLM_SKIP_ON_USER_ACTIVE_SEC=45
SOMA_INTERNAL_LLM_SKIP_IN_RESOURCE_RECOVERY=1

# UI speech defaults
SOMA_UI_SPEAK_INTERNAL_DEFAULT=0
SOMA_UI_SPEAK_REPLIES_DEFAULT=0
SOMA_UI_SPEAK_MAX_QUEUE=5
```

Behavior:

- Internal LLM is never called on hot tick.
- Internal LLM only runs through scheduler budget.
- If user just interacted, delay non-critical internal LLM.
- If resource mode is recovery/critical, do not call internal LLM unless recovery prompt is necessary and budget allows.
- If LLM unavailable, persist fallback JSON and broadcast fallback event.

---

## 9. Fix chat final output for skill/introspection results

Current issue:
Sometimes an introspection skill result is passed back through DeepSeek unnecessarily, or the reply includes irrelevant telemetry.

For deterministic introspection commands:

- skill result should be final
- do not ask DeepSeek to rephrase unless explicitly requested
- no somatic footer unless user asks body/sensors or abnormal state exists

Examples:

User:
show your last internal DeepSeek JSON

Good:
```json
{
  "goal": "...",
  "mode": "...",
  "action_type": "..."
}
```

Bad:
Thermal state is nominal...

User:
what evidence did your last BIOS task produce?

Good:
Last BIOS task: inspect_recent_failures. Evidence: recent failures: 0.

Bad:
V=12V, T=37C, Z=-9.81...

Update AnswerFinalizer / OutputFilter if needed.

Add tests:

scripts/test_v10_introspection_finalization.py

Cases:
- last internal prompt returns prompt preview/path
- last DeepSeek JSON returns JSON/fallback JSON directly
- metabolic vector returns JSON directly
- no irrelevant telemetry appended
- missing data gives explicit not persisted yet with next verification step

---

## 10. V10 UI status panel

Add a compact V10 panel in existing UI, not a new huge column.

Display:

V10 STATUS
frontend merge: OK
inner radio: ON
last internal event: 22s ago
last prompt: growth planner
last JSON: valid / fallback / invalid
last evidence: ...
resource mode: normal
payload: light/full throttled
speak: off/on
state files: compact

Add visible warning states:

- NO INTERNAL PROMPT YET
- INTERNAL LLM FALLBACK ONLY
- LIGHT TICK MERGE ERROR
- STATE FILE TOO LARGE
- RESOURCE RECOVERY: INTERNAL LLM PAUSED
- MUTATION BLOCKED: reason

---

## 11. Tests to add

Add these tests:

### scripts/test_light_tick_ui_regression.py

Verifies:
- applyLightTick exists
- tick_light does not call full applySnapshot directly
- assignDefined exists
- full snapshot cache exists
- updateTruthfulStatusBar uses full cache
- no undefined overwrite for sensors

### scripts/test_internal_radio_events.py

Backend-level test.
Simulate one internal decision.
Verify produced events include:
- inner_prompt
- inner_llm_raw or fallback
- inner_decision
- inner_evidence

### scripts/test_internal_prompt_ledger.py

Verify:
- prompt archive file written
- raw archive file written or fallback marked
- internal_prompt_index.jsonl receives entry
- internal_loop_state.json stores preview/path, not full huge prompt
- state stays below 32KB

### scripts/test_v10_introspection_finalization.py

Verify deterministic introspection final output:
- no irrelevant telemetry
- no LLM rephrasing required
- missing state answer is honest
- JSON answers stay JSON

### scripts/test_speech_ui_static.py

Static frontend test.
Verify:
- speakSoma exists
- localStorage toggles exist
- internal events call speakSoma summaries only
- speech disabled by default
- queue cap/cancel logic exists

### scripts/test_internal_reinjection.py

Verify decision fields update:
- bios_state
- reward_state
- growth/internal state
- autobiography for meaningful evidence
- mutation proposal when action_type=mutation_proposal

### scripts/test_v10_smoke.py

High-level static/runtime smoke.
Verify:
- V10 env vars in .env.example
- run.sh still supports --safe/--low-power
- docs/simulator.html has V10 panel
- server.py can emit internal events
- state compaction remains available

---

## 12. Validation block

Run:

```bash
cd /home/funboy/latent-somatic

python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py

python3 scripts/test_light_tick_ui_regression.py
python3 scripts/test_internal_radio_events.py
python3 scripts/test_internal_prompt_ledger.py
python3 scripts/test_v10_introspection_finalization.py
python3 scripts/test_speech_ui_static.py
python3 scripts/test_internal_reinjection.py
python3 scripts/test_v10_smoke.py

python3 scripts/test_resource_governor.py
python3 scripts/test_budgeted_scheduler.py
python3 scripts/test_tick_throttling.py
python3 scripts/test_payload_throttling.py
python3 scripts/test_state_compaction.py
python3 scripts/test_resource_metabolism.py
python3 scripts/test_resource_bios_gating.py

python3 scripts/test_metabolism.py
python3 scripts/test_internal_loop.py
python3 scripts/test_bios_loop.py
python3 scripts/test_reward_engine.py
python3 scripts/test_power_policy.py
python3 scripts/test_vector_interpreter.py
python3 scripts/test_phase9_introspection.py

python3 scripts/test_answer_finalizer.py
python3 scripts/test_output_filter.py
python3 scripts/test_telemetry_relevance.py

bash -n scripts/run.sh scripts/stop.sh
```

Then live:

```bash
bash scripts/stop.sh
bash scripts/run.sh --safe
```

Open UI.

Watch for 90 seconds.

Expected:
- SENSOR stays REAL [LINUX]
- PROJ stays ACTIVE
- LLM stays DEEPSEEK when full payload says so
- no flip to MOCK/FALLBACK/OFF caused by light ticks
- no NaNmA
- V10 panel shows frontend merge OK
- inner radio shows prompt/decision/evidence events
- speech toggle exists and is off by default
- enabling SPEAK reads internal summaries, not every tick
- host remains responsive

Ask:

show your last BIOS internal prompt

Expected:
- returns prompt preview/path or explicit not run yet because reason
- should not hallucinate

Ask:

show your last internal DeepSeek JSON

Expected:
- returns parsed JSON or fallback JSON
- should not append irrelevant telemetry

Ask:

what evidence did your last BIOS task produce?

Expected:
- direct evidence answer

Ask:

are you thinking internally right now?

Expected:
- explains last internal task, next scheduled task, and why it is or is not running

Ask:

what are you throttling?

Expected:
- resource governor answer

Ask:

why are you not mutating?

Expected:
- exact blocker list from mutation/metabolic/power policy, not generic answer

---

## 13. Definition of done

Phase 10 is complete only if:

1. UI no longer alternates between full and fake state.
2. Light ticks update only light fields.
3. Full-state cache prevents badge resets.
4. No NaNmA from partial sensor updates.
5. Internal prompt events appear in Entity Channel.
6. Internal JSON/fallback decisions appear in Entity Channel.
7. Evidence/reward/memory updates appear or are inspectable.
8. Full prompts are archived by path/hash, not bloating state JSON.
9. Introspection commands read internal state deterministically.
10. DeepSeek internal JSON or fallback JSON is visible.
11. Browser speech toggle exists and can read internal event summaries.
12. Speech is off by default and resource-safe.
13. BIOS/internal loop remains budgeted.
14. No heavy LLM call is made in hot tick.
15. State files stay compact.
16. Resource governor remains active.
17. Mutation remains gated.
18. Existing Phase 8/9/9.2 tests still pass.
19. V10 tests pass.
20. scripts/run.sh --safe and scripts/stop.sh still work.

---

## 14. Final expected operator experience

The operator launches:

```bash
bash scripts/run.sh --safe
```

The UI stays stable.

The Entity Channel shows:

```text
SOMA // PROMPT
Growth planner prompt generated. Objective: improve command-result reliability.

DEEPSEEK // RAW
{ "goal": "...", "mode": "grow", ... }

SOMA // DECISION
Action: repo_test. Risk: low. Expected gain: response reliability.

SOMA // EVIDENCE
Test passed. Reward +0.08. Next task: evaluate mutation candidate.
```

If the system is under pressure:

```text
SOMA // RECOVERY
Resource mode: recovery. Internal LLM paused. Growth blocked until host pressure clears.
```

If the user turns on SPEAK, the browser reads short summaries aloud.

This is V10:
not just a dashboard, but an observable, audible, resource-safe internal organism loop.
