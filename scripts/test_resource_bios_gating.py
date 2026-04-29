#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.bios import BiosLoop
from soma_core.reward import RewardEngine


class DummyExecutor:
    def run_raw(self, cmd: str):
        return True, f"ok:{cmd}", ""


class DummyBaselines:
    def summary(self):
        return {"keys": {"idle_cpu_percent": {"confidence": 0.8}}}

    def update_from_snapshot(self, _snapshot):
        return {"updated_keys": ["idle_cpu_percent"], "stable_now": ["idle_cpu_percent"], "material_changes": [], "summary": {}}


class DummyExperience:
    def get_lessons(self, limit=5):
        return [{"id": "a", "behavioral_update": "keep the host responsive"}][:limit]


class DummyMetabolic:
    def __init__(self, mode: str, recovery_required: bool = False) -> None:
        self._mode = mode
        self._recovery_required = recovery_required

    def current(self):
        return {
            "mode": self._mode,
            "growth_allowed": self._mode == "grow",
            "recovery_required": self._recovery_required,
            "stable_cycles": 5,
            "reasons": ["host_resource_pressure"] if self._mode in {"stabilize", "recover"} else [],
            "raw_source_quality": 0.95,
            "sensor_confidence_calibrated": 0.9,
            "baseline_confidence": 0.8,
            "missing_sensor_classes": [],
        }

    def update(self, _snapshot, _context):
        return self.current()


class DummyGovernor:
    def __init__(self, mode: str, bios_interval_sec: float) -> None:
        self._mode = mode
        self._bios_interval_sec = bios_interval_sec

    def allow(self, operation: str, *, estimated_cost: str = "low"):
        if operation == "bios_llm" and self._mode in {"critical", "recovery"}:
            return False, f"{self._mode}:llm_paused"
        return True, f"{self._mode}:allowed"

    def recommended_bios_interval_sec(self) -> float:
        return self._bios_interval_sec

    def recommended_llm_timeout_sec(self) -> float:
        return 8.0 if self._mode == "critical" else 12.0


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def grow_snapshot(resource_mode: str = "normal") -> dict:
    return {
        "_growth": {"missing_requirements": [], "stage": "metabolic_growth_ready"},
        "derived": {},
        "system": {},
        "provider": {},
        "resource": {"mode": resource_mode},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        llm_calls: list[str] = []
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            use_llm=True,
            executor=DummyExecutor(),
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("grow"),
            call_llm_raw=lambda prompt, _timeout: llm_calls.append(prompt) or '{"task":"run_light_validation","reason":"test","requires_shell":true,"command":"python3 scripts/test_command_planner.py"}',
            resource_governor=DummyGovernor("critical", 3600.0),
            data_root=Path(td),
        )
        result = bios.run_once(grow_snapshot("critical"))
        failures += check("critical mode blocks internal llm", llm_calls == [] and bios.status().get("llm_calls_today") == 0, str(result))

    with tempfile.TemporaryDirectory() as td:
        bios = BiosLoop(
            interval_sec=1.0,
            max_tasks_per_hour=5,
            use_llm=False,
            executor=DummyExecutor(),
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("observe"),
            resource_governor=DummyGovernor("reduced", 10.0),
            data_root=Path(td),
        )
        bios._state["last_run_at"] = time.time() - 2.0
        failures += check("reduced mode stretches bios interval", bios.maybe_run(grow_snapshot("reduced"), last_user_interaction_at=0.0) is None, str(bios.status()))

    with tempfile.TemporaryDirectory() as td:
        reward = RewardEngine(data_root=Path(td) / "mind")
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            use_llm=False,
            executor=DummyExecutor(),
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("observe"),
            reward_engine=reward,
            resource_governor=DummyGovernor("normal", 1.0),
            data_root=Path(td),
        )
        yielded = bios.maybe_run(grow_snapshot("normal"), last_user_interaction_at=time.time())
        failures += check("user active window makes bios yield", yielded is None and reward.summary().get("last_kind") == "yielded_for_user_activity", str(reward.summary()))

    with tempfile.TemporaryDirectory() as td:
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            use_llm=False,
            executor=DummyExecutor(),
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("recover", recovery_required=True),
            resource_governor=DummyGovernor("critical", 3600.0),
            data_root=Path(td),
        )
        urgent_snapshot = {
            **grow_snapshot("critical"),
            "metabolic": {"mode": "recover", "recovery_required": True},
        }
        urgent = bios.maybe_run(urgent_snapshot, last_user_interaction_at=time.time())
        failures += check("recovery task can still run if urgent", urgent is not None, str(urgent))
    return failures


if __name__ == "__main__":
    sys.exit(main())
