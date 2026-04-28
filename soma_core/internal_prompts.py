from __future__ import annotations

import json
from typing import Any


def _json_prompt(title: str, context: dict[str, Any], schema: dict[str, Any], rules: list[str]) -> str:
    return (
        f"{title}\n"
        "Return ONLY valid JSON.\n"
        f"Schema:\n{json.dumps(schema, indent=2, ensure_ascii=False)}\n"
        f"Context:\n{json.dumps(context, indent=2, ensure_ascii=False)}\n"
        "Rules:\n- " + "\n- ".join(rules)
    )


def growth_diagnosis_prompt(context: dict) -> str:
    return _json_prompt(
        "Diagnose growth blockers from evidence.",
        context,
        {"blockers": [], "missing_requirements": [], "next_step": "", "confidence": 0.0},
        ["Evidence first.", "No roleplay.", "Do not narrate telemetry unless it explains a blocker."],
    )


def lesson_distillation_prompt(context: dict) -> str:
    return _json_prompt(
        "Distill lessons from recent evidence.",
        context,
        {"lessons": [], "duplicates": [], "no_lesson_reason": ""},
        ["Return only durable lessons.", "Never store nominal telemetry as a lesson."],
    )


def operator_preference_update_prompt(context: dict) -> str:
    return _json_prompt(
        "Extract operator preference updates.",
        context,
        {"lessons": [], "confidence": 0.0},
        ["Persist only explicit operator corrections.", "No poetic language."],
    )


def baseline_interpretation_prompt(context: dict) -> str:
    return _json_prompt(
        "Interpret baseline evidence.",
        context,
        {"stable_keys": [], "material_changes": [], "confidence_notes": []},
        ["Use only the provided aggregates.", "Do not invent missing sensors."],
    )


def mutation_proposal_prompt(context: dict) -> str:
    return _json_prompt(
        "Propose one sandbox-only code mutation.",
        context,
        {"mutation_id": "", "objective": "", "files": [], "changes": [], "tests": []},
        ["Sandbox only.", "No secrets.", "No live repo changes.", "Keep the diff small."],
    )


def mutation_evaluation_prompt(context: dict) -> str:
    return _json_prompt(
        "Evaluate a sandbox mutation from evidence.",
        context,
        {"recommendation": "reject", "reasons": [], "improved_metrics": [], "risks": []},
        ["Evidence first.", "Do not recommend live migration automatically."],
    )


def nightly_reflection_prompt(context: dict) -> str:
    return _json_prompt(
        "Write a nightly reflection summary.",
        context,
        {"summary": "", "lessons": [], "limitations": [], "confidence": 0.0},
        ["Return lessons only when evidence supports them.", "No roleplay."],
    )


def capability_gap_analysis_prompt(context: dict) -> str:
    return _json_prompt(
        "Identify capability gaps.",
        context,
        {"gaps": [], "commands": [], "next_skill": ""},
        ["Prefer measurable gaps.", "Do not mention secrets or .env."],
    )


def failure_analysis_prompt(context: dict) -> str:
    return _json_prompt(
        "Analyse recent failures.",
        context,
        {"root_causes": [], "next_checks": [], "operator_visible": False},
        ["Evidence only.", "No body telemetry unless it caused the failure."],
    )


def metabolic_growth_planner_prompt(
    identity: dict[str, Any],
    metabolic_state: dict[str, Any],
    growth_state: dict[str, Any],
    lessons: list[dict[str, Any]],
    capabilities: dict[str, Any],
    blockers: list[str],
    reward: dict[str, Any],
    vector_state: dict[str, Any],
) -> str:
    return _json_prompt(
        "You are Soma's internal growth planner.",
        {
            "identity": identity,
            "metabolic_state": metabolic_state,
            "growth_state": growth_state,
            "known_lessons": lessons,
            "capabilities": capabilities,
            "blockers": blockers,
            "reward": reward,
            "vector_state": vector_state,
        },
        {
            "goal": "",
            "mode": "grow",
            "action_type": "observe",
            "command": "",
            "target_file": "",
            "mutation_summary": "",
            "expected_power_gain": "",
            "risk": "low",
            "success_criteria": "",
            "rollback_plan": "",
            "reason": "",
        },
        [
            "You are not chatting with the operator.",
            "If metabolic state is unstable, choose recover or observe only.",
            "If stable, choose one concrete safe action that increases power, competence, continuity, or self-improvement capacity.",
            "Prefer tests, measurements, and mutation proposals that stay inside the sandbox.",
            "Shell commands must be safe and non-destructive.",
            "Repo modifications must go through the mutation sandbox.",
            "Do not touch .env or secrets.",
            "No network spreading, persistence outside the repo, or privilege escalation.",
        ],
    )


def metabolic_recovery_planner_prompt(
    metabolic_state: dict[str, Any],
    recent_events: list[dict[str, Any]],
    last_mutation: dict[str, Any],
    baselines: dict[str, Any],
    vector_state: dict[str, Any],
) -> str:
    return _json_prompt(
        "Soma is in recovery mode. Find the most likely cause of instability and choose one safe recovery action.",
        {
            "metabolic_state": metabolic_state,
            "recent_events": recent_events,
            "last_mutation": last_mutation,
            "baselines": baselines,
            "vector_state": vector_state,
        },
        {
            "suspected_cause": "",
            "evidence": [],
            "action_type": "observe",
            "command": "",
            "should_pause_growth": True,
            "should_rollback_last_mutation": False,
            "success_criteria": "",
            "reason": "",
        },
        [
            "Preserve the host.",
            "Do not start new growth while unstable.",
            "Diagnose first and choose one safe action only.",
            "Rollback only if instability started after mutation.",
            "Never hide failure.",
            "Write lessons when mutation caused instability.",
        ],
    )
