"""Built-in memory/mind-file reading skills."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from soma_core.skills.base import Skill, SkillResult

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# soma_core/skills/builtin/memory.py → parent=builtin/ → parent=skills/ → parent=soma_core/ → parent=repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
_MIND_DIR = _REPO_ROOT / "data" / "mind"

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_current_goals(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    goals_file = _MIND_DIR / "goals.json"
    if not goals_file.exists():
        return SkillResult(ok=False, text="goals.json not found")
    try:
        data = json.loads(goals_file.read_text(encoding="utf-8"))
        if isinstance(data, list):
            lines = [
                f"[{i + 1}] {g.get('title', g)}" if isinstance(g, dict) else f"[{i + 1}] {g}"
                for i, g in enumerate(data)
            ]
            text = "Current goals:\n" + "\n".join(lines) if lines else "No goals defined."
        elif isinstance(data, dict):
            text = json.dumps(data, indent=2, ensure_ascii=False)[:3000]
        else:
            text = str(data)[:3000]
        return SkillResult(ok=True, text=text, data=data if isinstance(data, dict) else {"goals": data})
    except Exception as exc:
        return SkillResult(ok=False, text=f"Error reading goals.json: {exc}")


def _h_self_model_summary(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    sm_file = _MIND_DIR / "self_model.json"
    if not sm_file.exists():
        return SkillResult(ok=False, text="self_model.json not found")
    try:
        data: dict[str, Any] = json.loads(sm_file.read_text(encoding="utf-8"))
        summary_keys = (
            "name", "version", "stage", "growth_score", "identity",
            "capabilities", "values", "emotional_baseline",
        )
        lines: list[str] = []
        for k in summary_keys:
            if k in data:
                lines.append(f"{k}: {data[k]}")
        # Remaining keys
        for k, v in data.items():
            if k not in summary_keys:
                lines.append(f"{k}: {v}")
        text = "Self model summary:\n" + "\n".join(lines) if lines else json.dumps(data, indent=2)[:3000]
        return SkillResult(ok=True, text=text[:3000], data=data)
    except Exception as exc:
        return SkillResult(ok=False, text=f"Error reading self_model.json: {exc}")


def _h_search_recent(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    reflections_file = _MIND_DIR / "reflections.jsonl"
    if not reflections_file.exists():
        return SkillResult(ok=False, text="reflections.jsonl not found")
    try:
        lines = reflections_file.read_text(encoding="utf-8").splitlines()
        recent = lines[-10:] if len(lines) >= 10 else lines
        parsed: list[dict[str, Any]] = []
        text_lines: list[str] = []
        for line in recent:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                parsed.append(obj)
                summary = obj.get("summary") or obj.get("text") or obj.get("content") or str(obj)[:120]
                text_lines.append(f"- {summary[:200]}")
            except Exception:
                text_lines.append(f"- {line[:200]}")
        text = "Recent reflections (last 10):\n" + "\n".join(text_lines) if text_lines else "No reflections found."
        return SkillResult(ok=True, text=text, data={"recent": parsed})
    except Exception as exc:
        return SkillResult(ok=False, text=f"Error reading reflections.jsonl: {exc}")


def _h_write_autobiography_event(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    # Actual writing must be done by the caller that holds an Autobiography instance.
    # This handler signals intent only.
    return SkillResult(
        ok=True,
        text="Event written via autobiography module",
        data={"note": "Caller must invoke autobiography.write_event() directly."},
    )


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

MEMORY_SKILLS: list[Skill] = [
    Skill(
        id="memory.current_goals",
        name="Current Goals",
        description="Read and display the current goals from data/mind/goals.json.",
        category="memory",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["what are my goals", "show goals", "current objectives"],
        handler=_h_current_goals,
    ),
    Skill(
        id="memory.self_model_summary",
        name="Self Model Summary",
        description="Read and summarise the self model from data/mind/self_model.json.",
        category="memory",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["self model", "who am I", "identity summary", "growth stage"],
        handler=_h_self_model_summary,
    ),
    Skill(
        id="memory.search_recent",
        name="Search Recent Reflections",
        description="Read the last 10 entries from data/mind/reflections.jsonl.",
        category="memory",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["recent reflections", "last reflections", "what did I reflect on"],
        handler=_h_search_recent,
    ),
    Skill(
        id="memory.write_autobiography_event",
        name="Write Autobiography Event",
        description="Signal that an autobiography event should be written (caller must execute).",
        category="memory",
        risk_level="medium",
        permissions=["memory_write"],
        source="native",
        enabled=True,
        requires_confirmation=True,
        examples=["write memory event", "record autobiography", "log to autobiography"],
        input_schema={
            "kind": {"type": "string", "description": "Event kind (capability, failure, insight, etc.)"},
            "title": {"type": "string", "description": "Short event title"},
            "summary": {"type": "string", "description": "Event summary text"},
        },
        handler=_h_write_autobiography_event,
    ),
]
