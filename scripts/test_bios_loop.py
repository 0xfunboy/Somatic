#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.bios import BiosLoop
from soma_core.internal_loop import InternalLoop
from soma_core.introspection import IntrospectionRouter
from soma_core.metabolism import MetabolicEngine
from soma_core.power_policy import PowerPolicy
from soma_core.reward import RewardEngine


class DummyExecutor:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def run_raw(self, cmd: str):
        self.commands.append(cmd)
        return True, "ok", ""


class DummyBaselines:
    def update_from_snapshot(self, _snapshot):
        return {"updated_keys": ["idle_cpu_percent"], "stable_now": ["idle_cpu_percent"], "material_changes": [], "summary": {}}

    def summary(self):
        return {"keys": {"idle_cpu_percent": {"confidence": 0.8}}}


class DummyExperience:
    def get_lessons(self, limit=5):
        return [{"id": "x", "behavioral_update": "keep technical answers direct"}][:limit]


class DummyMetabolic:
    def __init__(self, mode: str) -> None:
        self._mode = mode

    def current(self):
        return {
            "mode": self._mode,
            "growth_allowed": self._mode in {"grow", "mutate"},
            "recovery_required": self._mode == "recover",
            "stable_cycles": 5,
            "reasons": [] if self._mode in {"grow", "observe"} else ["stress_above_max"],
        }

    def update(self, _snapshot, _context):
        return self.current()


class DummyInternalLoop:
    def __init__(self) -> None:
        self.called: list[str] = []

    def run_mode_cycle(self, mode, _context):
        self.called.append(mode)
        if mode == "recover":
            return {
                "prompt_type": "recovery_planner",
                "prompt": "recovery prompt",
                "llm_raw": "",
                "parsed": {"action_type": "pause_growth"},
                "parsed_fallback": {},
                "action_taken": {"action_type": "pause_growth", "command": "", "goal": "recover"},
                "evidence": {"ok": True, "reason": "pause growth"},
                "reward": {"kind": "neutral", "value": 0.0},
                "next_task": "recover",
            }
        prompt_type = "stabilization_planner" if mode == "stabilize" else "growth_planner" if mode == "grow" else "observation_planner"
        prompt = "stabilization prompt" if mode == "stabilize" else "growth prompt" if mode == "grow" else "observation prompt"
        return {
            "prompt_type": prompt_type,
            "prompt": prompt,
            "llm_raw": "",
            "parsed": {"action_type": "repo_test" if mode == "grow" else "observe"},
            "parsed_fallback": {},
            "action_taken": {"action_type": "repo_test" if mode == "grow" else "observe", "command": "python3 scripts/test_answer_finalizer.py" if mode == "grow" else "", "goal": "verify"},
            "evidence": {"ok": True, "mode": mode},
            "reward": {"kind": "test_pass" if mode == "grow" else "neutral", "value": 0.15 if mode == "grow" else 0.0},
            "next_task": "evaluate_reward" if mode == "grow" else "observe",
        }

    def status(self):
        return {"last_prompt_type": "growth_planner", "last_run_at": 1.0}


class DummyAutobiography:
    def get_quality_summary(self):
        return {"stage": "meaningful", "lessons_count": 0}

    def write_meaningful_event(self, payload):
        return {"stored": True, "reason": "", "payload": payload}


class DummyPowerPolicy:
    def allowed(self, _decision):
        return True, []


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    snapshot = {"_growth": {"missing_requirements": ["idle_cpu_baseline_exists"], "stage": "stable_body_baseline"}, "derived": {}, "system": {}, "provider": {}}
    with tempfile.TemporaryDirectory() as td:
        exe = DummyExecutor()
        bios = BiosLoop(
            interval_sec=1.0,
            max_tasks_per_hour=1,
            executor=exe,
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("observe"),
            data_root=Path(td),
        )
        result = bios.run_once(snapshot)
        failures += check("observe mode prefers cheap evidence", result["task"]["task"] == "check_runtime_storage", str(result))
        failures += check("writes bios history", (Path(td) / "bios_history.jsonl").exists())
        second = bios.maybe_run(snapshot, last_user_interaction_at=0.0)
        failures += check("respects max tasks per hour", second is None, str(second))
        failures += check("does not write to chat", "chat" not in json.dumps(result))

    with tempfile.TemporaryDirectory() as td:
        exe = DummyExecutor()
        internal = DummyInternalLoop()
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            executor=exe,
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("grow"),
            internal_loop=internal,
            data_root=Path(td),
        )
        result = bios.run_once({"_growth": {"missing_requirements": ["three_categories"], "stage": "verified_command_agency"}, "derived": {}, "system": {}, "provider": {}})
        failures += check("grow mode uses internal loop", internal.called == ["grow"], str(internal.called))
        failures += check("internal evidence captured", result["result"]["evidence"]["ok"] is True, str(result))
        failures += check("bios state stores internal prompt", json.loads((Path(td) / "bios_state.json").read_text(encoding="utf-8")).get("last_internal_prompt") == "growth prompt")

    with tempfile.TemporaryDirectory() as td:
        exe = DummyExecutor()
        internal = DummyInternalLoop()
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            executor=exe,
            baseline_store=DummyBaselines(),
            experience=DummyExperience(),
            metabolic_engine=DummyMetabolic("stabilize"),
            internal_loop=internal,
            data_root=Path(td),
        )
        result = bios.run_once({"_growth": {"missing_requirements": [], "stage": "metabolic_growth_ready"}, "derived": {}, "system": {}, "provider": {}})
        state = json.loads((Path(td) / "bios_state.json").read_text(encoding="utf-8"))
        failures += check("stabilize mode still uses internal loop", internal.called == ["stabilize"], str(internal.called))
        failures += check("stabilize mode stores stabilization prompt", state.get("last_internal_prompt") == "stabilization prompt", str(state))
        failures += check("stabilize result preserves evidence", result["result"]["evidence"].get("mode") == "stabilize", str(result))

    with tempfile.TemporaryDirectory() as td:
        mind_root = Path(td) / "data" / "mind"
        reward = RewardEngine(data_root=mind_root)
        metabolic = MetabolicEngine(data_root=mind_root, window_cycles=20)
        internal = InternalLoop(
            call_llm_raw=None,
            executor=DummyExecutor(),
            reward=reward,
            power_policy=PowerPolicy(),
            mutation=None,
            autobiography=DummyAutobiography(),
            experience=DummyExperience(),
            data_root=mind_root,
        )
        bios = BiosLoop(
            interval_sec=0.0,
            max_tasks_per_hour=5,
            executor=DummyExecutor(),
            baseline_store=DummyBaselines(),
            autobiography=DummyAutobiography(),
            experience=DummyExperience(),
            metabolic_engine=metabolic,
            internal_loop=internal,
            reward_engine=reward,
            data_root=mind_root,
        )
        rich_snapshot = {
            "timestamp": 1.0,
            "provider": {"is_real": True, "name": "linux", "source_quality": 0.33},
            "system": {
                "cpu_percent": 12.0,
                "cpu_count_logical": 8,
                "cpu_freq_mhz": 4100.0,
                "memory_percent": 42.0,
                "memory_total_gb": 31.0,
                "swap_percent": 0.0,
                "disk_used_percent": 41.0,
                "disk_busy_percent": 8.0,
                "disk_total_gb": 950.0,
                "disk_read_mb_s": 1.5,
                "disk_write_mb_s": 0.4,
                "net_up_mbps": 0.2,
                "net_down_mbps": 1.1,
                "cpu_temp": 47.0,
            },
            "derived": {"thermal_stress": 0.12, "energy_stress": 0.08, "instability": 0.05},
            "llm": {"available": False, "mode": "fallback"},
            "vector_state": {"vector_stability": 0.93, "vector_drift": 0.04, "vector_anomaly": 0.02},
            "mutation_status": {"sandbox_root_exists": True, "last_tests_ok": True},
            "cpp_bridge_status": {"enabled": False, "smoke_ok": False},
            "command_agency": {"successful": 6, "failed": 0, "regression_ok": True},
            "baselines": {"keys": {"idle_cpu_percent": {"confidence": 0.8}, "cpu_temp_c": {"confidence": 0.78}, "ram_idle_percent": {"confidence": 0.79}}},
            "_growth": {"missing_requirements": [], "blocked_by": [], "stage": "metabolic_growth_ready"},
        }
        rich_snapshot["metabolic"] = metabolic.update(
            rich_snapshot,
            {
                "growth": rich_snapshot["_growth"],
                "reward": reward.summary(),
                "vector_state": rich_snapshot["vector_state"],
                "mutation": rich_snapshot["mutation_status"],
                "cpp_bridge": rich_snapshot["cpp_bridge_status"],
                "command_agency": rich_snapshot["command_agency"],
                "baselines": rich_snapshot["baselines"],
                "llm_mode": rich_snapshot["llm"]["mode"],
                "llm_available": rich_snapshot["llm"]["available"],
                "capabilities": {"survival_policy": True},
            },
        )
        result = bios.run_once(rich_snapshot)
        router = IntrospectionRouter(repo_root=Path(td))
        internal_state = json.loads((mind_root / "internal_loop_state.json").read_text(encoding="utf-8"))
        bios_state = json.loads((mind_root / "bios_state.json").read_text(encoding="utf-8"))
        failures += check("partial linux telemetry can leave permanent stabilize", rich_snapshot["metabolic"]["mode"] in {"observe", "grow"}, str(rich_snapshot["metabolic"]))
        failures += check("bios live integration writes internal prompt", bool(internal_state.get("last_prompt")), str(internal_state))
        failures += check("bios live integration stores fallback decision", bool(internal_state.get("last_parsed") or internal_state.get("last_parsed_fallback")), str(internal_state))
        failures += check("bios live integration prompt introspection not empty", "No internal BIOS prompt" not in router.execute("show your last BIOS internal prompt")["text"], str(bios_state))
    return failures


if __name__ == "__main__":
    sys.exit(main())
