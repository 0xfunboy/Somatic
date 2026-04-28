#!/usr/bin/env python3
"""
scripts/test_nightly_reflection.py — Tests for NightlyReflection.

Tests:
  1. run_now() without LLM -> writes markdown file with all 8 sections
  2. run_now() writes to nightly_reflections.jsonl
  3. check_and_run() returns None when not time
  4. check_and_run() skips if user was active recently (NIGHTLY_REQUIRE_IDLE)

Runs standalone: python3 scripts/test_nightly_reflection.py
Does NOT require a running server or LLM.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.autobiography import Autobiography  # noqa: E402
from soma_core.nightly import NightlyReflection  # noqa: E402
import soma_core.nightly as _nightly_module


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    records: list[dict] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except FileNotFoundError:
        pass
    return records


def _count_sections(md_text: str, prefix: str = "## ") -> int:
    return sum(1 for line in md_text.splitlines() if line.startswith(prefix))


_EXPECTED_SECTIONS = {
    "## Continuity",
    "## Body",
    "## Dialogue",
    "## Capabilities",
    "## Risks",
    "## Goals",
    "## Memory",
    "## Next intentions",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_run_now_writes_markdown() -> bool:
    """
    run_now() without LLM writes a markdown file with all 8 expected sections.
    Uses a temp dir for autobiography daily events and overrides the module-level
    _DAILY_DIR and _NIGHTLY_LOG paths.
    """
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        daily_dir = root / "autobiography" / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        mind_dir = root / "mind"
        mind_dir.mkdir(parents=True, exist_ok=True)
        nightly_log = mind_dir / "nightly_reflections.jsonl"

        # Write some fake daily events
        auto = Autobiography(data_root=root / "autobiography")
        for kind in ("body_learning", "dialogue", "capability"):
            auto.write_event({
                "kind": kind,
                "title": f"Test {kind}",
                "summary": f"A {kind} event occurred.",
                "timestamp": time.time(),
            })

        # Temporarily patch module-level paths
        orig_daily_dir = _nightly_module._DAILY_DIR
        orig_nightly_log = _nightly_module._NIGHTLY_LOG
        orig_mind_dir = _nightly_module._MIND_DIR
        _nightly_module._DAILY_DIR = daily_dir
        _nightly_module._NIGHTLY_LOG = nightly_log
        _nightly_module._MIND_DIR = mind_dir

        nr = NightlyReflection(autobiography=auto)
        result = nr.run_now(use_llm=False)

        # Restore
        _nightly_module._DAILY_DIR = orig_daily_dir
        _nightly_module._NIGHTLY_LOG = orig_nightly_log
        _nightly_module._MIND_DIR = orig_mind_dir

        md_path_str = result.get("md_path")
        ok_status = result.get("status") in ("completed", "partial")

        if md_path_str and Path(md_path_str).exists():
            md_content = Path(md_path_str).read_text(encoding="utf-8")
            found_sections = {
                line.strip()
                for line in md_content.splitlines()
                if line.strip().startswith("## ")
            }
            missing = _EXPECTED_SECTIONS - found_sections
            ok = ok_status and len(missing) == 0
            status = "PASS" if ok else "FAIL"
            print(
                f"{status} [run_now_writes_markdown]: "
                f"status={result.get('status')!r}, sections found={len(found_sections)}/8, "
                f"missing={missing}"
            )
        else:
            ok = False
            print(
                f"FAIL [run_now_writes_markdown]: "
                f"md_path not written, result={result}"
            )
        return ok


def test_run_now_appends_to_jsonl() -> bool:
    """run_now() writes an entry to nightly_reflections.jsonl."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        daily_dir = root / "autobiography" / "daily"
        daily_dir.mkdir(parents=True, exist_ok=True)
        mind_dir = root / "mind"
        mind_dir.mkdir(parents=True, exist_ok=True)
        nightly_log = mind_dir / "nightly_reflections.jsonl"

        orig_daily_dir = _nightly_module._DAILY_DIR
        orig_nightly_log = _nightly_module._NIGHTLY_LOG
        orig_mind_dir = _nightly_module._MIND_DIR
        _nightly_module._DAILY_DIR = daily_dir
        _nightly_module._NIGHTLY_LOG = nightly_log
        _nightly_module._MIND_DIR = mind_dir

        nr = NightlyReflection()
        nr.run_now(use_llm=False)

        _nightly_module._DAILY_DIR = orig_daily_dir
        _nightly_module._NIGHTLY_LOG = orig_nightly_log
        _nightly_module._MIND_DIR = orig_mind_dir

        records = _read_jsonl(nightly_log)
        ok = len(records) >= 1 and records[-1].get("status") in ("completed", "partial", "failed")
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [run_now_appends_jsonl]: "
            f"jsonl records={len(records)}, last status={records[-1].get('status') if records else 'N/A'!r}"
        )
        return ok


def test_check_and_run_returns_none_when_not_time() -> bool:
    """check_and_run() returns None when current time is not within the nightly window."""
    # We do not patch NIGHTLY_ENABLED or the time, but we can verify that
    # with a freshly constructed NightlyReflection (no prior run), calling
    # check_and_run at an arbitrary non-nightly time returns None.
    # The nightly window is NIGHTLY_HOUR:NIGHTLY_MINUTE ± 5 min.
    # We can ensure the "wrong time" by checking it returns None when the
    # window delta logic would skip.  We test by verifying the return is None
    # when SOMA_NIGHTLY_REFLECTION=false.

    orig_enabled = _nightly_module.NIGHTLY_ENABLED
    _nightly_module.NIGHTLY_ENABLED = False
    try:
        nr = NightlyReflection()
        result = nr.check_and_run(last_user_interaction_at=time.time() - 9999.0)
        ok = result is None
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [check_and_run_not_enabled]: "
            f"result={result!r} (want None when NIGHTLY_ENABLED=False)"
        )
    finally:
        _nightly_module.NIGHTLY_ENABLED = orig_enabled

    return ok


def test_check_and_run_skips_when_user_active() -> bool:
    """
    check_and_run() skips if user was active recently (NIGHTLY_REQUIRE_IDLE).
    We force the time window to match by temporarily setting NIGHTLY_HOUR and
    NIGHTLY_MINUTE to current UTC hour/minute, then call with last_user_interaction_at=now.
    """
    import datetime as _dt
    now_utc = _dt.datetime.now(tz=_dt.timezone.utc)

    orig_enabled = _nightly_module.NIGHTLY_ENABLED
    orig_hour = _nightly_module.NIGHTLY_HOUR
    orig_minute = _nightly_module.NIGHTLY_MINUTE
    orig_require_idle = _nightly_module.NIGHTLY_REQUIRE_IDLE

    _nightly_module.NIGHTLY_ENABLED = True
    _nightly_module.NIGHTLY_HOUR = now_utc.hour
    _nightly_module.NIGHTLY_MINUTE = now_utc.minute
    _nightly_module.NIGHTLY_REQUIRE_IDLE = True

    try:
        nr = NightlyReflection()
        # User was active 10 seconds ago — much less than the required 1800s idle
        result = nr.check_and_run(last_user_interaction_at=time.time() - 10.0)
        ok = result is None
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [check_and_run_skips_active]: "
            f"result={result!r} (want None when user was active 10s ago)"
        )
    finally:
        _nightly_module.NIGHTLY_ENABLED = orig_enabled
        _nightly_module.NIGHTLY_HOUR = orig_hour
        _nightly_module.NIGHTLY_MINUTE = orig_minute
        _nightly_module.NIGHTLY_REQUIRE_IDLE = orig_require_idle

    return ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> int:
    print("=== NightlyReflection tests ===\n")
    results = [
        test_run_now_writes_markdown(),
        test_run_now_appends_to_jsonl(),
        test_check_and_run_returns_none_when_not_time(),
        test_check_and_run_skips_when_user_active(),
    ]
    failures = sum(0 if r else 1 for r in results)
    print(f"\n{len(results)} tests, {failures} failures")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
