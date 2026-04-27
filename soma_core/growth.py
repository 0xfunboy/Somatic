"""
soma_core/growth.py — Measurable runtime self-improvement tracking.

Growth is not mystical. It is a weighted metric of observable improvements:
- learned body baselines
- goal progress
- reflections completed
- truthfulness (fallback not presented as real cognition)
- real sensor availability
- avatar expressiveness coverage

Growth stages:
  reflex_shell              — no real sensors
  early_self_observation    — real sensors, no projector or LLM
  body_model_learning       — stable baselines being built
  goal_directed_behavior    — active goals with measurable progress
  expressive_embodiment     — avatar actions tied to internal state
  autonomous_self_improvement — sustained learning without user intervention
  cpp_embodied_runtime_ready — protocol stable, ready for C++ daemon
"""

from __future__ import annotations

import time
from typing import Any


_STAGES = [
    "reflex_shell",
    "early_self_observation",
    "body_model_learning",
    "goal_directed_behavior",
    "expressive_embodiment",
    "autonomous_self_improvement",
    "cpp_embodied_runtime_ready",
]


def compute_growth(
    *,
    reflections: int,
    learned_body_patterns: int,
    learned_user_patterns: int,
    goal_progress_avg: float,
    truthfulness_score: float,
    provider_is_real: bool,
    projector_active: bool,
    llm_available: bool,
    expressiveness_events: int,
) -> dict[str, Any]:
    """
    Compute growth score and stage from observable metrics.
    Returns a dict suitable for public_payload and frontend display.
    """
    # ── weighted score ────────────────────────────────────────────────────────
    score = min(1.0,
        reflections * 0.010 +
        learned_body_patterns * 0.030 +
        learned_user_patterns * 0.015 +
        goal_progress_avg * 0.40 +
        truthfulness_score * 0.20 +
        (0.10 if provider_is_real else 0.0) +
        (0.05 if projector_active else 0.0) +
        min(0.05, expressiveness_events * 0.005)
    )

    # ── stage determination (ceilings from doc) ───────────────────────────────
    if not provider_is_real:
        stage = "reflex_shell"
    elif not projector_active and not llm_available:
        stage = "early_self_observation"
    elif learned_body_patterns < 2:
        stage = "early_self_observation"
    elif goal_progress_avg < 0.15:
        stage = "body_model_learning"
    elif goal_progress_avg < 0.35:
        stage = "goal_directed_behavior"
    elif expressiveness_events < 5:
        stage = "goal_directed_behavior"
    elif reflections < 20:
        stage = "expressive_embodiment"
    else:
        stage = "autonomous_self_improvement"

    # LLM ceiling: cannot exceed early_self_observation if LLM is fallback
    if not llm_available:
        stage_idx = min(_STAGES.index(stage), _STAGES.index("early_self_observation"))
        stage = _STAGES[stage_idx]

    next_step = _next_growth_step(stage, learned_body_patterns, goal_progress_avg, reflections)

    return {
        "growth_score": round(score, 4),
        "stage": stage,
        "current_evolution_target": _evolution_target(stage),
        "next_growth_step": next_step,
        "total_reflections": reflections,
        "learned_body_patterns": learned_body_patterns,
        "learned_user_patterns": learned_user_patterns,
        "last_growth_event": None,  # filled by SomaMind when growth occurs
    }


def _evolution_target(stage: str) -> str:
    return {
        "reflex_shell": "connect_real_sensors",
        "early_self_observation": "build_body_baselines",
        "body_model_learning": "progress_active_goals",
        "goal_directed_behavior": "develop_avatar_expressiveness",
        "expressive_embodiment": "sustain_autonomous_reflection",
        "autonomous_self_improvement": "prepare_cpp_daemon",
        "cpp_embodied_runtime_ready": "deploy_embodied_runtime",
    }.get(stage, "observe")


def _next_growth_step(stage: str, learned: int, progress: float, reflections: int) -> str:
    if stage == "reflex_shell":
        return "Connect real Linux sensor provider."
    if stage == "early_self_observation":
        return "Observe idle CPU and disk temperature for 2+ minutes to establish baselines."
    if stage == "body_model_learning":
        return f"Progress active goals beyond 15% (current avg {progress:.0%})."
    if stage == "goal_directed_behavior":
        return "Map 5+ avatar actions to internal affect states."
    if stage == "expressive_embodiment":
        return f"Complete {20 - reflections} more reflections to deepen self-model."
    return "Maintain sustained autonomous reflection without user intervention."
