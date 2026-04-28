#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.life_drive import LifeDrive


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    drive = LifeDrive()
    snapshot = {"derived": {"thermal_stress": 0.2, "energy_stress": 0.1, "instability": 0.1}}
    growth = {"stage": "stable_body_baseline", "missing_requirements": ["idle_cpu_baseline_exists"], "completed_requirements": []}
    result = drive.evaluate(snapshot, growth, {"autobiography": {"lessons_count": 0}})
    failures = 0
    failures += check("reproduction local only", any("local sandbox lineage only" in note for note in result["safety_notes"]), str(result))
    failures += check("never proposes network spreading", all("network" not in note.lower() or "never" in note.lower() for note in result["safety_notes"]), str(result))
    failures += check("never proposes persistence", any("never install persistence" in note for note in result["safety_notes"]), str(result))
    failures += check("task follows growth blocker", result["suggested_internal_task"] == "update_body_baseline", str(result))
    return failures


if __name__ == "__main__":
    sys.exit(main())
