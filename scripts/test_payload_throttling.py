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


def sample_snapshot(*, resource_mode: str = "normal", metabolic_mode: str = "observe", scenario: str = "nominal") -> dict:
    return {
        "timestamp": 1.0,
        "scenario": scenario,
        "sensors": {"voltage": 12.3, "temp_si": 33.0, "az": -9.81},
        "system": {"cpu_percent": 21.0, "memory_percent": 41.0, "cpu_temp": 47.0},
        "metabolic": {"mode": metabolic_mode, "stability": 0.82, "stress": 0.18},
        "resource": {"mode": resource_mode, "host_pressure": 0.22, "budget": {"ui_hz_max": 0.5}},
        "bios_status": {"last_task": "observe"},
        "mutation_status": {"recommendation": ""},
    }


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        server.runtime = server.make_runtime_state()
        server.runtime["hz"] = 1.0
        server._scheduler = BudgetedScheduler()
        server._resource_governor = ResourceGovernor(data_root=Path(td))
        snapshot = sample_snapshot()

        sig = server._resource_signature(snapshot)
        server.runtime["force_full_payload"] = False
        server.runtime["last_full_payload_signature"] = sig
        server.runtime["last_full_payload_at"] = time.time()
        server._scheduler.mark("ui_full_payload")
        failures += check("full payload is not sent every tick", server.full_payload_due(snapshot) is False, str(server.runtime))

        light_interval = max(1.0 / max(server._cfg_ref.ui_light_tick_hz, 0.1), 0.1)
        server._scheduler._last_run["ui_light_payload"] = time.time() - (light_interval + 0.2)
        light_allowed, light_reason = server._scheduler.allow("ui_light_payload", light_interval, server._resource_governor, cost="low")
        light = server.light_tick_payload(snapshot)
        failures += check(
            "light payload sent on schedule",
            light_allowed is True and light.get("type") == "tick_light" and "trace" not in light and "mind" not in light,
            f"reason={light_reason} payload_keys={sorted(light.keys())}",
        )

        changed = sample_snapshot(resource_mode="reduced", metabolic_mode="recover", scenario="heavyload")
        failures += check("full payload sent on meaningful state change", server.full_payload_due(changed) is True, str(changed))
    return failures


if __name__ == "__main__":
    sys.exit(main())
