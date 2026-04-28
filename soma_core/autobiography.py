"""
soma_core/autobiography.py — Autobiographical memory module for Latent Somatic.

Converts important runtime events into human-readable markdown memory organised
under data/autobiography/.  All file I/O is thread-safe and uses only the
Python standard library.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _date_str(dt: datetime | None = None) -> str:
    return (_utc_now() if dt is None else dt).strftime("%Y-%m-%d")


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
    try:
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Markdown rendering helpers
# ---------------------------------------------------------------------------

_KIND_LABELS: dict[str, str] = {
    "body_learning": "Body Learning",
    "dialogue": "Dialogue",
    "capability": "Capability",
    "self_modification": "Self Modification",
    "reflection": "Reflection",
    "milestone": "Milestone",
    "failure": "Failure",
    "recovery": "Recovery",
}


def _render_event_block(event: dict) -> str:
    """Render a single event as a markdown section."""
    kind = event.get("kind", "unknown")
    title = event.get("title", "(untitled)")
    summary = event.get("summary", "")
    evidence = event.get("evidence") or []
    follow_up = event.get("follow_up")
    emotional_tone = event.get("emotional_tone", "")
    impact = event.get("impact", "")
    ts = event.get("timestamp")

    # Timestamp display
    if ts is not None:
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            ts_str = dt.strftime("%H:%M:%S UTC")
        except (ValueError, OSError):
            ts_str = str(ts)
    else:
        ts_str = ""

    label = _KIND_LABELS.get(kind, kind.replace("_", " ").title())
    header_parts = [f"[{label}]", title]
    if ts_str:
        header_parts.append(f"*{ts_str}*")
    header = " ".join(header_parts)

    lines: list[str] = [f"## {header}", ""]

    meta_parts: list[str] = []
    if emotional_tone:
        meta_parts.append(f"Tone: **{emotional_tone}**")
    if impact:
        meta_parts.append(f"Impact: **{impact}**")
    if meta_parts:
        lines.append("  ".join(meta_parts))
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
        lines.append(follow_up)
        lines.append("")

    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def _render_daily_markdown(date_str: str, events: list[dict]) -> str:
    """Render all events for a day into a markdown page."""
    lines: list[str] = [f"# {date_str}", ""]

    if not events:
        lines.append("*No events recorded for this day.*")
        lines.append("")
        return "\n".join(lines)

    # Group by kind for a cleaner narrative
    from collections import defaultdict
    by_kind: dict[str, list[dict]] = defaultdict(list)
    order: list[str] = []
    for ev in events:
        k = ev.get("kind", "unknown")
        if k not in by_kind:
            order.append(k)
        by_kind[k].append(ev)

    for kind in order:
        for ev in by_kind[kind]:
            lines.append(_render_event_block(ev))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Autobiography class
# ---------------------------------------------------------------------------

class Autobiography:
    """
    Autobiographical memory for the Latent Somatic agent.

    Directory layout under *data_root* (default: <repo>/data/autobiography/):
        timeline.md
        daily/
            YYYY-MM-DD.jsonl   — raw event log (append-only)
            YYYY-MM-DD.md      — human-readable rendered page
        milestones.json
        self_narrative.json
        unresolved_questions.json
        learned_lessons.json
    """

    def __init__(self, data_root: Path | None = None) -> None:
        if data_root is None:
            data_root = _REPO_ROOT / "data" / "autobiography"
        self._root = Path(data_root)
        self._daily_dir = self._root / "daily"
        self._timeline_file = self._root / "timeline.md"
        self._milestones_file = self._root / "milestones.json"
        self._narrative_file = self._root / "self_narrative.json"
        self._questions_file = self._root / "unresolved_questions.json"
        self._lessons_file = self._root / "learned_lessons.json"
        self._lock = threading.Lock()
        self._ensure_dirs()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _ensure_dirs(self) -> None:
        try:
            self._root.mkdir(parents=True, exist_ok=True)
            self._daily_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass

    def _jsonl_path(self, date_str: str) -> Path:
        return self._daily_dir / f"{date_str}.jsonl"

    def _md_path(self, date_str: str) -> Path:
        return self._daily_dir / f"{date_str}.md"

    def _append_jsonl(self, path: Path, record: dict) -> None:
        """Append a single JSON record as one line to a .jsonl file."""
        line = json.dumps(record, ensure_ascii=False) + "\n"
        try:
            with path.open("a", encoding="utf-8") as fh:
                fh.write(line)
        except OSError:
            pass

    def _read_jsonl(self, path: Path) -> list[dict]:
        """Read all records from a .jsonl file; skip malformed lines."""
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
        except OSError:
            pass
        return records

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_event(self, event: dict) -> None:
        """
        Persist a runtime event.

        - Appends to data/autobiography/daily/YYYY-MM-DD.jsonl (raw events).
        - If impact == "high", also appends to milestones.json.
        - If kind == "reflection", also appends to learned_lessons.json
          (using summary as the lesson text).
        - Thread-safe.
        """
        if "timestamp" not in event:
            event = {**event, "timestamp": time.time()}

        ts = event["timestamp"]
        try:
            dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
            date_str = _date_str(dt)
        except (ValueError, OSError):
            date_str = _date_str()

        with self._lock:
            jsonl_path = self._jsonl_path(date_str)
            self._append_jsonl(jsonl_path, event)

            if event.get("impact") == "high":
                self._update_milestones(event)

            if event.get("kind") == "reflection":
                summary = event.get("summary", "")
                if summary:
                    source = event.get("title", "reflection")
                    self._append_lesson(summary, source=source, confidence=0.7)

    def write_daily_page(self, date: str | None = None) -> Path:
        """
        Render the human-readable markdown page for *date* (default: today).

        Reads raw events from daily/YYYY-MM-DD.jsonl and writes
        daily/YYYY-MM-DD.md.  Returns the path written.
        """
        date_str = date if date is not None else _date_str()
        with self._lock:
            events = self._read_jsonl(self._jsonl_path(date_str))
            md_content = _render_daily_markdown(date_str, events)
            md_path = self._md_path(date_str)
            try:
                md_path.write_text(md_content, encoding="utf-8")
            except OSError:
                pass
        return md_path

    def append_timeline_entry(self, entry: str) -> None:
        """
        Append a one-line entry to timeline.md with a UTC timestamp prefix.

        Format:  2026-04-27T14:05:00Z  <entry>
        """
        line = f"{_ts_prefix()}  {entry}\n"
        with self._lock:
            try:
                with self._timeline_file.open("a", encoding="utf-8") as fh:
                    fh.write(line)
            except OSError:
                pass

    def update_self_narrative(self, key: str, value: str) -> None:
        """
        Update a key in self_narrative.json (e.g. "current_stage", "last_insight").
        """
        with self._lock:
            narrative = _load_json(self._narrative_file, {})
            narrative[key] = value
            narrative["_updated_at"] = _ts_prefix()
            try:
                _save_json(self._narrative_file, narrative)
            except OSError:
                pass

    def add_unresolved_question(self, question: str, context: dict) -> None:
        """
        Append an unresolved question record to unresolved_questions.json.
        """
        record = {
            "question": question,
            "context": context,
            "added_at": _ts_prefix(),
        }
        with self._lock:
            questions = _load_json(self._questions_file, [])
            questions.append(record)
            try:
                _save_json(self._questions_file, questions)
            except OSError:
                pass

    def get_recent_summary(self, n_events: int = 10) -> list[dict]:
        """
        Return the last *n_events* events from today's event file.

        If today has fewer events, walks backwards through recent days until
        the requested count is satisfied (up to 7 days back).
        """
        collected: list[dict] = []
        today = datetime.now(tz=timezone.utc)
        with self._lock:
            for delta in range(7):
                if len(collected) >= n_events:
                    break
                from datetime import timedelta
                day = today - timedelta(days=delta)
                date_str = _date_str(day)
                events = self._read_jsonl(self._jsonl_path(date_str))
                collected = events + collected  # prepend older days

        # Return the last n_events chronologically
        return collected[-n_events:]

    def get_identity_context_for_llm(self) -> dict:
        """
        Return a compact dict for LLM context injection.

        Keys:
          stage            — self_narrative["current_stage"] (or "unknown")
          last_insight     — self_narrative["last_insight"] (or "")
          recent_lessons   — last 5 lesson texts from learned_lessons.json
          active_questions — last 5 questions from unresolved_questions.json
        """
        with self._lock:
            narrative = _load_json(self._narrative_file, {})
            lessons_data = _load_json(self._lessons_file, [])
            questions_data = _load_json(self._questions_file, [])

        recent_lessons = [
            entry.get("lesson", "") for entry in lessons_data[-5:]
            if isinstance(entry, dict)
        ]
        active_questions = [
            entry.get("question", "") for entry in questions_data[-5:]
            if isinstance(entry, dict)
        ]

        return {
            "stage": narrative.get("current_stage", "unknown"),
            "last_insight": narrative.get("last_insight", ""),
            "recent_lessons": recent_lessons,
            "active_questions": active_questions,
        }

    def write_learned_lesson(self, lesson: str, source: str, confidence: float) -> None:
        """
        Append a learned lesson record to learned_lessons.json.
        """
        with self._lock:
            self._append_lesson(lesson, source=source, confidence=confidence)

    # ------------------------------------------------------------------
    # Private persistence helpers
    # ------------------------------------------------------------------

    def _update_milestones(self, event: dict) -> None:
        """Append a high-impact event to milestones.json (must hold _lock)."""
        milestones = _load_json(self._milestones_file, [])
        milestones.append({
            "timestamp": event.get("timestamp", time.time()),
            "kind": event.get("kind", "unknown"),
            "title": event.get("title", ""),
            "summary": event.get("summary", ""),
            "emotional_tone": event.get("emotional_tone", ""),
            "related_goal": event.get("related_goal", ""),
        })
        try:
            _save_json(self._milestones_file, milestones)
        except OSError:
            pass

    def _append_lesson(self, lesson: str, source: str, confidence: float) -> None:
        """Append a lesson entry to learned_lessons.json (must hold _lock)."""
        lessons = _load_json(self._lessons_file, [])
        lessons.append({
            "lesson": lesson,
            "source": source,
            "confidence": float(confidence),
            "recorded_at": _ts_prefix(),
        })
        try:
            _save_json(self._lessons_file, lessons)
        except OSError:
            pass
