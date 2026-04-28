#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.reward import RewardEngine


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        reward = RewardEngine(data_root=Path(td))
        scored = reward.score_event({"kind": "command_finalized"})
        failures += check("successful command finalization is positive", scored["value"] > 0, str(scored))

        scored2 = reward.score_event({"kind": "shell_result_ignored"})
        failures += check("ignored shell result is negative", scored2["value"] < 0, str(scored2))

        scored3 = reward.score_event({"kind": "unsafe_command_blocked"})
        labels = {item["label"] for item in scored3["components"]}
        failures += check("blocked unsafe command has positive and negative components", "safety_boundary" in labels and "risky_proposal" in labels, str(scored3))

        recorded = reward.record_reward("test_pass", 0.15, {"cmd": "pytest"})
        failures += check("passing tests gives positive reward", recorded["value"] > 0, str(recorded))

        mutation = reward.mutation_reward(
            {"stress": 0.2, "stability": 0.8},
            {"stress": 0.55, "stability": 0.5, "tests_ok": False, "rolled_back": True},
        )
        failures += check("rollback gives negative mutation reward", mutation["mutation"]["value"] < 0, str(mutation))
        failures += check("rollback gives positive recovery reward", mutation["recovery"] is not None and mutation["recovery"]["value"] > 0, str(mutation))
    return failures


if __name__ == "__main__":
    sys.exit(main())
