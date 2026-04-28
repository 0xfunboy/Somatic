#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.metabolism import MetabolicEngine
from soma_core.vector_interpreter import VectorInterpreter


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def make_snapshot(norm: float, mean: float, std: float, top_dims: list[int], *, cpp_smoke: bool = False) -> dict:
    return {
        "timestamp": 1.0,
        "projector": {"norm": norm, "top_dims": top_dims, "top_vals": [0.5] * len(top_dims)},
        "tensor": {"mean": mean, "std": std, "top_dims": top_dims, "top_vals": [0.5] * len(top_dims)},
        "cpp_bridge_status": {"smoke_ok": cpp_smoke},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        interp = VectorInterpreter(data_root=Path(td), baseline_min_samples=3)
        stable = {}
        for _ in range(5):
            stable = interp.interpret(make_snapshot(1.2, 0.02, 0.12, [1, 2, 3, 4]))
        failures += check("stable vector creates high stability", stable["vector_stability"] > 0.8, str(stable))

        drift = interp.interpret(make_snapshot(4.8, 1.6, 1.1, [90, 91, 92, 93]))
        failures += check("drift creates anomaly", drift["vector_anomaly"] >= 0.35, str(drift))

        mismatch = interp.interpret(make_snapshot(1.2, 0.02, 0.12, [1, 2, 3, 4]), cpp_projection={"norm": 7.5, "top_dims": [80, 81, 82]})
        failures += check("python cpp mismatch lowers consistency", mismatch["cpp_consistency"] is not None and mismatch["cpp_consistency"] < 0.5, str(mismatch))

        smoke = interp.interpret(make_snapshot(1.2, 0.02, 0.12, [1, 2, 3, 4], cpp_smoke=True))
        failures += check("cpp smoke ok yields neutral positive consistency", smoke["cpp_consistency"] == 0.6, str(smoke))

    with tempfile.TemporaryDirectory() as td_bad, tempfile.TemporaryDirectory() as td_good:
        engine_bad = MetabolicEngine(data_root=Path(td_bad))
        engine_good = MetabolicEngine(data_root=Path(td_good))
        base_snapshot = {
            "timestamp": 1.0,
            "provider": {"is_real": True, "name": "linux", "source_quality": 0.95},
            "system": {"memory_percent": 42.0, "disk_used_percent": 38.0, "disk_busy_percent": 10.0},
            "derived": {"thermal_stress": 0.12, "energy_stress": 0.1, "instability": 0.08},
            "llm": {"available": True, "mode": "deepseek"},
        }
        common = {
            "reward": {"rolling_score": 0.1, "trend": 0.05},
            "mutation": {"sandbox_root_exists": True, "last_tests_ok": True},
            "command_agency": {"successful": 5, "failed": 0, "regression_ok": True},
            "capabilities": {"survival_policy": True},
        }
        bad = engine_bad.update(base_snapshot, {**common, "cpp_bridge": {"enabled": True, "smoke_ok": True}, "vector_state": {"vector_stability": 0.8, "vector_drift": 0.4, "vector_anomaly": 0.4, "cpp_consistency": 0.2}})
        good = engine_good.update(base_snapshot, {**common, "cpp_bridge": {"enabled": True, "smoke_ok": True}, "vector_state": {"vector_stability": 0.95, "vector_drift": 0.05, "vector_anomaly": 0.02, "cpp_consistency": 0.9}})
        failures += check("cpp smoke ok and consistency increase self integrity", good["self_integrity"] > bad["self_integrity"], f"good={good['self_integrity']} bad={bad['self_integrity']}")
    return failures


if __name__ == "__main__":
    sys.exit(main())

