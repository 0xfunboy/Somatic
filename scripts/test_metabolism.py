#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.metabolism import MetabolicEngine


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def snapshot(ts: float, *, thermal: float = 0.15, energy: float = 0.12, instability: float = 0.08, memory_pct: float = 38.0, disk_used: float = 42.0, source_quality: float = 0.95) -> dict:
    return {
        "timestamp": ts,
        "provider": {"is_real": True, "name": "linux", "source_quality": source_quality},
        "system": {
            "cpu_percent": 14.0,
            "cpu_count_logical": 8,
            "cpu_temp": 47.0,
            "cpu_power_w": 24.0,
            "memory_percent": memory_pct,
            "memory_total_gb": 32.0,
            "disk_used_percent": disk_used,
            "disk_busy_percent": 12.0,
            "disk_total_gb": 1000.0,
            "net_up_mbps": 0.5,
            "net_down_mbps": 1.2,
        },
        "derived": {"thermal_stress": thermal, "energy_stress": energy, "instability": instability},
        "llm": {"available": True, "mode": "deepseek"},
    }


def main() -> int:
    failures = 0
    vector_state = {"vector_stability": 0.95, "vector_drift": 0.05, "vector_anomaly": 0.02}
    strong_baselines = {
        "keys": {
            "idle_cpu_percent": {"confidence": 0.8},
            "cpu_temp_c": {"confidence": 0.78},
            "disk_temp_c": {"confidence": 0.76},
            "ram_idle_percent": {"confidence": 0.82},
        }
    }
    context = {
        "reward": {"rolling_score": 0.15, "trend": 0.12},
        "mutation": {"sandbox_root_exists": True, "last_tests_ok": True},
        "cpp_bridge": {"enabled": True, "smoke_ok": True},
        "command_agency": {"successful": 6, "failed": 0, "regression_ok": True},
        "capabilities": {"survival_policy": True},
        "growth": {"missing_requirements": ["mutation_sandbox_ready"]},
        "vector_state": vector_state,
        "baselines": strong_baselines,
    }
    with tempfile.TemporaryDirectory() as td:
        engine = MetabolicEngine(data_root=Path(td), window_cycles=100)
        state = {}
        for i in range(100):
            state = engine.update(snapshot(float(i)), context)
        failures += check("stable input for 100 cycles allows growth", state.get("growth_allowed") is True and state.get("mode") == "grow", str(state))

        hot = engine.update(snapshot(101.0, thermal=0.92), context)
        failures += check("high temperature enters recovery", hot.get("recovery_required") is True and hot.get("mode") == "recover", str(hot))

        mem = engine.update(snapshot(102.0, thermal=0.1, memory_pct=97.0), context)
        failures += check("memory pressure enters recovery", mem.get("recovery_required") is True and mem.get("mode") == "recover", str(mem))

        lowq = engine.update(snapshot(103.0, source_quality=0.2), {**context, "baselines": {"keys": {}}})
        failures += check(
            "low source quality with weak baselines blocks growth",
            lowq.get("mode") in {"observe", "stabilize"} and lowq.get("growth_allowed") is False and lowq.get("sensor_confidence_calibrated", 1.0) < 0.55,
            str(lowq),
        )

        calibrated = {}
        for i in range(104, 110):
            calibrated = engine.update(snapshot(float(i), source_quality=0.33), context)
        failures += check(
            "stable baselines can calibrate partial linux telemetry above threshold",
            calibrated.get("sensor_confidence_calibrated", 0.0) > 0.55 and calibrated.get("mode") in {"observe", "grow"},
            str(calibrated),
        )
        failures += check("raw source quality remains visible", calibrated.get("raw_source_quality_low") is True, str(calibrated))
        failures += check("missing sensor classes are explicit", isinstance(calibrated.get("missing_sensor_classes"), list), str(calibrated))

        clean = {}
        for i in range(110, 114):
            clean = engine.update(snapshot(float(i)), context)
        failures += check("stable vector and tests ok support grow mode", clean.get("mode") == "grow", str(clean))
    return failures


if __name__ == "__main__":
    sys.exit(main())
