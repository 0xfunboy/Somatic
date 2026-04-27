#!/usr/bin/env python3
"""
scripts/test_command_planner.py — Regression tests for JSON command planner.

Tests _parse_planner_json() routing heuristics without calling a real LLM.
Runs standalone: python3 scripts/test_command_planner.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Inline copy of _parse_planner_json from server.py (pure function, no deps)
# ---------------------------------------------------------------------------

def _parse_planner_json(text: str) -> dict[str, Any]:
    """4-level fallback JSON extractor."""
    text = text.strip()

    # 1. Direct parse
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        pass

    # 2. First {...} block (greedy, handles prose around JSON)
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if m:
        try:
            obj = json.loads(m.group())
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 3. Fenced code block
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL | re.IGNORECASE)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

    # 4. Last resort: treat first non-empty line as raw command
    first_line = next((l.strip() for l in text.splitlines() if l.strip()), "")
    return {
        "use_shell": bool(first_line and not first_line.lower().startswith(("no", "none", "i ", "the "))),
        "command": first_line,
        "reason": "planner parse failed — raw fallback",
        "expected_effect": "",
        "risk_level": "unknown",
    }


# ---------------------------------------------------------------------------
# Simulated planner responses keyed to user requests
# ---------------------------------------------------------------------------

_PLANNER_RESPONSES: dict[str, str] = {
    "su che versione di python stai girando?": json.dumps({
        "use_shell": True,
        "command": "python3 --version",
        "reason": "Query Python interpreter version",
        "expected_effect": "prints Python version string",
        "risk_level": "low",
    }),
    "che versione di node hai?": json.dumps({
        "use_shell": True,
        "command": "node --version",
        "reason": "Query Node.js version",
        "expected_effect": "prints vXX.X.X",
        "risk_level": "low",
    }),
    "quanto spazio libero hai?": json.dumps({
        "use_shell": True,
        "command": "df -h /home/funboy",
        "reason": "Check free disk space",
        "expected_effect": "shows filesystem usage",
        "risk_level": "low",
    }),
    "quanta ram libera hai?": json.dumps({
        "use_shell": True,
        "command": "free -h",
        "reason": "Query available RAM",
        "expected_effect": "shows memory usage in human-readable form",
        "risk_level": "low",
    }),
    "che kernel stai usando?": json.dumps({
        "use_shell": True,
        "command": "uname -r",
        "reason": "Query Linux kernel version",
        "expected_effect": "prints kernel release string",
        "risk_level": "low",
    }),
    "fammi uno speed test reale": json.dumps({
        "use_shell": True,
        "command": (
            "curl -s -o /dev/null -w '%{speed_download}' --max-time 15 "
            "https://speed.cloudflare.com/__down?bytes=20000000 "
            "| python3 -c \"import sys; v=float(sys.stdin.read().strip() or 0); print(f'{v/131072:.2f} Mbps')\""
        ),
        "reason": "Measure real download speed via Cloudflare",
        "expected_effect": "outputs Mbps value",
        "risk_level": "low",
    }),
}

# ---------------------------------------------------------------------------
# Per-test assertions: (substring_expected_in_command, use_shell_must_be)
# ---------------------------------------------------------------------------

_ASSERTIONS: dict[str, tuple[str, bool]] = {
    "su che versione di python stai girando?": ("python3", True),
    "che versione di node hai?":               ("node", True),
    "quanto spazio libero hai?":               ("df", True),
    "quanta ram libera hai?":                  ("free", True),
    "che kernel stai usando?":                 ("uname", True),
    "fammi uno speed test reale":              ("curl", True),
}

# ---------------------------------------------------------------------------
# Additional parsing-edge-case tests
# ---------------------------------------------------------------------------

_PARSE_CASES: list[tuple[str, dict[str, Any]]] = [
    # Valid JSON blob
    (
        '{"use_shell": false, "command": "", "reason": "chitchat"}',
        {"use_shell": False, "command": "", "reason": "chitchat"},
    ),
    # Prose wrapping JSON
    (
        'Sure, here is the JSON:\n{"use_shell": true, "command": "ls -la", "reason": "list"}\nHope that helps!',
        {"use_shell": True, "command": "ls -la"},
    ),
    # Fenced code block
    (
        "```json\n{\"use_shell\": true, \"command\": \"pwd\", \"reason\": \"cwd\"}\n```",
        {"use_shell": True, "command": "pwd"},
    ),
    # Fallback raw line
    (
        "uname -a",
        {"command": "uname -a"},
    ),
    # NONE / no-shell
    (
        '{"use_shell": false, "command": "", "reason": "no shell needed"}',
        {"use_shell": False},
    ),
]

# ---------------------------------------------------------------------------
# Test runner
# ---------------------------------------------------------------------------

def run_tests() -> int:
    failures = 0
    total = 0

    print("=== Command planner JSON parsing tests ===\n")

    for user_text, (expected_substring, expected_use_shell) in _ASSERTIONS.items():
        total += 1
        raw = _PLANNER_RESPONSES[user_text]
        result = _parse_planner_json(raw)

        ok = True
        if result.get("use_shell") != expected_use_shell:
            print(f"FAIL [{user_text!r}]: use_shell={result.get('use_shell')!r}, want {expected_use_shell!r}")
            ok = False
        if expected_substring not in result.get("command", ""):
            print(f"FAIL [{user_text!r}]: command={result.get('command')!r} missing {expected_substring!r}")
            ok = False
        if ok:
            print(f"PASS [{user_text!r}] → command={result['command']!r}")

    print()
    print("=== JSON parsing edge cases ===\n")

    for raw, expected_subset in _PARSE_CASES:
        total += 1
        result = _parse_planner_json(raw)
        ok = True
        for k, v in expected_subset.items():
            if result.get(k) != v:
                print(f"FAIL [edge case]: key={k!r} got {result.get(k)!r}, want {v!r}")
                print(f"  input: {raw[:80]!r}")
                ok = False
                failures += 1
        if ok:
            print(f"PASS [edge case]: {raw[:60]!r}")

    # Count failures from routing tests
    for user_text, (expected_substring, expected_use_shell) in _ASSERTIONS.items():
        raw = _PLANNER_RESPONSES[user_text]
        result = _parse_planner_json(raw)
        if result.get("use_shell") != expected_use_shell or expected_substring not in result.get("command", ""):
            failures += 1

    print(f"\n{total} tests, {failures} failures")
    return failures


if __name__ == "__main__":
    sys.exit(run_tests())
