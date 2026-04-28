#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import soma_core.memory as memory_mod
from soma_core.memory import SomaMemory
from soma_core.reflection import ReflectionEngine


class DummyGoals:
    def add_evidence(self, *_args, **_kwargs):
        return None


class DummyBaselines:
    def summary(self):
        return {"keys": {}}


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def patch_memory_paths(root: Path) -> None:
    memory_mod._MIND_DIR = root
    memory_mod._SELF_MODEL_FILE = root / "self_model.json"
    memory_mod._PREFERENCES_FILE = root / "preferences.json"
    memory_mod._SKILLS_FILE = root / "skills.json"
    memory_mod._REFLECTIONS_FILE = root / "reflections.jsonl"
    memory_mod._DATA_DIR = root.parent
    memory_mod._EPISODIC_FILE = root.parent / "memory" / "episodic.jsonl"
    memory_mod._SEMANTIC_FILE = root.parent / "memory" / "semantic.json"


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "data" / "mind"
        root.mkdir(parents=True, exist_ok=True)
        patch_memory_paths(root)
        mem = SomaMemory()
        engine = ReflectionEngine(mem, DummyGoals(), baseline_store=DummyBaselines())

        for _ in range(100):
            mem.increment_reflections()
            mem.update_reflection_quality(meaningful=False)
        quality = mem.get_growth().get("reflection_quality", {})
        failures += check("100 empty reflections stay empty", quality.get("meaningful_reflections", 0) == 0 and quality.get("empty_reflections", 0) >= 100, str(quality))

        snapshot = {
            "timestamp": 1.0,
            "scenario": "nominal",
            "system": {"cpu_percent": 5.0, "memory_percent": 40.0, "cpu_temp": 35.0},
            "derived": {"thermal_stress": 0.1, "energy_stress": 0.1, "instability": 0.1},
            "baseline_update": {"stable_now": ["idle_cpu_percent"], "material_changes": [], "summary": {"idle_cpu_percent": {"value": 5.0}}},
        }
        engine._last_reflect_at = 0.0
        entry = engine.maybe_reflect(snapshot)
        quality = mem.get_growth().get("reflection_quality", {})
        failures += check("baseline adds meaningful reflection", bool(entry and entry["meaningful"]) and quality.get("meaningful_reflections", 0) >= 1, str(entry))

        engine._last_reflect_at = 0.0
        entry2 = engine.maybe_reflect(snapshot)
        quality = mem.get_growth().get("reflection_quality", {})
        failures += check("duplicate reflection tracked", bool(entry2 and entry2["duplicate"]) and quality.get("duplicate_reflections", 0) >= 1, str(entry2))
        failures += check("no_lesson_reason present", bool(entry2 and entry2.get("no_lesson_reason")), str(entry2))
    return failures


if __name__ == "__main__":
    sys.exit(main())
