from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from soma_core.state_compaction import load_jsonl_tail


_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default

class IntrospectionRouter:
    def __init__(self, *, repo_root: Path | None = None) -> None:
        self._repo_root = Path(repo_root or _REPO_ROOT)
        self._mind_root = self._repo_root / "data" / "mind"
        self._prompt_index_path = self._mind_root / "internal_prompt_index.jsonl"

    def execute(self, user_text: str, snapshot: dict[str, Any] | None = None, growth: dict[str, Any] | None = None) -> dict[str, Any] | None:
        low = (user_text or "").lower().strip()
        if not low:
            return None
        if "last bios internal prompt" in low or "last internal prompt" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            prompt = bios.get("last_internal_prompt") or state.get("last_prompt") or {}
            preview = self._prompt_preview_from_state(prompt, state=state, bios=bios)
            if not preview:
                return self._ok(
                    "introspection.last_bios_prompt",
                    "No internal BIOS prompt has been persisted yet. Next verification step: wait for the BIOS/internal loop to run again.",
                    {"prompt": {}},
                    deterministic=True,
                )
            return self._ok("introspection.last_bios_prompt", preview, {"prompt": prompt, "state": state, "bios": bios}, deterministic=True)
        if "last internal deepseek json" in low or "last deepseek json" in low or "last internal json" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            bios = _load_json(self._mind_root / "bios_state.json", {})
            parsed = state.get("last_parsed") or bios.get("last_parsed") or {}
            fallback = state.get("last_parsed_fallback") or bios.get("last_parsed_fallback") or {}
            if parsed:
                return self._ok("introspection.last_internal_json", self._json_text(parsed), {"parsed": parsed, "fallback": fallback}, deterministic=True, format="json")
            if fallback:
                return self._ok("introspection.last_internal_json", self._json_text(fallback), {"parsed": parsed, "fallback": fallback}, deterministic=True, format="json")
            return self._ok(
                "introspection.last_internal_json",
                "No internal DeepSeek JSON has been persisted yet. Next verification step: wait for the internal loop to complete another cycle.",
                {"parsed": {}, "fallback": {}},
                deterministic=True,
            )
        if "last raw internal llm answer" in low or "last internal raw" in low or "last raw deepseek" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            bios = _load_json(self._mind_root / "bios_state.json", {})
            raw = state.get("last_raw") or bios.get("last_raw") or {}
            text = self._raw_preview_from_state(raw, state=state, bios=bios)
            if not text:
                return self._ok(
                    "introspection.last_internal_raw",
                    "No raw internal LLM answer has been persisted yet. Next verification step: wait for an internal LLM cycle or inspect fallback decisions.",
                    {"raw": {}},
                    deterministic=True,
                )
            return self._ok("introspection.last_internal_raw", text, {"raw": raw, "state": state, "bios": bios}, deterministic=True)
        if ("what evidence did" in low and "bios" in low) or "last bios evidence" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            evidence = bios.get("last_evidence") or {}
            if evidence:
                return self._ok("introspection.last_bios_evidence", self._json_text(evidence), {"evidence": evidence}, deterministic=True, format="json")
            return self._ok("introspection.last_bios_evidence", "No BIOS evidence has been recorded yet.", {"evidence": {}}, deterministic=True)
        if "what task did your bios run last" in low or "last bios task" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            task = str(bios.get("last_task") or "").strip()
            result = str(bios.get("last_result") or "").strip()
            if not task:
                return self._ok("introspection.last_bios_task", "No BIOS task has been recorded yet.", {}, deterministic=True)
            return self._ok("introspection.last_bios_task", f"Last BIOS task: {task}. Result: {result or 'n/a'}.", bios, deterministic=True)
        if "what memory did it update" in low or "last memory update" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            memory_updates = state.get("last_memory_updates") or []
            if not memory_updates:
                return self._ok("introspection.memory_updates", "No internal memory update has been recorded yet.", {"memory_updates": []}, deterministic=True)
            return self._ok(
                "introspection.memory_updates",
                self._json_text(memory_updates),
                {"memory_updates": memory_updates},
                deterministic=True,
                format="json",
            )
        if "what did your last internal decision change" in low or "last internal decision change" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            data = {
                "action_taken": state.get("last_action_taken") or state.get("last_action") or {},
                "evidence": state.get("last_evidence") or {},
                "reward_delta": state.get("last_reward_delta"),
                "memory_updates": state.get("last_memory_updates") or [],
                "growth_updates": state.get("last_growth_updates") or [],
                "next_task": state.get("last_next_task") or "",
            }
            return self._ok("introspection.last_internal_change", self._json_text(data), data, deterministic=True, format="json")
        if "what is your next internal task" in low or "next internal task" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            next_task = str(state.get("last_next_task") or "").strip()
            if not next_task:
                return self._ok("introspection.next_internal_task", "No next internal task has been recorded yet.", {"next_task": ""}, deterministic=True)
            return self._ok("introspection.next_internal_task", f"Next internal task: {next_task}.", {"next_task": next_task}, deterministic=True)
        if "why did you choose that internal task" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            reason = str(state.get("last_reason") or "").strip()
            goal = str(state.get("last_goal") or "").strip()
            next_task = str(state.get("last_next_task") or "").strip()
            if not any((reason, goal, next_task)):
                return self._ok("introspection.internal_task_reason", "No internal task rationale has been recorded yet.", {}, deterministic=True)
            parts = []
            if next_task:
                parts.append(f"task={next_task}")
            if goal:
                parts.append(f"goal={goal}")
            if reason:
                parts.append(f"reason={reason}")
            return self._ok("introspection.internal_task_reason", ". ".join(parts) + ".", {"next_task": next_task, "goal": goal, "reason": reason}, deterministic=True)
        if "what growth blocker" in low or "growth blocker" in low:
            current_growth = growth or (snapshot or {}).get("_growth") or {}
            blockers = current_growth.get("blocked_by") or current_growth.get("missing_requirements") or []
            if not blockers:
                return self._ok("introspection.growth_blockers", "No active growth blocker is recorded right now.", {"blockers": []}, deterministic=True)
            return self._ok("introspection.growth_blockers", f"Current growth blockers: {', '.join(str(item) for item in blockers[:6])}.", {"blockers": blockers}, deterministic=True)
        if "mutation proposals" in low or "mutation reports" in low:
            reports = load_jsonl_tail(self._mind_root / "mutations" / "reports.jsonl", limit=5)
            if not reports:
                return self._ok("introspection.mutation_reports", "No mutation proposals or reports exist yet.", {"reports": []}, deterministic=True)
            short = [
                {
                    "mutation_id": item.get("mutation_id"),
                    "decision": item.get("decision"),
                    "power_gain": item.get("power_gain"),
                    "risk": item.get("risk"),
                }
                for item in reports
            ]
            return self._ok("introspection.mutation_reports", self._json_text(short), {"reports": short}, deterministic=True, format="json")
        if "why are you not mutating" in low or "why not mutating" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            mutation = _load_json(self._mind_root / "mutation_state.json", {})
            blockers = []
            if metabolic.get("recovery_required") or not metabolic.get("growth_allowed", False):
                blockers.extend(
                    [
                        str(item)
                        for item in (metabolic.get("reasons") or [])
                        if str(item) not in {"growth_allowed", "stable_metabolism"}
                    ]
                )
            blockers.extend(list(mutation.get("last_blockers") or []))
            if float(metabolic.get("sensor_confidence_calibrated", 0.0) or 0.0) < 0.55 and "low_calibrated_sensor_confidence" not in blockers:
                blockers.append("low_calibrated_sensor_confidence")
            if not blockers:
                blockers = ["no_recorded_mutation_blocker"]
            return self._ok("introspection.mutation_blockers", f"Mutation blockers: {', '.join(blockers[:8])}.", {"blockers": blockers}, deterministic=True)
        if "why are you in recovery" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            reasons = list(metabolic.get("reasons") or [])
            data = {
                "mode": metabolic.get("mode"),
                "resource_mode": metabolic.get("resource_mode"),
                "recovery_required": metabolic.get("recovery_required"),
                "reasons": reasons,
            }
            if not metabolic:
                return self._ok("introspection.recovery_reason", "No metabolic state has been persisted yet.", data, deterministic=True)
            return self._ok("introspection.recovery_reason", self._json_text(data), data, deterministic=True, format="json")
        if "are you thinking internally right now" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            data = {
                "bios_running": bool(bios.get("running")),
                "last_internal_prompt_type": state.get("last_prompt_type"),
                "last_run_at": state.get("last_run_at"),
                "last_decision_id": state.get("last_decision_id"),
            }
            return self._ok("introspection.internal_running", self._json_text(data), data, deterministic=True, format="json")
        if "read your last 3 internal decisions" in low or "last 3 internal decisions" in low:
            entries = load_jsonl_tail(self._prompt_index_path, limit=3)
            if not entries:
                return self._ok("introspection.last_internal_decisions", "No internal decisions have been persisted yet.", {"entries": []}, deterministic=True)
            return self._ok("introspection.last_internal_decisions", self._json_text(entries), {"entries": entries}, deterministic=True, format="json")
        if "why are you slowing down" in low or "resource mode" in low or "show resource governor status" in low:
            resource = _load_json(self._mind_root / "resource_state.json", {})
            if not resource:
                return self._ok("introspection.resource_mode", "No resource governor state has been persisted yet.", {}, deterministic=True)
            return self._ok("introspection.resource_mode", self._json_text(resource), resource, deterministic=True, format="json")
        if "what are you throttling" in low:
            resource = _load_json(self._mind_root / "resource_state.json", {})
            throttled = list(resource.get("throttled_operations") or [])
            mode = str(resource.get("mode") or "unknown")
            text = f"Resource mode {mode}. Throttling: {', '.join(throttled) if throttled else 'nothing right now'}."
            return self._ok("introspection.resource_throttling", text, {"mode": mode, "throttled_operations": throttled}, deterministic=True)
        if "what is your cpu budget" in low:
            resource = _load_json(self._mind_root / "resource_state.json", {})
            sample = resource.get("sample") or {}
            budget = resource.get("budget") or {}
            data = {
                "mode": resource.get("mode"),
                "cpu_percent": sample.get("cpu_percent"),
                "memory_percent": sample.get("memory_percent"),
                "tick_hz_max": budget.get("tick_hz_max"),
                "ui_hz_max": budget.get("ui_hz_max"),
            }
            text = self._json_text(data) if resource else "No resource budget has been persisted yet."
            return self._ok("introspection.cpu_budget", text, data, deterministic=True, format="json" if resource else "text")
        if "how much load are you causing" in low:
            resource = _load_json(self._mind_root / "resource_state.json", {})
            sample = resource.get("sample") or {}
            data = {
                "cpu_percent": sample.get("cpu_percent"),
                "memory_percent": sample.get("memory_percent"),
                "event_loop_lag_ms": sample.get("event_loop_lag_ms"),
                "average_tick_duration_ms": sample.get("average_tick_duration_ms"),
                "ui_broadcast_bytes_per_sec": sample.get("ui_broadcast_bytes_per_sec"),
                "file_write_bytes_per_min": sample.get("file_write_bytes_per_min"),
            }
            text = self._json_text(data) if resource else "No resource load sample has been persisted yet."
            return self._ok("introspection.resource_load", text, data, deterministic=True, format="json" if resource else "text")
        if "why did you pause growth" in low or "why did you pause or allow growth" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            if not metabolic:
                return self._ok("introspection.growth_pause", "No metabolic state has been persisted yet.", {}, deterministic=True)
            data = {
                "growth_allowed": metabolic.get("growth_allowed"),
                "resource_mode": metabolic.get("resource_mode"),
                "growth_suspended_by_resource": metabolic.get("growth_suspended_by_resource"),
                "reasons": metabolic.get("reasons", []),
            }
            text = self._json_text(data)
            return self._ok("introspection.growth_pause", text, data, deterministic=True, format="json")
        if "why did you pause mutation" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            mutation = _load_json(self._mind_root / "mutation_state.json", {})
            data = {
                "mutation_suspended_by_resource": metabolic.get("mutation_suspended_by_resource"),
                "resource_mode": metabolic.get("resource_mode"),
                "last_blockers": mutation.get("last_blockers", []),
            }
            text = self._json_text(data)
            return self._ok("introspection.mutation_pause", text, data, deterministic=True, format="json")
        if "show performance profile" in low:
            perf = _load_json(self._mind_root / "performance_state.json", {})
            if not perf:
                return self._ok("introspection.performance", "No performance profile has been persisted yet.", {}, deterministic=True)
            return self._ok("introspection.performance", self._json_text(perf), perf, deterministic=True, format="json")
        if "recovery or growth mode" in low or "metabolic mode" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            mode = metabolic.get("mode")
            reasons = metabolic.get("reasons") or []
            if not mode:
                return self._ok("introspection.metabolic_mode", "No metabolic state has been persisted yet.", {}, deterministic=True)
            return self._ok("introspection.metabolic_mode", f"Metabolic mode: {mode}. Reasons: {', '.join(reasons[:6]) or 'none'}.", metabolic, deterministic=True)
        if "metabolic vector" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            if not metabolic:
                return self._ok("introspection.metabolic_vector", "No metabolic vector has been persisted yet.", {}, deterministic=True)
            compact = {
                "mode": metabolic.get("mode"),
                "stability": metabolic.get("stability"),
                "stress": metabolic.get("stress"),
                "self_integrity": metabolic.get("self_integrity"),
                "growth_allowed": metabolic.get("growth_allowed"),
                "recovery_required": metabolic.get("recovery_required"),
                "reasons": metabolic.get("reasons", []),
                "raw_source_quality": metabolic.get("raw_source_quality"),
                "sensor_confidence_calibrated": metabolic.get("sensor_confidence_calibrated"),
                "baseline_confidence": metabolic.get("baseline_confidence"),
                "missing_sensor_classes": metabolic.get("missing_sensor_classes", []),
            }
            return self._ok("introspection.metabolic_vector", self._json_text(compact), compact, deterministic=True, format="json")
        if "reward trend" in low or "reward state" in low:
            reward = _load_json(self._mind_root / "reward_state.json", {})
            if not reward:
                return self._ok("introspection.reward", "No reward state has been persisted yet.", {}, deterministic=True)
            compact = {
                "rolling_score": reward.get("rolling_score"),
                "trend": reward.get("trend"),
                "last_kind": reward.get("last_kind"),
                "last_value": reward.get("last_value"),
                "count": reward.get("count"),
            }
            return self._ok("introspection.reward", self._json_text(compact), compact, deterministic=True, format="json")
        return None

    def _ok(
        self,
        skill_id: str,
        text: str,
        data: dict[str, Any],
        *,
        deterministic: bool = False,
        format: str = "text",
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "skill_id": skill_id,
            "text": text,
            "data": data,
            "source": "builtin",
            "deterministic": deterministic,
            "format": format,
        }

    def _render_prompt_ref(self, prompt: Any) -> str:
        if isinstance(prompt, dict):
            return json.dumps(prompt, ensure_ascii=False, indent=2)
        return str(prompt or "").strip()

    def _json_text(self, payload: Any) -> str:
        return json.dumps(payload, ensure_ascii=False, indent=2)

    def _prompt_preview_from_state(self, prompt: Any, *, state: dict[str, Any], bios: dict[str, Any]) -> str:
        if isinstance(prompt, dict):
            preview = str(
                prompt.get("preview")
                or bios.get("last_internal_prompt_preview")
                or state.get("last_prompt_preview")
                or ""
            ).strip()
            path = str(
                prompt.get("archive_path")
                or bios.get("last_internal_prompt_path")
                or state.get("last_prompt_path")
                or ""
            ).strip()
        else:
            preview = str(prompt or "").strip()
            path = ""
        if not preview and not path:
            return ""
        lines = [f"preview: {preview or '--'}"]
        if path:
            lines.append(f"path: {path}")
        return "\n".join(lines)

    def _raw_preview_from_state(self, raw: Any, *, state: dict[str, Any], bios: dict[str, Any]) -> str:
        if isinstance(raw, dict):
            preview = str(raw.get("preview") or bios.get("last_raw_preview") or state.get("last_raw_preview") or "").strip()
            path = str(raw.get("archive_path") or bios.get("last_raw_path") or state.get("last_raw_path") or "").strip()
        else:
            preview = str(raw or "").strip()
            path = ""
        if not preview and not path:
            return ""
        lines = [f"preview: {preview or '--'}"]
        if path:
            lines.append(f"path: {path}")
        return "\n".join(lines)
