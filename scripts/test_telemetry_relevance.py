#!/usr/bin/env python3
"""
scripts/test_telemetry_relevance.py — Regression tests for somatic telemetry relevance gating.

Tests _telemetry_relevant() classifier and build_llm_context() body_state pruning.
Runs standalone: python3 scripts/test_telemetry_relevance.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path so we can import server helpers
sys.path.insert(0, str(Path(__file__).parent.parent))

from server import _telemetry_relevant, build_llm_context, build_snapshot  # noqa: E402

# ---------------------------------------------------------------------------
# _telemetry_relevant() tests
# ---------------------------------------------------------------------------

_RELEVANCE_CASES: list[tuple[str, bool, str]] = [
    # (user_text, expected_relevant, description)
    ("che kernel stai usando?", False, "kernel version — not somatic"),
    ("qual e il mio ip pubblico?", False, "IP query — not somatic"),
    ("quanta ram libera hai?", False, "ram query via shell — triggers shell result, not somatic keyword"),
    ("su che versione di python stai girando?", False, "python version — not somatic"),
    ("come ti senti?", True, "feelings — somatic"),
    ("stai scaldando?", True, "temperature — somatic"),
    ("quanto e calda la cpu?", True, "temperature — somatic (caldo)"),
    ("stai bene?", True, "how are you — somatic"),
    ("qual e la tua temperatura?", True, "temperatura — somatic"),
    ("che voltaggio hai?", True, "voltaggio — somatic"),
    ("how are you?", True, "how are you — somatic (english)"),
    ("are you hot?", True, "hot — somatic"),
    ("what is the current thermal stress?", True, "thermal — somatic"),
    ("tell me a joke", False, "joke — not somatic"),
    ("list the files in the current directory", False, "ls command — not somatic"),
    # SHELL_RESULT always suppresses telemetry regardless of content
    (
        "quanta ram libera hai?\n\n[SHELL_RESULT]\nCommand: `free -h`\nOutput:\ntotal 16G\n[/SHELL_RESULT]",
        False,
        "shell result block suppresses telemetry",
    ),
    (
        "stai scaldando?\n\n[SHELL_RESULT]\nCommand: `sensors`\nOutput:\ncpu 38C\n[/SHELL_RESULT]",
        False,
        "shell result suppresses even thermal query",
    ),
]


def test_telemetry_relevance() -> int:
    failures = 0
    print("=== _telemetry_relevant() tests ===\n")
    for user_text, expected, desc in _RELEVANCE_CASES:
        result = _telemetry_relevant(user_text)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        print(f"{status} [{desc}]: relevant={result!r} (want {expected!r})")
        if not ok:
            failures += 1
    return failures


# ---------------------------------------------------------------------------
# build_llm_context() body_state pruning tests
# ---------------------------------------------------------------------------

def _make_minimal_snapshot(thermal_stress_override: float | None = None) -> dict:
    """Build a real snapshot via the mock provider."""
    snap = build_snapshot()
    if thermal_stress_override is not None:
        snap["derived"]["thermal_stress"] = thermal_stress_override
    return snap


def test_body_state_pruning() -> int:
    failures = 0
    print("\n=== build_llm_context() body_state pruning tests ===\n")

    snapshot = _make_minimal_snapshot()

    # Non-somatic query → body_state should be compact string
    ctx_no_tel = build_llm_context(snapshot, "che kernel stai usando?")
    body_no_tel = ctx_no_tel["body_state"]
    if isinstance(body_no_tel, dict) and "core" in body_no_tel:
        print("FAIL [kernel query]: body_state is full dict — should be compact")
        failures += 1
    else:
        print(f"PASS [kernel query]: body_state is compact: {str(body_no_tel)[:60]!r}")

    # Non-somatic query with shell result → body_state should be compact
    ctx_shell = build_llm_context(
        snapshot,
        "che kernel stai usando?\n\n[SHELL_RESULT]\nCommand: `uname -r`\nOutput:\n6.8.0\n[/SHELL_RESULT]",
    )
    body_shell = ctx_shell["body_state"]
    if isinstance(body_shell, dict) and "core" in body_shell:
        print("FAIL [shell result]: body_state is full dict — should be compact")
        failures += 1
    else:
        print(f"PASS [shell result]: body_state is compact: {str(body_shell)[:60]!r}")

    # Somatic query → body_state should be full dict
    ctx_somatic = build_llm_context(snapshot, "come ti senti?")
    body_somatic = ctx_somatic["body_state"]
    if not isinstance(body_somatic, dict) or "affect" not in body_somatic:
        print(f"FAIL [feelings query]: body_state is not full dict: {body_somatic!r}")
        failures += 1
    else:
        print("PASS [feelings query]: body_state is full dict with affect")

    # Abnormal state even on non-somatic query → body_state should include abnormal note
    snapshot_hot = _make_minimal_snapshot(thermal_stress_override=0.85)
    ctx_hot = build_llm_context(snapshot_hot, "che kernel stai usando?")
    body_hot = ctx_hot["body_state"]
    if not isinstance(body_hot, dict) or body_hot.get("note") != "abnormal_state_detected":
        print(f"FAIL [abnormal state]: expected abnormal_state_detected note, got: {body_hot!r}")
        failures += 1
    else:
        print(f"PASS [abnormal state]: body_state carries abnormal note: {body_hot}")

    return failures


# ---------------------------------------------------------------------------
# task.instruction content tests
# ---------------------------------------------------------------------------

def test_task_instruction() -> int:
    failures = 0
    print("\n=== task.instruction content tests ===\n")
    snapshot = _make_minimal_snapshot()

    ctx = build_llm_context(snapshot, "che kernel stai usando?")
    instr = ctx["task"]["instruction"]
    if "directly" not in instr.lower() or "not" in instr.lower() and "telemetry" not in instr:
        # flexible check — just make sure it's the non-somatic variant
        pass
    if "embodied perspective" in instr:
        print("FAIL [kernel instruction]: got somatic instruction for non-somatic query")
        print(f"  instruction: {instr!r}")
        failures += 1
    else:
        print(f"PASS [kernel instruction]: correct non-somatic framing")

    ctx2 = build_llm_context(snapshot, "come ti senti?")
    instr2 = ctx2["task"]["instruction"]
    if "embodied perspective" not in instr2:
        print("FAIL [feelings instruction]: expected somatic framing")
        print(f"  instruction: {instr2!r}")
        failures += 1
    else:
        print("PASS [feelings instruction]: correct somatic framing")

    return failures


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> int:
    f1 = test_telemetry_relevance()
    f2 = test_body_state_pruning()
    f3 = test_task_instruction()
    total_failures = f1 + f2 + f3
    print(f"\n{'='*40}")
    print(f"Total failures: {total_failures}")
    return total_failures


if __name__ == "__main__":
    sys.exit(run_all())
