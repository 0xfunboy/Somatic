"""Built-in network diagnostic skills."""
from __future__ import annotations

import subprocess
from typing import Any

from soma_core.skills.base import Skill, SkillResult

# ---------------------------------------------------------------------------
# Shared subprocess helper
# ---------------------------------------------------------------------------


def _run(cmd: str, timeout: int = 20) -> tuple[bool, str, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, r.stdout.strip()[:4000], r.stderr.strip()[:500]
    except Exception as exc:
        return False, "", str(exc)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_public_ip(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("curl -s --max-time 5 https://ifconfig.me")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_ping_gateway(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run(
        "ip route | grep default | awk '{print $3}' | xargs ping -c 3 -W 2",
        timeout=20,
    )
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_speed_test_light(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    cmd = (
        "curl -s -o /dev/null -w '%{speed_download}' --max-time 15 "
        "https://speed.cloudflare.com/__down?bytes=20000000 | "
        "python3 -c \"import sys; v=float(sys.stdin.read().strip() or 0); "
        "print(f'{v/131072:.2f} Mbps')\""
    )
    ok, out, err = _run(cmd, timeout=20)
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_http_check(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run(
        "curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://google.com"
    )
    text = f"HTTP status: {out}" if out else err
    return SkillResult(ok=ok, text=text, stdout=out, stderr=err)


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

NETWORK_SKILLS: list[Skill] = [
    Skill(
        id="network.public_ip",
        name="Public IP",
        description="Retrieve the current public IP address via ifconfig.me.",
        category="network",
        risk_level="low",
        permissions=["network", "read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["what is my public IP", "public IP address", "external IP"],
        handler=_h_public_ip,
    ),
    Skill(
        id="network.ping_gateway",
        name="Ping Gateway",
        description="Ping the default gateway to test local network connectivity.",
        category="network",
        risk_level="low",
        permissions=["network", "read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["ping gateway", "network connectivity", "is the network up"],
        handler=_h_ping_gateway,
    ),
    Skill(
        id="network.speed_test_light",
        name="Speed Test (Light)",
        description="Estimate download speed with a 20 MB Cloudflare test file.",
        category="network",
        risk_level="low",
        permissions=["network", "read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["internet speed", "download speed test", "bandwidth test"],
        handler=_h_speed_test_light,
    ),
    Skill(
        id="network.http_check",
        name="HTTP Check",
        description="Check HTTP status code for https://google.com.",
        category="network",
        risk_level="low",
        permissions=["network"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["check internet", "is internet working", "http status"],
        handler=_h_http_check,
    ),
]
