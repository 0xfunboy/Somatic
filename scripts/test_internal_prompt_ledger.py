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


def growth_context() -> dict:
    return {
        "identity": {"name": "Soma", "kind": "embodied local software organism"},
        "metabolic": {"mode": "grow", "resource_mode": "normal", "growth_allowed": True, "recovery_required": False, "stress": 0.12, "stability": 0.92},
        "growth": {"missing_requirements": ["command_agency"]},
        "lessons": [{"observation": "A" * 5000}],
        "capabilities": {"survival_policy": True},
        "blockers": ["command_agency"],
        "reward": {"rolling_score": 0.1, "trend": 0.03},
        "vector_state": {"vector_stability": 0.94, "vector_drift": 0.04},
        "seconds_since_user_input": 999.0,
        "resource": {"mode": "normal"},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        reward = RewardEngine(data_root=root)
        loop = InternalLoop(
            call_llm_raw=lambda *_args: json.dumps(
                {
                    "goal": "verify command agency with a safe repo-local test",
                    "mode": "grow",
                    "action_type": "repo_test",
                    "command": "python3 scripts/test_answer_finalizer.py",
                    "expected_power_gain": "higher response reliability",
                    "success_criteria": "tests pass",
                    "risk": "low",
                    "reason": "command evidence first",
                }
            ),
            executor=DummyExecutor(),
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=DummyMutation(),
            data_root=root,
        )
        loop.run_growth_cycle(growth_context())

        state_path = root / "internal_loop_state.json"
        ledger_path = root / "internal_prompt_index.jsonl"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        lines = ledger_path.read_text(encoding="utf-8").splitlines()
        entry = json.loads(lines[-1])

        failures += check("prompt ledger file written", ledger_path.exists() and bool(lines), str(ledger_path))
        failures += check("prompt archive path exists", Path(str(entry.get("prompt_path") or "")).exists(), str(entry))
        failures += check("raw archive path exists", Path(str(entry.get("raw_path") or "")).exists(), str(entry))
        failures += check("state stores prompt preview and path", bool(state.get("last_prompt_preview")) and bool(state.get("last_prompt_path")), str(state))
        failures += check("state stores raw preview and path", bool(state.get("last_raw_preview")) and bool(state.get("last_raw_path")), str(state))
        failures += check("state remains compact", state_path.stat().st_size < 32 * 1024, str(state_path.stat().st_size))
        failures += check("ledger entry tracks fallback flag", "fallback" in entry, str(entry))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        prompt_archive = root / "internal_prompts" / "aa" / "aa.internal_prompt.txt.gz"
        raw_archive = root / "internal_prompts" / "bb" / "bb.internal_raw.txt.gz"
        prompt_archive.parent.mkdir(parents=True, exist_ok=True)
        raw_archive.parent.mkdir(parents=True, exist_ok=True)
        prompt_archive.write_text("prompt", encoding="utf-8")
        raw_archive.write_text("raw", encoding="utf-8")
        state = {
            "enabled": True,
            "run_count": 1,
            "last_mode": "recover",
            "last_prompt_type": "recovery_planner",
            "last_prompt": {"sha1": "aa", "archive_path": str(prompt_archive)},
            "last_prompt_preview": "prompt preview",
            "last_prompt_path": str(prompt_archive),
            "last_raw": {"sha1": "bb", "archive_path": str(raw_archive)},
            "last_raw_preview": "",
            "last_raw_path": str(raw_archive),
            "last_parsed": {},
            "last_parsed_fallback": {"action_type": "pause_growth", "reason": "fallback recovery"},
            "last_fallback": True,
            "last_action": {"action_type": "pause_growth", "goal": "stabilize"},
            "last_action_taken": {"action_type": "pause_growth", "goal": "stabilize"},
            "last_evidence": {"ok": True, "reason": "metabolic instability"},
            "last_reward_delta": 0.08,
            "last_memory_updates": [],
            "last_growth_updates": [{"internal_plan": {"goal": "stabilize"}}],
            "last_next_task": "recover",
            "last_goal": "stabilize",
            "last_reason": "fallback recovery",
            "last_resource_mode": "recovery",
            "last_metabolic_mode": "recover",
            "last_run_at": 123.0,
        }
        (root / "internal_loop_state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        loop = InternalLoop(data_root=root)
        seeded = loop.last_decisions(limit=1)
        failures += check("seeded ledger exists from compact state", (root / "internal_prompt_index.jsonl").exists() and bool(seeded), str(seeded))
        failures += check("seeded ledger keeps fallback marker", bool(seeded and seeded[0].get("fallback")), str(seeded))
        failures += check("seeded ledger keeps prompt path", bool(seeded and seeded[0].get("prompt_path") == str(prompt_archive)), str(seeded))
    return failures


if __name__ == "__main__":
    sys.exit(main())
