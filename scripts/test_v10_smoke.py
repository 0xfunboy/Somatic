#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    run_text = (ROOT / "scripts" / "run.sh").read_text(encoding="utf-8")
    ui_text = (ROOT / "docs" / "simulator.html").read_text(encoding="utf-8")
    server_text = (ROOT / "server.py").read_text(encoding="utf-8")
    compact_text = (ROOT / "scripts" / "compact_mind_state.py").read_text(encoding="utf-8")

    failures += check("env includes V10 internal radio defaults", "SOMA_V10_INTERNAL_RADIO=1" in env_text and "SOMA_UI_SPEAK_INTERNAL_DEFAULT=0" in env_text)
    failures += check("run.sh keeps safe and low-power modes", "--safe" in run_text and "--low-power" in run_text and "SOMA_V10_INTERNAL_RADIO" in run_text)
    failures += check("simulator has V10 panel", "V10 Status" in ui_text and 'id="v10-merge"' in ui_text)
    failures += check("simulator has speech toggle", 'id="toggle-speak"' in ui_text and "function speakSoma(text, kind)" in ui_text)
    failures += check("server can emit internal events", "broadcast_pending_runtime_events" in server_text and "_queue_runtime_event" in server_text and "pending_ws_events" in server_text)
    failures += check("state compaction script still available", "internal_prompt_index.jsonl" in compact_text)
    return failures


if __name__ == "__main__":
    sys.exit(main())
