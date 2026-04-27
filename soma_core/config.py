"""
soma_core/config.py — Centralized runtime configuration from environment variables.

Single source of truth for all feature flags and tunable parameters.
Replaces scattered os.getenv() calls across server.py.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _bool(key: str, default: bool) -> bool:
    v = os.getenv(key, "").strip().lower()
    if not v:
        return default
    return v not in {"0", "false", "no", "off"}


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


def _str(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


@dataclass(frozen=True)
class SomaConfig:
    # ── sensor ────────────────────────────────────────────────────────────────
    sensor_provider: str = field(default_factory=lambda: _str("SOMA_SENSOR_PROVIDER", "mock").lower())

    # ── LLM ───────────────────────────────────────────────────────────────────
    llm_mode: str = field(default_factory=lambda: _str("SOMA_LLM_MODE", "off").lower())
    llm_timeout_s: float = field(default_factory=lambda: _float("SOMA_LLM_TIMEOUT_SEC", 30.0))
    reflection_interval_s: float = field(default_factory=lambda: _float("SOMA_REFLECTION_INTERVAL_SEC", 120.0))
    goal_update_interval_s: float = field(default_factory=lambda: _float("SOMA_GOAL_UPDATE_INTERVAL_SEC", 30.0))
    speech_cooldown_s: float = field(default_factory=lambda: _float("SOMA_SPONTANEOUS_SPEECH_COOLDOWN_SEC", 90.0))

    # ── volitional core flags (ON by default) ─────────────────────────────────
    volition_enabled: bool = field(default_factory=lambda: _bool("SOMA_VOLITION", True))
    cognitive_trace_enabled: bool = field(default_factory=lambda: _bool("SOMA_COGNITIVE_TRACE", True))

    # ── autonomy master switch (OFF by default) ───────────────────────────────
    autonomy_unlocked: bool = field(default_factory=lambda: _bool("SOMA_AUTONOMY_UNLOCKED", False))

    # ── agentic feature gates (OFF by default, implied ON when autonomy_unlocked) ─
    discovery_enabled: bool = field(default_factory=lambda: _bool("SOMA_DISCOVERY", False))
    capability_learning_enabled: bool = field(default_factory=lambda: _bool("SOMA_CAPABILITY_LEARNING", False))
    shell_exec_enabled: bool = field(default_factory=lambda: _bool("SOMA_SHELL_EXEC", False))
    self_modify_enabled: bool = field(default_factory=lambda: _bool("SOMA_SELF_MODIFY", False))
    cns_pulse_enabled: bool = field(default_factory=lambda: _bool("SOMA_CNS_PULSE", False))

    # ── survival envelope (only relevant when shell/autonomy is active) ───────
    package_mutation_enabled: bool = field(default_factory=lambda: _bool("SOMA_SYSTEM_PACKAGE_MUTATION", False))
    command_timeout_s: float = field(default_factory=lambda: _float("SOMA_COMMAND_TIMEOUT_SEC", 30.0))
    max_command_output_chars: int = field(default_factory=lambda: int(_float("SOMA_MAX_COMMAND_OUTPUT_CHARS", 12000)))
    max_write_mb: int = field(default_factory=lambda: int(_float("SOMA_MAX_WRITE_MB", 256)))
    min_free_disk_gb: float = field(default_factory=lambda: _float("SOMA_MIN_FREE_DISK_GB", 5.0))
    max_cpu_load: float = field(default_factory=lambda: _float("SOMA_MAX_CPU_LOAD_FOR_HEAVY_TASK", 6.0))
    max_memory_pct: float = field(default_factory=lambda: _float("SOMA_MAX_MEMORY_PERCENT_FOR_HEAVY_TASK", 85.0))

    # ── timing ────────────────────────────────────────────────────────────────
    tick_hz: float = field(default_factory=lambda: _float("SOMA_TICK_HZ", 2.0))

    @property
    def any_exec_active(self) -> bool:
        return self.autonomy_unlocked or self.shell_exec_enabled

    @property
    def any_self_modify_active(self) -> bool:
        return self.autonomy_unlocked or self.self_modify_enabled

    def feature_gate_table(self) -> str:
        lines = [
            f"Autonomy: {'UNLOCKED' if self.autonomy_unlocked else 'off'}",
            "Agentic features:",
            f"  discovery:           {'on' if (self.discovery_enabled or self.autonomy_unlocked) else 'off'}",
            f"  capability_learning: {'on' if (self.capability_learning_enabled or self.autonomy_unlocked) else 'off'}",
            f"  shell_exec:          {'on' if self.any_exec_active else 'off'}",
            f"  self_modify:         {'on' if self.any_self_modify_active else 'off'}",
            f"  cns_pulse:           {'on' if (self.cns_pulse_enabled or self.autonomy_unlocked) else 'off'}",
            "Volitional core:",
            f"  volition:            {'on' if self.volition_enabled else 'off'}",
            f"  cognitive_trace:     {'on' if self.cognitive_trace_enabled else 'off'}",
            f"  reflection_interval: {self.reflection_interval_s}s",
            f"  speech_cooldown:     {self.speech_cooldown_s}s",
            "Survival envelope:",
            f"  package_mutation:    {'on' if self.package_mutation_enabled else 'off (SOMA_SYSTEM_PACKAGE_MUTATION=0)'}",
            f"  command_timeout:     {self.command_timeout_s}s",
            f"  min_free_disk:       {self.min_free_disk_gb}GB",
            f"  max_cpu_load:        {self.max_cpu_load}",
            f"  max_memory_pct:      {self.max_memory_pct}%",
        ]
        return "\n".join(lines)


# Singleton loaded at import time
CFG = SomaConfig()
