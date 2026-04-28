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
            data_root=Path(td),
        )
        result = bios.run_once(snapshot)
        failures += check("selects baseline task", result["task"]["task"] == "update_body_baseline", str(result))
        failures += check("writes bios history", (Path(td) / "bios_history.jsonl").exists())
        second = bios.maybe_run(snapshot, last_user_interaction_at=0.0)
        failures += check("respects max tasks per hour", second is None, str(second))
        failures += check("does not write to chat", "chat" not in json.dumps(result))

    with tempfile.TemporaryDirectory() as td:
        exe = DummyExecutor()
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            executor=exe,
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            call_llm_raw=lambda *_args, **_kwargs: json.dumps({"task": "verify_environment_fact", "reason": "check command agency", "requires_shell": True, "command": "uname -r"}),
            data_root=Path(td),
        )
        result = bios.run_once({"_growth": {"missing_requirements": ["three_categories"], "stage": "verified_command_agency"}, "derived": {}, "system": {}, "provider": {}})
        failures += check("handles mocked llm json", result["task"]["task"] == "verify_environment_fact", str(result))
        failures += check("shell task uses executor", exe.commands == ["uname -r"], str(exe.commands))
    return failures


if __name__ == "__main__":
    sys.exit(main())
