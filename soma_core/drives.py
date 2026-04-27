"""
soma_core/drives.py — Compute drive intensities from real runtime state.

Drives are continuous [0,1] signals derived from snapshot state.
They are NOT affect (physiological analogs) — they are motivational.
Each drive maps to one or more long-term goals and influences policy.
"""

from __future__ import annotations

from typing import Any


def _clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def compute_drives(snapshot: dict[str, Any]) -> dict[str, Any]:
    """
    Compute all drive intensities from the current snapshot.
    Returns a dict with per-drive floats and a 'dominant' string.
    """
    derived = snapshot.get("derived", {})
    affect = snapshot.get("affect", {})
    system = snapshot.get("system", {})
    projector = snapshot.get("projector", {})
    llm = snapshot.get("llm", {})
    mind_prev = snapshot.get("mind", {})  # previous mind state if available

    thermal_stress = float(derived.get("thermal_stress", 0.0))
    energy_stress = float(derived.get("energy_stress", 0.0))
    instability = float(derived.get("instability", 0.0))
    comfort = float(derived.get("comfort", 1.0))
    source_quality = float(system.get("source_quality", 0.5))
    cpu_pct = float(system.get("cpu_percent") or 0.0)
    battery = system.get("battery_percent")

    llm_available = llm.get("available", False)
    llm_fallback = not llm_available or llm.get("mode", "") in ("fallback", "off", "")
    projector_real = projector.get("mode", "") == "torchscript"

    # 1. self_preservation — high when body is threatened
    self_preservation = _clamp(
        thermal_stress * 0.50 +
        energy_stress * 0.35 +
        instability * 0.25 +
        (1.0 - source_quality) * 0.10
    )

    # 2. stability — high when conditions are changing or uncertain
    stability = _clamp(
        instability * 0.40 +
        (1.0 - source_quality) * 0.30 +
        thermal_stress * 0.20 +
        (0.3 if not projector_real else 0.0)
    )

    # 3. self_knowledge — high when gaps/uncertainty exist
    knowledge_gap = float(affect.get("knowledge_gap", 0.0))
    body = snapshot.get("_memory_body", {})  # populated by mind if available
    missing_baselines = sum(
        1 for k in ("cpu_temp_baseline", "disk_temp_baseline", "memory_percent_baseline")
        if body.get(k) is None
    ) / 3.0
    self_knowledge = _clamp(
        knowledge_gap * 0.40 +
        missing_baselines * 0.30 +
        (0.3 if source_quality < 0.4 else 0.0) +
        (0.2 if not projector_real else 0.0)
    )

    # 4. social_contact — high when user recently interacted
    last_user_interaction = float(snapshot.get("_last_user_interaction_age_s", 300.0))
    social_contact = _clamp(
        (1.0 - _clamp(last_user_interaction / 120.0)) * 0.60 +
        affect.get("curiosity", 0.0) * 0.20 +
        (0.2 if llm_fallback else 0.0)  # want to communicate but limited
    )

    # 5. expressiveness — high when affect is strong and avatar not expressing it
    affect_magnitude = max(
        affect.get("heat", 0.0),
        affect.get("cold", 0.0),
        affect.get("energy_low", 0.0),
        affect.get("instability", 0.0),
        affect.get("fatigue", 0.0),
    )
    expressiveness = _clamp(affect_magnitude * 0.70 + (1.0 - comfort) * 0.30)

    # 6. curiosity — high when novelty/gaps exist
    curiosity = _clamp(
        affect.get("curiosity", 0.0) * 0.50 +
        knowledge_gap * 0.30 +
        (0.2 if source_quality < 0.5 else 0.0)
    )

    # 7. caution — high when uncertain/fallback/degraded
    caution = _clamp(
        (1.0 if llm_fallback else 0.0) * 0.35 +
        (1.0 - source_quality) * 0.30 +
        instability * 0.20 +
        (0.15 if not projector_real else 0.0)
    )

    # 8. energy_conservation — high under load or low battery
    if battery is not None:
        batt_urgency = _clamp((40.0 - float(battery)) / 40.0)
    else:
        batt_urgency = 0.0
    energy_conservation = _clamp(
        thermal_stress * 0.30 +
        cpu_pct / 200.0 +
        batt_urgency * 0.40 +
        energy_stress * 0.30
    )

    drives = {
        "self_preservation": round(self_preservation, 3),
        "stability": round(stability, 3),
        "self_knowledge": round(self_knowledge, 3),
        "social_contact": round(social_contact, 3),
        "expressiveness": round(expressiveness, 3),
        "curiosity": round(curiosity, 3),
        "caution": round(caution, 3),
        "energy_conservation": round(energy_conservation, 3),
    }

    dominant = max(drives, key=lambda k: drives[k])
    return {**drives, "dominant": dominant}
