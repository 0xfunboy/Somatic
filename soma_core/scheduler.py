from __future__ import annotations

import time
from typing import Any


class BudgetedScheduler:
    def __init__(self) -> None:
        self._last_run: dict[str, float] = {}
        self._last_reason: dict[str, str] = {}
        self._last_interval: dict[str, float] = {}

    def due(self, name: str, interval_sec: float) -> bool:
        now = time.time()
        last = float(self._last_run.get(name, 0.0) or 0.0)
        return (now - last) >= max(0.0, float(interval_sec))

    def mark(self, name: str) -> None:
        self._last_run[name] = time.time()
        self._last_reason[name] = "ran"

    def allow(self, name: str, interval_sec: float, resource_governor: Any, cost: str = "low") -> tuple[bool, str]:
        self._last_interval[name] = max(0.0, float(interval_sec))
        if not self.due(name, interval_sec):
            reason = "interval_not_due"
            self._last_reason[name] = reason
            return False, reason
        allowed, reason = resource_governor.allow(name, estimated_cost=cost)
        self._last_reason[name] = reason
        return allowed, reason

    def status(self) -> dict[str, Any]:
        now = time.time()
        rows: dict[str, Any] = {}
        for name in sorted(set(self._last_run) | set(self._last_interval)):
            last = float(self._last_run.get(name, 0.0) or 0.0)
            interval = float(self._last_interval.get(name, 0.0) or 0.0)
            next_due_in = max(0.0, interval - (now - last)) if last and interval else 0.0
            rows[name] = {
                "last_run_at": last,
                "interval_sec": round(interval, 3),
                "next_due_in_sec": round(next_due_in, 3),
                "last_reason": self._last_reason.get(name, ""),
            }
        return {"timestamp": now, "tasks": rows}
