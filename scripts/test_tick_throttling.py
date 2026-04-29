#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("SOMA_SENSOR_PROVIDER", "mock")
os.environ.setdefault("SOMA_LLM_MODE", "off")
os.environ.setdefault("SOMA_BIOS_LOOP", "0")
os.environ.setdefault("SOMA_CPP_BRIDGE", "0")
os.environ.setdefault("SOMA_MUTATION_SANDBOX", "0")
os.environ.setdefault("SOMA_AUTO_COMPACT_MIND_STATE", "0")

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.resource_governor import ResourceGovernor
from soma_core.scheduler import BudgetedScheduler

import server  # noqa: E402


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def resource_snapshot(cpu: float) -> dict:
    return {
        "system": {
            "cpu_percent": cpu,
            "memory_percent": 40.0,
            "swap_percent": 0.0,
            "disk_busy_percent": 5.0,
            "disk_used_percent": 40.0,
            "cpu_temp": 45.0,
        },
        "metabolic": {"stress": 0.12},
        "reward": {"trend": 0.04},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        server.runtime = server.make_runtime_state()
        server._scheduler = BudgetedScheduler()
        server._resource_governor = ResourceGovernor(data_root=Path(td))

        server._resource_governor.sample(resource_snapshot(60.0))
        server.runtime["hz"] = 0.2
        server.apply_autonomic_rate({"target_hz": 5.0})
        failures += check("policy target 5hz is capped by resource max 1hz", float(server.runtime["hz"]) <= 1.0, str(server.runtime["hz"]))

        clamped = server.clamp_requested_hz(5.0)
        failures += check(
            "manual set_hz cannot exceed resource max by default",
            clamped <= server._resource_governor.recommended_tick_hz() <= 1.0,
            f"clamped={clamped} budget={server._resource_governor.budget()}",
        )

        server._resource_governor.sample(resource_snapshot(20.0))
        normal_budget = server._resource_governor.budget()
        normal_interval = max(1.0 / max(float(normal_budget.get("projector_hz_max", 0.0) or 0.0), 0.1), 1.0)
        normal_scheduler = BudgetedScheduler()
        normal_scheduler._last_run["projector"] = time.time() - 2.0
        normal_due, _ = normal_scheduler.allow("projector", normal_interval, server._resource_governor, cost="medium")

        server._resource_governor.sample(resource_snapshot(60.0))
        reduced_budget = server._resource_governor.budget()
        reduced_interval = max(1.0 / max(float(reduced_budget.get("projector_hz_max", 0.0) or 0.0), 0.1), 1.0)
        reduced_scheduler = BudgetedScheduler()
        reduced_scheduler._last_run["projector"] = time.time() - 2.0
        reduced_due, reduced_reason = reduced_scheduler.allow("projector", reduced_interval, server._resource_governor, cost="medium")

        failures += check(
            "reduced mode lowers projector frequency",
            normal_due is True and reduced_due is False and reduced_interval > normal_interval,
            f"normal_interval={normal_interval} reduced_interval={reduced_interval} reduced_reason={reduced_reason}",
        )
    return failures


if __name__ == "__main__":
    sys.exit(main())
