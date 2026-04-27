"""
soma_core/reflection.py — ReflectionEngine: analytical + optional LLM-based self-reflection.

Analytical reflection runs every N ticks at zero LLM cost:
  - detects new CPU/thermal baselines from recent sensor history
  - records learned facts (sensor ranges, policy transitions)
  - updates goal evidence based on observable progress

LLM-assisted reflection is triggered on significant events (new scenario,
drive spike, milestone) and requires a callable async llm_fn to be injected.
"""

from __future__ import annotations

import time
from collections import deque
from typing import Any, Callable, Coroutine

from soma_core.memory import SomaMemory
from soma_core.goals import GoalStore


_BASELINE_WINDOW = 120        # samples to average for a stable baseline
_BASELINE_MIN_SAMPLES = 30    # minimum before we commit a baseline
_REFLECTION_MIN_INTERVAL = 60  # seconds between analytical reflections


class ReflectionEngine:
    """
    Produces ReflectionEntry dicts; caller decides how to broadcast/store them.

    Usage:
        engine = ReflectionEngine(memory, goal_store)
        entry = engine.maybe_reflect(snapshot)   # returns dict or None
    """

    def __init__(
        self,
        memory: SomaMemory,
        goal_store: GoalStore,
        llm_fn: Callable[[str], Coroutine[Any, Any, str | None]] | None = None,
    ) -> None:
        self._mem = memory
        self._goals = goal_store
        self._llm_fn = llm_fn
        self._last_reflect_at: float = 0.0
        self._cpu_window: deque[float] = deque(maxlen=_BASELINE_WINDOW)
        self._temp_si_window: deque[float] = deque(maxlen=_BASELINE_WINDOW)
        self._last_scenario: str = ""
        self._scenario_streak: int = 0

    # ── public API ───────────────────────────────────────────────────────────

    def ingest(self, snapshot: dict[str, Any]) -> None:
        """Feed every tick; accumulates sensor history."""
        cpu = snapshot["system"].get("cpu_percent")
        temp = snapshot["sensors"].get("temp_si")
        if isinstance(cpu, (int, float)) and cpu == cpu:  # not NaN
            self._cpu_window.append(float(cpu))
        if isinstance(temp, (int, float)) and temp == temp:
            self._temp_si_window.append(float(temp))

        scenario = snapshot.get("scenario", "")
        if scenario == self._last_scenario:
            self._scenario_streak += 1
        else:
            self._last_scenario = scenario
            self._scenario_streak = 1

    def maybe_reflect(self, snapshot: dict[str, Any]) -> dict[str, Any] | None:
        """
        Run analytical reflection if enough time has passed.
        Returns a ReflectionEntry dict on success, None if skipped.
        """
        now = time.time()
        if now - self._last_reflect_at < _REFLECTION_MIN_INTERVAL:
            return None
        self._last_reflect_at = now

        learned: list[str] = []
        goal_updates: list[dict[str, Any]] = []
        self_model_updates: dict[str, Any] = {}

        # --- baseline learning ---
        cpu_baseline = self._learn_baseline("cpu_percent_baseline", self._cpu_window)
        if cpu_baseline is not None:
            self_model_updates["cpu_percent_baseline"] = cpu_baseline
            learned.append(f"CPU baseline stabilised at {cpu_baseline:.1f}%")

        temp_baseline = self._learn_baseline("cpu_temp_baseline", self._temp_si_window)
        if temp_baseline is not None:
            self_model_updates["cpu_temp_baseline"] = temp_baseline
            learned.append(f"CPU temp baseline stabilised at {temp_baseline:.1f}°C")

        # --- goal progress evidence ---
        affect = snapshot.get("affect", {})
        homeostasis = snapshot.get("homeostasis", {})
        stability_margin = homeostasis.get("stability_margin", 1.0)
        thermal_margin = homeostasis.get("thermal_margin", 1.0)

        if stability_margin > 0.85 and thermal_margin > 0.85:
            self._goals.add_evidence(
                "maintain_stability",
                f"Stability margin {stability_margin:.2f}, thermal margin {thermal_margin:.2f}",
                progress_delta=0.01,
            )
            goal_updates.append({"id": "maintain_stability", "delta": 0.01})

        if cpu_baseline is not None or temp_baseline is not None:
            self._goals.add_evidence(
                "understand_own_body",
                f"New sensor baseline computed: {list(self_model_updates.keys())}",
                progress_delta=0.05,
            )
            goal_updates.append({"id": "understand_own_body", "delta": 0.05})

        # --- persist updates ---
        for key, value in self_model_updates.items():
            self._mem.update_body_baseline(key, value)
        for fact in learned:
            self._mem.record_learned_fact(fact)

        total_reflections = self._mem.increment_reflections()

        entry: dict[str, Any] = {
            "timestamp": now,
            "kind": "analytical_reflection",
            "trigger": self._determine_trigger(snapshot),
            "summary": self._make_summary(learned, snapshot),
            "learned": learned,
            "goal_updates": goal_updates,
            "self_model_updates": self_model_updates,
            "total_reflections": total_reflections,
        }
        self._mem.append_reflection(entry)
        return entry

    # ── helpers ──────────────────────────────────────────────────────────────

    def _learn_baseline(self, key: str, window: deque[float]) -> float | None:
        if len(window) < _BASELINE_MIN_SAMPLES:
            return None
        body = self._mem.get_body()
        existing = body.get(key)
        mean = sum(window) / len(window)
        if existing is None or abs(mean - existing) > 2.0:
            return round(mean, 2)
        return None

    def _determine_trigger(self, snapshot: dict[str, Any]) -> str:
        scenario = snapshot.get("scenario", "nominal")
        if self._scenario_streak <= 5:
            return f"scenario_change:{scenario}"
        dominant = snapshot.get("homeostasis", {}).get("dominant", [])
        if dominant:
            return f"drive_dominant:{dominant[0].get('name', 'unknown')}"
        return "periodic"

    def _make_summary(self, learned: list[str], snapshot: dict[str, Any]) -> str:
        if not learned:
            scenario = snapshot.get("scenario", "nominal")
            cpu = snapshot["system"].get("cpu_percent")
            cpu_str = f"{cpu:.0f}%" if isinstance(cpu, (int, float)) else "--"
            return f"Periodic reflection — scenario: {scenario}, CPU: {cpu_str}. No new baselines."
        return "Learned: " + "; ".join(learned[:3]) + "."
