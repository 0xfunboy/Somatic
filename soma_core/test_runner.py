from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable


@dataclass(frozen=True)
class TestStep:
    id: str
    title: str
    command: str
    description: str = ""
    timeout_sec: float = 60.0


@dataclass(frozen=True)
class TestSuite:
    id: str
    label: str
    description: str
    category: str
    estimated_minutes: float
    steps: tuple[TestStep, ...]
    requires_live_backend: bool = False
    stop_on_failure: bool = False


def _suite_catalog() -> tuple[TestSuite, ...]:
    return (
        TestSuite(
            id="runtime_smoke",
            label="Runtime Smoke",
            description="Checks the live WebSocket runtime, the current payload family, and a repo-local runtime storage report.",
            category="live",
            estimated_minutes=0.6,
            requires_live_backend=True,
            steps=(
                TestStep(
                    id="ws_smoke",
                    title="WebSocket smoke",
                    command="python3 scripts/ws_smoke_test.py --host 127.0.0.1 --port {ws_port} --timeout 20 --text 'show your last BIOS internal prompt'",
                    description="Confirms init, tick, and chat_reply over the currently running backend.",
                    timeout_sec=30.0,
                ),
                TestStep(
                    id="runtime_storage_report",
                    title="Runtime storage report",
                    command="python3 scripts/runtime_storage_report.py",
                    description="Summarizes repo-local runtime/journal/mind storage usage.",
                    timeout_sec=20.0,
                ),
            ),
        ),
        TestSuite(
            id="phase9_core",
            label="Phase 9 Core Validation",
            description="The high-signal metabolic / BIOS / introspection validation block required by the current runtime, including compact prompt persistence.",
            category="validation",
            estimated_minutes=1.2,
            steps=(
                TestStep("py_compile", "Python compile", "python3 -m py_compile server.py soma_core/*.py sensor_providers/*.py", "Validates Python syntax across the runtime.", 30.0),
                TestStep("test_metabolism", "Metabolic engine", "python3 scripts/test_metabolism.py", "Checks calibrated confidence, growth gating, and recovery switching.", 30.0),
                TestStep("test_internal_loop", "Internal loop", "python3 scripts/test_internal_loop.py", "Checks JSON planning, fallback persistence, and stabilize/observe execution.", 30.0),
                TestStep("test_bios_loop", "BIOS loop", "python3 scripts/test_bios_loop.py", "Checks BIOS integration and compact prompt persistence.", 30.0),
                TestStep("test_phase9_introspection", "Phase 9 introspection", "python3 scripts/test_phase9_introspection.py", "Checks deterministic introspection over persisted internal state.", 30.0),
                TestStep("test_growth_recovery_switch", "Growth / recovery switch", "python3 scripts/test_growth_recovery_switch.py", "Checks mutation gating when recovery is required.", 30.0),
            ),
        ),
        TestSuite(
            id="phase9_2_resource",
            label="Phase 9.2 Resource Governor",
            description="Validation for host-preservation, tick throttling, compact state, payload cadence, BIOS yielding, and resource-aware metabolism.",
            category="validation",
            estimated_minutes=1.6,
            steps=(
                TestStep("test_resource_governor", "Resource governor", "python3 scripts/test_resource_governor.py", "Checks host-pressure mode selection and recovery behavior.", 30.0),
                TestStep("test_budgeted_scheduler", "Budgeted scheduler", "python3 scripts/test_budgeted_scheduler.py", "Checks interval gating and heavy-operation blocking.", 30.0),
                TestStep("test_tick_throttling", "Tick throttling", "python3 scripts/test_tick_throttling.py", "Checks resource-capped tick rate and projector throttling.", 30.0),
                TestStep("test_state_compaction", "State compaction", "python3 scripts/test_state_compaction.py", "Checks prompt archiving and compact persisted state.", 30.0),
                TestStep("test_payload_throttling", "Payload throttling", "python3 scripts/test_payload_throttling.py", "Checks light/full payload cadence and meaningful full refreshes.", 30.0),
                TestStep("test_resource_metabolism", "Resource metabolism", "python3 scripts/test_resource_metabolism.py", "Checks host pressure effects on growth, stress, and rewards.", 30.0),
                TestStep("test_resource_bios_gating", "Resource BIOS gating", "python3 scripts/test_resource_bios_gating.py", "Checks BIOS yield, interval stretching, and critical-mode LLM blocking.", 30.0),
            ),
        ),
        TestSuite(
            id="cognition_regressions",
            label="Cognition Regressions",
            description="Regression coverage for answer finalization, relevance/output filters, growth, reward, and vector interpretation.",
            category="regression",
            estimated_minutes=1.8,
            steps=(
                TestStep("test_answer_finalizer", "Answer finalizer", "python3 scripts/test_answer_finalizer.py"),
                TestStep("test_output_filter", "Output filter", "python3 scripts/test_output_filter.py"),
                TestStep("test_relevance_filter", "Relevance filter", "python3 scripts/test_relevance_filter.py"),
                TestStep("test_growth_engine", "Growth engine", "python3 scripts/test_growth_engine.py"),
                TestStep("test_vector_interpreter", "Vector interpreter", "python3 scripts/test_vector_interpreter.py"),
                TestStep("test_reward_engine", "Reward engine", "python3 scripts/test_reward_engine.py"),
                TestStep("test_power_policy", "Power policy", "python3 scripts/test_power_policy.py"),
                TestStep("test_mutation_reward", "Mutation reward", "python3 scripts/test_mutation_reward.py"),
                TestStep("test_command_planner", "Command planner", "python3 scripts/test_command_planner.py"),
                TestStep("test_telemetry_relevance", "Telemetry relevance", "python3 scripts/test_telemetry_relevance.py"),
            ),
        ),
        TestSuite(
            id="memory_reflection",
            label="Memory and Reflection",
            description="Checks autobiographical quality, baselines, journaling, nightly reflection, and self-improvement workflow glue.",
            category="memory",
            estimated_minutes=1.8,
            steps=(
                TestStep("test_autobiography", "Autobiography", "python3 scripts/test_autobiography.py"),
                TestStep("test_autobiography_quality", "Autobiography quality", "python3 scripts/test_autobiography_quality.py"),
                TestStep("test_baselines", "Body baselines", "python3 scripts/test_baselines.py"),
                TestStep("test_experience_distiller", "Experience distiller", "python3 scripts/test_experience_distiller.py"),
                TestStep("test_reflection_quality", "Reflection quality", "python3 scripts/test_reflection_quality.py"),
                TestStep("test_nightly_reflection", "Nightly reflection", "python3 scripts/test_nightly_reflection.py"),
                TestStep("test_journal_compaction", "Journal compaction", "python3 scripts/test_journal_compaction.py"),
                TestStep("test_life_drive", "Life drive", "python3 scripts/test_life_drive.py"),
                TestStep("test_self_improvement_workflow", "Self-improvement workflow", "python3 scripts/test_self_improvement_workflow.py"),
            ),
        ),
        TestSuite(
            id="sandbox_cpp",
            label="Sandbox and C++ Bridge",
            description="Checks mutation sandbox exclusions/flow and C++ bridge status handling without requiring migration.",
            category="systems",
            estimated_minutes=1.2,
            steps=(
                TestStep("test_mutation_sandbox", "Mutation sandbox", "python3 scripts/test_mutation_sandbox.py"),
                TestStep("test_cpp_bridge", "C++ bridge", "python3 scripts/test_cpp_bridge.py"),
                TestStep("test_phase8_regressions", "Phase 8 regressions", "python3 scripts/test_phase8_regressions.py"),
            ),
        ),
    )


class FrontendTestRunner:
    def __init__(
        self,
        *,
        execute_command: Callable[[str, float], tuple[bool, str, str]],
        ws_port_getter: Callable[[], int],
    ) -> None:
        self._execute_command = execute_command
        self._ws_port_getter = ws_port_getter
        self._suites = {suite.id: suite for suite in _suite_catalog()}
        self._lock = asyncio.Lock()
        self._status: dict[str, Any] = {
            "busy": False,
            "active_suite_id": "",
            "active_suite_label": "",
            "active_step_id": "",
            "active_step_title": "",
            "last_suite_id": "",
            "last_suite_label": "",
            "last_status": "idle",
            "last_summary": "",
            "last_run_started_at": 0.0,
            "last_run_completed_at": 0.0,
            "passed_steps": 0,
            "failed_steps": 0,
            "total_steps": 0,
            "history": [],
        }

    def catalog(self) -> list[dict[str, Any]]:
        return [
            {
                "id": suite.id,
                "label": suite.label,
                "description": suite.description,
                "category": suite.category,
                "estimated_minutes": suite.estimated_minutes,
                "requires_live_backend": suite.requires_live_backend,
                "steps": [
                    {
                        "id": step.id,
                        "title": step.title,
                        "description": step.description,
                        "timeout_sec": step.timeout_sec,
                    }
                    for step in suite.steps
                ],
            }
            for suite in self._suites.values()
        ]

    def status(self) -> dict[str, Any]:
        return dict(self._status)

    async def run_suite(
        self,
        suite_id: str,
        *,
        emit: Callable[[dict[str, Any]], Awaitable[None]],
    ) -> dict[str, Any]:
        suite = self._suites.get(suite_id)
        if suite is None:
            return {"ok": False, "reason": "unknown_suite"}

        async with self._lock:
            started_at = time.time()
            self._status.update(
                {
                    "busy": True,
                    "active_suite_id": suite.id,
                    "active_suite_label": suite.label,
                    "active_step_id": "",
                    "active_step_title": "",
                    "last_suite_id": suite.id,
                    "last_suite_label": suite.label,
                    "last_status": "running",
                    "last_summary": "",
                    "last_run_started_at": started_at,
                    "last_run_completed_at": 0.0,
                    "passed_steps": 0,
                    "failed_steps": 0,
                    "total_steps": len(suite.steps),
                }
            )
            await emit(
                {
                    "type": "test_run_started",
                    "suite": self._suite_public(suite),
                    "runner": self.status(),
                }
            )

            step_results: list[dict[str, Any]] = []
            for idx, step in enumerate(suite.steps, start=1):
                self._status["active_step_id"] = step.id
                self._status["active_step_title"] = step.title
                await emit(
                    {
                        "type": "test_step_started",
                        "suite_id": suite.id,
                        "step_index": idx,
                        "step_total": len(suite.steps),
                        "step": self._step_public(step),
                        "runner": self.status(),
                    }
                )
                resolved = step.command.format(ws_port=self._ws_port_getter())
                t0 = time.perf_counter()
                ok, stdout, stderr = await asyncio.to_thread(self._execute_command, resolved, step.timeout_sec)
                duration_ms = round((time.perf_counter() - t0) * 1000.0, 1)
                result = self._build_step_result(step, resolved, ok, stdout, stderr, duration_ms)
                step_results.append(result)
                if ok:
                    self._status["passed_steps"] = int(self._status.get("passed_steps", 0)) + 1
                else:
                    self._status["failed_steps"] = int(self._status.get("failed_steps", 0)) + 1
                await emit(
                    {
                        "type": "test_step_result",
                        "suite_id": suite.id,
                        "step_index": idx,
                        "step_total": len(suite.steps),
                        "step": result,
                        "runner": self.status(),
                    }
                )
                if suite.stop_on_failure and not ok:
                    break

            completed_at = time.time()
            suite_ok = all(item["ok"] for item in step_results) and bool(step_results)
            summary = self._suite_summary(suite, step_results)
            self._status.update(
                {
                    "busy": False,
                    "active_suite_id": "",
                    "active_suite_label": "",
                    "active_step_id": "",
                    "active_step_title": "",
                    "last_status": "passed" if suite_ok else "failed",
                    "last_summary": summary,
                    "last_run_completed_at": completed_at,
                }
            )
            history = list(self._status.get("history") or [])
            history.append(
                {
                    "suite_id": suite.id,
                    "suite_label": suite.label,
                    "ok": suite_ok,
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "passed_steps": self._status["passed_steps"],
                    "failed_steps": self._status["failed_steps"],
                    "summary": summary,
                }
            )
            self._status["history"] = history[-12:]
            payload = {
                "type": "test_run_completed",
                "suite_id": suite.id,
                "suite_label": suite.label,
                "ok": suite_ok,
                "summary": summary,
                "results": step_results,
                "runner": self.status(),
            }
            await emit(payload)
            return payload

    def _build_step_result(
        self,
        step: TestStep,
        resolved_command: str,
        ok: bool,
        stdout: str,
        stderr: str,
        duration_ms: float,
    ) -> dict[str, Any]:
        stdout = (stdout or "").strip()
        stderr = (stderr or "").strip()
        pass_count = len(re.findall(r"^PASS\b", stdout, flags=re.MULTILINE))
        fail_count = len(re.findall(r"^FAIL\b", stdout, flags=re.MULTILINE))
        summary = ""
        json_preview: dict[str, Any] | None = None
        if stdout.startswith("{") and stdout.endswith("}"):
            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError:
                payload = None
            if isinstance(payload, dict):
                json_preview = payload
                if payload.get("ok") is True:
                    summary = self._json_summary(payload)
        if not summary:
            if fail_count:
                summary = f"{fail_count} assertion(s) failed, {pass_count} passed."
            elif pass_count:
                summary = f"{pass_count} assertion(s) passed."
            elif ok and stdout:
                summary = stdout.splitlines()[0][:180]
            elif ok:
                summary = "Command exited successfully."
            else:
                summary = (stderr or stdout or "Command failed.")[:180]
        return {
            "id": step.id,
            "title": step.title,
            "description": step.description,
            "command": resolved_command,
            "ok": bool(ok),
            "duration_ms": duration_ms,
            "summary": summary,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "stdout_preview": stdout[:1200],
            "stderr_preview": stderr[:600],
            "json_preview": json_preview,
        }

    def _json_summary(self, payload: dict[str, Any]) -> str:
        if "reply_preview" in payload:
            provider = payload.get("provider") or "unknown"
            llm_mode = payload.get("llm_mode") or "unknown"
            return f"WebSocket smoke passed via {provider}; llm={llm_mode}."
        if "mind_kb" in payload or "runtime_kb" in payload:
            return "Runtime storage report generated."
        return "Structured runtime report generated."

    def _suite_summary(self, suite: TestSuite, results: list[dict[str, Any]]) -> str:
        total = len(results)
        failed = sum(1 for item in results if not item["ok"])
        passed = total - failed
        if failed == 0:
            return f"{suite.label}: all {passed}/{total} step(s) passed."
        failed_titles = ", ".join(item["title"] for item in results if not item["ok"])
        return f"{suite.label}: {passed}/{total} step(s) passed; failures: {failed_titles}."

    def _suite_public(self, suite: TestSuite) -> dict[str, Any]:
        return {
            "id": suite.id,
            "label": suite.label,
            "description": suite.description,
            "category": suite.category,
            "estimated_minutes": suite.estimated_minutes,
            "requires_live_backend": suite.requires_live_backend,
            "step_count": len(suite.steps),
        }

    def _step_public(self, step: TestStep) -> dict[str, Any]:
        return {
            "id": step.id,
            "title": step.title,
            "description": step.description,
            "timeout_sec": step.timeout_sec,
        }
