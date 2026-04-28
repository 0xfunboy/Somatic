"""
soma_core/journal.py — Central runtime journal manager for Latent Somatic.

Deduplicates, rotates, archives, and compacts runtime logs.
Replaces the "write every tick" pattern with meaningful event storage.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import shutil
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent.resolve()

_IMPORTANT_PHASES = frozenset({
    "command_proposed", "command_risk_check", "command_executed",
    "command_blocked", "skill_learned",
    "self_modify_started", "self_modify_validated", "self_modify_reverted",
    "reflection", "memory_update", "growth", "warning", "llm", "fallback",
    "policy", "command_planner_request", "command_planner_response",
    "command_result_used_in_chat",
    "bios_task_started", "bios_task_completed", "bios_task_failed", "bios_task_skipped",
})

_NOISY_PHASES = frozenset({
    "perception", "body_model", "somatic_projection", "drives",
    "goals", "action_selection",
})


def _today_str() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def _float_bucket(v: float) -> int:
    if v < 0.35:
        return 0
    if v <= 0.65:
        return 1
    return 2


def _semantic_hash(payload: dict[str, Any]) -> str:
    skip = {"timestamp", "summary"}
    cleaned: dict[str, Any] = {}
    for k, v in payload.items():
        if k in skip:
            continue
        cleaned[k] = v
    canonical = json.dumps(cleaned, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


def _actuation_semantic_hash(payload: dict[str, Any]) -> str:
    derived = payload.get("derived", payload)
    buckets = {
        "thermal_stress": _float_bucket(float(derived.get("thermal_stress", 0.0))),
        "energy_stress": _float_bucket(float(derived.get("energy_stress", 0.0))),
        "instability": _float_bucket(float(derived.get("instability", 0.0))),
    }
    key_parts: dict[str, Any] = {
        "provider": payload.get("provider"),
        "scenario": payload.get("scenario"),
        "policy_mode": payload.get("policy_mode"),
        "commands": payload.get("commands"),
        "visible_action": payload.get("visible_action"),
        "severity_buckets": buckets,
    }
    canonical = json.dumps(key_parts, sort_keys=True, ensure_ascii=True, separators=(",", ":"))
    return hashlib.sha1(canonical.encode()).hexdigest()[:12]


def _read_last_lines(path: Path, n: int) -> list[str]:
    try:
        with path.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            if size == 0:
                return []
            chunk = min(size, n * 512)
            f.seek(max(0, size - chunk))
            raw = f.read()
        lines = raw.decode("utf-8", errors="replace").splitlines()
        return lines[-n:] if len(lines) > n else lines
    except OSError:
        return []


def _file_size_mb(path: Path) -> float:
    try:
        return path.stat().st_size / (1024 * 1024)
    except OSError:
        return 0.0


def _safe_write_line(path: Path, obj: dict[str, Any]) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=True, separators=(",", ":")) + "\n")
    except OSError:
        pass


def _count_lines(path: Path) -> int:
    try:
        count = 0
        with path.open("rb") as f:
            for _ in f:
                count += 1
        return count
    except OSError:
        return 0


class JournalManager:
    def __init__(
        self,
        data_root: Path | None = None,
        *,
        persistence: str = "important",
        hot_max_mb: float = 10.0,
    ) -> None:
        self._data_root: Path = data_root if data_root is not None else _REPO_ROOT / "data" / "journal"
        self._persistence = persistence
        self._hot_max_mb = hot_max_mb
        self._lock = threading.Lock()

        self._hot_dir = self._data_root / "hot"
        self._daily_dir = self._data_root / "daily"
        self._archive_dir = self._data_root / "archive"
        self._index_dir = self._data_root / "index"

        self._trace_file = self._hot_dir / "cognitive_trace.hot.jsonl"
        self._actuation_file = self._hot_dir / "actuation.hot.jsonl"
        self._events_file = self._hot_dir / "events.hot.jsonl"
        self._important_events_file = self._index_dir / "important_events.jsonl"

        for d in (self._hot_dir, self._daily_dir, self._archive_dir, self._index_dir):
            try:
                d.mkdir(parents=True, exist_ok=True)
            except OSError:
                pass

        # In-memory dedup state: last semantic hash per channel
        self._last_trace_hash: str | None = None
        self._last_actuation_hash: str | None = None
        self._last_actuation_count: int = 0
        self._last_actuation_first_seen: float = 0.0
        self._last_actuation_last_seen: float = 0.0
        self._last_actuation_payload: dict[str, Any] = {}
        self._last_events_hash: str | None = None

    # ── append_trace ────────────────────────────────────────────────────────

    def append_trace(self, event: dict[str, Any]) -> None:
        if self._persistence == "off":
            return

        phase = event.get("phase", "")
        if self._persistence == "important" and phase not in _IMPORTANT_PHASES:
            return

        h = _semantic_hash(event)

        with self._lock:
            if h == self._last_trace_hash:
                return
            self._last_trace_hash = h
            _safe_write_line(self._trace_file, event)

        self.rotate_if_needed()

    # ── append_actuation ────────────────────────────────────────────────────

    def append_actuation(self, payload: dict[str, Any]) -> None:
        h = _actuation_semantic_hash(payload)
        now = time.time()

        with self._lock:
            if self._last_actuation_hash is None:
                # First write
                self._last_actuation_hash = h
                self._last_actuation_count = 1
                self._last_actuation_first_seen = now
                self._last_actuation_last_seen = now
                self._last_actuation_payload = payload
                _safe_write_line(self._actuation_file, payload)
                return

            if h == self._last_actuation_hash:
                self._last_actuation_count += 1
                self._last_actuation_last_seen = now
                return

            # Hash changed — flush collapsed entry if count > 1
            if self._last_actuation_count > 1:
                elapsed_s = self._last_actuation_last_seen - self._last_actuation_first_seen
                elapsed_min = elapsed_s / 60.0
                scenario = self._last_actuation_payload.get("scenario", "unknown")
                policy_mode = self._last_actuation_payload.get("policy_mode", "unknown")
                summary = (
                    f"Actuation remained in {policy_mode}/{scenario} "
                    f"for {elapsed_min:.0f}m."
                )
                collapsed: dict[str, Any] = {
                    "kind": "repeated_state",
                    "semantic_hash": self._last_actuation_hash,
                    "count": self._last_actuation_count,
                    "first_seen": self._last_actuation_first_seen,
                    "last_seen": self._last_actuation_last_seen,
                    "summary": summary,
                }
                _safe_write_line(self._actuation_file, collapsed)

            # Write new state
            self._last_actuation_hash = h
            self._last_actuation_count = 1
            self._last_actuation_first_seen = now
            self._last_actuation_last_seen = now
            self._last_actuation_payload = payload
            _safe_write_line(self._actuation_file, payload)

        self.rotate_if_needed()

    # ── append_event ────────────────────────────────────────────────────────

    def append_event(self, kind: str, payload: dict[str, Any], importance: float = 0.5) -> None:
        obj: dict[str, Any] = {
            "timestamp": time.time(),
            "kind": kind,
            "importance": importance,
            **payload,
        }

        if importance >= 0.7:
            with self._lock:
                _safe_write_line(self._events_file, obj)
            self.rotate_if_needed()
            return

        h = _semantic_hash(obj)
        with self._lock:
            if h == self._last_events_hash:
                return
            self._last_events_hash = h
            _safe_write_line(self._events_file, obj)

        self.rotate_if_needed()

    # ── append_autobiographical_event ────────────────────────────────────────

    def append_autobiographical_event(self, event: dict[str, Any]) -> None:
        with self._lock:
            _safe_write_line(self._important_events_file, event)

    # ── recent_events ───────────────────────────────────────────────────────

    def recent_events(self, limit: int = 50) -> list[dict[str, Any]]:
        lines = _read_last_lines(self._events_file, limit)
        result: list[dict[str, Any]] = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                result.append(json.loads(line))
            except json.JSONDecodeError:
                pass
        return result

    # ── compact_now ─────────────────────────────────────────────────────────

    def compact_now(self, source_files: list[Path] | None = None) -> dict[str, Any]:
        date_str = _today_str()
        archive_day_dir = self._archive_dir / date_str

        try:
            archive_day_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return {
                "date": date_str,
                "input_files": [],
                "total_lines": 0,
                "unique_states": 0,
                "archive_paths": [],
                "compression_ratio": 0.0,
                "saved_bytes": 0,
                "errors": [str(e)],
            }

        files = source_files if source_files is not None else [
            self._trace_file,
            self._actuation_file,
            self._events_file,
        ]

        total_lines = 0
        unique_states = 0
        archive_paths: list[str] = []
        errors: list[str] = []
        total_original = 0
        total_compressed = 0

        for src in files:
            if not src.exists():
                continue
            stem = src.stem
            out_name = f"{stem}.raw.jsonl.gz"
            out_path = archive_day_dir / out_name

            lines_in: list[bytes] = []
            try:
                with src.open("rb") as f:
                    lines_in = f.readlines()
            except OSError as e:
                errors.append(f"read {src}: {e}")
                continue

            seen_hashes: set[str] = set()
            unique_lines: list[bytes] = []
            file_original_size = 0
            for raw_line in lines_in:
                stripped = raw_line.strip()
                if not stripped:
                    continue
                total_lines += 1
                file_original_size += len(raw_line)
                h = hashlib.sha1(stripped).hexdigest()[:16]
                if h not in seen_hashes:
                    seen_hashes.add(h)
                    unique_lines.append(raw_line)
                    unique_states += 1

            total_original += file_original_size

            try:
                with gzip.open(out_path, "wb", compresslevel=6) as gz:
                    for line in unique_lines:
                        gz.write(line)
                compressed_size = out_path.stat().st_size
                total_compressed += compressed_size
                archive_paths.append(str(out_path))
            except OSError as e:
                errors.append(f"compress {out_path}: {e}")

        saved = total_original - total_compressed
        ratio = (saved / total_original) if total_original > 0 else 0.0

        report: dict[str, Any] = {
            "date": date_str,
            "input_files": [str(f) for f in files],
            "total_lines": total_lines,
            "unique_states": unique_states,
            "archive_paths": archive_paths,
            "compression_ratio": round(ratio, 4),
            "saved_bytes": saved,
            "errors": errors,
        }

        report_path = archive_day_dir / "compaction_report.json"
        try:
            with report_path.open("w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
        except OSError as e:
            errors.append(f"write report: {e}")
            report["errors"] = errors

        return report

    # ── rotate_if_needed ────────────────────────────────────────────────────

    def rotate_if_needed(self) -> None:
        hot_files = [self._trace_file, self._actuation_file, self._events_file]
        for f in hot_files:
            if _file_size_mb(f) > self._hot_max_mb:
                self._rotate_file(f)

    def _rotate_file(self, src: Path) -> None:
        date_str = _today_str()
        archive_day_dir = self._archive_dir / date_str
        try:
            archive_day_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            return

        ts = int(time.time())
        out_name = f"{src.stem}.{ts}.jsonl.gz"
        out_path = archive_day_dir / out_name

        with self._lock:
            try:
                with src.open("rb") as f_in:
                    with gzip.open(out_path, "wb", compresslevel=6) as f_out:
                        shutil.copyfileobj(f_in, f_out)
                src.write_bytes(b"")
            except OSError:
                pass

    # ── daily_summary ───────────────────────────────────────────────────────

    def daily_summary(self, date: str | None = None) -> dict[str, Any]:
        target = date or _today_str()
        events_path = self._daily_dir / f"{target}.events.jsonl"

        events: list[dict[str, Any]] = []
        if events_path.exists():
            try:
                with events_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
            except OSError:
                pass

        kind_counts: dict[str, int] = {}
        importance_sum = 0.0
        for ev in events:
            k = ev.get("kind", "unknown")
            kind_counts[k] = kind_counts.get(k, 0) + 1
            importance_sum += float(ev.get("importance", 0.5))

        avg_importance = (importance_sum / len(events)) if events else 0.0

        return {
            "date": target,
            "total_events": len(events),
            "kind_counts": kind_counts,
            "avg_importance": round(avg_importance, 4),
        }

    # ── write_daily_summary ─────────────────────────────────────────────────

    def write_daily_summary(self, date: str | None = None) -> Path:
        target = date or _today_str()
        summary_path = self._daily_dir / f"{target}.summary.json"
        daily_events_path = self._daily_dir / f"{target}.events.jsonl"

        # Aggregate from hot events file into daily events file for today
        if date is None or date == _today_str():
            events = self.recent_events(limit=10_000)
            try:
                with daily_events_path.open("a", encoding="utf-8") as f:
                    for ev in events:
                        f.write(json.dumps(ev, ensure_ascii=True, separators=(",", ":")) + "\n")
            except OSError:
                pass

        summary = self.daily_summary(target)

        try:
            with summary_path.open("w", encoding="utf-8") as f:
                json.dump(summary, f, indent=2)
        except OSError:
            pass

        return summary_path
