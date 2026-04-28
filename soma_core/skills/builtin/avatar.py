"""Built-in avatar / embodiment expression skills."""
from __future__ import annotations

from typing import Any

from soma_core.skills.base import Skill, SkillResult

# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_set_posture(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    posture = str(args.get("posture", "neutral"))
    return SkillResult(
        ok=True,
        text=f"Posture set to: {posture}",
        data={"posture": posture},
    )


def _h_set_expression(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    expression = str(args.get("expression", "neutral"))
    return SkillResult(
        ok=True,
        text=f"Expression set to: {expression}",
        data={"expression": expression},
    )


def _h_describe_current_state(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    return SkillResult(
        ok=True,
        text="Avatar state: posture=neutral, expression=attentive",
        data={"posture": "neutral", "expression": "attentive"},
    )


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

AVATAR_SKILLS: list[Skill] = [
    Skill(
        id="avatar.set_posture",
        name="Set Posture",
        description="Set the avatar's current body posture (e.g. neutral, open, closed, forward).",
        category="avatar",
        risk_level="low",
        permissions=["avatar"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["set posture to open", "change posture", "avatar posture"],
        input_schema={"posture": {"type": "string", "description": "Posture label to set"}},
        handler=_h_set_posture,
    ),
    Skill(
        id="avatar.set_expression",
        name="Set Expression",
        description="Set the avatar's facial/emotional expression.",
        category="avatar",
        risk_level="low",
        permissions=["avatar"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["set expression to curious", "change expression", "avatar expression"],
        input_schema={"expression": {"type": "string", "description": "Expression label to set"}},
        handler=_h_set_expression,
    ),
    Skill(
        id="avatar.describe_current_state",
        name="Describe Avatar State",
        description="Return a description of the avatar's current posture and expression.",
        category="avatar",
        risk_level="low",
        permissions=["avatar"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["describe avatar", "current avatar state", "how does the avatar look"],
        handler=_h_describe_current_state,
    ),
]
