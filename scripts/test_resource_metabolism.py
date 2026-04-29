#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.metabolism import MetabolicEngine
from soma_core.mutation import MutationSandbox
from soma_core.reward import RewardEngine


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def snapshot(ts: float) -> dict:
    return {
        "timestamp": ts,
        "provider": {"is_real": True, "name": "linux", "source_quality": 0.95},
        "system": {
            "cpu_percent": 14.0,
            "cpu_count_logical": 8,
            "cpu_temp": 45.0,
            "cpu_power_w": 22.0,
            "memory_percent": 36.0,
            "memory_total_gb": 32.0,
            "disk_used_percent": 41.0,
            "disk_busy_percent": 10.0,
            "disk_total_gb": 1000.0,
            "net_up_mbps": 0.4,
            "net_down_mbps": 1.0,
        },
        "derived": {"thermal_stress": 0.12, "energy_stress": 0.1, "instability": 0.05},
        "llm": {"available": True, "mode": "deepseek"},
    }


def base_context(resource: dict) -> dict:
    return {
        "reward": {"rolling_score": 0.18, "trend": 0.12},
        "mutation": {"sandbox_root_exists": True, "last_tests_ok": True},
        "cpp_bridge": {"enabled": True, "smoke_ok": True},
        "command_agency": {"successful": 8, "failed": 0, "regression_ok": True},
        "capabilities": {"survival_policy": True},
        "growth": {"missing_requirements": []},
        "vector_state": {"vector_stability": 0.95, "vector_drift": 0.04, "vector_anomaly": 0.02},
        "baselines": {
            "keys": {
                "idle_cpu_percent": {"confidence": 0.82},
                "cpu_temp_c": {"confidence": 0.79},
                "disk_temp_c": {"confidence": 0.78},
                "ram_idle_percent": {"confidence": 0.81},
            }
        },
        "resource": resource,
    }


def drive_engine(engine: MetabolicEngine, resource: dict, cycles: int = 5) -> dict:
    state = {}
    for idx in range(cycles):
        state = engine.update(snapshot(float(idx)), base_context(resource))
    return state


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        low_engine = MetabolicEngine(data_root=Path(td) / "low")
        high_engine = MetabolicEngine(data_root=Path(td) / "high")
        reward = RewardEngine(data_root=Path(td) / "reward")

        low_state = drive_engine(low_engine, {"mode": "normal", "host_pressure": 0.1})
        high_state = drive_engine(high_engine, {"mode": "critical", "host_pressure": 0.9})

        failures += check("host pressure increases metabolic stress", float(high_state.get("stress", 0.0)) > float(low_state.get("stress", 0.0)), f"low={low_state.get('stress')} high={high_state.get('stress')}")
        failures += check(
            "host pressure disables growth allowed",
            low_state.get("growth_allowed") is True and high_state.get("growth_allowed") is False and high_state.get("growth_suspended_by_resource") is True,
            f"low={low_state} high={high_state}",
        )

        sandbox = MutationSandbox(repo_root=Path(td) / "repo", mutation_root=Path(td) / "mutants", reward_engine=reward)
        sandbox._state_path = Path(td) / "mutation_state.json"
        can_mutate, blockers = sandbox.can_mutate(high_state, {"recovery_required": False}, reward.summary())
        failures += check("host pressure blocks mutation", can_mutate is False and "resource_mode_not_normal" in blockers, str(blockers))

        scored = reward.score_event({"kind": "growth_suspended_for_host_health"})
        recorded = reward.record_reward("growth_suspended_for_host_health", float(scored.get("value", 0.0) or 0.0), {"metabolic": high_state})
        failures += check("reward records growth suspended for host health", recorded.get("kind") == "growth_suspended_for_host_health" and recorded.get("value", 0.0) > 0.0, str(recorded))
    return failures


if __name__ == "__main__":
    sys.exit(main())
