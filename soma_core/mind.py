"""
soma_core/mind.py — SomaMind: the volitional loop of the Latent Somatic agent.

SomaMind is called once per tick by server.py.  It:
  1. Perceives the current snapshot (affect + homeostasis)
  2. Updates goal priorities from current drives
  3. Decides which action to emit (if any)
  4. Optionally runs a reflection cycle
  5. Returns a MindState dict that server.py merges into public_payload

It owns no I/O.  All external calls (LLM, broadcast) are injected as callbacks
so the core loop stays deterministic and testable.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from soma_core.goals import GoalStore
from soma_core.memory import SomaMemory
from soma_core.reflection import ReflectionEngine


class SomaMind:
    """
    Entry point: call `tick(snapshot)` every sensor cycle.
    Returns a MindState dict ready to be merged into public_payload.
    """

    def __init__(
        self,
        goal_store: GoalStore,
        memory: SomaMemory,
        reflection_engine: ReflectionEngine,
        *,
        on_reflection: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._goals = goal_store
        self._mem = memory
        self._reflection = reflection_engine
        self._on_reflection = on_reflection  # callback to broadcast reflection to frontend

        self._last_reflection_at: float = 0.0
        self._last_reflection_trigger: str = ""
        self._last_learned: str = ""
        self._speech_cooldown_until: float = 0.0
        self._tick_count: int = 0
        self._priority_update_interval: int = 30  # ticks between goal re-scoring

    # ── main loop ─────────────────────────────────────────────────────────────

    def tick(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Called every sensor tick. Returns MindState dict.
        Side effects: may update goals.json, self_model.json, reflections.jsonl.
        """
        self._tick_count += 1
        now = time.time()

        affect = snapshot.get("affect", {})
        homeostasis = snapshot.get("homeostasis", {})

        # 1. Update goal priorities periodically
        if self._tick_count % self._priority_update_interval == 0:
            self._goals.update_priorities(affect, homeostasis)

        # 2. Feed reflection engine
        self._reflection.ingest(snapshot)

        # 3. Run analytical reflection (throttled internally)
        reflection_entry = self._reflection.maybe_reflect(snapshot)
        if reflection_entry is not None:
            self._last_reflection_at = reflection_entry["timestamp"]
            self._last_reflection_trigger = reflection_entry.get("trigger", "")
            learned = reflection_entry.get("learned", [])
            self._last_learned = learned[0] if learned else ""
            if self._on_reflection:
                try:
                    self._on_reflection(reflection_entry)
                except Exception:
                    pass

        # 4. Identify current dominant goal and drive
        top_goal = self._goals.top_goal()
        dominant_drives = homeostasis.get("dominant", [])
        dom_drive = dominant_drives[0] if dominant_drives else {}

        # 5. Speech cooldown countdown
        speech_remaining = max(0.0, self._speech_cooldown_until - now)

        return {
            "active_goal_id": top_goal["id"] if top_goal else "",
            "active_goal_title": top_goal["title"] if top_goal else "",
            "active_goal_progress": round(top_goal["progress"], 2) if top_goal else 0.0,
            "dominant_drive": dom_drive.get("name", ""),
            "dominant_drive_intensity": round(float(dom_drive.get("intensity", 0.0)), 3),
            "policy_mode": snapshot.get("policy", {}).get("mode", "nominal"),
            "last_reflection_at": self._last_reflection_at,
            "last_reflection_trigger": self._last_reflection_trigger,
            "last_learned": self._last_learned,
            "speech_cooldown_remaining": round(speech_remaining, 1),
            "volition_enabled": True,
            "llm_live": _is_llm_live(snapshot),
        }

    # ── helpers ───────────────────────────────────────────────────────────────

    def set_speech_cooldown(self, seconds: float) -> None:
        self._speech_cooldown_until = time.time() + seconds

    def goal_evidence(self, goal_id: str, text: str, progress_delta: float = 0.0) -> None:
        self._goals.add_evidence(goal_id, text, progress_delta)

    def goals_for_llm(self) -> list[dict[str, Any]]:
        return self._goals.summary_for_llm()

    def memory_for_llm(self) -> dict[str, Any]:
        return self._mem.context_for_llm()


def _is_llm_live(snapshot: dict[str, Any]) -> bool:
    """True only when the LLM is in a live (non-fallback) mode."""
    llm = snapshot.get("llm", {})
    mode = llm.get("mode", "")
    return llm.get("available", False) and mode not in ("fallback", "off", "")
