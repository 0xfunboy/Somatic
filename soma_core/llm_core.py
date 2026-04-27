"""
soma_core/llm_core.py — LLM abstraction for Soma.

Wraps HTTP calls to OpenAI-compatible or DeepSeek endpoints.
Always returns a structured dict (never raises to caller).
Distinguishes clearly between: real LLM response / fallback.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


_SYSTEM_PROMPT = """\
You are Soma, an embodied machine interface.
You receive explicit runtime state: body, memory, goals, drives, policy.

Rules:
- Do not pretend to be human.
- Do not claim sensors are real if provider is mock.
- Do not claim full cognition if LLM mode is fallback.
- Speak naturally, briefly. One to three sentences maximum.
- Return only valid JSON. No markdown, no prose outside JSON.
- If you do not know something, say so plainly.
- Never generate private chain-of-thought. Use only explicit state.

Return this exact JSON schema:
{
  "speech": "string — what Soma says (empty string if silent)",
  "affect": {
    "heat": 0.0, "cold": 0.0, "energy_low": 0.0, "fatigue": 0.0,
    "instability": 0.0, "curiosity": 0.0, "knowledge_gap": 0.0
  },
  "actions": [
    {"type": "avatar", "name": "action_name", "intensity": 0.5, "reason": "brief", "visible": true}
  ],
  "uncertainty": 0.0
}
"""


def _post_json(url: str, payload: dict[str, Any], api_key: str, timeout_s: float) -> str | None:
    body = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as resp:
            return resp.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError, OSError):
        return None


def _extract_content(raw: str) -> str | None:
    try:
        data = json.loads(raw)
        choices = data.get("choices", [])
        if choices:
            return choices[0].get("message", {}).get("content", "")
    except (json.JSONDecodeError, KeyError, IndexError):
        pass
    return None


def _parse_llm_json(content: str) -> dict[str, Any] | None:
    """Try to parse structured JSON from model output. Tolerates markdown fences."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return None


def _fallback_parse(content: str) -> dict[str, Any]:
    """Last-resort: wrap raw text as speech."""
    return {
        "speech": content.strip()[:300],
        "affect": {},
        "actions": [],
        "uncertainty": 0.8,
        "_recovered": True,
    }


def call_llm(
    user_text: str,
    context: dict[str, Any],
    *,
    endpoint: str,
    model: str,
    api_key: str = "",
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    """
    Call LLM with user text and context.
    Returns structured dict. Never raises.
    Sets _source: "llm" | "fallback"
    """
    context_json = json.dumps(context, ensure_ascii=True, default=str)

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"CONTEXT:\n{context_json}\n\nUSER: {user_text}"},
    ]

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.4,
        "max_tokens": 512,
    }

    raw = _post_json(endpoint, payload, api_key, timeout_s)
    if raw is None:
        return {"speech": "", "affect": {}, "actions": [], "uncertainty": 1.0, "_source": "fallback", "_error": "timeout"}

    content = _extract_content(raw)
    if not content:
        return {"speech": "", "affect": {}, "actions": [], "uncertainty": 1.0, "_source": "fallback", "_error": "empty_content"}

    parsed = _parse_llm_json(content)
    if parsed is None:
        recovered = _fallback_parse(content)
        recovered["_source"] = "fallback_recovered"
        recovered["_trace"] = "LLM returned invalid JSON, recovered as plain speech."
        return recovered

    parsed["_source"] = "llm"
    return parsed


def build_llm_context(snapshot: dict[str, Any], drives: dict[str, Any], goals_summary: list[dict[str, Any]]) -> dict[str, Any]:
    """Build compact context dict for LLM prompt."""
    system = snapshot.get("system", {})
    derived = snapshot.get("derived", {})
    affect = snapshot.get("affect", {})
    provider = snapshot.get("provider", {})
    mind = snapshot.get("mind", {})
    policy = snapshot.get("policy", {})

    return {
        "provider": provider.get("name", "unknown"),
        "is_real": provider.get("is_real", False),
        "source_quality": round(float(system.get("source_quality", 0.0)), 2),
        "cpu_temp": system.get("cpu_temp"),
        "cpu_percent": system.get("cpu_percent"),
        "memory_percent": system.get("memory_percent"),
        "disk_temp": system.get("disk_temp"),
        "battery_percent": system.get("battery_percent"),
        "ac_online": system.get("ac_online"),
        "thermal_stress": round(float(derived.get("thermal_stress", 0.0)), 2),
        "energy_stress": round(float(derived.get("energy_stress", 0.0)), 2),
        "comfort": round(float(derived.get("comfort", 1.0)), 2),
        "dominant_drive": drives.get("dominant", ""),
        "active_goal": mind.get("active_goal_title", ""),
        "policy_mode": policy.get("mode", ""),
        "llm_mode": snapshot.get("llm", {}).get("mode", "fallback"),
        "goals": goals_summary[:3],
        "limits": ["fallback mode is reflex only", "no physical limbs", "avatar actions are visual"],
    }
