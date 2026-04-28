from __future__ import annotations

import re
from typing import Any

from soma_core.relevance import RelevanceFilter


_BANNED_SNIPPETS = (
    "i am processing that with a live body state",
    "my current somatic context is",
    "nominal state via linux",
    "somatic context",
    "12.0v",
    "voltage",
    "voltaggio",
    "tensione operativa",
    "silicon",
    "silicio",
    "thermal_stress",
    "energy_stress",
    "comfort=",
    "somatic map",
    "mappa somatica",
    "projector norm",
    "temperatura del silicio",
    "la mia temperatura",
    "la mia ram",
    "ram 4",
    "cpu 3",
    "il mio core",
    "my core voltage",
)
_TELEMETRY_PATTERNS = (
    re.compile(r"\b\d+(?:\.\d+)?\s*v\b", re.IGNORECASE),
    re.compile(r"\b\d+(?:\.\d+)?\s*°?c\b", re.IGNORECASE),
    re.compile(r"\bthermal\b", re.IGNORECASE),
    re.compile(r"\bthermal stress\b", re.IGNORECASE),
    re.compile(r"\benergy stress\b", re.IGNORECASE),
)


def _fallback_text(user_text: str) -> str:
    low = (user_text or "").lower()
    if any(mark in low for mark in ("what", "how", "why", "kernel", "version", "public ip")):
        return "I do not have enough verified operational context to answer that with confidence."
    return "Non ho abbastanza contesto operativo verificato per rispondere con certezza."


class OutputFilter:
    def __init__(self, relevance: RelevanceFilter | None = None) -> None:
        self._relevance = relevance or RelevanceFilter()

    def clean_response(
        self,
        text: str,
        user_text: str,
        snapshot: dict[str, Any],
        *,
        command_result: dict[str, Any] | None = None,
        skill_result: dict[str, Any] | None = None,
    ) -> str:
        raw = (text or "").strip()
        if not raw:
            return _fallback_text(user_text)

        mention_body, _reason = self._relevance.should_mention_body(user_text, snapshot, command_result)
        if mention_body:
            return self._normalize(raw)

        parts = re.split(r"(?<=[.!?])\s+|\n+", raw)
        kept: list[str] = []
        for part in parts:
            snippet = part.strip()
            if not snippet:
                continue
            low = snippet.lower()
            if any(item in low for item in _BANNED_SNIPPETS):
                continue
            if any(pattern.search(snippet) for pattern in _TELEMETRY_PATTERNS):
                if command_result and command_result.get("ok"):
                    continue
                if skill_result and skill_result.get("ok"):
                    continue
            kept.append(snippet)

        if kept:
            return self._normalize(" ".join(kept))

        if command_result and command_result.get("ok"):
            cmd = str(command_result.get("cmd") or "command")
            stdout = str(command_result.get("stdout") or "").strip()
            return self._normalize(
                f"Ho verificato con `{cmd}`: {stdout}." if stdout else f"Ho eseguito `{cmd}`: successo, ma senza output."
            )
        if skill_result and skill_result.get("ok"):
            skill_text = str(skill_result.get("text") or skill_result.get("stdout") or "").strip()
            if skill_text:
                return self._normalize(skill_text)
        useful = self._most_useful_non_telemetry(raw)
        return self._normalize(useful or _fallback_text(user_text))

    def _most_useful_non_telemetry(self, text: str) -> str:
        for part in re.split(r"(?<=[.!?])\s+|\n+", text):
            snippet = part.strip()
            if not snippet:
                continue
            low = snippet.lower()
            if any(item in low for item in _BANNED_SNIPPETS):
                continue
            if any(pattern.search(snippet) for pattern in _TELEMETRY_PATTERNS):
                continue
            return snippet
        return ""

    def _normalize(self, text: str) -> str:
        cleaned = re.sub(r"\s+", " ", text).strip()
        return cleaned
