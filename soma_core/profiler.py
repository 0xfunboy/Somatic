from __future__ import annotations

import json
import time
from collections import deque
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from soma_core.config import CFG


_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


class OperationProfiler:
    def __init__(self, *, data_root: Path | None = None, window: int = 120) -> None:
        self._data_root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
        self._state_path = self._data_root / "performance_state.json"
        self._window = max(20, int(window))
        self._active: dict[str, float] = {}
        self._metrics: dict[str, deque[float]] = {}
        self._latest: dict[str, float] = {}
        self._counts: dict[str, int] = {}
        self._gauge_values: dict[str, float] = {}
        self._last_persist_at = 0.0
        self._has_persisted_operations = False

    def start(self, name: str) -> None:
        self._active[name] = time.perf_counter()

    def end(self, name: str) -> float:
        started = self._active.pop(name, None)
        if started is None:
            return 0.0
        duration_ms = max(0.0, (time.perf_counter() - started) * 1000.0)
        self.record(name, duration_ms)
        return duration_ms

    @contextmanager
    def measure(self, name: str) -> Iterator[None]:
        self.start(name)
        try:
            yield
        finally:
            self.end(name)

    def record(self, name: str, duration_ms: float) -> None:
        series = self._metrics.setdefault(name, deque(maxlen=self._window))
        value = round(max(0.0, float(duration_ms)), 3)
        series.append(value)
        self._latest[name] = value
        self._counts[name] = int(self._counts.get(name, 0)) + 1
        if not self._has_persisted_operations:
            self._persist(force=True)
            return
        self._persist_if_needed()

    def set_gauge(self, name: str, value: float) -> None:
        self._gauge_values[name] = round(float(value), 3)
        self._persist_if_needed()

    def summary(self) -> dict[str, Any]:
        operations: dict[str, Any] = {}
        slowest_name = ""
        slowest_ms = 0.0
        for name, values in self._metrics.items():
            if not values:
                continue
            avg_ms = round(sum(values) / len(values), 3)
            latest_ms = round(self._latest.get(name, values[-1]), 3)
            max_ms = round(max(values), 3)
            operations[name] = {
                "avg_ms": avg_ms,
                "latest_ms": latest_ms,
                "max_ms": max_ms,
                "count": int(self._counts.get(name, 0)),
            }
            if latest_ms >= slowest_ms:
                slowest_name = name
                slowest_ms = latest_ms
        payload = {
            "timestamp": time.time(),
            "operations": operations,
            "gauges": dict(self._gauge_values),
            "slowest_operation": slowest_name,
            "slowest_operation_ms": round(slowest_ms, 3),
            "tick_total_ms": round(self._latest.get("tick_total", 0.0), 3),
            "event_loop_lag_ms": round(self._gauge_values.get("event_loop_lag_ms", 0.0), 3),
        }
        self._persist(force=False, payload=payload)
        return payload

    def _persist_if_needed(self) -> None:
        now = time.time()
        if (now - self._last_persist_at) >= max(1.0, CFG.resource_write_state_interval_sec):
            self._persist()

    def _persist(self, *, force: bool = False, payload: dict[str, Any] | None = None) -> None:
        now = time.time()
        if not force and (now - self._last_persist_at) < max(1.0, CFG.resource_write_state_interval_sec):
            return
        data = payload or {
            "timestamp": now,
            "operations": {
                name: {
                    "avg_ms": round(sum(values) / len(values), 3),
                    "latest_ms": round(self._latest.get(name, values[-1] if values else 0.0), 3),
                    "max_ms": round(max(values) if values else 0.0, 3),
                    "count": int(self._counts.get(name, 0)),
                }
                for name, values in self._metrics.items()
                if values
            },
            "gauges": dict(self._gauge_values),
            "slowest_operation": "",
            "slowest_operation_ms": 0.0,
            "tick_total_ms": round(self._latest.get("tick_total", 0.0), 3),
            "event_loop_lag_ms": round(self._gauge_values.get("event_loop_lag_ms", 0.0), 3),
        }
        if not data.get("slowest_operation"):
            slowest_name = ""
            slowest_ms = 0.0
            for name, row in (data.get("operations") or {}).items():
                latest_ms = float((row or {}).get("latest_ms", 0.0) or 0.0)
                if latest_ms >= slowest_ms:
                    slowest_name = name
                    slowest_ms = latest_ms
            data["slowest_operation"] = slowest_name
            data["slowest_operation_ms"] = round(slowest_ms, 3)
        _save_json(self._state_path, data)
        self._last_persist_at = now
        self._has_persisted_operations = bool(data.get("operations"))
