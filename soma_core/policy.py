"""
soma_core/policy.py — Policy selection: maps drive state + snapshot → policy mode.

Policy modes (exhaustive):
  nominal_idle         — no stress, no user, baseline monitoring
  attend_user          — user is actively interacting
  observe_and_learn    — self_knowledge drive dominant, no urgency
  preserve_stability   — self_preservation dominant
  thermal_discomfort   — thermal stress above threshold
  low_energy           — energy stress above threshold
  high_uncertainty     — caution/source_quality issues
  reflection           — reflection cycle due
  fallback_reflex      — LLM unavailable during user interaction
  expressive_response  — strong affect with avatar available
  degraded_runtime     — sensor or projector critically degraded
"""

from __future__ import annotations

from typing import Any


def select_policy(
    drives: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    reflection_due: bool = False,
    user_present: bool = False,
    llm_available: bool = False,
) -> dict[str, Any]:
    """
    Returns a PolicyState dict.
    """
    derived = snapshot.get("derived", {})
    system = snapshot.get("system", {})
    affect = snapshot.get("affect", {})
    projector = snapshot.get("projector", {})

    thermal_stress = float(derived.get("thermal_stress", 0.0))
    energy_stress = float(derived.get("energy_stress", 0.0))
    instability = float(derived.get("instability", 0.0))
    source_quality = float(system.get("source_quality", 0.5))
    comfort = float(derived.get("comfort", 1.0))

    dominant = drives.get("dominant", "curiosity")
    caution = float(drives.get("caution", 0.0))
    expressiveness = float(drives.get("expressiveness", 0.0))
    self_knowledge = float(drives.get("self_knowledge", 0.0))
    self_preservation = float(drives.get("self_preservation", 0.0))

    projector_ok = projector.get("available", False)
    provider_is_real = snapshot.get("provider", {}).get("is_real", False)

    # ── Priority-ordered selection ─────────────────────────────────────────────

    if source_quality < 0.15 and not provider_is_real:
        mode = "degraded_runtime"
        urgency = 0.9
        reason = "Sensor provider degraded or unavailable."

    elif thermal_stress >= 0.70 or instability >= 0.75:
        mode = "preserve_stability"
        urgency = max(thermal_stress, instability)
        reason = f"Thermal stress {thermal_stress:.2f} or instability {instability:.2f} critical."

    elif thermal_stress >= 0.55:
        mode = "thermal_discomfort"
        urgency = thermal_stress
        reason = f"Thermal stress {thermal_stress:.2f} above comfort threshold."

    elif energy_stress >= 0.65:
        mode = "low_energy"
        urgency = energy_stress
        reason = f"Energy stress {energy_stress:.2f} — conserving power."

    elif user_present and not llm_available:
        mode = "fallback_reflex"
        urgency = 0.5
        reason = "User active but LLM unavailable — reflex mode only."

    elif user_present:
        mode = "attend_user"
        urgency = 0.4
        reason = "User is interacting."

    elif reflection_due:
        mode = "reflection"
        urgency = 0.3
        reason = "Periodic reflection cycle due."

    elif caution > 0.55 or source_quality < 0.35:
        mode = "high_uncertainty"
        urgency = caution
        reason = f"Caution drive {caution:.2f}, source quality {source_quality:.2f}."

    elif dominant == "self_knowledge" and self_knowledge > 0.40:
        mode = "observe_and_learn"
        urgency = 0.2
        reason = f"Self-knowledge drive dominant ({self_knowledge:.2f})."

    elif expressiveness > 0.55 and projector_ok:
        mode = "expressive_response"
        urgency = 0.25
        reason = f"Expressiveness drive {expressiveness:.2f}."

    else:
        mode = "nominal_idle"
        urgency = 0.1
        reason = "No significant stress — baseline monitoring."

    # ── Compute policy permissions ────────────────────────────────────────────
    allow_speech = (
        llm_available and
        user_present and
        mode not in ("degraded_runtime", "preserve_stability", "low_energy")
    )
    allow_avatar = projector_ok or True  # avatar is always CSS-driven
    allow_tool_use = False  # never by default in volitional core

    confidence = _policy_confidence(source_quality, projector_ok, provider_is_real)

    return {
        "mode": mode,
        "dominant_drive": dominant,
        "active_goal_id": "",   # filled by SomaMind after goal selection
        "active_goal_title": "",
        "reason_summary": reason,
        "urgency": round(urgency, 3),
        "allow_speech": allow_speech,
        "allow_tool_use": allow_tool_use,
        "allow_avatar_action": allow_avatar,
        "confidence": round(confidence, 3),
    }


def _policy_confidence(source_quality: float, projector_ok: bool, provider_is_real: bool) -> float:
    base = source_quality * 0.5
    if projector_ok:
        base += 0.3
    if provider_is_real:
        base += 0.2
    return max(0.0, min(1.0, base))
