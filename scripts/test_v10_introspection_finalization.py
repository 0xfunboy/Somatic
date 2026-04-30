#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.answering import AnswerFinalizer
from soma_core.introspection import IntrospectionRouter
from soma_core.output_filter import OutputFilter
from soma_core.relevance import RelevanceFilter


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    failures = 0
    snapshot = {
        "derived": {"thermal_stress": 0.1, "energy_stress": 0.1, "instability": 0.1},
        "system": {"cpu_temp": 36.0, "disk_temp": 33.0, "memory_percent": 41.0, "disk_used_percent": 50.0},
        "provider": {"source_quality": 1.0},
    }
    finalizer = AnswerFinalizer(OutputFilter(RelevanceFilter()))

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mind = root / "data" / "mind"
        write_json(
            mind / "internal_loop_state.json",
            {
                "last_prompt_preview": "prompt preview",
                "last_prompt_path": "/tmp/prompt.gz",
                "last_parsed": {"goal": "observe", "mode": "observe", "action_type": "observe"},
                "last_parsed_fallback": {},
                "last_evidence": {"reason": "fresh evidence"},
            },
        )
        write_json(
            mind / "metabolic_state.json",
            {
                "mode": "recover",
                "stability": 0.4,
                "stress": 0.8,
                "growth_allowed": False,
                "recovery_required": True,
                "reasons": ["host_pressure"],
                "raw_source_quality": 0.33,
                "sensor_confidence_calibrated": 0.71,
                "baseline_confidence": 0.92,
                "missing_sensor_classes": ["gpu"],
            },
        )
        router = IntrospectionRouter(repo_root=root)
        skill = router.execute("show your last internal DeepSeek JSON")
        text = finalizer.finalize("show your last internal DeepSeek JSON", snapshot, skill_result=skill)
        failures += check("json answer stays json", text.strip().startswith("{") and '"action_type": "observe"' in text, text)
        failures += check("json answer has no telemetry filler", "temperature" not in text.lower() and "voltage" not in text.lower(), text)

        skill = router.execute("what is your metabolic vector?")
        text = finalizer.finalize("what is your metabolic vector?", snapshot, skill_result=skill)
        failures += check("metabolic vector stays json", text.strip().startswith("{") and '"mode": "recover"' in text, text)

    with tempfile.TemporaryDirectory() as td:
        router = IntrospectionRouter(repo_root=Path(td))
        skill = router.execute("show your last internal DeepSeek JSON")
        text = finalizer.finalize("show your last internal DeepSeek JSON", snapshot, skill_result=skill)
        failures += check("missing state answer is honest", "persisted yet" in text.lower(), text)
    return failures


if __name__ == "__main__":
    sys.exit(main())
