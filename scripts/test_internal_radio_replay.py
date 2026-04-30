#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import server  # noqa: E402


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    server.runtime = server.make_runtime_state()
    snapshot = {
        "internal_loop": {
            "last_run_at": 123.0,
            "last_mode": "recover",
            "last_prompt_type": "recovery_planner",
            "last_prompt_preview": "recovery prompt preview",
            "last_prompt_path": "/tmp/recovery.prompt.gz",
            "last_raw_preview": "",
            "last_raw_path": "",
            "last_parsed": {},
            "last_parsed_fallback": {"action_type": "pause_growth", "reason": "fallback recovery"},
            "last_fallback": True,
            "last_action_taken": {"action_type": "pause_growth", "goal": "stabilize metabolism"},
            "last_evidence": {"ok": True, "reason": "metabolic instability"},
            "last_reward_delta": 0.08,
            "last_memory_updates": [{"memory": "stability first"}],
            "last_growth_updates": [{"internal_plan": {"goal": "stabilize metabolism"}}],
            "last_next_task": "recover",
            "last_goal": "stabilize metabolism",
            "last_reason": "fallback recovery",
            "last_resource_mode": "recovery",
            "last_metabolic_mode": "recover",
            "last_decision_id": "replay-1",
        },
        "bios_status": {},
    }

    replay = server._internal_radio_replay_events(snapshot)
    types = [event.get("type") for event in replay]
    failures += check("replay includes prompt event", "inner_prompt" in types, str(replay))
    failures += check("replay includes raw fallback event", "inner_llm_raw" in types, str(replay))
    failures += check("replay includes decision event", "inner_decision" in types, str(replay))
    failures += check("replay includes evidence event", "inner_evidence" in types, str(replay))
    failures += check(
        "replayed raw event marks fallback source",
        any(event.get("type") == "inner_llm_raw" and event.get("source") == "fallback" for event in replay),
        str(replay),
    )

    server._prime_runtime_internal_event_state(snapshot)
    failures += check(
        "runtime v10 state primed from replay",
        float(server.runtime.get("last_internal_event_at", 0.0) or 0.0) == 123.0
        and str(server.runtime.get("last_internal_event_type") or "") == "inner_evidence",
        str(server.runtime),
    )
    return failures


if __name__ == "__main__":
    sys.exit(main())
