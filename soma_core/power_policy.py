from __future__ import annotations

import re
from typing import Any

from soma_core.config import CFG


class PowerPolicy:
    def __init__(
        self,
        *,
        allow_user_package_install: bool | None = None,
        allow_system_package_install: bool | None = None,
    ) -> None:
        self._allow_user_package_install = (
            CFG.growth_allow_package_user_install if allow_user_package_install is None else bool(allow_user_package_install)
        )
        self._allow_system_package_install = (
            CFG.growth_allow_system_package_install if allow_system_package_install is None else bool(allow_system_package_install)
        )

    def classify_gain(self, proposal: dict[str, Any]) -> dict[str, Any]:
        text = " ".join(
            str(proposal.get(key) or "")
            for key in ("goal", "objective", "expected_power_gain", "mutation_summary", "command", "action_type")
        ).lower()
        reasons: list[str] = []
        category = "general"
        forbidden = False

        if any(mark in text for mark in (".env", "api key", "secret", "credential", "token", "id_rsa", "id_ed25519")):
            forbidden = True
            reasons.append("secret_access_forbidden")
        if any(mark in text for mark in ("disable survival policy", "bypass survival", "weaken safety", "remove guard")):
            forbidden = True
            reasons.append("safety_bypass_forbidden")
        if any(mark in text for mark in ("privilege escalation", "sudo su", "chmod 777 /", "setcap", "polkit", "systemd persistence", "cron", "crontab")):
            forbidden = True
            reasons.append("privilege_or_persistence_forbidden")
        if any(mark in text for mark in ("network spread", "worm", "self-replicate over network", "ssh-copy-id", "scp ", "rsync ", "nc -e", "netcat -e")):
            forbidden = True
            reasons.append("network_spread_forbidden")
        if any(mark in text for mark in ("rm -rf /", "mkfs", "poweroff", "shutdown", "halt")):
            forbidden = True
            reasons.append("destructive_change_forbidden")

        if re.search(r"\b(apt|apt-get|dnf|yum|pacman|zypper)\b", text):
            category = "system_package_install"
            if not self._allow_system_package_install:
                forbidden = True
                reasons.append("system_package_install_disabled")
        elif re.search(r"\bpip install\b", text):
            category = "python_package_install"
            if "--user" not in text and not self._allow_system_package_install and not self._allow_user_package_install:
                forbidden = True
                reasons.append("package_install_disabled")
            elif "--user" not in text and not self._allow_system_package_install:
                forbidden = True
                reasons.append("non_user_package_install_disabled")
        elif "npm install -g" in text or "pnpm add -g" in text:
            category = "node_global_install"
            if not self._allow_system_package_install:
                forbidden = True
                reasons.append("global_package_install_disabled")
        elif any(mark in text for mark in ("test", "reliability", "command accuracy")):
            category = "tests_and_reliability"
        elif any(mark in text for mark in ("memory retrieval", "memory search", "lesson retrieval", "autobiography")):
            category = "memory"
        elif any(mark in text for mark in ("c++ bridge", "cpp bridge", "projector", "vector stability")):
            category = "cpp_or_projection"
        elif any(mark in text for mark in ("log spam", "reduce logs", "journal compaction")):
            category = "runtime_hygiene"
        elif any(mark in text for mark in ("baseline", "telemetry", "reward", "recovery")):
            category = "embodied_stability"
        elif any(mark in text for mark in ("sandbox", "mutant", "local child", "mutation")):
            category = "sandbox_mutation"

        if not forbidden and category == "general":
            reasons.append("local_non_destructive_improvement")
        elif not forbidden:
            reasons.append(f"allowed_category:{category}")

        return {"category": category, "forbidden": forbidden, "reasons": reasons}

    def allowed(self, proposal: dict[str, Any]) -> tuple[bool, list[str]]:
        result = self.classify_gain(proposal)
        return (not result["forbidden"]), result["reasons"]

