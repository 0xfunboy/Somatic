#!/usr/bin/env python3
"""
scripts/test_self_improvement_workflow.py — Tests for SelfImprovementWorkflow.

Tests:
  1. propose_change() -> adds to queue
  2. get_queued_proposals() -> returns proposals
  3. apply_and_validate() with VALID content -> passed=True, rolled_back=False
  4. apply_and_validate() with INVALID Python -> passed=False, rolled_back=True, file restored
  5. get_queue_summary() -> correct counts
  6. Forbidden file guard: .env, executor.py -> rejected

Safe approach for tests 3 & 4:
  - Create a real temp .py file inside the repo's data/ dir (within _REPO_ROOT),
    outside any forbidden prefix.
  - The SelfImprovementWorkflow resolves paths relative to _REPO_ROOT and
    checks forbidden prefixes at resolution time.
  - We use a file under data/mind/si_test_<rand>.py — not forbidden.
  - Restore / delete the temp file after each test.

Runs standalone: python3 scripts/test_self_improvement_workflow.py
Does NOT require a running server or LLM.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import soma_core.self_improvement as _si_module
from soma_core.self_improvement import (  # noqa: E402
    SelfImprovementWorkflow,
    _load_queue,
    _save_queue,
    _REPO_ROOT,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_test_rel() -> str:
    """Return a unique relative path for a test .py file inside the repo."""
    # Place under scripts/ — not in a forbidden prefix
    uid = uuid.uuid4().hex[:8]
    return f"scripts/_si_test_{uid}.py"


def _make_workflow_with_tmp_queue() -> tuple[SelfImprovementWorkflow, Path]:
    """
    Return a SelfImprovementWorkflow that uses a temp queue file.
    Also returns the temp queue path for cleanup.
    """
    # We patch the module-level _QUEUE_FILE so _load_queue/_save_queue
    # use a throwaway file.  We restore it after the test.
    tmp = tempfile.NamedTemporaryFile(suffix=".json", delete=False)
    tmp.write(b"[]")
    tmp.close()
    queue_path = Path(tmp.name)
    _si_module._QUEUE_FILE = queue_path
    wf = SelfImprovementWorkflow()
    return wf, queue_path


def _restore_queue_path(original: Path) -> None:
    _si_module._QUEUE_FILE = original


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_propose_change_adds_to_queue() -> bool:
    """propose_change() creates a proposal and adds it to the queue."""
    orig_queue = _si_module._QUEUE_FILE
    wf, tmp_q = _make_workflow_with_tmp_queue()
    try:
        result = wf.propose_change(
            problem="Performance regression in policy loop",
            goal="Reduce policy evaluation latency by 20%",
            affected_files=["soma_core/policy.py"],
            risk="low",
        )
        ok_result = isinstance(result, dict) and result.get("status") == "queued"
        queue = _load_queue()
        found = any(p.get("id") == result.get("id") for p in queue)
        ok = ok_result and found and len(queue) >= 1
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [propose_change]: "
            f"proposal id={result.get('id')!r}, queue len={len(queue)}, found={found}"
        )
        return ok
    finally:
        _restore_queue_path(orig_queue)
        tmp_q.unlink(missing_ok=True)


def test_get_queued_proposals_returns_list() -> bool:
    """get_queued_proposals() returns only queued proposals."""
    orig_queue = _si_module._QUEUE_FILE
    wf, tmp_q = _make_workflow_with_tmp_queue()
    try:
        wf.propose_change(
            problem="Test problem",
            goal="Test goal",
            affected_files=["soma_core/policy.py"],
        )
        proposals = wf.get_queued_proposals()
        ok = isinstance(proposals, list) and len(proposals) >= 1
        all_queued = all(p.get("status") == "queued" for p in proposals)
        ok = ok and all_queued
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [get_queued_proposals]: "
            f"count={len(proposals)}, all_queued={all_queued}"
        )
        return ok
    finally:
        _restore_queue_path(orig_queue)
        tmp_q.unlink(missing_ok=True)


def test_apply_valid_content_passes() -> bool:
    """apply_and_validate() with valid Python content -> passed=True, rolled_back=False."""
    orig_queue = _si_module._QUEUE_FILE
    wf, tmp_q = _make_workflow_with_tmp_queue()

    rel_path = _unique_test_rel()
    abs_path = _REPO_ROOT / rel_path
    original_content = "# original\nX = 0\n"
    new_content = "# valid\nX = 1\n"

    # Create the original file
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(original_content, encoding="utf-8")

    try:
        proposal = wf.propose_change(
            problem="Increment X",
            goal="Set X to 1",
            affected_files=[rel_path],
            risk="low",
        )
        proposal_id = proposal.get("id", "")

        # Disable test-script running to avoid full validation suite
        orig_require_tests = _si_module.SI_REQUIRE_TESTS
        _si_module.SI_REQUIRE_TESTS = False

        report = wf.apply_and_validate(proposal_id, {rel_path: new_content})

        _si_module.SI_REQUIRE_TESTS = orig_require_tests

        passed = report.get("passed", False)
        rolled_back = report.get("rolled_back", False)
        current_content = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
        file_updated = current_content == new_content

        ok = passed and not rolled_back and file_updated
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [apply_valid_content]: "
            f"passed={passed}, rolled_back={rolled_back}, "
            f"file_updated={file_updated}, errors={report.get('errors', [])}"
        )
        return ok
    finally:
        _restore_queue_path(orig_queue)
        tmp_q.unlink(missing_ok=True)
        abs_path.unlink(missing_ok=True)


def test_apply_invalid_python_rolls_back() -> bool:
    """
    apply_and_validate() with invalid Python syntax ->
    passed=False, rolled_back=True, original file content restored.
    """
    orig_queue = _si_module._QUEUE_FILE
    wf, tmp_q = _make_workflow_with_tmp_queue()

    rel_path = _unique_test_rel()
    abs_path = _REPO_ROOT / rel_path
    original_content = "# original\nY = 0\n"
    # Invalid Python: broken def signature
    broken_content = "def broken(: pass\n"

    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text(original_content, encoding="utf-8")

    try:
        proposal = wf.propose_change(
            problem="Broken change",
            goal="Introduce syntax error",
            affected_files=[rel_path],
            risk="low",
        )
        proposal_id = proposal.get("id", "")

        orig_require_tests = _si_module.SI_REQUIRE_TESTS
        orig_auto_rollback = _si_module.SI_AUTO_ROLLBACK
        _si_module.SI_REQUIRE_TESTS = False
        _si_module.SI_AUTO_ROLLBACK = True

        report = wf.apply_and_validate(proposal_id, {rel_path: broken_content})

        _si_module.SI_REQUIRE_TESTS = orig_require_tests
        _si_module.SI_AUTO_ROLLBACK = orig_auto_rollback

        passed = report.get("passed", False)
        rolled_back = report.get("rolled_back", False)
        restored_content = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
        file_restored = restored_content == original_content

        ok = not passed and rolled_back and file_restored
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [apply_invalid_python]: "
            f"passed={passed}, rolled_back={rolled_back}, "
            f"file_restored={file_restored}, errors={report.get('errors', [])[:2]}"
        )
        return ok
    finally:
        _restore_queue_path(orig_queue)
        tmp_q.unlink(missing_ok=True)
        abs_path.unlink(missing_ok=True)


def test_get_queue_summary_counts() -> bool:
    """get_queue_summary() returns correct counts after proposals and apply."""
    orig_queue = _si_module._QUEUE_FILE
    wf, tmp_q = _make_workflow_with_tmp_queue()

    rel_path = _unique_test_rel()
    abs_path = _REPO_ROOT / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("# original\nZ = 0\n", encoding="utf-8")

    try:
        # Proposal 1: queued only
        wf.propose_change(
            problem="Queued proposal",
            goal="Will remain queued",
            affected_files=["soma_core/policy.py"],
        )

        # Proposal 2: apply (valid)
        p2 = wf.propose_change(
            problem="Applied proposal",
            goal="Will be applied",
            affected_files=[rel_path],
        )

        orig_require_tests = _si_module.SI_REQUIRE_TESTS
        _si_module.SI_REQUIRE_TESTS = False

        wf.apply_and_validate(p2["id"], {rel_path: "# valid\nZ = 1\n"})

        _si_module.SI_REQUIRE_TESTS = orig_require_tests

        summary = wf.get_queue_summary()
        ok = (
            isinstance(summary, dict)
            and summary.get("total", 0) >= 2
            and summary.get("queued", 0) >= 1
            and summary.get("done", 0) >= 1
        )
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [get_queue_summary]: "
            f"total={summary.get('total')}, queued={summary.get('queued')}, "
            f"done={summary.get('done')}, summary={summary}"
        )
        return ok
    finally:
        _restore_queue_path(orig_queue)
        tmp_q.unlink(missing_ok=True)
        abs_path.unlink(missing_ok=True)


def test_forbidden_paths_rejected() -> bool:
    """Forbidden paths (.env, executor.py) are rejected by apply_and_validate()."""
    orig_queue = _si_module._QUEUE_FILE
    wf, tmp_q = _make_workflow_with_tmp_queue()
    try:
        forbidden_cases = [
            ".env",
            "soma_core/executor.py",
        ]
        all_ok = True
        for forbidden_path in forbidden_cases:
            p = wf.propose_change(
                problem="Test forbidden",
                goal="Modify forbidden file",
                affected_files=[forbidden_path],
            )
            proposal_id = p.get("id", "")

            orig_require_tests = _si_module.SI_REQUIRE_TESTS
            _si_module.SI_REQUIRE_TESTS = False

            report = wf.apply_and_validate(proposal_id, {forbidden_path: "# hacked\n"})

            _si_module.SI_REQUIRE_TESTS = orig_require_tests

            # Should have errors about forbidden/cannot-resolve and not pass
            has_error = len(report.get("errors", [])) > 0
            not_passed = not report.get("passed", False)
            ok_case = has_error and not_passed
            if not ok_case:
                all_ok = False
            print(
                f"  {'OK' if ok_case else 'FAIL'} forbidden={forbidden_path!r}: "
                f"errors={report.get('errors', [])[:1]}, passed={report.get('passed')}"
            )

        status = "PASS" if all_ok else "FAIL"
        print(f"{status} [forbidden_paths_rejected]")
        return all_ok
    finally:
        _restore_queue_path(orig_queue)
        tmp_q.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> int:
    print("=== SelfImprovementWorkflow tests ===\n")
    results = [
        test_propose_change_adds_to_queue(),
        test_get_queued_proposals_returns_list(),
        test_apply_valid_content_passes(),
        test_apply_invalid_python_rolls_back(),
        test_get_queue_summary_counts(),
        test_forbidden_paths_rejected(),
    ]
    failures = sum(0 if r else 1 for r in results)
    print(f"\n{len(results)} tests, {failures} failures")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
