"""
soma_core/memory.py — Namespaced persistent memory for the Soma agent.

Wraps the existing flat memory files in soma_core/ namespace readers/writers,
and extends them with typed self/, body/, operator/ sub-namespaces backed by
data/mind/self_model.json and data/mind/preferences.json.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_MIND_DIR = Path(__file__).parent.parent / "data" / "mind"
_SELF_MODEL_FILE = _MIND_DIR / "self_model.json"
_PREFERENCES_FILE = _MIND_DIR / "preferences.json"
_SKILLS_FILE = _MIND_DIR / "skills.json"
_REFLECTIONS_FILE = _MIND_DIR / "reflections.jsonl"

# Legacy episodic/semantic paths (read-only here; server.py owns writes)
_DATA_DIR = Path(__file__).parent.parent / "data"
_EPISODIC_FILE = _DATA_DIR / "memory" / "episodic.jsonl"
_SEMANTIC_FILE = _DATA_DIR / "memory" / "semantic.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


class SomaMemory:
    """
    Namespaced memory gateway.

    Namespaces:
      self/       — identity, preferences, growth (self_model.json)
      body/       — known sensor baselines (self_model.json:known_body)
      operator/   — interaction profile (preferences.json:operator)
      skills/     — confirmed capabilities and bash shortcuts (skills.json)

    All mutation methods flush to disk immediately to survive restarts.
    """

    # ── self / identity ──────────────────────────────────────────────────────

    def get_identity(self) -> dict[str, Any]:
        return _load_json(_SELF_MODEL_FILE, {}).get("identity", {})

    def get_growth(self) -> dict[str, Any]:
        return _load_json(_SELF_MODEL_FILE, {}).get("growth", {})

    def set_growth(self, growth: dict[str, Any]) -> None:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        sm["growth"] = growth
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)

    def increment_reflections(self) -> int:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        sm.setdefault("growth", {})
        sm["growth"]["total_reflections"] = int(sm["growth"].get("total_reflections", 0)) + 1
        sm["growth"].setdefault("reflection_quality", {
            "total_reflections": 0,
            "meaningful_reflections": 0,
            "empty_reflections": 0,
            "duplicate_reflections": 0,
            "lessons_learned": 0,
        })
        sm["growth"]["reflection_quality"]["total_reflections"] = int(
            sm["growth"]["reflection_quality"].get("total_reflections", 0)
        ) + 1
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)
        return sm["growth"]["total_reflections"]

    def record_learned_fact(self, fact: str) -> None:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        sm.setdefault("growth", {})
        learned = sm["growth"].get("recently_learned", [])
        learned.append({"fact": fact[:300], "at": time.time()})
        sm["growth"]["recently_learned"] = learned[-20:]
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)

    # ── body / sensor baselines ──────────────────────────────────────────────

    def get_body(self) -> dict[str, Any]:
        return _load_json(_SELF_MODEL_FILE, {}).get("known_body", {})

    def update_body_baseline(self, key: str, value: float) -> None:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        sm.setdefault("known_body", {})
        sm["known_body"][key] = round(value, 3)
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)

    def update_reflection_quality(
        self,
        *,
        meaningful: bool,
        duplicate: bool = False,
        lessons_learned: int = 0,
    ) -> dict[str, Any]:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        growth = sm.setdefault("growth", {})
        quality = growth.setdefault("reflection_quality", {
            "total_reflections": 0,
            "meaningful_reflections": 0,
            "empty_reflections": 0,
            "duplicate_reflections": 0,
            "lessons_learned": 0,
        })
        if meaningful:
            quality["meaningful_reflections"] = int(quality.get("meaningful_reflections", 0)) + 1
        else:
            quality["empty_reflections"] = int(quality.get("empty_reflections", 0)) + 1
        if duplicate:
            quality["duplicate_reflections"] = int(quality.get("duplicate_reflections", 0)) + 1
        if lessons_learned:
            quality["lessons_learned"] = int(quality.get("lessons_learned", 0)) + int(lessons_learned)
        growth["reflection_quality"] = quality
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)
        return quality

    def record_command_result(self, category: str, ok: bool, command: str, *, source: str = "shell", regression_ok: bool | None = None) -> dict[str, Any]:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        growth = sm.setdefault("growth", {})
        agency = growth.setdefault("command_agency", {
            "successful": 0,
            "failed": 0,
            "categories": [],
            "recent_commands": [],
            "regression_ok": False,
        })
        if ok:
            agency["successful"] = int(agency.get("successful", 0)) + 1
            categories = set(agency.get("categories", []))
            categories.add(category)
            agency["categories"] = sorted(categories)
        else:
            agency["failed"] = int(agency.get("failed", 0)) + 1
        recent = agency.get("recent_commands", [])
        recent.append({
            "command": command[:160],
            "category": category,
            "ok": bool(ok),
            "source": source,
            "at": time.time(),
        })
        agency["recent_commands"] = recent[-30:]
        if regression_ok is not None:
            agency["regression_ok"] = bool(regression_ok)
        growth["command_agency"] = agency
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)
        return agency

    def set_body_field(self, key: str, value: Any) -> None:
        sm = _load_json(_SELF_MODEL_FILE, {"identity": {}, "known_body": {}, "preferences": {}, "growth": {}, "updated_at": 0.0})
        sm.setdefault("known_body", {})[key] = value
        sm["updated_at"] = time.time()
        _save_json(_SELF_MODEL_FILE, sm)

    # ── operator preferences ─────────────────────────────────────────────────

    def get_operator(self) -> dict[str, Any]:
        return _load_json(_PREFERENCES_FILE, {}).get("operator", {})

    def get_interaction(self) -> dict[str, Any]:
        return _load_json(_PREFERENCES_FILE, {}).get("interaction", {})

    def touch_operator_interaction(self) -> None:
        prefs = _load_json(_PREFERENCES_FILE, {"operator": {}, "interaction": {}, "updated_at": 0.0})
        prefs.setdefault("operator", {})["last_interaction_at"] = time.time()
        prefs["updated_at"] = time.time()
        _save_json(_PREFERENCES_FILE, prefs)

    def add_topic_of_interest(self, topic: str) -> None:
        prefs = _load_json(_PREFERENCES_FILE, {"operator": {}, "interaction": {}, "updated_at": 0.0})
        prefs.setdefault("operator", {}).setdefault("topics_of_interest", [])
        topics = prefs["operator"]["topics_of_interest"]
        if topic not in topics:
            topics.append(topic)
            prefs["updated_at"] = time.time()
            _save_json(_PREFERENCES_FILE, prefs)

    # ── skills ───────────────────────────────────────────────────────────────

    def get_skills(self) -> dict[str, Any]:
        return _load_json(_SKILLS_FILE, {"confirmed_capabilities": [], "confirmed_unavailable": [], "bash_shortcuts": []})

    def confirm_capability(self, name: str) -> None:
        skills = self.get_skills()
        if name not in skills["confirmed_capabilities"]:
            skills["confirmed_capabilities"].append(name)
            skills["updated_at"] = time.time()
            _save_json(_SKILLS_FILE, skills)

    def confirm_unavailable(self, name: str) -> None:
        skills = self.get_skills()
        if name not in skills["confirmed_unavailable"]:
            skills["confirmed_unavailable"].append(name)
            skills["updated_at"] = time.time()
            _save_json(_SKILLS_FILE, skills)

    # ── reflections (append-only log) ────────────────────────────────────────

    def append_reflection(self, entry: dict[str, Any]) -> None:
        _REFLECTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _REFLECTIONS_FILE.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=True) + "\n")

    def last_reflections(self, n: int = 5) -> list[dict[str, Any]]:
        try:
            lines = _REFLECTIONS_FILE.read_text(encoding="utf-8").splitlines()
            result = []
            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                    if len(result) >= n:
                        break
            return list(reversed(result))
        except FileNotFoundError:
            return []

    # ── legacy episodic/semantic (read-only) ─────────────────────────────────

    def get_semantic(self) -> dict[str, Any]:
        return _load_json(_SEMANTIC_FILE, {})

    def last_episodes(self, n: int = 10) -> list[dict[str, Any]]:
        try:
            lines = _EPISODIC_FILE.read_text(encoding="utf-8").splitlines()
            result = []
            for line in reversed(lines):
                line = line.strip()
                if line:
                    try:
                        result.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
                    if len(result) >= n:
                        break
            return list(reversed(result))
        except FileNotFoundError:
            return []

    # ── summary for LLM context injection ────────────────────────────────────

    def context_for_llm(self) -> dict[str, Any]:
        identity = self.get_identity()
        body = self.get_body()
        operator = self.get_operator()
        growth = self.get_growth()
        return {
            "name": identity.get("name", "Soma"),
            "kind": identity.get("kind", "embodied machine interface"),
            "body_baselines": {k: v for k, v in body.items() if v is not None},
            "operator_verbosity": operator.get("verbosity", "concise"),
            "total_reflections": growth.get("total_reflections", 0),
            "recently_learned": [e["fact"] for e in growth.get("recently_learned", [])[-3:]],
        }
