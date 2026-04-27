"""
soma_core/types.py — Runtime state contract for the Latent Somatic Fusion agent.

All types are plain Python typed dicts so they can be serialized to JSON and
are portable to a future C++ daemon without modification.
"""

from __future__ import annotations
from typing import Any


# ── Body layer ────────────────────────────────────────────────────────────────

class BodyState(dict):
    """Compact snapshot of somatic sensor readings."""
    voltage: float
    current_ma: float
    temp_si: float   # silicon temp (CPU)
    temp_ml: float
    temp_mr: float
    ax: float; ay: float; az: float
    gx: float; gy: float; gz: float


class SystemTelemetry(dict):
    """Machine-level telemetry from the host OS."""
    cpu_percent: float | None
    cpu_temp: float | None
    cpu_power_w: float | None
    memory_percent: float | None
    disk_busy_percent: float | None
    net_down_mbps: float | None
    net_up_mbps: float | None
    gpu_util_percent: float | None
    battery_percent: float | None
    ac_online: bool | None
    source_quality: float


class SomaticVectorState(dict):
    """Output of the somatic projector."""
    available: bool
    mode: str           # "torchscript" | "analytic"
    norm: float
    top_dims: list[int]
    top_vals: list[float]
    machine_fusion_enabled: bool
    machine_fusion_mode: str


# ── Affect and homeostasis ────────────────────────────────────────────────────

class AffectState(dict):
    """Continuous affect signals [0, 1]."""
    cold: float
    heat: float
    energy_low: float
    fatigue: float
    instability: float
    curiosity: float
    knowledge_gap: float


class HomeostasisState(dict):
    """Homeostatic drives and margins."""
    drives: dict[str, float]
    dominant: list[dict[str, Any]]
    stability_margin: float
    thermal_margin: float
    energy_margin: float
    power_source: str
    body_orientation: str


# ── Goals ─────────────────────────────────────────────────────────────────────

class Goal(dict):
    """A single persistent intentional goal."""
    id: str
    title: str
    drive: str
    priority: float      # [0, 1]
    status: str          # "active" | "paused" | "completed" | "failed"
    progress: float      # [0, 1]
    created_at: float
    updated_at: float
    next_action: str
    evidence: list[str]


class GoalSet(dict):
    """Full persistent goal store."""
    active_goals: list[Goal]
    completed_goals: list[Goal]
    updated_at: float


# ── Policy and actions ────────────────────────────────────────────────────────

class PolicyState(dict):
    """Current behavioral policy."""
    mode: str            # "nominal" | "lowbatt" | "overheat" | etc.
    posture: str
    fan_target: str
    compute_governor: str
    language_profile: str
    thermal_guard: bool
    balance_guard: bool


class ActionCommand(dict):
    """A single executable action emitted by the mind."""
    type: str       # "posture" | "expression" | "gesture" | "visual" | "speak" | "reflect" | "observe"
    name: str
    intensity: float    # [0, 1]
    payload: dict[str, Any]   # optional extra data


# ── Reflection ────────────────────────────────────────────────────────────────

class ReflectionEntry(dict):
    """Output of a single reflection cycle."""
    timestamp: float
    kind: str            # "self_reflection"
    trigger: str         # what caused the reflection
    summary: str
    learned: list[str]
    goal_updates: list[dict[str, Any]]
    self_model_updates: dict[str, Any]


# ── Self model ────────────────────────────────────────────────────────────────

class SelfModel(dict):
    """Persistent self-representation — updated by reflection."""
    identity: dict[str, Any]
    known_body: dict[str, Any]
    preferences: dict[str, Any]
    growth: dict[str, Any]
    updated_at: float


# ── Top-level snapshot ────────────────────────────────────────────────────────

class SomaSnapshot(dict):
    """
    Full runtime snapshot — mirrors the WebSocket 'tick' payload.
    Used as the shared state object across soma_core modules.
    """
    timestamp: float
    scenario: str
    provider: dict[str, Any]
    sensors: BodyState
    system: SystemTelemetry
    affect: AffectState
    derived: dict[str, float]
    homeostasis: HomeostasisState
    machine_vector: list[float]
    projector: SomaticVectorState
    policy: PolicyState
    actuation: dict[str, Any]
    summary: str


# ── Mind state (added to every tick payload) ──────────────────────────────────

class MindState(dict):
    """Live state of the SomaMind — broadcast on every tick."""
    active_goal_id: str
    active_goal_title: str
    active_goal_progress: float
    dominant_drive: str
    dominant_drive_intensity: float
    policy_mode: str
    last_reflection_at: float
    last_reflection_trigger: str
    last_learned: str
    speech_cooldown_remaining: float
    volition_enabled: bool
    llm_live: bool          # True only when LLM is not in fallback mode
