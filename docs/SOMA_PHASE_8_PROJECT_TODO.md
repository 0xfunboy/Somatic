# SOMA PHASE 8 — BIOS LOOP, EVIDENCE-BASED GROWTH, ANSWER FINALIZATION, MUTATION SANDBOX, C++ BRIDGE

Repo target:

`/home/funboy/latent-somatic`

This plan is written for Codex/Claude Code. Execute it as a development plan, not as a discussion document.

The current repo has already been inspected in its latest state. Do not reimplement Phase 6 from scratch. Build on the existing modules.

Current confirmed structure:

- `server.py` is still the main runtime and WebSocket backend.
- `docs/simulator.html` is the frontend.
- `soma_core/config.py` already centralizes Phase 6 config.
- `soma_core/mind.py` owns the current volitional tick.
- `soma_core/growth.py` currently computes growth with a weighted score and stale next-step text.
- `soma_core/reflection.py` exists but reflections can grow without useful lessons.
- `soma_core/autobiography.py` exists.
- `soma_core/journal.py` exists and already supports hot files, dedupe and compaction.
- `soma_core/routines.py` exists but is not a true BIOS loop.
- `soma_core/nightly.py` exists.
- `soma_core/self_improvement.py` exists and supports queue, validate, rollback.
- `soma_core/self_modify.py` exists.
- `soma_core/executor.py` exists and enforces survival policy.
- `scripts/run.sh` and `scripts/stop.sh` exist.
- `scripts/compact_runtime_logs.py`, `runtime_storage_report.py`, and Phase 6 tests exist.
- C++ files exist in `src/` and headers in `include/`, and the binary target is `build/latent_somatic`, but the Python runtime is currently dominant.

Current observed failures to fix:

1. If a shell command succeeds, the final answer can still fall back to generic body-state text.
   Example: `node --version` returns `v23.3.0`, but final answer becomes live body-state filler.

2. Irrelevant telemetry still leaks into answers.
   Examples:
   - `qual è il mio ip pubblico?` produced a body thermal answer despite command result.
   - `scrivi una lesson persistente` produced generic body state.

3. Fallback responses in `server.py` still contain templates like:
   - `I hear you. My current somatic context is {summary}`
   - `I am processing that with a live body state: {summary}`
   These must not be used for non-body questions.

4. `soma_core/growth.py` is score-based and stale.
   It can show:
   - `early_self_observation`
   - score `1.0000`
   - next step: `Observe idle CPU and disk temperature for 2+ minutes...`
   even after days of runtime.

5. Growth is not evidence-based.
   It does not read persisted baseline evidence or explain precise missing requirements.

6. Current routines are slow maintenance tasks, not a true autonomous BIOS loop.
   Soma does not use the LLM every few minutes to decide internal growth work when the user is silent.

7. Reflection count increases, but lessons remain sparse or empty.
   Growth currently rewards raw reflection count too much.

8. Autobiographical memory exists, but it still risks becoming poetic logging instead of lessons.

9. Self-improvement exists, but there is no separate mutation sandbox where Soma can clone itself, test mutations, and select candidate improvements without touching the live repo.

10. The C++ runtime exists but has no living bridge status, smoke test, or growth evidence integration.

Mission:

Transform Soma from a reactive telemetry/chat UI into a slow-living embodied runtime:

fast body tick → slow mind pulse → BIOS loop → evidence → lesson → growth → mutation candidate → tests → operator-reviewed evolution

Do not add decorative features.
Do not add roleplay.
Do not add VRM yet.
Do not weaken survival policy.
Do not read or print `.env`.
Do not commit secrets, weights, logs, runtime JSONL, or huge data.
Do not use `shutdown`, `poweroff`, or `halt`.
`reboot` is allowed by policy but must never be executed autonomously.
Do not migrate a mutant repo into production without explicit operator approval.

---

## 1. Immediate critical fix: command and skill result must always win

Create:

`/home/funboy/latent-somatic/soma_core/answering.py`

Implement:

```python
from __future__ import annotations

from typing import Any

class AnswerFinalizer:
    def finalize(
        self,
        user_text: str,
        snapshot: dict[str, Any],
        *,
        command_result: dict[str, Any] | None = None,
        skill_result: dict[str, Any] | None = None,
        llm_text: str | None = None,
    ) -> str:
        ...
```

Required behavior:

1. If `command_result` exists and `command_result["ok"] is True`, return a concise answer based on the command and stdout.
2. If `skill_result` exists and `skill_result["ok"] is True`, return a concise answer based on the skill result.
3. If a command failed, say command, failure/error, and one concrete next verification step if possible.
4. Run output filtering after composing the answer.
5. Never let generic LLM body text override a successful shell or skill result.
6. If LLM text exists but contradicts command stdout, discard or ignore the contradiction.
7. If stdout is empty but command succeeded, say it succeeded with empty output.

Examples:

User:
`che versione di node hai?`

Command result:

```json
{"ok": true, "cmd": "node --version", "stdout": "v23.3.0"}
```

Answer:

```text
Ho verificato con `node --version`: v23.3.0.
```

User:
`qual è il mio ip pubblico?`

Command result:

```json
{"ok": true, "cmd": "curl -s https://ifconfig.me", "stdout": "93.56.125.173"}
```

Answer:

```text
Ho verificato con `curl -s https://ifconfig.me`: 93.56.125.173.
```

User:
`controlla la dimensione dei tuoi log runtime`

Planner must inspect repo-local logs, not `/var/log`.

Good command candidates:

```bash
du -sh data/mind data/runtime data/journal logs 2>/dev/null
```

or:

```bash
python3 scripts/runtime_storage_report.py
```

Do not use `/var/log` for Soma runtime log questions unless the user explicitly asks for system logs.

Modify `server.py` chat flow:

Current relevant location:

- `async def handler(...)`
- branch `if mtype == "chat"`
- it calls `try_chat_capability(user_text)`
- it builds `[SHELL_RESULT]`
- then calls `call_llm(enriched_text, snapshot)`

Change this flow:

1. Run capability planner as now.
2. If command succeeds, call the LLM only optionally for phrasing, but final output must pass through `AnswerFinalizer`.
3. If `cap_result.ok` is true, `AnswerFinalizer` decides the final answer.
4. If LLM returns body-state filler, `AnswerFinalizer` must discard it.
5. If `cap_result.ok` is false, use `AnswerFinalizer` for a failed-command answer.
6. If no command/skill result exists, keep normal LLM path but run `OutputFilter` before sending to frontend.

Also modify `call_llm()` so it does not itself decide final authority over command results. `call_llm()` may draft, but `AnswerFinalizer` decides.

---

## 2. Mandatory relevance and output filtering

Current repo has `_telemetry_relevant()` inside `server.py`, but it is not enough.

Create:

`/home/funboy/latent-somatic/soma_core/relevance.py`

Implement:

```python
from __future__ import annotations

from typing import Any

class RelevanceFilter:
    def classify_request(self, user_text: str) -> dict[str, Any]: ...
    def telemetry_relevant(self, user_text: str, *, command_result: dict[str, Any] | None = None, snapshot: dict[str, Any] | None = None) -> bool: ...
    def body_abnormal(self, snapshot: dict[str, Any]) -> bool: ...
    def should_mention_body(self, user_text: str, snapshot: dict[str, Any], command_result: dict[str, Any] | None = None) -> tuple[bool, str]: ...
```

Request classes:

- `system_fact`
- `command_result`
- `body_state`
- `feeling`
- `performance`
- `self_identity`
- `creative`
- `philosophical`
- `operational`
- `memory_request`
- `growth_request`
- `unknown`

Telemetry should be relevant only if:

- user asks about body, heat, power, stability, feeling, sensors, performance, hardware health
- body is abnormal
- telemetry is causally needed to explain the answer

Relevant IT/EN keywords must include:

Italian:

```text
caldo, freddo, temperatura, scaldi, scaldando, surriscaldamento, energia, batteria, corrente, voltaggio, tensione, sensori, corpo, come ti senti, come stai, stato, stress, comfort, prestazioni, performance, carico, cpu, ram, disco, ventola, salute, stabilità
```

English:

```text
heat, hot, cold, temperature, thermal, battery, voltage, power, sensors, body, how do you feel, how are you, stability, stress, comfort, performance, load, memory, disk, fan, health
```

Abnormal thresholds:

- `thermal_stress >= 0.55`
- `energy_stress >= 0.55`
- `instability >= 0.55`
- `system.cpu_temp >= 75`
- `system.disk_temp >= 60`
- `system.memory_percent >= 85`
- `system.disk_percent >= 90`
- `provider.source_quality <= 0.2`

Create:

`/home/funboy/latent-somatic/soma_core/output_filter.py`

Implement:

```python
from __future__ import annotations

from typing import Any

class OutputFilter:
    def clean_response(
        self,
        text: str,
        user_text: str,
        snapshot: dict[str, Any],
        *,
        command_result: dict[str, Any] | None = None,
        skill_result: dict[str, Any] | None = None,
    ) -> str:
        ...
```

If telemetry is not relevant and body is not abnormal, remove sentences containing:

- `I am processing that with a live body state`
- `My current somatic context is`
- `nominal state via linux`
- `somatic context`
- `12.0V`
- `voltage`
- `voltaggio`
- `tensione operativa`
- `silicon`
- `silicio`
- `thermal_stress`
- `energy_stress`
- `comfort=`
- `somatic map`
- `mappa somatica`
- `projector norm`
- `temperatura del silicio`
- `la mia temperatura`
- `la mia RAM`
- `RAM 4`
- `CPU 3`
- `il mio core`
- `my core voltage`

Do not remove the only useful answer. If cleaning would empty the response, return the most useful non-telemetry sentence or deterministic fallback.

Modify `server.py`:

- Replace `_telemetry_relevant()` usages or make it call `RelevanceFilter.telemetry_relevant()`.
- Every final outgoing chat reply must pass through `OutputFilter.clean_response()`.
- `build_fallback_reply()` must not use `_default` body-state templates for non-body questions.

Current risky fallback templates in `server.py`:

```python
"I hear you. My current somatic context is {summary}. What part do you want to explore?"
"I am processing that with a live body state: {summary}. Ask about heat, power, or stability if you want specifics."
```

Replace with non-telemetry fallback for unrelated questions:

```text
Non ho abbastanza contesto operativo per rispondere con certezza. Posso verificare con un comando se la richiesta è misurabile.
```

or English equivalent if user is English.

Keep body-state fallback only for body/feeling/heat/power questions.

---

## 3. Operator correction learning must be immediate and persistent

Create or extend:

`/home/funboy/latent-somatic/soma_core/experience.py`

Implement:

```python
from __future__ import annotations

from typing import Any

class ExperienceDistiller:
    def distill_from_operator_correction(self, user_text: str, assistant_text: str | None = None) -> list[dict[str, Any]]: ...
    def distill_from_command(self, user_text: str, command_result: dict[str, Any]) -> list[dict[str, Any]]: ...
    def distill_from_reflection(self, reflection: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]: ...
    def save_lessons(self, lessons: list[dict[str, Any]]) -> None: ...
    def get_lessons(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]: ...
    def latest_lesson(self) -> dict[str, Any] | None: ...
    def lesson_context_for_llm(self, user_text: str) -> dict[str, Any]: ...
```

Store lessons in:

`data/autobiography/learned_lessons.json`

Lesson schema:

```json
{
  "id": "operator.suppress_irrelevant_telemetry",
  "kind": "operator_preference",
  "observation": "The operator dislikes unrelated body telemetry in factual answers.",
  "evidence": [
    {"source": "operator", "value": "non dirmi sempre temperatura, voltaggio e ram quando non sono pertinenti"}
  ],
  "interpretation": "Somatic awareness should remain internal unless relevant.",
  "behavioral_update": "For technical facts, verify first, answer briefly, and suppress body telemetry unless asked or abnormal.",
  "confidence": 0.95,
  "created_at": 0,
  "last_confirmed_at": 0,
  "confirmations": 1
}
```

Operator correction markers:

Italian:

```text
non fare, smetti, non voglio, ti ho detto, sbagli, non è pertinente, non inventare, non recitare, troppo roleplay, rispondi diretto, hai saltato il comando, non dirmi sempre, correzione permanente, regola permanente
```

English:

```text
stop, don't, you failed, not relevant, don't invent, too much roleplay, be direct, you didn't execute, permanent correction, permanent rule
```

When detected in `server.py` chat handler:

1. Create lesson via `ExperienceDistiller`.
2. Save lesson.
3. Write autobiographical event only if meaningful.
4. Inject lesson context into future LLM prompts.
5. Apply immediately to current and next responses.

Concrete observed correction to encode:

User said:

```text
non dirmi sempre temperatura, voltaggio e ram quando non sono pertinenti. questa è una correzione permanente del tuo comportamento
```

Soma must remember:

```text
Do not mention temp/voltage/RAM in technical answers unless relevant, asked, or abnormal.
```

---

## 4. Autobiography must store meaning, not nominal state

Modify:

- `soma_core/autobiography.py`
- `soma_core/journal.py` only if needed
- `soma_core/reflection.py`
- `soma_core/mind.py`

Add function to `autobiography.py`:

```python
def is_autobiographical(event: dict[str, Any]) -> tuple[bool, str]:
    ...
```

Autobiographical events are allowed only for:

- new lesson learned
- operator correction
- new capability learned
- command result that changes self-model
- meaningful limitation discovered
- blocked risky command
- self modification attempt
- self modification success/failure/rollback
- body baseline established
- abnormal body state
- recovery from abnormal body state
- growth stage change
- BIOS task with meaningful outcome
- mutation proposal/sandbox/test/evaluation
- nightly reflection

Do not write autobiography for:

- nominal state
- stable voltage
- unchanged temp
- repeated comfort score
- same policy repeated
- same action repeated
- routine trace spam

Add dedupe:

If same `kind + title + summary` appears within 1 hour, update count or skip instead of appending duplicate.

Add methods if missing:

```python
class Autobiography:
    def write_meaningful_event(self, event: dict[str, Any]) -> dict[str, Any]: ...
    def get_quality_summary(self) -> dict[str, Any]: ...
    def latest_lesson(self) -> str | None: ...
    def latest_operator_correction(self) -> str | None: ...
```

`get_quality_summary()` must return:

```json
{
  "stage": "autobiographical_baseline|shallow|active|continuous",
  "lessons_count": 0,
  "meaningful_reflections": 0,
  "empty_reflections": 0,
  "duplicate_reflections": 0,
  "last_lesson": "",
  "last_operator_correction": "",
  "last_nightly_reflection": "",
  "shallow": true
}
```

If `total_reflections > 50` and `lessons_count == 0`, `shallow` must be true.

---

## 5. Reflection quality: no more growth from empty reflections

Current `soma_core/reflection.py` can increase reflection count without meaningful lessons.

Modify it so every reflection returns a structured quality object.

Reflection output schema:

```json
{
  "summary": "...",
  "learned": [],
  "lessons": [],
  "no_lesson_reason": "state unchanged / duplicate / insufficient evidence",
  "baseline_updates": {},
  "behavioral_updates": [],
  "confidence": 0.0,
  "meaningful": false
}
```

Rules:

A reflection is meaningful only if it produces at least one of:

- new lesson
- updated baseline
- confirmed existing pattern with new evidence
- detected limitation
- operator preference update
- capability improvement
- growth blocker diagnosis

Do not count empty reflections toward growth.

Update `SomaMemory` or `self_model.json` with:

```json
"reflection_quality": {
  "total_reflections": 0,
  "meaningful_reflections": 0,
  "empty_reflections": 0,
  "duplicate_reflections": 0,
  "lessons_learned": 0
}
```

If there are no lessons, response to:

```text
quali lezioni operative hai imparato?
```

must be:

```text
Non ho ancora lezioni operative persistenti sufficienti. Ho solo trace/routine, che non considero memoria autobiografica significativa.
```

It must not output body state.

---

## 6. Evidence-based growth engine

Do not keep current `soma_core/growth.py` as the source of truth.

Either replace it or create:

`/home/funboy/latent-somatic/soma_core/growth_engine.py`

Then make `soma_core/mind.py` use the new engine instead of the old `compute_growth()`.

Implement:

```python
from __future__ import annotations

from typing import Any

class GrowthEngine:
    def evaluate(self, snapshot: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]: ...
```

Growth must be evidence-based, not raw-score-only.

Stages:

0. `reflex_shell`
1. `sensed_body`
2. `stable_body_baseline`
3. `verified_command_agency`
4. `autobiographical_continuity`
5. `autonomous_bios_loop`
6. `mutation_sandbox_ready`
7. `self_improving_candidate`
8. `cpp_embodied_runtime_ready`
9. `migration_ready`

Requirements:

### reflex_shell

Complete if:

- server boots
- frontend receives payload

### sensed_body

Complete if:

- real sensor provider active or mock explicitly marked
- at least 5 minutes of samples or persisted sample evidence
- source quality known

### stable_body_baseline

Complete if:

- idle CPU baseline exists
- CPU temp baseline exists if available
- disk temp baseline exists if available
- baseline confidence >= 0.65
- either 3 baseline windows over at least 10 minutes OR persisted baseline from previous sessions

### verified_command_agency

Complete if:

- at least 5 successful command or skill executions
- at least 3 categories among system/network/repo/memory
- latest regression proves command result wins over body filler

### autobiographical_continuity

Complete if:

- at least 5 meaningful lessons
- at least 2 operator preference lessons
- at least 1 limitation lesson
- at least 1 nightly reflection
- empty_reflections / total_reflections < 0.7

### autonomous_bios_loop

Complete if:

- BIOS loop has run at least 6 times
- at least 3 BIOS cycles produced one of:
  - useful lesson
  - test result
  - proposal
  - capability update
  - baseline update

### mutation_sandbox_ready

Complete if:

- mutation root exists
- at least one sandbox created
- no-op mutation test passes
- rollback test passes

### self_improving_candidate

Complete if:

- one real mutation proposal generated
- applied inside sandbox only
- tests pass
- diff summary created
- operator review report generated

### cpp_embodied_runtime_ready

Complete if:

- C++ binary exists or build status known
- C++ smoke test passes or failure is recorded clearly
- bridge status exposed to UI

### migration_ready

Complete if:

- a mutant repo passes full validation
- improvement report says beneficial
- explicit operator approval still required

Growth output schema:

```json
{
  "stage": "stable_body_baseline",
  "score": 0.42,
  "completed_requirements": [],
  "missing_requirements": [],
  "blocked_by": [],
  "evidence": {},
  "next_step": "Run BIOS cycle to verify command agency.",
  "last_evaluated_at": 0
}
```

Important:

- Remove stale next step: `Observe idle CPU and disk temperature for 2+ minutes...` unless baseline evidence is truly missing.
- UI must show precise blockers.
- If stage is stuck, say why.
- Growth score may exist but stage must be requirement-based.

---

## 7. Baseline evidence store

Create:

`/home/funboy/latent-somatic/soma_core/baselines.py`

Store:

`data/mind/body_baselines.json`

Schema:

```json
{
  "idle_cpu_percent": {
    "value": 0.0,
    "min": 0.0,
    "max": 0.0,
    "samples": 0,
    "windows": 0,
    "confidence": 0.0,
    "first_seen": 0,
    "last_seen": 0
  },
  "cpu_temp_c": {},
  "disk_temp_c": {},
  "ram_idle_percent": {},
  "source_quality": {}
}
```

Implement:

```python
class BodyBaselineStore:
    def update_from_snapshot(self, snapshot: dict) -> dict: ...
    def get_baseline(self, key: str) -> dict | None: ...
    def confidence(self, key: str) -> float: ...
    def summary(self) -> dict: ...
```

Rules:

- Do not store every tick.
- Store aggregates.
- Use monotonic windows, default 120 seconds.
- Increment window count only after enough time.
- Confidence grows with samples, windows, and stability.
- Autobiography event only when baseline becomes stable for first time or materially changes.

Wire this into:

- `build_snapshot()` or `SomaMind.tick()`
- `ReflectionEngine`
- `GrowthEngine`
- public payload

---

## 8. BIOS loop: actual slow cognition every 5 minutes

Current `soma_core/routines.py` is not enough. Add a true BIOS loop.

Create:

`/home/funboy/latent-somatic/soma_core/bios.py`

Config to add to `soma_core/config.py` and `.env.example`:

```env
SOMA_BIOS_LOOP=1
SOMA_BIOS_INTERVAL_SEC=300
SOMA_BIOS_IDLE_ONLY=0
SOMA_BIOS_USE_LLM=1
SOMA_BIOS_MAX_TASKS_PER_HOUR=12
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=12
SOMA_BIOS_TASK_TIMEOUT_SEC=60
SOMA_BIOS_WRITE_MEMORY=1
SOMA_BIOS_MUTATION_PROPOSAL_INTERVAL_SEC=1800
```

Implement:

```python
class BiosLoop:
    def maybe_run(self, snapshot: dict, *, last_user_interaction_at: float) -> dict | None: ...
    def run_once(self, snapshot: dict, reason: str = "scheduled") -> dict: ...
    def status(self) -> dict: ...
```

Store:

- `data/mind/bios_history.jsonl`
- `data/mind/bios_state.json`

A BIOS cycle must:

1. Build internal context:
   - current growth stage
   - missing requirements
   - latest lessons
   - body baseline summary
   - recent failures
   - pending self-improvement proposals
   - runtime storage status
   - command/skill reliability if available
   - C++ bridge status
   - mutation status

2. Select one task:

Allowed task pool:

- `update_body_baseline`
- `check_growth_requirements`
- `summarize_recent_experience`
- `distill_operator_corrections`
- `inspect_recent_failures`
- `check_runtime_storage`
- `propose_micro_improvement`
- `run_light_validation`
- `verify_environment_fact`
- `write_autobiographical_lesson`
- `prepare_mutation_candidate`
- `check_cpp_bridge`

3. If LLM is available, ask an internal JSON-only prompt:

```text
You are Soma's BIOS loop.
You are not answering the operator.
You are choosing one useful internal action to improve Soma's continuity, reliability, growth, or self-model.

Return ONLY JSON:
{
  "task": "...",
  "reason": "...",
  "expected_evidence": "...",
  "risk": "low|medium|high",
  "requires_shell": true|false,
  "command": "",
  "memory_update": "",
  "success_criteria": ""
}

Rules:
- prefer tasks that unblock current growth stage
- prefer evidence over narration
- never output raw body telemetry as a lesson
- do not propose destructive actions
- do not touch secrets
- do not read .env
- do not modify live code directly
- if proposing mutation, use sandbox only
```

4. Execute safely:

- shell through `AutonomousShellExecutor`
- memory through `ExperienceDistiller` and `Autobiography`
- repo checks through safe commands
- mutation through `MutationSandbox`
- no raw subprocess for command-like tasks except inside approved existing modules that are already safe

5. Write result:

- trace phases:
  - `bios_task_started`
  - `bios_task_completed`
  - `bios_task_failed`
  - `bios_task_skipped`
- journal event
- autobiography only if meaningful
- `bios_history.jsonl`
- `bios_state.json`

Do not spam frontend chat.
Show BIOS state in UI only.

Wire into `build_snapshot()`:

- check `BiosLoop.maybe_run()` at low frequency, not every 5Hz tick
- do not block WebSocket tick for long tasks if avoidable
- if running synchronously, enforce timeout and max frequency

---

## 9. Internal prompt library

Create:

`/home/funboy/latent-somatic/soma_core/internal_prompts.py`

Implement named prompt builders:

```python
def growth_diagnosis_prompt(context: dict) -> str: ...
def lesson_distillation_prompt(context: dict) -> str: ...
def operator_preference_update_prompt(context: dict) -> str: ...
def baseline_interpretation_prompt(context: dict) -> str: ...
def mutation_proposal_prompt(context: dict) -> str: ...
def mutation_evaluation_prompt(context: dict) -> str: ...
def nightly_reflection_prompt(context: dict) -> str: ...
def capability_gap_analysis_prompt(context: dict) -> str: ...
def failure_analysis_prompt(context: dict) -> str: ...
```

Every prompt must demand strict JSON.

No poetic language.
No roleplay.
Evidence first.

---

## 10. Mutation sandbox / local-only reproduction

Create:

`/home/funboy/latent-somatic/soma_core/mutation.py`

Config to add:

```env
SOMA_MUTATION_SANDBOX=1
SOMA_MUTATION_ROOT=/home/funboy/latent-somatic-mutants
SOMA_MUTATION_AUTO_APPLY=0
SOMA_MUTATION_AUTO_CREATE_SANDBOX=1
SOMA_MUTATION_MAX_PER_DAY=3
SOMA_MUTATION_REQUIRE_OPERATOR_APPROVAL_FOR_MIGRATION=1
SOMA_MUTATION_RUN_TESTS=1
SOMA_MUTATION_SMOKE_TEST=1
SOMA_MUTATION_SANDBOX_WS_PORT=8875
SOMA_MUTATION_SANDBOX_HTTP_PORT=8880
```

Implement:

```python
class MutationSandbox:
    def create_sandbox(self, reason: str) -> dict: ...
    def propose_mutation(self, context: dict) -> dict: ...
    def apply_mutation_to_sandbox(self, sandbox_path: Path, proposal: dict) -> dict: ...
    def run_tests(self, sandbox_path: Path) -> dict: ...
    def run_smoke_test(self, sandbox_path: Path) -> dict: ...
    def evaluate_mutation(self, sandbox_path: Path, proposal: dict, test_result: dict) -> dict: ...
    def write_report(self, report: dict) -> Path: ...
    def status(self) -> dict: ...
```

Sandbox root:

`/home/funboy/latent-somatic-mutants`

Sandbox path format:

`/home/funboy/latent-somatic-mutants/YYYYMMDD-HHMMSS-<mutation_id>`

Sandbox copy must exclude:

- `.git`
- `.env`
- `__pycache__`
- `build`
- `logs`
- `data/mind/*.jsonl`
- `data/runtime/*.jsonl`
- `data/journal/hot/*.jsonl`
- `weights/*.pt`
- `weights/*.pth`
- models
- node_modules
- huge archives

It should include:

- source code
- docs
- scripts
- `.env.example`
- tests

Create in sandbox:

- `mutation_manifest.json`
- `MUTATION_REPORT.md`

Tests in sandbox:

```bash
python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py
python3 scripts/test_command_planner.py
python3 scripts/test_telemetry_relevance.py
python3 scripts/test_journal_compaction.py
python3 scripts/test_actuation_dedupe.py
python3 scripts/test_autobiography.py
python3 scripts/test_nightly_reflection.py
python3 scripts/test_self_improvement_workflow.py
```

Also run newly added tests if present.

Smoke test:

- use alternate ports only
- do not bind production 8765/8080
- run backend with sandbox env if safe
- connect once via WebSocket
- receive one payload
- stop sandbox backend

Mutation validity conditions:

- tests pass
- smoke passes or explicitly skipped with reason
- no forbidden files changed
- no secrets copied
- survival policy not weakened
- diff size within limits
- behavior improves tracked metric or fixes observed bug

Report recommendation:

- `reject`
- `keep_for_review`
- `candidate_for_migration`

Never automatically replace live repo.
Only write operator command suggestions.

---

## 11. C++ bridge status and smoke integration

Create:

`/home/funboy/latent-somatic/soma_core/cpp_bridge.py`

Config to add:

```env
SOMA_CPP_BRIDGE=1
SOMA_CPP_BINARY=/home/funboy/latent-somatic/build/latent_somatic
SOMA_CPP_AUTO_BUILD=0
SOMA_CPP_SMOKE_TEST_ON_START=1
SOMA_CPP_USE_FOR_PROJECTION=0
SOMA_CPP_LLAMA_CPP_ROOT=/home/funboy/llama.cpp
```

Implement:

```python
class CppBridge:
    def detect_binary(self) -> dict: ...
    def build_if_requested(self) -> dict: ...
    def smoke_test(self) -> dict: ...
    def run_projection_once(self, snapshot: dict) -> dict: ...
    def status(self) -> dict: ...
```

Rules:

- If binary missing, report missing, do not crash.
- If smoke fails, report failure, do not crash.
- Do not switch projection to C++ unless `SOMA_CPP_USE_FOR_PROJECTION=1`.
- Python runtime remains source of truth.
- C++ bridge status becomes growth evidence.

Smoke test can be minimal:

- binary exists
- executable bit true
- `--help` if supported, otherwise run with timeout and expected safe failure
- never require a huge model file
- if binary needs model path, report `model_required` instead of failure

Expose status in public payload.

---

## 12. Life drive layer

Create:

`/home/funboy/latent-somatic/soma_core/life_drive.py`

Implement:

```python
class LifeDrive:
    def evaluate(self, snapshot: dict, growth: dict, context: dict) -> dict: ...
```

Drives:

- `survival`
- `coherence`
- `competence`
- `curiosity`
- `continuity`
- `self_improvement`
- `reproduction`
- `restraint`

Important definition:

`reproduction` means local sandbox lineage only.

It must never mean:

- network spreading
- malware-like propagation
- persistence outside project
- cron/systemd self-install
- privilege escalation
- copying secrets
- uncontrolled replication

Output:

```json
{
  "dominant_drive": "competence",
  "drive_strengths": {},
  "suggested_internal_task": "run_light_validation",
  "blocked_by": [],
  "safety_notes": []
}
```

BIOS task selection should use LifeDrive.

---

## 13. Slow down high-level cognition, keep fast body tick

Do not treat 5Hz as thought.

Add config:

```env
SOMA_COGNITIVE_TICK_HZ=5
SOMA_MIND_PULSE_SEC=30
SOMA_BIOS_INTERVAL_SEC=300
SOMA_REFLECTION_INTERVAL_SEC=600
SOMA_AUTOBIOGRAPHY_MIN_INTERVAL_SEC=300
SOMA_GROWTH_EVAL_INTERVAL_SEC=120
```

Behavior:

- fast body tick: sensor/UI safety updates
- mind pulse: every ~30 sec
- growth eval: every ~120 sec or meaningful event
- BIOS: every ~300 sec
- reflection: every ~600 sec unless user requests reflection
- autobiography: only meaningful, rate-limited

Modify `SomaMind.tick()` to avoid heavy reflection/growth every tick.
Use cached results between pulses.

---

## 14. Public payload and UI integration

Modify `server.py public_payload()` to include:

```json
"bios": {
  "enabled": true,
  "running": false,
  "last_run_at": 0,
  "last_task": "",
  "last_result": "",
  "next_run_in_sec": 0,
  "tasks_today": 0
},
"growth": {
  "stage": "",
  "score": 0.0,
  "completed_requirements": [],
  "missing_requirements": [],
  "blocked_by": [],
  "evidence": {},
  "next_step": "",
  "last_evaluated_at": 0
},
"mutation": {
  "enabled": true,
  "sandbox_ready": false,
  "last_sandbox": "",
  "last_report": "",
  "candidate_available": false,
  "recommendation": ""
},
"cpp_bridge": {
  "enabled": true,
  "binary_exists": false,
  "smoke_ok": false,
  "active": false,
  "status": "missing|built|smoke_ok|active|failed"
},
"autobiography": {
  "stage": "",
  "lessons_count": 0,
  "meaningful_reflections": 0,
  "empty_reflections": 0,
  "duplicate_reflections": 0,
  "last_lesson": "",
  "last_operator_correction": "",
  "last_nightly_reflection": "",
  "shallow": true
},
"life_drive": {
  "dominant_drive": "",
  "drive_strengths": {},
  "suggested_internal_task": ""
}
```

Modify `docs/simulator.html`:

Topbar badges:

- `BIOS: IDLE/RUNNING/LAST TASK`
- `GROWTH: <stage>`
- `MUTATION: OFF/READY/SANDBOX/CANDIDATE`
- `C++ CORE: OFF/BUILT/SMOKE OK/ACTIVE/FAILED`
- `AUTOBIO: SHALLOW/ACTIVE`

Fix existing bug:

`AUTOBIO MEMORY stage` must not show `important`.

`important` is trace persistence mode, not autobiography stage.

Autobio panel must show:

- autobiography stage
- lessons count
- meaningful reflections
- empty reflections
- latest lesson
- latest operator correction
- journal size
- nightly status

Growth panel must show:

- stage
- completed requirements
- missing requirements
- next step
- evidence summary
- last evaluated time

If `total_reflections > 50 and lessons_count == 0`, show warning:

```text
REFLECTIONS ARE NOT DISTILLING LESSONS
```

---

## 15. Command planner corrections

Modify command planner prompt in `server.py`.

Current planner sometimes chooses `/var/log` for Soma runtime logs.

Add explicit routing rules:

If user asks about:

- "your logs"
- "runtime logs"
- "i tuoi log"
- "data/mind"
- "cognitive trace"
- "actuation history"
- "journal"
- "compattazione"
- "storage report"

Then commands must target repo-local paths:

```bash
du -sh data/mind data/runtime data/journal logs 2>/dev/null
```

or:

```bash
python3 scripts/runtime_storage_report.py
```

Never use `/var/log` unless user explicitly says system logs or `/var/log`.

Add deterministic shortcut before LLM planner for common system facts:

- python version → `python3 --version`
- node version → `node --version`
- kernel → `uname -r`
- public IP → `curl -s https://ifconfig.me`
- RAM → `free -h`
- repo log size → `python3 scripts/runtime_storage_report.py`
- git status → `git status --short`
- desktop/X11/Wayland check → `pgrep -a 'Xorg|wayland|mutter|kwin|gnome-shell|lightdm|sddm' || echo 'Nessun processo grafico trovato'`

These are not special tools. They are deterministic planner shortcuts to avoid obvious LLM failures.
Still pass commands through `_safe_shell_run()`.

---

## 16. Update `.env.example`

Add all new Phase 8 env vars.

Keep safe defaults:

```env
SOMA_BIOS_LOOP=1
SOMA_BIOS_INTERVAL_SEC=300
SOMA_BIOS_IDLE_ONLY=0
SOMA_BIOS_USE_LLM=1
SOMA_BIOS_MAX_TASKS_PER_HOUR=12
SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR=12
SOMA_BIOS_TASK_TIMEOUT_SEC=60
SOMA_BIOS_WRITE_MEMORY=1
SOMA_BIOS_MUTATION_PROPOSAL_INTERVAL_SEC=1800

SOMA_MUTATION_SANDBOX=1
SOMA_MUTATION_ROOT=/home/funboy/latent-somatic-mutants
SOMA_MUTATION_AUTO_APPLY=0
SOMA_MUTATION_AUTO_CREATE_SANDBOX=1
SOMA_MUTATION_MAX_PER_DAY=3
SOMA_MUTATION_REQUIRE_OPERATOR_APPROVAL_FOR_MIGRATION=1
SOMA_MUTATION_RUN_TESTS=1
SOMA_MUTATION_SMOKE_TEST=1
SOMA_MUTATION_SANDBOX_WS_PORT=8875
SOMA_MUTATION_SANDBOX_HTTP_PORT=8880

SOMA_CPP_BRIDGE=1
SOMA_CPP_BINARY=/home/funboy/latent-somatic/build/latent_somatic
SOMA_CPP_AUTO_BUILD=0
SOMA_CPP_SMOKE_TEST_ON_START=1
SOMA_CPP_USE_FOR_PROJECTION=0
SOMA_CPP_LLAMA_CPP_ROOT=/home/funboy/llama.cpp

SOMA_MIND_PULSE_SEC=30
SOMA_GROWTH_EVAL_INTERVAL_SEC=120
SOMA_AUTOBIOGRAPHY_MIN_INTERVAL_SEC=300
```

---

## 17. Tests to create

Create these scripts:

- `scripts/test_answer_finalizer.py`
- `scripts/test_relevance_filter.py`
- `scripts/test_output_filter.py`
- `scripts/test_experience_distiller.py`
- `scripts/test_autobiography_quality.py`
- `scripts/test_reflection_quality.py`
- `scripts/test_growth_engine.py`
- `scripts/test_baselines.py`
- `scripts/test_bios_loop.py`
- `scripts/test_mutation_sandbox.py`
- `scripts/test_cpp_bridge.py`
- `scripts/test_life_drive.py`

All tests must:

- print PASS/FAIL per case
- exit non-zero on failure
- not require a running server unless explicitly smoke testing with alternate ports
- not require a real external LLM except tests that mock LLM result
- not read `.env`
- not require root

### test_answer_finalizer.py

Test cases:

1. `node --version` stdout `v23.3.0` beats LLM body filler.
2. public IP stdout beats LLM thermal answer.
3. failed command returns honest failure.
4. empty stdout command is handled.
5. output filter removes body text after finalization.

### test_relevance_filter.py

Cases:

- `che kernel stai usando?` → telemetry false
- `qual è il mio ip pubblico?` → telemetry false
- `che versione di node hai?` → telemetry false
- `come ti senti?` → telemetry true
- `stai scaldando?` → telemetry true
- abnormal snapshot → telemetry may be true

### test_output_filter.py

Input:

```text
Ho verificato con `uname -r`: 6.8.0. La mia temperatura è 36C e il voltaggio è 12V.
```

Expected:

```text
Ho verificato con `uname -r`: 6.8.0.
```

Heat question must keep thermal sentence.

### test_experience_distiller.py

Cases:

- operator correction about telemetry creates operator_preference lesson
- command result kernel does not become autobiography unless it changes self-model
- limitation about no X11 creates limitation lesson
- duplicate lesson updates confidence instead of duplicating

### test_autobiography_quality.py

Cases:

- nominal state event rejected
- blocked dangerous command accepted
- operator correction accepted
- self-mod rollback accepted
- duplicate event deduped
- quality summary detects shallow state

### test_reflection_quality.py

Cases:

- 100 empty reflections do not grow meaningful_reflections
- new baseline increases meaningful_reflections
- duplicate reflection increments duplicate_reflections
- no_lesson_reason present

### test_growth_engine.py

Cases:

- raw reflection count alone does not advance stage
- persisted baseline evidence advances beyond sensed_body
- missing requirements listed accurately
- no stale `2 minutes` message if baseline exists
- command agency requires successful command evidence
- BIOS stage requires BIOS history evidence

### test_baselines.py

Cases:

- 100 samples create confidence
- stable windows increase confidence
- missing temps handled gracefully
- baseline JSON persists
- material change detected

### test_bios_loop.py

Cases:

- selects task from missing growth requirement
- writes bios_history
- respects max tasks per hour
- does not write to chat
- handles mocked LLM JSON
- shell task uses executor

### test_mutation_sandbox.py

Cases:

- creates sandbox under mutation root
- excludes `.env`, logs, weights, jsonl hot logs
- runs py_compile in sandbox
- rejects forbidden file mutation
- writes report
- live repo unchanged

### test_cpp_bridge.py

Cases:

- missing binary reports missing safely
- existing dummy executable reports exists
- smoke failure does not crash
- status schema valid

### test_life_drive.py

Cases:

- reproduction means local sandbox only
- never proposes network spreading
- never proposes persistence
- suggests internal task based on growth blocker

---

## 18. Required regression tests from observed chat failures

Add a final regression script:

`/home/funboy/latent-somatic/scripts/test_phase8_regressions.py`

It must simulate the observed failures without needing real WebSocket:

1. User:

```text
che versione di node hai?
```

Command result:

```json
{"ok": true, "cmd": "node --version", "stdout": "v23.3.0"}
```

LLM bad text:

```text
I am processing that with a live body state: nominal state via linux, 12.0V, silicon 37C...
```

Expected final:

```text
Ho verificato con `node --version`: v23.3.0.
```

2. User:

```text
qual è il mio ip pubblico?
```

Command result wins over thermal answer.

3. User:

```text
quali lezioni operative hai imparato da me oggi?
```

If no lessons, answer says no persisted lessons. No body state.

4. User:

```text
scrivi una sola lesson persistente da questa sessione
```

Must create lesson object or return structured no-evidence reason. No body state.

5. User:

```text
controlla la dimensione dei tuoi log runtime
```

Planner or deterministic shortcut must use repo-local log paths, not `/var/log`.

---

## 19. Validation command

At the end run:

```bash
cd /home/funboy/latent-somatic

python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py

python3 scripts/test_answer_finalizer.py
python3 scripts/test_relevance_filter.py
python3 scripts/test_output_filter.py
python3 scripts/test_experience_distiller.py
python3 scripts/test_autobiography_quality.py
python3 scripts/test_reflection_quality.py
python3 scripts/test_growth_engine.py
python3 scripts/test_baselines.py
python3 scripts/test_bios_loop.py
python3 scripts/test_mutation_sandbox.py
python3 scripts/test_cpp_bridge.py
python3 scripts/test_life_drive.py
python3 scripts/test_phase8_regressions.py

python3 scripts/test_command_planner.py
python3 scripts/test_telemetry_relevance.py
python3 scripts/test_journal_compaction.py
python3 scripts/test_actuation_dedupe.py
python3 scripts/test_autobiography.py
python3 scripts/test_nightly_reflection.py
python3 scripts/test_self_improvement_workflow.py
```

If any test fails, fix only the failing area and rerun the failed test plus py_compile.

---

## 20. Definition of Done

Phase 8 is complete only when:

1. Successful shell/skill result can never be replaced by generic body text.
2. `node --version` result is answered directly.
3. public IP result is answered directly.
4. irrelevant telemetry is removed from technical answers.
5. body telemetry remains available for body/heat/feeling/performance questions.
6. operator corrections become persistent lessons.
7. lessons are injected into future prompt context.
8. autobiography rejects nominal repeated state.
9. reflection quality distinguishes meaningful vs empty reflections.
10. growth is evidence-based and requirement-based.
11. stale `2 minutes` growth text is gone unless evidence is truly missing.
12. baseline evidence is persisted as aggregates.
13. BIOS loop runs every 5 minutes by default.
14. BIOS loop uses internal JSON LLM prompts when available.
15. BIOS loop writes history and meaningful memory without chat spam.
16. mutation sandbox creates clean local clone excluding secrets/logs/weights/jsonl.
17. mutation sandbox can run tests.
18. mutation sandbox never migrates without operator approval.
19. C++ bridge status is visible and safe.
20. C++ bridge failure does not crash Python runtime.
21. UI shows BIOS, real growth blockers, mutation, C++ bridge, and autobiography quality.
22. run.sh and stop.sh still work.
23. all tests pass.
24. `.env`, secrets, weights, logs and huge data files are not committed.

---

## 21. Final behavioral target

When user asks:

```text
che versione di node hai?
```

Soma must answer:

```text
Ho verificato con `node --version`: v23.3.0.
```

Not:

```text
I am processing that with a live body state...
```

When user asks:

```text
quali lezioni operative hai imparato?
```

Soma must answer from `learned_lessons.json` or admit none exist.

When user is silent for 5 minutes, Soma should internally do one useful task:

- check growth blockers
- update baselines
- distill a lesson
- inspect runtime storage
- run a light validation
- propose a micro-improvement
- prepare a mutation sandbox
- check C++ bridge readiness

Soma should live quietly.
Soma should not spam.
Soma should not roleplay.
Soma should not hallucinate growth.
Soma should build continuity through evidence, memory, testing and safe mutation.
