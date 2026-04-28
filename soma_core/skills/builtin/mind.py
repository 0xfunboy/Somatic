"""Built-in mind/cognition introspection skills."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from soma_core.skills.base import Skill, SkillResult

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

# soma_core/skills/builtin/mind.py → parent=builtin/ → parent=skills/ → parent=soma_core/ → parent=repo root
_REPO_ROOT = Path(__file__).parent.parent.parent.parent.resolve()
_MIND_DIR = _REPO_ROOT / "data" / "mind"
_JOURNAL_HOT_DIR = _REPO_ROOT / "data" / "journal" / "hot"

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_reflect_now(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    # Actual reflection triggering must be done by the caller that holds the
    # reflection/mind instance.  This handler signals the intent.
    return SkillResult(
        ok=True,
        text="Reflection triggered. Result will appear in trace.",
        data={"note": "Caller must invoke the reflection module directly."},
    )


def _h_growth_status(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    sm_file = _MIND_DIR / "self_model.json"
    if not sm_file.exists():
        return SkillResult(ok=False, text="self_model.json not found")
    try:
        data: dict[str, Any] = json.loads(sm_file.read_text(encoding="utf-8"))
        growth_score = data.get("growth_score", "N/A")
        stage = data.get("stage", "N/A")
        text = f"Growth score: {growth_score}\nStage: {stage}"
        # Include any additional growth-related fields
        extra_keys = ("level", "xp", "milestones", "next_milestone", "capabilities_count")
        extra_lines: list[str] = []
        for k in extra_keys:
            if k in data:
                extra_lines.append(f"{k}: {data[k]}")
        if extra_lines:
            text += "\n" + "\n".join(extra_lines)
        return SkillResult(
            ok=True,
            text=text,
            data={"growth_score": growth_score, "stage": stage},
        )
    except Exception as exc:
        return SkillResult(ok=False, text=f"Error reading self_model.json: {exc}")


def _h_trace_recent(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    # Prefer hot cognitive trace, fall back to the main trace file
    candidates = [
        _JOURNAL_HOT_DIR / "cognitive_trace.hot.jsonl",
        _MIND_DIR / "cognitive_trace.jsonl",
    ]
    trace_file: Path | None = None
    for candidate in candidates:
        if candidate.exists():
            trace_file = candidate
            break
    if trace_file is None:
        return SkillResult(ok=False, text="cognitive_trace file not found")
    try:
        lines = trace_file.read_text(encoding="utf-8").splitlines()
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
                phase = obj.get("phase", "?")
                msg = obj.get("message") or obj.get("text") or obj.get("summary") or str(obj)[:120]
                text_lines.append(f"[{phase}] {msg[:200]}")
            except Exception:
                text_lines.append(f"- {line[:200]}")
        text = (
            f"Recent cognitive trace (last 10, from {trace_file.name}):\n"
            + "\n".join(text_lines)
            if text_lines
            else "No trace entries found."
        )
        return SkillResult(ok=True, text=text, data={"recent": parsed})
    except Exception as exc:
        return SkillResult(ok=False, text=f"Error reading cognitive trace: {exc}")


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

MIND_SKILLS: list[Skill] = [
    Skill(
        id="mind.reflect_now",
        name="Reflect Now",
        description="Trigger an immediate reflection cycle (caller must execute via reflection module).",
        category="mind",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["reflect now", "trigger reflection", "self reflect"],
        handler=_h_reflect_now,
    ),
    Skill(
        id="mind.growth_status",
        name="Growth Status",
        description="Read current growth score and stage from self_model.json.",
        category="mind",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["growth status", "what stage am I", "growth score", "how have I grown"],
        handler=_h_growth_status,
    ),
    Skill(
        id="mind.trace_recent",
        name="Recent Cognitive Trace",
        description="Show last 10 entries from the cognitive trace journal.",
        category="mind",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["cognitive trace", "recent trace", "what was I doing", "trace log"],
        handler=_h_trace_recent,
    ),
]
