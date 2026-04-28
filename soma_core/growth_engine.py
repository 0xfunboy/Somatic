from __future__ import annotations

import time
from typing import Any

from soma_core.config import CFG


_STAGES = [
    "reflex_shell",
    "sensed_body",
    "stable_body_baseline",
    "verified_command_agency",
    "autobiographical_continuity",
    "autonomous_bios_loop",
    "metabolic_growth_ready",
    "mutation_sandbox_ready",
    "self_improving_candidate",
    "cpp_embodied_runtime_ready",
    "migration_ready",
]


class GrowthEngine:
    def evaluate(self, snapshot: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        evidence = {
            "frontend_connected": bool(context.get("frontend_connected", True)),
            "provider_real": bool(snapshot.get("provider", {}).get("is_real", False)),
            "provider_name": snapshot.get("provider", {}).get("name", "unknown"),
            "source_quality": float(snapshot.get("provider", {}).get("source_quality") or 0.0),
            "sensor_confidence_calibrated": float((context.get("metabolic") or {}).get("sensor_confidence_calibrated", 0.0) or 0.0),
            "baseline_confidence": float((context.get("metabolic") or {}).get("baseline_confidence", 0.0) or 0.0),
            "sample_minutes": float(context.get("sample_minutes", 0.0)),
            "baselines": context.get("baselines", {}),
            "command_agency": context.get("command_agency", {}),
            "autobiography": context.get("autobiography", {}),
            "bios": context.get("bios", {}),
            "mutation": context.get("mutation", {}),
            "cpp_bridge": context.get("cpp_bridge", {}),
            "metabolic": context.get("metabolic", {}),
            "reward": context.get("reward", {}),
            "vector_state": context.get("vector_state", {}),
            "internal_loop": context.get("internal_loop", {}),
        }
        stage_details = [
            self._reflex_shell(evidence),
            self._sensed_body(evidence),
            self._stable_body_baseline(evidence),
            self._verified_command_agency(evidence),
            self._autobiographical_continuity(evidence),
            self._autonomous_bios_loop(evidence),
            self._metabolic_growth_ready(evidence),
            self._mutation_sandbox_ready(evidence),
            self._self_improving_candidate(evidence),
            self._cpp_embodied_runtime_ready(evidence),
            self._migration_ready(evidence),
        ]
        current = stage_details[-1]
        for detail in stage_details:
            if not detail["done"]:
                current = detail
                break
        completed = sum(1 for detail in stage_details if detail["done"])
        score = round(completed / max(1, len(stage_details)), 4)
        metabolic = evidence.get("metabolic", {})
        metabolic_mode = str(metabolic.get("mode") or "observe")
        growth_allowed = bool(metabolic.get("growth_allowed", False))
        recovery_required = bool(metabolic.get("recovery_required", False))
        blocked_by = list(current["blocked_by"])
        if recovery_required:
            for reason in metabolic.get("reasons", []) or ["recovery_required"]:
                if reason not in blocked_by:
                    blocked_by.append(reason)
        next_step = current["next_step"]
        internal_loop = evidence.get("internal_loop", {})
        if recovery_required:
            next_step = "Growth paused. Stay in recovery mode until stress and vector anomaly subside."
        elif growth_allowed and metabolic_mode in {"grow", "mutate", "evaluate", "reproduce"} and not internal_loop.get("last_run_at"):
            next_step = "Metabolism is stable. Run the internal growth planner to produce evidence."
        elif growth_allowed and metabolic_mode == "observe":
            next_step = "Metabolism is stable but no growth action happened recently. Trigger an internal growth cycle."
        return {
            "stage": current["stage"],
            "score": score,
            "growth_score": score,
            "metabolic_mode": metabolic_mode,
            "growth_allowed": growth_allowed,
            "recovery_required": recovery_required,
            "completed_requirements": current["completed"],
            "missing_requirements": current["missing"],
            "blocked_by": blocked_by,
            "evidence": evidence,
            "next_step": next_step,
            "last_internal_decision": str(internal_loop.get("last_prompt_type") or internal_loop.get("last_decision_id") or ""),
            "last_evaluated_at": time.time(),
        }

    def _reflex_shell(self, evidence: dict[str, Any]) -> dict[str, Any]:
        reqs = {
            "server_boots": True,
            "frontend_receives_payload": bool(evidence.get("frontend_connected", True)),
        }
        return self._pack("reflex_shell", reqs, next_step="Continue acquiring sensor evidence.")

    def _sensed_body(self, evidence: dict[str, Any]) -> dict[str, Any]:
        source_quality = float(evidence.get("source_quality", 0.0))
        reqs = {
            "sensor_provider_active": bool(evidence.get("provider_name")),
            "sample_evidence_5_minutes": float(evidence.get("sample_minutes", 0.0)) >= 5.0,
            "source_quality_known": source_quality >= 0.0,
        }
        blocked = [] if evidence.get("provider_real") or evidence.get("provider_name") == "mock" else ["sensor provider unavailable"]
        return self._pack("sensed_body", reqs, blocked_by=blocked, next_step="Collect at least 5 minutes of body samples.")

    def _stable_body_baseline(self, evidence: dict[str, Any]) -> dict[str, Any]:
        baselines = evidence.get("baselines", {}).get("keys", {})
        cpu = baselines.get("idle_cpu_percent", {})
        cpu_temp = baselines.get("cpu_temp_c", {})
        disk_temp = baselines.get("disk_temp_c", {})
        reqs = {
            "idle_cpu_baseline_exists": bool(cpu),
            "cpu_temp_baseline_exists_if_available": (not evidence.get("provider_real")) or bool(cpu_temp) or snapshot_missing_allowed(evidence, "cpu_temp_c"),
            "disk_temp_baseline_exists_if_available": (not evidence.get("provider_real")) or bool(disk_temp) or snapshot_missing_allowed(evidence, "disk_temp_c"),
            "baseline_confidence_ge_0_65": max(
                float(cpu.get("confidence", 0.0)),
                float(cpu_temp.get("confidence", 0.0)),
                float(disk_temp.get("confidence", 0.0)),
            ) >= 0.65,
            "three_windows_or_persisted": max(
                int(cpu.get("windows", 0)),
                int(cpu_temp.get("windows", 0)),
                int(disk_temp.get("windows", 0)),
            ) >= 3 or bool(cpu.get("samples", 0)),
        }
        return self._pack(
            "stable_body_baseline",
            reqs,
            next_step="Update body baselines until confidence crosses 0.65.",
        )

    def _verified_command_agency(self, evidence: dict[str, Any]) -> dict[str, Any]:
        agency = evidence.get("command_agency", {})
        categories = agency.get("categories", [])
        reqs = {
            "five_successful_executions": int(agency.get("successful", 0)) >= 5,
            "three_categories": len(categories) >= 3,
            "regression_proves_command_result_wins": bool(agency.get("regression_ok", False)),
        }
        return self._pack(
            "verified_command_agency",
            reqs,
            next_step="Run more successful commands or skills across system, network, repo, and memory.",
        )

    def _autobiographical_continuity(self, evidence: dict[str, Any]) -> dict[str, Any]:
        autobio = evidence.get("autobiography", {})
        total = max(1, int(autobio.get("total_reflections", 0)))
        empty = int(autobio.get("empty_reflections", 0))
        reqs = {
            "five_meaningful_lessons": int(autobio.get("lessons_count", 0)) >= 5,
            "two_operator_preferences": int(autobio.get("operator_lessons_count", 0)) >= 2,
            "one_limitation_lesson": int(autobio.get("limitation_lessons_count", 0)) >= 1,
            "one_nightly_reflection": bool(autobio.get("last_nightly_reflection")),
            "empty_ratio_below_0_7": (empty / total) < 0.7,
        }
        return self._pack(
            "autobiographical_continuity",
            reqs,
            next_step="Distill real lessons and operator corrections instead of adding empty reflections.",
        )

    def _autonomous_bios_loop(self, evidence: dict[str, Any]) -> dict[str, Any]:
        bios = evidence.get("bios", {})
        reqs = {
            "bios_runs_6_times": int(bios.get("run_count", 0)) >= 6,
            "bios_useful_cycles_3": int(bios.get("useful_cycles", 0)) >= 3,
        }
        return self._pack("autonomous_bios_loop", reqs, next_step="Let BIOS complete more useful cycles.")

    def _metabolic_growth_ready(self, evidence: dict[str, Any]) -> dict[str, Any]:
        metabolic = evidence.get("metabolic", {})
        reward = evidence.get("reward", {})
        reqs = {
            "metabolic_mode_known": bool(metabolic.get("mode")),
            "growth_allowed": bool(metabolic.get("growth_allowed", False)),
            "stable_cycles_ready": int(metabolic.get("stable_cycles", 0)) >= CFG.growth_min_stable_bios_cycles,
            "reward_not_strongly_negative": float(reward.get("rolling_score", 0.0)) >= -0.25,
        }
        blocked = list(metabolic.get("reasons", [])) if not metabolic.get("growth_allowed", False) else []
        return self._pack(
            "metabolic_growth_ready",
            reqs,
            blocked_by=blocked,
            next_step="Hold stability and let the internal growth planner choose an evidence-producing action.",
        )

    def _mutation_sandbox_ready(self, evidence: dict[str, Any]) -> dict[str, Any]:
        mutation = evidence.get("mutation", {})
        reqs = {
            "mutation_root_exists": bool(mutation.get("sandbox_root_exists", False)),
            "one_sandbox_created": int(mutation.get("sandbox_count", 0)) >= 1,
            "noop_test_passes": bool(mutation.get("last_noop_ok", False)),
            "rollback_test_passes": bool(mutation.get("rollback_ok", False)),
        }
        blocked = list(mutation.get("last_blockers", []))
        return self._pack("mutation_sandbox_ready", reqs, blocked_by=blocked, next_step="Create a sandbox and validate no-op mutation flow.")

    def _self_improving_candidate(self, evidence: dict[str, Any]) -> dict[str, Any]:
        mutation = evidence.get("mutation", {})
        reward = evidence.get("reward", {})
        reqs = {
            "real_mutation_proposal": bool(mutation.get("proposal_generated", False)),
            "applied_in_sandbox_only": bool(mutation.get("sandbox_only", False)),
            "tests_pass": bool(mutation.get("last_tests_ok", False)),
            "diff_summary_created": bool(mutation.get("last_diff_summary")),
            "operator_review_report": bool(mutation.get("last_report")),
            "reward_supportive": float(reward.get("rolling_score", 0.0)) >= 0.0,
        }
        return self._pack("self_improving_candidate", reqs, next_step="Generate and evaluate a real sandbox-only mutation proposal.")

    def _cpp_embodied_runtime_ready(self, evidence: dict[str, Any]) -> dict[str, Any]:
        cpp = evidence.get("cpp_bridge", {})
        reqs = {
            "binary_exists_or_status_known": bool(cpp.get("binary_exists", False)) or cpp.get("status") in {"missing", "failed", "model_required"},
            "smoke_passes_or_failure_recorded": bool(cpp.get("smoke_ok", False)) or bool(cpp.get("last_error")),
            "bridge_status_exposed": bool(cpp),
        }
        return self._pack("cpp_embodied_runtime_ready", reqs, next_step="Refresh C++ bridge detection and smoke status.")

    def _migration_ready(self, evidence: dict[str, Any]) -> dict[str, Any]:
        mutation = evidence.get("mutation", {})
        reqs = {
            "mutant_passes_full_validation": bool(mutation.get("full_validation_ok", False)),
            "improvement_report_beneficial": mutation.get("recommendation") == "candidate_for_migration",
            "operator_approval_required": bool(mutation.get("operator_approval_required", True)),
        }
        return self._pack("migration_ready", reqs, next_step="Await explicit operator approval after a beneficial mutant validation.")

    def _pack(
        self,
        stage: str,
        requirements: dict[str, bool],
        *,
        blocked_by: list[str] | None = None,
        next_step: str = "",
    ) -> dict[str, Any]:
        completed = [name for name, ok in requirements.items() if ok]
        missing = [name for name, ok in requirements.items() if not ok]
        return {
            "stage": stage,
            "done": not missing,
            "completed": completed,
            "missing": missing,
            "blocked_by": blocked_by or [],
            "next_step": next_step if missing else "Maintain evidence and continue validation.",
        }


def snapshot_missing_allowed(evidence: dict[str, Any], _key: str) -> bool:
    return evidence.get("provider_name") == "mock"
