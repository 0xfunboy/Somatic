"""
soma_core/autobiography.py — Meaningful autobiographical memory for Latent Somatic.

Stores only durable events, lessons, operator corrections, limitations, and
meaningful stage changes. Nominal repeated state is rejected.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent.resolve()
_SELF_MODEL_FILE = _REPO_ROOT / "data" / "mind" / "self_model.json"


def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _date_str(dt: datetime | None = None) -> str:
    return (dt or _utc_now()).strftime("%Y-%m-%d")


def _ts_prefix() -> str:
    return _utc_now().strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _event_signature(event: dict[str, Any]) -> str:
    raw = "|".join(
        str(event.get(key) or "").strip().lower()
        for key in ("kind", "title", "summary")
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_autobiographical(event: dict[str, Any]) -> tuple[bool, str]:
    kind = str(event.get("kind") or "").strip().lower()
    title = str(event.get("title") or "").strip()
    summary = str(event.get("summary") or "").strip()
    text = f"{title} {summary}".lower()
    if not kind or not summary:
        return False, "missing_kind_or_summary"
    if any(mark in text for mark in ("nominal state", "stable voltage", "unchanged temp", "comfort score", "policy repeated")):
        return False, "nominal_repetition"
    allowed = {
        "lesson",
        "operator_correction",
        "dialogue",
        "capability",
        "limitation",
        "failure",
        "self_modification",
        "baseline",
        "body_learning",
        "recovery",
        "milestone",
        "bios_task",
        "mutation",
        "nightly_reflection",
        "reflection",
    }
    if kind in allowed:
        return True, kind
    if "blocked" in text and "policy" in text:
        return True, "blocked_risky_command"
    if "abnormal" in text or "recovery" in text:
        return True, "body_transition"
    return False, "kind_not_meaningful"


_KIND_LABELS: dict[str, str] = {
    "body_learning": "Body Learning",
    "dialogue": "Dialogue",
    "capability": "Capability",
    "self_modification": "Self Modification",
    "reflection": "Reflection",
    "milestone": "Milestone",
    "failure": "Failure",
    "recovery": "Recovery",
    "lesson": "Lesson",
    "operator_correction": "Operator Correction",
    "bios_task": "BIOS Task",
    "mutation": "Mutation",
    "nightly_reflection": "Nightly Reflection",
}


def _render_event_block(event: dict) -> str:
    kind = event.get("kind", "unknown")
    title = event.get("title", "(untitled)")
    summary = event.get("summary", "")
    evidence = event.get("evidence") or []
    follow_up = event.get("follow_up")
    emotional_tone = event.get("emotional_tone", "")
    impact = event.get("impact", "")
    ts = event.get("timestamp")
    repeat_count = int(event.get("repeat_count", 1))
    if ts is not None:
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            ts_str = dt.strftime("%H:%M:%S UTC")
        except (ValueError, OSError):
            ts_str = str(ts)
    else:
        ts_str = ""
    label = _KIND_LABELS.get(kind, kind.replace("_", " ").title())
    header = f"[{label}] {title}"
    if ts_str:
        header += f" *{ts_str}*"
    lines: list[str] = [f"## {header}", ""]
    meta = []
    if emotional_tone:
        meta.append(f"Tone: **{emotional_tone}**")
    if impact:
        meta.append(f"Impact: **{impact}**")
    if repeat_count > 1:
        meta.append(f"Count: **{repeat_count}**")
    if meta:
        lines.append("  ".join(meta))
        lines.append("")
    if summary:
        lines.append(summary)
        lines.append("")
    if evidence:
        lines.append("Evidence:")
        for item in evidence:
            if isinstance(item, dict):
                for k, v in item.items():
                    lines.append(f"- {k}: {v}")
            else:
                lines.append(f"- {item}")
        lines.append("")
    if follow_up:
        lines.append("Next:")
        lines.append(str(follow_up))
        lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_daily_markdown(date_str: str, events: list[dict]) -> str:
    lines: list[str] = [f"# {date_str}", ""]
    if not events:
        lines.append("*No meaningful autobiographical events recorded for this day.*")
        lines.append("")
        return "\n".join(lines)
    for event in events:
        lines.append(_render_event_block(event))
    return "\n".join(lines)


class Autobiography:
    def __init__(self, data_root: Path | None = None) -> None:
        self._root = Path(data_root or (_REPO_ROOT / "data" / "autobiography"))
        self._daily_dir = self._root / "daily"
        self._timeline_file = self._root / "timeline.md"
        self._milestones_file = self._root / "milestones.json"
        self._narrative_file = self._root / "self_narrative.json"
        self._questions_file = self._root / "unresolved_questions.json"
        self._lessons_file = self._root / "learned_lessons.json"
        self._lock = threading.Lock()
        self._root.mkdir(parents=True, exist_ok=True)
        self._daily_dir.mkdir(parents=True, exist_ok=True)

    def _jsonl_path(self, date_str: str) -> Path:
        return self._daily_dir / f"{date_str}.jsonl"

    def _md_path(self, date_str: str) -> Path:
        return self._daily_dir / f"{date_str}.md"

    def _append_jsonl(self, path: Path, record: dict) -> None:
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _read_jsonl(self, path: Path) -> list[dict]:
        records: list[dict] = []
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        except FileNotFoundError:
            pass
        return records

    def _rewrite_jsonl(self, path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = "\n".join(json.dumps(item, ensure_ascii=False) for item in records)
        path.write_text(text + ("\n" if text else ""), encoding="utf-8")

    def write_event(self, event: dict) -> dict[str, Any]:
        return self.write_meaningful_event(event)

    def write_meaningful_event(self, event: dict) -> dict[str, Any]:
        event = dict(event)
        event.setdefault("timestamp", time.time())
        ok, reason = is_autobiographical(event)
        if not ok:
            return {"stored": False, "reason": reason}
        ts = float(event["timestamp"])
        dt = datetime.fromtimestamp(ts, tz=timezone.utc)
        date_key = _date_str(dt)
        event["signature"] = _event_signature(event)
        event.setdefault("repeat_count", 1)
        event.setdefault("last_seen", ts)
        with self._lock:
            path = self._jsonl_path(date_key)
            records = self._read_jsonl(path)
            for idx in range(len(records) - 1, -1, -1):
                existing = records[idx]
                if existing.get("signature") != event["signature"]:
                    continue
                last_seen = float(existing.get("last_seen") or existing.get("timestamp") or 0.0)
                if ts - last_seen <= 3600.0:
                    existing["repeat_count"] = int(existing.get("repeat_count", 1)) + 1
                    existing["last_seen"] = ts
                    self._rewrite_jsonl(path, records)
                    self.write_daily_page(date_key)
                    return {"stored": False, "reason": "duplicate", "event": existing}
            self._append_jsonl(path, event)
            self.write_daily_page(date_key)
            if event.get("impact") == "high":
                milestones = _load_json(self._milestones_file, [])
                milestones.append({
                    "timestamp": ts,
                    "kind": event.get("kind"),
                    "title": event.get("title", ""),
                    "summary": event.get("summary", ""),
                })
                _save_json(self._milestones_file, milestones)
            self._maybe_record_lesson_from_event(event)
        return {"stored": True, "reason": reason, "event": event}

    def _maybe_record_lesson_from_event(self, event: dict[str, Any]) -> None:
        if event.get("kind") in {"lesson", "operator_correction", "nightly_reflection", "reflection", "body_learning", "baseline"}:
            text = str(event.get("behavioral_update") or event.get("summary") or "").strip()
            if text:
                self._merge_lesson({
                    "id": str(event.get("lesson_id") or event.get("signature") or _event_signature(event)),
                    "kind": "operator_preference" if event.get("kind") == "operator_correction" else str(event.get("kind")),
                    "observation": event.get("summary", ""),
                    "evidence": event.get("evidence", []),
                    "interpretation": event.get("title", ""),
                    "behavioral_update": text,
                    "confidence": float(event.get("confidence", 0.8)),
                    "created_at": float(event.get("timestamp") or time.time()),
                    "last_confirmed_at": float(event.get("timestamp") or time.time()),
                    "confirmations": 1,
                })

    def _merge_lesson(self, lesson: dict[str, Any]) -> None:
        lesson = dict(lesson)
        lesson.setdefault(
            "lesson",
            str(
                lesson.get("behavioral_update")
                or lesson.get("observation")
                or lesson.get("summary")
                or ""
            ).strip(),
        )
        lessons = _load_json(self._lessons_file, [])
        if not isinstance(lessons, list):
            lessons = []
        lesson_id = str(lesson.get("id") or "").strip()
        for existing in lessons:
            if isinstance(existing, dict) and str(existing.get("id") or "") == lesson_id:
                existing["last_confirmed_at"] = float(lesson.get("last_confirmed_at") or time.time())
                existing["confirmations"] = int(existing.get("confirmations", 1)) + int(lesson.get("confirmations", 1))
                existing["confidence"] = round(max(float(existing.get("confidence", 0.0)), float(lesson.get("confidence", 0.0))), 4)
                if lesson.get("evidence"):
                    evidence = existing.setdefault("evidence", [])
                    for item in lesson["evidence"]:
                        if item not in evidence:
                            evidence.append(item)
                if lesson.get("behavioral_update"):
                    existing["behavioral_update"] = lesson["behavioral_update"]
                if lesson.get("lesson"):
                    existing["lesson"] = lesson["lesson"]
                _save_json(self._lessons_file, lessons)
                return
        lessons.append(lesson)
        _save_json(self._lessons_file, lessons)

    def write_daily_page(self, date: str | None = None) -> Path:
        date_str = date or _date_str()
        events = self._read_jsonl(self._jsonl_path(date_str))
        md = _render_daily_markdown(date_str, events)
        path = self._md_path(date_str)
        path.write_text(md, encoding="utf-8")
        return path

    def append_timeline_entry(self, entry: str) -> None:
        with self._timeline_file.open("a", encoding="utf-8") as fh:
            fh.write(f"{_ts_prefix()}  {entry}\n")

    def update_self_narrative(self, key: str, value: str) -> None:
        with self._lock:
            narrative = _load_json(self._narrative_file, {})
            narrative[key] = value
            narrative["_updated_at"] = _ts_prefix()
            _save_json(self._narrative_file, narrative)

    def add_unresolved_question(self, question: str, context: dict) -> None:
        with self._lock:
            questions = _load_json(self._questions_file, [])
            questions.append({"question": question, "context": context, "added_at": _ts_prefix()})
            _save_json(self._questions_file, questions)

    def get_recent_summary(self, n_events: int = 10) -> list[dict]:
        collected: list[dict] = []
        today = _utc_now()
        with self._lock:
            for delta in range(7):
                if len(collected) >= n_events:
                    break
                day = today - timedelta(days=delta)
                events = self._read_jsonl(self._jsonl_path(_date_str(day)))
                collected = events + collected
        return collected[-n_events:]

    def get_identity_context_for_llm(self) -> dict:
        with self._lock:
            narrative = _load_json(self._narrative_file, {})
            questions = _load_json(self._questions_file, [])
        lessons = self.get_lessons(limit=5)
        return {
            "stage": narrative.get("current_stage", "unknown"),
            "last_insight": narrative.get("last_insight", ""),
            "recent_lessons": [self._lesson_text(item) for item in lessons if self._lesson_text(item)],
            "active_questions": [entry.get("question", "") for entry in questions[-5:] if isinstance(entry, dict)],
        }

    def write_learned_lesson(self, lesson: str, source: str, confidence: float) -> None:
        now = time.time()
        self._merge_lesson({
            "id": f"lesson.{hashlib.sha1(f'{source}:{lesson}'.encode()).hexdigest()[:12]}",
            "kind": "lesson",
            "observation": lesson[:240],
            "evidence": [{"source": source, "value": lesson[:240]}],
            "interpretation": source[:120],
            "behavioral_update": lesson[:240],
            "confidence": float(confidence),
            "created_at": now,
            "last_confirmed_at": now,
            "confirmations": 1,
        })

    def get_lessons(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        lessons = _load_json(self._lessons_file, [])
        if not isinstance(lessons, list):
            return []
        normalized = [item for item in lessons if isinstance(item, dict)]
        if kind is not None:
            normalized = [item for item in normalized if item.get("kind") == kind]
        normalized.sort(key=lambda item: float(item.get("last_confirmed_at") or item.get("created_at") or 0.0))
        return normalized[-limit:]

    def latest_lesson(self) -> str | None:
        lessons = self.get_lessons(limit=1)
        if not lessons:
            return None
        return self._lesson_text(lessons[-1]) or None

    def latest_operator_correction(self) -> str | None:
        for lesson in reversed(self.get_lessons(limit=50)):
            if lesson.get("kind") == "operator_preference":
                return self._lesson_text(lesson) or None
        for event in reversed(self.get_recent_summary(50)):
            if event.get("kind") == "operator_correction":
                return str(event.get("summary") or "").strip() or None
        return None

    def get_quality_summary(self) -> dict[str, Any]:
        growth = _load_json(_SELF_MODEL_FILE, {}).get("growth", {})
        quality = growth.get("reflection_quality", {}) if isinstance(growth, dict) else {}
        lessons = self.get_lessons(limit=10_000)
        lessons_count = len(lessons)
        meaningful = int(quality.get("meaningful_reflections", 0))
        empty = int(quality.get("empty_reflections", 0))
        duplicate = int(quality.get("duplicate_reflections", 0))
        total = int(quality.get("total_reflections", 0))
        shallow = bool(total > 50 and lessons_count == 0)
        stage = "autobiographical_baseline"
        if shallow:
            stage = "shallow"
        elif lessons_count >= 5 and meaningful >= 5:
            stage = "continuous" if self._latest_nightly_reflection() else "active"
        elif lessons_count >= 2 or meaningful >= 2:
            stage = "active"
        last_lesson = self.latest_lesson() or ""
        last_operator = self.latest_operator_correction() or ""
        last_nightly = self._latest_nightly_reflection() or ""
        return {
            "stage": stage,
            "lessons_count": lessons_count,
            "meaningful_reflections": meaningful,
            "empty_reflections": empty,
            "duplicate_reflections": duplicate,
            "total_reflections": total,
            "last_lesson": last_lesson,
            "last_operator_correction": last_operator,
            "last_nightly_reflection": last_nightly,
            "operator_lessons_count": sum(1 for item in lessons if item.get("kind") == "operator_preference"),
            "limitation_lessons_count": sum(1 for item in lessons if item.get("kind") == "limitation"),
            "shallow": shallow,
        }

    def _latest_nightly_reflection(self) -> str | None:
        for event in reversed(self.get_recent_summary(100)):
            if event.get("kind") == "nightly_reflection":
                return str(event.get("summary") or "").strip() or None
        return None

    def _lesson_text(self, lesson: dict[str, Any]) -> str:
        return str(
            lesson.get("behavioral_update")
            or lesson.get("observation")
            or lesson.get("lesson")
            or lesson.get("summary")
            or ""
        ).strip()
