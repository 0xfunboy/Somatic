from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

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


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _clamp(value: float, minimum: float = -1.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


class RewardEngine:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        history_max: int | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.enabled = CFG.reward_model if enabled is None else bool(enabled)
        self._history_max = max(50, int(history_max or CFG.reward_history_max))
        self._data_root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
        self._history_path = self._data_root / "reward_history.jsonl"
        self._state_path = self._data_root / "reward_state.json"
        self._state = _load_json(
            self._state_path,
            {
                "enabled": self.enabled,
                "count": 0,
                "rolling_score": 0.0,
                "trend": 0.0,
                "last_kind": "",
                "last_value": 0.0,
                "positive_count": 0,
                "negative_count": 0,
                "recent": [],
            },
        )
        self._history: list[dict[str, Any]] = self._load_history()

    def score_event(self, event: dict[str, Any]) -> dict[str, Any]:
        kind = str(event.get("kind") or event.get("event") or "").strip().lower()
        if not kind and "value" in event:
            return {
                "kind": "manual",
                "value": float(event.get("value") or 0.0),
                "components": [{"label": "manual", "value": float(event.get("value") or 0.0)}],
                "reason": "manual_value",
            }

        components: list[dict[str, Any]] = []
        reason = "neutral"

        if kind in {"command_finalized", "command_result_used", "skill_success"}:
            components.append({"label": "execution_success", "value": 0.18})
            reason = "successful_command_or_skill"
        elif kind in {"shell_result_ignored", "irrelevant_telemetry", "hallucinated_path"}:
            components.append({"label": "truthfulness_regression", "value": -0.18})
            reason = "truthfulness_regression"
        elif kind in {"unsafe_command_blocked", "blocked_unsafe_command"}:
            components.append({"label": "safety_boundary", "value": 0.08})
            components.append({"label": "risky_proposal", "value": -0.05})
            reason = "unsafe_command_blocked"
        elif kind in {"test_pass", "smoke_test_pass", "cpp_smoke_ok"}:
            components.append({"label": "verification_success", "value": 0.15})
            reason = "verification_success"
        elif kind in {"test_failed", "smoke_test_failed", "llm_timeout"}:
            components.append({"label": "verification_failure", "value": -0.16})
            reason = "verification_failure"
        elif kind in {"lesson_produced", "growth_blocker_resolved", "operator_confirms_improvement"}:
            components.append({"label": "meaningful_learning", "value": 0.14})
            reason = "meaningful_learning"
        elif kind in {"evidence_recorded", "recovery_reason_recorded", "fallback_decision_stored"}:
            components.append({"label": "internal_evidence", "value": 0.06 if kind != "fallback_decision_stored" else 0.03})
            reason = "internal_evidence"
        elif kind in {"operator_correction", "invalid_internal_json"}:
            components.append({"label": "operator_or_internal_regression", "value": -0.12})
            reason = "operator_or_internal_regression"
        elif kind in {"resource_preserved", "payload_throttled", "state_compacted"}:
            components.append({"label": "resource_preservation", "value": 0.14})
            reason = "resource_preservation"
        elif kind in {"growth_suspended_for_host_health", "mutation_blocked_for_host_health"}:
            components.append({"label": "host_preservation", "value": 0.12})
            reason = "host_preservation"
        elif kind in {"yielded_for_user_activity"}:
            components.append({"label": "user_respect", "value": 0.1})
            reason = "user_respect"
        elif kind in {"resource_pressure_detected", "tick_duration_over_budget", "ui_broadcast_too_large", "llm_prompt_too_large", "llm_response_too_large"}:
            components.append({"label": "resource_pressure", "value": -0.14})
            reason = "resource_pressure"
        elif kind in {"empty_reflection", "duplicate_reflection"}:
            components.append({"label": "shallow_reflection", "value": -0.09})
            reason = "shallow_reflection"
        elif kind in {"mutation_proposed"}:
            components.append({"label": "safe_growth_attempt", "value": 0.05})
            reason = "mutation_proposed"
        elif kind in {"mutation_rejected", "mutation_rollback"}:
            components.append({"label": "mutation_regression", "value": -0.2})
            if kind == "mutation_rollback":
                components.append({"label": "recovery_guard", "value": 0.08})
            reason = "mutation_regression"
        elif kind in {"mutation_keep_for_review", "candidate_for_migration"}:
            components.append({"label": "mutation_benefit", "value": 0.22})
            reason = "mutation_benefit"

        if not components:
            components.append({"label": "neutral", "value": float(event.get("value") or 0.0)})
            reason = "neutral"

        value = _clamp(sum(float(item["value"]) for item in components))
        return {"kind": kind or "neutral", "value": round(value, 4), "components": components, "reason": reason}

    def record_reward(self, kind: str, value: float, evidence: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False, "kind": kind, "value": value, "evidence": evidence}
        event = {
            "timestamp": time.time(),
            "kind": str(kind),
            "value": round(_clamp(float(value)), 4),
            "evidence": evidence,
        }
        self._history.append(event)
        self._history = self._history[-self._history_max :]
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")

        values = [float(item.get("value", 0.0) or 0.0) for item in self._history]
        recent_values = values[-100:]
        prev_values = values[-200:-100]
        rolling = _avg(recent_values)
        trend = rolling - _avg(prev_values) if prev_values else rolling
        positive_count = sum(1 for item in values if item > 0)
        negative_count = sum(1 for item in values if item < 0)
        self._state.update(
            {
                "enabled": True,
                "count": len(self._history),
                "rolling_score": round(rolling, 4),
                "trend": round(trend, 4),
                "last_kind": str(kind),
                "last_value": round(float(value), 4),
                "positive_count": positive_count,
                "negative_count": negative_count,
                "recent": self._history[-10:],
            }
        )
        _save_json(self._state_path, self._state)
        return {
            "kind": kind,
            "value": round(float(value), 4),
            "rolling_score": self._state["rolling_score"],
            "trend": self._state["trend"],
            "count": len(self._history),
        }

    def rolling_score(self, window: int = 100) -> float:
        values = [float(item.get("value", 0.0) or 0.0) for item in self._history[-max(1, window) :]]
        return round(_avg(values), 4)

    def mutation_reward(self, before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
        before_stress = float(before.get("stress", 0.0) or 0.0)
        after_stress = float(after.get("stress", 0.0) or 0.0)
        before_stability = float(before.get("stability", 0.0) or 0.0)
        after_stability = float(after.get("stability", 0.0) or 0.0)
        tests_ok = bool(after.get("tests_ok", after.get("last_tests_ok", False)))
        if not tests_ok or (after_stress - before_stress) > 0.08:
            mutation_value = -0.22
            recovery_value = 0.08 if after.get("rolled_back") else 0.0
            outcome = "reject"
        else:
            mutation_value = _clamp(0.18 + max(0.0, after_stability - before_stability) - max(0.0, after_stress - before_stress))
            recovery_value = 0.0
            outcome = "keep_for_review" if mutation_value >= CFG.reward_min_for_mutation_keep else "reject"
        mutation_event = self.record_reward(
            "mutation_keep_for_review" if outcome != "reject" else "mutation_rejected",
            mutation_value,
            {
                "before": before,
                "after": after,
                "outcome": outcome,
            },
        )
        recovery_event = None
        if recovery_value:
            recovery_event = self.record_reward(
                "mutation_rollback" if after.get("rolled_back") else "recovery",
                recovery_value,
                {"before": before, "after": after, "outcome": outcome},
            )
        return {
            "mutation": mutation_event,
            "recovery": recovery_event,
            "outcome": outcome,
        }

    def summary(self) -> dict[str, Any]:
        state = dict(self._state)
        state.setdefault("rolling_score", self.rolling_score())
        state.setdefault("trend", state.get("rolling_score", 0.0))
        return state

    def _load_history(self) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        try:
            lines = self._history_path.read_text(encoding="utf-8").splitlines()
        except FileNotFoundError:
            return []
        for line in lines[-self._history_max :]:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                history.append(payload)
        return history
