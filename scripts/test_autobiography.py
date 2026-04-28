#!/usr/bin/env python3
"""
scripts/test_autobiography.py — Tests for the Autobiography module.

Tests:
  1. write_event()  — writes to daily JSONL
  2. write_daily_page() — generates markdown file
  3. get_recent_summary() — returns list
  4. get_identity_context_for_llm() — returns dict with required keys
  5. High-impact event -> also appears in milestones.json
  6. Reflection kind -> also appears in learned_lessons.json

Runs standalone: python3 scripts/test_autobiography.py
Does NOT require a running server or LLM.
"""
from __future__ import annotations

import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.autobiography import Autobiography  # noqa: E402


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


def _load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_write_event_to_daily_jsonl() -> bool:
    """write_event() writes to daily JSONL."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auto = Autobiography(data_root=root)

        event = {
            "kind": "dialogue",
            "title": "First contact",
            "summary": "The operator said hello.",
            "timestamp": time.time(),
        }
        auto.write_event(event)

        daily_dir = root / "daily"
        jsonl_files = list(daily_dir.glob("*.jsonl"))

        if not jsonl_files:
            print("FAIL [write_event]: no daily JSONL file created")
            return False

        records = _read_jsonl(jsonl_files[0])
        found = any(r.get("title") == "First contact" for r in records)
        ok = len(records) >= 1 and found
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [write_event]: "
            f"{len(records)} record(s) in daily JSONL, target event found={found}"
        )
        return ok


def test_write_daily_page() -> bool:
    """write_daily_page() generates a markdown file."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auto = Autobiography(data_root=root)

        auto.write_event({
            "kind": "capability",
            "title": "Learned ls",
            "summary": "Discovered ls command.",
            "timestamp": time.time(),
        })

        md_path = auto.write_daily_page()

        ok = md_path.exists() and md_path.stat().st_size > 0
        status = "PASS" if ok else "FAIL"
        content_preview = md_path.read_text(encoding="utf-8")[:100] if md_path.exists() else ""
        print(
            f"{status} [write_daily_page]: "
            f"md_path={md_path.name}, size={md_path.stat().st_size if md_path.exists() else 0}B"
            f"\n         preview: {content_preview!r}"
        )
        return ok


def test_get_recent_summary_returns_list() -> bool:
    """get_recent_summary() returns a list."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auto = Autobiography(data_root=root)

        for i in range(5):
            auto.write_event({
                "kind": "dialogue",
                "title": f"msg {i}",
                "summary": f"message {i}",
                "timestamp": time.time() + i,
            })

        result = auto.get_recent_summary(n_events=10)
        ok = isinstance(result, list) and len(result) >= 5
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [get_recent_summary]: "
            f"type={type(result).__name__}, len={len(result)} (want >= 5)"
        )
        return ok


def test_get_identity_context_for_llm_keys() -> bool:
    """get_identity_context_for_llm() returns dict with required keys."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auto = Autobiography(data_root=root)

        auto.update_self_narrative("current_stage", "early_embodiment")
        auto.update_self_narrative("last_insight", "CPU temp correlates with load.")
        auto.write_learned_lesson("High temp correlates with high load.", source="test", confidence=0.9)
        auto.add_unresolved_question("Why does instability spike on login?", context={})

        ctx = auto.get_identity_context_for_llm()

        required_keys = {"stage", "last_insight", "recent_lessons", "active_questions"}
        missing = required_keys - set(ctx.keys())
        has_stage = ctx.get("stage") == "early_embodiment"
        has_lessons = isinstance(ctx.get("recent_lessons"), list)
        has_questions = isinstance(ctx.get("active_questions"), list)

        ok = not missing and has_stage and has_lessons and has_questions
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [get_identity_context_for_llm]: "
            f"keys={set(ctx.keys())}, stage={ctx.get('stage')!r}, "
            f"lessons={ctx.get('recent_lessons')}, missing={missing}"
        )
        return ok


def test_high_impact_event_in_milestones() -> bool:
    """High-impact event -> also appears in milestones.json."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auto = Autobiography(data_root=root)

        auto.write_event({
            "kind": "milestone",
            "title": "First autonomous action",
            "summary": "Executed first shell command without prompting.",
            "impact": "high",
            "timestamp": time.time(),
        })

        milestones = _load_json(root / "milestones.json", [])
        found = any(m.get("title") == "First autonomous action" for m in milestones)
        ok = found and len(milestones) >= 1
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [high_impact_milestones]: "
            f"milestones count={len(milestones)}, target found={found}"
        )
        return ok


def test_reflection_in_learned_lessons() -> bool:
    """Reflection kind -> also appears in learned_lessons.json."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        auto = Autobiography(data_root=root)

        auto.write_event({
            "kind": "reflection",
            "title": "Thermal baseline",
            "summary": "Idle CPU temperature is approximately 36 Celsius.",
            "timestamp": time.time(),
        })

        lessons = _load_json(root / "learned_lessons.json", [])
        found = any(
            "36 Celsius" in (entry.get("lesson", "") or "")
            or "36" in (entry.get("lesson", "") or "")
            for entry in lessons
        )
        ok = len(lessons) >= 1 and found
        status = "PASS" if ok else "FAIL"
        print(
            f"{status} [reflection_in_lessons]: "
            f"lessons count={len(lessons)}, target found={found}, "
            f"lessons={[e.get('lesson','')[:60] for e in lessons]}"
        )
        return ok


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run_all() -> int:
    print("=== Autobiography tests ===\n")
    results = [
        test_write_event_to_daily_jsonl(),
        test_write_daily_page(),
        test_get_recent_summary_returns_list(),
        test_get_identity_context_for_llm_keys(),
        test_high_impact_event_in_milestones(),
        test_reflection_in_learned_lessons(),
    ]
    failures = sum(0 if r else 1 for r in results)
    print(f"\n{len(results)} tests, {failures} failures")
    return failures


if __name__ == "__main__":
    sys.exit(run_all())
