"""
soma_core/goals.py — Persistent goal store and priority scoring.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from soma_core.types import Goal, GoalSet

_GOALS_FILE = Path(__file__).parent.parent / "data" / "mind" / "goals.json"


def _load() -> GoalSet:
    try:
        data = json.loads(_GOALS_FILE.read_text(encoding="utf-8"))
        return GoalSet(data)
    except (FileNotFoundError, json.JSONDecodeError):
        return GoalSet(active_goals=[], completed_goals=[], updated_at=0.0)


def _save(gs: GoalSet) -> None:
    gs["updated_at"] = time.time()
    _GOALS_FILE.write_text(json.dumps(gs, indent=2, ensure_ascii=True), encoding="utf-8")


class GoalStore:
    """
    Loads, scores, and persists goals.
    Designed to be called once per tick (update_priorities) and on events (add_evidence).
    """

    def __init__(self) -> None:
        self._gs = _load()
        self._ensure_builtin_goals()

    # ── built-in goals ────────────────────────────────────────────────────────

    _BUILTIN: list[dict[str, Any]] = [
        {"id": "maintain_stability",         "title": "Maintain somatic stability",                         "drive": "homeostasis",   "priority": 0.90},
        {"id": "understand_own_body",        "title": "Understand my thermal and resource profile",         "drive": "self_knowledge","priority": 0.75},
        {"id": "reduce_false_claims",        "title": "Never report data I do not actually measure",        "drive": "integrity",     "priority": 0.80},
        {"id": "improve_dialogue",           "title": "Improve quality of dialogue with operator",          "drive": "social",        "priority": 0.60},
        {"id": "learn_environment_patterns", "title": "Learn recurring patterns in my environment",         "drive": "self_knowledge","priority": 0.55},
        {"id": "develop_avatar_expressiveness", "title": "Develop richer avatar expression",                "drive": "expression",    "priority": 0.40},
    ]

    def _ensure_builtin_goals(self) -> None:
        existing_ids = {g["id"] for g in self._gs["active_goals"]}
        changed = False
        for spec in self._BUILTIN:
            if spec["id"] not in existing_ids:
                self._gs["active_goals"].append(Goal(
                    id=spec["id"], title=spec["title"],
                    drive=spec["drive"], priority=spec["priority"],
                    status="active", progress=0.0,
                    created_at=time.time(), updated_at=time.time(),
                    next_action="observe", evidence=[],
                ))
                changed = True
        if changed:
            _save(self._gs)

    # ── queries ───────────────────────────────────────────────────────────────

    def active_goals(self) -> list[Goal]:
        return [g for g in self._gs["active_goals"] if g["status"] == "active"]

    def top_goal(self) -> Goal | None:
        goals = self.active_goals()
        return max(goals, key=lambda g: g["priority"]) if goals else None

    def get(self, goal_id: str) -> Goal | None:
        for g in self._gs["active_goals"]:
            if g["id"] == goal_id:
                return g
        return None

    # ── mutations ─────────────────────────────────────────────────────────────

    def add_evidence(self, goal_id: str, text: str, progress_delta: float = 0.0) -> None:
        g = self.get(goal_id)
        if g is None:
            return
        g["evidence"].append(text[:200])
        if len(g["evidence"]) > 20:
            g["evidence"] = g["evidence"][-20:]
        g["progress"] = min(1.0, g["progress"] + progress_delta)
        g["updated_at"] = time.time()
        _save(self._gs)

    def update_priorities(self, affect: dict[str, float], homeostasis: dict[str, Any]) -> None:
        """
        Re-score goal priorities from current drives and affect.
        Called every N ticks (not every tick — no disk write needed every second).
        """
        homeo_drives = homeostasis.get("drives", {})
        stability_margin = homeostasis.get("stability_margin", 1.0)
        energy_margin = homeostasis.get("energy_margin", 1.0)
        thermal_margin = homeostasis.get("thermal_margin", 1.0)

        for g in self._gs["active_goals"]:
            if g["status"] != "active":
                continue
            drive = g["drive"]
            base = g["priority"]

            if drive == "homeostasis":
                # Urgency rises when margins fall
                boost = (1.0 - min(stability_margin, energy_margin, thermal_margin)) * 0.3
                g["priority"] = min(1.0, base + boost)
            elif drive == "self_knowledge":
                gap = affect.get("knowledge_gap", 0.0)
                g["priority"] = min(1.0, base + gap * 0.15)
            elif drive == "integrity":
                # Always high — slight boost when LLM is in fallback (more likely to hallucinate)
                g["priority"] = max(base, 0.75)
            elif drive == "social":
                curiosity = affect.get("curiosity", 0.5)
                g["priority"] = min(1.0, 0.50 + curiosity * 0.25)
            # other drives: no dynamic scoring yet

        _save(self._gs)

    def complete_goal(self, goal_id: str, reason: str = "") -> None:
        g = self.get(goal_id)
        if g is None:
            return
        g["status"] = "completed"
        g["updated_at"] = time.time()
        if reason:
            g["evidence"].append(f"[COMPLETED] {reason}")
        self._gs["completed_goals"].append(g)
        self._gs["active_goals"] = [x for x in self._gs["active_goals"] if x["id"] != goal_id]
        _save(self._gs)

    def summary_for_llm(self) -> list[dict[str, Any]]:
        """Compact goal summary for LLM context injection."""
        return [
            {
                "id": g["id"],
                "title": g["title"],
                "priority": round(g["priority"], 2),
                "progress": round(g["progress"], 2),
                "drive": g["drive"],
            }
            for g in self.active_goals()
        ]
