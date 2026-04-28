"""
soma_core/routines.py — Low-frequency autonomous background routines.

NOT every tick. NOT chatty. At most one routine fires per call to maybe_run(),
and only when the system is idle and within the hourly quota.

Routine schedule (minimum intervals):
  body_baseline_observation    600s
  capability_consolidation    1800s
  goal_progress_review         900s
  memory_compaction_check      900s
  self_health_check            600s
  self_improvement_planning   3600s
"""

from __future__ import annotations

import json
import os
import shutil
import time
import threading
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Config (read from env at import time)
# ---------------------------------------------------------------------------

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


ROUTINES_ENABLED        = _bool("SOMA_ROUTINES_ENABLED", True)
ROUTINE_MIN_INTERVAL_SEC = _float("SOMA_ROUTINE_MIN_INTERVAL_SEC", 300.0)
ROUTINE_IDLE_ONLY       = _bool("SOMA_ROUTINE_IDLE_ONLY", True)
ROUTINE_MAX_PER_HOUR    = int(_float("SOMA_ROUTINE_MAX_PER_HOUR", 6.0))

_REPO_ROOT = Path(__file__).parent.parent.resolve()
_MIND_DIR  = _REPO_ROOT / "data" / "mind"

# How long without a user message before we consider the system idle
_IDLE_THRESHOLD_S = 120.0
# Largest hot-log file size (bytes) before emitting a warning
_LOG_SIZE_WARN_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Result helper
# ---------------------------------------------------------------------------

def _result(
    routine: str,
    result: str,
    reason: str,
    events: list[Any] | None = None,
    next_run_after: float = 0.0,
) -> dict[str, Any]:
    return {
        "timestamp": time.time(),
        "routine": routine,
        "result": result,
        "reason": reason,
        "events": events or [],
        "next_run_after": next_run_after,
    }


# ---------------------------------------------------------------------------
# RoutineRunner
# ---------------------------------------------------------------------------

class RoutineRunner:
    """
    Runs low-frequency background routines from within SomaMind.tick().

    Call maybe_run(snapshot) once per tick.  At most one routine fires per
    call.  All exceptions are caught internally — this must never raise.
    """

    # (name, min_interval_s)
    _SCHEDULE: list[tuple[str, float]] = [
        ("self_health_check",          600.0),
        ("body_baseline_observation",  600.0),
        ("goal_progress_review",       900.0),
        ("memory_compaction_check",    900.0),
        ("capability_consolidation",  1800.0),
        ("self_improvement_planning", 3600.0),
    ]

    def __init__(
        self,
        *,
        trace: Any,
        memory: Any,
        autobiography: Any,
        journal: Any,
    ) -> None:
        self._trace = trace
        self._memory = memory
        self._autobiography = autobiography
        self._journal = journal

        # monotonic next-run times keyed by routine name
        self._next_run: dict[str, float] = {
            name: time.monotonic() + interval * 0.5  # stagger cold start
            for name, interval in self._SCHEDULE
        }
        self._last_user_interaction: float = 0.0
        self._lock = threading.Lock()

        # Rolling window for hourly quota: list of wall-clock run timestamps
        self._run_times: list[float] = []

    # ── public API ─────────────────────────────────────────────────────────────

    def set_last_user_interaction(self, t: float) -> None:
        """Call when the user sends a message."""
        self._last_user_interaction = t

    def maybe_run(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Called from SomaMind.tick().  Non-blocking.
        Runs at most one routine per call.
        Returns a list of 0 or 1 result dicts.
        """
        try:
            return self._maybe_run_inner(snapshot)
        except Exception as exc:
            return [_result("unknown", "failed", f"RoutineRunner.maybe_run raised: {exc}")]

    # ── internals ──────────────────────────────────────────────────────────────

    def _maybe_run_inner(self, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
        if not ROUTINES_ENABLED:
            return []

        now_wall = time.time()
        now_mono = time.monotonic()

        # Idle check
        if ROUTINE_IDLE_ONLY:
            idle_s = now_wall - self._last_user_interaction
            if idle_s < _IDLE_THRESHOLD_S:
                return []

        # Hourly quota check
        with self._lock:
            hour_ago = now_wall - 3600.0
            self._run_times = [t for t in self._run_times if t > hour_ago]
            if len(self._run_times) >= ROUTINE_MAX_PER_HOUR:
                return []

        # Find the first overdue routine (respecting ROUTINE_MIN_INTERVAL_SEC floor)
        due_name: str | None = None
        due_interval: float = 0.0
        for name, interval in self._SCHEDULE:
            effective_interval = max(interval, ROUTINE_MIN_INTERVAL_SEC)
            if now_mono >= self._next_run.get(name, 0.0):
                due_name = name
                due_interval = effective_interval
                break

        if due_name is None:
            return []

        # Record run attempt before executing
        with self._lock:
            self._run_times.append(now_wall)
        self._next_run[due_name] = now_mono + due_interval

        # Dispatch
        try:
            method = getattr(self, f"_routine_{due_name}")
            res = method(snapshot)
        except Exception as exc:
            res = _result(due_name, "failed", str(exc), next_run_after=now_mono + due_interval)

        # Emit trace event (best-effort)
        try:
            if self._trace is not None:
                level = "warning" if res["result"] == "failed" else "info"
                self._trace.emit(
                    "warning" if level == "warning" else "reflection",
                    f"Routine {due_name}: {res['result']} — {res['reason'][:120]}",
                    level=level,
                )
        except Exception:
            pass

        return [res]

    # ── routines ───────────────────────────────────────────────────────────────

    def _routine_body_baseline_observation(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Summarise the current body state from memory and note any pattern changes.
        No LLM, no blocking I/O.
        """
        routine = "body_baseline_observation"
        now_mono = time.monotonic()
        events: list[Any] = []

        body: dict[str, Any] = {}
        if self._memory is not None:
            try:
                body = self._memory.get_body()
            except Exception:
                pass

        snapshot_system = snapshot.get("system", {})
        interesting_keys = (
            "cpu_temp_baseline",
            "disk_temp_baseline",
            "memory_percent_baseline",
            "cpu_percent_baseline",
        )
        known_count = sum(1 for k in interesting_keys if body.get(k) is not None)

        # Compare snapshot live values to stored baselines
        changes: list[str] = []
        cpu_live = snapshot_system.get("cpu_percent")
        cpu_base = body.get("cpu_percent_baseline")
        if cpu_live is not None and cpu_base is not None:
            if abs(float(cpu_live) - float(cpu_base)) > 15.0:
                changes.append(f"cpu_pct live={cpu_live:.1f} vs baseline={cpu_base:.1f}")

        temp_live = snapshot_system.get("cpu_temp")
        temp_base = body.get("cpu_temp_baseline")
        if temp_live is not None and temp_base is not None:
            if abs(float(temp_live) - float(temp_base)) > 8.0:
                changes.append(f"cpu_temp live={temp_live:.1f} vs baseline={temp_base:.1f}")

        if changes:
            events.append({"body_drift": changes})
            # Write to autobiography
            if self._autobiography is not None:
                try:
                    self._autobiography.write_event({
                        "kind": "body_learning",
                        "title": "Body baseline drift observed",
                        "summary": "; ".join(changes),
                        "impact": "low",
                    })
                except Exception:
                    pass

        reason = (
            f"Observed body state. {known_count} baselines known."
            + (f" Drift detected: {'; '.join(changes[:2])}." if changes else " No significant drift.")
        )
        return _result(routine, "completed", reason, events, now_mono)

    def _routine_capability_consolidation(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Summarise newly confirmed capabilities and write a short autobiography event.
        """
        routine = "capability_consolidation"
        now_mono = time.monotonic()
        events: list[Any] = []

        skills: dict[str, Any] = {}
        if self._memory is not None:
            try:
                skills = self._memory.get_skills()
            except Exception:
                pass

        confirmed = skills.get("confirmed_capabilities", [])
        unavailable = skills.get("confirmed_unavailable", [])

        summary_parts = []
        if confirmed:
            summary_parts.append(f"Confirmed capabilities ({len(confirmed)}): {', '.join(confirmed[:8])}")
        if unavailable:
            summary_parts.append(f"Known unavailable ({len(unavailable)}): {', '.join(unavailable[:4])}")

        if summary_parts and self._autobiography is not None:
            try:
                self._autobiography.write_event({
                    "kind": "capability",
                    "title": "Capability consolidation",
                    "summary": ". ".join(summary_parts),
                    "impact": "low",
                })
            except Exception:
                pass
            events.append({"confirmed": len(confirmed), "unavailable": len(unavailable)})

        reason = (
            f"Consolidated capabilities: {len(confirmed)} confirmed, {len(unavailable)} unavailable."
        )
        return _result(routine, "completed", reason, events, now_mono)

    def _routine_goal_progress_review(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Load active goals from disk and update next_action fields where stale.
        """
        routine = "goal_progress_review"
        now_mono = time.monotonic()
        events: list[Any] = []

        goals_file = _MIND_DIR / "goals.json"
        goals_data: dict[str, Any] = {}
        try:
            goals_data = json.loads(goals_file.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return _result(routine, "skipped", "goals.json missing or unreadable", next_run_after=now_mono)

        active = [g for g in goals_data.get("active_goals", []) if g.get("status") == "active"]
        stale_threshold = 1800.0  # seconds
        now_wall = time.time()
        updated: list[str] = []

        for goal in active:
            last_updated = float(goal.get("updated_at", 0.0))
            progress = float(goal.get("progress", 0.0))
            if (now_wall - last_updated) > stale_threshold and goal.get("next_action") in (None, "observe", ""):
                # Determine a simple next action based on progress
                if progress < 0.1:
                    next_action = "gather_initial_evidence"
                elif progress < 0.5:
                    next_action = "deepen_understanding"
                else:
                    next_action = "consolidate_and_verify"
                goal["next_action"] = next_action
                updated.append(f"{goal['id']}→{next_action}")

        if updated:
            goals_data["updated_at"] = now_wall
            try:
                goals_file.write_text(json.dumps(goals_data, indent=2, ensure_ascii=True), encoding="utf-8")
            except OSError:
                pass
            events.append({"updated_goals": updated})

        reason = (
            f"Reviewed {len(active)} active goals. Updated next_action on {len(updated)}: "
            + (", ".join(updated[:4]) if updated else "none.")
        )
        return _result(routine, "completed", reason, events, now_mono)

    def _routine_memory_compaction_check(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Check hot log files for size threshold; emit warning trace if exceeded.
        No compaction performed here — compaction is owned by nightly.py or JournalManager.
        """
        routine = "memory_compaction_check"
        now_mono = time.monotonic()
        events: list[Any] = []

        hot_dir_candidates = [
            _MIND_DIR,
            _REPO_ROOT / "data" / "journal" / "hot",
            _REPO_ROOT / "data" / "runtime",
        ]

        large_files: list[str] = []
        for directory in hot_dir_candidates:
            if not directory.exists():
                continue
            for p in directory.iterdir():
                if p.suffix in (".jsonl", ".json", ".log") and p.is_file():
                    try:
                        size = p.stat().st_size
                        if size > _LOG_SIZE_WARN_BYTES:
                            large_files.append(f"{p.name}={size // (1024 * 1024)}MB")
                    except OSError:
                        pass

        if large_files:
            events.append({"large_files": large_files})
            if self._trace is not None:
                try:
                    self._trace.emit(
                        "warning",
                        f"Log compaction recommended. Large files: {', '.join(large_files[:4])}",
                        level="warning",
                    )
                except Exception:
                    pass

        reason = (
            f"Hot log scan complete. {len(large_files)} file(s) exceed threshold."
            + (f" Files: {', '.join(large_files[:3])}." if large_files else "")
        )
        result_str = "completed" if not large_files else "completed"
        return _result(routine, result_str, reason, events, now_mono)

    def _routine_self_health_check(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Check disk free, memory usage, LLM availability, and log file health.
        Uses shutil.disk_usage and snapshot data — no subprocess.
        """
        routine = "self_health_check"
        now_mono = time.monotonic()
        events: list[Any] = []
        issues: list[str] = []

        # Disk free
        try:
            usage = shutil.disk_usage(_REPO_ROOT)
            free_gb = usage.free / (1024 ** 3)
            total_gb = usage.total / (1024 ** 3)
            pct_used = (usage.used / usage.total) * 100.0 if usage.total else 0.0
            events.append({"disk_free_gb": round(free_gb, 2), "disk_used_pct": round(pct_used, 1)})
            if free_gb < 2.0:
                issues.append(f"disk low: {free_gb:.2f}GB free of {total_gb:.1f}GB")
        except OSError as exc:
            issues.append(f"disk check failed: {exc}")

        # Memory from snapshot
        mem_pct = snapshot.get("system", {}).get("memory_percent")
        if mem_pct is not None:
            events.append({"memory_pct": round(float(mem_pct), 1)})
            if float(mem_pct) > 90.0:
                issues.append(f"memory high: {mem_pct:.1f}%")

        # LLM availability from snapshot
        llm_info = snapshot.get("llm", {})
        llm_available = bool(llm_info.get("available", False))
        events.append({"llm_available": llm_available})
        if not llm_available:
            issues.append("LLM unavailable")

        # Cognitive trace log size
        trace_file = _MIND_DIR / "cognitive_trace.jsonl"
        try:
            trace_size = trace_file.stat().st_size
            trace_mb = trace_size / (1024 * 1024)
            events.append({"cognitive_trace_mb": round(trace_mb, 2)})
            if trace_mb > 50.0:
                issues.append(f"cognitive_trace.jsonl large: {trace_mb:.1f}MB")
        except OSError:
            pass

        reason = (
            "Health check complete. "
            + (f"Issues: {'; '.join(issues)}." if issues else "All nominal.")
        )
        result_str = "completed" if not issues else "completed"

        if issues and self._trace is not None:
            try:
                self._trace.emit("warning", f"Self-health issues: {'; '.join(issues[:3])}", level="warning")
            except Exception:
                pass

        return _result(routine, result_str, reason, events, now_mono)

    def _routine_self_improvement_planning(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        """
        Propose a small repo improvement by writing a JSON record to
        data/mind/self_improvement_queue.json.  Does NOT auto-apply.
        """
        routine = "self_improvement_planning"
        now_mono = time.monotonic()

        queue_file = _MIND_DIR / "self_improvement_queue.json"

        # Gather simple observations to base proposals on
        proposals_seen: list[dict[str, Any]] = []
        try:
            if queue_file.exists():
                proposals_seen = json.loads(queue_file.read_text(encoding="utf-8"))
                if not isinstance(proposals_seen, list):
                    proposals_seen = []
        except (json.JSONDecodeError, OSError):
            proposals_seen = []

        # Build a lightweight proposal based on observable state
        body: dict[str, Any] = {}
        if self._memory is not None:
            try:
                body = self._memory.get_body()
            except Exception:
                pass

        skills: dict[str, Any] = {}
        if self._memory is not None:
            try:
                skills = self._memory.get_skills()
            except Exception:
                pass

        confirmed = skills.get("confirmed_capabilities", [])
        baselines_known = sum(
            1 for k in ("cpu_temp_baseline", "cpu_percent_baseline",
                        "disk_temp_baseline", "memory_percent_baseline")
            if body.get(k) is not None
        )

        # Simple heuristic: suggest what's least developed
        if baselines_known < 2:
            proposal_text = (
                "Improve sensor baseline learning: extend reflection window or add "
                "disk temperature baseline tracking to ReflectionEngine."
            )
            area = "sensor_baselines"
        elif len(confirmed) < 5:
            proposal_text = (
                "Expand capability discovery: add a passive scan for common developer "
                "tools (git, docker, python, node) at startup."
            )
            area = "capability_discovery"
        else:
            proposal_text = (
                "Add a lightweight anomaly threshold to body_baseline_observation routine "
                "that triggers an autobiography event when CPU temp exceeds 3× std deviation."
            )
            area = "anomaly_detection"

        # Deduplicate by area
        existing_areas = {p.get("area") for p in proposals_seen}
        if area in existing_areas:
            return _result(
                routine,
                "skipped",
                f"Proposal for area '{area}' already in queue.",
                next_run_after=now_mono,
            )

        record: dict[str, Any] = {
            "timestamp": time.time(),
            "area": area,
            "proposal": proposal_text,
            "status": "pending",
            "requires_approval": True,
        }
        proposals_seen.append(record)

        try:
            _MIND_DIR.mkdir(parents=True, exist_ok=True)
            queue_file.write_text(
                json.dumps(proposals_seen, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
        except OSError as exc:
            return _result(routine, "failed", f"Could not write queue: {exc}", next_run_after=now_mono)

        return _result(
            routine,
            "completed",
            f"Proposed improvement in area '{area}'. Requires approval before application.",
            [{"area": area, "proposal_len": len(proposal_text)}],
            now_mono,
        )
