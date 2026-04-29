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
    cns_pulse_enabled: bool = field(default_factory=lambda: _bool("SOMA_CNS_PULSE_ENABLED", _bool("SOMA_CNS_PULSE", False)))

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
    tick_hz_max_normal: float = field(default_factory=lambda: _float("SOMA_TICK_HZ_MAX_NORMAL", 2.0))
    tick_hz_max_reduced: float = field(default_factory=lambda: _float("SOMA_TICK_HZ_MAX_REDUCED", 1.0))
    tick_hz_max_critical: float = field(default_factory=lambda: _float("SOMA_TICK_HZ_MAX_CRITICAL", 0.5))
    tick_hz_max_recovery: float = field(default_factory=lambda: _float("SOMA_TICK_HZ_MAX_RECOVERY", 0.2))
    operator_can_override_resource_hz: bool = field(default_factory=lambda: _bool("SOMA_OPERATOR_CAN_OVERRIDE_RESOURCE_HZ", False))
    ui_full_payload_hz: float = field(default_factory=lambda: _float("SOMA_UI_FULL_PAYLOAD_HZ", 0.5))
    ui_light_tick_hz: float = field(default_factory=lambda: _float("SOMA_UI_LIGHT_TICK_HZ", 2.0))
    ui_max_broadcast_bytes_per_sec: int = field(default_factory=lambda: int(_float("SOMA_UI_MAX_BROADCAST_BYTES_PER_SEC", 250000.0)))
    cns_pulse_interval_sec: float = field(default_factory=lambda: _float("SOMA_CNS_PULSE_INTERVAL_SEC", 10.0))
    discovery_interval_sec: float = field(default_factory=lambda: _float("SOMA_DISCOVERY_INTERVAL_SEC", 600.0))

    # ── resource governor ─────────────────────────────────────────────────────
    resource_governor: bool = field(default_factory=lambda: _bool("SOMA_RESOURCE_GOVERNOR", True))
    resource_mode_default: str = field(default_factory=lambda: _str("SOMA_RESOURCE_MODE_DEFAULT", "normal").lower())
    host_cpu_reduced_percent: float = field(default_factory=lambda: _float("SOMA_HOST_CPU_REDUCED_PERCENT", 55.0))
    host_cpu_critical_percent: float = field(default_factory=lambda: _float("SOMA_HOST_CPU_CRITICAL_PERCENT", 75.0))
    host_mem_reduced_percent: float = field(default_factory=lambda: _float("SOMA_HOST_MEM_REDUCED_PERCENT", 70.0))
    host_mem_critical_percent: float = field(default_factory=lambda: _float("SOMA_HOST_MEM_CRITICAL_PERCENT", 85.0))
    host_swap_critical_percent: float = field(default_factory=lambda: _float("SOMA_HOST_SWAP_CRITICAL_PERCENT", 20.0))
    host_temp_reduced_c: float = field(default_factory=lambda: _float("SOMA_HOST_TEMP_REDUCED_C", 70.0))
    host_temp_critical_c: float = field(default_factory=lambda: _float("SOMA_HOST_TEMP_CRITICAL_C", 82.0))
    event_loop_lag_reduced_ms: float = field(default_factory=lambda: _float("SOMA_EVENT_LOOP_LAG_REDUCED_MS", 250.0))
    event_loop_lag_critical_ms: float = field(default_factory=lambda: _float("SOMA_EVENT_LOOP_LAG_CRITICAL_MS", 1000.0))
    tick_duration_reduced_ms: float = field(default_factory=lambda: _float("SOMA_TICK_DURATION_REDUCED_MS", 150.0))
    tick_duration_critical_ms: float = field(default_factory=lambda: _float("SOMA_TICK_DURATION_CRITICAL_MS", 500.0))
    resource_recovery_stable_sec: float = field(default_factory=lambda: _float("SOMA_RESOURCE_RECOVERY_STABLE_SEC", 120.0))
    resource_history_interval_sec: float = field(default_factory=lambda: _float("SOMA_RESOURCE_HISTORY_INTERVAL_SEC", 300.0))
    resource_write_state_interval_sec: float = field(default_factory=lambda: _float("SOMA_WRITE_STATE_INTERVAL_SEC", 30.0))
    resource_max_state_bytes: int = field(default_factory=lambda: int(_float("SOMA_MAX_STATE_BYTES", 65536.0)))

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
    bios_interval_sec_normal: float = field(default_factory=lambda: _float("SOMA_BIOS_INTERVAL_SEC_NORMAL", 600.0))
    bios_interval_sec_reduced: float = field(default_factory=lambda: _float("SOMA_BIOS_INTERVAL_SEC_REDUCED", 1800.0))
    bios_interval_sec_critical: float = field(default_factory=lambda: _float("SOMA_BIOS_INTERVAL_SEC_CRITICAL", 3600.0))
    bios_interval_sec_recovery: float = field(default_factory=lambda: _float("SOMA_BIOS_INTERVAL_SEC_RECOVERY", 3600.0))
    bios_max_llm_calls_per_hour_normal: int = field(default_factory=lambda: int(_float("SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_NORMAL", 4.0)))
    bios_max_llm_calls_per_hour_reduced: int = field(default_factory=lambda: int(_float("SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_REDUCED", 1.0)))
    bios_max_llm_calls_per_hour_critical: int = field(default_factory=lambda: int(_float("SOMA_BIOS_MAX_LLM_CALLS_PER_HOUR_CRITICAL", 0.0)))
    bios_yield_when_user_active: bool = field(default_factory=lambda: _bool("SOMA_BIOS_YIELD_WHEN_USER_ACTIVE", True))
    user_active_window_sec: float = field(default_factory=lambda: _float("SOMA_USER_ACTIVE_WINDOW_SEC", 120.0))

    # ── Phase 9: metabolic growth ────────────────────────────────────────────
    metabolic_engine: bool = field(default_factory=lambda: _bool("SOMA_METABOLIC_ENGINE", True))
    metabolic_window_cycles: int = field(default_factory=lambda: int(_float("SOMA_METABOLIC_WINDOW_CYCLES", 100.0)))
    metabolic_bios_window: int = field(default_factory=lambda: int(_float("SOMA_METABOLIC_BIOS_WINDOW", 10.0)))
    growth_stability_threshold: float = field(default_factory=lambda: _float("SOMA_GROWTH_STABILITY_THRESHOLD", 0.65))
    growth_max_stress: float = field(default_factory=lambda: _float("SOMA_GROWTH_MAX_STRESS", 0.35))
    min_self_integrity: float = field(default_factory=lambda: _float("SOMA_MIN_SELF_INTEGRITY", 0.75))
    metabolic_vector_history_max: int = field(default_factory=lambda: int(_float("SOMA_METABOLIC_VECTOR_HISTORY_MAX", 5000.0)))
    metabolic_history_interval_sec: float = field(default_factory=lambda: _float("SOMA_METABOLIC_HISTORY_INTERVAL_SEC", 60.0))

    # ── Phase 9: growth / recovery loop ──────────────────────────────────────
    growth_loop: bool = field(default_factory=lambda: _bool("SOMA_GROWTH_LOOP", True))
    growth_llm_interval_sec: float = field(default_factory=lambda: _float("SOMA_GROWTH_LLM_INTERVAL_SEC", 300.0))
    growth_min_stable_bios_cycles: int = field(default_factory=lambda: int(_float("SOMA_GROWTH_MIN_STABLE_BIOS_CYCLES", 3.0)))
    growth_max_tasks_per_day: int = field(default_factory=lambda: int(_float("SOMA_GROWTH_MAX_TASKS_PER_DAY", 24.0)))
    growth_require_tests: bool = field(default_factory=lambda: _bool("SOMA_GROWTH_REQUIRE_TESTS", True))
    growth_allow_package_user_install: bool = field(default_factory=lambda: _bool("SOMA_GROWTH_ALLOW_PACKAGE_USER_INSTALL", True))
    growth_allow_system_package_install: bool = field(default_factory=lambda: _bool("SOMA_GROWTH_ALLOW_SYSTEM_PACKAGE_INSTALL", False))
    recovery_loop: bool = field(default_factory=lambda: _bool("SOMA_RECOVERY_LOOP", True))
    recovery_check_interval_sec: float = field(default_factory=lambda: _float("SOMA_RECOVERY_CHECK_INTERVAL_SEC", 60.0))
    recovery_rollback_on_mutation_stress: bool = field(default_factory=lambda: _bool("SOMA_RECOVERY_ROLLBACK_ON_MUTATION_STRESS", True))
    recovery_require_stable_cycles: int = field(default_factory=lambda: int(_float("SOMA_RECOVERY_REQUIRE_STABLE_CYCLES", 5.0)))

    # ── Phase 9: reward / internal loop / vector interpreter ─────────────────
    reward_model: bool = field(default_factory=lambda: _bool("SOMA_REWARD_MODEL", True))
    reward_history_max: int = field(default_factory=lambda: int(_float("SOMA_REWARD_HISTORY_MAX", 1000.0)))
    reward_min_for_mutation_keep: float = field(default_factory=lambda: _float("SOMA_REWARD_MIN_FOR_MUTATION_KEEP", 0.15))
    reproduction_local_only: bool = field(default_factory=lambda: _bool("SOMA_REPRODUCTION_LOCAL_ONLY", True))
    reproduction_root: str = field(default_factory=lambda: _str("SOMA_REPRODUCTION_ROOT", "/home/funboy/latent-somatic-mutants"))
    reproduction_max_children: int = field(default_factory=lambda: int(_float("SOMA_REPRODUCTION_MAX_CHILDREN", 10.0)))
    reproduction_no_network_spread: bool = field(default_factory=lambda: _bool("SOMA_REPRODUCTION_NO_NETWORK_SPREAD", True))
    reproduction_no_secret_copy: bool = field(default_factory=lambda: _bool("SOMA_REPRODUCTION_NO_SECRET_COPY", True))
    reproduction_require_operator_for_migration: bool = field(default_factory=lambda: _bool("SOMA_REPRODUCTION_REQUIRE_OPERATOR_FOR_MIGRATION", True))
    internal_loop: bool = field(default_factory=lambda: _bool("SOMA_INTERNAL_LOOP", True))
    internal_decision_history_max: int = field(default_factory=lambda: int(_float("SOMA_INTERNAL_DECISION_HISTORY_MAX", 1000.0)))
    internal_llm_json_required: bool = field(default_factory=lambda: _bool("SOMA_INTERNAL_LLM_JSON_REQUIRED", True))
    internal_invalid_json_penalty: float = field(default_factory=lambda: _float("SOMA_INTERNAL_INVALID_JSON_PENALTY", -0.05))
    internal_llm_max_prompt_chars: int = field(default_factory=lambda: int(_float("SOMA_INTERNAL_LLM_MAX_PROMPT_CHARS", 6000.0)))
    internal_llm_max_response_chars: int = field(default_factory=lambda: int(_float("SOMA_INTERNAL_LLM_MAX_RESPONSE_CHARS", 4000.0)))
    vector_interpreter: bool = field(default_factory=lambda: _bool("SOMA_VECTOR_INTERPRETER", True))
    vector_baseline_min_samples: int = field(default_factory=lambda: int(_float("SOMA_VECTOR_BASELINE_MIN_SAMPLES", 100.0)))
    vector_drift_threshold: float = field(default_factory=lambda: _float("SOMA_VECTOR_DRIFT_THRESHOLD", 0.35))
    vector_cpp_mismatch_threshold: float = field(default_factory=lambda: _float("SOMA_VECTOR_CPP_MISMATCH_THRESHOLD", 0.20))
    projector_hz_normal: float = field(default_factory=lambda: _float("SOMA_PROJECTOR_HZ_NORMAL", 1.0))
    projector_hz_reduced: float = field(default_factory=lambda: _float("SOMA_PROJECTOR_HZ_REDUCED", 0.2))
    projector_hz_critical: float = field(default_factory=lambda: _float("SOMA_PROJECTOR_HZ_CRITICAL", 0.05))
    projector_hz_recovery: float = field(default_factory=lambda: _float("SOMA_PROJECTOR_HZ_RECOVERY", 0.02))
    vector_interpreter_hz: float = field(default_factory=lambda: _float("SOMA_VECTOR_INTERPRETER_HZ", 0.2))
    cpp_projection_hz: float = field(default_factory=lambda: _float("SOMA_CPP_PROJECTION_HZ", 0.02))
    cpp_smoke_test_interval_sec: float = field(default_factory=lambda: _float("SOMA_CPP_SMOKE_TEST_INTERVAL_SEC", 3600.0))

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

    # ── state compaction ──────────────────────────────────────────────────────
    auto_compact_mind_state: bool = field(default_factory=lambda: _bool("SOMA_AUTO_COMPACT_MIND_STATE", True))
    mind_state_max_bytes: int = field(default_factory=lambda: int(_float("SOMA_MIND_STATE_MAX_BYTES", 262144.0)))

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
