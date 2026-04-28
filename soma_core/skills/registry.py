from __future__ import annotations

"""Skill registry — thread-safe in-memory store with JSON persistence."""

import json
import threading
from pathlib import Path
from typing import Any

from soma_core.skills.base import Skill, skill_from_metadata, skill_to_metadata

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# soma_core/skills/registry.py  →  parent = skills/  →  parent = soma_core/  →  parent = repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.resolve()
_REGISTRY_FILE = _REPO_ROOT / "data" / "skills" / "registry.json"

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

# Ranking weight for each field when scoring search results (higher = better match)
_SEARCH_WEIGHTS: dict[str, int] = {
    "id": 5,
    "examples": 4,
    "name": 3,
    "description": 2,
    "category": 1,
}


def _score_skill(skill: Skill, query_lower: str) -> int:
    """Return a relevance score >= 0 for *skill* against *query_lower*."""
    score = 0
    tokens = query_lower.split()
    for token in tokens:
        if token in skill.id.lower():
            score += _SEARCH_WEIGHTS["id"]
        if any(token in ex.lower() for ex in skill.examples):
            score += _SEARCH_WEIGHTS["examples"]
        if token in skill.name.lower():
            score += _SEARCH_WEIGHTS["name"]
        if token in skill.description.lower():
            score += _SEARCH_WEIGHTS["description"]
        if token in skill.category.lower():
            score += _SEARCH_WEIGHTS["category"]
    return score


class SkillRegistry:
    """Thread-safe registry of :class:`~soma_core.skills.base.Skill` instances.

    Skills are stored in-memory and can be persisted to / loaded from a
    JSON file at ``data/skills/registry.json`` (relative to the repo root).
    """

    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self._lock = threading.Lock()
        _REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def register(self, skill: Skill) -> None:
        """Register (or replace) a skill in the registry.

        The skill's ``id`` is used as the primary key.
        """
        with self._lock:
            self._skills[skill.id] = skill

    def get(self, skill_id: str) -> Skill | None:
        """Return the skill with *skill_id*, or ``None`` if not found."""
        with self._lock:
            return self._skills.get(skill_id)

    def list(self, enabled_only: bool = True) -> list[Skill]:
        """Return all registered skills, optionally filtered to enabled ones only."""
        with self._lock:
            skills = list(self._skills.values())
        if enabled_only:
            skills = [s for s in skills if s.enabled]
        return sorted(skills, key=lambda s: s.id)

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(self, query: str) -> list[Skill]:
        """Search for skills matching *query*.

        Ranking priority: id > examples > name > description > category.

        Returns skills with a score > 0, sorted by descending score.
        """
        if not query.strip():
            return self.list(enabled_only=False)
        query_lower = query.lower()
        with self._lock:
            skills = list(self._skills.values())
        scored = [(s, _score_skill(s, query_lower)) for s in skills]
        scored = [(s, sc) for s, sc in scored if sc > 0]
        scored.sort(key=lambda t: t[1], reverse=True)
        return [s for s, _ in scored]

    # ------------------------------------------------------------------
    # Metadata export / persistence
    # ------------------------------------------------------------------

    def export_metadata(self) -> dict[str, Any]:
        """Return a JSON-serialisable snapshot of all registered skills."""
        with self._lock:
            skills = list(self._skills.values())
        return {
            "version": 1,
            "skills": [skill_to_metadata(s) for s in sorted(skills, key=lambda s: s.id)],
        }

    def save_metadata(self) -> None:
        """Persist all skill metadata to :data:`_REGISTRY_FILE`."""
        payload = export = self.export_metadata()
        _REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _REGISTRY_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(export, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_REGISTRY_FILE)

    def load_metadata(self) -> None:
        """Load skill metadata from :data:`_REGISTRY_FILE`.

        ``handler`` and ``validator`` are set to ``None`` on all loaded skills;
        callers must re-wire them as needed.
        """
        if not _REGISTRY_FILE.exists():
            return
        raw = _REGISTRY_FILE.read_text(encoding="utf-8")
        data: dict[str, Any] = json.loads(raw)
        skill_list: list[dict[str, Any]] = data.get("skills", [])
        with self._lock:
            for item in skill_list:
                try:
                    skill = skill_from_metadata(item)
                    self._skills[skill.id] = skill
                except Exception:
                    # Skip malformed entries rather than aborting the whole load
                    continue

    # ------------------------------------------------------------------
    # LLM context
    # ------------------------------------------------------------------

    def describe_for_llm(self, max_skills: int = 50) -> str:
        """Return a compact, human-readable list of skills for inclusion in an
        LLM context window.

        Each line has the form::

            [id] name (category, risk_level) — description

        Only enabled skills are included.  At most *max_skills* entries are
        returned (sorted by id).
        """
        skills = self.list(enabled_only=True)[:max_skills]
        if not skills:
            return "(no skills registered)"
        lines: list[str] = []
        for s in skills:
            perms = ", ".join(s.permissions) if s.permissions else "none"
            line = (
                f"[{s.id}] {s.name} "
                f"(category={s.category}, risk={s.risk_level}, perms={perms}) "
                f"— {s.description}"
            )
            if s.examples:
                line += f"  e.g.: {s.examples[0]}"
            lines.append(line)
        return "\n".join(lines)
