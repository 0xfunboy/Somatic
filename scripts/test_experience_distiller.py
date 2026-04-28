#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.experience import ExperienceDistiller


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        store = ExperienceDistiller(Path(td) / "learned_lessons.json")
        lessons = store.distill_from_operator_correction(
            "non dirmi sempre temperatura, voltaggio e ram quando non sono pertinenti. questa è una correzione permanente del tuo comportamento"
        )
        failures += check("operator correction lesson", len(lessons) == 1 and lessons[0]["kind"] == "operator_preference")

        lessons2 = store.distill_from_command("che kernel stai usando?", {"ok": True, "cmd": "uname -r", "stdout": "6.8.0", "stderr": ""})
        failures += check("kernel command no autobiography lesson", lessons2 == [], str(lessons2))

        lessons3 = store.distill_from_command("hai X11?", {"ok": True, "cmd": "pgrep -a Xorg", "stdout": "Nessun processo grafico trovato", "stderr": ""})
        failures += check("x11 limitation lesson", len(lessons3) == 1 and lessons3[0]["kind"] == "limitation", str(lessons3))

        store.save_lessons(lessons)
        store.save_lessons(lessons)
        saved = store.get_lessons(limit=10)
        failures += check("duplicate merges", len(saved) == 1 and saved[0]["confirmations"] >= 2, str(saved))
    return failures


if __name__ == "__main__":
    sys.exit(main())
