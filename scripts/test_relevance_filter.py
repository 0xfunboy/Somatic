#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.relevance import RelevanceFilter


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    rf = RelevanceFilter()
    nominal = {"derived": {"thermal_stress": 0.2, "energy_stress": 0.2, "instability": 0.2}, "system": {"cpu_temp": 40.0, "disk_temp": 33.0, "memory_percent": 40.0, "disk_used_percent": 50.0}, "provider": {"source_quality": 1.0}}
    abnormal = {"derived": {"thermal_stress": 0.8, "energy_stress": 0.2, "instability": 0.2}, "system": {"cpu_temp": 80.0, "disk_temp": 33.0, "memory_percent": 40.0, "disk_used_percent": 50.0}, "provider": {"source_quality": 1.0}}
    failures = 0
    failures += check("kernel false", rf.telemetry_relevant("che kernel stai usando?", snapshot=nominal) is False)
    failures += check("public ip false", rf.telemetry_relevant("qual è il mio ip pubblico?", snapshot=nominal) is False)
    failures += check("node version false", rf.telemetry_relevant("che versione di node hai?", snapshot=nominal) is False)
    failures += check("feelings true", rf.telemetry_relevant("come ti senti?", snapshot=nominal) is True)
    failures += check("heat true", rf.telemetry_relevant("stai scaldando?", snapshot=nominal) is True)
    failures += check("abnormal can force relevance", rf.telemetry_relevant("che kernel stai usando?", snapshot=abnormal) is True)
    return failures


if __name__ == "__main__":
    sys.exit(main())
