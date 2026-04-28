"""
soma_core/skills/memory.py — Skill reliability tracking.

Persists to:
  data/skills/skill_reliability.json  — per-skill aggregates (success/fail counts)
  data/skills/skill_history.jsonl     — per-invocation log (last N entries)
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
_SKILLS_DIR = _REPO_ROOT / "data" / "skills"
_RELIABILITY_FILE = _SKILLS_DIR / "skill_reliability.json"
_HISTORY_FILE = _SKILLS_DIR / "skill_history.jsonl"

_HISTORY_MAX_LINES = 2000
_EWA_ALPHA = 0.15  # exponential weighted average decay for reliability score


class SkillReliabilityStore:
    """
    Tracks per-skill success/failure rates.

    Reliability score: exponentially-weighted average of outcomes (1=ok, 0=fail).
    New skills start with a neutral 0.5 score and decay toward actual performance.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, dict[str, Any]] = {}
        _SKILLS_DIR.mkdir(parents=True, exist_ok=True)
        self._load()

    # ── public API ──────────────────────────────────────────────────────────

    def record_outcome(
        self,
        skill_id: str,
        ok: bool,
        error_hint: str = "",
        args_summary: str = "",
        duration_ms: float = 0.0,
    ) -> None:
        """Record a single skill invocation outcome."""
        now = time.time()
        with self._lock:
            entry = self._data.setdefault(
                skill_id,
                {
                    "skill_id": skill_id,
                    "success_count": 0,
                    "fail_count": 0,
                    "reliability": 0.5,
                    "last_ok": None,
                    "last_fail": None,
                    "last_error": "",
                    "avg_duration_ms": 0.0,
                },
            )
            if ok:
                entry["success_count"] += 1
                entry["last_ok"] = now
            else:
                entry["fail_count"] += 1
                entry["last_fail"] = now
                entry["last_error"] = error_hint[:200]

            # Exponential weighted average
            entry["reliability"] = round(
                (1.0 - _EWA_ALPHA) * entry["reliability"] + _EWA_ALPHA * (1.0 if ok else 0.0),
                4,
            )
            # Duration moving average
            if duration_ms > 0:
                prev = entry.get("avg_duration_ms", 0.0)
                entry["avg_duration_ms"] = round(prev * 0.9 + duration_ms * 0.1, 1)

        self._append_history(skill_id, ok, error_hint, args_summary, duration_ms, now)
        self._save()

    def get_reliability(self, skill_id: str) -> float:
        """Return reliability score 0.0–1.0 (0.5 if never seen)."""
        with self._lock:
            return self._data.get(skill_id, {}).get("reliability", 0.5)

    def is_reliable(self, skill_id: str, threshold: float = 0.65) -> bool:
        """Return True if reliability score >= threshold."""
        return self.get_reliability(skill_id) >= threshold

    def get_stats(self, skill_id: str) -> dict[str, Any]:
        with self._lock:
            return dict(self._data.get(skill_id, {"skill_id": skill_id, "reliability": 0.5}))

    def all_stats(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(v) for v in self._data.values()]

    # ── persistence ─────────────────────────────────────────────────────────

    def _save(self) -> None:
        with self._lock:
            payload = {"version": 1, "skills": list(self._data.values())}
        tmp = _RELIABILITY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_RELIABILITY_FILE)

    def _load(self) -> None:
        if not _RELIABILITY_FILE.exists():
            return
        try:
            raw = json.loads(_RELIABILITY_FILE.read_text(encoding="utf-8"))
            for entry in raw.get("skills", []):
                sid = entry.get("skill_id", "")
                if sid:
                    self._data[sid] = entry
        except Exception:
            pass

    def _append_history(
        self,
        skill_id: str,
        ok: bool,
        error_hint: str,
        args_summary: str,
        duration_ms: float,
        ts: float,
    ) -> None:
        record = json.dumps(
            {
                "ts": round(ts, 3),
                "skill_id": skill_id,
                "ok": ok,
                "error": error_hint[:120] if not ok else "",
                "args": args_summary[:80],
                "dur_ms": round(duration_ms, 1),
            },
            ensure_ascii=False,
        )
        try:
            with open(_HISTORY_FILE, "a", encoding="utf-8") as fh:
                fh.write(record + "\n")
            self._trim_history()
        except Exception:
            pass

    def _trim_history(self) -> None:
        try:
            lines = _HISTORY_FILE.read_text(encoding="utf-8").splitlines()
            if len(lines) > _HISTORY_MAX_LINES:
                _HISTORY_FILE.write_text(
                    "\n".join(lines[-_HISTORY_MAX_LINES:]) + "\n", encoding="utf-8"
                )
        except Exception:
            pass
