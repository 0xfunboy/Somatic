#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.growth_engine import GrowthEngine


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def make_snapshot(real: bool = True) -> dict:
    return {"provider": {"is_real": real, "name": "linux", "source_quality": 0.9}}


def main() -> int:
    ge = GrowthEngine()
    failures = 0
    base_ctx = {
        "frontend_connected": True,
        "sample_minutes": 10.0,
        "baselines": {"keys": {"idle_cpu_percent": {"confidence": 0.8, "windows": 3, "samples": 120}, "cpu_temp_c": {"confidence": 0.8, "windows": 3, "samples": 120}, "disk_temp_c": {"confidence": 0.8, "windows": 3, "samples": 120}}},
        "command_agency": {"successful": 0, "categories": [], "regression_ok": False},
        "autobiography": {"lessons_count": 0, "operator_lessons_count": 0, "limitation_lessons_count": 0, "last_nightly_reflection": "", "empty_reflections": 0, "total_reflections": 100},
        "bios": {"run_count": 0, "useful_cycles": 0},
        "mutation": {"sandbox_root_exists": False, "sandbox_count": 0, "last_noop_ok": False, "rollback_ok": False},
        "cpp_bridge": {"status": "missing", "binary_exists": False, "smoke_ok": False, "last_error": "binary_missing"},
    }
    result = ge.evaluate(make_snapshot(True), {**base_ctx, "autobiography": {**base_ctx["autobiography"], "lessons_count": 0}})
    failures += check("raw reflection count alone does not advance", result["stage"] in {"verified_command_agency", "autobiographical_continuity"}, str(result))

    ctx2 = dict(base_ctx)
    result2 = ge.evaluate(make_snapshot(True), ctx2)
    failures += check("persisted baseline advances beyond sensed_body", result2["stage"] != "sensed_body", str(result2))
    failures += check("missing requirements listed", isinstance(result2["missing_requirements"], list) and len(result2["missing_requirements"]) > 0, str(result2["missing_requirements"]))
    failures += check("no stale two minutes text", "2+ minutes" not in result2["next_step"], result2["next_step"])

    ctx3 = dict(base_ctx)
    ctx3["command_agency"] = {"successful": 5, "categories": ["system", "network"], "regression_ok": True}
    result3 = ge.evaluate(make_snapshot(True), ctx3)
    failures += check("command agency needs three categories", result3["stage"] == "verified_command_agency", str(result3))

    ctx4 = dict(base_ctx)
    ctx4["command_agency"] = {"successful": 5, "categories": ["system", "network", "repo"], "regression_ok": True}
    ctx4["autobiography"] = {"lessons_count": 5, "operator_lessons_count": 2, "limitation_lessons_count": 1, "last_nightly_reflection": "done", "empty_reflections": 1, "total_reflections": 10}
    ctx4["bios"] = {"run_count": 2, "useful_cycles": 0}
    result4 = ge.evaluate(make_snapshot(True), ctx4)
    failures += check("BIOS stage requires BIOS history evidence", result4["stage"] == "autonomous_bios_loop", str(result4))
    return failures


if __name__ == "__main__":
    sys.exit(main())
