"""
soma_core/nightly.py — Daily autobiographical summary and log compaction.

At SOMA_NIGHTLY_HOUR:SOMA_NIGHTLY_MINUTE (default 03:30 UTC) writes a
structured markdown reflection page and optionally compacts hot logs.

Design rules:
  - stdlib only, no external deps
  - thread-safe
  - never crashes the caller
  - deterministic version always written first; LLM only polishes it
  - `_REPO_ROOT = Path(__file__).parent.parent.resolve()`
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

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


NIGHTLY_ENABLED       = _bool("SOMA_NIGHTLY_REFLECTION", True)
NIGHTLY_HOUR          = int(_float("SOMA_NIGHTLY_HOUR", 3.0))
NIGHTLY_MINUTE        = int(_float("SOMA_NIGHTLY_MINUTE", 30.0))
NIGHTLY_REQUIRE_IDLE  = _bool("SOMA_NIGHTLY_REQUIRE_IDLE", True)
NIGHTLY_COMPACT_LOGS  = _bool("SOMA_NIGHTLY_COMPACT_LOGS", True)
NIGHTLY_USE_LLM       = _bool("SOMA_NIGHTLY_USE_LLM", True)

_REPO_ROOT             = Path(__file__).parent.parent.resolve()
_NIGHTLY_LOG           = _REPO_ROOT / "data" / "mind" / "nightly_reflections.jsonl"
_DAILY_DIR             = _REPO_ROOT / "data" / "autobiography" / "daily"
_MIND_DIR              = _REPO_ROOT / "data" / "mind"

# Window around the configured time during which nightly reflection may fire
_WINDOW_SECONDS        = 300   # 5 minutes
# Minimum seconds of idle before running when NIGHTLY_REQUIRE_IDLE=True
_IDLE_REQUIRED_S       = 1800.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _date_str(dt: datetime | None = None) -> str:
    return (_utc_now() if dt is None else dt).strftime("%Y-%m-%d")


def _load_jsonl(path: Path, limit: int = 200) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    except (FileNotFoundError, OSError):
        pass
    return records


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return default


def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(obj, ensure_ascii=True) + "\n")
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Markdown builder
# ---------------------------------------------------------------------------

def _build_markdown(
    date_str: str,
    *,
    autobiography_events: list[dict[str, Any]],
    recent_reflections: list[dict[str, Any]],
    capability_events: list[dict[str, Any]],
    goals_data: dict[str, Any],
    self_model: dict[str, Any],
    narrative: dict[str, Any],
) -> str:
    lines: list[str] = [f"# Soma Nightly Reflection — {date_str}", ""]

    # ── Continuity ────────────────────────────────────────────────────────────
    lines.append("## Continuity")
    stage = narrative.get("current_stage", "unknown")
    last_insight = narrative.get("last_insight", "")
    growth = self_model.get("growth", {})
    total_reflections = growth.get("total_reflections", 0)
    session_lines = [f"Stage: **{stage}**.  Total reflections to date: {total_reflections}."]
    if last_insight:
        session_lines.append(f"Last insight: {last_insight}")
    lines.extend(session_lines)
    lines.append("")

    # ── Body ──────────────────────────────────────────────────────────────────
    lines.append("## Body")
    body = self_model.get("known_body", {})
    body_events = [e for e in autobiography_events if e.get("kind") == "body_learning"]
    if body:
        for k, v in sorted(body.items()):
            if v is not None:
                lines.append(f"- {k}: {v}")
    else:
        lines.append("- No body baselines recorded yet.")
    if body_events:
        lines.append("")
        lines.append("Body events today:")
        for ev in body_events[-5:]:
            title = ev.get("title", "")
            summary = ev.get("summary", "")
            lines.append(f"- **{title}**: {summary}")
    lines.append("")

    # ── Dialogue ──────────────────────────────────────────────────────────────
    lines.append("## Dialogue")
    dialogue_events = [e for e in autobiography_events if e.get("kind") == "dialogue"]
    if dialogue_events:
        for ev in dialogue_events[-6:]:
            ts = ev.get("timestamp")
            ts_str = ""
            if ts is not None:
                try:
                    dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                    ts_str = f" *(~{dt.strftime('%H:%M UTC')})*"
                except (ValueError, OSError):
                    pass
            title = ev.get("title", "")
            summary = ev.get("summary", "")
            lines.append(f"- **{title}**{ts_str}: {summary}")
    else:
        lines.append("- No operator interactions recorded today.")
    lines.append("")

    # ── Capabilities ──────────────────────────────────────────────────────────
    lines.append("## Capabilities")
    cap_events = [e for e in autobiography_events if e.get("kind") == "capability"]
    cap_events.extend(capability_events)
    if cap_events:
        for ev in cap_events[-6:]:
            title = ev.get("title", "")
            summary = ev.get("summary", "")
            lines.append(f"- **{title}**: {summary}")
    else:
        lines.append("- No capability events today.")
    lines.append("")

    # ── Risks ─────────────────────────────────────────────────────────────────
    lines.append("## Risks")
    risk_events = [e for e in autobiography_events if e.get("kind") in ("failure", "self_modification")]
    blocked_events = [
        e for e in autobiography_events
        if "blocked" in str(e.get("kind", "")).lower()
        or "blocked" in str(e.get("title", "")).lower()
    ]
    all_risk = risk_events + blocked_events
    if all_risk:
        for ev in all_risk[-5:]:
            title = ev.get("title", "")
            summary = ev.get("summary", "")
            lines.append(f"- **{title}**: {summary}")
    else:
        lines.append("- No blocked or dangerous events today.")
    lines.append("")

    # ── Goals ─────────────────────────────────────────────────────────────────
    lines.append("## Goals")
    active_goals = [g for g in goals_data.get("active_goals", []) if g.get("status") == "active"]
    if active_goals:
        for g in sorted(active_goals, key=lambda x: -float(x.get("priority", 0))):
            progress_pct = int(float(g.get("progress", 0.0)) * 100)
            next_action = g.get("next_action", "observe")
            lines.append(
                f"- **{g.get('title', g.get('id', '?'))}** "
                f"(priority {float(g.get('priority', 0)):.2f}, progress {progress_pct}%) "
                f"— next: {next_action}"
            )
    else:
        lines.append("- No active goals.")
    lines.append("")

    # ── Memory ────────────────────────────────────────────────────────────────
    lines.append("## Memory")
    recently_learned = growth.get("recently_learned", [])
    if recently_learned:
        lines.append(f"Recently learned ({len(recently_learned)} entries):")
        for entry in recently_learned[-5:]:
            if isinstance(entry, dict):
                lines.append(f"- {entry.get('fact', str(entry))}")
            else:
                lines.append(f"- {entry}")
    else:
        lines.append("- No new learning recorded.")
    if recent_reflections:
        lines.append("")
        lines.append(f"Recent reflections ({len(recent_reflections)}):")
        for r in recent_reflections[-3:]:
            trigger = r.get("trigger", "")
            summary = r.get("summary", "")
            lines.append(f"- [{trigger}] {summary}")
    lines.append("")

    # ── Next intentions ───────────────────────────────────────────────────────
    lines.append("## Next intentions")
    intentions = _derive_intentions(active_goals, recently_learned, all_risk)
    for intention in intentions:
        lines.append(f"- {intention}")
    lines.append("")

    return "\n".join(lines)


def _derive_intentions(
    active_goals: list[dict[str, Any]],
    recently_learned: list[Any],
    risk_events: list[dict[str, Any]],
) -> list[str]:
    """
    Produce 3-5 concrete next steps from observable state.
    Purely deterministic — no LLM.
    """
    intentions: list[str] = []

    # Top priority goal
    if active_goals:
        top = max(active_goals, key=lambda g: float(g.get("priority", 0)))
        next_action = top.get("next_action", "observe")
        intentions.append(
            f"Continue goal '{top.get('title', top.get('id', '?'))}' — action: {next_action}."
        )

    # Learning continuity
    if recently_learned:
        intentions.append(
            "Consolidate recent learnings into body model baselines during next idle window."
        )
    else:
        intentions.append(
            "Accumulate more sensor observations to establish stable body baselines."
        )

    # Risk follow-up
    if risk_events:
        intentions.append(
            "Review blocked/failed events and update policy constraints if patterns repeat."
        )

    # Dialogue improvement if no dialogue events today
    intentions.append(
        "Engage with operator to improve dialogue quality and gather preference signals."
    )

    # Capability expansion
    intentions.append(
        "Verify confirmed capabilities remain available and probe for new environment tools."
    )

    return intentions[:5]


# ---------------------------------------------------------------------------
# NightlyReflection
# ---------------------------------------------------------------------------

class NightlyReflection:
    """
    Generates a daily autobiographical reflection markdown page at quiet time.

    Wiring:
        nightly = NightlyReflection(
            journal=journal_manager,
            autobiography=autobiography,
            trace=cognitive_trace,
            call_llm_raw=lambda prompt, timeout: str | None,
        )
        # call from a low-frequency background hook or RoutineRunner:
        nightly.check_and_run(last_user_interaction_at=soma_mind._last_user_interaction_at)
    """

    def __init__(
        self,
        *,
        journal: Any = None,
        autobiography: Any = None,
        trace: Any = None,
        call_llm_raw: Callable[[str, float], str | None] | None = None,
    ) -> None:
        self._journal = journal
        self._autobiography = autobiography
        self._trace = trace
        self._call_llm_raw = call_llm_raw
        self._lock = threading.Lock()
        self._last_run_date: str = ""

    # ── public API ─────────────────────────────────────────────────────────────

    def check_and_run(self, *, last_user_interaction_at: float) -> dict[str, Any] | None:
        """
        Call periodically (e.g. once per minute from server.py, or from a routine).

        Returns the reflection result dict if the nightly ran, None if skipped.
        Never raises.
        """
        try:
            return self._check_and_run_inner(last_user_interaction_at=last_user_interaction_at)
        except Exception:
            return None

    def run_now(self, date: str | None = None, *, use_llm: bool = False) -> dict[str, Any]:
        """
        Run immediately regardless of time or idle checks.
        Returns the result dict.  Never raises.
        """
        try:
            return self._run_reflection(date=date, use_llm=use_llm)
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "date": date or _date_str(),
                "timestamp": time.time(),
            }

    # ── internals ──────────────────────────────────────────────────────────────

    def _check_and_run_inner(self, *, last_user_interaction_at: float) -> dict[str, Any] | None:
        if not NIGHTLY_ENABLED:
            return None

        now = _utc_now()
        today_str = _date_str(now)

        # Time-window check: only run within ±WINDOW_SECONDS of configured time
        target_seconds = NIGHTLY_HOUR * 3600 + NIGHTLY_MINUTE * 60
        current_seconds = now.hour * 3600 + now.minute * 60 + now.second
        delta = abs(current_seconds - target_seconds)
        # Handle midnight wrap
        delta = min(delta, 86400 - delta)
        if delta > _WINDOW_SECONDS:
            return None

        # Deduplication — only run once per calendar day
        with self._lock:
            if self._last_run_date == today_str:
                return None

        # Idle check
        if NIGHTLY_REQUIRE_IDLE:
            idle_s = time.time() - last_user_interaction_at
            if idle_s < _IDLE_REQUIRED_S:
                return None

        with self._lock:
            # Re-check under lock after acquiring
            if self._last_run_date == today_str:
                return None
            self._last_run_date = today_str

        return self._run_reflection(date=today_str, use_llm=NIGHTLY_USE_LLM)

    def _run_reflection(self, date: str | None, *, use_llm: bool) -> dict[str, Any]:
        date_str = date if date else _date_str()
        started_at = time.time()

        # ── Gather data ───────────────────────────────────────────────────────

        # Autobiography events for the day
        auto_events: list[dict[str, Any]] = []
        if self._autobiography is not None:
            try:
                auto_events = self._autobiography.get_recent_summary(n_events=50)
                # Filter to today
                auto_events = [
                    e for e in auto_events
                    if self._event_date(e) == date_str
                ]
            except Exception:
                auto_events = []
        else:
            # Fall back to reading JSONL directly
            jsonl_path = _DAILY_DIR / f"{date_str}.jsonl"
            auto_events = _load_jsonl(jsonl_path, limit=100)

        # Recent reflections (from memory)
        recent_reflections: list[dict[str, Any]] = []
        reflections_file = _MIND_DIR / "reflections.jsonl"
        recent_reflections = _load_jsonl(reflections_file, limit=10)

        # Capability events
        capability_events: list[dict[str, Any]] = []
        if self._journal is not None:
            try:
                all_events = self._journal.recent_events(limit=200)
                capability_events = [
                    e for e in all_events
                    if e.get("kind") in ("skill_learned", "capability")
                    and self._event_date(e) == date_str
                ]
            except Exception:
                pass

        # Goals
        goals_file = _MIND_DIR / "goals.json"
        goals_data = _load_json(goals_file, {"active_goals": [], "completed_goals": []})

        # Self model
        self_model = _load_json(_MIND_DIR / "self_model.json", {})
        narrative = _load_json(
            _REPO_ROOT / "data" / "autobiography" / "self_narrative.json", {}
        )

        # ── Build deterministic markdown ──────────────────────────────────────
        md_content = _build_markdown(
            date_str,
            autobiography_events=auto_events,
            recent_reflections=recent_reflections,
            capability_events=capability_events,
            goals_data=goals_data,
            self_model=self_model,
            narrative=narrative,
        )

        # ── Optionally polish with LLM ─────────────────────────────────────────
        llm_used = False
        if use_llm and self._call_llm_raw is not None:
            try:
                polished = self._llm_polish(md_content, date_str)
                if polished and len(polished) > 200:
                    md_content = polished
                    llm_used = True
            except Exception:
                pass  # fall back to deterministic version silently

        # ── Write daily markdown ──────────────────────────────────────────────
        daily_md_path = _DAILY_DIR / f"{date_str}.md"
        md_written = False
        try:
            _DAILY_DIR.mkdir(parents=True, exist_ok=True)
            daily_md_path.write_text(md_content, encoding="utf-8")
            md_written = True
        except OSError:
            pass

        # ── Compact logs ──────────────────────────────────────────────────────
        compact_result: dict[str, Any] = {}
        if NIGHTLY_COMPACT_LOGS and self._journal is not None:
            try:
                compact_result = self._journal.compact_now()
            except Exception as exc:
                compact_result = {"error": str(exc)}

        # ── Build result dict ─────────────────────────────────────────────────
        elapsed = time.time() - started_at
        result: dict[str, Any] = {
            "timestamp": started_at,
            "date": date_str,
            "status": "completed" if md_written else "partial",
            "md_path": str(daily_md_path) if md_written else None,
            "events_count": len(auto_events),
            "reflections_count": len(recent_reflections),
            "llm_used": llm_used,
            "compact_result": compact_result,
            "elapsed_s": round(elapsed, 3),
        }

        # ── Persist to nightly_reflections.jsonl ──────────────────────────────
        _append_jsonl(_NIGHTLY_LOG, result)

        # ── Write autobiography event ─────────────────────────────────────────
        if self._autobiography is not None:
            try:
                self._autobiography.write_event({
                    "kind": "milestone",
                    "title": f"Nightly reflection — {date_str}",
                    "summary": (
                        f"Daily summary generated. {len(auto_events)} events processed. "
                        f"LLM polish: {'yes' if llm_used else 'no'}."
                    ),
                    "impact": "low",
                })
            except Exception:
                pass

        # ── Emit trace event ──────────────────────────────────────────────────
        if self._trace is not None:
            try:
                self._trace.emit(
                    "reflection",
                    f"Nightly reflection complete for {date_str}. "
                    f"{len(auto_events)} events. LLM={'yes' if llm_used else 'no'}.",
                    outputs={"date": date_str, "llm_used": llm_used, "elapsed_s": elapsed},
                    level="info",
                )
            except Exception:
                pass

        return result

    def _llm_polish(self, raw_md: str, date_str: str) -> str | None:
        """
        Call the LLM to lightly polish the deterministic markdown.
        Returns polished text, or None on any failure.
        """
        if self._call_llm_raw is None:
            return None

        prompt = (
            f"You are Soma's autobiographical memory module. Below is a raw nightly reflection "
            f"for {date_str}. Improve its readability and narrative flow without adding fictional "
            f"content. Preserve all factual data, bullet points, and section headers exactly. "
            f"Output only the improved markdown, no preamble.\n\n{raw_md[:6000]}"
        )
        try:
            result = self._call_llm_raw(prompt, 20.0)
            return result if isinstance(result, str) and result.strip() else None
        except Exception:
            return None

    @staticmethod
    def _event_date(event: dict[str, Any]) -> str:
        """Extract YYYY-MM-DD string from an event's timestamp field."""
        ts = event.get("timestamp")
        if ts is not None:
            try:
                dt = datetime.fromtimestamp(float(ts), tz=timezone.utc)
                return _date_str(dt)
            except (ValueError, OSError):
                pass
        return _date_str()
