"""
soma_core/actions.py — Formal action vocabulary for the Soma agent.

Actions are either:
  - silent/internal: internal state changes, visible only in cognitive trace
  - visible/avatar: CSS/animation commands sent to frontend avatar
  - speech: text utterances (gated by LLM and speech cooldown)

Actions must NOT be generated randomly.
They must derive from drive state, policy, and affect.
"""

from __future__ import annotations

from typing import Any


# ── silent action names ───────────────────────────────────────────────────────

SILENT_ACTIONS = frozenset({
    "observe",
    "reflect_silently",
    "store_memory",
    "update_goal",
    "update_self_model",
    "change_attention",
    "reduce_tick_rate",
    "increase_tick_rate",
    "mark_uncertainty",
    "track_thermal_baseline",
    "track_load_baseline",
    "track_disk_baseline",
})

# ── visible/avatar action names ────────────────────────────────────────────────

AVATAR_ACTIONS = frozenset({
    "neutral_idle",
    "attend_user",
    "cold_closed",
    "heat_open",
    "fatigue_slow",
    "instability_corrective",
    "low_power_still",
    "curious_focus",
    "discomfort_shift",
    "relief_soften",
    "thinking_idle",
})


def make_action(
    action_type: str,
    name: str,
    intensity: float,
    reason: str,
    *,
    visible: bool = True,
    target: str = "avatar",
    duration_ms: int = 3000,
) -> dict[str, Any]:
    return {
        "type": action_type,
        "name": name,
        "intensity": round(max(0.0, min(1.0, intensity)), 3),
        "reason": reason,
        "visible": visible,
        "target": target,
        "duration_ms": duration_ms,
    }


def select_actions(
    drives: dict[str, Any],
    affect: dict[str, float],
    policy_mode: str,
    *,
    user_present: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Returns (silent_actions, visible_actions) based on current drive/affect/policy.
    Does NOT generate speech — that is gated separately by SomaMind.
    """
    silent: list[dict[str, Any]] = []
    visible: list[dict[str, Any]] = []

    dominant = drives.get("dominant", "curiosity")
    thermal_stress = affect.get("heat", 0.0)
    energy_stress = affect.get("energy_low", 0.0)
    instability = affect.get("instability", 0.0)
    fatigue = affect.get("fatigue", 0.0)
    cold = affect.get("cold", 0.0)
    curiosity = affect.get("curiosity", 0.0)
    knowledge_gap = affect.get("knowledge_gap", 0.0)

    # ── silent actions ────────────────────────────────────────────────────────

    # Always observe
    silent.append(make_action("silent", "observe", 1.0, "Continuous somatic observation.", visible=False, target="internal"))

    # Baseline tracking
    if policy_mode in ("observe_and_learn", "nominal_idle") or dominant == "self_knowledge":
        silent.append(make_action("silent", "track_thermal_baseline", 0.6, "Accumulating thermal history.", visible=False, target="memory"))
        if knowledge_gap > 0.3:
            silent.append(make_action("silent", "mark_uncertainty", knowledge_gap, "Hardware map incomplete.", visible=False, target="internal"))

    # Reflection
    if policy_mode == "reflection":
        silent.append(make_action("silent", "reflect_silently", 0.8, "Reflection cycle triggered.", visible=False, target="internal"))

    # Goal update
    if dominant in ("self_knowledge", "stability"):
        silent.append(make_action("silent", "update_goal", 0.5, f"Drive {dominant} active.", visible=False, target="goals"))

    # Rate adjustment
    if thermal_stress > 0.65 or energy_stress > 0.65:
        silent.append(make_action("silent", "reduce_tick_rate", max(thermal_stress, energy_stress), "Reducing compute under stress.", visible=False, target="system"))
    elif curiosity > 0.6 and policy_mode in ("observe_and_learn", "curious_focus"):
        silent.append(make_action("silent", "increase_tick_rate", curiosity * 0.5, "Heightened attention.", visible=False, target="system"))

    # ── visible avatar actions ────────────────────────────────────────────────

    if instability >= 0.55:
        visible.append(make_action("avatar", "instability_corrective", instability, "Correcting for physical instability.", duration_ms=2000))
    elif thermal_stress >= 0.65:
        visible.append(make_action("avatar", "heat_open", thermal_stress, "Thermal discomfort response.", duration_ms=4000))
    elif cold >= 0.60:
        visible.append(make_action("avatar", "cold_closed", cold, "Cold response — conserving heat.", duration_ms=4000))
    elif energy_stress >= 0.60:
        visible.append(make_action("avatar", "low_power_still", energy_stress, "Low energy mode.", duration_ms=5000))
    elif fatigue >= 0.65:
        visible.append(make_action("avatar", "fatigue_slow", fatigue, "Fatigue response.", duration_ms=4000))
    elif user_present:
        visible.append(make_action("avatar", "attend_user", 0.7, "User is present.", duration_ms=3000))
    elif curiosity >= 0.55 and dominant == "curiosity":
        visible.append(make_action("avatar", "curious_focus", curiosity, "Curiosity dominant.", duration_ms=3000))
    elif policy_mode == "reflection":
        visible.append(make_action("avatar", "thinking_idle", 0.5, "In reflection cycle.", duration_ms=5000))
    else:
        visible.append(make_action("avatar", "neutral_idle", 0.4, "Nominal state.", duration_ms=3000))

    return silent, visible
