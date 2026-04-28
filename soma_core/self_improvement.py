"""
soma_core/self_improvement.py — Safe self-modification workflow for Latent Somatic.

Allows Soma to propose, plan, apply, test, and rollback code changes in a
controlled, auditable manner.

Config env vars (read at import time):
  SOMA_SELF_IMPROVEMENT_ENABLED         — master switch (default True)
  SOMA_SELF_IMPROVEMENT_AUTO_APPLY      — skip human approval gate (default False)
  SOMA_SELF_IMPROVEMENT_AUTO_ROLLBACK   — rollback on test failure (default True)
  SOMA_SELF_IMPROVEMENT_MAX_FILES       — max files per change (default 5)
  SOMA_SELF_IMPROVEMENT_MAX_DIFF_LINES  — diff line cap (default 500)
  SOMA_SELF_IMPROVEMENT_REQUIRE_TESTS   — run test scripts before accepting (default True)
"""

from __future__ import annotations

import json
import os
import py_compile
import subprocess
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── repo root ─────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# ── config ────────────────────────────────────────────────────────────────────


def _bool(key: str, default: bool) -> bool:
    v = os.getenv(key, "").strip().lower()
    if not v:
        return default
    return v not in {"0", "false", "no", "off"}


def _float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, str(default)))
    except (ValueError, TypeError):
        return default


SI_ENABLED = _bool("SOMA_SELF_IMPROVEMENT_ENABLED", True)
SI_AUTO_APPLY = _bool("SOMA_SELF_IMPROVEMENT_AUTO_APPLY", False)
SI_AUTO_ROLLBACK = _bool("SOMA_SELF_IMPROVEMENT_AUTO_ROLLBACK", True)
SI_MAX_FILES = int(_float("SOMA_SELF_IMPROVEMENT_MAX_FILES", 5.0))
SI_MAX_DIFF_LINES = int(_float("SOMA_SELF_IMPROVEMENT_MAX_DIFF_LINES", 500.0))
SI_REQUIRE_TESTS = _bool("SOMA_SELF_IMPROVEMENT_REQUIRE_TESTS", True)

# ── paths ─────────────────────────────────────────────────────────────────────

_QUEUE_FILE = _REPO_ROOT / "data" / "mind" / "self_improvement_queue.json"
_REPORTS_DIR = _REPO_ROOT / "data" / "mind" / "self_improvement_reports"

# ── forbidden paths (never modify these) ─────────────────────────────────────

_FORBIDDEN = (
    ".env",
    "data/mind/",
    "data/runtime/",
    "weights/",
    ".git/",
    "soma_core/executor.py",
    "soma_core/self_modify.py",
    "soma_core/self_improvement.py",
)

# ── validation commands ───────────────────────────────────────────────────────

_VALIDATION_COMMANDS: list[tuple[str, bool]] = [
    # (command, always_run)
    ("python3 -m py_compile server.py soma_core/*.py", True),
    ("python3 scripts/test_answer_finalizer.py", False),
    ("python3 scripts/test_relevance_filter.py", False),
    ("python3 scripts/test_output_filter.py", False),
    ("python3 scripts/test_experience_distiller.py", False),
    ("python3 scripts/test_autobiography_quality.py", False),
    ("python3 scripts/test_reflection_quality.py", False),
    ("python3 scripts/test_growth_engine.py", False),
    ("python3 scripts/test_baselines.py", False),
    ("python3 scripts/test_bios_loop.py", False),
    ("python3 scripts/test_mutation_sandbox.py", False),
    ("python3 scripts/test_cpp_bridge.py", False),
    ("python3 scripts/test_life_drive.py", False),
    ("python3 scripts/test_phase8_regressions.py", False),
    ("python3 scripts/test_command_planner.py", True),
    ("python3 scripts/test_telemetry_relevance.py", True),
    ("python3 scripts/test_journal_compaction.py", False),   # run only if file exists
    ("python3 scripts/test_actuation_dedupe.py", False),
]

# ── helpers ───────────────────────────────────────────────────────────────────


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


def _now_ts() -> float:
    return time.time()


def _report_filename() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S") + ".json"


def _is_forbidden(rel_path: str) -> bool:
    """Return True if rel_path matches any forbidden prefix."""
    for forbidden in _FORBIDDEN:
        if rel_path == forbidden or rel_path.startswith(forbidden):
            return True
    return False


def _resolve_rel(rel_path: str) -> Path | None:
    """Resolve rel_path to an absolute path inside the repo; return None if outside or forbidden."""
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
    if _is_forbidden(rel):
        return None

    return full


def _load_queue() -> list[dict]:
    try:
        raw = _QUEUE_FILE.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _save_queue(proposals: list[dict]) -> None:
    _QUEUE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _QUEUE_FILE.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(proposals, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_QUEUE_FILE)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _save_report(report: dict) -> Path:
    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = _report_filename() + f"_{report.get('id', 'unknown')}.json"
    path = _REPORTS_DIR / filename
    try:
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass
    return path


def _count_diff_lines(original: str, new_content: str) -> int:
    """Rough diff line count: number of lines that differ."""
    orig_lines = original.splitlines()
    new_lines = new_content.splitlines()
    max_len = max(len(orig_lines), len(new_lines))
    diff_count = abs(len(new_lines) - len(orig_lines))
    for o, n in zip(orig_lines, new_lines):
        if o != n:
            diff_count += 1
    return diff_count


def _py_compile_check(path: Path) -> tuple[bool, str]:
    """Run py_compile on a single Python file. Returns (ok, error_msg)."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pyc", delete=True) as tf:
            py_compile.compile(str(path), cfile=tf.name, doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)[:400]


def _script_exists(cmd: str) -> bool:
    """Check whether the first script argument in the command actually exists on disk."""
    parts = cmd.split()
    # find the script argument (first token not starting with '-' or 'python')
    for part in parts:
        if part.startswith("scripts/"):
            return (_REPO_ROOT / part).exists()
    return True  # no script path found — let it run


# ── main class ────────────────────────────────────────────────────────────────


class SelfImprovementWorkflow:
    """
    Safe self-modification workflow.

    All public methods are thread-safe and never raise to the caller.
    """

    def __init__(
        self,
        *,
        self_modifier: Any | None = None,
        executor: Any | None = None,
        trace: Any | None = None,
        autobiography: Any | None = None,
    ) -> None:
        self._modifier = self_modifier
        self._executor = executor
        self._trace = trace
        self._autobiography = autobiography
        self._lock = threading.Lock()
        # In-memory backup store keyed by proposal_id
        self._backups: dict[str, dict[str, str | None]] = {}

    # ── proposal management ───────────────────────────────────────────────────

    def propose_change(
        self,
        problem: str,
        goal: str,
        affected_files: list[str],
        risk: str = "medium",
    ) -> dict:
        """
        Create a new improvement proposal and add it to the queue.

        Returns the proposal dict, or an empty dict when SI_ENABLED is False.
        Never raises.
        """
        if not SI_ENABLED:
            return {}

        try:
            proposal: dict = {
                "id": _short_id(),
                "timestamp": _now_ts(),
                "problem": str(problem),
                "goal": str(goal),
                "affected_files": list(affected_files),
                "risk": str(risk),
                "status": "queued",
                "plan": None,
                "report_path": None,
            }

            with self._lock:
                proposals = _load_queue()
                proposals.append(proposal)
                _save_queue(proposals)

            self._emit(
                "self_modify_started",
                f"Improvement proposed [{proposal['id']}]: {goal[:100]}",
                inputs={"id": proposal["id"], "risk": risk, "files": affected_files},
                level="info",
            )
            return proposal
        except Exception as exc:
            self._emit("warning", f"propose_change failed: {exc}", level="warning")
            return {}

    def get_queued_proposals(self) -> list[dict]:
        """Return all proposals currently in 'queued' status. Never raises."""
        try:
            with self._lock:
                proposals = _load_queue()
            return [p for p in proposals if p.get("status") == "queued"]
        except Exception:
            return []

    def plan_change(self, proposal_id: str, plan: dict) -> bool:
        """
        Attach a plan to a proposal and set its status to 'planned'.

        Returns True on success, False otherwise.
        """
        try:
            with self._lock:
                proposals = _load_queue()
                for p in proposals:
                    if p.get("id") == proposal_id:
                        p["plan"] = dict(plan)
                        p["status"] = "planned"
                        _save_queue(proposals)
                        self._emit(
                            "self_modify_validated",
                            f"Change planned [{proposal_id}]: {plan.get('objective', '')[:80]}",
                            inputs={"id": proposal_id},
                            level="info",
                        )
                        return True
            return False
        except Exception as exc:
            self._emit("warning", f"plan_change failed: {exc}", level="warning")
            return False

    # ── apply & validate ──────────────────────────────────────────────────────

    def apply_and_validate(
        self,
        proposal_id: str,
        file_changes: dict[str, str],
    ) -> dict:
        """
        Apply file_changes for proposal_id, validate, optionally rollback.

        file_changes: {rel_path: new_content}

        Returns a report dict.  Never raises.
        """
        report: dict = {
            "id": proposal_id,
            "timestamp": _now_ts(),
            "objective": "",
            "files_changed": [],
            "tests_run": [],
            "passed": False,
            "rolled_back": False,
            "diff_summary": "",
            "operator_review_needed": False,
            "errors": [],
        }

        if not SI_ENABLED:
            report["errors"].append("SI_ENABLED is False — workflow disabled")
            return report

        try:
            # ── fetch proposal ────────────────────────────────────────────────
            proposal = self._get_proposal(proposal_id)
            if proposal is None:
                report["errors"].append(f"Proposal '{proposal_id}' not found")
                return report

            report["objective"] = (proposal.get("plan") or {}).get("objective", proposal.get("goal", ""))

            # ── scope guard ───────────────────────────────────────────────────
            if len(file_changes) > SI_MAX_FILES:
                report["errors"].append(
                    f"Too many files: {len(file_changes)} > SI_MAX_FILES={SI_MAX_FILES}"
                )
                self._update_proposal_status(proposal_id, "failed")
                return report

            rejected: list[str] = []
            for rel_path in file_changes:
                if _is_forbidden(rel_path):
                    rejected.append(rel_path)
            if rejected:
                report["errors"].append(f"Forbidden path(s): {rejected}")
                self._update_proposal_status(proposal_id, "failed")
                return report

            # ── diff-size guard ───────────────────────────────────────────────
            total_diff_lines = 0
            resolved_paths: dict[str, Path] = {}
            for rel_path, new_content in file_changes.items():
                full = _resolve_rel(rel_path)
                if full is None:
                    report["errors"].append(f"Cannot resolve path: {rel_path}")
                    self._update_proposal_status(proposal_id, "failed")
                    return report
                resolved_paths[rel_path] = full
                original = full.read_text(encoding="utf-8") if full.exists() else ""
                total_diff_lines += _count_diff_lines(original, new_content)

            if total_diff_lines > SI_MAX_DIFF_LINES:
                report["errors"].append(
                    f"Diff too large: ~{total_diff_lines} lines > SI_MAX_DIFF_LINES={SI_MAX_DIFF_LINES}"
                )
                self._update_proposal_status(proposal_id, "failed")
                return report

            report["diff_summary"] = f"~{total_diff_lines} diff lines across {len(file_changes)} file(s)"

            # ── backup ────────────────────────────────────────────────────────
            backup: dict[str, str | None] = {}
            for rel_path, full in resolved_paths.items():
                backup[rel_path] = full.read_text(encoding="utf-8") if full.exists() else None
            with self._lock:
                self._backups[proposal_id] = backup

            # ── mark applying ─────────────────────────────────────────────────
            self._update_proposal_status(proposal_id, "applying")
            self._emit(
                "self_modify_started",
                f"Applying {len(file_changes)} file(s) for [{proposal_id}]",
                inputs={"id": proposal_id, "files": list(file_changes.keys())},
                level="info",
            )

            # ── write files ───────────────────────────────────────────────────
            write_errors: list[str] = []
            written: list[str] = []

            for rel_path, new_content in file_changes.items():
                full = resolved_paths[rel_path]
                ok, msg = self._write_file(rel_path, full, new_content)
                if ok:
                    written.append(rel_path)
                else:
                    write_errors.append(msg)

            if write_errors:
                report["errors"].extend(write_errors)
                # Rollback whatever was written
                self._do_rollback(proposal_id, backup, written)
                report["rolled_back"] = True
                self._update_proposal_status(proposal_id, "rolled_back")
                self._write_report(report)
                return report

            report["files_changed"] = written

            # ── py_compile validation on .py files ────────────────────────────
            compile_errors: list[str] = []
            for rel_path in written:
                full = resolved_paths[rel_path]
                if full.suffix == ".py":
                    ok, err = _py_compile_check(full)
                    if not ok:
                        compile_errors.append(f"{rel_path}: {err}")

            if compile_errors:
                report["errors"].extend(compile_errors)
                if SI_AUTO_ROLLBACK:
                    self._do_rollback(proposal_id, backup, written)
                    report["rolled_back"] = True
                    self._update_proposal_status(proposal_id, "rolled_back")
                else:
                    self._update_proposal_status(proposal_id, "failed")
                self._emit(
                    "self_modify_reverted",
                    f"py_compile failed for [{proposal_id}]: {compile_errors[0][:80]}",
                    level="warning",
                )
                self._write_report(report)
                return report

            # ── integration test scripts ──────────────────────────────────────
            test_errors: list[str] = []
            tests_run: list[str] = []

            if SI_REQUIRE_TESTS:
                for cmd, always_run in _VALIDATION_COMMANDS:
                    if not always_run and not _script_exists(cmd):
                        continue
                    tests_run.append(cmd)
                    try:
                        result = subprocess.run(
                            cmd,
                            shell=True,
                            cwd=str(_REPO_ROOT),
                            timeout=60,
                            capture_output=True,
                            text=True,
                        )
                        if result.returncode != 0:
                            err_text = (result.stderr or result.stdout or "non-zero exit")[:300]
                            test_errors.append(f"[{cmd[:60]}] FAIL: {err_text}")
                    except subprocess.TimeoutExpired:
                        test_errors.append(f"[{cmd[:60]}] TIMEOUT after 60s")
                    except Exception as exc:
                        test_errors.append(f"[{cmd[:60]}] ERROR: {exc}")

            report["tests_run"] = tests_run

            if test_errors:
                report["errors"].extend(test_errors)
                if SI_AUTO_ROLLBACK:
                    self._do_rollback(proposal_id, backup, written)
                    report["rolled_back"] = True
                    self._update_proposal_status(proposal_id, "rolled_back")
                    self._emit(
                        "self_modify_reverted",
                        f"Tests failed, rolled back [{proposal_id}]",
                        inputs={"id": proposal_id},
                        outputs={"errors": test_errors[:3]},
                        level="warning",
                    )
                else:
                    report["operator_review_needed"] = True
                    self._update_proposal_status(proposal_id, "failed")
                self._write_report(report)
                return report

            # ── success ───────────────────────────────────────────────────────
            report["passed"] = True
            report["operator_review_needed"] = not SI_AUTO_APPLY
            self._update_proposal_status(proposal_id, "done")

            self._emit(
                "self_modify_validated",
                f"Change validated and applied [{proposal_id}]: {len(written)} file(s)",
                inputs={"id": proposal_id},
                outputs={"files": written, "diff_lines": total_diff_lines},
                level="info",
            )

            # ── autobiography ─────────────────────────────────────────────────
            self._write_autobiography_event(proposal_id, report)

            self._write_report(report)
            return report

        except Exception as exc:
            report["errors"].append(f"Unexpected error in apply_and_validate: {exc}")
            try:
                self._update_proposal_status(proposal_id, "failed")
            except Exception:
                pass
            self._emit("warning", f"apply_and_validate crashed: {exc}", level="warning")
            return report

    # ── rollback ──────────────────────────────────────────────────────────────

    def rollback(self, proposal_id: str) -> bool:
        """
        Restore backups for the given proposal.

        Returns True if at least one file was successfully restored.
        Never raises.
        """
        try:
            with self._lock:
                backup = self._backups.get(proposal_id)

            if not backup:
                self._emit(
                    "warning",
                    f"rollback [{proposal_id}]: no backup found",
                    level="warning",
                )
                return False

            # Determine which files were actually written (all keys in backup)
            written = list(backup.keys())
            success = self._do_rollback(proposal_id, backup, written)
            self._update_proposal_status(proposal_id, "rolled_back")
            return success
        except Exception as exc:
            self._emit("warning", f"rollback failed: {exc}", level="warning")
            return False

    # ── queue summary ─────────────────────────────────────────────────────────

    def get_queue_summary(self) -> dict:
        """
        Return counts by status.  Never raises.

        Returns {"total": N, "queued": N, "done": N, "failed": N, "rolled_back": N}
        """
        try:
            with self._lock:
                proposals = _load_queue()
            counts: dict[str, int] = {
                "total": len(proposals),
                "queued": 0,
                "planned": 0,
                "applying": 0,
                "done": 0,
                "failed": 0,
                "rolled_back": 0,
            }
            for p in proposals:
                status = p.get("status", "queued")
                if status in counts:
                    counts[status] += 1
            return counts
        except Exception:
            return {"total": 0, "queued": 0, "done": 0, "failed": 0, "rolled_back": 0}

    # ── private helpers ───────────────────────────────────────────────────────

    def _get_proposal(self, proposal_id: str) -> dict | None:
        with self._lock:
            proposals = _load_queue()
        for p in proposals:
            if p.get("id") == proposal_id:
                return p
        return None

    def _update_proposal_status(self, proposal_id: str, status: str) -> None:
        try:
            with self._lock:
                proposals = _load_queue()
                for p in proposals:
                    if p.get("id") == proposal_id:
                        p["status"] = status
                        break
                _save_queue(proposals)
        except Exception:
            pass

    def _write_file(self, rel_path: str, full_path: Path, new_content: str) -> tuple[bool, str]:
        """Write a file via self_modifier if available, else direct write."""
        if self._modifier is not None:
            try:
                ok, msg = self._modifier.apply(rel_path, new_content, reason="self_improvement workflow")
                return ok, msg
            except Exception as exc:
                return False, f"self_modifier.apply failed: {exc}"
        # Fallback: direct write
        try:
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(new_content, encoding="utf-8")
            return True, f"Written: {rel_path}"
        except OSError as exc:
            return False, f"Write failed for {rel_path}: {exc}"

    def _do_rollback(
        self,
        proposal_id: str,
        backup: dict[str, str | None],
        files_to_restore: list[str],
    ) -> bool:
        """Restore backup content for each listed file. Returns True if all succeeded."""
        any_success = False
        for rel_path in files_to_restore:
            if rel_path not in backup:
                continue
            original_content = backup[rel_path]
            full = _resolve_rel(rel_path)
            if full is None:
                # Path was valid when backed up; re-derive without forbidden check for restore
                try:
                    full = (_REPO_ROOT / rel_path).resolve()
                except Exception:
                    continue
            try:
                if original_content is None:
                    # File did not exist before — remove it
                    full.unlink(missing_ok=True)
                else:
                    full.parent.mkdir(parents=True, exist_ok=True)
                    full.write_text(original_content, encoding="utf-8")
                any_success = True
            except OSError:
                pass
        return any_success

    def _write_report(self, report: dict) -> None:
        """Persist the report and update proposal.report_path."""
        try:
            report_path = _save_report(report)
            proposal_id = report.get("id", "")
            if proposal_id:
                with self._lock:
                    proposals = _load_queue()
                    for p in proposals:
                        if p.get("id") == proposal_id:
                            p["report_path"] = str(report_path)
                            break
                    _save_queue(proposals)
        except Exception:
            pass

    def _write_autobiography_event(self, proposal_id: str, report: dict) -> None:
        if self._autobiography is None:
            return
        try:
            passed = report.get("passed", False)
            rolled_back = report.get("rolled_back", False)
            tone = "satisfied" if passed else ("cautious" if rolled_back else "concerned")
            impact = "high" if passed and not rolled_back else "low"
            self._autobiography.write_event({
                "kind": "self_modification",
                "title": f"Code change [{proposal_id}]: {'applied' if passed else 'rolled back'}",
                "summary": (
                    f"Objective: {report.get('objective', '')}. "
                    f"Files changed: {report.get('files_changed', [])}. "
                    f"Diff: {report.get('diff_summary', '')}. "
                    f"Tests run: {len(report.get('tests_run', []))}. "
                    f"Passed: {passed}. Rolled back: {rolled_back}."
                ),
                "evidence": [{"errors": e} for e in report.get("errors", [])[:3]],
                "emotional_tone": tone,
                "impact": impact,
                "timestamp": report.get("timestamp", _now_ts()),
            })
        except Exception:
            pass

    def _emit(
        self,
        phase: str,
        summary: str,
        *,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        if self._trace is None:
            return
        try:
            self._trace.emit(
                phase,
                summary,
                inputs=inputs or {},
                outputs=outputs or {},
                level=level,
            )
        except Exception:
            pass
