from __future__ import annotations

import json
import math
import time
from pathlib import Path
from typing import Any


_REPO_ROOT = Path(__file__).parent.parent.resolve()
_DEFAULT_PATH = _REPO_ROOT / "data" / "mind" / "body_baselines.json"


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _empty_entry() -> dict[str, Any]:
    return {
        "value": 0.0,
        "min": 0.0,
        "max": 0.0,
        "samples": 0,
        "windows": 0,
        "confidence": 0.0,
        "first_seen": 0.0,
        "last_seen": 0.0,
        "stable": False,
        "last_material_change": 0.0,
    }


class BodyBaselineStore:
    def __init__(self, data_path: Path | None = None, *, window_sec: float = 120.0) -> None:
        self._path = data_path or _DEFAULT_PATH
        self._window_sec = max(1.0, float(window_sec))
        self._data: dict[str, Any] = _load_json(self._path, {})
        self._window: dict[str, dict[str, Any]] = {}

    def update_from_snapshot(self, snapshot: dict) -> dict:
        raw_ts = snapshot.get("timestamp")
        ts = float(raw_ts) if raw_ts is not None else time.time()
        system = snapshot.get("system", {}) if isinstance(snapshot, dict) else {}
        provider = snapshot.get("provider", {}) if isinstance(snapshot, dict) else {}
        source_quality = provider.get("source_quality", system.get("source_quality"))
        values = {
            "idle_cpu_percent": system.get("cpu_percent"),
            "cpu_temp_c": system.get("cpu_temp"),
            "disk_temp_c": system.get("disk_temp"),
            "ram_idle_percent": system.get("memory_percent"),
            "source_quality": source_quality,
        }
        updated_keys: list[str] = []
        stable_now: list[str] = []
        material_changes: list[str] = []
        for key, raw_value in values.items():
            if raw_value is None:
                continue
            value = float(raw_value)
            win = self._window.setdefault(
                key,
                {"started_at": ts, "samples": [], "min": value, "max": value},
            )
            win["samples"].append(value)
            win["min"] = min(float(win["min"]), value)
            win["max"] = max(float(win["max"]), value)
            if ts - float(win["started_at"]) < self._window_sec:
                continue
            entry = self._finalize_window(key, ts)
            updated_keys.append(key)
            if entry.get("stable"):
                stable_now.append(key)
            if entry.get("_material_change"):
                material_changes.append(key)
        if updated_keys:
            _save_json(self._path, self._serializable())
        return {
            "updated_keys": updated_keys,
            "stable_now": stable_now,
            "material_changes": material_changes,
            "summary": self.summary(),
        }

    def get_baseline(self, key: str) -> dict | None:
        entry = self._data.get(key)
        return dict(entry) if isinstance(entry, dict) else None

    def confidence(self, key: str) -> float:
        entry = self.get_baseline(key)
        return float(entry.get("confidence", 0.0)) if entry else 0.0

    def summary(self) -> dict:
        baselines = {}
        for key, entry in self._data.items():
            if not isinstance(entry, dict):
                continue
            baselines[key] = {
                "value": round(float(entry.get("value", 0.0)), 3),
                "min": round(float(entry.get("min", 0.0)), 3),
                "max": round(float(entry.get("max", 0.0)), 3),
                "samples": int(entry.get("samples", 0)),
                "windows": int(entry.get("windows", 0)),
                "confidence": round(float(entry.get("confidence", 0.0)), 4),
                "stable": bool(entry.get("stable", False)),
                "last_seen": float(entry.get("last_seen", 0.0)),
            }
        return {
            "keys": baselines,
            "stable_keys": [key for key, entry in baselines.items() if entry["stable"]],
            "confident_keys": [key for key, entry in baselines.items() if entry["confidence"] >= 0.65],
        }

    def _finalize_window(self, key: str, ts: float) -> dict[str, Any]:
        win = self._window.get(key) or {}
        samples = [float(item) for item in win.get("samples", [])]
        if not samples:
            return self._data.setdefault(key, _empty_entry())
        avg = sum(samples) / len(samples)
        spread = max(samples) - min(samples)
        entry = self._data.setdefault(key, _empty_entry())
        prev_value = float(entry.get("value", avg))
        prev_conf = float(entry.get("confidence", 0.0))
        entry["value"] = round(((prev_value * entry["windows"]) + avg) / max(1, entry["windows"] + 1), 4)
        entry["min"] = round(min(float(entry.get("min", avg) or avg), min(samples)), 4) if entry["samples"] else round(min(samples), 4)
        entry["max"] = round(max(float(entry.get("max", avg) or avg), max(samples)), 4) if entry["samples"] else round(max(samples), 4)
        entry["samples"] = int(entry.get("samples", 0)) + len(samples)
        entry["windows"] = int(entry.get("windows", 0)) + 1
        entry["first_seen"] = float(entry.get("first_seen") or ts)
        entry["last_seen"] = ts
        stability = max(0.0, 1.0 - min(1.0, spread / max(abs(avg), 1.0, 10.0)))
        sample_factor = min(1.0, entry["samples"] / 100.0)
        window_factor = min(1.0, entry["windows"] / 3.0)
        entry["confidence"] = round(min(1.0, (sample_factor * 0.4) + (window_factor * 0.4) + (stability * 0.2)), 4)
        entry["stable"] = bool(entry["confidence"] >= 0.65)
        delta = abs(avg - prev_value)
        threshold = max(3.0, abs(prev_value) * 0.15)
        material = bool(entry["windows"] > 1 and delta >= threshold and prev_conf >= 0.65)
        entry["_material_change"] = material
        if material:
            entry["last_material_change"] = ts
        self._window[key] = {"started_at": ts, "samples": [], "min": avg, "max": avg}
        return entry

    def _serializable(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, entry in self._data.items():
            if not isinstance(entry, dict):
                continue
            clone = dict(entry)
            clone.pop("_material_change", None)
            result[key] = clone
        return result
