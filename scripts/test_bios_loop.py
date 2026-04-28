#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.bios import BiosLoop


class DummyExecutor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run_raw(self, cmd: str):
        self.commands.append(cmd)
        return True, "ok", ""


class DummyBaselines:
    def update_from_snapshot(self, _snapshot):
        return {"updated_keys": ["idle_cpu_percent"], "stable_now": ["idle_cpu_percent"], "material_changes": [], "summary": {}}

    def summary(self):
        return {"keys": {"idle_cpu_percent": {"confidence": 0.8}}}


class DummyExperience:
    def get_lessons(self, limit=5):
        return [{"id": "x", "behavioral_update": "keep technical answers direct"}][:limit]


class DummyMetabolic:
    def __init__(self, mode: str) -> None:
        self._mode = mode

    def current(self):
        return {
            "mode": self._mode,
            "growth_allowed": self._mode in {"grow", "mutate"},
            "recovery_required": self._mode == "recover",
            "stable_cycles": 5,
            "reasons": [] if self._mode in {"grow", "observe"} else ["stress_above_max"],
        }

    def update(self, _snapshot, _context):
        return self.current()


class DummyInternalLoop:
    def __init__(self) -> None:
        self.called: list[str] = []

    def run_growth_cycle(self, _context):
        self.called.append("grow")
        return {
            "prompt": "growth prompt",
            "parsed": {"action_type": "repo_test"},
            "action_taken": {"action_type": "repo_test", "command": "python3 scripts/test_answer_finalizer.py", "goal": "verify"},
            "evidence": {"ok": True, "command": "python3 scripts/test_answer_finalizer.py"},
            "reward": {"kind": "test_pass", "value": 0.15},
            "next_task": "evaluate_reward",
        }

    def run_recovery_cycle(self, _context):
        self.called.append("recover")
        return {
            "prompt": "recovery prompt",
            "parsed": {"action_type": "pause_growth"},
            "action_taken": {"action_type": "pause_growth", "command": "", "goal": "recover"},
            "evidence": {"ok": True, "reason": "pause growth"},
            "reward": {"kind": "neutral", "value": 0.0},
            "next_task": "recover",
        }

    def status(self):
        return {"last_prompt_type": "growth_planner", "last_run_at": 1.0}


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    snapshot = {"_growth": {"missing_requirements": ["idle_cpu_baseline_exists"], "stage": "stable_body_baseline"}, "derived": {}, "system": {}, "provider": {}}
    with tempfile.TemporaryDirectory() as td:
        exe = DummyExecutor()
        bios = BiosLoop(
            interval_sec=1.0,
            max_tasks_per_hour=1,
            executor=exe,
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("observe"),
            data_root=Path(td),
        )
        result = bios.run_once(snapshot)
        failures += check("observe mode prefers cheap evidence", result["task"]["task"] == "check_runtime_storage", str(result))
        failures += check("writes bios history", (Path(td) / "bios_history.jsonl").exists())
        second = bios.maybe_run(snapshot, last_user_interaction_at=0.0)
        failures += check("respects max tasks per hour", second is None, str(second))
        failures += check("does not write to chat", "chat" not in json.dumps(result))

    with tempfile.TemporaryDirectory() as td:
        exe = DummyExecutor()
        internal = DummyInternalLoop()
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            executor=exe,
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("grow"),
            internal_loop=internal,
            data_root=Path(td),
        )
        result = bios.run_once({"_growth": {"missing_requirements": ["three_categories"], "stage": "verified_command_agency"}, "derived": {}, "system": {}, "provider": {}})
        failures += check("grow mode uses internal loop", internal.called == ["grow"], str(internal.called))
        failures += check("internal evidence captured", result["result"]["evidence"]["ok"] is True, str(result))
        failures += check("bios state stores internal prompt", json.loads((Path(td) / "bios_state.json").read_text(encoding="utf-8")).get("last_internal_prompt") == "growth prompt")
    return failures


if __name__ == "__main__":
    sys.exit(main())
