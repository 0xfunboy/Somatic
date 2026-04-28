#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.internal_loop import InternalLoop
from soma_core.power_policy import PowerPolicy
from soma_core.reward import RewardEngine


class DummyExecutor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run_raw(self, cmd: str):
        self.commands.append(cmd)
        if "fail" in cmd:
            return False, "", "simulated failure"
        return True, "PASS", ""


class DummyMutation:
    def can_mutate(self, *_args, **_kwargs):
        return False, ["mutation_not_requested"]


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def growth_context() -> dict:
    return {
        "identity": {"name": "Soma", "kind": "embodied local software organism"},
        "metabolic": {"mode": "grow", "growth_allowed": True, "recovery_required": False, "stress": 0.2, "stability": 0.9},
        "growth": {"missing_requirements": ["command_agency"]},
        "lessons": [],
        "capabilities": {"survival_policy": True},
        "blockers": ["command_agency"],
        "reward": {"rolling_score": 0.1, "trend": 0.05},
        "vector_state": {"vector_stability": 0.92, "vector_drift": 0.05, "vector_anomaly": 0.02},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        reward = RewardEngine(data_root=Path(td))
        exe = DummyExecutor()
        loop = InternalLoop(
            call_llm_raw=lambda *_args: json.dumps({
                "goal": "increase command-result reliability",
                "mode": "grow",
                "action_type": "repo_test",
                "command": "python3 scripts/test_answer_finalizer.py",
                "expected_power_gain": "higher response reliability",
                "success_criteria": "tests pass",
                "risk": "low",
                "reason": "command-result failures reduce agency",
            }),
            executor=exe,
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=DummyMutation(),
            data_root=Path(td),
        )
        record = loop.run_growth_cycle(growth_context())
        failures += check("valid llm json creates an action", record["action_taken"]["action_type"] == "repo_test", str(record))
        failures += check("growth decision persisted", (Path(td) / "internal_decisions.jsonl").exists(), str((Path(td) / "internal_decisions.jsonl")))
        failures += check("executor used for repo test", exe.commands == ["python3 scripts/test_answer_finalizer.py"], str(exe.commands))

    with tempfile.TemporaryDirectory() as td:
        reward = RewardEngine(data_root=Path(td))
        exe = DummyExecutor()
        loop = InternalLoop(
            call_llm_raw=lambda *_args: "not json",
            executor=exe,
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=DummyMutation(),
            data_root=Path(td),
        )
        record = loop.run_growth_cycle(growth_context())
        state = loop.status()
        failures += check("invalid json falls back", record["fallback_used"] is True and state["invalid_json_count"] == 1, str(record))
        failures += check("invalid json receives negative reward", reward.summary().get("last_kind") == "command_finalized" or reward.summary().get("negative_count", 0) >= 1, str(reward.summary()))

    with tempfile.TemporaryDirectory() as td:
        reward = RewardEngine(data_root=Path(td))
        loop = InternalLoop(
            call_llm_raw=lambda *_args: json.dumps({
                "suspected_cause": "mutation stress",
                "evidence": ["stress increased"],
                "action_type": "pause_growth",
                "command": "",
                "should_pause_growth": True,
                "should_rollback_last_mutation": False,
                "success_criteria": "stability improves",
                "reason": "diagnose first",
            }),
            executor=DummyExecutor(),
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=DummyMutation(),
            data_root=Path(td),
        )
        record = loop.run_recovery_cycle({
            "metabolic": {"mode": "recover", "growth_allowed": False, "recovery_required": True},
            "recent_failures": [{"kind": "mutation", "summary": "stress increased"}],
            "baselines": {},
            "vector_state": {"vector_anomaly": 0.8},
        })
        failures += check("recovery decision pauses mutation", record["action_taken"]["action_type"] == "pause_growth", str(record))
        failures += check("decision contains causal fields", all(key in record for key in ("prompt", "llm_raw", "parsed", "action_taken", "evidence", "reward", "next_task")), str(record.keys()))
    return failures


if __name__ == "__main__":
    sys.exit(main())

