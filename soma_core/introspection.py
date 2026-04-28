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
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            prompt = str(state.get("last_prompt") or "").strip()
            return self._ok("introspection.last_bios_prompt", prompt or "No internal BIOS prompt has been persisted yet.", {"prompt": prompt})
        if "last internal deepseek json" in low or "last deepseek json" in low or "last internal json" in low:
            state = _load_json(self._mind_root / "internal_loop_state.json", {})
            parsed = state.get("last_parsed") or {}
            text = json.dumps(parsed, ensure_ascii=False, indent=2) if parsed else "No internal DeepSeek JSON has been persisted yet."
            return self._ok("introspection.last_internal_json", text, {"parsed": parsed})
        if "what task did your bios run last" in low or "last bios task" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            task = str(bios.get("last_task") or "").strip()
            result = str(bios.get("last_result") or "").strip()
            if not task:
                return self._ok("introspection.last_bios_task", "No BIOS task has been recorded yet.", {})
            return self._ok("introspection.last_bios_task", f"Last BIOS task: {task}. Result: {result or 'n/a'}.", bios)
        if ("what evidence did" in low and "bios" in low) or "last bios evidence" in low:
            bios = _load_json(self._mind_root / "bios_state.json", {})
            evidence = bios.get("last_evidence") or {}
            text = json.dumps(evidence, ensure_ascii=False, indent=2) if evidence else "No BIOS evidence has been recorded yet."
            return self._ok("introspection.last_bios_evidence", text, {"evidence": evidence})
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
            blockers.extend(list(metabolic.get("reasons") or []))
            blockers.extend(list(mutation.get("last_blockers") or []))
            if not blockers:
                blockers = ["no_recorded_mutation_blocker"]
            return self._ok("introspection.mutation_blockers", f"Mutation blockers: {', '.join(blockers[:8])}.", {"blockers": blockers})
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
