from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable

from soma_core.internal_prompts import growth_diagnosis_prompt
from soma_core.config import CFG


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


class BiosLoop:
    def __init__(
        self,
        *,
        enabled: bool = True,
        interval_sec: float = 300.0,
        idle_only: bool = False,
        use_llm: bool = True,
        max_tasks_per_hour: int = 12,
        max_llm_calls_per_hour: int = 12,
        task_timeout_sec: float = 60.0,
        write_memory: bool = True,
        mutation_proposal_interval_sec: float = 1800.0,
        executor: Any = None,
        trace: Any = None,
        journal: Any = None,
        autobiography: Any = None,
        experience: Any = None,
        baseline_store: Any = None,
        growth_engine: Any = None,
        life_drive: Any = None,
        mutation: Any = None,
        cpp_bridge: Any = None,
        metabolic_engine: Any = None,
        internal_loop: Any = None,
        reward_engine: Any = None,
        vector_interpreter: Any = None,
        power_policy: Any = None,
        call_llm_raw: Callable[[str, float], str | None] | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.enabled = enabled
        self.interval_sec = float(interval_sec)
        self.idle_only = idle_only
        self.use_llm = use_llm
        self.max_tasks_per_hour = int(max_tasks_per_hour)
        self.max_llm_calls_per_hour = int(max_llm_calls_per_hour)
        self.task_timeout_sec = float(task_timeout_sec)
        self.write_memory = write_memory
        self.mutation_proposal_interval_sec = float(mutation_proposal_interval_sec)
        self._executor = executor
        self._trace = trace
        self._journal = journal
        self._autobiography = autobiography
        self._experience = experience
        self._baseline_store = baseline_store
        self._growth_engine = growth_engine
        self._life_drive = life_drive
        self._mutation = mutation
        self._cpp_bridge = cpp_bridge
        self._metabolic_engine = metabolic_engine
        self._internal_loop = internal_loop
        self._reward_engine = reward_engine
        self._vector_interpreter = vector_interpreter
        self._power_policy = power_policy
        self._call_llm_raw = call_llm_raw
        self._data_root = data_root or (_REPO_ROOT / "data" / "mind")
        self._history_path = self._data_root / "bios_history.jsonl"
        self._state_path = self._data_root / "bios_state.json"
        self._state = _load_json(self._state_path, {
            "enabled": enabled,
            "running": False,
            "last_run_at": 0.0,
            "last_task": "",
            "last_result": "",
            "tasks_today": 0,
            "run_count": 0,
            "useful_cycles": 0,
            "llm_calls_today": 0,
            "metabolic_mode": "observe",
            "last_internal_decision": {},
            "last_internal_prompt": "",
            "last_evidence": {},
        })
        self._run_times: list[float] = []
        self._llm_times: list[float] = []

    def maybe_run(self, snapshot: dict, *, last_user_interaction_at: float) -> dict | None:
        if not self.enabled:
            return None
        now = time.time()
        if self.idle_only and (now - last_user_interaction_at) < self.interval_sec:
            return None
        if now - float(self._state.get("last_run_at", 0.0)) < self.interval_sec:
            return None
        self._prune(now)
        if len(self._run_times) >= self.max_tasks_per_hour:
            return None
        return self.run_once(snapshot, reason="scheduled")

    def run_once(self, snapshot: dict, reason: str = "scheduled") -> dict:
        now = time.time()
        self._prune(now)
        self._state["running"] = True
        growth = (snapshot.get("_growth") or {}) if isinstance(snapshot, dict) else {}
        context = self._build_context(snapshot, growth)
        if self._metabolic_engine is not None:
            metabolic = self._metabolic_engine.current()
            if not metabolic or not metabolic.get("timestamp"):
                metabolic = self._metabolic_engine.update(snapshot, context)
        else:
            metabolic = snapshot.get("metabolic", {}) if isinstance(snapshot, dict) else {}
        context["metabolic"] = metabolic
        context["growth"] = growth
        mode = str((metabolic or {}).get("mode") or "observe")
        self._state["metabolic_mode"] = mode
        internal_record: dict[str, Any] | None = None
        if self._internal_loop is not None and mode in {"grow", "mutate", "evaluate", "reproduce"}:
            internal_record = self._internal_loop.run_growth_cycle(context)
        elif self._internal_loop is not None and mode == "recover":
            internal_record = self._internal_loop.run_recovery_cycle(context)

        if internal_record is not None:
            task = {
                "task": str(internal_record.get("next_task") or internal_record.get("action_taken", {}).get("action_type") or mode),
                "reason": f"metabolic:{mode}",
                "requires_shell": False,
            }
            evidence = internal_record.get("evidence") or {}
            reward = internal_record.get("reward") or {}
            action = internal_record.get("action_taken") or {}
            result = {
                "ok": bool(evidence.get("ok", True)),
                "summary": f"{action.get('action_type', 'observe')}: {str(action.get('goal') or evidence.get('reason') or evidence.get('command') or 'no summary')[:220]}",
                "meaningful": bool(evidence) or bool(reward),
                "evidence": evidence,
                "reward": reward,
                "internal_record": internal_record,
            }
            self._state["last_internal_decision"] = internal_record.get("parsed") or action
            self._state["last_internal_prompt"] = str(internal_record.get("prompt") or "")
            self._state["last_evidence"] = evidence
        else:
            task = self._select_task(context)
            self._state["last_internal_decision"] = {}
            self._state["last_internal_prompt"] = ""
            result = self._execute_task(task, snapshot, context)
            self._state["last_evidence"] = result.get("data") or result.get("evidence") or {}
        self._emit("bios_task_started", f"BIOS task started: {task['task']}", outputs={"reason": task.get("reason", "")})
        useful = bool(result.get("meaningful") or result.get("ok") or result.get("lessons"))
        if useful:
            self._state["useful_cycles"] = int(self._state.get("useful_cycles", 0)) + 1
        self._state.update({
            "running": False,
            "last_run_at": now,
            "last_task": task["task"],
            "last_result": result.get("summary", result.get("status", "")),
            "tasks_today": int(self._state.get("tasks_today", 0)) + 1,
            "run_count": int(self._state.get("run_count", 0)) + 1,
            "last_mode": mode,
        })
        self._run_times.append(now)
        self._append_history({"timestamp": now, "reason": reason, "task": task, "result": result})
        _save_json(self._state_path, self._state)
        self._emit(
            "bios_task_completed" if result.get("ok", True) else "bios_task_failed",
            f"BIOS task {task['task']}: {result.get('summary', result.get('status', 'done'))}",
            outputs={"task": task["task"], "ok": result.get("ok", True)},
        )
        return {"task": task, "result": result}

    def status(self) -> dict:
        state = dict(self._state)
        state["next_run_in_sec"] = max(0.0, self.interval_sec - (time.time() - float(self._state.get("last_run_at", 0.0))))
        return state

    def _build_context(self, snapshot: dict, growth: dict) -> dict[str, Any]:
        autobio_quality = self._autobiography.get_quality_summary() if self._autobiography is not None else {}
        mutation_status = self._mutation.status() if self._mutation is not None else {}
        cpp_status = self._cpp_bridge.status() if self._cpp_bridge is not None else {}
        baseline_summary = self._baseline_store.summary() if self._baseline_store is not None else {}
        life_drive = self._life_drive.evaluate(snapshot, growth, {"autobiography": autobio_quality}) if self._life_drive is not None else {}
        reward = self._reward_engine.summary() if self._reward_engine is not None else {}
        vector_state = snapshot.get("vector_state") or {}
        internal_status = self._internal_loop.status() if self._internal_loop is not None else {}
        return {
            "growth_stage": growth.get("stage"),
            "missing_requirements": growth.get("missing_requirements", []),
            "latest_lessons": self._experience.get_lessons(limit=5) if self._experience is not None else [],
            "body_baselines": baseline_summary,
            "recent_failures": self._recent_failures(),
            "pending_self_improvement": [],
            "runtime_storage_status": self._runtime_storage_status(),
            "command_reliability": {},
            "cpp_bridge": cpp_status,
            "mutation": mutation_status,
            "life_drive": life_drive,
            "autobiography": autobio_quality,
            "reward": reward,
            "vector_state": vector_state,
            "internal_loop": internal_status,
            "recent_events": self._recent_failures(),
            "capabilities": {
                "survival_policy": self._executor is not None,
                "cpp_bridge": bool(cpp_status),
            },
            "identity": {"name": "Soma", "kind": "embodied local software organism"},
            "cpp_bridge_obj": self._cpp_bridge,
        }

    def _select_task(self, context: dict[str, Any]) -> dict[str, Any]:
        missing = context.get("missing_requirements", [])
        metabolic = context.get("metabolic", {}) or {}
        mode = str(metabolic.get("mode") or "observe")
        if mode == "stabilize":
            return {"task": "inspect_recent_failures", "reason": "metabolic mode requests stabilization", "requires_shell": False}
        if mode == "observe":
            return {"task": "check_runtime_storage", "reason": "observe mode gathers cheap evidence", "requires_shell": False}

        baseline_keys = (context.get("body_baselines", {}) or {}).get("keys", {})
        baseline_ready = bool(baseline_keys.get("idle_cpu_percent", {}).get("confidence", 0.0) >= CFG.growth_stability_threshold)
        if self.use_llm and self._call_llm_raw is not None and len(self._llm_times) < self.max_llm_calls_per_hour:
            prompt = growth_diagnosis_prompt(context)
            raw = self._call_llm_raw(prompt, min(self.task_timeout_sec, 20.0))
            self._llm_times.append(time.time())
            self._state["llm_calls_today"] = int(self._state.get("llm_calls_today", 0)) + 1
            task = self._parse_llm_task(raw)
            if task is not None:
                return task
        if any("baseline" in item for item in missing) and not baseline_ready:
            return {"task": "update_body_baseline", "reason": "growth blocker: baseline missing", "requires_shell": False}
        if any("command" in item or "execution" in item for item in missing):
            return {"task": "verify_environment_fact", "reason": "growth blocker: command agency", "requires_shell": True, "command": "uname -r"}
        if any("lesson" in item or "operator" in item for item in missing):
            return {"task": "summarize_recent_experience", "reason": "growth blocker: lessons missing", "requires_shell": False}
        if any("bios" in item for item in missing):
            return {"task": "check_growth_requirements", "reason": "growth blocker: BIOS evidence", "requires_shell": False}
        if any("mutation" in item for item in missing):
            return {"task": "prepare_mutation_candidate", "reason": "growth blocker: mutation sandbox", "requires_shell": False}
        if any("cpp" in item for item in missing):
            return {"task": "check_cpp_bridge", "reason": "growth blocker: cpp bridge", "requires_shell": False}
        return {"task": "run_light_validation", "reason": "routine maintenance", "requires_shell": True, "command": "python3 scripts/test_command_planner.py"}

    def _execute_task(self, task: dict[str, Any], snapshot: dict, context: dict[str, Any]) -> dict[str, Any]:
        name = task["task"]
        if name == "update_body_baseline":
            if self._baseline_store is None:
                return {"ok": False, "summary": "baseline store unavailable"}
            update = self._baseline_store.update_from_snapshot(snapshot)
            return {"ok": True, "summary": f"updated baselines: {', '.join(update['updated_keys']) or 'none'}", "meaningful": bool(update["updated_keys"]), "data": update}
        if name == "check_growth_requirements":
            return {"ok": True, "summary": f"missing requirements: {len(context.get('missing_requirements', []))}", "meaningful": True}
        if name == "summarize_recent_experience":
            lessons = self._experience.get_lessons(limit=3) if self._experience is not None else []
            return {"ok": True, "summary": f"recent lessons: {len(lessons)}", "meaningful": bool(lessons), "lessons": lessons}
        if name == "inspect_recent_failures":
            failures = self._recent_failures()
            return {"ok": True, "summary": f"recent failures: {len(failures)}", "meaningful": bool(failures), "data": failures}
        if name == "check_runtime_storage":
            return {"ok": True, "summary": self._runtime_storage_status(), "meaningful": True}
        if name == "observe_vector_state":
            vector_state = context.get("vector_state", {})
            return {"ok": True, "summary": f"vector={vector_state.get('mode_contribution', 'unknown')} drift={vector_state.get('vector_drift', 0.0)}", "meaningful": bool(vector_state), "data": vector_state}
        if name == "observe_reward_trend":
            reward = context.get("reward", {})
            return {"ok": True, "summary": f"reward trend={reward.get('trend', 0.0)} rolling={reward.get('rolling_score', 0.0)}", "meaningful": bool(reward), "data": reward}
        if name == "propose_micro_improvement":
            return {"ok": True, "summary": "queued micro improvement proposal", "meaningful": True}
        if name == "run_light_validation":
            return self._shell_task(task.get("command") or "python3 scripts/test_command_planner.py")
        if name == "verify_environment_fact":
            return self._shell_task(task.get("command") or "uname -r")
        if name == "write_autobiographical_lesson":
            if self._autobiography is None:
                return {"ok": False, "summary": "autobiography unavailable"}
            lessons = self._experience.get_lessons(limit=1) if self._experience is not None else []
            if not lessons:
                return {"ok": False, "summary": "no lessons to write"}
            event = self._autobiography.write_meaningful_event({
                "kind": "bios_task",
                "title": "BIOS distilled a lesson",
                "summary": str(lessons[-1].get("behavioral_update") or lessons[-1].get("observation") or "")[:300],
                "impact": "medium",
            })
            return {"ok": True, "summary": "wrote autobiographical lesson", "meaningful": bool(event.get("stored", True))}
        if name == "prepare_mutation_candidate":
            if self._mutation is None:
                return {"ok": False, "summary": "mutation sandbox unavailable"}
            sandbox = self._mutation.create_child_if_allowed(
                task.get("reason", "bios"),
                context.get("metabolic", {}) or {},
                growth=context.get("growth", {}) or {},
                reward=context.get("reward", {}) or {},
            )
            return {
                "ok": bool(sandbox.get("ok")),
                "summary": sandbox.get("summary", f"sandbox created at {sandbox.get('sandbox_path', '')}"),
                "meaningful": bool(sandbox.get("ok")),
                "data": sandbox,
            }
        if name == "check_cpp_bridge":
            if self._cpp_bridge is None:
                return {"ok": False, "summary": "cpp bridge unavailable"}
            status = self._cpp_bridge.smoke_test()
            return {"ok": bool(status.get("smoke_ok")), "summary": status.get("status", "unknown"), "meaningful": True, "data": status}
        return {"ok": False, "summary": f"unknown BIOS task: {name}"}

    def _shell_task(self, command: str) -> dict[str, Any]:
        if self._executor is None:
            return {"ok": False, "summary": "executor unavailable"}
        ok, stdout, stderr = self._executor.run_raw(command)
        return {
            "ok": ok,
            "summary": (stdout or stderr or command)[:300],
            "meaningful": ok,
            "command": command,
            "stdout": stdout[:500],
            "stderr": stderr[:300],
        }

    def _append_history(self, record: dict[str, Any]) -> None:
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _recent_failures(self) -> list[dict[str, Any]]:
        if self._journal is None:
            return []
        events = self._journal.recent_events(limit=100)
        return [event for event in events if event.get("importance", 0.0) >= 0.7 or "fail" in str(event.get("kind", "")).lower()][-10:]

    def _runtime_storage_status(self) -> str:
        targets = [
            _REPO_ROOT / "data" / "mind",
            _REPO_ROOT / "data" / "runtime",
            _REPO_ROOT / "data" / "journal",
            _REPO_ROOT / "logs",
        ]
        parts = []
        for path in targets:
            if path.exists():
                size = sum(item.stat().st_size for item in path.rglob("*") if item.is_file())
                parts.append(f"{path.name}={round(size / 1024, 1)}KB")
        return ", ".join(parts) if parts else "no runtime storage"

    def _emit(self, phase: str, summary: str, *, outputs: dict[str, Any] | None = None) -> None:
        if self._trace is not None:
            try:
                self._trace.emit(phase, summary, outputs=outputs or {}, level="info")
            except Exception:
                pass

    def _prune(self, now: float) -> None:
        hour_ago = now - 3600.0
        self._run_times = [item for item in self._run_times if item > hour_ago]
        self._llm_times = [item for item in self._llm_times if item > hour_ago]

    def _parse_llm_task(self, raw: str | None) -> dict[str, Any] | None:
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict) or "task" not in payload:
            return None
        return payload
