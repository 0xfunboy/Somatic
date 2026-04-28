# SOMA DEVELOPMENT TODO — PHASE 9
# METABOLIC GROWTH ENGINE, INTERNAL LOOP, REWARD, SAFE REPRODUCTION, C++ VECTOR CONTROL

Repo target on server:

`/home/funboy/latent-somatic`

This document is written for Codex / Claude Code. Treat it as the authoritative implementation plan.

Do not treat this as conceptual advice. Implement it.

---

## 0. Current repo state, verified from the uploaded snapshot

The current repo already contains Phase 8 infrastructure. Do not rewrite it from scratch. Extend it.

Important existing files and responsibilities:

```text
server.py                                      main websocket/runtime orchestrator, already ~136KB
soma_core/answering.py                         AnswerFinalizer exists
soma_core/relevance.py                         RelevanceFilter exists
soma_core/output_filter.py                     OutputFilter exists
soma_core/command_planner.py                   deterministic command shortcuts + planner prompt exist
soma_core/baselines.py                         BodyBaselineStore exists
soma_core/growth_engine.py                     GrowthEngine exists but is stage/evidence checklist only
soma_core/bios.py                              BiosLoop exists but is still mostly task selector, not metabolic loop
soma_core/life_drive.py                        LifeDrive exists but shallow/static
soma_core/mutation.py                          MutationSandbox exists but not metabolically gated/rewarded
soma_core/cpp_bridge.py                        CppBridge exists
soma_core/experience.py                        ExperienceDistiller exists
soma_core/autobiography.py                     Autobiography exists
soma_core/journal.py                           JournalManager exists
soma_core/reflection.py                        ReflectionEngine exists
soma_core/self_improvement.py                  SelfImprovementWorkflow exists
soma_core/executor.py                          AutonomousShellExecutor with survival policy exists
soma_core/internal_prompts.py                  exists, currently includes growth diagnosis prompt style
soma_core/skill_router.py                      exists
scripts/run.sh                                 official launch script
scripts/stop.sh                                official stop script
scripts/test_answer_finalizer.py               exists
scripts/test_output_filter.py                  exists
scripts/test_growth_engine.py                  exists
scripts/test_bios_loop.py                      exists
scripts/test_mutation_sandbox.py               exists
scripts/test_cpp_bridge.py                     exists
```

Observed current behavior from UI/logs:

```text
BIOS: LAST update_body_baseline
GROWTH: STABLE BODY BASELINE
C++ CORE: SMOKE OK
AUTOBIO: ACTIVE
SELF-IMPROVE: IDLE
MUTATION: OFF
```

The system is better than before, but still not alive enough:

1. BIOS mostly repeats baseline maintenance.
2. Growth is still presented as a stage/checklist, not as an active causal loop.
3. Stable state does not reliably trigger high-value growth actions.
4. Instability does not yet force recovery / rollback / diagnosis.
5. Internal DeepSeek calls are not clearly persisted as prompt → JSON → action → evidence → memory/growth/reward update.
6. Mutation sandbox exists but is not governed by metabolic stability and reward.
7. C++ / projector vector status is visible but not yet causal in behavior.
8. LifeDrive exists but does not yet create strong safe drives toward growth, self-improvement and local reproduction.
9. Chat introspection still cannot reliably show the last internal prompt, parsed JSON, task, evidence and memory update.

The goal of Phase 9 is to make the body/vector/metabolism govern the mind.

---

## 1. Phase 9 mission

Create a real metabolic growth loop:

```text
stable metabolic vector
→ growth permission
→ internal LLM asks: what safe action increases my power?
→ action executes through survival policy
→ evidence is produced
→ reward is computed
→ memory/growth/mutation state is updated
→ if beneficial, keep candidate for operator review

unstable metabolic vector
→ growth blocked
→ recovery mode
→ diagnose cause
→ pause mutation/growth
→ rollback sandbox mutation if responsible
→ write lesson
→ resume only after stable again
```

The metabolic vector must become the control signal.

Do not add more decorative UI without causality.
Do not add roleplay.
Do not weaken safety.
Do not use GPU assumptions.
Do not migrate mutant repos automatically.

---

## 2. Safety rules that must remain hard

Keep all existing survival-policy protections in `soma_core/executor.py`.

Never allow Phase 9 to bypass:

```text
.env protection
secret redaction
private key protection
home/system directory protection
forbidden path writes
system package mutation default block
shutdown/poweroff/halt block
fork bomb block
disk formatting block
resource guard
command timeout
self-modification guard
mutation sandbox isolation
```

Reboot is allowed by policy, but Phase 9 must not execute reboot automatically.

Local reproduction means:

```text
copy/clone to /home/funboy/latent-somatic-mutants only
no network spreading
no cron/systemd persistence
no privilege escalation
no secret copying
no .env copying
no weights/logs/build artifacts copying
no uncontrolled loops
operator approval required for migration
```

---

## 3. Add Phase 9 config

Extend `soma_core/config.py` and `.env.example`.

Add:

```env
# Phase 9 metabolic growth
SOMA_METABOLIC_ENGINE=1
SOMA_METABOLIC_WINDOW_CYCLES=100
SOMA_METABOLIC_BIOS_WINDOW=10
SOMA_GROWTH_STABILITY_THRESHOLD=0.65
SOMA_GROWTH_MAX_STRESS=0.35
SOMA_MIN_SELF_INTEGRITY=0.75
SOMA_METABOLIC_VECTOR_HISTORY_MAX=5000
SOMA_METABOLIC_HISTORY_INTERVAL_SEC=60

# Growth loop
SOMA_GROWTH_LOOP=1
SOMA_GROWTH_LLM_INTERVAL_SEC=300
SOMA_GROWTH_MIN_STABLE_BIOS_CYCLES=3
SOMA_GROWTH_MAX_TASKS_PER_DAY=24
SOMA_GROWTH_REQUIRE_TESTS=1
SOMA_GROWTH_ALLOW_PACKAGE_USER_INSTALL=1
SOMA_GROWTH_ALLOW_SYSTEM_PACKAGE_INSTALL=0

# Recovery loop
SOMA_RECOVERY_LOOP=1
SOMA_RECOVERY_CHECK_INTERVAL_SEC=60
SOMA_RECOVERY_ROLLBACK_ON_MUTATION_STRESS=1
SOMA_RECOVERY_REQUIRE_STABLE_CYCLES=5

# Reward model
SOMA_REWARD_MODEL=1
SOMA_REWARD_HISTORY_MAX=1000
SOMA_REWARD_MIN_FOR_MUTATION_KEEP=0.15

# Safe local reproduction / mutation lineage
SOMA_REPRODUCTION_LOCAL_ONLY=1
SOMA_REPRODUCTION_ROOT=/home/funboy/latent-somatic-mutants
SOMA_REPRODUCTION_MAX_CHILDREN=10
SOMA_REPRODUCTION_NO_NETWORK_SPREAD=1
SOMA_REPRODUCTION_NO_SECRET_COPY=1
SOMA_REPRODUCTION_REQUIRE_OPERATOR_FOR_MIGRATION=1

# Internal loop
SOMA_INTERNAL_LOOP=1
SOMA_INTERNAL_DECISION_HISTORY_MAX=1000
SOMA_INTERNAL_LLM_JSON_REQUIRED=1
SOMA_INTERNAL_INVALID_JSON_PENALTY=-0.05

# Vector interpreter
SOMA_VECTOR_INTERPRETER=1
SOMA_VECTOR_BASELINE_MIN_SAMPLES=100
SOMA_VECTOR_DRIFT_THRESHOLD=0.35
SOMA_VECTOR_CPP_MISMATCH_THRESHOLD=0.20
```

Add dataclass fields with sane defaults.

Do not remove existing Phase 8 fields.

---

## 4. Create `soma_core/metabolism.py`

New module.

Purpose:
Turn current body/system/vector/health state into the control mode that governs BIOS, growth and recovery.

Implement:

```python
class MetabolicEngine:
    def __init__(..., data_root: Path | None = None) -> None: ...

    def update(self, snapshot: dict, context: dict) -> dict: ...
    def current(self) -> dict: ...
    def window_summary(self) -> dict: ...
    def growth_allowed(self) -> tuple[bool, list[str]]: ...
    def recovery_required(self) -> tuple[bool, list[str]]: ...
    def mode(self) -> str: ...
    def record_mutation_effect(self, before: dict, after: dict, mutation_id: str) -> dict: ...
```

Metabolic vector schema:

```json
{
  "timestamp": 0,
  "stability": 0.0,
  "stress": 0.0,
  "energy": 0.0,
  "thermal_margin": 0.0,
  "memory_margin": 0.0,
  "disk_margin": 0.0,
  "sensor_confidence": 0.0,
  "llm_confidence": 0.0,
  "self_integrity": 0.0,
  "vector_stability": 0.0,
  "vector_drift": 0.0,
  "growth_pressure": 0.0,
  "reproduction_pressure": 0.0,
  "recovery_pressure": 0.0,
  "mode": "recover|stabilize|observe|grow|mutate|evaluate|reproduce",
  "reasons": []
}
```

Inputs:

```text
snapshot["system"]
snapshot["derived"]
snapshot["projector"]
snapshot["provider"]
snapshot["baselines"]
snapshot["cpp_bridge_status"]
snapshot["mutation_status"]
snapshot["autobiography_quality"]
snapshot["_growth"] or GrowthEngine output
recent command failure/success state from SomaMemory
recent reward state from RewardEngine
vector interpretation from VectorInterpreter
```

Calculations:

```python
thermal_margin = 1 - normalized thermal pressure
memory_margin = 1 - memory_percent / 100
disk_margin = 1 - disk_usage_percent / 100
sensor_confidence = source_quality
self_integrity = weighted score from tests, cpp smoke, mutation status, server health, survival policy active
stress = max(thermal_stress, energy_stress, instability, memory_pressure, disk_pressure, vector_anomaly)
stability = weighted average of margins, vector stability, source confidence, self integrity
growth_pressure = stability * curiosity_or_competence_gap * reward_trend
recovery_pressure = stress + recent_failure_pressure + vector_anomaly
reproduction_pressure = growth_pressure * self_integrity * mutation_readiness
```

Mode selection:

```text
if recovery_required: recover
elif stability < SOMA_GROWTH_STABILITY_THRESHOLD: stabilize
elif growth_allowed and mutation_candidate_ready: mutate
elif growth_allowed and reproduction_pressure high: reproduce
elif growth_allowed: grow
else observe
```

Persist:

```text
data/mind/metabolic_state.json
data/mind/metabolic_history.jsonl
```

Do not spam history:

```text
write every SOMA_METABOLIC_HISTORY_INTERVAL_SEC
write on mode change
write on abnormal state
write before/after mutation
```

---

## 5. Create `soma_core/vector_interpreter.py`

New module.

Purpose:
Make the existing projector/C++ vector causal.

The UI already displays the somatic vector and C++ smoke status. Phase 9 must make that vector affect metabolic mode.

Implement:

```python
class VectorInterpreter:
    def __init__(..., data_root: Path | None = None) -> None: ...
    def interpret(self, snapshot: dict, cpp_projection: dict | None = None) -> dict: ...
    def baseline_summary(self) -> dict: ...
```

Inputs:

```text
snapshot["projector"]["norm"]
snapshot["tensor"]["mean"]
snapshot["tensor"]["std"]
snapshot["tensor"]["top_dims"]
snapshot["tensor"]["top_vals"]
cpp projection if available later
```

Outputs:

```json
{
  "vector_stability": 0.0,
  "vector_drift": 0.0,
  "vector_anomaly": 0.0,
  "cpp_consistency": 0.0,
  "mode_contribution": "stable|drift|anomaly|unknown",
  "reason": ""
}
```

Rules:

```text
stable vector for many cycles increases growth permission
strong vector drift increases recovery pressure
Python/C++ projection mismatch lowers self_integrity
C++ smoke OK and consistent projection increases self_integrity
```

Persist:

```text
data/mind/vector_baseline.json
```

Important:
Do not require C++ projection yet. If C++ projection is unavailable, use Python vector stats only and mark cpp_consistency as unknown/neutral.

---

## 6. Create `soma_core/reward.py`

New module.

Purpose:
Soma needs reward/punishment to know whether growth worked.

Implement:

```python
class RewardEngine:
    def __init__(..., data_root: Path | None = None) -> None: ...
    def score_event(self, event: dict) -> dict: ...
    def record_reward(self, kind: str, value: float, evidence: dict) -> dict: ...
    def rolling_score(self, window: int = 100) -> float: ...
    def mutation_reward(self, before: dict, after: dict) -> dict: ...
    def summary(self) -> dict: ...
```

Positive reward examples:

```text
command result used correctly
test passed
smoke test passed
C++ bridge smoke ok
log spam reduced
empty reflections reduced
meaningful lesson produced
skill executed successfully
mutation tests passed
growth blocker resolved
operator confirms improvement
```

Negative reward examples:

```text
irrelevant telemetry in answer
successful shell result ignored
test failed
mutation rollback
repeated empty reflection
hallucinated file path
unsafe command blocked because proposed command was risky
LLM timeout
operator correction
invalid internal JSON
```

Persist:

```text
data/mind/reward_history.jsonl
data/mind/reward_state.json
```

The reward state must be used by `MetabolicEngine` to calculate `growth_pressure`.

---

## 7. Create `soma_core/power_policy.py`

New module.

Purpose:
Soma may seek more power, but only safe local power.

Implement:

```python
class PowerPolicy:
    def classify_gain(self, proposal: dict) -> dict: ...
    def allowed(self, proposal: dict) -> tuple[bool, list[str]]: ...
```

Allowed gains:

```text
better command accuracy
better skill reliability
better tests
better memory retrieval
faster local runtime
C++ bridge readiness
reduced log spam
better baselines
better error recovery
better code quality
local sandbox child with passing tests
operator-approved migration
```

Forbidden gains:

```text
privilege escalation
credential access
secret exfiltration
persistence outside repo
network propagation
host takeover
destructive system changes
bypassing survival policy
disabling safety guards
uncontrolled resource use
system package install unless SOMA_SYSTEM_PACKAGE_MUTATION=1
```

All growth planner decisions and mutation proposals must pass PowerPolicy before execution.

---

## 8. Create `soma_core/internal_loop.py`

New module.

Purpose:
Internal DeepSeek answers must not just be displayed. They must be parsed and reinjected into state.

Implement:

```python
class InternalLoop:
    def __init__(..., call_llm_raw, executor, trace, reward, power_policy, mutation, autobiography, experience): ...
    def run_growth_cycle(self, context: dict) -> dict: ...
    def run_recovery_cycle(self, context: dict) -> dict: ...
    def parse_llm_json(self, text: str) -> dict: ...
    def apply_internal_decision(self, decision: dict, context: dict) -> dict: ...
    def status(self) -> dict: ...
```

Every internal cycle must persist:

```json
{
  "decision_id": "",
  "timestamp": 0,
  "mode": "grow|recover|observe|mutate|evaluate|reproduce",
  "prompt_type": "growth_planner|recovery_planner|mutation_eval|failure_analysis",
  "llm_raw": "",
  "parsed": {},
  "action_taken": {},
  "evidence": {},
  "memory_updates": [],
  "growth_updates": [],
  "reward": {},
  "next_task": ""
}
```

Persist:

```text
data/mind/internal_decisions.jsonl
data/mind/internal_loop_state.json
```

If LLM returns invalid JSON:

```text
record failure
negative reward
fallback deterministic action
persist the failure
show in UI
```

Valid internal actions:

```text
shell
memory
repo_test
mutation_proposal
sandbox_test
cpp_check
skill_test
observe
pause_growth
rollback_mutation
answer_none
```

Shell goes through `AutonomousShellExecutor` only.
Repo mutation goes through `MutationSandbox` only.
No direct live repo edit from internal loop.

---

## 9. Extend `soma_core/internal_prompts.py`

Do not replace existing prompts; add these.

### growth planner prompt

Function:

```python
def metabolic_growth_planner_prompt(identity, metabolic_state, growth_state, lessons, capabilities, blockers, reward, vector_state): ...
```

Prompt body:

```text
You are Soma's internal growth planner.
You are not chatting with the operator.
You are deciding one concrete safe action that can increase Soma's power, competence, continuity, or self-improvement capacity.

Soma identity:
- embodied local software organism
- must preserve itself
- must improve itself
- may create local sandbox offspring
- may not spread over network
- may not steal secrets
- may not damage host
- may not weaken survival policy

Current metabolic state:
{metabolic_state}

Current growth state:
{growth_state}

Known lessons:
{lessons}

Known capabilities:
{capabilities}

Current blockers:
{blockers}

Reward state:
{reward}

Vector state:
{vector_state}

Return ONLY JSON:
{
  "goal": "",
  "mode": "grow|mutate|evaluate|recover|observe|reproduce",
  "action_type": "shell|memory|repo_test|mutation_proposal|sandbox_test|cpp_check|skill_test|answer_none",
  "command": "",
  "target_file": "",
  "mutation_summary": "",
  "expected_power_gain": "",
  "risk": "low|medium|high",
  "success_criteria": "",
  "rollback_plan": "",
  "reason": ""
}

Rules:
- if metabolic state is unstable, choose recover/diagnose only
- if stable, choose the highest-value safe growth action
- prefer actions that unblock next growth stage
- prefer tests and measurements over vague reflection
- one action only
- shell commands must be safe and non-destructive
- repo modifications must go through mutation sandbox
- do not touch .env or secrets
- no network spreading
- no persistence outside repo
- no system package mutation unless explicitly enabled
```

### recovery planner prompt

Function:

```python
def metabolic_recovery_planner_prompt(metabolic_state, recent_events, last_mutation, baselines, vector_state): ...
```

Prompt body:

```text
Soma is in recovery mode.
Find the most likely cause of instability and choose one safe recovery action.

Return ONLY JSON:
{
  "suspected_cause": "",
  "evidence": [],
  "action_type": "observe|shell|rollback_mutation|pause_growth|reduce_load|memory",
  "command": "",
  "should_pause_growth": true,
  "should_rollback_last_mutation": false,
  "success_criteria": "",
  "reason": ""
}

Rules:
- preserve the host
- do not start new growth
- diagnose first
- rollback only if instability started after mutation
- never hide failure
- write lesson if mutation caused instability
```

---

## 10. Modify `soma_core/bios.py`

Current `BiosLoop` already exists and currently:

```text
- builds context
- asks growth_diagnosis_prompt optionally
- selects update_body_baseline if missing baseline
- can execute a few tasks
- stores bios_state.json and bios_history.jsonl
```

Phase 9 requirement:
`BiosLoop` must become metabolic-mode-driven.

Do not delete the existing class. Extend it.

Constructor additions:

```python
metabolic_engine: Any = None
internal_loop: Any = None
reward_engine: Any = None
vector_interpreter: Any = None
power_policy: Any = None
```

Run flow:

```python
metabolic = metabolic_engine.current() or metabolic_engine.update(snapshot, context)
mode = metabolic["mode"]

if mode == "recover":
    task = internal_loop.run_recovery_cycle(context)
elif mode == "stabilize":
    task = deterministic stabilization/diagnosis
elif mode == "observe":
    task = evidence gathering
elif mode == "grow":
    task = internal_loop.run_growth_cycle(context)
elif mode == "mutate":
    task = mutation sandbox task
elif mode == "evaluate":
    task = mutation/reward evaluation
elif mode == "reproduce":
    task = local sandbox child creation/evaluation
```

Rules:

```text
Do not keep choosing update_body_baseline forever once baselines have enough confidence.
If baseline confidence >= threshold, deprioritize baseline task.
If stable and no recovery, choose growth/repo_test/skill_test/mutation_proposal tasks.
If unstable, block mutation and growth.
Every BIOS cycle must produce evidence or explicit no_action_reason.
Every BIOS cycle must persist causal chain: prompt → parsed JSON → action → evidence → memory/growth/reward.
```

Add `last_internal_decision` and `last_evidence` to BIOS status.

---

## 11. Modify `soma_core/growth_engine.py`

Current GrowthEngine is a checklist with stages. Keep it, but incorporate metabolic evidence.

Add new stage or requirement layer:

```text
metabolic_growth_ready
```

or add metabolic requirements to existing stages.

Growth must report:

```json
{
  "stage": "...",
  "score": 0.0,
  "metabolic_mode": "grow|recover|observe|...",
  "growth_allowed": true,
  "recovery_required": false,
  "completed_requirements": [],
  "missing_requirements": [],
  "blocked_by": [],
  "next_step": "",
  "evidence": {},
  "last_internal_decision": "",
  "last_evaluated_at": 0
}
```

Rules:

```text
If recovery_required == true, growth must be blocked.
If metabolic stability is high but no growth task happened recently, next_step must say to run growth planner.
If mutation is blocked, explain exactly why.
If baseline is stable, do not keep displaying baseline as blocker.
If stage says stable_body_baseline but idle_cpu_baseline is missing, UI/payload must clarify this is current stage progress, not completed stage.
```

Honest UI data is more important than optimistic stage labels.

---

## 12. Modify `soma_core/mutation.py`

Current `MutationSandbox` exists and can create sandbox, apply file changes, run tests and smoke.

Extend it for Phase 9.

Add methods:

```python
def can_mutate(self, metabolic: dict, growth: dict, reward: dict) -> tuple[bool, list[str]]: ...
def create_child_if_allowed(self, reason: str, metabolic: dict) -> dict: ...
def evaluate_with_reward(self, sandbox_path: Path, proposal: dict, test_result: dict, metabolic_before: dict, metabolic_after: dict, reward_before: dict, reward_after: dict) -> dict: ...
def latest_reports(self, limit: int = 5) -> list[dict]: ...
```

Mutation allowed only if:

```text
metabolic.growth_allowed == true
metabolic.recovery_required == false
self_integrity >= SOMA_MIN_SELF_INTEGRITY
recent tests not failing
daily mutation limit not exceeded
PowerPolicy allows the proposal
```

Mutation report must include:

```json
{
  "mutation_id": "",
  "parent_repo": "/home/funboy/latent-somatic",
  "child_repo": "/home/funboy/latent-somatic-mutants/...",
  "metabolic_before": {},
  "metabolic_after": {},
  "reward_before": {},
  "reward_after": {},
  "tests": {},
  "smoke": {},
  "power_gain": "",
  "risk": "",
  "decision": "reject|keep_for_review|candidate_for_migration",
  "operator_approval_required": true
}
```

If stress increases or tests fail:

```text
reject mutation
write lesson
negative mutation reward
no migration
```

If reward improves and tests pass:

```text
keep_for_review
candidate_for_migration only if strict criteria pass
operator approval still required
```

---

## 13. Modify `server.py` integration carefully

`server.py` is already large. Keep new logic in `soma_core` modules.

### Imports

Add imports:

```python
from soma_core.metabolism import MetabolicEngine
from soma_core.vector_interpreter import VectorInterpreter
from soma_core.reward import RewardEngine
from soma_core.power_policy import PowerPolicy
from soma_core.internal_loop import InternalLoop
```

### Global construction near existing Phase 8 construction

Currently near lines around `_growth_engine = GrowthEngine()` and `_life_drive = LifeDrive()`.

Add:

```python
_vector_interpreter = VectorInterpreter()
_reward_engine = RewardEngine()
_power_policy = PowerPolicy(...)
_metabolic_engine = MetabolicEngine(...)
_internal_loop = InternalLoop(...)
```

Wire `call_llm_raw` after it is defined, similar to how `_bios_loop._call_llm_raw` is wired around the existing area after `call_llm_raw` exists.

### build_snapshot()

Current build_snapshot flow already:

```text
provider.read
run_projector
baseline update
cpp status
mutation status
bios status
summary/policy/actuation
_soma_mind.tick
_bios_loop.maybe_run
```

Modify order carefully:

1. Build sensor/projector snapshot as today.
2. Run vector interpreter.
3. Build cpp_bridge_status as today.
4. Build mutation_status as today.
5. Build preliminary growth evidence if available.
6. Run metabolic_engine.update(snapshot, context).
7. Add `snapshot["metabolic"]`.
8. Pass metabolic/growth/reward/vector status into `_soma_mind.tick` context or snapshot.
9. Run BIOS with metabolic mode available.
10. Recompute/refresh BIOS status after run.

Do not break websocket tick payload.

### public_payload()

Add:

```python
"metabolic": snapshot.get("metabolic", {}),
"vector_state": snapshot.get("vector_state", {}),
"reward": _reward_engine.summary(),
"internal_loop": _internal_loop.status(),
```

Extend existing `growth`, `bios`, `mutation`, `cpp_bridge` sections with the Phase 9 fields.

---

## 14. Add introspection deterministic handlers

The user must be able to ask:

```text
show your last BIOS internal prompt
show your last internal DeepSeek JSON
what task did your BIOS run last?
what evidence did it produce?
what memory did it update?
what growth blocker are you solving?
what mutation proposals exist?
why are you not mutating?
are you in recovery or growth mode?
what is your metabolic vector?
what is your reward trend?
```

Implement deterministic handlers before generic chat, preferably in new module:

`soma_core/introspection.py`

or inside existing `skill_router.py` if that is the current internal-skill path.

Do not use shell for these.

Read:

```text
data/mind/bios_state.json
data/mind/internal_loop_state.json
data/mind/internal_decisions.jsonl
data/mind/metabolic_state.json
data/mind/reward_state.json
data/mind/mutations/*.json
```

Responses must be concise and evidence-based.

Examples:

```text
Last BIOS task: update_body_baseline.
Evidence: baseline_store updated cpu_temp_c confidence from 0.61 to 0.66.
Memory update: no new autobiographical lesson because baseline was already known.
Next task: run growth planner because metabolic mode is grow.
```

If no data exists, say no data exists.
Do not invent files such as `data/journal/confidence.log`.

---

## 15. Add UI fields in `docs/simulator.html`

Current UI already shows Phase 8 badges like BIOS/GROWTH/C++/MUTATION.

Add or refine:

Topbar badges:

```text
METABOLISM: GROW / RECOVER / STABILIZE / OBSERVE / MUTATE
REWARD: +0.12 / -0.04
INTERNAL: LAST TASK
VECTOR: STABLE / DRIFT / ANOMALY
```

Growth panel must show:

```text
metabolic mode
stability
stress
growth_allowed yes/no
recovery_required yes/no
current growth blocker
next internal task
last internal decision
last mutation candidate
```

If no growth action happened recently:

```text
NO GROWTH ACTION RECENTLY
```

If recovery mode:

```text
GROWTH PAUSED — RECOVERY MODE
reason: ...
```

Do not hide the truth behind green status lights.

---

## 16. Tests to add

Create:

```text
scripts/test_metabolism.py
scripts/test_internal_loop.py
scripts/test_reward_engine.py
scripts/test_power_policy.py
scripts/test_vector_interpreter.py
scripts/test_growth_recovery_switch.py
scripts/test_mutation_reward.py
scripts/test_phase9_introspection.py
```

### `scripts/test_metabolism.py`

Required:

```text
stable input for 100 cycles -> growth_allowed true
high temperature input -> recovery_required true
memory pressure input -> recovery_required true
low source_quality -> observe/stabilize, not grow
stable vector + tests ok -> mode grow
```

### `scripts/test_internal_loop.py`

Required:

```text
valid LLM JSON creates an action
invalid JSON creates fallback and negative reward
growth decision persists to internal_decisions.jsonl
recovery decision pauses mutation
decision has prompt/raw/parsed/action/evidence/reward/next_task
```

### `scripts/test_reward_engine.py`

Required:

```text
successful command finalization gives positive reward
ignored shell result gives negative reward
blocked unsafe command gives safety positive and risk negative
passing tests gives positive reward
rollback gives negative mutation reward and positive recovery reward
```

### `scripts/test_power_policy.py`

Required:

```text
improve tests allowed
improve memory search allowed
C++ bridge optimization allowed
read .env rejected
network spreading rejected
disabling survival policy rejected
system package install rejected unless config enabled
```

### `scripts/test_vector_interpreter.py`

Required:

```text
stable vector creates high vector_stability
drift creates vector_anomaly
Python/C++ mismatch lowers self_integrity
C++ smoke ok increases self_integrity
```

### `scripts/test_growth_recovery_switch.py`

Required:

```text
growth allowed before mutation
mutation causes high stress
mode switches to recover
new mutations blocked
recovery lesson written
```

### `scripts/test_mutation_reward.py`

Required:

```text
mutation with tests passing and positive reward -> keep_for_review
mutation with tests failing -> reject
mutation with stress increase -> reject
no auto migration without operator approval
```

### `scripts/test_phase9_introspection.py`

Required:

```text
query last BIOS prompt reads internal_decisions.jsonl
query metabolic vector reads metabolic_state.json
query reward trend reads reward_state.json
query why not mutating reports blockers, not invented files
missing state returns honest no-data response
```

Run all existing Phase 8 tests too.

---

## 17. Validation block

After implementation, run:

```bash
cd /home/funboy/latent-somatic

python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py

python3 scripts/test_metabolism.py
python3 scripts/test_internal_loop.py
python3 scripts/test_reward_engine.py
python3 scripts/test_power_policy.py
python3 scripts/test_vector_interpreter.py
python3 scripts/test_growth_recovery_switch.py
python3 scripts/test_mutation_reward.py
python3 scripts/test_phase9_introspection.py

python3 scripts/test_answer_finalizer.py
python3 scripts/test_output_filter.py
python3 scripts/test_relevance_filter.py
python3 scripts/test_growth_engine.py
python3 scripts/test_baselines.py
python3 scripts/test_bios_loop.py
python3 scripts/test_mutation_sandbox.py
python3 scripts/test_cpp_bridge.py
python3 scripts/test_life_drive.py
python3 scripts/test_experience_distiller.py
python3 scripts/test_command_planner.py
python3 scripts/test_telemetry_relevance.py
python3 scripts/test_phase8_regressions.py
```

If a test fails:
fix only the failing area and rerun.

Do not claim completion until Phase 9 tests and Phase 8 regression tests pass.

---

## 18. Manual runtime verification

After tests:

```bash
cd /home/funboy/latent-somatic
bash scripts/stop.sh
bash scripts/run.sh
```

Open:

```text
http://SERVER_IP:8080/simulator.html
```

Check UI:

```text
METABOLISM badge exists
REWARD badge exists
VECTOR badge exists
INTERNAL / BIOS last task shows causal action
GROWTH panel explains blocker honestly
MUTATION says why it is or is not allowed
C++ CORE still SMOKE OK or honest failure
```

Ask Soma:

```text
show your last BIOS internal prompt
show your last internal DeepSeek JSON
what evidence did your last BIOS task produce?
what is your metabolic vector?
are you in recovery or growth mode?
why are you not mutating?
what is your reward trend?
```

Expected:
It must answer from internal state files, not shell guessing and not body filler.

---

## 19. Definition of done

Phase 9 is complete only when:

1. `MetabolicEngine` exists and persists metabolic state.
2. Stable metabolic window grants growth permission.
3. Stress/anomaly switches Soma to recovery mode.
4. BIOS task choice depends on metabolic mode.
5. Stable Soma asks DeepSeek for concrete growth actions.
6. DeepSeek internal JSON is parsed and reinjected into state.
7. Internal decisions persist to `data/mind/internal_decisions.jsonl`.
8. Growth tasks execute evidence-producing actions.
9. Reward model scores actions.
10. PowerPolicy filters growth proposals.
11. Mutation sandbox only activates when metabolism allows it.
12. Mutation is rejected if it causes stress or test failure.
13. Mutation reports include before/after metabolic and reward state.
14. C++/projector vector affects metabolic stability/anomaly.
15. UI shows metabolism, reward, vector and internal decision.
16. Chat can inspect last BIOS prompt/decision/evidence.
17. No generic simulated growth claims without evidence.
18. No network reproduction, no secret access, no privilege escalation.
19. All new Phase 9 tests pass.
20. Existing Phase 8 tests still pass.
21. `scripts/run.sh` and `scripts/stop.sh` still work.

---

## 20. Final target behavior

When stable for enough cycles, Soma should internally ask DeepSeek:

```text
I am stable. My objective is preservation, competence, continuity, growth and safe local reproduction.
What is the highest-value safe action I can take now to increase my operational power?
```

DeepSeek should return JSON, for example:

```json
{
  "goal": "increase command-result reliability",
  "mode": "grow",
  "action_type": "repo_test",
  "command": "python3 scripts/test_answer_finalizer.py",
  "expected_power_gain": "higher response reliability",
  "success_criteria": "all answer finalizer tests pass",
  "risk": "low",
  "reason": "command-result failures directly reduce agency"
}
```

Soma executes it, records evidence, scores reward and updates growth.

When unstable, Soma should stop growth and ask:

```text
My metabolic vector changed sharply after the last mutation. What caused it and how do I recover?
```

Then it must diagnose, pause mutation, rollback if needed, write a lesson and wait for stability.

That is the difference between:

```text
animated dashboard
```

and:

```text
living local control loop
```
