#!/usr/bin/env python3
"""
scripts/test_journal_compaction.py — Tests for JournalManager deduplication and compaction.

Tests:
  1. append_trace 1000 perception events (noisy phase) in "important" mode
     -> hot file grows by 0 lines (noisy phases suppressed)
  2. append_trace 10 command_executed events
     -> hot file grows by ~10 lines (important phase persisted)
  3. compact_now() on a temp dir with 500 duplicate actuation lines
     -> returns compression_ratio > 0.9
  4. rotate_if_needed() when hot file exceeds threshold
     -> file gets rotated to archive

Runs standalone: python3 scripts/test_journal_compaction.py
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

# Make sure soma_core is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.journal import JournalManager  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _count_lines(path: Path) -> int:
    try:
        return sum(1 for line in path.open("rb") if line.strip())
    except OSError:
        return 0


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_noisy_phases_suppressed() -> bool:
    """
    Feed 1000 perception events (noisy phase) to a JournalManager with
    persistence='important'.  The hot trace file should grow by 0 lines.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jm = JournalManager(data_root=root, persistence="important")
        before = _count_lines(jm._trace_file)

        for i in range(1000):
            jm.append_trace({
                "phase": "perception",
                "timestamp": time.time(),
                "summary": f"tick {i}",
                "level": "debug",
            })

        after = _count_lines(jm._trace_file)
        grew = after - before
        ok = grew == 0
        status = "PASS" if ok else "FAIL"
        print(f"{status} [noisy_phases_suppressed]: file grew by {grew} lines (want 0)")
        return ok


def test_important_phases_persisted() -> bool:
    """
    Feed 10 command_executed events (important phase).
    The hot trace file should grow by ~10 lines.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jm = JournalManager(data_root=root, persistence="important")
        before = _count_lines(jm._trace_file)

        for i in range(10):
            jm.append_trace({
                "phase": "command_executed",
                "timestamp": time.time(),
                "summary": f"cmd_{i} completed",
                "level": "info",
                # Make each unique so dedup doesn't suppress
                "cmd_index": i,
            })

        after = _count_lines(jm._trace_file)
        grew = after - before
        # Semantic hash deduplicates on phase + summary_prefix[:40] + level,
        # so with distinct summaries all 10 should be written.
        ok = grew >= 8  # allow a tiny margin in case hashes collide by prefix
        status = "PASS" if ok else "FAIL"
        print(f"{status} [important_phases_persisted]: file grew by {grew} lines (want ~10)")
        return ok


def test_compact_now_ratio() -> bool:
    """
    Write 500 duplicate actuation lines to the hot actuation file, then call
    compact_now(). Returned compression_ratio should be > 0.9.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        jm = JournalManager(data_root=root, persistence="important")

        # Write 500 identical lines directly to the actuation hot file
        sample_payload = {
            "timestamp": 1700000000.0,
            "provider": {"name": "linux"},
            "scenario": "normal",
            "policy_mode": "balanced",
            "actions": [{"name": "idle", "visible": True}],
            "summary": "stable state",
        }
        line = json.dumps(sample_payload, ensure_ascii=True) + "\n"
        with jm._actuation_file.open("w", encoding="utf-8") as f:
            for _ in range(500):
                f.write(line)

        report = jm.compact_now(source_files=[jm._actuation_file])
        ratio = report.get("compression_ratio", 0.0)
        ok = ratio > 0.9
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [compact_now_ratio]: compression_ratio={ratio:.4f} "
            f"(want > 0.9), unique_states={report.get('unique_states')}"
        )
        return ok


def test_rotate_if_needed() -> bool:
    """
    Create a hot file that exceeds hot_max_mb, call rotate_if_needed().
    The hot file should be emptied and an archive gz should appear.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        # Set a very low threshold so we can trigger rotation without writing GBs
        jm = JournalManager(data_root=root, persistence="important", hot_max_mb=0.00001)

        # Write a few KB to the trace file to exceed the tiny threshold
        line = json.dumps({"phase": "command_executed", "summary": "x" * 200}) + "\n"
        with jm._trace_file.open("w", encoding="utf-8") as f:
            for _ in range(20):
                f.write(line)

        size_before = jm._trace_file.stat().st_size if jm._trace_file.exists() else 0
        jm.rotate_if_needed()
        size_after = jm._trace_file.stat().st_size if jm._trace_file.exists() else 0

        # After rotation, the hot file should be empty (0 bytes)
        # and at least one gz file should exist in the archive dir
        archive_gzs = list(jm._archive_dir.rglob("*.jsonl.gz"))
        rotated = size_after == 0 and size_before > 0 and len(archive_gzs) > 0
        ok = rotated
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [rotate_if_needed]: "
            f"before={size_before}B after={size_after}B gz_files={len(archive_gzs)}"
        )
        return ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> int:
    print("=== JournalManager compaction tests ===\n")
    results = [
        test_noisy_phases_suppressed(),
        test_important_phases_persisted(),
        test_compact_now_ratio(),
        test_rotate_if_needed(),
    ]
    failures = sum(0 if r else 1 for r in results)
    print(f"\n{len(results)} tests, {failures} failures")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
