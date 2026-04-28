"""
soma_core/mind.py — SomaMind: fast body tick, slower mind pulse and growth.
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
from soma_core.growth_engine import GrowthEngine
from soma_core.trace import CognitiveTrace
from soma_core.life_drive import LifeDrive


class SomaMind:
    def __init__(
        self,
        goal_store: GoalStore,
        memory: SomaMemory,
        reflection_engine: ReflectionEngine,
        *,
        on_reflection: Callable[[dict[str, Any]], None] | None = None,
        on_growth: Callable[[dict[str, Any]], None] | None = None,
        autobiography: Any | None = None,
        growth_engine: GrowthEngine | None = None,
        life_drive: LifeDrive | None = None,
    ) -> None:
        self._goals = goal_store
        self._mem = memory
        self._reflection = reflection_engine
        self._on_reflection = on_reflection
        self._on_growth = on_growth
        self._autobiography = autobiography
        self._growth_engine = growth_engine or GrowthEngine()
        self._life_drive = life_drive or LifeDrive()

        self._trace = CognitiveTrace()
        self._tick_count = 0
        self._goal_update_every = max(1, int(CFG.goal_update_interval_s * CFG.tick_hz))
        self._speech_cooldown_until = 0.0
        self._last_reflection_at = 0.0
        self._last_reflection_trigger = ""
        self._last_learned = ""
        self._last_user_interaction_at = 0.0
        self._expressiveness_events = 0
        self._last_growth_stage = ""
        self._last_growth_eval_at = 0.0
        self._last_mind_pulse_at = 0.0
        self._life_drive_state: dict[str, Any] = {
            "dominant_drive": "coherence",
            "drive_strengths": {},
            "suggested_internal_task": "check_growth_requirements",
        }
        self._growth: dict[str, Any] = {
            "stage": "reflex_shell",
            "score": 0.0,
            "growth_score": 0.0,
            "completed_requirements": [],
            "missing_requirements": [],
            "blocked_by": [],
            "evidence": {},
            "next_step": "",
            "last_evaluated_at": 0.0,
        }

    def tick(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not CFG.volition_enabled:
            return self._passive_state(snapshot)

        self._tick_count += 1
        now = time.time()
        user_present = (now - self._last_user_interaction_at) < 30.0
        snapshot["_memory_body"] = self._mem.get_body()
        snapshot["_last_user_interaction_age_s"] = now - self._last_user_interaction_at

        self._trace.perception(snapshot)
        self._trace.body_model(snapshot.get("derived", {}), snapshot.get("scenario", "nominal"))
        self._trace.somatic_projection(snapshot.get("projector", {}))

        drives = compute_drives(snapshot)
        self._trace.drives(drives)

        if self._tick_count % self._goal_update_every == 0:
            self._goals.update_priorities(snapshot.get("affect", {}), snapshot.get("homeostasis", {}))

        top_goal = self._goals.top_goal()
        if top_goal:
            self._trace.goals(top_goal["id"], top_goal["title"], top_goal["priority"], top_goal["progress"])

        reflection_due = (now - self._last_reflection_at) >= CFG.reflection_interval_s
        llm_available = _is_llm_live(snapshot)
        policy = select_policy(
            drives,
            snapshot,
            reflection_due=reflection_due,
            user_present=user_present,
            llm_available=llm_available,
        )
        if top_goal:
            policy["active_goal_id"] = top_goal["id"]
            policy["active_goal_title"] = top_goal["title"]
        self._trace.policy(policy["mode"], policy["reason_summary"])

        silent_actions, visible_actions = select_actions(drives, snapshot.get("affect", {}), policy["mode"], user_present=user_present)
        self._trace.action_selection(silent_actions + visible_actions)
        if any(action["name"] != "neutral_idle" for action in visible_actions):
            self._expressiveness_events += 1

        reflection_entry = None
        self._reflection.ingest(snapshot)
        if reflection_due:
            reflection_entry = self._reflection.maybe_reflect(snapshot)
            if reflection_entry is not None:
                self._last_reflection_at = float(reflection_entry["timestamp"])
                self._last_reflection_trigger = reflection_entry.get("trigger", "")
                learned = reflection_entry.get("learned", [])
                self._last_learned = learned[0] if learned else ""
                self._trace.reflection(
                    reflection_entry["trigger"],
                    reflection_entry["summary"],
                    learned,
                    float(reflection_entry.get("confidence", 0.5)),
                )
                if self._on_reflection:
                    try:
                        self._on_reflection(reflection_entry)
                    except Exception:
                        pass

        if self._tick_count % max(1, int(CFG.tick_hz * 10)) == 0:
            self._trace.llm_status(llm_available, snapshot.get("llm", {}).get("mode", "off"))

        growth_due = (
            (now - self._last_growth_eval_at) >= CFG.growth_eval_interval_s
            or reflection_entry is not None
            or not self._growth.get("last_evaluated_at")
        )
        if growth_due:
            self._growth = self._growth_engine.evaluate(snapshot, {
                "frontend_connected": True,
                "sample_minutes": float(snapshot.get("sample_minutes", 0.0)),
                "baselines": snapshot.get("baselines", {}),
                "command_agency": snapshot.get("command_agency", {}),
                "autobiography": snapshot.get("autobiography_quality", {}),
                "bios": snapshot.get("bios_status", {}),
                "mutation": snapshot.get("mutation_status", {}),
                "cpp_bridge": snapshot.get("cpp_bridge_status", {}),
            })
            self._last_growth_eval_at = now
            self._life_drive_state = self._life_drive.evaluate(
                snapshot,
                self._growth,
                {"autobiography": snapshot.get("autobiography_quality", {})},
            )
            self._mem.set_growth({
                **self._growth,
                "reflection_quality": self._mem.get_growth().get("reflection_quality", {}),
                "command_agency": snapshot.get("command_agency", {}),
            })
            self._trace.growth(
                self._growth.get("next_step", ""),
                float(self._growth.get("growth_score", 0.0)),
                self._growth.get("stage", "reflex_shell"),
            )
            if self._on_growth:
                try:
                    self._on_growth(self._growth)
                except Exception:
                    pass
            new_stage = self._growth.get("stage", "")
            if new_stage and new_stage != self._last_growth_stage and self._autobiography is not None:
                self._autobiography.write_meaningful_event({
                    "kind": "milestone",
                    "title": f"Growth stage reached: {new_stage}",
                    "summary": (
                        f"Soma advanced to growth stage '{new_stage}'. "
                        f"Missing requirements: {', '.join(self._growth.get('missing_requirements', [])[:4]) or 'none'}."
                    ),
                    "impact": "high",
                    "timestamp": now,
                })
                self._last_growth_stage = new_stage

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
            "life_drive": self._life_drive_state,
            "trace": self._trace.get_recent(12),
        }

    def on_user_message(self, text: str, snapshot: dict[str, Any]) -> None:
        self._last_user_interaction_at = time.time()
        self._goals.add_evidence("improve_dialogue", f"User: {text[:100]}", progress_delta=0.01)
        self._trace.emit("perception", f'User message received: "{text[:80]}".', level="info")

    def should_speak(self, snapshot: dict[str, Any]) -> bool:
        if not CFG.volition_enabled:
            return False
        now = time.time()
        if now < self._speech_cooldown_until:
            return False
        if snapshot.get("scenario") in {"overheat", "fall", "lowbatt"}:
            return True
        return False

    def mark_spoke(self) -> None:
        self._speech_cooldown_until = time.time() + CFG.speech_cooldown_s

    def _passive_state(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return {
            "volition_enabled": False,
            "active_goal_id": "",
            "active_goal_title": "",
            "active_goal_progress": 0.0,
            "dominant_drive": snapshot.get("homeostasis", {}).get("dominant", [{}])[0].get("name", ""),
            "dominant_drive_intensity": 0.0,
            "drives": {},
            "policy_mode": "passive",
            "policy_urgency": 0.0,
            "policy_confidence": 0.0,
            "silent_actions": [],
            "visible_action": snapshot.get("actions", [{}])[0].get("name", "neutral_idle"),
            "visible_action_intensity": snapshot.get("actions", [{}])[0].get("intensity", 0.0),
            "visible_actions": snapshot.get("actions", []),
            "last_reflection_at": 0.0,
            "last_reflection_trigger": "",
            "last_learned": "",
            "speech_cooldown_remaining": 0.0,
            "llm_live": _is_llm_live(snapshot),
            "growth": self._growth,
            "life_drive": self._life_drive_state,
            "trace": self._trace.get_recent(12),
        }


def _is_llm_live(snapshot: dict[str, Any]) -> bool:
    llm = snapshot.get("llm", {})
    return bool(llm.get("available")) if isinstance(llm, dict) else False
