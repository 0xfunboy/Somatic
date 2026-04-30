#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.bios import BiosLoop
from soma_core.internal_loop import InternalLoop
from soma_core.power_policy import PowerPolicy
from soma_core.reward import RewardEngine


class DummyExecutor:
    def run_raw(self, cmd: str):
        return True, f"ok:{cmd}", ""


class DummyMutation:
    def can_mutate(self, *_args, **_kwargs):
        return True, []

    def propose_mutation(self, context: dict):
        return {
            "mutation_id": "mut-1234",
            "objective": context.get("objective") or "safe local mutation proposal",
            "tests": context.get("tests") or [],
        }


class DummyBaselines:
    def summary(self):
        return {"keys": {"idle_cpu_percent": {"confidence": 0.92}}}

    def update_from_snapshot(self, _snapshot):
        return {"updated_keys": ["idle_cpu_percent"], "stable_now": ["idle_cpu_percent"], "material_changes": []}


class DummyExperience:
    def get_lessons(self, limit=5):
        return []


class DummyAutobiography:
    def __init__(self) -> None:
        self.events: list[dict] = []

    def get_quality_summary(self):
        return {"stage": "meaningful", "lessons_count": 1}

    def write_meaningful_event(self, payload):
        self.events.append(dict(payload))
        return {"stored": True, "reason": "", "event": payload}


class DummyMetabolic:
    def current(self):
        return {
            "mode": "grow",
            "resource_mode": "normal",
            "growth_allowed": True,
            "recovery_required": False,
            "stable_cycles": 5,
            "reasons": [],
            "sensor_confidence_calibrated": 0.93,
            "self_integrity": 0.95,
        }

    def update(self, _snapshot, _context):
        return self.current()


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        autobio = DummyAutobiography()
        reward = RewardEngine(data_root=root)
        loop = InternalLoop(
            call_llm_raw=lambda *_args: json.dumps(
                {
                    "goal": "prepare a sandbox-safe mutation proposal",
                    "mode": "grow",
                    "action_type": "mutation_proposal",
                    "mutation_summary": "Tighten UI merge safety",
                    "expected_power_gain": "more stable operator UI",
                    "success_criteria": "proposal archived for sandbox review",
                    "rollback_plan": "keep proposal sandbox-only",
                    "risk": "low",
                    "reason": "stable metabolism permits sandbox planning",
                }
            ),
            executor=DummyExecutor(),
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=DummyMutation(),
            autobiography=autobio,
            experience=DummyExperience(),
            data_root=root,
        )
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            executor=DummyExecutor(),
            baseline_store=DummyBaselines(),
            autobiography=autobio,
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic(),
            internal_loop=loop,
            reward_engine=reward,
            data_root=root,
        )
        snapshot = {
            "provider": {"is_real": True, "name": "linux", "source_quality": 0.9},
            "system": {"cpu_percent": 11.0, "memory_percent": 32.0, "cpu_temp": 42.0},
            "derived": {"thermal_stress": 0.1, "energy_stress": 0.1, "instability": 0.04},
            "vector_state": {"vector_stability": 0.94, "vector_drift": 0.04},
            "reward": reward.summary(),
            "_growth": {"stage": "metabolic_growth_ready", "missing_requirements": [], "blocked_by": []},
            "resource": {"mode": "normal"},
        }
        result = bios.run_once(snapshot)
        internal_state = json.loads((root / "internal_loop_state.json").read_text(encoding="utf-8"))
        bios_state = json.loads((root / "bios_state.json").read_text(encoding="utf-8"))
        reward_state = json.loads((root / "reward_state.json").read_text(encoding="utf-8"))

        failures += check("internal state keeps last goal", internal_state.get("last_goal") == "prepare a sandbox-safe mutation proposal", str(internal_state))
        failures += check("internal growth updates include mutation proposal", "mutation_proposal" in json.dumps(internal_state.get("last_growth_updates", [])), str(internal_state.get("last_growth_updates")))
        failures += check("bios state mirrors internal next task", bios_state.get("last_internal_next_task") == "sandbox_test", str(bios_state))
        failures += check("reward state updated for mutation proposal", reward_state.get("last_kind") == "mutation_proposed", str(reward_state))
        failures += check("autobiography receives meaningful internal evidence", len(autobio.events) >= 1, str(autobio.events))
        failures += check("bios result exposes internal record", bool((result.get("result") or {}).get("internal_record")), str(result))
    return failures


if __name__ == "__main__":
    sys.exit(main())
