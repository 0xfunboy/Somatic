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
    def run_raw(self, cmd: str):
        return True, f"ok:{cmd}", ""


class DummyMutation:
    def can_mutate(self, *_args, **_kwargs):
        return False, ["mutation_not_requested"]


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        events: list[dict] = []
        reward = RewardEngine(data_root=Path(td))
        loop = InternalLoop(
            call_llm_raw=lambda *_args: json.dumps(
                {
                    "goal": "observe current blocker",
                    "mode": "observe",
                    "action_type": "observe",
                    "reason": "cheap evidence first",
                    "success_criteria": "fresh evidence persisted",
                    "next_check": "observe",
                    "risk": "low",
                }
            ),
            executor=DummyExecutor(),
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=DummyMutation(),
            emit_event=events.append,
            data_root=Path(td),
        )
        record = loop.run_mode_cycle(
            "observe",
            {
                "metabolic": {"mode": "observe", "resource_mode": "normal", "growth_allowed": False, "recovery_required": False},
                "resource": {"mode": "normal"},
                "growth": {"missing_requirements": []},
                "vector_state": {"mode_contribution": "stable"},
                "reward": reward.summary(),
                "seconds_since_user_input": 999.0,
            },
        )
        kinds = [event.get("type") for event in events]
        failures += check("inner_prompt event emitted", "inner_prompt" in kinds, str(kinds))
        failures += check("inner_llm_raw event emitted", "inner_llm_raw" in kinds, str(events))
        failures += check("inner_decision event emitted", "inner_decision" in kinds, str(events))
        failures += check("inner_evidence event emitted", "inner_evidence" in kinds, str(events))
        failures += check(
            "raw event is compact preview",
            any(event.get("type") == "inner_llm_raw" and event.get("source") in {"deepseek", "fallback", "invalid_json", "timeout"} for event in events),
            str(events),
        )
        failures += check("record keeps emitted events", len(record.get("events", [])) == 4, str(record.get("events")))
    return failures


if __name__ == "__main__":
    sys.exit(main())
