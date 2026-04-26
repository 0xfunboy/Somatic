#!/usr/bin/env python3
"""Minimal WebSocket smoke test for the latent-somatic runtime."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

import websockets


COMMON_FIELDS = ("provider", "sensors", "system", "derived", "projector", "llm", "affect", "actions", "homeostasis", "machine_vector", "policy", "actuation")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def decode_message(raw: str) -> dict[str, Any]:
    payload = json.loads(raw)
    require(isinstance(payload, dict), "WebSocket payload is not an object")
    require("type" in payload, "WebSocket payload missing type")
    return payload


def validate_common_payload(payload: dict[str, Any], *, expected_type: str) -> None:
    require(payload.get("type") == expected_type, f"Expected {expected_type}, got {payload.get('type')}")
    for field in COMMON_FIELDS:
        require(field in payload, f"{expected_type} missing field: {field}")
    require(isinstance(payload["actions"], list), f"{expected_type}.actions must be a list")
    require(isinstance(payload["affect"], dict), f"{expected_type}.affect must be an object")
    require(isinstance(payload["homeostasis"], dict), f"{expected_type}.homeostasis must be an object")
    require(isinstance(payload["machine_vector"], dict), f"{expected_type}.machine_vector must be an object")
    require(payload["machine_vector"].get("dim") == 128, f"{expected_type}.machine_vector.dim must be 128")
    require(isinstance(payload["policy"], dict), f"{expected_type}.policy must be an object")
    require(isinstance(payload["actuation"], dict), f"{expected_type}.actuation must be an object")


async def recv_until(ws, wanted_type: str, timeout_s: float) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    while True:
        remaining = deadline - time.monotonic()
        require(remaining > 0, f"Timed out waiting for {wanted_type}")
        payload = decode_message(await asyncio.wait_for(ws.recv(), timeout=remaining))
        if payload.get("type") == wanted_type:
            return payload


async def run(args: argparse.Namespace) -> None:
    uri = f"ws://{args.host}:{args.port}"
    async with websockets.connect(uri, open_timeout=args.timeout) as ws:
        init_payload = decode_message(await asyncio.wait_for(ws.recv(), timeout=args.timeout))
        require(init_payload.get("type") == "init", f"Expected init, got {init_payload.get('type')}")
        validate_common_payload(init_payload, expected_type="init")

        tick_payload = await recv_until(ws, "tick", args.timeout)
        validate_common_payload(tick_payload, expected_type="tick")

        await ws.send(json.dumps({"type": "chat", "text": args.text}))
        reply_payload = await recv_until(ws, "chat_reply", args.timeout)
        validate_common_payload(reply_payload, expected_type="chat_reply")

        reply_text = str(reply_payload.get("text") or "").strip()
        require(reply_text, "chat_reply.text is empty")

        llm_payload = reply_payload["llm"]
        require(isinstance(llm_payload, dict), "chat_reply.llm must be an object")
        if args.expect_llm:
            require(bool(llm_payload.get("available")), "LLM was expected to be available but reply says otherwise")
        if args.expect_llm_mode:
            require(
                str(llm_payload.get("mode")) == args.expect_llm_mode,
                f"Expected llm.mode={args.expect_llm_mode}, got {llm_payload.get('mode')}",
            )

        provider = reply_payload["provider"]
        projector = reply_payload["projector"]
        print(
            json.dumps(
                {
                    "ok": True,
                    "provider": provider.get("name"),
                    "provider_is_real": provider.get("is_real"),
                    "projector_mode": projector.get("mode"),
                    "llm_available": llm_payload.get("available"),
                    "llm_mode": llm_payload.get("mode"),
                    "reply_preview": reply_text[:160],
                },
                ensure_ascii=True,
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke test the latent-somatic WebSocket runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--text", default="What are you feeling right now?")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--expect-llm", action="store_true")
    parser.add_argument("--expect-llm-mode", choices=("off", "fallback", "openai_compatible", "deepseek"))
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
