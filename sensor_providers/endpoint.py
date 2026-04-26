from __future__ import annotations

import json
import urllib.request

from .base import SensorProvider, normalize_snapshot


class EndpointSensorProvider(SensorProvider):
    name = "endpoint"
    is_real = True

    def __init__(self, endpoint: str):
        self.endpoint = (endpoint or "").strip()

    def read(self) -> dict[str, object]:
        if not self.endpoint:
            return normalize_snapshot(
                {
                    "system": {
                        "source_quality": 0.0,
                        "source_quality_label": "endpoint_missing",
                    }
                },
                provider=self.name,
                is_real=False,
            )

        request = urllib.request.Request(
            self.endpoint,
            headers={"Accept": "application/json", "User-Agent": "latent-somatic/endpoint-provider"},
            method="GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=1.5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except Exception:
            payload = {
                "system": {
                    "source_quality": 0.05,
                    "source_quality_label": "endpoint_unreachable",
                }
            }

        if isinstance(payload, dict) and "core" in payload and isinstance(payload["core"], dict):
            payload = {
                "core": dict(payload["core"]),
                "system": payload.get("system") if isinstance(payload.get("system"), dict) else {},
                "raw": payload.get("raw") if isinstance(payload.get("raw"), dict) else {},
                "scenario": payload.get("scenario"),
            }
        elif isinstance(payload, dict) and "sensors" in payload and isinstance(payload["sensors"], dict):
            payload = {
                "core": dict(payload["sensors"]),
                "system": payload.get("system") if isinstance(payload.get("system"), dict) else {},
                "raw": payload.get("raw") if isinstance(payload.get("raw"), dict) else {},
                "scenario": payload.get("scenario"),
            }

        if not isinstance(payload, dict):
            payload = {
                "system": {
                    "source_quality": 0.05,
                    "source_quality_label": "endpoint_invalid",
                }
            }

        system = payload.get("system") if isinstance(payload.get("system"), dict) else {}
        if "source_quality" not in system:
            core = payload.get("core") if isinstance(payload.get("core"), dict) else {}
            present = sum(core.get(field) is not None for field in core)
            system["source_quality"] = min(1.0, 0.2 + (present / 20.0))
            system["source_quality_label"] = "external"
            payload["system"] = system

        return normalize_snapshot(
            payload,
            provider=self.name,
            is_real=bool(self.endpoint),
        )
