"""
soma_core/mind.py — SomaMind: the volitional loop of the Latent Somatic agent.

Full tick loop:
  perceive → body model → drives → goals → policy → actions → reflect → memory → growth → trace

Returns MindState dict merged into public_payload every tick.
All external I/O is handled by server.py; SomaMind owns only logic.
"""

from __future__ import annotations

import time
from typing import Any, Callable

from soma_core.config import CFG
from soma_core.goals import GoalStore
from soma_core.memory import SomaMemory
from soma_core.reflection import ReflectionEngine
from soma_core.drives import compute_drives
from soma_core.policy import select_policy
from soma_core.actions import select_actions
from soma_core.growth import compute_growth
from soma_core.trace import CognitiveTrace


class SomaMind:
    """
    Called once per tick by server.py.
    Returns MindState dict for public_payload.
    Side effects: may write to data/mind/*.json and data/mind/*.jsonl.
    """

    def __init__(
        self,
        goal_store: GoalStore,
        memory: SomaMemory,
        reflection_engine: ReflectionEngine,
        *,
        on_reflection: Callable[[dict[str, Any]], None] | None = None,
        on_growth: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self._goals = goal_store
        self._mem = memory
        self._reflection = reflection_engine
        self._on_reflection = on_reflection
        self._on_growth = on_growth

        self._trace = CognitiveTrace()
        self._tick_count: int = 0
        self._goal_update_every: int = max(1, int(CFG.goal_update_interval_s * CFG.tick_hz))
        self._speech_cooldown_until: float = 0.0
        self._last_reflection_at: float = 0.0
        self._last_reflection_trigger: str = ""
        self._last_learned: str = ""
        self._last_user_interaction_at: float = 0.0
        self._expressiveness_events: int = 0
        self._growth_last_event: str | None = None

        # Growth baseline
        self._growth: dict[str, Any] = {"growth_score": 0.0, "stage": "reflex_shell", "current_evolution_target": "connect_real_sensors"}

    # ── main tick ─────────────────────────────────────────────────────────────

    def tick(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not CFG.volition_enabled:
            return self._passive_state(snapshot)

        self._tick_count += 1
        now = time.time()
        user_present = (now - self._last_user_interaction_at) < 30.0

        # ── inject memory body into snapshot for drive computation ─────────────
        snapshot["_memory_body"] = self._mem.get_body()
        snapshot["_last_user_interaction_age_s"] = now - self._last_user_interaction_at

        # 1. Trace: perception
        self._trace.perception(snapshot)

        # 2. Trace: body model
        derived = snapshot.get("derived", {})
        scenario = snapshot.get("scenario", "nominal")
        self._trace.body_model(derived, scenario)

        # 3. Trace: somatic projection
        self._trace.somatic_projection(snapshot.get("projector", {}))

        # 4. Compute drives
        drives = compute_drives(snapshot)
        self._trace.drives(drives)

        # 5. Update goal priorities periodically
        if self._tick_count % self._goal_update_every == 0:
            self._goals.update_priorities(snapshot.get("affect", {}), snapshot.get("homeostasis", {}))

        # 6. Select active goal
        top_goal = self._goals.top_goal()
        if top_goal:
            self._trace.goals(top_goal["id"], top_goal["title"], top_goal["priority"], top_goal["progress"])

        # 7. Determine if reflection is due
        reflection_due = (now - self._last_reflection_at) >= CFG.reflection_interval_s

        # 8. Policy selection
        llm_available = _is_llm_live(snapshot)
        policy = select_policy(
            drives, snapshot,
            reflection_due=reflection_due,
            user_present=user_present,
            llm_available=llm_available,
        )
        if top_goal:
            policy["active_goal_id"] = top_goal["id"]
            policy["active_goal_title"] = top_goal["title"]
        self._trace.policy(policy["mode"], policy["reason_summary"])

        # 9. Action selection
        affect = snapshot.get("affect", {})
        silent_actions, visible_actions = select_actions(drives, affect, policy["mode"], user_present=user_present)
        self._trace.action_selection(silent_actions + visible_actions)

        # Count expressiveness events
        for a in visible_actions:
            if a["name"] != "neutral_idle":
                self._expressiveness_events += 1
                break

        # 10. Reflection (throttled)
        reflection_entry = None
        if reflection_due:
            self._reflection.ingest(snapshot)
            reflection_entry = self._reflection.maybe_reflect(snapshot)
            if reflection_entry is not None:
                self._last_reflection_at = reflection_entry["timestamp"]
                self._last_reflection_trigger = reflection_entry.get("trigger", "")
                learned = reflection_entry.get("learned", [])
                self._last_learned = learned[0] if learned else ""
                if learned:
                    self._growth_last_event = learned[0]
                self._trace.reflection(
                    reflection_entry["trigger"],
                    reflection_entry["summary"],
                    learned,
                    reflection_entry.get("confidence", 0.7),
                )
                mem_updates = reflection_entry.get("self_model_updates", {})
                if mem_updates:
                    self._trace.memory_update(mem_updates)
                if self._on_reflection:
                    try:
                        self._on_reflection(reflection_entry)
                    except Exception:
                        pass
        else:
            self._reflection.ingest(snapshot)

        # 11. LLM status trace (once per N ticks to avoid spam)
        if self._tick_count % max(1, int(CFG.tick_hz * 10)) == 0:
            llm_info = snapshot.get("llm", {})
            self._trace.llm_status(llm_available, llm_info.get("mode", "off"))

        # 12. Growth
        sm = self._mem.get_growth()
        body = self._mem.get_body()
        learned_body = int(sm.get("learned_body_patterns", 0)) + self._count_body_baselines(body)
        learned_user = int(sm.get("learned_user_patterns", 0))

        goals_progress = [g["progress"] for g in self._goals.active_goals()]
        avg_progress = sum(goals_progress) / max(len(goals_progress), 1)

        provider_is_real = snapshot.get("provider", {}).get("is_real", False)
        projector_active = snapshot.get("projector", {}).get("mode") == "torchscript"
        total_reflections = int(sm.get("total_reflections", 0))

        self._growth = compute_growth(
            reflections=total_reflections,
            learned_body_patterns=learned_body,
            learned_user_patterns=learned_user,
            goal_progress_avg=avg_progress,
            truthfulness_score=0.9,  # system never presents fallback as real → high score
            provider_is_real=provider_is_real,
            projector_active=projector_active,
            llm_available=llm_available,
            expressiveness_events=self._expressiveness_events,
        )
        if self._growth_last_event:
            self._growth["last_growth_event"] = self._growth_last_event

        # Emit growth trace on stage/score changes
        if self._tick_count % max(1, int(CFG.tick_hz * 30)) == 0:
            self._trace.growth(
                self._growth.get("next_growth_step", ""),
                self._growth["growth_score"],
                self._growth["stage"],
            )

        # 13. Build and return MindState
        speech_remaining = max(0.0, self._speech_cooldown_until - now)
        return {
            "volition_enabled": True,
            "active_goal_id": top_goal["id"] if top_goal else "",
            "active_goal_title": top_goal["title"] if top_goal else "",
            "active_goal_progress": round(top_goal["progress"], 3) if top_goal else 0.0,
            "dominant_drive": drives.get("dominant", ""),
            "dominant_drive_intensity": float(drives.get(drives.get("dominant", ""), 0.0)),
            "drives": {k: v for k, v in drives.items() if k != "dominant"},
            "policy_mode": policy["mode"],
            "policy_urgency": policy["urgency"],
            "policy_confidence": policy["confidence"],
            "silent_actions": [a["name"] for a in silent_actions],
            "visible_action": visible_actions[0]["name"] if visible_actions else "neutral_idle",
            "visible_action_intensity": visible_actions[0]["intensity"] if visible_actions else 0.0,
            "visible_actions": visible_actions,
            "last_reflection_at": self._last_reflection_at,
            "last_reflection_trigger": self._last_reflection_trigger,
            "last_learned": self._last_learned,
            "speech_cooldown_remaining": round(speech_remaining, 1),
            "llm_live": llm_available,
            "growth": self._growth,
            "trace": self._trace.get_recent(12),
        }

    def on_user_message(self, text: str, snapshot: dict[str, Any]) -> None:
        """Call when user sends a message — resets social presence tracking."""
        self._last_user_interaction_at = time.time()
        self._goals.add_evidence("improve_dialogue", f"User: {text[:100]}", progress_delta=0.01)
        self._trace.emit("perception", f"User message received: \"{text[:80]}\".", level="info")

    def should_speak(self, snapshot: dict[str, Any]) -> bool:
        """Whether autonomous speech is permitted now."""
        if not CFG.volition_enabled:
            return False
        if time.time() < self._speech_cooldown_until:
            return False
        derived = snapshot.get("derived", {})
        ts = derived.get("thermal_stress", 0.0)
        es = derived.get("energy_stress", 0.0)
        ins = derived.get("instability", 0.0)
        # Only speak on significant events
        return max(ts, es, ins) >= 0.65 or (self._last_learned and (time.time() - self._last_reflection_at) < 5.0)

    def set_speech_cooldown(self, seconds: float) -> None:
        self._speech_cooldown_until = time.time() + seconds

    def get_trace(self, n: int = 20, phase: str | None = None) -> list[dict[str, Any]]:
        return self._trace.get_recent(n, phase_filter=phase)

    def goals_for_llm(self) -> list[dict[str, Any]]:
        return self._goals.summary_for_llm()

    def memory_for_llm(self) -> dict[str, Any]:
        return self._mem.context_for_llm()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _passive_state(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "volition_enabled": False,
            "active_goal_id": "",
            "active_goal_title": "",
            "active_goal_progress": 0.0,
            "dominant_drive": "",
            "dominant_drive_intensity": 0.0,
            "drives": {},
            "policy_mode": "passive",
            "policy_urgency": 0.0,
            "policy_confidence": 0.0,
            "silent_actions": [],
            "visible_action": "neutral_idle",
            "visible_action_intensity": 0.0,
            "visible_actions": [],
            "last_reflection_at": 0.0,
            "last_reflection_trigger": "",
            "last_learned": "",
            "speech_cooldown_remaining": 0.0,
            "llm_live": _is_llm_live(snapshot),
            "growth": {"growth_score": 0.0, "stage": "reflex_shell"},
            "trace": [],
        }

    def _count_body_baselines(self, body: dict[str, Any]) -> int:
        keys = ("cpu_temp_baseline", "disk_temp_baseline", "memory_percent_baseline", "cpu_percent_baseline")
        return sum(1 for k in keys if body.get(k) is not None)


def _is_llm_live(snapshot: dict[str, Any]) -> bool:
    llm = snapshot.get("llm", {})
    return bool(llm.get("available", False)) and llm.get("mode", "") not in ("fallback", "off", "")
