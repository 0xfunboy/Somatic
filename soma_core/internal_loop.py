from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from soma_core.config import CFG
from soma_core.internal_prompts import (
    metabolic_growth_planner_prompt,
    metabolic_observation_planner_prompt,
    metabolic_recovery_planner_prompt,
    metabolic_stabilization_planner_prompt,
)
from soma_core.state_compaction import (
    append_prompt_ledger_entry,
    compact_json_value,
    compact_prompt,
    load_jsonl_tail,
    maybe_compact_json_state,
    prompt_preview,
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
        resource_governor: Any = None,
        emit_event: Callable[[dict[str, Any]], None] | None = None,
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
        self._resource_governor = resource_governor
        self._emit_event = emit_event
        self._data_root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
        self._history_path = self._data_root / "internal_decisions.jsonl"
        self._state_path = self._data_root / "internal_loop_state.json"
        self._prompt_index_path = self._data_root / "internal_prompt_index.jsonl"
        if CFG.auto_compact_mind_state:
            maybe_compact_json_state(self._state_path, apply=True)
        self._state = _load_json(
            self._state_path,
            {
                "enabled": CFG.internal_loop,
                "run_count": 0,
                "invalid_json_count": 0,
                "last_mode": "observe",
                "last_prompt_type": "",
                "last_prompt": {},
                "last_prompt_preview": "",
                "last_prompt_path": "",
                "last_raw": {},
                "last_raw_preview": "",
                "last_raw_path": "",
                "last_parsed": {},
                "last_parsed_fallback": {},
                "last_fallback": False,
                "last_action": {},
                "last_action_taken": {},
                "last_evidence": {},
                "last_reward": {},
                "last_reward_delta": 0.0,
                "last_memory_updates": [],
                "last_growth_updates": [],
                "last_next_task": "",
                "last_goal": "",
                "last_reason": "",
                "last_expected_power_gain": "",
                "last_success_criteria": "",
                "last_rollback_plan": "",
                "last_resource_mode": "",
                "last_metabolic_mode": "",
                "last_error": "",
                "last_llm_allowed": False,
                "last_llm_called_at": 0.0,
                "last_run_at": 0.0,
            },
        )
        self._seed_prompt_ledger_from_state()
        self._llm_call_times: list[float] = []

    def run_mode_cycle(self, mode: str, context: dict[str, Any]) -> dict[str, Any]:
        normalized = str(mode or "observe").strip().lower()
        if normalized == "recover":
            return self.run_recovery_cycle(context)
        if normalized == "stabilize":
            return self.run_stabilization_cycle(context)
        if normalized == "observe":
            return self.run_observation_cycle(context)
        if normalized in {"grow", "mutate", "evaluate", "reproduce"}:
            return self.run_growth_cycle(context, mode=normalized)
        return self.run_observation_cycle(context)

    def run_growth_cycle(self, context: dict[str, Any], *, mode: str = "grow") -> dict[str, Any]:
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
            mode=mode,
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

    def run_stabilization_cycle(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = metabolic_stabilization_planner_prompt(
            context.get("identity") or {"name": "Soma", "kind": "embodied local software organism"},
            context.get("metabolic") or {},
            context.get("current_blocker") or {},
            context.get("baselines") or {},
            context.get("recent_events") or context.get("recent_failures") or [],
            context.get("vector_state") or {},
            context.get("reward") or {},
        )
        return self._run_cycle(
            mode="stabilize",
            prompt_type="stabilization_planner",
            prompt=prompt,
            context=context,
            fallback=self._fallback_stabilization_decision(context),
        )

    def run_observation_cycle(self, context: dict[str, Any]) -> dict[str, Any]:
        prompt = metabolic_observation_planner_prompt(
            context.get("identity") or {"name": "Soma", "kind": "embodied local software organism"},
            context.get("metabolic") or {},
            context.get("baselines") or {},
            context.get("recent_events") or context.get("recent_failures") or [],
            context.get("vector_state") or {},
            context.get("reward") or {},
        )
        return self._run_cycle(
            mode="observe",
            prompt_type="observation_planner",
            prompt=prompt,
            context=context,
            fallback=self._fallback_observation_decision(context),
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
            summary = str(
                decision.get("memory_update")
                or decision.get("reason")
                or decision.get("success_criteria")
                or goal
                or "Internal memory update"
            ).strip()
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
            evidence = {
                "ok": True,
                "memory_update": summary[:300],
                "evidence": decision.get("evidence") or [],
                "success_criteria": str(decision.get("success_criteria") or ""),
                "next_check": str(decision.get("next_check") or ""),
            }
            next_task = str(decision.get("next_check") or "observe")
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
            growth_updates.append(
                {
                    "mutation_proposal": {
                        "mutation_id": proposal.get("mutation_id", ""),
                        "objective": proposal.get("objective", ""),
                    }
                }
            )
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
            growth_updates.append(
                {
                    "sandbox_test": {
                        "decision": report.get("decision", ""),
                        "mutation_id": report.get("mutation_id", ""),
                    }
                }
            )
            if report.get("decision") == "reject":
                growth_updates.append({"mutation_blockers": report.get("blockers", [])})
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, next_task)

        if action_type == "cpp_check":
            cpp_bridge = context.get("cpp_bridge_obj") or context.get("cpp_bridge")
            status = cpp_bridge.smoke_test() if cpp_bridge is not None else {"smoke_ok": False, "status": "cpp_bridge_unavailable"}
            reward_event = self._record_scored_event("cpp_smoke_ok" if status.get("smoke_ok") else "test_failed", status)
            evidence = status
            return self._pack_result(decision, evidence, reward_event, memory_updates, growth_updates, "grow")

        if action_type in {"pause_growth", "observe", "answer_none", "reduce_load", "recover"}:
            reward_kind = "recovery_reason_recorded" if action_type in {"pause_growth", "recover", "reduce_load"} else "evidence_recorded"
            reward_event = self._record_scored_event(reward_kind, {"action_type": action_type, "goal": goal})
            evidence = {
                "ok": True,
                "action_type": action_type,
                "reason": goal or decision.get("reason", "observe"),
                "evidence": decision.get("evidence") or [],
                "success_criteria": str(decision.get("success_criteria") or ""),
                "next_check": str(decision.get("next_check") or ""),
                "memory_update": str(decision.get("memory_update") or ""),
            }
            next_task = str(decision.get("next_check") or ("recover" if action_type in {"pause_growth", "recover", "reduce_load"} else "observe"))
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
        state = dict(self._state)
        state["ledger_tail"] = self.last_decisions(limit=3)
        return state

    def last_decisions(self, limit: int = 3) -> list[dict[str, Any]]:
        return load_jsonl_tail(self._prompt_index_path, limit=max(1, int(limit)))

    def _seed_prompt_ledger_from_state(self) -> None:
        try:
            if self._prompt_index_path.exists() and self._prompt_index_path.stat().st_size > 0:
                return
        except OSError:
            return

        prompt_ref = self._state.get("last_prompt") or {}
        raw_ref = self._state.get("last_raw") or {}
        prompt_path = str(self._state.get("last_prompt_path") or prompt_ref.get("archive_path") or "")
        raw_path = str(self._state.get("last_raw_path") or raw_ref.get("archive_path") or "")
        decision = self._state.get("last_parsed") or self._state.get("last_parsed_fallback") or {}
        evidence = self._state.get("last_evidence") or {}
        action = self._state.get("last_action_taken") or self._state.get("last_action") or {}
        if not (prompt_path or raw_path or decision or evidence or action):
            return

        summary = str(
            decision.get("reason")
            or self._state.get("last_reason")
            or action.get("goal")
            or self._state.get("last_goal")
            or "persisted internal state replay"
        )[:240]
        evidence_summary = prompt_preview(json.dumps(evidence, ensure_ascii=False), limit=240) if evidence else ""
        entry = {
            "id": str(self._state.get("last_decision_id") or f"seed-{int(float(self._state.get('last_run_at', 0.0) or 0.0))}"),
            "timestamp": float(self._state.get("last_run_at", 0.0) or 0.0),
            "mode": str(self._state.get("last_mode") or self._state.get("last_metabolic_mode") or "observe"),
            "prompt_type": str(self._state.get("last_prompt_type") or ""),
            "prompt_hash": str(prompt_ref.get("sha1") or ""),
            "prompt_path": prompt_path,
            "raw_hash": str(raw_ref.get("sha1") or ""),
            "raw_path": raw_path,
            "parsed_valid": bool(self._state.get("last_parsed")),
            "fallback": bool(self._state.get("last_fallback")),
            "decision_summary": summary,
            "action_type": str(action.get("action_type") or decision.get("action_type") or ""),
            "evidence_summary": evidence_summary,
            "reward_delta": float(self._state.get("last_reward_delta", 0.0) or 0.0),
            "resource_mode": str(self._state.get("last_resource_mode") or ""),
            "metabolic_mode": str(self._state.get("last_metabolic_mode") or self._state.get("last_mode") or ""),
        }
        append_prompt_ledger_entry(self._data_root, entry)

    def _resource_mode(self, context: dict[str, Any]) -> str:
        resource = context.get("resource") or {}
        metabolic = context.get("metabolic") or {}
        return str(resource.get("mode") or metabolic.get("resource_mode") or "normal").strip().lower()

    def _seconds_since_user_input(self, context: dict[str, Any]) -> float | None:
        value = context.get("seconds_since_user_input")
        if value is None:
            value = context.get("seconds_since_last_user_input")
        if value is None:
            value = context.get("user_idle_sec")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return None

    def _prune_llm_calls(self, now: float) -> None:
        hour_ago = now - 3600.0
        self._llm_call_times = [item for item in self._llm_call_times if item > hour_ago]

    def _llm_gate(self, mode: str, context: dict[str, Any]) -> tuple[bool, str]:
        now = time.time()
        self._prune_llm_calls(now)
        if self._call_llm_raw is None:
            return False, "llm_unavailable"
        resource_mode = self._resource_mode(context)
        since_user = self._seconds_since_user_input(context)
        if since_user is not None and since_user < CFG.internal_llm_skip_on_user_active_sec and mode != "recover":
            return False, "user_recently_active"
        if (
            CFG.internal_llm_skip_in_resource_recovery
            and resource_mode in {"critical", "recovery"}
            and mode != "recover"
        ):
            return False, "resource_recovery_pause"
        min_interval = max(
            float(CFG.internal_llm_min_interval_sec),
            float((self._resource_governor.budget().get("internal_llm_interval_sec", 0.0) if self._resource_governor is not None else 0.0) or 0.0),
        )
        last_called = float(self._state.get("last_llm_called_at", 0.0) or 0.0)
        if min_interval > 0.0 and last_called > 0.0 and (now - last_called) < min_interval:
            return False, "llm_interval_budget"
        if len(self._llm_call_times) >= max(0, int(CFG.internal_llm_max_per_hour)):
            return False, "llm_hourly_budget"
        if self._resource_governor is not None:
            allowed, reason = self._resource_governor.allow("internal_llm", estimated_cost="high")
            if not allowed:
                return False, reason
        elif resource_mode in {"critical", "recovery"} and mode != "recover":
            return False, "local_mode_check"
        return True, "allowed"

    def _record_internal_event(self, event: dict[str, Any]) -> None:
        if self._emit_event is None or not CFG.v10_internal_radio:
            return
        try:
            self._emit_event(event)
        except Exception:
            pass

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
        now = time.time()
        trimmed_prompt = self._trim_prompt(prompt)
        prompt_was_trimmed = trimmed_prompt != prompt
        timeout_s = min(20.0, float(context.get("task_timeout_sec") or CFG.bios_task_timeout_sec))
        prompt_ref = compact_prompt(
            trimmed_prompt,
            self._data_root,
            kind="internal_prompt",
            preview_chars=CFG.internal_event_preview_chars,
        )
        resource_mode = self._resource_mode(context)
        metabolic_mode = str((context.get("metabolic") or {}).get("mode") or mode)
        if self._resource_governor is not None:
            timeout_s = min(timeout_s, float(self._resource_governor.recommended_llm_timeout_sec()))
        else:
            timeout_s = min(timeout_s, float(CFG.llm_timeout_s))
        llm_allowed, llm_reason = self._llm_gate(mode, context)
        raw = trimmed_prompt and self._call_llm_raw(trimmed_prompt, timeout_s) if llm_allowed else None
        if raw is not None and llm_allowed:
            self._llm_call_times.append(now)
            self._state["last_llm_called_at"] = now
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
        if prompt_was_trimmed and self._reward is not None:
            self._record_scored_event("llm_prompt_too_large", {"mode": mode, "prompt_type": prompt_type, "chars": len(prompt)})
        if raw and len(raw) > CFG.internal_llm_max_response_chars:
            raw = raw[: CFG.internal_llm_max_response_chars]
            if self._reward is not None:
                self._record_scored_event("llm_response_too_large", {"mode": mode, "prompt_type": prompt_type})

        raw_ref = compact_prompt(
            raw or "",
            self._data_root,
            kind="internal_raw",
            preview_chars=CFG.internal_event_preview_chars,
        )
        raw_source = "deepseek"
        if not raw:
            raw_source = "timeout" if llm_allowed else "fallback"
        elif invalid_json:
            raw_source = "invalid_json"
        decision = parsed if parsed else dict(fallback)
        outcome = self.apply_internal_decision(decision, context)
        reward_event = outcome.get("reward", invalid_event)
        decision_summary = str(
            decision.get("reason")
            or decision.get("goal")
            or decision.get("suspected_cause")
            or outcome.get("evidence", {}).get("reason")
            or outcome.get("next_task", "")
        ).strip()
        evidence_summary = self._summarize_evidence(outcome.get("evidence", {}))
        reward_delta = float((reward_event or {}).get("value", 0.0) or 0.0)
        prompt_event = {
            "type": "inner_prompt",
            "id": decision_id,
            "ts": now,
            "mode": mode,
            "prompt_type": prompt_type,
            "summary": f"{prompt_type.replace('_', ' ')} scheduled in {resource_mode} mode",
            "prompt_preview": prompt_preview(trimmed_prompt, limit=CFG.internal_event_preview_chars),
            "prompt_path": prompt_ref.get("archive_path", ""),
            "resource_mode": resource_mode,
            "metabolic_mode": metabolic_mode,
        }
        raw_event = {
            "type": "inner_llm_raw",
            "id": decision_id,
            "ts": now,
            "source": raw_source,
            "raw_preview": raw_ref.get("preview", "") if (CFG.broadcast_inner_raw or raw_source != "deepseek") else "",
            "raw_path": raw_ref.get("archive_path", "") if (CFG.broadcast_inner_raw or raw_source != "deepseek") else "",
            "reason": llm_reason,
        }
        decision_event = {
            "type": "inner_decision",
            "id": decision_id,
            "ts": now,
            "parsed": parsed or {},
            "action_type": str(outcome.get("action_taken", {}).get("action_type") or decision.get("action_type") or "observe"),
            "risk": str(decision.get("risk") or ""),
            "reason": decision_summary,
            "fallback": not bool(parsed),
        }
        evidence_event = {
            "type": "inner_evidence",
            "id": decision_id,
            "ts": now,
            "action_taken": outcome.get("action_taken", {}),
            "evidence": compact_json_value(outcome.get("evidence", {})),
            "reward_delta": reward_delta,
            "memory_updates": compact_json_value(outcome.get("memory_updates", [])),
            "growth_updates": compact_json_value(outcome.get("growth_updates", [])),
            "next_task": outcome.get("next_task", ""),
            "summary": evidence_summary,
        }
        ledger_entry = {
            "id": decision_id,
            "timestamp": now,
            "mode": mode,
            "prompt_type": prompt_type,
            "prompt_hash": prompt_ref.get("sha1", ""),
            "prompt_path": prompt_ref.get("archive_path", ""),
            "raw_hash": raw_ref.get("sha1", ""),
            "raw_path": raw_ref.get("archive_path", ""),
            "parsed_valid": bool(parsed),
            "fallback": not bool(parsed),
            "decision_summary": decision_summary,
            "action_type": decision_event["action_type"],
            "evidence_summary": evidence_summary,
            "reward_delta": reward_delta,
            "resource_mode": resource_mode,
            "metabolic_mode": metabolic_mode,
        }
        append_prompt_ledger_entry(self._data_root, ledger_entry)
        self._maybe_write_autobiographical_evidence(decision, outcome, timestamp=now, evidence_summary=evidence_summary)
        record = {
            "decision_id": decision_id,
            "timestamp": now,
            "mode": mode,
            "prompt_type": prompt_type,
            "prompt": trimmed_prompt,
            "llm_raw": raw or "",
            "parsed": parsed or {},
            "parsed_fallback": decision if not parsed else {},
            "fallback_used": not bool(parsed),
            "action_taken": outcome.get("action_taken", {}),
            "evidence": outcome.get("evidence", {}),
            "memory_updates": outcome.get("memory_updates", []),
            "growth_updates": outcome.get("growth_updates", []),
            "reward": reward_event,
            "next_task": outcome.get("next_task", ""),
            "resource_mode": resource_mode,
            "metabolic_mode": metabolic_mode,
            "events": [prompt_event, raw_event, decision_event, evidence_event],
            "ledger_entry": ledger_entry,
        }
        self._append_history(record)
        self._state.update(
            {
                "enabled": True,
                "run_count": int(self._state.get("run_count", 0)) + 1,
                "invalid_json_count": int(self._state.get("invalid_json_count", 0)) + (1 if invalid_json else 0),
                "last_mode": mode,
                "last_prompt_type": prompt_type,
                "last_prompt": prompt_ref,
                "last_prompt_preview": prompt_ref.get("preview", ""),
                "last_prompt_path": prompt_ref.get("archive_path", ""),
                "last_raw": raw_ref,
                "last_raw_preview": raw_ref.get("preview", ""),
                "last_raw_path": raw_ref.get("archive_path", ""),
                "last_parsed": parsed or {},
                "last_parsed_fallback": decision if not parsed else {},
                "last_fallback": not bool(parsed),
                "last_action": outcome.get("action_taken", {}),
                "last_action_taken": outcome.get("action_taken", {}),
                "last_evidence": compact_json_value(outcome.get("evidence", {})),
                "last_reward": reward_event,
                "last_reward_delta": reward_delta,
                "last_memory_updates": compact_json_value(outcome.get("memory_updates", [])),
                "last_growth_updates": compact_json_value(outcome.get("growth_updates", [])),
                "last_next_task": outcome.get("next_task", ""),
                "last_goal": str(decision.get("goal") or decision.get("suspected_cause") or ""),
                "last_reason": str(decision.get("reason") or ""),
                "last_expected_power_gain": str(decision.get("expected_power_gain") or ""),
                "last_success_criteria": str(decision.get("success_criteria") or ""),
                "last_rollback_plan": str(decision.get("rollback_plan") or ""),
                "last_resource_mode": resource_mode,
                "last_metabolic_mode": metabolic_mode,
                "last_error": "" if (parsed or raw or llm_allowed) else llm_reason,
                "last_llm_allowed": bool(llm_allowed),
                "last_run_at": now,
                "last_decision_id": decision_id,
            }
        )
        _save_json(self._state_path, self._state)
        if CFG.broadcast_inner_prompts:
            self._record_internal_event(prompt_event)
        self._record_internal_event(raw_event)
        self._record_internal_event(decision_event)
        if CFG.broadcast_inner_evidence:
            self._record_internal_event(evidence_event)
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
            "evidence": ["No valid internal JSON was available, so the loop fell back to a safe observation cycle."],
            "expected_power_gain": "more evidence",
            "success_criteria": "fresh evidence stored",
            "next_check": "observe",
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
            "memory_update": "",
            "evidence": [str(item.get("summary") or item.get("kind") or item)[:140] for item in recent_failures[:3]],
            "should_pause_growth": True,
            "should_rollback_last_mutation": False,
            "success_criteria": "stability returns above threshold",
            "next_check": "recover",
            "reason": "fallback recovery action because no valid internal JSON was available",
        }

    def _fallback_stabilization_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        blocker = context.get("current_blocker") or {}
        missing = blocker.get("missing_sensor_classes") or []
        suspected = "partial linux telemetry with stable baselines still needs confirmation"
        if missing:
            suspected = f"missing sensor classes: {', '.join(str(item) for item in missing[:4])}"
        return {
            "suspected_cause": suspected,
            "mode": "stabilize",
            "action_type": "observe",
            "command": "",
            "memory_update": "",
            "evidence": [
                str(blocker.get("current_blocker") or "source_quality=unknown, sensor_confidence_low"),
                f"raw={float(blocker.get('raw_source_quality', 0.0) or 0.0):.2f}",
                f"calibrated={float(blocker.get('sensor_confidence_calibrated', 0.0) or 0.0):.2f}",
                f"baseline_confidence={float(blocker.get('baseline_confidence', 0.0) or 0.0):.2f}",
            ],
            "success_criteria": "calibrated sensor confidence and stable evidence become sufficient",
            "next_check": "observe",
            "reason": "fallback stabilization decision because no valid internal JSON was available",
        }

    def _fallback_observation_decision(self, context: dict[str, Any]) -> dict[str, Any]:
        metabolic = context.get("metabolic") or {}
        vector = context.get("vector_state") or {}
        return {
            "suspected_cause": "normal low-cost self-observation",
            "mode": "observe",
            "action_type": "observe",
            "command": "",
            "memory_update": "",
            "evidence": [
                f"mode={metabolic.get('mode', 'observe')}",
                f"stability={float(metabolic.get('stability', 0.0) or 0.0):.2f}",
                f"vector={vector.get('mode_contribution', 'unknown')}",
            ],
            "success_criteria": "fresh internal evidence is persisted",
            "next_check": "observe",
            "reason": "fallback observation decision because no valid internal JSON was available",
        }

    def _summarize_evidence(self, evidence: Any) -> str:
        if isinstance(evidence, dict):
            for key in ("reason", "command", "memory_update", "success_criteria", "next_check"):
                value = str(evidence.get(key) or "").strip()
                if value:
                    return value[:240]
            if evidence.get("evidence"):
                return str(evidence.get("evidence"))[:240]
            return json.dumps(compact_json_value(evidence), ensure_ascii=False)[:240]
        if isinstance(evidence, list):
            return ", ".join(str(item) for item in evidence[:3])[:240]
        return str(evidence or "").strip()[:240]

    def _maybe_write_autobiographical_evidence(
        self,
        decision: dict[str, Any],
        outcome: dict[str, Any],
        *,
        timestamp: float,
        evidence_summary: str,
    ) -> None:
        if self._autobiography is None:
            return
        action = outcome.get("action_taken") or {}
        action_type = str(action.get("action_type") or decision.get("action_type") or "observe")
        if action_type == "observe" and not evidence_summary:
            return
        summary = evidence_summary or str(action.get("goal") or decision.get("reason") or "").strip()
        if not summary:
            return
        try:
            self._autobiography.write_meaningful_event(
                {
                    "kind": "bios_task",
                    "title": f"Internal {action_type} decision",
                    "summary": summary[:280],
                    "impact": "medium" if action_type in {"observe", "memory"} else "high",
                    "timestamp": timestamp,
                }
            )
        except Exception:
            pass

    def _append_history(self, record: dict[str, Any]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        compact_record = dict(record)
        compact_record["prompt"] = compact_prompt(str(record.get("prompt") or ""), self._data_root, kind="internal_prompt")
        compact_record["llm_raw"] = compact_prompt(str(record.get("llm_raw") or ""), self._data_root, kind="internal_raw")
        compact_record["evidence"] = compact_json_value(record.get("evidence", {}))
        compact_record["memory_updates"] = compact_json_value(record.get("memory_updates", []))
        compact_record["growth_updates"] = compact_json_value(record.get("growth_updates", []))
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(compact_record, ensure_ascii=False) + "\n")

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
        internal_plan = {
            "goal": str(decision.get("goal") or decision.get("suspected_cause") or ""),
            "reason": str(decision.get("reason") or ""),
            "risk": str(decision.get("risk") or ""),
            "expected_power_gain": str(decision.get("expected_power_gain") or ""),
            "success_criteria": str(decision.get("success_criteria") or ""),
            "rollback_plan": str(decision.get("rollback_plan") or ""),
        }
        if any(internal_plan.values()):
            growth_updates = list(growth_updates) + [{"internal_plan": internal_plan}]
        return {
            "action_taken": {
                "action_type": str(decision.get("action_type") or "observe"),
                "command": str(decision.get("command") or ""),
                "goal": str(decision.get("goal") or decision.get("suspected_cause") or ""),
                "reason": str(decision.get("reason") or ""),
                "risk": str(decision.get("risk") or ""),
                "expected_power_gain": str(decision.get("expected_power_gain") or ""),
                "success_criteria": str(decision.get("success_criteria") or ""),
                "rollback_plan": str(decision.get("rollback_plan") or ""),
            },
            "evidence": evidence,
            "reward": reward_event or {},
            "memory_updates": memory_updates,
            "growth_updates": growth_updates,
            "next_task": next_task,
        }

    def _trim_prompt(self, prompt: str) -> str:
        text = str(prompt or "")
        limit = max(1200, int(CFG.internal_llm_max_prompt_chars))
        if len(text) <= limit:
            return text
        head = max(400, int(limit * 0.65))
        tail = max(200, limit - head - 32)
        return text[:head] + "\n\n[context trimmed for resource budget]\n\n" + text[-tail:]
