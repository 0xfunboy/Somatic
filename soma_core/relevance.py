from __future__ import annotations

import re
from typing import Any


_IT_BODY = (
    "caldo", "freddo", "temperatura", "scaldi", "scaldando", "surriscaldamento",
    "energia", "batteria", "corrente", "voltaggio", "tensione", "sensori",
    "corpo", "come ti senti", "come stai", "stato", "stress", "comfort",
    "prestazioni", "performance", "carico", "cpu", "ram", "disco", "ventola",
    "salute", "stabilita", "stabilità", "termico", "thermal",
)
_EN_BODY = (
    "heat", "hot", "cold", "temperature", "thermal", "battery", "voltage",
    "power", "sensors", "body", "how do you feel", "how are you", "stability",
    "stress", "comfort", "performance", "load", "memory", "disk", "fan",
    "health", "cpu", "ram", "gpu",
)
_MEMORY = (
    "lesson", "lessons", "lezione", "lezioni", "memory", "memoria",
    "autobiography", "autobiograf", "reflection", "riflession", "remember",
    "ricordi", "hai imparato", "learned", "learn",
)
_GROWTH = (
    "growth", "crescita", "stage", "stadio", "blocker", "blockers", "blocco",
    "bios", "mutation", "sandbox", "cpp", "bridge", "baseline", "evol",
)
_SYSTEM_FACT = (
    "version", "versione", "kernel", "python", "node", "ip pubblico",
    "public ip", "ram libera", "free ram", "git status", "log runtime",
    "runtime logs", "storage report", "desktop", "wayland", "x11", "repo log",
)
_SYSTEM_FACT_PATTERNS = (
    re.compile(r"\b(quanta|quanti|quanto)\s+ram\s+libera\b"),
    re.compile(r"\bfree\s+ram\b"),
    re.compile(r"\b(public|pubblico)\s+ip\b"),
    re.compile(r"\b(node|python)\s+--version\b"),
    re.compile(r"\b(runtime|repo)\s+log(s)?\b"),
    re.compile(r"\blog\s+size\b"),
)
_FEELING = ("come ti senti", "come stai", "stai bene", "how do you feel", "how are you")
_IDENTITY = ("chi sei", "cosa sei", "who are you", "what are you")
_CREATIVE = ("poem", "poesia", "story", "storia", "invent", "creative")
_PHIL = ("why", "perché", "coscienza", "consciousness", "meaning", "senso")
_OP = ("run", "esegui", "verifica", "check", "controlla", "ispeziona")


def _tokens(text: str) -> set[str]:
    return {tok for tok in re.findall(r"[a-z0-9_]{2,}", text.lower())}


class RelevanceFilter:
    def classify_request(self, user_text: str) -> dict[str, Any]:
        low = (user_text or "").lower().strip()
        if not low:
            return {"class": "unknown", "reason": "empty"}
        if "[shell_result]" in low:
            return {"class": "command_result", "reason": "shell_context"}
        if any(mark in low for mark in _MEMORY):
            return {"class": "memory_request", "reason": "memory_keywords"}
        if any(mark in low for mark in _GROWTH):
            return {"class": "growth_request", "reason": "growth_keywords"}
        if any(mark in low for mark in _FEELING):
            return {"class": "feeling", "reason": "feeling_keywords"}
        if any(mark in low for mark in _IDENTITY):
            return {"class": "self_identity", "reason": "identity_keywords"}
        if any(mark in low for mark in _CREATIVE):
            return {"class": "creative", "reason": "creative_keywords"}
        if any(mark in low for mark in _PHIL):
            return {"class": "philosophical", "reason": "philosophical_keywords"}
        if any(mark in low for mark in _SYSTEM_FACT) or any(pattern.search(low) for pattern in _SYSTEM_FACT_PATTERNS):
            return {"class": "system_fact", "reason": "system_fact_keywords"}
        if any(mark in low for mark in _IT_BODY + _EN_BODY):
            if any(mark in low for mark in ("prestazioni", "performance", "carico", "load")):
                return {"class": "performance", "reason": "performance_keywords"}
            return {"class": "body_state", "reason": "body_keywords"}
        if any(mark in low for mark in _OP):
            return {"class": "operational", "reason": "operational_keywords"}
        return {"class": "unknown", "reason": "fallback"}

    def body_abnormal(self, snapshot: dict[str, Any]) -> bool:
        derived = snapshot.get("derived", {}) if isinstance(snapshot, dict) else {}
        system = snapshot.get("system", {}) if isinstance(snapshot, dict) else {}
        provider = snapshot.get("provider", {}) if isinstance(snapshot, dict) else {}
        checks = (
            float(derived.get("thermal_stress", 0.0)) >= 0.55,
            float(derived.get("energy_stress", 0.0)) >= 0.55,
            float(derived.get("instability", 0.0)) >= 0.55,
            float(system.get("cpu_temp") or 0.0) >= 75.0,
            float(system.get("disk_temp") or 0.0) >= 60.0,
            float(system.get("memory_percent") or 0.0) >= 85.0,
            float(system.get("disk_used_percent") or system.get("disk_percent") or 0.0) >= 90.0,
            float(provider.get("source_quality") or 1.0) <= 0.2,
        )
        return any(checks)

    def telemetry_relevant(
        self,
        user_text: str,
        *,
        command_result: dict[str, Any] | None = None,
        snapshot: dict[str, Any] | None = None,
    ) -> bool:
        classification = self.classify_request(user_text)
        request_class = classification["class"]
        if request_class in {"body_state", "feeling", "performance"}:
            return True
        if snapshot and self.body_abnormal(snapshot):
            return True
        if command_result and command_result.get("ok") and request_class in {"system_fact", "command_result", "memory_request"}:
            return False
        return False

    def should_mention_body(
        self,
        user_text: str,
        snapshot: dict[str, Any],
        command_result: dict[str, Any] | None = None,
    ) -> tuple[bool, str]:
        classification = self.classify_request(user_text)
        request_class = classification["class"]
        if request_class in {"body_state", "feeling", "performance"}:
            return True, request_class
        if self.body_abnormal(snapshot):
            return True, "abnormal_body_state"
        if command_result and command_result.get("ok"):
            return False, "successful_command_result"
        if request_class in {"memory_request", "growth_request", "system_fact", "operational"}:
            return False, request_class
        return False, "not_relevant"
