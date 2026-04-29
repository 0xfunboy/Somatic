#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.introspection import IntrospectionRouter


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mind = root / "data" / "mind"
        write_json(mind / "internal_loop_state.json", {"last_prompt": "PROMPT_X", "last_parsed": {}, "last_parsed_fallback": {"mode": "observe", "action_type": "observe"}, "last_memory_updates": []})
        write_json(mind / "bios_state.json", {"last_task": "run_growth_cycle", "last_result": "ok", "last_internal_prompt": "PROMPT_X", "last_parsed_fallback": {"mode": "observe", "action_type": "observe"}, "last_evidence": {"command": "python3 scripts/test_answer_finalizer.py"}})
        write_json(mind / "metabolic_state.json", {"mode": "recover", "stability": 0.31, "stress": 0.82, "self_integrity": 0.74, "growth_allowed": False, "recovery_required": True, "reasons": ["stress_above_max"], "raw_source_quality": 0.33, "sensor_confidence_calibrated": 0.58, "baseline_confidence": 0.77, "missing_sensor_classes": ["gpu", "battery"]})
        write_json(mind / "reward_state.json", {"rolling_score": 0.12, "trend": 0.03, "last_kind": "test_pass", "last_value": 0.15, "count": 4})
        write_json(mind / "mutation_state.json", {"last_blockers": ["low_calibrated_sensor_confidence", "growth_not_allowed", "recovery_required"]})
        write_json(
            mind / "resource_state.json",
            {
                "mode": "reduced",
                "throttled_operations": ["full_payload_hz", "projector", "vector_interpreter", "mutation"],
                "sample": {"cpu_percent": 62.0, "memory_percent": 48.0, "event_loop_lag_ms": 90.0},
                "budget": {"tick_hz_max": 1.0, "ui_hz_max": 0.5},
            },
        )
        write_json(
            mind / "performance_state.json",
            {
                "operations": {"tick_total": {"avg_ms": 41.0, "latest_ms": 44.0, "max_ms": 56.0, "count": 7}},
                "slowest_operation": "tick_total",
                "slowest_operation_ms": 44.0,
                "event_loop_lag_ms": 90.0,
            },
        )
        router = IntrospectionRouter(repo_root=root)

        failures += check("last bios prompt reads internal state", "PROMPT_X" in router.execute("show your last BIOS internal prompt")["text"])
        failures += check("last internal json reads fallback state", '"mode": "observe"' in router.execute("show your last internal DeepSeek JSON")["text"])
        failures += check("metabolic vector reads metabolic state", '"mode": "recover"' in router.execute("what is your metabolic vector?")["text"])
        failures += check("reward trend reads reward state", '"rolling_score": 0.12' in router.execute("what is your reward trend?")["text"])
        failures += check("why not mutating reports calibrated blocker", "low_calibrated_sensor_confidence" in router.execute("why are you not mutating?")["text"])
        failures += check("resource mode introspection reads governor state", '"mode": "reduced"' in router.execute("what is your resource mode?")["text"])
        failures += check("throttling introspection explains slowed subsystems", "projector" in router.execute("what are you throttling?")["text"])
        failures += check("performance profile introspection reads persisted profile", "tick_total" in router.execute("show performance profile")["text"])
        failures += check("resource governor status introspection returns persisted status", '"tick_hz_max": 1.0' in router.execute("show resource governor status")["text"])

    with tempfile.TemporaryDirectory() as td:
        router = IntrospectionRouter(repo_root=Path(td))
        failures += check("missing state returns honest no-data", "No metabolic" in router.execute("what is your metabolic vector?")["text"])
    return failures


if __name__ == "__main__":
    sys.exit(main())
