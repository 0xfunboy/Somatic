#!/usr/bin/env python3
from __future__ import annotations

import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.mutation import MutationSandbox


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as repo_td, tempfile.TemporaryDirectory() as muts_td:
        repo = Path(repo_td)
        write(repo / "server.py", "print('ok')\n")
        write(repo / ".env", "SECRET=1\n")
        write(repo / "logs" / "x.log", "x\n")
        write(repo / "weights" / "a.pt", "bin\n")
        write(repo / "data" / "mind" / "trace.jsonl", "{}\n")
        write(repo / "data" / "runtime" / "actuation.jsonl", "{}\n")
        write(repo / "data" / "journal" / "hot" / "cognitive_trace.hot.jsonl", "{}\n")
        write(repo / "soma_core" / "core.py", "x = 1\n")
        write(repo / "sensor_providers" / "base.py", "x = 1\n")
        for name in (
            "test_metabolism.py",
            "test_internal_loop.py",
            "test_reward_engine.py",
            "test_power_policy.py",
            "test_vector_interpreter.py",
            "test_growth_recovery_switch.py",
            "test_mutation_reward.py",
            "test_phase9_introspection.py",
            "test_answer_finalizer.py",
            "test_output_filter.py",
            "test_relevance_filter.py",
            "test_growth_engine.py",
            "test_baselines.py",
            "test_bios_loop.py",
            "test_mutation_sandbox.py",
            "test_cpp_bridge.py",
            "test_life_drive.py",
            "test_experience_distiller.py",
            "test_command_planner.py",
            "test_telemetry_relevance.py",
            "test_phase8_regressions.py",
        ):
            write(repo / "scripts" / name, "print('PASS')\n")
        sandbox = MutationSandbox(repo_root=repo, mutation_root=muts_td)
        created = sandbox.create_sandbox("test")
        sandbox_path = Path(created["sandbox_path"])
        failures += check("creates sandbox", created["ok"] and sandbox_path.exists(), str(created))
        failures += check("excludes .env", not (sandbox_path / ".env").exists())
        failures += check("excludes logs", not (sandbox_path / "logs").exists())
        failures += check("excludes weights", not (sandbox_path / "weights").exists())
        failures += check("excludes hot jsonl", not (sandbox_path / "data" / "journal" / "hot" / "cognitive_trace.hot.jsonl").exists())
        tests = sandbox.run_tests(sandbox_path)
        failures += check("runs py_compile in sandbox", tests["ok"], str(tests))
        apply = sandbox.apply_mutation_to_sandbox(sandbox_path, {"file_changes": {".env": "BAD=1\n"}})
        failures += check("rejects forbidden mutation", apply["ok"] is False and ".env" in apply["forbidden_files"], str(apply))
        report = sandbox.evaluate_mutation(sandbox_path, {"objective": "noop", "file_changes": {}}, tests)
        report_path = sandbox.write_report(report)
        failures += check("writes report", report_path.exists(), str(report_path))
        allowed, blockers = sandbox.can_mutate({"growth_allowed": True, "recovery_required": False, "self_integrity": 0.9, "sensor_confidence_calibrated": 0.9}, {}, {"rolling_score": 0.2})
        failures += check("mutation can be allowed when stable", allowed is True and blockers == [], str(blockers))
        failures += check("live repo unchanged", (repo / "server.py").read_text(encoding="utf-8") == "print('ok')\n")
    return failures



if __name__ == "__main__":
    sys.exit(main())
