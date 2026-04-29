from __future__ import annotations

import json
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _load_jsonl_tail(path: Path, limit: int = 20) -> list[dict[str, Any]]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return []
    items: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return items


class IntrospectionRouter:
    def __init__(self, *, repo_root: Path | None = None) -> None:
        self._repo_root = Path(repo_root or _REPO_ROOT)
        self._mind_root = self._repo_root / "data" / "mind"

    def execute(self, user_text: str, snapshot: dict[str, Any] | None = None, growth: dict[str, Any] | None = None) -> dict[str, Any] | None:
        low = (user_text or "").lower().strip()
        if not low:
            return None
        if "last bios internal prompt" in low or "last internal prompt" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            prompt = bios.get("last_internal_prompt") or state.get("last_prompt") or {}
            return self._ok("introspection.last_bios_prompt", self._render_prompt_ref(prompt) or "No internal BIOS prompt has been persisted yet.", {"prompt": prompt})
        if "last internal deepseek json" in low or "last deepseek json" in low or "last internal json" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            bios = _load_json(self._mind_root / "bios_state.json", {})
            parsed = state.get("last_parsed") or bios.get("last_parsed") or {}
            fallback = state.get("last_parsed_fallback") or bios.get("last_parsed_fallback") or {}
            text = json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else "No internal DeepSeek JSON has been persisted yet."
            if not parsed and fallback:
                text = json.dumps(fallback, ensure_ascii=False, indent=2)
            return self._ok("introspection.last_internal_json", text, {"parsed": parsed, "fallback": fallback})
        if ("what evidence did" in low and "bios" in low) or "last bios evidence" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            evidence = bios.get("last_evidence") or {}
            text = json.dumps(evidence, ensure_ascii=False, indent=2) if evidence else "No BIOS evidence has been recorded yet."
            return self._ok("introspection.last_bios_evidence", text, {"evidence": evidence})
        if "what task did your bios run last" in low or "last bios task" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            task = str(bios.get("last_task") or "").strip()
            result = str(bios.get("last_result") or "").strip()
            if not task:
                return self._ok("introspection.last_bios_task", "No BIOS task has been recorded yet.", {})
            return self._ok("introspection.last_bios_task", f"Last BIOS task: {task}. Result: {result or 'n/a'}.", bios)
        if "what memory did it update" in low or "last memory update" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            memory_updates = state.get("last_memory_updates") or []
            if not memory_updates:
                return self._ok("introspection.memory_updates", "No internal memory update has been recorded yet.", {"memory_updates": []})
            return self._ok(
                "introspection.memory_updates",
                json.dumps(memory_updates, ensure_ascii=False, indent=2),
                {"memory_updates": memory_updates},
            )
        if "what growth blocker" in low or "growth blocker" in low:
            current_growth = growth or (snapshot or {}).get("_growth") or {}
            blockers = current_growth.get("blocked_by") or current_growth.get("missing_requirements") or []
            if not blockers:
                return self._ok("introspection.growth_blockers", "No active growth blocker is recorded right now.", {"blockers": []})
            return self._ok("introspection.growth_blockers", f"Current growth blockers: {', '.join(str(item) for item in blockers[:6])}.", {"blockers": blockers})
        if "mutation proposals" in low or "mutation reports" in low:
            reports = _load_jsonl_tail(self._mind_root / "mutations" / "reports.jsonl", limit=5)
            if not reports:
                return self._ok("introspection.mutation_reports", "No mutation proposals or reports exist yet.", {"reports": []})
            short = [
                {
                    "mutation_id": item.get("mutation_id"),
                    "decision": item.get("decision"),
                    "power_gain": item.get("power_gain"),
                    "risk": item.get("risk"),
                }
                for item in reports
            ]
            return self._ok("introspection.mutation_reports", json.dumps(short, ensure_ascii=False, indent=2), {"reports": short})
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
            return self._ok("introspection.mutation_blockers", f"Mutation blockers: {', '.join(blockers[:8])}.", {"blockers": blockers})
        if "why are you slowing down" in low or "resource mode" in low or "show resource governor status" in low:
            resource = _load_json(self._mind_root / "resource_state.json", {})
            if not resource:
                return self._ok("introspection.resource_mode", "No resource governor state has been persisted yet.", {})
            return self._ok("introspection.resource_mode", json.dumps(resource, ensure_ascii=False, indent=2), resource)
        if "what are you throttling" in low:
            resource = _load_json(self._mind_root / "resource_state.json", {})
            throttled = list(resource.get("throttled_operations") or [])
            mode = str(resource.get("mode") or "unknown")
            text = f"Resource mode {mode}. Throttling: {', '.join(throttled) if throttled else 'nothing right now'}."
            return self._ok("introspection.resource_throttling", text, {"mode": mode, "throttled_operations": throttled})
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
            text = json.dumps(data, ensure_ascii=False, indent=2) if resource else "No resource budget has been persisted yet."
            return self._ok("introspection.cpu_budget", text, data)
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
            text = json.dumps(data, ensure_ascii=False, indent=2) if resource else "No resource load sample has been persisted yet."
            return self._ok("introspection.resource_load", text, data)
        if "why did you pause growth" in low or "why did you pause or allow growth" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            if not metabolic:
                return self._ok("introspection.growth_pause", "No metabolic state has been persisted yet.", {})
            data = {
                "growth_allowed": metabolic.get("growth_allowed"),
                "resource_mode": metabolic.get("resource_mode"),
                "growth_suspended_by_resource": metabolic.get("growth_suspended_by_resource"),
                "reasons": metabolic.get("reasons", []),
            }
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return self._ok("introspection.growth_pause", text, data)
        if "why did you pause mutation" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            mutation = _load_json(self._mind_root / "mutation_state.json", {})
            data = {
                "mutation_suspended_by_resource": metabolic.get("mutation_suspended_by_resource"),
                "resource_mode": metabolic.get("resource_mode"),
                "last_blockers": mutation.get("last_blockers", []),
            }
            text = json.dumps(data, ensure_ascii=False, indent=2)
            return self._ok("introspection.mutation_pause", text, data)
        if "show performance profile" in low:
            perf = _load_json(self._mind_root / "performance_state.json", {})
            if not perf:
                return self._ok("introspection.performance", "No performance profile has been persisted yet.", {})
            return self._ok("introspection.performance", json.dumps(perf, ensure_ascii=False, indent=2), perf)
        if "recovery or growth mode" in low or "metabolic mode" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            mode = metabolic.get("mode")
            reasons = metabolic.get("reasons") or []
            if not mode:
                return self._ok("introspection.metabolic_mode", "No metabolic state has been persisted yet.", {})
            return self._ok("introspection.metabolic_mode", f"Metabolic mode: {mode}. Reasons: {', '.join(reasons[:6]) or 'none'}.", metabolic)
        if "metabolic vector" in low:
            metabolic = _load_json(self._mind_root / "metabolic_state.json", {})
            if not metabolic:
                return self._ok("introspection.metabolic_vector", "No metabolic vector has been persisted yet.", {})
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
            return self._ok("introspection.metabolic_vector", json.dumps(compact, ensure_ascii=False, indent=2), compact)
        if "reward trend" in low or "reward state" in low:
            reward = _load_json(self._mind_root / "reward_state.json", {})
            if not reward:
                return self._ok("introspection.reward", "No reward state has been persisted yet.", {})
            compact = {
                "rolling_score": reward.get("rolling_score"),
                "trend": reward.get("trend"),
                "last_kind": reward.get("last_kind"),
                "last_value": reward.get("last_value"),
                "count": reward.get("count"),
            }
            return self._ok("introspection.reward", json.dumps(compact, ensure_ascii=False, indent=2), compact)
        return None

    def _ok(self, skill_id: str, text: str, data: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "skill_id": skill_id,
            "text": text,
            "data": data,
            "source": "builtin",
        }

    def _render_prompt_ref(self, prompt: Any) -> str:
        if isinstance(prompt, dict):
            return json.dumps(prompt, ensure_ascii=False, indent=2)
        return str(prompt or "").strip()
