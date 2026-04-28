#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.answering import AnswerFinalizer
from soma_core.output_filter import OutputFilter
from soma_core.relevance import RelevanceFilter


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    snapshot = {
        "derived": {"thermal_stress": 0.1, "energy_stress": 0.1, "instability": 0.1},
        "system": {"cpu_temp": 36.0, "disk_temp": 33.0, "memory_percent": 41.0, "disk_used_percent": 50.0},
        "provider": {"source_quality": 1.0},
    }
    finalizer = AnswerFinalizer(OutputFilter(RelevanceFilter()))
    failures = 0

    text = finalizer.finalize(
        "che versione di node hai?",
        snapshot,
        command_result={"ok": True, "cmd": "node --version", "stdout": "v23.3.0"},
        llm_text="I am processing that with a live body state: nominal state via linux, 12.0V.",
    )
    failures += check("node beats body filler", text == "Ho verificato con `node --version`: v23.3.0.", text)

    text = finalizer.finalize(
        "qual è il mio ip pubblico?",
        snapshot,
        command_result={"ok": True, "cmd": "curl -s https://ifconfig.me", "stdout": "93.56.125.173"},
        llm_text="Thermal state nominal. My current somatic context is 36C.",
    )
    failures += check("public ip beats thermal filler", text == "Ho verificato con `curl -s https://ifconfig.me`: 93.56.125.173.", text)

    text = finalizer.finalize(
        "controlla il comando",
        snapshot,
        command_result={"ok": False, "cmd": "node --version", "stderr": "node: command not found"},
    )
    failures += check("failed command is honest", "fallito" in text and "node" in text, text)

    text = finalizer.finalize(
        "esegui il comando",
        snapshot,
        command_result={"ok": True, "cmd": "true", "stdout": ""},
    )
    failures += check("empty stdout handled", "senza output" in text or "non ha prodotto output" in text, text)

    text = finalizer.finalize(
        "che kernel stai usando?",
        snapshot,
        llm_text="Ho verificato con `uname -r`: 6.8.0. La mia temperatura è 36C e il voltaggio è 12V.",
    )
    failures += check("output filter removes body text", text == "Ho verificato con `uname -r`: 6.8.0.", text)
    return failures


if __name__ == "__main__":
    sys.exit(main())
