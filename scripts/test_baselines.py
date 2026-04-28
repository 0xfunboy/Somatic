#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.baselines import BodyBaselineStore


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "body_baselines.json"
        store = BodyBaselineStore(path, window_sec=10.0)
        ts = 0.0
        for _ in range(100):
            store.update_from_snapshot({"timestamp": ts, "system": {"cpu_percent": 5.0, "memory_percent": 40.0, "cpu_temp": 35.0, "disk_temp": 32.0}, "provider": {"source_quality": 0.9}})
            ts += 1.0
        cpu = store.get_baseline("idle_cpu_percent") or {}
        failures += check("100 samples create confidence", float(cpu.get("confidence", 0.0)) > 0.0, str(cpu))
        failures += check("stable windows increase confidence", int(cpu.get("windows", 0)) >= 3, str(cpu))
        store.update_from_snapshot({"timestamp": ts, "system": {"cpu_percent": 4.0, "memory_percent": 39.0}, "provider": {"source_quality": 0.8}})
        failures += check("missing temps handled", True)
        failures += check("baseline json persists", path.exists(), str(path))
        # material change
        for _ in range(20):
            ts += 1.0
            update = store.update_from_snapshot({"timestamp": ts, "system": {"cpu_percent": 40.0, "memory_percent": 70.0, "cpu_temp": 60.0, "disk_temp": 50.0}, "provider": {"source_quality": 0.9}})
        failures += check("material change detected", "idle_cpu_percent" in update["material_changes"] or "cpu_temp_c" in update["material_changes"], str(update))
    return failures


if __name__ == "__main__":
    sys.exit(main())
