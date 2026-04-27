"""
soma_core/self_modify.py — Repo-scoped code modification with safety guards.

Rules:
  - Only operates inside /home/funboy/latent-somatic (the repo root)
  - Never touches .env, data/mind/*.jsonl, weights/, .git/
  - Creates a git diff snapshot before modifying
  - Runs py_compile validation after writing Python files
  - Reverts to backup on validation failure
  - Never commits .env or data/mind/*.jsonl

Trace phases emitted: self_modify_started, self_modify_validated, self_modify_reverted
"""

from __future__ import annotations

import py_compile
import shlex
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from soma_core.executor import AutonomousShellExecutor
    from soma_core.trace import CognitiveTrace

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# Relative paths (or prefixes) that must never be modified
_FORBIDDEN_REL = (
    ".env",
    "data/mind/",
    "weights/",
    ".git/",
    "soma_core/executor.py",   # guard: don't let Soma disable its own safety
    "soma_core/self_modify.py",
)

# Files allowed in git commits (never auto-commit .env, mind state, or weights)
_COMMIT_BLOCKED_PATTERNS = (
    ".env",
    "data/mind/",
    "weights/",
    ".git/",
)


class SelfModifyError(Exception):
    pass


class AutonomousSelfModifier:
    """
    Applies code changes inside the repo with git diff + validation + revert.
    """

    def __init__(
        self,
        executor: "AutonomousShellExecutor",
        trace: "CognitiveTrace",
    ) -> None:
        self._exec = executor
        self._trace = trace

    # ── public interface ──────────────────────────────────────────────────────

    def apply(
        self,
        rel_path: str,
        new_content: str,
        reason: str = "",
    ) -> tuple[bool, str]:
        """
        Apply new_content to rel_path (relative to repo root).
        Returns (success, message).
        """
        full_path = self._resolve_and_guard(rel_path)
        if full_path is None:
            msg = f"Rejected: '{rel_path}' is outside repo or in a protected path"
            self._trace.emit(
                "command_blocked",
                msg,
                inputs={"rel_path": rel_path},
                level="warning",
            )
            return False, msg

        self._trace.emit(
            "self_modify_started",
            f"Applying change to {rel_path}: {reason[:120]}",
            inputs={"rel_path": rel_path, "reason": reason[:200], "content_len": len(new_content)},
            level="info",
        )

        # Snapshot current state
        diff_before = self._git_diff(rel_path)
        backup = full_path.read_text(encoding="utf-8") if full_path.exists() else None

        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(new_content, encoding="utf-8")
        except OSError as exc:
            msg = f"Write failed: {exc}"
            self._trace.emit("self_modify_reverted", msg, level="warning")
            return False, msg

        # Validate Python files
        if full_path.suffix == ".py":
            ok, err = self._validate_python(full_path)
            if not ok:
                # Revert
                if backup is not None:
                    full_path.write_text(backup, encoding="utf-8")
                else:
                    full_path.unlink(missing_ok=True)
                msg = f"Syntax validation failed, reverted: {err}"
                self._trace.emit(
                    "self_modify_reverted",
                    f"Reverted {rel_path}: {err[:120]}",
                    inputs={"rel_path": rel_path},
                    outputs={"error": err[:300]},
                    level="warning",
                )
                return False, msg

        diff_after = self._git_diff(rel_path)
        self._trace.emit(
            "self_modify_validated",
            f"Change applied and validated: {rel_path}",
            inputs={"rel_path": rel_path},
            outputs={
                "diff_lines_before": diff_before.count("\n"),
                "diff_lines_after": diff_after.count("\n"),
            },
            level="info",
        )
        return True, f"Applied: {rel_path} ({len(new_content)} chars)"

    def safe_git_commit(
        self,
        files: list[str],
        message: str,
    ) -> tuple[bool, str]:
        """
        Stage and commit specific files — never .env, mind state, or weights.
        """
        safe_files = [f for f in files if not self._is_commit_blocked(f)]
        if not safe_files:
            return False, "No safe files to commit"

        stage_args = " ".join(shlex.quote(f) for f in safe_files)
        ok, stdout, stderr = self._exec.run_raw(
            f"git -C {shlex.quote(str(_REPO_ROOT))} add {stage_args}"
        )
        if not ok:
            return False, f"git add failed: {stderr[:120]}"

        ok, stdout, stderr = self._exec.run_raw(
            f"git -C {shlex.quote(str(_REPO_ROOT))} commit -m {shlex.quote(message)}"
        )
        if not ok:
            if "nothing to commit" in stdout + stderr:
                return True, "nothing to commit"
            return False, f"git commit failed: {stderr[:120]}"

        return True, stdout[:300]

    # ── guards ────────────────────────────────────────────────────────────────

    def _resolve_and_guard(self, rel_path: str) -> Path | None:
        """Resolve path, verify it's inside repo and not in a forbidden location."""
        try:
            if rel_path.startswith("/"):
                full = Path(rel_path).resolve()
            else:
                full = (_REPO_ROOT / rel_path).resolve()
        except Exception:
            return None

        if not str(full).startswith(str(_REPO_ROOT)):
            return None

        rel = str(full.relative_to(_REPO_ROOT))
        for forbidden in _FORBIDDEN_REL:
            if rel == forbidden or rel.startswith(forbidden):
                return None

        return full

    def _is_commit_blocked(self, rel_path: str) -> bool:
        for pattern in _COMMIT_BLOCKED_PATTERNS:
            if rel_path == pattern or rel_path.startswith(pattern):
                return True
        return False

    # ── helpers ───────────────────────────────────────────────────────────────

    def _git_diff(self, rel_path: str) -> str:
        try:
            result = subprocess.run(
                ["git", "-C", str(_REPO_ROOT), "diff", "HEAD", "--", rel_path],
                capture_output=True, text=True, timeout=10,
            )
            return result.stdout[:4096]
        except Exception:
            return ""

    def _validate_python(self, path: Path) -> tuple[bool, str]:
        try:
            with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tf:
                py_compile.compile(str(path), cfile=tf.name, doraise=True)
            return True, ""
        except py_compile.PyCompileError as exc:
            return False, str(exc)[:300]
