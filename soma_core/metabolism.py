from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from soma_core.config import CFG


_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _clamp01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))


def _avg(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


_SENSOR_CLASS_FIELDS: dict[str, tuple[str, ...]] = {
    "compute": ("cpu_percent", "cpu_count_logical", "cpu_freq_mhz", "load_1"),
    "memory": ("memory_percent", "memory_total_gb", "swap_percent"),
    "storage": ("disk_used_percent", "disk_busy_percent", "disk_total_gb", "disk_read_mb_s", "disk_write_mb_s"),
    "network": ("net_mbps", "net_up_mbps", "net_down_mbps"),
    "thermal": ("cpu_temp", "disk_temp", "thermal_sensors_c"),
    "power": ("cpu_power_w", "ac_online", "battery_percent"),
    "cooling": ("fan_rpm", "fan_sensors_rpm"),
    "gpu": ("gpu_temp", "gpu_power_w", "gpu_util_percent", "gpu_memory_percent", "gpu_memory_total_mb"),
}


def _field_available(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _sensor_inventory(system: dict[str, Any]) -> tuple[int, list[str]]:
    available: list[str] = []
    missing: list[str] = []
    for sensor_class, fields in _SENSOR_CLASS_FIELDS.items():
        if any(_field_available(system.get(field)) for field in fields):
            available.append(sensor_class)
        else:
            missing.append(sensor_class)
    return len(available), missing


class MetabolicEngine:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        window_cycles: int | None = None,
        bios_window: int | None = None,
        growth_stability_threshold: float | None = None,
        growth_max_stress: float | None = None,
        min_self_integrity: float | None = None,
        history_max: int | None = None,
        history_interval_sec: float | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.enabled = CFG.metabolic_engine if enabled is None else bool(enabled)
        self._window_cycles = max(10, int(window_cycles or CFG.metabolic_window_cycles))
        self._bios_window = max(1, int(bios_window or CFG.metabolic_bios_window))
        self._growth_threshold = float(growth_stability_threshold or CFG.growth_stability_threshold)
        self._max_stress = float(growth_max_stress or CFG.growth_max_stress)
        self._min_self_integrity = float(min_self_integrity or CFG.min_self_integrity)
        self._history_max = max(100, int(history_max or CFG.metabolic_vector_history_max))
        self._history_interval_sec = max(1.0, float(history_interval_sec or CFG.metabolic_history_interval_sec))
        self._data_root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
        self._state_path = self._data_root / "metabolic_state.json"
        self._history_path = self._data_root / "metabolic_history.jsonl"
        self._state = _load_json(
            self._state_path,
            {
                "timestamp": 0.0,
                "stability": 0.0,
                "stress": 0.0,
                "energy": 0.0,
                "thermal_margin": 0.0,
                "memory_margin": 0.0,
                "disk_margin": 0.0,
                "sensor_confidence": 0.0,
                "raw_source_quality": 0.0,
                "available_sensor_count": 0,
                "available_sensor_ratio": 0.0,
                "stable_baseline_confidence": 0.0,
                "baseline_confidence": 0.0,
                "sensor_confidence_calibrated": 0.0,
                "raw_source_quality_low": True,
                "calibrated_sensor_confidence_ok": False,
                "calibrated_sensor_confidence_low": True,
                "missing_sensor_classes": [],
                "llm_confidence": 0.0,
                "self_integrity": 0.0,
                "vector_stability": 0.0,
                "vector_drift": 0.0,
                "growth_pressure": 0.0,
                "reproduction_pressure": 0.0,
                "recovery_pressure": 0.0,
                "host_pressure": 0.0,
                "resource_mode": "normal",
                "resource_throttle": False,
                "growth_suspended_by_resource": False,
                "mutation_suspended_by_resource": False,
                "growth_allowed": False,
                "recovery_required": False,
                "stable_cycles": 0,
                "mode": "observe",
                "reasons": [],
                "sensor_confidence_reasons": {},
                "last_mutation_effect": {},
                "window": {"avg_stability": 0.0, "avg_stress": 0.0, "stable_cycles": 0, "samples": 0},
            },
        )
        self._window: list[dict[str, Any]] = []
        self._last_history_write_at = float(self._state.get("_last_history_write_at", 0.0) or 0.0)

    def update(self, snapshot: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        if not self.enabled:
            self._state.update({
                "enabled": False,
                "mode": "observe",
                "growth_allowed": False,
                "recovery_required": False,
                "reasons": ["metabolic_engine_disabled"],
            })
            _save_json(self._state_path, self._state)
            return self.current()

        system = snapshot.get("system", {}) if isinstance(snapshot, dict) else {}
        derived = snapshot.get("derived", {}) if isinstance(snapshot, dict) else {}
        provider = snapshot.get("provider", {}) if isinstance(snapshot, dict) else {}
        vector_state = context.get("vector_state") or snapshot.get("vector_state", {}) or {}
        reward_state = context.get("reward") or snapshot.get("reward", {}) or {}
        growth_state = context.get("growth") or snapshot.get("_growth", {}) or {}
        mutation_status = context.get("mutation") or snapshot.get("mutation_status", {}) or {}
        cpp_status = context.get("cpp_bridge") or snapshot.get("cpp_bridge_status", {}) or {}
        command_agency = context.get("command_agency") or snapshot.get("command_agency", {}) or {}
        capabilities = context.get("capabilities") or {}
        baselines = context.get("baselines") or snapshot.get("baselines", {}) or {}
        resource_state = context.get("resource") or snapshot.get("resource", {}) or {}

        thermal_stress = _clamp01(derived.get("thermal_stress"))
        energy_stress = _clamp01(derived.get("energy_stress"))
        instability = _clamp01(derived.get("instability"))
        memory_ratio = _clamp01((system.get("memory_percent") or 0.0) / 100.0)
        disk_used_ratio = _clamp01((system.get("disk_used_percent") or 0.0) / 100.0)
        disk_busy_ratio = _clamp01((system.get("disk_busy_percent") or 0.0) / 100.0)
        memory_pressure = _clamp01((memory_ratio - 0.75) / 0.25)
        disk_pressure = _clamp01(max((disk_used_ratio - 0.85) / 0.15, (disk_busy_ratio - 0.75) / 0.25))
        vector_anomaly = _clamp01(vector_state.get("vector_anomaly"))
        vector_drift = _clamp01(vector_state.get("vector_drift"))
        vector_stability = _clamp01(vector_state.get("vector_stability", 0.5 if vector_state else 0.0))
        raw_source_quality = _clamp01(provider.get("source_quality", system.get("source_quality", 0.0)))
        available_sensor_count, missing_sensor_classes = _sensor_inventory(system)
        available_sensor_ratio = available_sensor_count / max(1, len(_SENSOR_CLASS_FIELDS))
        baseline_keys = (baselines.get("keys") or {}) if isinstance(baselines, dict) else {}
        baseline_candidates = [
            float((baseline_keys.get(key) or {}).get("confidence", 0.0) or 0.0)
            for key in ("idle_cpu_percent", "cpu_temp_c", "disk_temp_c", "ram_idle_percent", "source_quality")
        ]
        stable_baseline_confidence = _clamp01(_avg([value for value in baseline_candidates if value > 0.0]))
        sensor_confidence_calibrated = max(
            raw_source_quality,
            _clamp01(
                (raw_source_quality * 0.20)
                + (available_sensor_ratio * 0.35)
                + (stable_baseline_confidence * 0.45)
            ),
        )
        sensor_confidence = sensor_confidence_calibrated
        raw_source_quality_low = raw_source_quality < 0.55
        calibrated_sensor_confidence_ok = sensor_confidence_calibrated >= 0.55
        calibrated_sensor_confidence_low = not calibrated_sensor_confidence_ok
        sensor_confidence_reasons = {
            "raw_source_quality_low": raw_source_quality_low,
            "calibrated_sensor_confidence_ok": calibrated_sensor_confidence_ok,
            "calibrated_sensor_confidence_low": calibrated_sensor_confidence_low,
            "missing_sensor_classes": missing_sensor_classes,
            "baseline_confidence": round(stable_baseline_confidence, 4),
        }

        llm_mode = str((snapshot.get("llm") or {}).get("mode") or context.get("llm_mode") or "").lower()
        llm_available = bool((snapshot.get("llm") or {}).get("available")) or bool(context.get("llm_available"))
        if llm_available:
            llm_confidence = 1.0
        elif llm_mode in {"deepseek", "openai", "openai_compatible", "gemrouter"}:
            llm_confidence = 0.45
        elif llm_mode == "off":
            llm_confidence = 0.35
        else:
            llm_confidence = 0.25

        thermal_margin = round(1.0 - thermal_stress, 4)
        memory_margin = round(1.0 - memory_ratio, 4)
        disk_margin = round(1.0 - disk_used_ratio, 4)

        cpp_factor = 0.8
        if cpp_status.get("enabled"):
            if cpp_status.get("smoke_ok"):
                cpp_factor = 1.0
            elif cpp_status.get("status") in {"missing", "model_required"}:
                cpp_factor = 0.75
            else:
                cpp_factor = 0.45

        mutation_factor = 0.9
        if mutation_status.get("recommendation") == "reject":
            mutation_factor = 0.55
        elif mutation_status.get("last_tests_ok") is False and mutation_status.get("sandbox_count", 0):
            mutation_factor = 0.45
        elif mutation_status.get("last_tests_ok") is True:
            mutation_factor = 1.0

        policy_factor = 1.0 if capabilities.get("survival_policy", True) else 0.4
        command_factor = 0.75
        if command_agency:
            successful = int(command_agency.get("successful", 0) or 0)
            failed = int(command_agency.get("failed", 0) or 0)
            total = successful + failed
            ratio = (successful / total) if total else 0.6
            command_factor = max(0.25, min(1.0, ratio))
            if command_agency.get("regression_ok"):
                command_factor = min(1.0, command_factor + 0.15)

        cpp_consistency = vector_state.get("cpp_consistency")
        if isinstance(cpp_consistency, (int, float)):
            vector_integrity = 0.55 + (_clamp01(cpp_consistency) * 0.45)
        else:
            vector_integrity = 0.75 if cpp_status.get("smoke_ok") else 0.65

        self_integrity = round(
            _avg([policy_factor, cpp_factor, mutation_factor, command_factor, vector_integrity]),
            4,
        )

        reward_trend = float(reward_state.get("trend", reward_state.get("rolling_score", 0.0)) or 0.0)
        reward_support = _clamp01(0.5 + reward_trend)
        host_pressure = _clamp01(resource_state.get("host_pressure", 0.0))
        resource_mode = str(resource_state.get("mode") or "normal").lower()
        resource_throttle = resource_mode != "normal" or host_pressure >= 0.55
        failed_commands = int(command_agency.get("failed", 0) or 0)
        successful_commands = int(command_agency.get("successful", 0) or 0)
        total_commands = max(1, failed_commands + successful_commands)
        failure_ratio = failed_commands / total_commands
        recent_failure_pressure = _clamp01(max(failure_ratio, max(0.0, -reward_trend)))
        stress = round(max(thermal_stress, energy_stress, instability, memory_pressure, disk_pressure, vector_anomaly, recent_failure_pressure, host_pressure), 4)

        stability = round(
            _avg([
                thermal_margin,
                memory_margin,
                disk_margin,
                sensor_confidence,
                llm_confidence,
                self_integrity,
                vector_stability,
            ]),
            4,
        )
        competence_gap = min(1.0, len(growth_state.get("missing_requirements", []) or []) / 8.0)
        growth_pressure = round(_clamp01(stability * max(0.25, 0.25 + competence_gap) * max(0.25, reward_support) * max(0.1, 1.0 - host_pressure)), 4)
        mutation_readiness = 1.0 if mutation_status.get("sandbox_root_exists") else 0.4
        reproduction_pressure = round(_clamp01(growth_pressure * self_integrity * mutation_readiness), 4)
        recovery_pressure = round(_clamp01(max(stress, vector_anomaly, host_pressure) * 0.7 + recent_failure_pressure * 0.3), 4)
        growth_suspended_by_resource = resource_mode in {"reduced", "critical", "recovery"} or host_pressure >= 0.6
        mutation_suspended_by_resource = resource_mode != "normal"

        stable_now = (
            stability >= self._growth_threshold
            and stress <= self._max_stress
            and self_integrity >= self._min_self_integrity
            and sensor_confidence_calibrated >= 0.55
            and vector_anomaly < CFG.vector_drift_threshold
        )
        stable_cycles = int(self._state.get("stable_cycles", 0) or 0)
        stable_cycles = stable_cycles + 1 if stable_now else 0

        recovery_required, recovery_reasons = self._compute_recovery_required(
            stress=stress,
            vector_anomaly=vector_anomaly,
            self_integrity=self_integrity,
            mutation_status=mutation_status,
            host_pressure=host_pressure,
            resource_mode=resource_mode,
        )
        growth_allowed, growth_blockers = self._compute_growth_allowed(
            stability=stability,
            stress=stress,
            self_integrity=self_integrity,
            sensor_confidence=sensor_confidence_calibrated,
            vector_anomaly=vector_anomaly,
            stable_cycles=stable_cycles,
            recovery_required=recovery_required,
            reward_state=reward_state,
            resource_mode=resource_mode,
            growth_suspended_by_resource=growth_suspended_by_resource,
        )

        mode_reasons: list[str] = []
        if recovery_required:
            mode = "recover"
            mode_reasons = recovery_reasons
        elif growth_suspended_by_resource and resource_mode in {"critical", "recovery"}:
            mode = "recover"
            mode_reasons = ["host_resource_pressure"]
        elif growth_suspended_by_resource:
            mode = "stabilize"
            mode_reasons = ["host_resource_pressure"]
        elif sensor_confidence_calibrated < 0.55:
            mode = "stabilize" if stress > 0.2 or stable_baseline_confidence < 0.55 else "observe"
            mode_reasons = ["calibrated_sensor_confidence_low"]
        elif stability < self._growth_threshold:
            mode = "stabilize"
            mode_reasons = growth_blockers or ["stability_below_threshold"]
        elif growth_allowed and mutation_status.get("candidate_available") and mutation_status.get("last_tests_ok"):
            mode = "mutate"
            mode_reasons = ["growth_allowed", "mutation_candidate_ready"]
        elif growth_allowed and mutation_status.get("recommendation") in {"keep_for_review", "candidate_for_migration"}:
            mode = "evaluate"
            mode_reasons = ["mutation_under_review"]
        elif growth_allowed and reproduction_pressure >= 0.72:
            mode = "reproduce"
            mode_reasons = ["growth_allowed", "reproduction_pressure_high"]
        elif growth_allowed:
            mode = "grow"
            mode_reasons = ["growth_allowed", "stable_metabolism"]
        else:
            mode = "observe"
            mode_reasons = growth_blockers or ["observe_until_more_evidence"]

        previous_mode = str(self._state.get("mode") or "")
        record = {
            "timestamp": float(snapshot.get("timestamp") or time.time()),
            "stability": stability,
            "stress": stress,
            "energy": round(1.0 - energy_stress, 4),
            "thermal_margin": thermal_margin,
            "memory_margin": memory_margin,
            "disk_margin": disk_margin,
            "sensor_confidence": round(sensor_confidence, 4),
            "raw_source_quality": round(raw_source_quality, 4),
            "available_sensor_count": int(available_sensor_count),
            "available_sensor_ratio": round(available_sensor_ratio, 4),
            "stable_baseline_confidence": round(stable_baseline_confidence, 4),
            "baseline_confidence": round(stable_baseline_confidence, 4),
            "sensor_confidence_calibrated": round(sensor_confidence_calibrated, 4),
            "raw_source_quality_low": raw_source_quality_low,
            "calibrated_sensor_confidence_ok": calibrated_sensor_confidence_ok,
            "calibrated_sensor_confidence_low": calibrated_sensor_confidence_low,
            "missing_sensor_classes": missing_sensor_classes,
            "llm_confidence": round(llm_confidence, 4),
            "self_integrity": self_integrity,
            "vector_stability": round(vector_stability, 4),
            "vector_drift": round(vector_drift, 4),
            "growth_pressure": growth_pressure,
            "reproduction_pressure": reproduction_pressure,
            "recovery_pressure": recovery_pressure,
            "host_pressure": round(host_pressure, 4),
            "resource_mode": resource_mode,
            "resource_throttle": bool(resource_throttle),
            "growth_suspended_by_resource": bool(growth_suspended_by_resource),
            "mutation_suspended_by_resource": bool(mutation_suspended_by_resource),
            "growth_allowed": bool(growth_allowed),
            "recovery_required": bool(recovery_required),
            "stable_cycles": stable_cycles,
            "mode": mode,
            "reasons": mode_reasons,
            "sensor_confidence_reasons": sensor_confidence_reasons,
        }

        self._window.append(record)
        self._window = self._window[-self._window_cycles :]
        record["window"] = self.window_summary()
        record["last_mutation_effect"] = dict(self._state.get("last_mutation_effect", {}) or {})
        self._state.update(record)
        self._state["_last_history_write_at"] = float(self._last_history_write_at)
        self._persist_if_needed(record, previous_mode=previous_mode)
        return self.current()

    def current(self) -> dict[str, Any]:
        state = dict(self._state)
        state.pop("_last_history_write_at", None)
        return state

    def window_summary(self) -> dict[str, Any]:
        stabilities = [float(item.get("stability", 0.0)) for item in self._window[-self._window_cycles :]]
        stresses = [float(item.get("stress", 0.0)) for item in self._window[-self._window_cycles :]]
        modes = [str(item.get("mode") or "") for item in self._window[-self._bios_window :]]
        stable_cycles = sum(
            1
            for item in self._window[-self._window_cycles :]
            if float(item.get("stability", 0.0)) >= self._growth_threshold and float(item.get("stress", 1.0)) <= self._max_stress
        )
        return {
            "avg_stability": round(_avg(stabilities), 4),
            "avg_stress": round(_avg(stresses), 4),
            "stable_cycles": int(stable_cycles),
            "samples": len(self._window),
            "recent_modes": modes[-self._bios_window :],
        }

    def growth_allowed(self) -> tuple[bool, list[str]]:
        state = self.current()
        if state.get("growth_allowed"):
            return True, []
        reasons = list(state.get("reasons") or [])
        return False, reasons or ["growth_not_allowed"]

    def recovery_required(self) -> tuple[bool, list[str]]:
        state = self.current()
        if state.get("recovery_required"):
            return True, list(state.get("reasons") or ["recovery_required"])
        return False, []

    def mode(self) -> str:
        return str(self._state.get("mode") or "observe")

    def record_mutation_effect(self, before: dict[str, Any], after: dict[str, Any], mutation_id: str) -> dict[str, Any]:
        before_stress = float(before.get("stress", 0.0) or 0.0)
        after_stress = float(after.get("stress", 0.0) or 0.0)
        before_stability = float(before.get("stability", 0.0) or 0.0)
        after_stability = float(after.get("stability", 0.0) or 0.0)
        effect = {
            "mutation_id": mutation_id,
            "timestamp": time.time(),
            "stress_delta": round(after_stress - before_stress, 4),
            "stability_delta": round(after_stability - before_stability, 4),
            "regressed": (after_stress - before_stress) > 0.08 or (after_stability - before_stability) < -0.08,
        }
        self._state["last_mutation_effect"] = effect
        self._persist_if_needed(self.current(), force=True)
        return effect

    def _compute_growth_allowed(
        self,
        *,
        stability: float,
        stress: float,
        self_integrity: float,
        sensor_confidence: float,
        vector_anomaly: float,
        stable_cycles: int,
        recovery_required: bool,
        reward_state: dict[str, Any],
        resource_mode: str,
        growth_suspended_by_resource: bool,
    ) -> tuple[bool, list[str]]:
        blockers: list[str] = []
        if resource_mode in {"critical", "recovery"}:
            blockers.append("host_resource_pressure")
        elif growth_suspended_by_resource:
            blockers.append("growth_suspended_by_resource")
        if recovery_required:
            blockers.append("recovery_required")
        if stability < self._growth_threshold:
            blockers.append("stability_below_threshold")
        if stress > self._max_stress:
            blockers.append("stress_above_max")
        if self_integrity < self._min_self_integrity:
            blockers.append("self_integrity_below_min")
        if sensor_confidence < 0.55:
            blockers.append("calibrated_sensor_confidence_low")
        if vector_anomaly >= CFG.vector_drift_threshold:
            blockers.append("vector_anomaly_high")
        if stable_cycles < CFG.growth_min_stable_bios_cycles:
            blockers.append("insufficient_stable_cycles")
        if float(reward_state.get("rolling_score", 0.0) or 0.0) < -0.25:
            blockers.append("reward_trend_negative")
        return not blockers, blockers

    def _compute_recovery_required(
        self,
        *,
        stress: float,
        vector_anomaly: float,
        self_integrity: float,
        mutation_status: dict[str, Any],
        host_pressure: float,
        resource_mode: str,
    ) -> tuple[bool, list[str]]:
        reasons: list[str] = []
        if resource_mode in {"critical", "recovery"} or host_pressure >= 0.75:
            reasons.append("host_resource_pressure")
        if stress > self._max_stress:
            reasons.append("stress_above_max")
        if vector_anomaly >= CFG.vector_drift_threshold:
            reasons.append("vector_anomaly_high")
        if self_integrity < self._min_self_integrity:
            reasons.append("self_integrity_low")
        if CFG.recovery_rollback_on_mutation_stress and mutation_status.get("recommendation") == "reject":
            reasons.append("mutation_regression_detected")
        return bool(reasons), reasons

    def _persist_if_needed(self, record: dict[str, Any], *, force: bool = False, previous_mode: str = "") -> None:
        now = time.time()
        mode_changed = str(record.get("mode")) != str(previous_mode or "")
        abnormal = bool(record.get("recovery_required")) or float(record.get("stress", 0.0)) > self._max_stress
        should_history = force or mode_changed or abnormal or (now - self._last_history_write_at) >= self._history_interval_sec
        serializable = dict(record)
        serializable["window"] = self.window_summary()
        if should_history:
            self._last_history_write_at = now
        _save_json(self._state_path, {**serializable, "_last_history_write_at": self._last_history_write_at})
        if not should_history:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(serializable, ensure_ascii=False) + "\n")
