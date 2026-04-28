from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from soma_core.config import CFG


_REPO_ROOT = Path(__file__).parent.parent.resolve()


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


def _clamp01(value: Any) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = 0.0
    return max(0.0, min(1.0, numeric))


class VectorInterpreter:
    def __init__(
        self,
        *,
        enabled: bool | None = None,
        baseline_min_samples: int | None = None,
        drift_threshold: float | None = None,
        cpp_mismatch_threshold: float | None = None,
        data_root: Path | None = None,
    ) -> None:
        self.enabled = CFG.vector_interpreter if enabled is None else bool(enabled)
        self._baseline_min_samples = max(1, int(baseline_min_samples or CFG.vector_baseline_min_samples))
        self._drift_threshold = float(drift_threshold or CFG.vector_drift_threshold)
        self._cpp_mismatch_threshold = float(cpp_mismatch_threshold or CFG.vector_cpp_mismatch_threshold)
        self._path = Path(data_root or (_REPO_ROOT / "data" / "mind")) / "vector_baseline.json"
        self._baseline = _load_json(
            self._path,
            {
                "samples": 0,
                "norm_mean": 0.0,
                "tensor_mean": 0.0,
                "tensor_std": 0.0,
                "top_dim_counts": {},
                "last_vector": {},
            },
        )

    def interpret(self, snapshot: dict[str, Any], cpp_projection: dict[str, Any] | None = None) -> dict[str, Any]:
        if not self.enabled:
            return {
                "vector_stability": 0.0,
                "vector_drift": 0.0,
                "vector_anomaly": 0.0,
                "cpp_consistency": None,
                "mode_contribution": "unknown",
                "reason": "vector_interpreter_disabled",
            }

        projector = snapshot.get("projector", {}) if isinstance(snapshot, dict) else {}
        tensor = snapshot.get("tensor", {}) if isinstance(snapshot, dict) else {}
        norm = float(projector.get("norm", tensor.get("norm", 0.0)) or 0.0)
        tensor_mean = float(tensor.get("mean", snapshot.get("mean", 0.0)) or 0.0)
        tensor_std = float(tensor.get("std", snapshot.get("std", 0.0)) or 0.0)
        top_dims_raw = projector.get("top_dims", tensor.get("top_dims", [])) or []
        top_vals_raw = projector.get("top_vals", tensor.get("top_vals", [])) or []
        top_dims: list[int] = []
        top_vals: list[float] = []
        for item in list(top_dims_raw)[:8]:
            try:
                top_dims.append(int(item))
            except (TypeError, ValueError):
                continue
        for item in list(top_vals_raw)[:8]:
            try:
                top_vals.append(float(item))
            except (TypeError, ValueError):
                continue

        samples = int(self._baseline.get("samples", 0) or 0)
        norm_mean = float(self._baseline.get("norm_mean", norm) or norm)
        mean_mean = float(self._baseline.get("tensor_mean", tensor_mean) or tensor_mean)
        std_mean = float(self._baseline.get("tensor_std", tensor_std) or tensor_std)
        top_dim_counts = dict(self._baseline.get("top_dim_counts", {}) or {})
        baseline_top = [
            int(key)
            for key, _count in sorted(top_dim_counts.items(), key=lambda item: item[1], reverse=True)[:8]
            if str(key).lstrip("-").isdigit()
        ]
        norm_delta = abs(norm - norm_mean) / max(abs(norm_mean), 1.0)
        mean_delta = abs(tensor_mean - mean_mean) / max(abs(mean_mean), 1.0)
        std_delta = abs(tensor_std - std_mean) / max(abs(std_mean), 0.1, 1.0)
        overlap_union = len(set(top_dims) | set(baseline_top)) or 1
        top_overlap = len(set(top_dims) & set(baseline_top)) / overlap_union
        drift = _clamp01((norm_delta * 0.45) + (mean_delta * 0.15) + (std_delta * 0.15) + ((1.0 - top_overlap) * 0.25))
        stability = round(1.0 - drift, 4)
        anomaly = round(drift if drift >= self._drift_threshold else drift * 0.5, 4)

        cpp_consistency: float | None
        cpp_reason = "cpp_unavailable"
        if isinstance(cpp_projection, dict) and cpp_projection:
            cpp_norm = float(cpp_projection.get("norm", norm) or norm)
            cpp_top = [int(item) for item in cpp_projection.get("top_dims", [])[:8] if str(item).lstrip("-").isdigit()]
            cpp_overlap_union = len(set(top_dims) | set(cpp_top)) or 1
            cpp_overlap = len(set(top_dims) & set(cpp_top)) / cpp_overlap_union
            cpp_diff = abs(norm - cpp_norm) / max(abs(norm), abs(cpp_norm), 1.0)
            cpp_consistency = round(1.0 - _clamp01((cpp_diff * 0.7) + ((1.0 - cpp_overlap) * 0.3)), 4)
            cpp_reason = "cpp_projection_compared"
        elif (snapshot.get("cpp_bridge_status") or {}).get("smoke_ok"):
            cpp_consistency = 0.6
            cpp_reason = "cpp_smoke_ok_projection_unavailable"
        else:
            cpp_consistency = None

        if samples == 0:
            mode = "unknown"
            reason = "vector_baseline_warming_up"
        elif anomaly >= self._drift_threshold:
            mode = "anomaly"
            reason = "vector_anomaly_above_threshold"
        elif drift >= max(0.05, self._drift_threshold * 0.6):
            mode = "drift"
            reason = "vector_drift_detected"
        else:
            mode = "stable"
            reason = "vector_within_baseline"

        updated_samples = samples + 1
        self._baseline["samples"] = updated_samples
        self._baseline["norm_mean"] = ((norm_mean * samples) + norm) / max(1, updated_samples)
        self._baseline["tensor_mean"] = ((mean_mean * samples) + tensor_mean) / max(1, updated_samples)
        self._baseline["tensor_std"] = ((std_mean * samples) + tensor_std) / max(1, updated_samples)
        for dim in top_dims:
            top_dim_counts[str(dim)] = int(top_dim_counts.get(str(dim), 0)) + 1
        self._baseline["top_dim_counts"] = top_dim_counts
        self._baseline["last_vector"] = {
            "norm": norm,
            "tensor_mean": tensor_mean,
            "tensor_std": tensor_std,
            "top_dims": top_dims,
            "top_vals": [round(value, 6) for value in top_vals],
            "cpp_reason": cpp_reason,
        }
        _save_json(self._path, self._baseline)

        return {
            "vector_stability": stability,
            "vector_drift": round(drift, 4),
            "vector_anomaly": anomaly,
            "cpp_consistency": cpp_consistency,
            "mode_contribution": mode,
            "reason": reason,
            "baseline_ready": updated_samples >= self._baseline_min_samples,
        }

    def baseline_summary(self) -> dict[str, Any]:
        baseline = dict(self._baseline)
        top_dim_counts = baseline.get("top_dim_counts", {}) or {}
        baseline["dominant_dims"] = [
            key for key, _count in sorted(top_dim_counts.items(), key=lambda item: item[1], reverse=True)[:8]
        ]
        return baseline

