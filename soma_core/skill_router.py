from __future__ import annotations

from pathlib import Path
from typing import Any

from soma_core.autobiography import Autobiography
from soma_core.skills.base import SkillResult


class SkillRouter:
    def __init__(self, autobiography: Autobiography | None = None, introspector: Any | None = None) -> None:
        self._autobiography = autobiography
        self._introspector = introspector

    def attach_introspector(self, introspector: Any) -> None:
        self._introspector = introspector

    def execute(self, user_text: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if self._introspector is not None:
            try:
                result = self._introspector.execute(
                    user_text,
                    (context or {}).get("snapshot"),
                    (context or {}).get("growth"),
                )
            except Exception:
                result = None
            if result is not None:
                return result
        low = (user_text or "").lower()
        if any(mark in low for mark in ("lezioni", "lesson", "lessons", "hai imparato", "learned")):
            return self._lessons_skill()
        if any(mark in low for mark in ("autobiography quality", "qualità autobiografica", "autobio quality")):
            return self._autobiography_quality_skill()
        return None

    def _lessons_skill(self) -> dict[str, Any]:
        if self._autobiography is None:
            return {
                "ok": False,
                "skill_id": "memory.lessons",
                "text": "Autobiography module not available.",
                "source": "builtin",
            }
        lessons = self._autobiography.get_lessons(limit=5)
        if not lessons:
            return {
                "ok": True,
                "skill_id": "memory.lessons",
                "text": "Non ho ancora lezioni operative persistenti sufficienti. Ho solo trace/routine, che non considero memoria autobiografica significativa.",
                "data": {"lessons": []},
                "source": "builtin",
            }
        lines = []
        for idx, lesson in enumerate(lessons, start=1):
            text = (
                lesson.get("behavioral_update")
                or lesson.get("observation")
                or lesson.get("lesson")
                or lesson.get("summary")
                or ""
            )
            if text:
                lines.append(f"{idx}. {str(text).strip()}")
        return {
            "ok": True,
            "skill_id": "memory.lessons",
            "text": "\n".join(lines) if lines else "Non ho ancora lezioni operative persistenti sufficienti. Ho solo trace/routine, che non considero memoria autobiografica significativa.",
            "data": {"lessons": lessons},
            "source": "builtin",
        }

    def _autobiography_quality_skill(self) -> dict[str, Any]:
        if self._autobiography is None:
            return {
                "ok": False,
                "skill_id": "memory.autobiography_quality",
                "text": "Autobiography module not available.",
                "source": "builtin",
            }
        quality = self._autobiography.get_quality_summary()
        text = (
            f"Stage={quality.get('stage')} lessons={quality.get('lessons_count')} "
            f"meaningful={quality.get('meaningful_reflections')} "
            f"empty={quality.get('empty_reflections')} duplicate={quality.get('duplicate_reflections')}"
        )
        return {
            "ok": True,
            "skill_id": "memory.autobiography_quality",
            "text": text,
            "data": quality,
            "source": "builtin",
        }
