"""Built-in repository introspection and code-quality skills."""
from __future__ import annotations

import subprocess
from typing import Any

from soma_core.skills.base import Skill, SkillResult

# ---------------------------------------------------------------------------
# Shared subprocess helper
# ---------------------------------------------------------------------------


def _run(cmd: str, timeout: int = 15) -> tuple[bool, str, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()[:4000], r.stderr.strip()[:500]
    except Exception as exc:
        return False, "", str(exc)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_git_status(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("git status --short")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_git_diff_summary(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("git diff --stat HEAD~1 2>/dev/null || git diff --stat")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_run_py_compile(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run(
        "python3 -m py_compile server.py soma_core/*.py 2>&1 && echo OK",
        timeout=30,
    )
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_run_validation(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    cmd = (
        "python3 scripts/test_command_planner.py 2>&1 | tail -3 && "
        "python3 scripts/test_telemetry_relevance.py 2>&1 | tail -3"
    )
    ok, out, err = _run(cmd, timeout=60)
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_search_code(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    pattern = str(args.get("pattern", "")).replace('"', '\\"') or "TODO"
    cmd = f'grep -rn "{pattern}" soma_core/ server.py --include="*.py" | head -20'
    ok, out, err = _run(cmd)
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_inspect_file(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    path = str(args.get("path", "server.py")).replace('"', '\\"')
    ok, out, err = _run(f'head -100 "{path}"')
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

REPO_SKILLS: list[Skill] = [
    Skill(
        id="repo.git_status",
        name="Git Status",
        description="Show short git status of the working tree.",
        category="repo",
        risk_level="low",
        permissions=["read_repo"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["git status", "what files changed", "repo status"],
        handler=_h_git_status,
    ),
    Skill(
        id="repo.git_diff_summary",
        name="Git Diff Summary",
        description="Show a stat summary of changes vs HEAD~1 (or working tree).",
        category="repo",
        risk_level="low",
        permissions=["read_repo"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["what changed recently", "git diff", "diff summary"],
        handler=_h_git_diff_summary,
    ),
    Skill(
        id="repo.run_py_compile",
        name="Python Compile Check",
        description="Run py_compile on server.py and soma_core/*.py to catch syntax errors.",
        category="repo",
        risk_level="low",
        permissions=["read_repo"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["check syntax", "compile check", "python syntax errors"],
        handler=_h_run_py_compile,
    ),
    Skill(
        id="repo.run_validation",
        name="Run Validation Tests",
        description="Run test_command_planner and test_telemetry_relevance scripts.",
        category="repo",
        risk_level="low",
        permissions=["read_repo"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["run tests", "validate", "test scripts"],
        handler=_h_run_validation,
    ),
    Skill(
        id="repo.search_code",
        name="Search Code",
        description="Grep for a pattern in soma_core/ and server.py.",
        category="repo",
        risk_level="low",
        permissions=["read_repo"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["search code for X", "find pattern in source", "grep source"],
        input_schema={"pattern": {"type": "string", "description": "Pattern to search for"}},
        handler=_h_search_code,
    ),
    Skill(
        id="repo.inspect_file",
        name="Inspect File",
        description="Show first 100 lines of a file.",
        category="repo",
        risk_level="low",
        permissions=["read_repo"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["inspect server.py", "show file contents", "read file"],
        input_schema={"path": {"type": "string", "description": "Path to the file to inspect"}},
        handler=_h_inspect_file,
    ),
]
