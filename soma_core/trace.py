"""
soma_core/trace.py — Observable cognitive trace (NOT hidden LLM chain-of-thought).

Generates structured trace events from explicit runtime state.
Events are broadcast to the frontend and appended to cognitive_trace.jsonl.

Label in UI: COGNITIVE TRACE
Subtext: "Observable runtime trace, not hidden LLM chain-of-thought."

Persistence modes (SOMA_TRACE_PERSISTENCE):
  off       — in-memory buffer only, no disk writes
  important — persist only meaningful phases (default)
  all       — persist everything (debug mode)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    pass  # JournalManager type hint only if needed

_TRACE_FILE = Path(__file__).parent.parent / "data" / "mind" / "cognitive_trace.jsonl"
_MAX_TRACE_BUFFER = 50  # keep in-memory for frontend

# Phases that are meaningful and should be persisted in "important" mode
_IMPORTANT_PHASES: frozenset[str] = frozenset({
    "command_proposed", "command_risk_check", "command_executed",
    "command_blocked", "skill_learned",
    "self_modify_started", "self_modify_validated", "self_modify_reverted",
    "reflection", "memory_update", "growth", "warning", "llm", "fallback",
    "policy", "command_planner_request", "command_planner_response",
    "command_result_used_in_chat",
})

# High-frequency phases that should NOT be persisted in "important" mode
_NOISY_PHASES: frozenset[str] = frozenset({
    "perception", "body_model", "somatic_projection", "drives",
    "goals", "action_selection",
})

_PERSISTENCE_MODE: str = os.getenv("SOMA_TRACE_PERSISTENCE", "important").strip().lower()
if _PERSISTENCE_MODE not in {"off", "important", "all"}:
    _PERSISTENCE_MODE = "important"


class CognitiveTrace:
    """
    Append-only observable trace buffer.
    Call emit() to add events; get_recent() for frontend broadcast.
    Disk persistence controlled by SOMA_TRACE_PERSISTENCE.
    """

    PHASES = frozenset({
        "perception", "body_model", "somatic_projection", "drives",
        "goals", "policy", "action_selection", "reflection",
        "memory_update", "llm", "fallback", "warning", "growth",
        # autonomy phases
        "command_proposed", "command_risk_check", "command_executed",
        "command_blocked", "self_modify_started", "self_modify_validated",
        "self_modify_reverted", "skill_learned",
        # command planner phases
        "command_planner_request", "command_planner_response", "command_result_used_in_chat",
    })

    def __init__(self, journal: Any = None) -> None:
        self._buffer: list[dict[str, Any]] = []
        self._journal = journal  # JournalManager or None
        if _PERSISTENCE_MODE != "off":
            _TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)

    def set_journal(self, journal: Any) -> None:
        """Attach a JournalManager after construction (avoids circular imports)."""
        self._journal = journal

    def emit(
        self,
        phase: str,
        summary: str,
        *,
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        confidence: float = 1.0,
        visible: bool = True,
        level: str = "info",
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "timestamp": time.time(),
            "phase": phase,
            "summary": summary,
            "inputs": inputs or {},
            "outputs": outputs or {},
            "confidence": round(confidence, 3),
            "visible": visible,
            "level": level,
        }
        self._buffer.append(event)
        if len(self._buffer) > _MAX_TRACE_BUFFER:
            self._buffer = self._buffer[-_MAX_TRACE_BUFFER:]
        self._persist(event)
        return event

    def get_recent(self, n: int = 20, phase_filter: str | None = None) -> list[dict[str, Any]]:
        events = self._buffer
        if phase_filter and phase_filter != "all":
            events = [e for e in events if e["phase"] == phase_filter]
        return events[-n:]

    def _persist(self, event: dict[str, Any]) -> None:
        if _PERSISTENCE_MODE == "off":
            return
        phase = event["phase"]
        if _PERSISTENCE_MODE == "important" and phase in _NOISY_PHASES:
            return  # skip high-frequency noise

        # Delegate to JournalManager if available (handles deduplication + hot file rotation)
        if self._journal is not None:
            try:
                self._journal.append_trace(event)
                return
            except Exception:
                pass  # fall through to direct write

        # Direct fallback write to legacy cognitive_trace.jsonl
        self._append_to_file(event)

    def _append_to_file(self, event: dict[str, Any]) -> None:
        try:
            with _TRACE_FILE.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=True) + "\n")
        except OSError:
            pass

    # ── convenience emitters per phase ───────────────────────────────────────

    def perception(self, snapshot: dict[str, Any]) -> None:
        provider = snapshot.get("provider", {})
        system = snapshot.get("system", {})
        is_real = provider.get("is_real", False)
        quality = float(system.get("source_quality", 0.0))
        cpu_temp = system.get("cpu_temp")
        disk_temp = system.get("disk_temp")
        cpu_pct = system.get("cpu_percent")

        parts = []
        parts.append(f"Provider: {provider.get('name', 'unknown')} ({'real' if is_real else 'mock'}), quality={quality:.2f}.")
        if cpu_temp is not None:
            parts.append(f"CPU temp {cpu_temp:.1f}°C.")
        if disk_temp is not None:
            parts.append(f"Disk temp {disk_temp:.1f}°C.")
        if cpu_pct is not None:
            parts.append(f"CPU load {cpu_pct:.0f}%.")

        self.emit(
            "perception",
            " ".join(parts),
            inputs={"provider": provider.get("name"), "source_quality": quality, "is_real": is_real},
            outputs={"cpu_temp": cpu_temp, "cpu_pct": cpu_pct},
            confidence=quality,
            level="warning" if quality < 0.3 else "info",
        )

    def body_model(self, derived: dict[str, float], scenario: str) -> None:
        ts = derived.get("thermal_stress", 0.0)
        es = derived.get("energy_stress", 0.0)
        ins = derived.get("instability", 0.0)
        comfort = derived.get("comfort", 1.0)
        self.emit(
            "body_model",
            f"Scenario: {scenario}. Thermal stress {ts:.2f}, energy stress {es:.2f}, "
            f"instability {ins:.2f}, comfort {comfort:.2f}.",
            inputs={"scenario": scenario},
            outputs={"thermal_stress": ts, "energy_stress": es, "instability": ins, "comfort": comfort},
            level="warning" if max(ts, es, ins) > 0.6 else "info",
        )

    def somatic_projection(self, projector: dict[str, Any]) -> None:
        mode = projector.get("mode", "unknown")
        norm = projector.get("norm", 0.0)
        available = projector.get("available", False)
        self.emit(
            "somatic_projection",
            f"Projected body state. Mode: {mode}. Norm: {norm:.2f}." if available
            else "Somatic projector unavailable — using fallback analytic vector.",
            inputs={"mode": mode},
            outputs={"norm": norm, "available": available},
            confidence=0.9 if mode == "torchscript" else 0.5,
            level="warning" if not available else "info",
        )

    def drives(self, drive_state: dict[str, Any]) -> None:
        dominant = drive_state.get("dominant", "unknown")
        intensity = drive_state.get(dominant, 0.0)
        self.emit(
            "drives",
            f"Dominant drive: {dominant} ({intensity:.2f}). "
            f"self_knowledge={drive_state.get('self_knowledge',0):.2f}, "
            f"caution={drive_state.get('caution',0):.2f}, "
            f"expressiveness={drive_state.get('expressiveness',0):.2f}.",
            inputs={},
            outputs={"dominant": dominant, "intensity": intensity},
        )

    def goals(self, goal_id: str, goal_title: str, priority: float, progress: float) -> None:
        self.emit(
            "goals",
            f"Active goal: {goal_title} (id={goal_id}). Priority {priority:.2f}, progress {progress:.0%}.",
            outputs={"goal_id": goal_id, "priority": priority, "progress": progress},
        )

    def policy(self, mode: str, reason: str) -> None:
        self.emit(
            "policy",
            f"Policy mode: {mode}. {reason}",
            outputs={"mode": mode},
        )

    def action_selection(self, actions: list[dict[str, Any]]) -> None:
        if not actions:
            self.emit("action_selection", "No actions selected this tick.", outputs={})
            return
        names = ", ".join(a.get("name", "?") for a in actions[:3])
        silent = [a for a in actions if not a.get("visible", True)]
        visible = [a for a in actions if a.get("visible", False)]
        self.emit(
            "action_selection",
            f"Selected {len(actions)} action(s): {names}. "
            f"Silent: {len(silent)}, visible: {len(visible)}.",
            outputs={"count": len(actions), "names": names},
        )

    def reflection(self, trigger: str, summary: str, learned: list[str], confidence: float) -> None:
        learned_str = "; ".join(learned[:2]) if learned else "no new learning"
        self.emit(
            "reflection",
            f"Reflection triggered by {trigger}. {summary} Learned: {learned_str}.",
            outputs={"trigger": trigger, "learned_count": len(learned)},
            confidence=confidence,
            level="info",
        )

    def memory_update(self, updates: dict[str, Any]) -> None:
        if not updates:
            return
        keys = list(updates.keys())[:3]
        self.emit(
            "memory_update",
            f"Memory updated: {', '.join(keys)}.",
            outputs=updates,
        )

    def llm_status(self, available: bool, mode: str) -> None:
        if available:
            self.emit(
                "llm",
                f"LLM available: mode={mode}.",
                outputs={"available": True, "mode": mode},
                level="info",
            )
        else:
            self.emit(
                "fallback",
                "LLM unavailable. Reflex fallback mode active. No language generation.",
                outputs={"available": False, "mode": "fallback"},
                level="warning",
            )

    def growth(self, event: str, score: float, stage: str) -> None:
        self.emit(
            "growth",
            f"Growth event: {event}. Score: {score:.3f}. Stage: {stage}.",
            outputs={"event": event, "score": score, "stage": stage},
            level="info",
        )

    def warning(self, text: str, **kwargs: Any) -> None:
        self.emit("warning", text, level="warning", **kwargs)

    # ── autonomy phase emitters ───────────────────────────────────────────────

    def command_proposed(self, cmd: str, reason: str) -> None:
        self.emit(
            "command_proposed",
            f"Proposed: {cmd[:100]}",
            inputs={"cmd": cmd[:200], "reason": reason[:200]},
            level="info",
        )

    def command_blocked(self, cmd: str, reason: str) -> None:
        self.emit(
            "command_blocked",
            f"Blocked ({reason[:80]}): {cmd[:80]}",
            inputs={"cmd": cmd[:200]},
            outputs={"reason": reason},
            level="warning",
        )

    def command_executed(self, cmd: str, success: bool, stdout: str, stderr: str) -> None:
        result = stdout[:80] if success else (stderr or stdout)[:80]
        self.emit(
            "command_executed",
            f"{'OK' if success else 'FAIL'}: {cmd[:60]} → {result}",
            outputs={"success": success, "stdout_chars": len(stdout)},
            level="info" if success else "warning",
        )

    def skill_learned(self, skill: str, cmd: str) -> None:
        self.emit(
            "skill_learned",
            f"Skill confirmed: {skill}",
            outputs={"skill": skill, "cmd": cmd[:100]},
            level="info",
        )

    def self_modify(self, phase: str, rel_path: str, detail: str) -> None:
        self.emit(
            phase,
            f"{phase.replace('_', ' ').title()}: {rel_path} — {detail[:100]}",
            inputs={"rel_path": rel_path},
            outputs={"detail": detail[:200]},
            level="warning" if "revert" in phase else "info",
        )
