#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.output_filter import OutputFilter
from soma_core.relevance import RelevanceFilter


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    filt = OutputFilter(RelevanceFilter())
    snapshot = {"derived": {"thermal_stress": 0.2, "energy_stress": 0.2, "instability": 0.2}, "system": {"cpu_temp": 36.0, "disk_temp": 33.0, "memory_percent": 45.0, "disk_used_percent": 55.0}, "provider": {"source_quality": 1.0}}
    failures = 0
    text = filt.clean_response(
        "Ho verificato con `uname -r`: 6.8.0. La mia temperatura è 36C e il voltaggio è 12V.",
        "che kernel stai usando?",
        snapshot,
        command_result={"ok": True, "cmd": "uname -r", "stdout": "6.8.0"},
    )
    failures += check("strip telemetry for kernel", text == "Ho verificato con `uname -r`: 6.8.0.", text)
    text = filt.clean_response(
        "CPU 76C. Thermal stress elevato.",
        "stai scaldando?",
        snapshot,
    )
    failures += check("keep heat for heat question", "76C" in text or "Thermal" in text, text)
    return failures


if __name__ == "__main__":
    sys.exit(main())
