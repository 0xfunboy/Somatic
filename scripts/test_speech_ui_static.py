#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
HTML = (ROOT / "docs" / "simulator.html").read_text(encoding="utf-8")


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    failures += check("speakSoma exists", "function speakSoma(text, kind)" in HTML)
    failures += check("speech disabled by default", "localFlag('soma_speak_internal', false)" in HTML)
    failures += check("speak toggle exists", 'id="toggle-speak"' in HTML and "toggleSpeakInternal()" in HTML)
    failures += check("localStorage toggles exist", "soma_show_internal" in HTML and "soma_show_raw" in HTML and "soma_speak_internal" in HTML)
    failures += check("speech queue cap exists", "const SPEAK_MAX_QUEUE = 5;" in HTML and "speechSynthesis.cancel()" in HTML)
    failures += check("internal events build speech summaries", "speakText =" in HTML and "appendInnerRadioEvent(event)" in HTML)
    return failures


if __name__ == "__main__":
    sys.exit(main())
