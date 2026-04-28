#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import soma_core.autobiography as autobiography_mod
from soma_core.autobiography import Autobiography, is_autobiographical


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        autobiography_mod._SELF_MODEL_FILE = tmp / "self_model.json"
        (tmp / "self_model.json").write_text(json.dumps({"growth": {"reflection_quality": {"total_reflections": 100, "meaningful_reflections": 0, "empty_reflections": 100, "duplicate_reflections": 0, "lessons_learned": 0}}}), encoding="utf-8")
        auto = Autobiography(tmp / "autobiography")

        ok, _ = is_autobiographical({"kind": "reflection", "title": "Nominal state", "summary": "Nominal state. Stable voltage and unchanged temp."})
        failures += check("nominal state rejected", ok is False)

        stored = auto.write_meaningful_event({"kind": "failure", "title": "Blocked risky command", "summary": "Survival policy blocked a dangerous command.", "impact": "medium"})
        failures += check("blocked dangerous command accepted", stored["stored"] is True, str(stored))

        stored = auto.write_meaningful_event({"kind": "operator_correction", "title": "Persistent rule", "summary": "Do not mention irrelevant telemetry.", "impact": "high"})
        failures += check("operator correction accepted", stored["stored"] is True, str(stored))

        stored = auto.write_meaningful_event({"kind": "self_modification", "title": "Rollback", "summary": "A self modification was rolled back after failing validation.", "impact": "medium"})
        failures += check("self-mod rollback accepted", stored["stored"] is True, str(stored))

        first = auto.write_meaningful_event({"kind": "lesson", "title": "One lesson", "summary": "A durable lesson.", "impact": "medium"})
        second = auto.write_meaningful_event({"kind": "lesson", "title": "One lesson", "summary": "A durable lesson.", "impact": "medium"})
        failures += check("duplicate event deduped", first["stored"] is True and second["stored"] is False and second["reason"] == "duplicate", str(second))

        (tmp / "autobiography" / "learned_lessons.json").write_text("[]", encoding="utf-8")
        quality = auto.get_quality_summary()
        failures += check("quality detects shallow", quality["shallow"] is True, str(quality))
    return failures


if __name__ == "__main__":
    sys.exit(main())
