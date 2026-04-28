#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.autobiography import Autobiography
from soma_core.experience import ExperienceDistiller
from soma_core.metabolism import MetabolicEngine
from soma_core.mutation import MutationSandbox
from soma_core.reward import RewardEngine


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def snapshot(ts: float, thermal: float) -> dict:
    return {
        "timestamp": ts,
        "provider": {"is_real": True, "name": "linux", "source_quality": 0.95},
        "system": {"memory_percent": 35.0, "disk_used_percent": 40.0, "disk_busy_percent": 10.0},
        "derived": {"thermal_stress": thermal, "energy_stress": 0.1, "instability": 0.08},
        "llm": {"available": True, "mode": "deepseek"},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as repo_td, tempfile.TemporaryDirectory() as muts_td, tempfile.TemporaryDirectory() as mind_td, tempfile.TemporaryDirectory() as autobio_td:
        repo = Path(repo_td)
        (repo / "server.py").write_text("print('ok')\n", encoding="utf-8")
        reward = RewardEngine(data_root=Path(mind_td))
        engine = MetabolicEngine(data_root=Path(mind_td))
        experience = ExperienceDistiller(lessons_path=Path(mind_td) / "learned_lessons.json")
        autobio = Autobiography(data_root=Path(autobio_td))
        mutation = MutationSandbox(repo_root=repo, mutation_root=muts_td, reward_engine=reward, autobiography=autobio, experience=experience)

        stable_ctx = {
            "reward": {"rolling_score": 0.2, "trend": 0.15},
            "mutation": {"sandbox_root_exists": True, "last_tests_ok": True},
            "cpp_bridge": {"enabled": True, "smoke_ok": True},
            "command_agency": {"successful": 8, "failed": 0, "regression_ok": True},
            "capabilities": {"survival_policy": True},
            "growth": {"missing_requirements": []},
            "vector_state": {"vector_stability": 0.95, "vector_drift": 0.03, "vector_anomaly": 0.01},
        }
        for i in range(6):
            stable = engine.update(snapshot(float(i), 0.12), stable_ctx)
        failures += check("growth allowed before mutation", stable["growth_allowed"] is True and stable["mode"] == "grow", str(stable))

        unstable = engine.update(snapshot(7.0, 0.95), stable_ctx)
        failures += check("mutation causes mode switch to recover", unstable["mode"] == "recover", str(unstable))

        allowed, blockers = mutation.can_mutate(unstable, {"stage": "metabolic_growth_ready"}, {"rolling_score": 0.2})
        failures += check("new mutations blocked in recovery", allowed is False and "recovery_required" in blockers, str(blockers))

        sandbox_path = Path(muts_td) / "candidate"
        sandbox_path.mkdir(parents=True, exist_ok=True)
        report = mutation.evaluate_with_reward(
            sandbox_path,
            {"mutation_id": "m1", "objective": "unsafe mutation", "risk": "high"},
            {"ok": False},
            stable,
            {**unstable, "tests_ok": False},
            {"rolling_score": 0.2},
            {"rolling_score": -0.2},
        )
        failures += check("stressful mutation rejected", report["decision"] == "reject", str(report))
        failures += check("recovery lesson written", any(item.get("kind") == "mutation_lesson" for item in experience.get_lessons(limit=10)), str(experience.get_lessons(limit=10)))
    return failures


if __name__ == "__main__":
    sys.exit(main())

