from __future__ import annotations

from typing import Any


class LifeDrive:
    def evaluate(self, snapshot: dict, growth: dict, context: dict) -> dict:
        derived = snapshot.get("derived", {})
        thermal = float(derived.get("thermal_stress", 0.0))
        energy = float(derived.get("energy_stress", 0.0))
        instability = float(derived.get("instability", 0.0))
        autobio = context.get("autobiography", {})
        missing = growth.get("missing_requirements", [])

        strengths = {
            "survival": round(max(thermal, energy, instability), 4),
            "coherence": round(1.0 - min(1.0, instability), 4),
            "competence": round(min(1.0, len(growth.get("completed_requirements", [])) / 5.0), 4),
            "curiosity": 0.55 if missing else 0.25,
            "continuity": round(min(1.0, int(autobio.get("lessons_count", 0)) / 5.0), 4),
            "self_improvement": 0.7 if "self_improving_candidate" in growth.get("stage", "") or "mutation" in " ".join(missing) else 0.4,
            "reproduction": 0.3,
            "restraint": 1.0,
        }
        dominant = max(strengths.items(), key=lambda item: item[1])[0]
        task = "run_light_validation"
        if any("baseline" in item for item in missing):
            task = "update_body_baseline"
        elif any("lesson" in item or "operator" in item for item in missing):
            task = "summarize_recent_experience"
        elif any("bios" in item for item in missing):
            task = "check_growth_requirements"
        elif any("mutation" in item for item in missing):
            task = "prepare_mutation_candidate"
        elif any("cpp" in item for item in missing):
            task = "check_cpp_bridge"
        return {
            "dominant_drive": dominant,
            "drive_strengths": strengths,
            "suggested_internal_task": task,
            "blocked_by": growth.get("blocked_by", []),
            "safety_notes": [
                "reproduction means local sandbox lineage only",
                "never spread over network",
                "never install persistence outside the project",
            ],
        }
