"""Built-in system introspection skills."""
from __future__ import annotations

import subprocess
from typing import Any

from soma_core.skills.base import Skill, SkillResult

# ---------------------------------------------------------------------------
# Shared subprocess helper
# ---------------------------------------------------------------------------


def _run(cmd: str) -> tuple[bool, str, str]:
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return r.returncode == 0, r.stdout.strip()[:4000], r.stderr.strip()[:500]
    except Exception as exc:
        return False, "", str(exc)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _h_python_version(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run('python3 -c "import sys; print(sys.version)"')
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_kernel_version(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("uname -r")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_os_info(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("uname -a")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_memory_status(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("free -h")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_disk_usage(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("df -h /home/funboy")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_cpu_info_short(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run('nproc && grep "model name" /proc/cpuinfo | head -1')
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_process_list(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run("ps aux --sort=-%cpu | head -20")
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_python_processes(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run('pgrep -a python3 || echo "none"')
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


def _h_env_status_safe(args: dict[str, Any], context: dict[str, Any]) -> SkillResult:
    ok, out, err = _run(
        'env | grep -v -i "key\\|secret\\|token\\|password\\|api" | head -30'
    )
    return SkillResult(ok=ok, text=out or err, stdout=out, stderr=err)


# ---------------------------------------------------------------------------
# Skill definitions
# ---------------------------------------------------------------------------

SYSTEM_SKILLS: list[Skill] = [
    Skill(
        id="system.python_version",
        name="Python Version",
        description="Report the Python 3 version currently in use.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["What Python version is running?", "python version"],
        handler=_h_python_version,
    ),
    Skill(
        id="system.kernel_version",
        name="Kernel Version",
        description="Report the Linux kernel version via uname -r.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["kernel version", "what kernel is running"],
        handler=_h_kernel_version,
    ),
    Skill(
        id="system.os_info",
        name="OS Info",
        description="Report full OS/kernel info via uname -a.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["os info", "system info", "uname"],
        handler=_h_os_info,
    ),
    Skill(
        id="system.memory_status",
        name="Memory Status",
        description="Show current memory usage in human-readable form (free -h).",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["memory usage", "how much RAM is free", "free memory"],
        handler=_h_memory_status,
    ),
    Skill(
        id="system.disk_usage",
        name="Disk Usage",
        description="Show disk usage for /home/funboy (df -h).",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["disk space", "how much disk is free", "storage usage"],
        handler=_h_disk_usage,
    ),
    Skill(
        id="system.cpu_info_short",
        name="CPU Info Short",
        description="Report CPU core count and model name.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["cpu info", "how many cores", "processor model"],
        handler=_h_cpu_info_short,
    ),
    Skill(
        id="system.process_list",
        name="Process List",
        description="Show top 20 processes by CPU usage.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["running processes", "what is using CPU", "top processes"],
        handler=_h_process_list,
    ),
    Skill(
        id="system.python_processes",
        name="Python Processes",
        description="List running Python 3 processes.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["python processes", "running python scripts"],
        handler=_h_python_processes,
    ),
    Skill(
        id="system.env_status_safe",
        name="Environment Status (Safe)",
        description="Show environment variables, filtered to exclude secrets/API keys.",
        category="system",
        risk_level="low",
        permissions=["read_system"],
        source="native",
        enabled=True,
        requires_confirmation=False,
        examples=["environment variables", "env vars", "show env"],
        handler=_h_env_status_safe,
    ),
]
