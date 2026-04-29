#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.config import CFG
from soma_core.resource_governor import ResourceGovernor


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def sample_snapshot(*, cpu: float = 20.0, memory: float = 40.0, swap: float = 0.0, disk_busy: float = 8.0, cpu_temp: float = 48.0) -> dict:
    return {
        "system": {
            "cpu_percent": cpu,
            "memory_percent": memory,
            "swap_percent": swap,
            "disk_busy_percent": disk_busy,
            "disk_used_percent": 42.0,
            "cpu_temp": cpu_temp,
        },
        "metabolic": {"stress": 0.12},
        "reward": {"trend": 0.05},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        gov = ResourceGovernor(data_root=Path(td))

        normal = gov.sample(sample_snapshot(cpu=20.0, memory=40.0))
        failures += check("cpu 20 and ram 40 gives normal mode", normal["mode"] == "normal", str(normal))

        reduced = gov.sample(sample_snapshot(cpu=60.0, memory=40.0))
        failures += check("cpu 60 gives reduced mode", reduced["mode"] == "reduced", str(reduced))

        critical_cpu = gov.sample(sample_snapshot(cpu=80.0, memory=40.0))
        failures += check("cpu 80 gives critical mode", critical_cpu["mode"] == "critical", str(critical_cpu))

        critical_mem = gov.sample(sample_snapshot(cpu=20.0, memory=88.0))
        failures += check("memory 88 gives critical mode", critical_mem["mode"] == "critical", str(critical_mem))

        gov.update_runtime_metrics(event_loop_lag_ms=1200.0)
        critical_lag = gov.sample(sample_snapshot(cpu=20.0, memory=40.0))
        failures += check("event loop lag 1200ms gives critical mode", critical_lag["mode"] == "critical", str(critical_lag))

        gov._state["mode"] = "critical"
        gov._stable_since = time.time() - CFG.resource_recovery_stable_sec - 1.0
        gov.update_runtime_metrics(event_loop_lag_ms=0.0, tick_total_ms_avg=0.0)
        recovered = gov.sample(sample_snapshot(cpu=20.0, memory=40.0))
        failures += check("stable again past recovery window returns to normal", recovered["mode"] == "normal", str(recovered))
    return failures


if __name__ == "__main__":
    sys.exit(main())
