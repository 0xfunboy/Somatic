from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

CORE_FIELDS = (
    "voltage",
    "current_ma",
    "temp_si",
    "temp_ml",
    "temp_mr",
    "ax",
    "ay",
    "az",
    "gx",
    "gy",
    "gz",
)

DEFAULT_SENSOR_STATE = {
    "voltage": 12.0,
    "current_ma": 250.0,
    "temp_si": 40.0,
    "temp_ml": 40.0,
    "temp_mr": 40.0,
    "ax": 0.0,
    "ay": 0.0,
    "az": -9.81,
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0,
}

DEFAULT_SYSTEM_STATE = {
    "cpu_percent": None,
    "cpu_count_logical": None,
    "cpu_count_physical": None,
    "cpu_freq_mhz": None,
    "cpu_per_core_percent": None,
    "memory_percent": None,
    "memory_used_gb": None,
    "memory_total_gb": None,
    "memory_available_gb": None,
    "swap_percent": None,
    "swap_used_gb": None,
    "swap_total_gb": None,
    "cpu_temp": None,
    "cpu_temp_sensors_c": None,
    "cpu_power_w": None,
    "gpu_temp": None,
    "gpu_power_w": None,
    "gpu_memory_used_mb": None,
    "gpu_memory_total_mb": None,
    "battery_percent": None,
    "ac_online": None,
    "fan_rpm": None,
    "fan_sensors_rpm": None,
    "source_quality": 0.0,
    "gpu_util_percent": None,
    "gpu_memory_percent": None,
    "battery_plugged": None,
    "load_1": None,
    "load_5": None,
    "load_15": None,
    "net_mbps": None,
    "net_up_mbps": None,
    "net_down_mbps": None,
    "disk_busy_percent": None,
    "disk_used_percent": None,
    "disk_total_gb": None,
    "disk_used_gb": None,
    "disk_free_gb": None,
    "disk_read_mb_s": None,
    "disk_write_mb_s": None,
    "disk_temp": None,
    "thermal_sensors_c": None,
    "source_quality_label": "unavailable",
}

SOURCE_QUALITY_ALIASES = {
    "synthetic": 0.1,
    "mock": 0.1,
    "mock_nominal": 0.12,
    "partial": 0.45,
    "external": 0.65,
    "real": 0.85,
    "endpoint_invalid": 0.05,
    "endpoint_missing": 0.0,
    "endpoint_unreachable": 0.05,
}


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp01(value: float | None) -> float:
    if value is None:
        return 0.0
    return clamp(float(value), 0.0, 1.0)


def safe_float(value: Any, default: float | None = None) -> float | None:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def rounded(value: float | None, digits: int = 3) -> float | None:
    if value is None:
        return None
    return round(float(value), digits)


def read_text(path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return None


def read_number(path, scale: float = 1.0) -> float | None:
    raw = read_text(path)
    if raw is None:
        return None
    try:
        return float(raw) / scale
    except ValueError:
        return None


def coerce_source_quality(value: Any, default: float = 0.0) -> float:
    if value is None:
        return clamp01(default)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in SOURCE_QUALITY_ALIASES:
            return SOURCE_QUALITY_ALIASES[lowered]
        for prefix, numeric in SOURCE_QUALITY_ALIASES.items():
            if lowered.startswith(prefix):
                return numeric
        try:
            return clamp01(float(lowered))
        except ValueError:
            return clamp01(default)
    try:
        return clamp01(float(value))
    except (TypeError, ValueError):
        return clamp01(default)


def quality_label(value: float) -> str:
    if value >= 0.8:
        return "real"
    if value >= 0.5:
        return "partial"
    if value >= 0.2:
        return "limited"
    if value > 0.0:
        return "synthetic"
    return "unavailable"


def _merged_core(core: dict[str, Any] | None) -> dict[str, float]:
    merged = dict(DEFAULT_SENSOR_STATE)
    if core:
        for field in CORE_FIELDS:
            merged[field] = safe_float(core.get(field), merged[field])
    return merged


def _merged_system(system: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(DEFAULT_SYSTEM_STATE)
    if system:
        for key, value in system.items():
            merged[key] = value
    return merged


def normalize_snapshot(
    payload: dict[str, Any] | None,
    *,
    provider: str,
    is_real: bool,
    scenario: str | None = None,
) -> dict[str, Any]:
    payload = payload or {}

    core_input = payload.get("core")
    if not isinstance(core_input, dict):
        core_input = {field: payload.get(field) for field in CORE_FIELDS}
    core = _merged_core(core_input)

    system = _merged_system(payload.get("system") if isinstance(payload.get("system"), dict) else None)
    source_quality = coerce_source_quality(
        payload.get("source_quality", system.get("source_quality")),
        default=0.0 if not is_real else 0.4,
    )
    system["source_quality"] = source_quality
    system["source_quality_label"] = str(system.get("source_quality_label") or quality_label(source_quality))

    raw = payload.get("raw")
    if not isinstance(raw, dict):
        raw = {}

    return {
        "provider": payload.get("provider", provider),
        "is_real": bool(payload.get("is_real", is_real)),
        "timestamp": float(payload.get("timestamp", time.time())),
        "core": core,
        "system": system,
        "raw": raw,
        "scenario": payload.get("scenario", scenario),
    }


class SensorProvider(ABC):
    name = "base"
    is_real = False

    @abstractmethod
    def read(self) -> dict[str, Any]:
        raise NotImplementedError

    def set_scenario(self, scenario: str) -> bool:
        return False

    def supports_scenarios(self) -> bool:
        return False
