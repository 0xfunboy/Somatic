#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).parent.parent
HTML = ROOT / "docs" / "simulator.html"


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    text = HTML.read_text(encoding="utf-8")
    failures = 0

    failures += check("applyLightTick exists", "function applyLightTick(msg)" in text)
    failures += check("assignDefined exists", "function assignDefined(target, source, keys)" in text)
    failures += check("deepMerge exists", "function deepMerge(target, source)" in text)
    failures += check("full snapshot cache exists", "window._LAST_FULL_SNAPSHOT" in text)

    truthful = re.search(r"function updateTruthfulStatusBar\(msg\)\s*\{(.*?)\n\}", text, re.S)
    failures += check(
        "updateTruthfulStatusBar uses full cache",
        truthful is not None and "_LAST_FULL_SNAPSHOT" in truthful.group(1),
    )

    tick_light_branch = re.search(r"else if \(msg\.type === 'tick_light'\) \{(.*?)\n  \} else if", text, re.S)
    branch_text = tick_light_branch.group(1) if tick_light_branch else ""
    failures += check(
        "tick_light path does not call full applySnapshot directly",
        "applyLightTick(msg);" in branch_text and "applySnapshot(msg)" not in branch_text,
        branch_text.strip()[:300],
    )

    failures += check(
        "tick_light path stores last light tick",
        "window._LAST_LIGHT_TICK = msg;" in branch_text,
        branch_text.strip()[:300],
    )

    failures += check(
        "no nullable direct sensor overwrite remains",
        not re.search(r"S\.(?:current_ma|voltage|temp_si|temp_ml|temp_mr|ax|ay|az|gx|gy|gz)\s*=\s*sv\.", text),
    )
    return failures


if __name__ == "__main__":
    sys.exit(main())
