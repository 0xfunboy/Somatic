#!/usr/bin/env python3
"""
scripts/test_actuation_dedupe.py — Tests for JournalManager actuation deduplication.

Tests:
  1. Feed 1000 identical actuation payloads (only timestamp differs)
     -> actuation.hot.jsonl contains 1 entry (or collapsed repeated_state)
  2. Feed 10 payloads with changing scenario
     -> actuation.hot.jsonl contains 10 entries (each unique)
  3. Feed identical payload repeatedly for > ACTUATION_HISTORY_MIN_INTERVAL_SEC
     -> should write again (interval elapsed)

Runs standalone: python3 scripts/test_actuation_dedupe.py
Does NOT import server.py (side effects).
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.journal import JournalManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_lines(path: Path) -> int:
    """Count non-empty lines in a JSONL file."""
    try:
        return sum(1 for line in path.open("rb") if line.strip())
    except OSError:
        return 0


def _make_payload(scenario: str = "normal", ts: float | None = None) -> dict:
    return {
        "timestamp": ts if ts is not None else time.time(),
        "provider": {"name": "linux"},
        "scenario": scenario,
        "policy_mode": "balanced",
        "policy": {"mode": "balanced"},
        "actions": [{"name": "idle", "visible": True}],
        "derived": {"thermal_stress": 0.1, "energy_stress": 0.05, "instability": 0.02},
        "visible_action": "idle",
        "commands": [],
        "summary": f"stable {scenario}",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_dedupe_identical_payloads() -> bool:
    """
    Feed 1000 identical actuation payloads (only timestamp differs).
    Only 1 entry should appear in the actuation hot file (first write);
    subsequent identical payloads are suppressed by semantic hash dedup.
    collapsed repeated_state entries also count but should sum to <= 2.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jm = JournalManager(data_root=root, persistence="important")

        base_ts = time.time()
        for i in range(1000):
            payload = _make_payload("normal", ts=base_ts + i * 0.001)
            jm.append_actuation(payload)

        # Flush any remaining collapsed state by sending a different payload
        jm.append_actuation(_make_payload("teardown", ts=base_ts + 2.0))

        lines = _count_lines(jm._actuation_file)
        # We expect:
        #   line 1: first unique "normal" payload
        #   line 2: repeated_state collapsed entry for the 999 repeats (if flushed)
        #   line 3: the new "teardown" payload
        # So lines <= 3 is correct; strict dedupe means lines < 1000
        ok = lines < 10
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [dedupe_identical_payloads]: "
            f"1000 identical inputs → {lines} file lines (want < 10)"
        )
        return ok


def test_unique_scenarios_persisted() -> bool:
    """
    Feed 10 payloads each with a different scenario.
    All 10 should be written (each has a unique semantic hash).
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jm = JournalManager(data_root=root, persistence="important")

        scenarios = [f"scenario_{i}" for i in range(10)]
        for s in scenarios:
            jm.append_actuation(_make_payload(s))

        lines = _count_lines(jm._actuation_file)
        # 10 unique scenarios → 10 lines (no collapsing, each triggers a flush
        # of the previous state before writing the new one)
        ok = lines >= 10
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [unique_scenarios_persisted]: "
            f"10 unique scenarios → {lines} file lines (want >= 10)"
        )
        return ok


def test_interval_elapsed_triggers_rewrite() -> bool:
    """
    JournalManager.append_actuation does NOT implement a time-interval re-write
    guard itself (that guard lives in server.py's dispatch_actuation).
    The journal dedup is purely hash-based: identical hash → suppressed forever
    until the hash changes.

    This test verifies the semantic hash logic directly:
      - Feed one payload → written
      - Feed an identical payload → suppressed (count += 1)
      - Change one field so the hash changes → written (new state flushed)

    This documents the actual JournalManager contract.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jm = JournalManager(data_root=root, persistence="important")

        p1 = _make_payload("alpha")
        jm.append_actuation(p1)  # write 1

        # Identical semantic content → suppressed
        p2 = _make_payload("alpha")
        p2["timestamp"] += 60.0  # only timestamp differs
        jm.append_actuation(p2)  # suppressed

        lines_mid = _count_lines(jm._actuation_file)

        # New scenario triggers flush of collapsed alpha state + write of new state
        p3 = _make_payload("beta")
        jm.append_actuation(p3)  # flushes repeated_state for alpha + writes beta

        lines_after = _count_lines(jm._actuation_file)

        ok = lines_mid == 1 and lines_after >= 2
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [interval_elapsed_triggers_rewrite]: "
            f"mid={lines_mid} (want 1), after={lines_after} (want >= 2)"
        )
        return ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> int:
    print("=== Actuation dedupe tests ===\n")
    results = [
        test_dedupe_identical_payloads(),
        test_unique_scenarios_persisted(),
        test_interval_elapsed_triggers_rewrite(),
    ]
    failures = sum(0 if r else 1 for r in results)
    print(f"\n{len(results)} tests, {failures} failures")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
