#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.mutation import MutationSandbox
from soma_core.reward import RewardEngine


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as repo_td, tempfile.TemporaryDirectory() as muts_td, tempfile.TemporaryDirectory() as mind_td:
        repo = Path(repo_td)
        (repo / "server.py").write_text("print('ok')\n", encoding="utf-8")
        reward = RewardEngine(data_root=Path(mind_td))
        mutation = MutationSandbox(repo_root=repo, mutation_root=muts_td, reward_engine=reward)
        sandbox_path = Path(muts_td) / "candidate"
        sandbox_path.mkdir(parents=True, exist_ok=True)
        before = {"stress": 0.2, "stability": 0.8}

        keep = mutation.evaluate_with_reward(
            sandbox_path,
            {"mutation_id": "keep1", "objective": "improve tests", "risk": "low"},
            {"ok": True},
            before,
            {"stress": 0.18, "stability": 0.86, "tests_ok": True},
            {"rolling_score": 0.0},
            {"rolling_score": 0.3},
        )
        failures += check("positive mutation reward keeps for review", keep["decision"] == "keep_for_review", str(keep))

        reject_fail = mutation.evaluate_with_reward(
            sandbox_path,
            {"mutation_id": "rej1", "objective": "break tests", "risk": "medium"},
            {"ok": False},
            before,
            {"stress": 0.22, "stability": 0.6, "tests_ok": False},
            {"rolling_score": 0.0},
            {"rolling_score": -0.2},
        )
        failures += check("mutation with tests failing is rejected", reject_fail["decision"] == "reject", str(reject_fail))

        reject_stress = mutation.evaluate_with_reward(
            sandbox_path,
            {"mutation_id": "rej2", "objective": "increase throughput", "risk": "medium"},
            {"ok": True},
            before,
            {"stress": 0.45, "stability": 0.7, "tests_ok": True},
            {"rolling_score": 0.0},
            {"rolling_score": 0.2},
        )
        failures += check("mutation with stress increase is rejected", reject_stress["decision"] == "reject", str(reject_stress))

        candidate = mutation.evaluate_with_reward(
            sandbox_path,
            {"mutation_id": "cand1", "objective": "improve validation", "risk": "low"},
            {"ok": True, "full_validation_ok": True},
            before,
            {"stress": 0.18, "stability": 0.9, "tests_ok": True},
            {"rolling_score": 0.0},
            {"rolling_score": 0.4},
        )
        failures += check("candidate still requires operator approval", candidate["operator_approval_required"] is True, str(candidate))
    return failures


if __name__ == "__main__":
    sys.exit(main())

