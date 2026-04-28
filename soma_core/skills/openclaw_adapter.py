from __future__ import annotations

"""Parser for OpenClaw/AgentSkills SKILL.md folders."""

import re
import time
from pathlib import Path
from typing import Any

from soma_core.skills.base import Skill, SkillPermission, SkillRisk
from soma_core.skills.validation import assess_risk, infer_permissions

# ---------------------------------------------------------------------------
# YAML loading — prefer PyYAML, fall back to minimal inline parser
# ---------------------------------------------------------------------------

try:
    import yaml as _yaml_lib  # type: ignore[import]

    def _yaml_loads(text: str) -> Any:
        return _yaml_lib.safe_load(text)

except ImportError:
    _yaml_lib = None  # type: ignore[assignment]

    def _yaml_loads(text: str) -> Any:  # type: ignore[misc]
        """Minimal YAML parser supporting strings, lists and simple booleans.

        Handles the subset actually used in SKILL.md frontmatter:

        * ``key: value`` string pairs
        * ``key:`` with ``  - item`` list items below it
        * Boolean literals ``true``/``false``/``yes``/``no``
        * Quoted strings (double or single)
        * Multi-word unquoted strings
        """
        result: dict[str, Any] = {}
        lines = text.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            # Skip blank lines and YAML document markers
            if not line.strip() or line.strip() in ("---", "..."):
                i += 1
                continue
            # Top-level key: value  (no leading whitespace)
            m = re.match(r'^([A-Za-z_][A-Za-z0-9_\-]*)\s*:\s*(.*)', line)
            if m:
                key = m.group(1)
                raw_val = m.group(2).strip()
                if raw_val == "":
                    # Possibly a list follows
                    items: list[str] = []
                    j = i + 1
                    while j < len(lines):
                        item_line = lines[j]
                        item_m = re.match(r'^\s+-\s+(.*)', item_line)
                        if item_m:
                            items.append(_parse_scalar(item_m.group(1).strip()))
                            j += 1
                        else:
                            break
                    result[key] = items
                    i = j
                    continue
                else:
                    result[key] = _parse_scalar(raw_val)
            i += 1
        return result


def _parse_scalar(value: str) -> Any:
    """Convert a raw YAML scalar string to a Python value."""
    # Strip surrounding quotes
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    lower = value.lower()
    if lower in ("true", "yes"):
        return True
    if lower in ("false", "no"):
        return False
    # Integer
    try:
        return int(value)
    except ValueError:
        pass
    # Float
    try:
        return float(value)
    except ValueError:
        pass
    return value


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VALID_RISKS: frozenset[str] = frozenset({"low", "medium", "high", "critical"})
_VALID_PERMISSIONS: frozenset[str] = frozenset(
    {
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
    }
)


def _safe_id(name: str) -> str:
    """Return a safe, lower-case skill-ID slug from a folder/display name."""
    slug = name.lower().replace(" ", "-")
    slug = re.sub(r"[^a-z0-9\-_]", "", slug)
    return slug


def _parse_skill_md(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file into ``(frontmatter_dict, instructions_body)``."""
    text = path.read_text(encoding="utf-8")

    # Detect YAML frontmatter delimited by `---`
    frontmatter: dict[str, Any] = {}
    instructions = text

    # The frontmatter block must start at the very beginning of the file
    fm_match = re.match(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?(.*)\Z", text, re.DOTALL)
    if fm_match:
        fm_text = fm_match.group(1)
        instructions = fm_match.group(2).strip()
        try:
            parsed = _yaml_loads(fm_text)
            if isinstance(parsed, dict):
                frontmatter = parsed
        except Exception:
            # Gracefully ignore malformed frontmatter
            frontmatter = {}

    return frontmatter, instructions


def _coerce_permissions(raw: Any) -> list[SkillPermission]:
    """Convert raw frontmatter permissions value to a validated list."""
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    return [p for p in raw if p in _VALID_PERMISSIONS]  # type: ignore[misc]


def _coerce_risk(raw: Any) -> SkillRisk:
    if isinstance(raw, str) and raw.lower() in _VALID_RISKS:
        return raw.lower()  # type: ignore[return-value]
    return "low"


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------


class OpenClawSkillAdapter:
    """Loads and validates skills from OpenClaw/AgentSkills SKILL.md folders."""

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------

    def load_folder(self, path: Path) -> Skill:
        """Load a single skill from *path* (a directory containing ``SKILL.md``).

        Raises :class:`ValueError` if ``SKILL.md`` is missing.
        """
        path = Path(path)
        skill_md = path / "SKILL.md"
        if not skill_md.exists():
            raise ValueError(f"SKILL.md not found in {path}")

        frontmatter, instructions = _parse_skill_md(skill_md)

        folder_name = path.name
        safe_name = _safe_id(folder_name)
        skill_id = f"openclaw.{safe_name}"

        name: str = frontmatter.get("name") or folder_name
        description: str = frontmatter.get("description") or ""
        category: str = frontmatter.get("category") or "general"
        examples_raw = frontmatter.get("examples", [])
        examples: list[str] = list(examples_raw) if isinstance(examples_raw, list) else []
        input_schema: dict[str, Any] = frontmatter.get("input_schema") or {}
        output_schema: dict[str, Any] = frontmatter.get("output_schema") or {}

        # Permissions: prefer frontmatter, else infer from instructions
        raw_perms = frontmatter.get("permissions", None)
        if raw_perms is not None:
            permissions: list[SkillPermission] = _coerce_permissions(raw_perms)
        else:
            inferred = infer_permissions(instructions)
            permissions = _coerce_permissions(inferred)

        # Risk: prefer frontmatter, else assess from instructions + permissions
        raw_risk = frontmatter.get("risk_level", None)
        if raw_risk is not None:
            risk_level: SkillRisk = _coerce_risk(raw_risk)
        else:
            assessment = assess_risk(instructions, list(permissions), frontmatter)
            risk_level = _coerce_risk(assessment["risk_level"])

        # Run full assessment to pick up quarantine / confirmation flags
        assessment = assess_risk(instructions, list(permissions), frontmatter)
        quarantine_reason: str | None = None
        if assessment["quarantine"]:
            quarantine_reason = "; ".join(assessment["reasons"])
        requires_confirmation: bool = bool(assessment["requires_confirmation"])

        skill = Skill(
            id=skill_id,
            name=name,
            description=description,
            category=category,
            risk_level=risk_level,
            permissions=permissions,
            input_schema=input_schema if isinstance(input_schema, dict) else {},
            output_schema=output_schema if isinstance(output_schema, dict) else {},
            examples=examples,
            instructions=instructions,
            source="openclaw",
            source_path=str(path),
            imported_at=time.time(),
            handler=None,
            validator=None,
            enabled=not bool(quarantine_reason),
            requires_confirmation=requires_confirmation,
            quarantine_reason=quarantine_reason,
        )
        return skill

    def load_all(self, root: Path) -> list[Skill]:
        """Recursively find all sub-directories under *root* that contain a
        ``SKILL.md`` and load them as skills.

        Directories that raise :class:`ValueError` are skipped silently.
        """
        root = Path(root)
        skills: list[Skill] = []
        for folder in sorted(root.iterdir()):
            if not folder.is_dir():
                continue
            skill_md = folder / "SKILL.md"
            if not skill_md.exists():
                continue
            try:
                skill = self.load_folder(folder)
                skills.append(skill)
            except Exception:
                continue
        return skills

    def validate_skill(self, skill: Skill) -> list[str]:
        """Validate a loaded :class:`Skill` and return a list of warning strings.

        An empty list means the skill is valid.
        """
        warnings: list[str] = []

        if not skill.id:
            warnings.append("skill.id is empty")
        if not skill.name:
            warnings.append("skill.name is empty")
        if not skill.description:
            warnings.append("skill.description is empty — LLM context will be poor")
        if not skill.instructions:
            warnings.append("skill.instructions is empty — no behaviour defined")
        if skill.risk_level not in _VALID_RISKS:
            warnings.append(f"unknown risk_level: {skill.risk_level!r}")
        for perm in skill.permissions:
            if perm not in _VALID_PERMISSIONS:
                warnings.append(f"unknown permission: {perm!r}")
        if skill.source != "openclaw":
            warnings.append(f"unexpected source for OpenClaw skill: {skill.source!r}")
        if skill.quarantine_reason and skill.enabled:
            warnings.append("skill has quarantine_reason but is still enabled")
        if skill.requires_confirmation and skill.risk_level == "low":
            warnings.append("requires_confirmation=True but risk_level is 'low' — inconsistent")

        return warnings

    def risk_assessment(self, skill: Skill) -> dict[str, Any]:
        """Return the full risk-assessment dict for *skill* (delegates to
        :func:`~soma_core.skills.validation.assess_risk`).
        """
        from soma_core.skills.validation import assess_risk  # local re-import for clarity

        metadata: dict[str, Any] = {
            "name": skill.name,
            "description": skill.description,
            "category": skill.category,
            "risk_level": skill.risk_level,
        }
        return assess_risk(skill.instructions, list(skill.permissions), metadata)
