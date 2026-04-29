from __future__ import annotations

import json
import time
from collections import deque
from pathlib import Path
from typing import Any

from soma_core.config import CFG

try:
    import psutil
except ImportError:  # pragma: no cover - optional dependency
    psutil = None


_REPO_ROOT = Path(__file__).parent.parent.resolve()


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _clamp01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))


class ResourceGovernor:
    def __init__(self, *, data_root: Path | None = None) -> None:
        self.enabled = CFG.resource_governor
        self._data_root = Path(data_root or (_REPO_ROOT / "data" / "mind"))
        self._state_path = self._data_root / "resource_state.json"
        self._history_path = self._data_root / "resource_history.jsonl"
        self._state = _load_json(
            self._state_path,
            {
                "timestamp": 0.0,
                "mode": CFG.resource_mode_default,
                "reasons": [],
                "host_pressure": 0.0,
                "throttled_operations": [],
                "sample": {},
                "budget": {},
            },
        )
        self._runtime_metrics: dict[str, Any] = {}
        self._operation_history: dict[str, deque[dict[str, Any]]] = {}
        self._operation_last: dict[str, dict[str, Any]] = {}
        self._bytes_window: deque[dict[str, Any]] = deque(maxlen=512)
        self._stable_since = 0.0
        self._last_history_write_at = float(self._state.get("timestamp", 0.0) or 0.0)
        self._last_mode_change_at = float(self._state.get("timestamp", 0.0) or 0.0)

    def update_runtime_metrics(self, metrics: dict[str, Any] | None = None, **extra: Any) -> None:
        merged = dict(metrics or {})
        merged.update(extra)
        self._runtime_metrics.update(merged)

    def record_bytes(self, channel: str, count: int) -> None:
        self._bytes_window.append(
            {
                "timestamp": time.time(),
                "channel": str(channel),
                "bytes": max(0, int(count)),
            }
        )

    def sample(self, snapshot: dict | None = None) -> dict:
        system = (snapshot or {}).get("system", {}) if isinstance(snapshot, dict) else {}
        metabolic = (snapshot or {}).get("metabolic", {}) if isinstance(snapshot, dict) else {}
        reward = (snapshot or {}).get("reward", {}) if isinstance(snapshot, dict) else {}
        now = time.time()

        cpu_percent = float(system.get("cpu_percent") if system.get("cpu_percent") is not None else self._ps_cpu_percent())
        memory_percent = float(system.get("memory_percent") if system.get("memory_percent") is not None else self._ps_memory_percent())
        swap_percent = float(system.get("swap_percent") if system.get("swap_percent") is not None else self._ps_swap_percent())
        disk_busy_percent = float(system.get("disk_busy_percent") or 0.0)
        disk_used_percent = float(system.get("disk_used_percent") or 0.0)
        cpu_temp = float(system.get("cpu_temp") or 0.0)
        event_loop_lag_ms = float(self._runtime_metrics.get("event_loop_lag_ms", 0.0) or 0.0)
        average_tick_duration_ms = float(self._runtime_metrics.get("tick_total_ms_avg", self._runtime_metrics.get("tick_total_ms", 0.0)) or 0.0)
        provider_duration_ms = float(self._runtime_metrics.get("provider_ms_avg", 0.0) or 0.0)
        projector_duration_ms = float(self._runtime_metrics.get("projector_ms_avg", 0.0) or 0.0)
        ui_clients = int(self._runtime_metrics.get("ui_clients", 0) or 0)
        metabolic_stress = float(metabolic.get("stress", self._runtime_metrics.get("metabolic_stress", 0.0)) or 0.0)
        reward_trend = float(reward.get("trend", reward.get("rolling_score", self._runtime_metrics.get("reward_trend", 0.0))) or 0.0)

        llm_calls_per_hour = self._calls_per_hour(("internal_llm", "bios_llm", "chat_llm"))
        bios_calls_per_hour = self._calls_per_hour(("bios_cycle",))
        shell_calls_per_hour = self._calls_per_hour(("shell", "heavy_shell", "repo_test"))
        file_write_bytes_per_min = self._bytes_per_minute("file_write")
        ui_bytes_per_sec = self._bytes_per_second("ui")

        cpu_pressure = max(0.0, min(1.5, cpu_percent / max(CFG.host_cpu_reduced_percent, 1.0)))
        mem_pressure = max(0.0, min(1.5, memory_percent / max(CFG.host_mem_reduced_percent, 1.0)))
        swap_pressure = max(0.0, min(1.5, swap_percent / max(CFG.host_swap_critical_percent, 1.0))) if CFG.host_swap_critical_percent > 0 else 0.0
        temp_pressure = max(0.0, min(1.5, cpu_temp / max(CFG.host_temp_reduced_c, 1.0))) if cpu_temp else 0.0
        lag_pressure = max(0.0, min(1.5, event_loop_lag_ms / max(CFG.event_loop_lag_reduced_ms, 1.0)))
        tick_pressure = max(0.0, min(1.5, average_tick_duration_ms / max(CFG.tick_duration_reduced_ms, 1.0)))
        host_pressure = round(
            _clamp01(
                max(
                    cpu_pressure / 1.5,
                    mem_pressure / 1.5,
                    min(1.0, swap_pressure / 1.5),
                    min(1.0, temp_pressure / 1.5),
                    min(1.0, lag_pressure / 1.5),
                    min(1.0, tick_pressure / 1.5),
                    min(1.0, disk_busy_percent / 100.0),
                    _clamp01(metabolic_stress),
                )
            ),
            4,
        )

        reasons: list[str] = []
        base_mode = "normal"
        if (
            cpu_percent >= CFG.host_cpu_critical_percent
            or memory_percent >= CFG.host_mem_critical_percent
            or swap_percent >= CFG.host_swap_critical_percent
            or cpu_temp >= CFG.host_temp_critical_c
            or event_loop_lag_ms >= CFG.event_loop_lag_critical_ms
            or average_tick_duration_ms >= CFG.tick_duration_critical_ms
        ):
            base_mode = "critical"
        elif (
            cpu_percent >= CFG.host_cpu_reduced_percent
            or memory_percent >= CFG.host_mem_reduced_percent
            or cpu_temp >= CFG.host_temp_reduced_c
            or event_loop_lag_ms >= CFG.event_loop_lag_reduced_ms
            or average_tick_duration_ms >= CFG.tick_duration_reduced_ms
        ):
            base_mode = "reduced"

        if cpu_percent >= CFG.host_cpu_reduced_percent:
            reasons.append("cpu_pressure")
        if memory_percent >= CFG.host_mem_reduced_percent:
            reasons.append("memory_pressure")
        if swap_percent >= CFG.host_swap_critical_percent:
            reasons.append("swap_pressure")
        if cpu_temp >= CFG.host_temp_reduced_c:
            reasons.append("thermal_pressure")
        if event_loop_lag_ms >= CFG.event_loop_lag_reduced_ms:
            reasons.append("event_loop_lag")
        if average_tick_duration_ms >= CFG.tick_duration_reduced_ms:
            reasons.append("tick_duration_high")
        if ui_bytes_per_sec > CFG.ui_max_broadcast_bytes_per_sec:
            reasons.append("ui_bandwidth_high")
        if file_write_bytes_per_min > CFG.resource_max_state_bytes * 4:
            reasons.append("file_write_pressure")
        if metabolic_stress >= 0.6:
            reasons.append("metabolic_stress_high")

        current_mode = str(self._state.get("mode") or CFG.resource_mode_default)
        if base_mode == "critical":
            mode = "critical"
            self._stable_since = 0.0
        elif current_mode in {"critical", "recovery"}:
            if base_mode == "normal":
                if self._stable_since <= 0.0:
                    self._stable_since = now
                mode = "recovery" if (now - self._stable_since) < CFG.resource_recovery_stable_sec else "normal"
            else:
                self._stable_since = 0.0
                mode = "recovery"
        else:
            mode = base_mode
            if base_mode == "normal":
                self._stable_since = now if self._stable_since <= 0.0 else self._stable_since
            else:
                self._stable_since = 0.0

        budget = self._build_budget(mode, projector_duration_ms=projector_duration_ms)
        throttled_operations = self._throttled_operations_for_mode(mode)
        sample = {
            "cpu_percent": round(cpu_percent, 3),
            "memory_percent": round(memory_percent, 3),
            "swap_percent": round(swap_percent, 3),
            "disk_busy_percent": round(disk_busy_percent, 3),
            "disk_used_percent": round(disk_used_percent, 3),
            "cpu_temp": round(cpu_temp, 3),
            "event_loop_lag_ms": round(event_loop_lag_ms, 3),
            "average_tick_duration_ms": round(average_tick_duration_ms, 3),
            "provider_duration_ms": round(provider_duration_ms, 3),
            "projector_duration_ms": round(projector_duration_ms, 3),
            "llm_calls_per_hour": round(llm_calls_per_hour, 3),
            "bios_calls_per_hour": round(bios_calls_per_hour, 3),
            "shell_calls_per_hour": round(shell_calls_per_hour, 3),
            "file_write_bytes_per_min": int(file_write_bytes_per_min),
            "ui_connected_clients": ui_clients,
            "ui_broadcast_bytes_per_sec": int(ui_bytes_per_sec),
            "metabolic_stress": round(metabolic_stress, 4),
            "reward_trend": round(reward_trend, 4),
        }
        previous_mode = str(self._state.get("mode") or CFG.resource_mode_default)
        if previous_mode != mode:
            self._last_mode_change_at = now
        self._state = {
            "timestamp": now,
            "mode": mode,
            "previous_mode": previous_mode,
            "mode_changed_at": self._last_mode_change_at,
            "reasons": reasons,
            "host_pressure": host_pressure,
            "reward_trend": round(reward_trend, 4),
            "sample": sample,
            "budget": budget,
            "throttled_operations": throttled_operations,
        }
        self._persist(mode_changed=(previous_mode != mode))
        return dict(self._state)

    def mode(self) -> str:
        return str(self._state.get("mode") or CFG.resource_mode_default)

    def budget(self) -> dict:
        return dict(self._state.get("budget") or self._build_budget(self.mode(), projector_duration_ms=0.0))

    def allow(self, operation: str, *, estimated_cost: str = "low") -> tuple[bool, str]:
        if not self.enabled:
            return True, "resource_governor_disabled"
        mode = self.mode()
        budget = self.budget()
        op = str(operation or "").lower()
        cost = str(estimated_cost or "low").lower()

        if op in {"mutation", "mutation_proposal", "sandbox_test"} and not budget.get("mutation_allowed", False):
            return False, f"{mode}:mutation_blocked"
        if op in {"growth", "growth_eval", "mind_growth"} and not budget.get("growth_allowed", False):
            return False, f"{mode}:growth_blocked"
        if op in {"internal_llm", "bios_llm"} and budget.get("internal_llm_interval_sec", 0.0) >= 3600.0:
            return False, f"{mode}:llm_paused"
        if op in {"test_suite", "repo_test"} and not budget.get("test_suite_allowed", False):
            return False, f"{mode}:tests_blocked"
        if op in {"heavy_shell"} and not budget.get("heavy_shell_allowed", False):
            return False, f"{mode}:heavy_shell_blocked"
        if op in {"shell"} and not budget.get("shell_allowed", True):
            return False, f"{mode}:shell_blocked"
        if mode == "recovery" and cost in {"medium", "high"} and op not in {"ui_full_payload", "resource_status", "bios_cycle"}:
            return False, "recovery_only_minimal_work"
        if mode == "critical" and cost == "high":
            return False, "critical_blocks_high_cost"
        return True, f"{mode}:allowed"

    def record_operation(self, operation: str, duration_ms: float, ok: bool = True) -> None:
        now = time.time()
        name = str(operation or "unknown")
        bucket = self._operation_history.setdefault(name, deque(maxlen=256))
        record = {"timestamp": now, "duration_ms": round(max(0.0, float(duration_ms)), 3), "ok": bool(ok)}
        bucket.append(record)
        self._operation_last[name] = record

    def recommended_tick_hz(self) -> float:
        return float(self.budget().get("tick_hz_max", CFG.tick_hz_max_normal))

    def recommended_bios_interval_sec(self) -> float:
        return float(self.budget().get("bios_interval_sec", CFG.bios_interval_sec_normal))

    def recommended_llm_timeout_sec(self) -> float:
        mode = self.mode()
        if mode == "normal":
            return min(20.0, CFG.llm_timeout_s)
        if mode == "reduced":
            return min(12.0, CFG.llm_timeout_s)
        if mode == "critical":
            return min(8.0, CFG.llm_timeout_s)
        return min(5.0, CFG.llm_timeout_s)

    def status(self) -> dict:
        state = dict(self._state)
        state["operation_last"] = dict(self._operation_last)
        state["recommended_tick_hz"] = self.recommended_tick_hz()
        state["recommended_bios_interval_sec"] = self.recommended_bios_interval_sec()
        state["recommended_llm_timeout_sec"] = self.recommended_llm_timeout_sec()
        return state

    def _persist(self, *, mode_changed: bool) -> None:
        _save_json(self._state_path, self._state)
        now = time.time()
        should_history = mode_changed or ((now - self._last_history_write_at) >= CFG.resource_history_interval_sec)
        if not should_history:
            return
        self._history_path.parent.mkdir(parents=True, exist_ok=True)
        with self._history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(self._state, ensure_ascii=False) + "\n")
        self._last_history_write_at = now

    def _build_budget(self, mode: str, *, projector_duration_ms: float) -> dict[str, Any]:
        projector_hz = CFG.projector_hz_normal
        if mode == "reduced":
            tick_hz = CFG.tick_hz_max_reduced
            ui_hz = min(CFG.ui_full_payload_hz, 0.5)
            projector_hz = CFG.projector_hz_reduced
            bios_interval = CFG.bios_interval_sec_reduced
            llm_interval = 1800.0
            mutation_allowed = False
            growth_allowed = False
            heavy_shell_allowed = False
            test_suite_allowed = False
        elif mode == "critical":
            tick_hz = CFG.tick_hz_max_critical
            ui_hz = min(CFG.ui_full_payload_hz, 0.25)
            projector_hz = CFG.projector_hz_critical
            bios_interval = CFG.bios_interval_sec_critical
            llm_interval = 3600.0
            mutation_allowed = False
            growth_allowed = False
            heavy_shell_allowed = False
            test_suite_allowed = False
        elif mode == "recovery":
            tick_hz = CFG.tick_hz_max_recovery
            ui_hz = min(CFG.ui_full_payload_hz, 0.2)
            projector_hz = CFG.projector_hz_recovery
            bios_interval = CFG.bios_interval_sec_recovery
            llm_interval = 3600.0
            mutation_allowed = False
            growth_allowed = False
            heavy_shell_allowed = False
            test_suite_allowed = False
        else:
            tick_hz = CFG.tick_hz_max_normal
            ui_hz = max(0.1, CFG.ui_full_payload_hz)
            bios_interval = CFG.bios_interval_sec_normal
            llm_interval = 900.0
            mutation_allowed = True
            growth_allowed = True
            heavy_shell_allowed = True
            test_suite_allowed = True
        if projector_duration_ms >= CFG.tick_duration_reduced_ms:
            projector_hz = min(projector_hz, CFG.projector_hz_critical)
        return {
            "tick_hz_max": round(float(tick_hz), 3),
            "ui_hz_max": round(float(ui_hz), 3),
            "projector_hz_max": round(float(projector_hz), 3),
            "vector_hz_max": round(float(CFG.vector_interpreter_hz if mode == "normal" else min(CFG.vector_interpreter_hz, 0.2)), 3),
            "cpp_bridge_hz_max": round(float(CFG.cpp_projection_hz if mode == "normal" else min(CFG.cpp_projection_hz, 0.05)), 3),
            "bios_interval_sec": round(float(bios_interval), 3),
            "internal_llm_interval_sec": round(float(llm_interval), 3),
            "mutation_allowed": bool(mutation_allowed),
            "growth_allowed": bool(growth_allowed),
            "shell_allowed": True,
            "heavy_shell_allowed": bool(heavy_shell_allowed),
            "test_suite_allowed": bool(test_suite_allowed),
            "write_state_interval_sec": round(float(CFG.resource_write_state_interval_sec), 3),
            "max_state_bytes": int(CFG.resource_max_state_bytes),
        }

    def _throttled_operations_for_mode(self, mode: str) -> list[str]:
        if mode == "normal":
            return []
        ops = ["full_payload_hz", "projector", "vector_interpreter", "cpp_bridge_projection", "mutation"]
        if mode in {"critical", "recovery"}:
            ops.extend(["bios_llm", "internal_llm", "heavy_shell", "test_suite"])
        if mode == "recovery":
            ops.append("growth")
        return ops

    def _calls_per_hour(self, names: tuple[str, ...]) -> float:
        now = time.time()
        count = 0
        for name in names:
            for row in self._operation_history.get(name, ()):
                if (now - float(row.get("timestamp", 0.0) or 0.0)) <= 3600.0:
                    count += 1
        return float(count)

    def _bytes_per_minute(self, channel: str) -> float:
        now = time.time()
        total = 0
        for row in self._bytes_window:
            if row.get("channel") != channel:
                continue
            if (now - float(row.get("timestamp", 0.0) or 0.0)) <= 60.0:
                total += int(row.get("bytes", 0) or 0)
        return float(total)

    def _bytes_per_second(self, channel: str) -> float:
        now = time.time()
        total = 0
        for row in self._bytes_window:
            if row.get("channel") != channel:
                continue
            if (now - float(row.get("timestamp", 0.0) or 0.0)) <= 1.0:
                total += int(row.get("bytes", 0) or 0)
        return float(total)

    def _ps_cpu_percent(self) -> float:
        if psutil is None:
            return 0.0
        return float(psutil.cpu_percent(interval=None) or 0.0)

    def _ps_memory_percent(self) -> float:
        if psutil is None:
            return 0.0
        try:
            return float(psutil.virtual_memory().percent or 0.0)
        except Exception:
            return 0.0

    def _ps_swap_percent(self) -> float:
        if psutil is None:
            return 0.0
        try:
            return float(psutil.swap_memory().percent or 0.0)
        except Exception:
            return 0.0
