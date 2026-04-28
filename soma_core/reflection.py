"""
soma_core/reflection.py — Reflection engine with measurable quality.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections import deque
from typing import TYPE_CHECKING, Any, Callable, Coroutine

if TYPE_CHECKING:
    pass

from soma_core.memory import SomaMemory
from soma_core.goals import GoalStore

_REFLECTION_MIN_INTERVAL = 60


def _signature(snapshot: dict[str, Any]) -> str:
    system = snapshot.get("system", {})
    derived = snapshot.get("derived", {})
    payload = {
        "scenario": snapshot.get("scenario"),
        "cpu": round(float(system.get("cpu_percent") or 0.0), 1),
        "mem": round(float(system.get("memory_percent") or 0.0), 1),
        "cpu_temp": round(float(system.get("cpu_temp") or 0.0), 1),
        "thermal": round(float(derived.get("thermal_stress") or 0.0), 2),
        "energy": round(float(derived.get("energy_stress") or 0.0), 2),
        "instability": round(float(derived.get("instability") or 0.0), 2),
    }
    return hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]


class ReflectionEngine:
    def __init__(
        self,
        memory: SomaMemory,
        goal_store: GoalStore,
        llm_fn: Callable[[str], Coroutine[Any, Any, str | None]] | None = None,
        autobiography: Any | None = None,
        baseline_store: Any | None = None,
        experience: Any | None = None,
    ) -> None:
        self._mem = memory
        self._goals = goal_store
        self._llm_fn = llm_fn
        self._autobiography = autobiography
        self._baseline_store = baseline_store
        self._experience = experience
        self._last_reflect_at: float = 0.0
        self._last_signature: str = ""
        self._history: deque[str] = deque(maxlen=20)

    def ingest(self, snapshot: dict[str, Any]) -> None:
        self._history.append(_signature(snapshot))

    def maybe_reflect(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        now = time.time()
        if now - self._last_reflect_at < _REFLECTION_MIN_INTERVAL:
            return None
        self._last_reflect_at = now

        sig = _signature(snapshot)
        duplicate = sig == self._last_signature
        self._last_signature = sig

        baseline_updates = {}
        if self._baseline_store is not None:
            baseline_updates = snapshot.get("baseline_update", {}) or {}
        lessons: list[dict[str, Any] | str] = []
        learned: list[str] = []
        behavioral_updates: list[str] = []
        no_lesson_reason = ""

        if duplicate:
            no_lesson_reason = "duplicate"
        elif baseline_updates.get("stable_now"):
            for key in baseline_updates["stable_now"]:
                learned.append(f"Baseline stabilized for {key}")
                lessons.append({
                    "id": f"baseline.{key}",
                    "kind": "lesson",
                    "observation": f"Baseline stabilized for {key}.",
                    "evidence": [{"source": "baseline_store", "value": key}],
                    "interpretation": "This body metric is now stable enough to guide later anomaly detection.",
                    "behavioral_update": f"Use {key} as a stable baseline during future body-state evaluations.",
                    "confidence": 0.8,
                })
        else:
            derived = snapshot.get("derived", {})
            if max(
                float(derived.get("thermal_stress", 0.0)),
                float(derived.get("energy_stress", 0.0)),
                float(derived.get("instability", 0.0)),
            ) >= 0.7:
                learned.append("Body abnormality detected")
                lessons.append({
                    "id": "limitation.abnormal_body_priority",
                    "kind": "limitation",
                    "observation": "Abnormal body state should suppress speculative language.",
                    "evidence": [{"source": "snapshot", "value": snapshot.get("scenario", "unknown")}],
                    "interpretation": "High stress states require direct, safety-oriented responses.",
                    "behavioral_update": "Prefer concise operational responses and stabilization-first behavior during abnormal states.",
                    "confidence": 0.78,
                })
            else:
                no_lesson_reason = "state unchanged / insufficient evidence"

        meaningful = bool(lessons or baseline_updates.get("material_changes"))
        confidence = 0.15 if not meaningful else min(0.95, 0.55 + (0.1 * len(lessons)))
        summary = self._make_summary(snapshot, learned, no_lesson_reason)

        total_reflections = self._mem.increment_reflections()
        if meaningful:
            for item in learned:
                self._mem.record_learned_fact(item)
        quality = self._mem.update_reflection_quality(
            meaningful=meaningful,
            duplicate=duplicate,
            lessons_learned=len(lessons),
        )

        entry: dict[str, Any] = {
            "timestamp": now,
            "kind": "analytical_reflection",
            "trigger": snapshot.get("scenario", "periodic"),
            "summary": summary,
            "learned": learned,
            "lessons": lessons,
            "no_lesson_reason": no_lesson_reason,
            "baseline_updates": baseline_updates,
            "behavioral_updates": behavioral_updates,
            "confidence": round(confidence, 4),
            "meaningful": meaningful,
            "duplicate": duplicate,
            "total_reflections": total_reflections,
            "reflection_quality": quality,
            "self_model_updates": baseline_updates.get("summary", {}),
        }
        self._mem.append_reflection(entry)

        if self._experience is not None:
            distilled = self._experience.distill_from_reflection(entry, snapshot)
            if distilled:
                self._experience.save_lessons(distilled)

        if meaningful and self._autobiography is not None:
            self._autobiography.write_meaningful_event({
                "kind": "reflection",
                "title": "Meaningful reflection",
                "summary": summary,
                "evidence": learned or [no_lesson_reason],
                "impact": "medium" if lessons else "low",
                "confidence": confidence,
                "behavioral_update": lessons[0]["behavioral_update"] if lessons and isinstance(lessons[0], dict) else "",
                "timestamp": now,
            })
        return entry

    def _make_summary(self, snapshot: dict[str, Any], learned: list[str], no_lesson_reason: str) -> str:
        if learned:
            return "Learned: " + "; ".join(learned[:3]) + "."
        scenario = snapshot.get("scenario", "nominal")
        cpu = snapshot.get("system", {}).get("cpu_percent")
        cpu_str = f"{float(cpu):.0f}%" if isinstance(cpu, (int, float)) else "--"
        return f"Reflection on {scenario}: CPU {cpu_str}. No lesson distilled ({no_lesson_reason or 'none'})."
