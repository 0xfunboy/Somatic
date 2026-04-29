#!/usr/bin/env python3
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.resource_governor import ResourceGovernor
from soma_core.scheduler import BudgetedScheduler


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def snapshot(cpu: float) -> dict:
    return {
        "system": {
            "cpu_percent": cpu,
            "memory_percent": 40.0,
            "swap_percent": 0.0,
            "disk_busy_percent": 6.0,
            "disk_used_percent": 35.0,
            "cpu_temp": 46.0,
        },
        "metabolic": {"stress": 0.1},
        "reward": {"trend": 0.03},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        gov = ResourceGovernor(data_root=Path(td))
        gov.sample(snapshot(20.0))
        scheduler = BudgetedScheduler()

        scheduler.mark("projector")
        allowed, reason = scheduler.allow("projector", 10.0, gov, cost="high")
        failures += check("expensive operation blocked before interval", allowed is False and reason == "interval_not_due", reason)

        cheap_allowed, cheap_reason = scheduler.allow("ui_light_payload", 0.0, gov, cost="low")
        failures += check("cheap operation allowed", cheap_allowed is True, cheap_reason)

        gov.sample(snapshot(80.0))
        heavy_allowed, heavy_reason = scheduler.allow("cpp_projection", 0.0, gov, cost="high")
        failures += check("critical mode blocks heavy operation", heavy_allowed is False, heavy_reason)

        status = scheduler.status()
        projector = status["tasks"].get("projector", {})
        failures += check(
            "scheduler status exposes next due time",
            "next_due_in_sec" in projector and projector.get("interval_sec") == 10.0 and projector.get("last_reason") == "interval_not_due",
            str(projector),
        )
    return failures


if __name__ == "__main__":
    sys.exit(main())
