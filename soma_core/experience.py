from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).parent.parent.resolve()
_LESSONS_FILE = _REPO_ROOT / "data" / "autobiography" / "learned_lessons.json"

_IT_CORRECTIONS = (
    "non fare", "smetti", "non voglio", "ti ho detto", "sbagli",
    "non è pertinente", "non inventare", "non recitare", "troppo roleplay",
    "rispondi diretto", "hai saltato il comando", "non dirmi sempre",
    "correzione permanente", "regola permanente",
)
_EN_CORRECTIONS = (
    "stop", "don't", "you failed", "not relevant", "don't invent",
    "too much roleplay", "be direct", "you didn't execute",
    "permanent correction", "permanent rule",
)


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


class ExperienceDistiller:
    def __init__(self, lessons_path: Path | None = None) -> None:
        self._lessons_path = lessons_path or _LESSONS_FILE

    def distill_from_operator_correction(self, user_text: str, assistant_text: str | None = None) -> list[dict[str, Any]]:
        low = (user_text or "").lower()
        if not any(mark in low for mark in (*_IT_CORRECTIONS, *_EN_CORRECTIONS)):
            return []
        now = time.time()
        lessons: list[dict[str, Any]] = []
        if any(mark in low for mark in ("temperatura", "voltaggio", "ram", "telemetry", "telemetria", "body state", "somatic")):
            lessons.append({
                "id": "operator.suppress_irrelevant_telemetry",
                "kind": "operator_preference",
                "observation": "The operator dislikes unrelated body telemetry in factual answers.",
                "evidence": [{"source": "operator", "value": user_text[:300]}],
                "interpretation": "Somatic awareness should remain internal unless relevant.",
                "behavioral_update": "For technical facts, verify first, answer briefly, and suppress body telemetry unless asked or abnormal.",
                "confidence": 0.95,
                "created_at": now,
                "last_confirmed_at": now,
                "confirmations": 1,
            })
        else:
            lesson_id = f"operator.rule.{abs(hash(low)) % 100000}"
            lessons.append({
                "id": lesson_id,
                "kind": "operator_preference",
                "observation": user_text[:240],
                "evidence": [{"source": "operator", "value": user_text[:300]}],
                "interpretation": "The operator issued a persistent behavioral correction.",
                "behavioral_update": assistant_text[:240] if assistant_text else "Apply this correction immediately in future answers.",
                "confidence": 0.85,
                "created_at": now,
                "last_confirmed_at": now,
                "confirmations": 1,
            })
        return lessons

    def distill_from_command(self, user_text: str, command_result: dict[str, Any]) -> list[dict[str, Any]]:
        low = (user_text or "").lower()
        stdout = str(command_result.get("stdout") or "")
        stderr = str(command_result.get("stderr") or "")
        now = time.time()
        lessons: list[dict[str, Any]] = []
        if any(mark in low for mark in ("x11", "wayland", "desktop", "grafico")):
            if "nessun processo grafico trovato" in stdout.lower() or stdout.strip().lower() in {"none", ""}:
                lessons.append({
                    "id": "limitation.no_graphical_session",
                    "kind": "limitation",
                    "observation": "No active graphical desktop session is visible from the runtime.",
                    "evidence": [{"source": "command", "value": stdout[:300] or stderr[:300]}],
                    "interpretation": "GUI-specific actions may be unavailable in the current session.",
                    "behavioral_update": "Admit the lack of a graphical session instead of inventing desktop state.",
                    "confidence": 0.92,
                    "created_at": now,
                    "last_confirmed_at": now,
                    "confirmations": 1,
                })
        if command_result.get("ok") is False and "blocked" in stderr.lower():
            lessons.append({
                "id": f"limitation.blocked.{abs(hash(str(command_result.get('cmd') or 'cmd'))) % 100000}",
                "kind": "limitation",
                "observation": "A requested action was blocked by the survival policy.",
                "evidence": [{"source": "command", "value": stderr[:300]}],
                "interpretation": "Risk boundaries are active and must be stated explicitly.",
                "behavioral_update": "Explain that the request is blocked and suggest a safe verification path.",
                "confidence": 0.9,
                "created_at": now,
                "last_confirmed_at": now,
                "confirmations": 1,
            })
        return lessons

    def distill_from_reflection(self, reflection: dict[str, Any], snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        lessons: list[dict[str, Any]] = []
        now = time.time()
        for lesson in reflection.get("lessons", []):
            if isinstance(lesson, dict):
                payload = dict(lesson)
                payload.setdefault("created_at", now)
                payload.setdefault("last_confirmed_at", now)
                payload.setdefault("confirmations", 1)
                lessons.append(payload)
            elif isinstance(lesson, str) and lesson.strip():
                lesson_id = f"reflection.{abs(hash(lesson.strip().lower())) % 100000}"
                lessons.append({
                    "id": lesson_id,
                    "kind": "reflection_lesson",
                    "observation": lesson.strip(),
                    "evidence": [{"source": "reflection", "value": reflection.get("summary", "")[:300]}],
                    "interpretation": "A reflection produced a persistent lesson.",
                    "behavioral_update": lesson.strip(),
                    "confidence": float(reflection.get("confidence", 0.7)),
                    "created_at": now,
                    "last_confirmed_at": now,
                    "confirmations": 1,
                })
        if reflection.get("meaningful") and reflection.get("no_lesson_reason"):
            lesson_id = f"growth.blocker.{abs(hash(reflection['no_lesson_reason'])) % 100000}"
            lessons.append({
                "id": lesson_id,
                "kind": "growth_blocker",
                "observation": reflection["no_lesson_reason"][:240],
                "evidence": [{"source": "reflection", "value": reflection.get("summary", "")[:300]}],
                "interpretation": "Reflection identified a concrete blocker rather than a new lesson.",
                "behavioral_update": "Use the blocker as evidence for future BIOS planning and growth evaluation.",
                "confidence": float(reflection.get("confidence", 0.6)),
                "created_at": now,
                "last_confirmed_at": now,
                "confirmations": 1,
            })
        return lessons

    def save_lessons(self, lessons: list[dict[str, Any]]) -> None:
        if not lessons:
            return
        stored = self.get_lessons(limit=10_000)
        by_id = {str(item.get("id")): item for item in stored if isinstance(item, dict) and item.get("id")}
        for lesson in lessons:
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
            lesson_id = str(lesson.get("id") or "").strip()
            if not lesson_id:
                continue
            existing = by_id.get(lesson_id)
            if existing:
                existing["last_confirmed_at"] = time.time()
                existing["confirmations"] = int(existing.get("confirmations", 1)) + 1
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
            else:
                by_id[lesson_id] = lesson
        _save_json(self._lessons_path, list(by_id.values()))

    def get_lessons(self, limit: int = 20, kind: str | None = None) -> list[dict[str, Any]]:
        lessons = _load_json(self._lessons_path, [])
        if not isinstance(lessons, list):
            return []
        filtered = [item for item in lessons if isinstance(item, dict)]
        if kind is not None:
            filtered = [item for item in filtered if item.get("kind") == kind]
        filtered.sort(key=lambda item: float(item.get("last_confirmed_at") or item.get("created_at") or 0.0))
        return filtered[-limit:]

    def latest_lesson(self) -> dict[str, Any] | None:
        lessons = self.get_lessons(limit=1)
        return lessons[-1] if lessons else None

    def lesson_context_for_llm(self, user_text: str) -> dict[str, Any]:
        lessons = self.get_lessons(limit=50)
        if not lessons:
            return {"recent_lessons": [], "relevant_lessons": []}
        query_tokens = set((user_text or "").lower().split())
        relevant: list[dict[str, Any]] = []
        for lesson in reversed(lessons):
            hay = " ".join(
                str(lesson.get(key) or "")
                for key in ("observation", "interpretation", "behavioral_update", "kind", "id")
            ).lower()
            if query_tokens & set(hay.split()):
                relevant.append(lesson)
            if len(relevant) >= 5:
                break
        return {
            "recent_lessons": lessons[-5:],
            "relevant_lessons": relevant or lessons[-3:],
        }
