from __future__ import annotations

import re
from typing import Any


def _contains(text: str, *patterns: str) -> bool:
    low = text.lower()
    return any(pattern in low for pattern in patterns)


def deterministic_shortcut(user_text: str) -> dict[str, Any] | None:
    low = (user_text or "").lower()
    if _contains(low, "python version", "versione di python", "su che versione di python"):
        return _ok("python3 --version", "Python version is a deterministic runtime fact.")
    if _contains(low, "node version", "versione di node", "che versione di node"):
        return _ok("node --version", "Node.js version is a deterministic runtime fact.")
    if _contains(low, "kernel", "uname", "che kernel stai usando"):
        return _ok("uname -r", "Kernel version is a deterministic runtime fact.")
    if _contains(low, "public ip", "ip pubblico", "external ip"):
        return _ok("curl -s https://ifconfig.me", "Public IP is measurable from the network edge.")
    if _contains(low, "ram libera", "free ram", "quanta ram", "memory free"):
        return _ok("free -h", "Memory availability is measurable locally.")
    if is_runtime_log_question(low):
        return _ok("python3 scripts/runtime_storage_report.py", "Runtime log size must inspect repo-local storage.")
    if _contains(low, "git status", "stato git", "repo status"):
        return _ok("git status --short", "Repository state is measurable locally.")
    if _contains(low, "x11", "wayland", "desktop", "grafico"):
        return _ok(
            "pgrep -a 'Xorg|wayland|mutter|kwin|gnome-shell|lightdm|sddm' || echo 'Nessun processo grafico trovato'",
            "Desktop session state is measurable from local processes.",
        )
    return None


def is_runtime_log_question(user_text: str) -> bool:
    return _contains(
        user_text,
        "your logs", "runtime logs", "i tuoi log", "data/mind", "cognitive trace",
        "actuation history", "journal", "compattazione", "storage report", "dimensione dei tuoi log runtime",
    )


def _ok(command: str, reason: str) -> dict[str, Any]:
    return {
        "use_shell": True,
        "command": command,
        "reason": reason,
        "expected_effect": reason,
        "risk_level": "low",
        "source": "deterministic_shortcut",
    }


def command_category(command: str) -> str:
    low = (command or "").lower()
    if any(tok in low for tok in ("curl", "ping", "ifconfig.me", "http")):
        return "network"
    if any(tok in low for tok in ("git", "runtime_storage_report.py", "data/mind", "journal", "du -sh")):
        return "repo"
    if any(tok in low for tok in ("lesson", "self_model", "growth", "bios")):
        return "memory"
    return "system"


def planner_prompt(user_text: str) -> str:
    return f"""You are the command planner for an autonomous Linux runtime.
Return ONLY valid JSON:
{{
  "use_shell": true,
  "command": "",
  "reason": "",
  "expected_effect": "",
  "risk_level": "low"
}}

Rules:
- use shell for measurable host/runtime facts
- use repo-local paths for Soma runtime logs
- never use /var/log for Soma runtime log questions unless the operator explicitly asks for system logs
- for runtime logs prefer:
  - python3 scripts/runtime_storage_report.py
  - du -sh data/mind data/runtime data/journal logs 2>/dev/null
- for python version use: python3 --version
- for node version use: node --version
- for kernel use: uname -r
- for public IP use: curl -s https://ifconfig.me
- for RAM use: free -h
- for git status use: git status --short
- for desktop/X11/Wayland use:
  pgrep -a 'Xorg|wayland|mutter|kwin|gnome-shell|lightdm|sddm' || echo 'Nessun processo grafico trovato'

User request: {user_text[:300]!r}
""".strip()
