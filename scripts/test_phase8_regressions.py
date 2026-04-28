#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.answering import AnswerFinalizer
from soma_core.output_filter import OutputFilter
from soma_core.relevance import RelevanceFilter
from soma_core.experience import ExperienceDistiller
from soma_core.command_planner import deterministic_shortcut
from soma_core.skill_router import SkillRouter
from soma_core.autobiography import Autobiography
from soma_core.executor import AutonomousShellExecutor, _resolve_nvm_default_bin


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    snapshot = {
        "derived": {"thermal_stress": 0.1, "energy_stress": 0.1, "instability": 0.1},
        "system": {"cpu_temp": 36.0, "disk_temp": 33.0, "memory_percent": 45.0, "disk_used_percent": 55.0},
        "provider": {"source_quality": 1.0},
    }
    finalizer = AnswerFinalizer(OutputFilter(RelevanceFilter()))
    failures = 0
    text = finalizer.finalize(
        "che versione di node hai?",
        snapshot,
        command_result={"ok": True, "cmd": "node --version", "stdout": "v23.3.0"},
        llm_text="I am processing that with a live body state: nominal state via linux, 12.0V, silicon 37C...",
    )
    failures += check("node regression fixed", text == "Ho verificato con `node --version`: v23.3.0.", text)

    text = finalizer.finalize(
        "qual è il mio ip pubblico?",
        snapshot,
        command_result={"ok": True, "cmd": "curl -s https://ifconfig.me", "stdout": "93.56.125.173"},
        llm_text="My current somatic context is thermal comfort 0.82.",
    )
    failures += check("public ip regression fixed", text == "Ho verificato con `curl -s https://ifconfig.me`: 93.56.125.173.", text)

    with tempfile.TemporaryDirectory() as td:
        auto = Autobiography(Path(td) / "autobiography")
        router = SkillRouter(auto)
        lesson_skill = router.execute("quali lezioni operative hai imparato da me oggi?")
        failures += check("no lessons admits none", lesson_skill is not None and "Non ho ancora lezioni operative persistenti sufficienti" in lesson_skill["text"], str(lesson_skill))

        distiller = ExperienceDistiller(Path(td) / "autobiography" / "learned_lessons.json")
        one_lesson = distiller.distill_from_operator_correction("non dirmi sempre temperatura e voltaggio quando non servono")
        if one_lesson:
            distiller.save_lessons(one_lesson)
        latest = distiller.latest_lesson()
        failures += check("persistent lesson creation or no-evidence reason", latest is not None or one_lesson == [], str(latest or one_lesson))

    shortcut = deterministic_shortcut("controlla la dimensione dei tuoi log runtime")
    failures += check("runtime logs use repo-local paths", shortcut is not None and "/var/log" not in shortcut["command"] and "runtime_storage_report.py" in shortcut["command"], str(shortcut))

    nvm_bin = _resolve_nvm_default_bin()
    if nvm_bin:
        executor = AutonomousShellExecutor(object(), object())
        ok, stdout, stderr = executor.run_raw("node --version")
        failures += check("executor prefers nvm default node", ok and stdout == "v23.3.0", stdout or stderr)
    return failures


if __name__ == "__main__":
    sys.exit(main())
