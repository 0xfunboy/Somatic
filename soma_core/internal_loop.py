from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from soma_core.config import CFG
from soma_core.internal_prompts import (
    metabolic_growth_planner_prompt,
    metabolic_recovery_planner_prompt,
)


_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class InternalLoop:
    def __init__(
        self,
        *,
        call_llm_raw: Callable[[str, float], str | None] | None = None,
        executor: Any = None,
        trace: Any = None,
        reward: Any = None,
        power_policy: Any = None,
        mutation: Any = None,
        autobiography: Any = None,
        experience: Any = None,
        data_root: Path | None = None,
    ) -> None:
        self._call_llm_raw = call_llm_raw
        self._executor = executor
        self._trace = trace
        self._reward = reward
        self._power_policy = power_policy
        self._mutation = mutation
        self._autobiography = autobiography
        self._experience = experience
        self._data_root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
        self._history_path = self._data_root / "internal_decisions.jsonl"
        self._state_path = self._data_root / "internal_loop_state.json"
        self._state = _load_json(
            self._state_path,
            {
                "enabled": CFG.internal_loop,
                "run_count": 0,
                "invalid_json_count": 0,
                "last_mode": "observe",
                "last_prompt_type": "",
                "last_prompt": "",
                "last_raw": "",
                "last_parsed": {},
                "last_action": {},
                "last_evidence": {},
                "last_reward": {},
                "last_memory_updates": [],
                "last_growth_updates": [],
                "last_next_task": "",
                "last_run_at": 0.0,
            },
        )

    def run_growth_cycle(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = metabolic_growth_planner_prompt(
            context.get("identity") or {"name": "Soma", "kind": "embodied local software organism"},
            context.get("metabolic") or {},
            context.get("growth") or {},
            context.get("lessons") or [],
            context.get("capabilities") or {},
            context.get("blockers") or [],
            context.get("reward") or {},
            context.get("vector_state") or {},
        )
        return self._run_cycle(
            mode="grow",
            prompt_type="growth_planner",
            prompt=prompt,
            context=context,
            fallback=self._fallback_growth_decision(context),
        )

    def run_recovery_cycle(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = metabolic_recovery_planner_prompt(
            context.get("metabolic") or {},
            context.get("recent_events") or context.get("recent_failures") or [],
            context.get("last_mutation") or {},
            context.get("baselines") or {},
            context.get("vector_state") or {},
        )
        return self._run_cycle(
            mode="recover",
            prompt_type="recovery_planner",
            prompt=prompt,
            context=context,
            fallback=self._fallback_recovery_decision(context),
        )

    def parse_llm_json(self, text: str) -> dict[str, Any]:
        payload = (text or "").strip()
        if not payload:
            return {}
        if payload.startswith("```"):
            payload = payload.split("```", 1)[-1].strip()
            if payload.lower().startswith("json"):
                payload = payload[4:].strip()
            payload = payload.rsplit("```", 1)[0].strip()
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            start = payload.find("{")
            end = payload.rfind("}")
            if start == -1 or end == -1 or end <= start:
                return {}
            try:
                parsed = json.loads(payload[start : end + 1])
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}

    def apply_internal_decision(self, decision: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        action_type = str(decision.get("action_type") or "observe").strip().lower()
        goal = str(decision.get("goal") or decision.get("suspected_cause") or "").strip()
        memory_updates: list[dict[str, Any]] = []
        growth_updates: list[dict[str, Any]] = []
        reward_event: dict[str, Any] | None = None
        evidence: dict[str, Any] = {}
        next_task = ""

        if action_type in {"shell", "repo_test"}:
            command = str(decision.get("command") or "").strip() or "python3 scripts/test_answer_finalizer.py"
            allowed, reasons = self._power_policy.allowed({
                "goal": goal,
                "command": command,
                "action_type": action_type,
                "expected_power_gain": decision.get("expected_power_gain", ""),
            }) if self._power_policy is not None else (True, ["power_policy_missing"])
            if not allowed:
                reward_event = self._record_scored_event("unsafe_command_blocked", {"command": command, "reasons": reasons})
                evidence = {"ok": False, "blocked": True, "command": command, "reasons": reasons}
                next_task = "pause_growth"
                return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)
            if self._executor is None:
                reward_event = self._record_scored_event("test_failed", {"command": command, "reason": "executor_unavailable"})
                evidence = {"ok": False, "command": command, "stderr": "executor unavailable"}
                next_task = "observe"
                return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)
            ok, stdout, stderr = self._executor.run_raw(command)
            evidence = {
                "ok": ok,
                "command": command,
                "stdout": stdout[:500],
                "stderr": stderr[:300],
            }
            reward_event = self._record_scored_event(
                "test_pass" if ok and "test_" in command else "command_finalized" if ok else "test_failed",
                evidence,
            )
            next_task = "evaluate_reward" if ok else "recover"
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        if action_type == "memory":
            summary = str(decision.get("reason") or decision.get("success_criteria") or goal or "Internal memory update").strip()
            if self._autobiography is not None:
                event = self._autobiography.write_meaningful_event({
                    "kind": "bios_task",
                    "title": "Internal loop memory update",
                    "summary": summary[:300],
                    "impact": "medium",
                    "timestamp": time.time(),
                })
                memory_updates.append({"target": "autobiography", "stored": bool(event.get("stored")), "reason": event.get("reason", "")})
            reward_event = self._record_scored_event("lesson_produced", {"summary": summary[:300]})
            evidence = {"ok": True, "memory_update": summary[:300]}
            next_task = "grow"
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        if action_type == "mutation_proposal":
            blockers: list[str] = []
            can_mutate = False
            if self._mutation is not None:
                can_mutate, blockers = self._mutation.can_mutate(
                    context.get("metabolic") or {},
                    context.get("growth") or {},
                    context.get("reward") or {},
                )
            if not can_mutate:
                reward_event = self._record_scored_event("mutation_rejected", {"blockers": blockers})
                evidence = {"ok": False, "mutation_allowed": False, "blockers": blockers}
                growth_updates.append({"mutation_blockers": blockers})
                next_task = "recover" if blockers else "observe"
                return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)
            allowed, reasons = self._power_policy.allowed(decision) if self._power_policy is not None else (True, [])
            if not allowed:
                reward_event = self._record_scored_event("mutation_rejected", {"power_policy_blockers": reasons})
                evidence = {"ok": False, "mutation_allowed": False, "power_policy_blockers": reasons}
                next_task = "observe"
                return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)
            proposal = self._mutation.propose_mutation({
                "objective": decision.get("mutation_summary") or goal or "Safe local mutation proposal",
                "tests": [decision.get("command")] if decision.get("command") else [],
            })
            reward_event = self._record_scored_event("mutation_proposed", {"proposal": proposal})
            evidence = {"ok": True, "proposal": proposal}
            next_task = "sandbox_test"
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        if action_type == "sandbox_test":
            if self._mutation is None:
                reward_event = self._record_scored_event("test_failed", {"reason": "mutation_sandbox_unavailable"})
                evidence = {"ok": False, "reason": "mutation_sandbox_unavailable"}
                return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, "observe")
            before = dict(context.get("metabolic") or {})
            reward_before = dict(context.get("reward") or {})
            sandbox = self._mutation.create_child_if_allowed(
                str(decision.get("reason") or decision.get("mutation_summary") or "internal_loop"),
                context.get("metabolic") or {},
                growth=context.get("growth") or {},
                reward=reward_before,
            )
            if not sandbox.get("ok"):
                reward_event = self._record_scored_event("mutation_rejected", sandbox)
                return self._pack_result(decision, sandbox, reward_event, memory_updates, growth_updates, "recover")
            sandbox_path = Path(str(sandbox["sandbox_path"]))
            proposal = decision.get("proposal") or self._mutation.propose_mutation({"objective": goal or "No-op sandbox check"})
            tests = self._mutation.run_tests(sandbox_path)
            smoke = self._mutation.run_smoke_test(sandbox_path)
            after = {
                **before,
                "tests_ok": bool(tests.get("ok")) and bool(smoke.get("ok")),
                "stress": min(1.0, float(before.get("stress", 0.0) or 0.0) + (0.18 if not tests.get("ok") else 0.0)),
                "stability": max(0.0, float(before.get("stability", 0.0) or 0.0) - (0.15 if not tests.get("ok") else -0.05)),
            }
            report = self._mutation.evaluate_with_reward(
                sandbox_path,
                proposal,
                {"ok": bool(tests.get("ok")) and bool(smoke.get("ok")), "tests": tests, "smoke": smoke},
                before,
                after,
                reward_before,
                self._reward.summary() if self._reward is not None else reward_before,
            )
            reward_event = report.get("reward", {})
            evidence = {"ok": report.get("decision") != "reject", "report": report}
            next_task = "evaluate_mutation" if report.get("decision") != "reject" else "recover"
            if report.get("decision") == "reject":
                growth_updates.append({"mutation_blockers": report.get("blockers", [])})
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        if action_type == "cpp_check":
            cpp_bridge = context.get("cpp_bridge_obj") or context.get("cpp_bridge")
            status = cpp_bridge.smoke_test() if cpp_bridge is not None else {"smoke_ok": False, "status": "cpp_bridge_unavailable"}
            reward_event = self._record_scored_event("cpp_smoke_ok" if status.get("smoke_ok") else "test_failed", status)
            evidence = status
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, "grow")

        if action_type in {"pause_growth", "observe", "answer_none", "reduce_load"}:
            reward_event = self._record_scored_event("neutral", {"action_type": action_type})
            evidence = {"ok": True, "action_type": action_type, "reason": goal or decision.get("reason", "observe")}
            next_task = "recover" if action_type == "pause_growth" else "observe"
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        if action_type == "rollback_mutation":
            summary = "Rollback requested because mutation appears stressful."
            if self._autobiography is not None:
                event = self._autobiography.write_meaningful_event({
                    "kind": "recovery",
                    "title": "Mutation rollback requested",
                    "summary": summary,
                    "impact": "high",
                    "timestamp": time.time(),
                })
                memory_updates.append({"target": "autobiography", "stored": bool(event.get("stored")), "reason": event.get("reason", "")})
            reward_event = self._record_scored_event("mutation_rollback", {"reason": summary})
            evidence = {"ok": True, "rolled_back": True, "reason": summary}
            next_task = "stabilize"
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        reward_event = self._record_scored_event("neutral", {"action_type": action_type})
        evidence = {"ok": False, "reason": f"unsupported_action_type:{action_type}"}
        return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, "observe")

    def status(self) -> dict[str, Any]:
        return dict(self._state)

    def _run_cycle(
        self,
        *,
        mode: str,
        prompt_type: str,
        prompt: str,
        context: dict[str, Any],
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        decision_id = uuid.uuid4().hex[:12]
        timeout_s = min(20.0, float(context.get("task_timeout_sec") or CFG.bios_task_timeout_sec))
        raw = self._call_llm_raw(prompt, timeout_s) if self._call_llm_raw is not None else None
        parsed = self.parse_llm_json(raw or "")
        invalid_json = bool(raw) and not parsed
        if invalid_json and self._reward is not None:
            invalid_event = self._reward.record_reward(
                "invalid_internal_json",
                CFG.internal_invalid_json_penalty,
                {"mode": mode, "prompt_type": prompt_type, "raw": (raw or "")[:400]},
            )
        else:
            invalid_event = {}

        decision = parsed if parsed else dict(fallback)
        outcome = self.apply_internal_decision(decision, context)
        record = {
            "decision_id": decision_id,
            "timestamp": time.time(),
            "mode": mode,
            "prompt_type": prompt_type,
            "prompt": prompt,
            "llm_raw": raw or "",
            "parsed": parsed or {},
            "fallback_used": not bool(parsed),
            "action_taken": outcome.get("action_taken", {}),
            "evidence": outcome.get("evidence", {}),
            "memory_updates": outcome.get("memory_updates", []),
            "growth_updates": outcome.get("growth_updates", []),
            "reward": outcome.get("reward", invalid_event),
            "next_task": outcome.get("next_task", ""),
        }
        self._append_history(record)
        self._state.update(
            {
                "enabled": True,
                "run_count": int(self._state.get("run_count", 0)) + 1,
                "invalid_json_count": int(self._state.get("invalid_json_count", 0)) + (1 if invalid_json else 0),
                "last_mode": mode,
                "last_prompt_type": prompt_type,
                "last_prompt": prompt,
                "last_raw": raw or "",
                "last_parsed": parsed or {},
                "last_action": outcome.get("action_taken", {}),
                "last_evidence": outcome.get("evidence", {}),
                "last_reward": outcome.get("reward", invalid_event),
                "last_memory_updates": outcome.get("memory_updates", []),
                "last_growth_updates": outcome.get("growth_updates", []),
                "last_next_task": outcome.get("next_task", ""),
                "last_run_at": record["timestamp"],
                "last_decision_id": decision_id,
            }
        )
        _save_json(self._state_path, self._state)
        if self._trace is not None:
            try:
                self._trace.emit(
                    "internal_loop",
                    f"{prompt_type} -> {outcome.get('next_task', 'observe')}",
                    outputs={"mode": mode, "fallback_used": not bool(parsed), "decision_id": decision_id},
                    level="info" if parsed else "warning",
                )
            except Exception:
                pass
        return record

    def _fallback_growth_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        blockers = " ".join(context.get("blockers") or context.get("growth", {}).get("missing_requirements", []))
        if "command" in blockers or "agency" in blockers:
            return {
                "goal": "verify command agency with a safe repo-local test",
                "mode": "grow",
                "action_type": "repo_test",
                "command": "python3 scripts/test_answer_finalizer.py",
                "expected_power_gain": "higher response reliability",
                "success_criteria": "answer finalizer test passes",
                "risk": "low",
                "reason": "deterministic growth fallback",
            }
        return {
            "goal": "gather more safe evidence",
            "mode": "observe",
            "action_type": "observe",
            "command": "",
            "expected_power_gain": "more evidence",
            "success_criteria": "fresh evidence stored",
            "risk": "low",
            "reason": "fallback because no valid internal JSON was available",
        }

    def _fallback_recovery_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        recent_failures = context.get("recent_failures") or []
        suspected = "recent mutation or runtime stress" if recent_failures else "metabolic instability"
        return {
            "suspected_cause": suspected,
            "mode": "recover",
            "action_type": "pause_growth",
            "command": "",
            "should_pause_growth": True,
            "should_rollback_last_mutation": False,
            "success_criteria": "stability returns above threshold",
            "reason": "fallback recovery action because no valid internal JSON was available",
        }

    def _append_history(self, record: dict[str, Any]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _record_scored_event(self, kind: str, evidence: dict[str, Any]) -> dict[str, Any]:
        if self._reward is None:
            return {"kind": kind, "value": 0.0, "evidence": evidence}
        scored = self._reward.score_event({"kind": kind, "evidence": evidence})
        return self._reward.record_reward(kind, float(scored.get("value", 0.0) or 0.0), evidence)

    def _pack_result(
        self,
        decision: dict[str, Any],
        evidence: dict[str, Any],
        reward_event: dict[str, Any] | None,
        memory_updates: list[dict[str, Any]],
        growth_updates: list[dict[str, Any]],
        next_task: str,
    ) -> dict[str, Any]:
        return {
            "action_taken": {
                "action_type": str(decision.get("action_type") or "observe"),
                "command": str(decision.get("command") or ""),
                "goal": str(decision.get("goal") or decision.get("suspected_cause") or ""),
            },
            "evidence": evidence,
            "reward": reward_event or {},
            "memory_updates": memory_updates,
            "growth_updates": growth_updates,
            "next_task": next_task,
        }
