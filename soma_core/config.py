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
    reflection_interval_s: float = field(default_factory=lambda: _float("SOMA_REFLECTION_INTERVAL_SEC", 600.0))
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
    cognitive_tick_hz: float = field(default_factory=lambda: _float("SOMA_COGNITIVE_TICK_HZ", 5.0))
    mind_pulse_sec: float = field(default_factory=lambda: _float("SOMA_MIND_PULSE_SEC", 30.0))
    growth_eval_interval_s: float = field(default_factory=lambda: _float("SOMA_GROWTH_EVAL_INTERVAL_SEC", 120.0))
    autobiography_min_interval_s: float = field(default_factory=lambda: _float("SOMA_AUTOBIOGRAPHY_MIN_INTERVAL_SEC", 300.0))

    # ── trace persistence ─────────────────────────────────────────────────────
    trace_persistence: str = field(default_factory=lambda: _str("SOMA_TRACE_PERSISTENCE", "important"))
    trace_hot_max_mb: float = field(default_factory=lambda: _float("SOMA_TRACE_HOT_MAX_MB", 10.0))
    trace_archive_gzip: bool = field(default_factory=lambda: _bool("SOMA_TRACE_ARCHIVE_GZIP", True))

    # ── journal ───────────────────────────────────────────────────────────────
    journal_enabled: bool = field(default_factory=lambda: _bool("SOMA_JOURNAL_ENABLED", True))
    journal_hot_max_mb: float = field(default_factory=lambda: _float("SOMA_JOURNAL_HOT_MAX_MB", 25.0))
    journal_compact_at_mb: float = field(default_factory=lambda: _float("SOMA_JOURNAL_COMPACT_AT_MB", 50.0))
    actuation_history_min_interval_s: float = field(default_factory=lambda: _float("SOMA_ACTUATION_HISTORY_MIN_INTERVAL_SEC", 30.0))

    # ── autobiography ─────────────────────────────────────────────────────────
    autobiography_enabled: bool = field(default_factory=lambda: _bool("SOMA_AUTOBIOGRAPHY_ENABLED", True))

    # ── routines ──────────────────────────────────────────────────────────────
    routines_enabled: bool = field(default_factory=lambda: _bool("SOMA_ROUTINES_ENABLED", True))
    routine_min_interval_s: float = field(default_factory=lambda: _float("SOMA_ROUTINE_MIN_INTERVAL_SEC", 300.0))
    routine_idle_only: bool = field(default_factory=lambda: _bool("SOMA_ROUTINE_IDLE_ONLY", True))
    routine_max_per_hour: int = field(default_factory=lambda: int(_float("SOMA_ROUTINE_MAX_PER_HOUR", 6.0)))

    # ── nightly reflection ────────────────────────────────────────────────────
    nightly_reflection: bool = field(default_factory=lambda: _bool("SOMA_NIGHTLY_REFLECTION", True))
    nightly_hour: int = field(default_factory=lambda: int(_float("SOMA_NIGHTLY_HOUR", 3.0)))
    nightly_minute: int = field(default_factory=lambda: int(_float("SOMA_NIGHTLY_MINUTE", 30.0)))
    nightly_require_idle: bool = field(default_factory=lambda: _bool("SOMA_NIGHTLY_REQUIRE_IDLE", True))
    nightly_compact_logs: bool = field(default_factory=lambda: _bool("SOMA_NIGHTLY_COMPACT_LOGS", True))
    nightly_use_llm: bool = field(default_factory=lambda: _bool("SOMA_NIGHTLY_USE_LLM", True))

    # ── self-improvement ──────────────────────────────────────────────────────
    self_improvement_enabled: bool = field(default_factory=lambda: _bool("SOMA_SELF_IMPROVEMENT_ENABLED", True))
    self_improvement_auto_apply: bool = field(default_factory=lambda: _bool("SOMA_SELF_IMPROVEMENT_AUTO_APPLY", False))
    self_improvement_auto_rollback: bool = field(default_factory=lambda: _bool("SOMA_SELF_IMPROVEMENT_AUTO_ROLLBACK", True))
    self_improvement_max_files: int = field(default_factory=lambda: int(_float("SOMA_SELF_IMPROVEMENT_MAX_FILES", 5.0)))
    self_improvement_max_diff_lines: int = field(default_factory=lambda: int(_float("SOMA_SELF_IMPROVEMENT_MAX_DIFF_LINES", 500.0)))
    self_improvement_require_tests: bool = field(default_factory=lambda: _bool("SOMA_SELF_IMPROVEMENT_REQUIRE_TESTS", True))

    # ── BIOS loop ─────────────────────────────────────────────────────────────
    bios_loop: bool = field(default_factory=lambda: _bool("SOMA_BIOS_LOOP", True))
    bios_interval_sec: float = field(default_factory=lambda: _float("SOMA_BIOS_INTERVAL_SEC", 300.0))
    bios_idle_only: bool = field(default_factory=lambda: _bool("SOMA_BIOS_IDLE_ONLY", False))
    bios_use_llm: bool = field(default_factory=lambda: _bool("SOMA_BIOS_USE_LLM", True))
    bios_max_tasks_per_hour: int = field(default_factory=lambda: int(_float("SOMA_BIOS_MAX_TASKS_PER_HOUR", 12.0)))
    bios_max_llm_calls_per_hour: int = field(default_factory=lambda: int(_float("SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR", 12.0)))
    bios_task_timeout_sec: float = field(default_factory=lambda: _float("SOMA_BIOS_TASK_TIMEOUT_SEC", 60.0))
    bios_write_memory: bool = field(default_factory=lambda: _bool("SOMA_BIOS_WRITE_MEMORY", True))
    bios_mutation_proposal_interval_sec: float = field(default_factory=lambda: _float("SOMA_BIOS_MUTATION_PROPOSAL_INTERVAL_SEC", 1800.0))

    # ── mutation sandbox ──────────────────────────────────────────────────────
    mutation_sandbox: bool = field(default_factory=lambda: _bool("SOMA_MUTATION_SANDBOX", True))
    mutation_root: str = field(default_factory=lambda: _str("SOMA_MUTATION_ROOT", "/home/funboy/latent-somatic-mutants"))
    mutation_auto_apply: bool = field(default_factory=lambda: _bool("SOMA_MUTATION_AUTO_APPLY", False))
    mutation_auto_create_sandbox: bool = field(default_factory=lambda: _bool("SOMA_MUTATION_AUTO_CREATE_SANDBOX", True))
    mutation_max_per_day: int = field(default_factory=lambda: int(_float("SOMA_MUTATION_MAX_PER_DAY", 3.0)))
    mutation_require_operator_approval_for_migration: bool = field(default_factory=lambda: _bool("SOMA_MUTATION_REQUIRE_OPERATOR_APPROVAL_FOR_MIGRATION", True))
    mutation_run_tests: bool = field(default_factory=lambda: _bool("SOMA_MUTATION_RUN_TESTS", True))
    mutation_smoke_test: bool = field(default_factory=lambda: _bool("SOMA_MUTATION_SMOKE_TEST", True))
    mutation_sandbox_ws_port: int = field(default_factory=lambda: int(_float("SOMA_MUTATION_SANDBOX_WS_PORT", 8875.0)))
    mutation_sandbox_http_port: int = field(default_factory=lambda: int(_float("SOMA_MUTATION_SANDBOX_HTTP_PORT", 8880.0)))

    # ── C++ bridge ────────────────────────────────────────────────────────────
    cpp_bridge: bool = field(default_factory=lambda: _bool("SOMA_CPP_BRIDGE", True))
    cpp_binary: str = field(default_factory=lambda: _str("SOMA_CPP_BINARY", "/home/funboy/latent-somatic/build/latent_somatic"))
    cpp_auto_build: bool = field(default_factory=lambda: _bool("SOMA_CPP_AUTO_BUILD", False))
    cpp_smoke_test_on_start: bool = field(default_factory=lambda: _bool("SOMA_CPP_SMOKE_TEST_ON_START", True))
    cpp_use_for_projection: bool = field(default_factory=lambda: _bool("SOMA_CPP_USE_FOR_PROJECTION", False))
    cpp_llama_cpp_root: str = field(default_factory=lambda: _str("SOMA_CPP_LLAMA_CPP_ROOT", "/home/funboy/llama.cpp"))

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
