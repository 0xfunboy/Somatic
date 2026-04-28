from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

SkillRisk = Literal["low", "medium", "high", "critical"]
SkillSource = Literal["native", "openclaw", "local", "learned"]
SkillPermission = Literal[
    "read_system",
    "read_repo",
    "write_repo",
    "network",
    "shell",
    "self_modify",
    "memory_write",
    "avatar",
    "llm",
    "external_import",
]


@dataclass
class SkillResult:
    ok: bool
    text: str
    data: dict[str, Any] = field(default_factory=dict)
    stdout: str = ""
    stderr: str = ""
    command: str | None = None
    risk_level: str = "low"
    source: str = "native"
    trace: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class Skill:
    id: str
    name: str
    description: str
    category: str
    risk_level: SkillRisk
    permissions: list[SkillPermission]
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    instructions: str = ""
    source: SkillSource = "native"
    source_path: str | None = None
    imported_at: float | None = None
    handler: Callable[..., SkillResult] | None = None
    validator: Callable[..., bool] | None = None
    enabled: bool = True
    requires_confirmation: bool = False
    quarantine_reason: str | None = None


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------

_SKIP_FIELDS = frozenset({"handler", "validator"})


def skill_to_metadata(skill: Skill) -> dict[str, Any]:
    """Return a JSON-serialisable dict representation of *skill*.

    The ``handler`` and ``validator`` callables are excluded because they
    cannot be serialised to JSON and must be re-wired at load time.
    """
    result: dict[str, Any] = {}
    for f in skill.__dataclass_fields__:  # type: ignore[attr-defined]
        if f in _SKIP_FIELDS:
            continue
        value = getattr(skill, f)
        # Ensure list fields are plain lists (not other iterables)
        if isinstance(value, (list, tuple)):
            value = list(value)
        result[f] = value
    return result


def skill_from_metadata(data: dict[str, Any]) -> Skill:
    """Reconstruct a :class:`Skill` from a metadata dict.

    ``handler`` and ``validator`` are always set to ``None``; callers must
    re-wire them after loading.
    """
    # Strip any unknown keys so we don't blow up on future schema additions
    known = {f for f in Skill.__dataclass_fields__}  # type: ignore[attr-defined]
    filtered = {k: v for k, v in data.items() if k in known}
    # Callables are never stored; always initialise to None
    filtered.pop("handler", None)
    filtered.pop("validator", None)
    return Skill(handler=None, validator=None, **filtered)
