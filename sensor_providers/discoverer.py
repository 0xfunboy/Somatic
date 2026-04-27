"""
Hardware discovery engine — LLM-guided sensor capability resolution.

Flow:
  1. Check which system telemetry fields return None.
  2. For each unknown field: ask the LLM which bash command to run.
  3. Run the command (sandboxed, timeout-bounded).
  4. success  → record command + mark field available.
  5. failure  → mark field unavailable, stop retrying.
  6. If SOMA_SELF_MODIFY=1: write discovered.py, git add/commit/push.

Callers keep this class synchronous; async wrappers live in server.py.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

# ── paths ────────────────────────────────────────────────────────────────────

_PROJECT_ROOT = Path(__file__).parent.parent
CAPABILITIES_DIR = _PROJECT_ROOT / "data" / "capabilities"
DISCOVERED_COMMANDS_FILE = CAPABILITIES_DIR / "discovered_commands.json"
TELEMETRY_CAPS_FILE = CAPABILITIES_DIR / "telemetry_caps.json"
DISCOVERED_SENSOR_FILE = Path(__file__).parent / "discovered.py"

# ── constants ─────────────────────────────────────────────────────────────────

MAX_OUTPUT_BYTES = 4096
SHELL_TIMEOUT_S = 8.0

# Fields we try to discover automatically when they return None.
DISCOVERABLE_FIELDS: dict[str, str] = {
    "gpu_memory_total_mb": "Total GPU VRAM in megabytes (integer or float)",
    "gpu_memory_used_mb":  "Used GPU VRAM in megabytes",
    "gpu_util_percent":    "GPU utilization percentage 0–100",
    "gpu_temp":            "GPU temperature in Celsius",
    "gpu_power_w":         "GPU power draw in Watts",
    "fan_rpm":             "Primary system fan speed in RPM — a single integer like 1200",
    "disk_temp":           "Primary storage device temperature in Celsius",
    "battery_percent":     "Battery charge percentage 0–100",
    "cpu_power_w":         "CPU package power draw in Watts (from powercap RAPL or sensors)",
    "ac_online":           "AC power adapter connected — print 1 if online, 0 if offline",
    "battery_plugged":     "Battery charging status — print 1 if charging, 0 if discharging",
    "disk_busy_percent":   "Primary disk I/O busy percentage 0–100 (from /proc/diskstats or iostat)",
}

# Prefixes of commands that must never be run.
BLOCKED_PREFIXES = (
    "rm ", "mv ", "dd ", "mkfs", "kill", "killall",
    "shutdown", "reboot", "poweroff", "halt",
    "format", "fdisk", "parted", "wipefs",
    "chmod 777", "chown", "sudo rm",
)


# ── shell executor ─────────────────────────────────────────────────────────────

class ShellExecutor:
    """Sandboxed synchronous command runner."""

    def __init__(self, timeout_s: float = SHELL_TIMEOUT_S) -> None:
        self.timeout_s = timeout_s

    def is_safe(self, cmd: str) -> bool:
        stripped = cmd.strip().lower()
        if "\n" in cmd:
            return False
        if any(stripped.startswith(p) for p in BLOCKED_PREFIXES):
            return False
        return True

    def run(self, cmd: str) -> tuple[bool, str, str]:
        """
        Returns (success, stdout, stderr).
        success = True only when returncode==0 AND stdout is non-empty.
        """
        if not self.is_safe(cmd):
            return False, "", "BLOCKED: unsafe command pattern"
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                env={**os.environ, "LANG": "C", "LC_ALL": "C"},
            )
            stdout = result.stdout.strip()[: MAX_OUTPUT_BYTES]
            stderr = result.stderr.strip()[:512]
            success = result.returncode == 0 and bool(stdout)
            return success, stdout, stderr
        except subprocess.TimeoutExpired:
            return False, "", f"TIMEOUT after {self.timeout_s}s"
        except Exception as exc:
            return False, "", str(exc)


# ── hardware discovery ─────────────────────────────────────────────────────────

class HardwareDiscovery:
    """
    Manages capability state.

    Discovery workflow:
      needs_discovery(field)       → True if not yet tried
      build_discovery_prompt(...)  → prompt string for the LLM
      record_llm_reply(...)        → parse LLM reply, run command, persist
      get_caps()                   → dict[str, bool|None]  (None=pending)
    """

    def __init__(self, shell: ShellExecutor) -> None:
        self.shell = shell
        CAPABILITIES_DIR.mkdir(parents=True, exist_ok=True)
        self.commands: dict[str, Any] = self._load(DISCOVERED_COMMANDS_FILE)
        self.caps: dict[str, Any] = self._load(TELEMETRY_CAPS_FILE)

    # ── persistence ──────────────────────────────────────────────────────────

    @staticmethod
    def _load(path: Path) -> dict:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save(self) -> None:
        DISCOVERED_COMMANDS_FILE.write_text(
            json.dumps(self.commands, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        TELEMETRY_CAPS_FILE.write_text(
            json.dumps(self.caps, indent=2, ensure_ascii=True), encoding="utf-8"
        )

    # ── queries ───────────────────────────────────────────────────────────────

    def needs_discovery(self, field: str) -> bool:
        """True if we have never tried to discover this field."""
        return field not in self.commands

    def get_caps(self) -> dict[str, bool | None]:
        """Return capability map: True=available, False=unavailable, None=pending."""
        return {
            field: self.caps.get(field, None)
            for field in DISCOVERABLE_FIELDS
        }

    def get_known_cmd(self, field: str) -> str | None:
        entry = self.commands.get(field, {})
        if entry.get("status") == "available":
            return entry.get("cmd")
        return None

    # ── prompt building ───────────────────────────────────────────────────────

    def build_discovery_prompt(
        self,
        field: str,
        description: str,
        system_profile: dict[str, Any],
    ) -> str:
        cpu_logical = system_profile.get("cpu_count_logical") or "?"
        cpu_physical = system_profile.get("cpu_count_physical") or "?"
        ram_gb = system_profile.get("memory_total_gb") or "?"
        os_info = f"{platform.system()} {platform.release()} {platform.machine()}"
        hostname = platform.node()

        return (
            "You are the sensor-discovery subsystem of an autonomous Linux embedded agent.\n"
            f"System: {os_info}, hostname={hostname}, "
            f"CPU logical={cpu_logical} physical={cpu_physical}, RAM={ram_gb}GB.\n"
            f"\nMissing telemetry field: `{field}`\n"
            f"Expected value: {description}\n"
            "\nReply with ONLY a single safe bash command that prints this value to stdout "
            "and exits in under 5 seconds.\n"
            "Do NOT include explanations, markdown fences, or comments.\n"
            "If this hardware cannot provide the value, reply exactly: UNAVAILABLE"
        )

    # ── result recording ──────────────────────────────────────────────────────

    def record_llm_reply(self, field: str, llm_text: str) -> str:
        """
        Parse the LLM reply, run the command, persist the result.
        Returns 'available' | 'unavailable'.
        """
        cmd_raw = llm_text.strip().strip("`").strip()

        if not cmd_raw or cmd_raw.upper().startswith("UNAVAILABLE"):
            self._mark_unavailable(field, f"LLM declared: {cmd_raw[:80]}")
            return "unavailable"

        # Strip any accidental code-fence language tag
        cmd = re.sub(r"^(bash|sh|zsh)\s+", "", cmd_raw, flags=re.IGNORECASE).strip()

        success, stdout, stderr = self.shell.run(cmd)
        # Reject "UNAVAILABLE" echoes — LLM sometimes generates cmds that echo this on failure
        if success and stdout.strip().upper() == "UNAVAILABLE":
            success = False
            stderr = "command output was literal UNAVAILABLE — device not present"
        if success:
            self._mark_available(field, cmd, stdout)
            return "available"
        else:
            reason = stderr or stdout or "no output"
            self._mark_unavailable(field, f"cmd={cmd!r} → {reason[:120]}")
            return "unavailable"

    def _mark_available(self, field: str, cmd: str, sample: str) -> None:
        self.commands[field] = {
            "status": "available",
            "cmd": cmd,
            "sample_output": sample[:200],
            "discovered_at": time.time(),
            "host": platform.node(),
        }
        self.caps[field] = True
        self._save()
        print(f"[DISCOVERY] ✓ {field}  cmd={cmd!r}  sample={sample[:60]!r}")

    def _mark_unavailable(self, field: str, reason: str) -> None:
        self.commands[field] = {
            "status": "unavailable",
            "reason": reason,
            "tried_at": time.time(),
            "host": platform.node(),
        }
        self.caps[field] = False
        self._save()
        print(f"[DISCOVERY] ✗ {field}  reason={reason[:80]!r}")

    def run_known_commands(self, missing_fields: list[str]) -> dict[str, str | None]:
        """
        For fields that already have a known working command, run and return output.
        Used to supply data in the tick loop without repeating discovery.
        """
        results: dict[str, str | None] = {}
        for field in missing_fields:
            cmd = self.get_known_cmd(field)
            if cmd:
                ok, stdout, _ = self.shell.run(cmd)
                results[field] = stdout if ok else None
        return results


# ── self-modifier ─────────────────────────────────────────────────────────────

SELF_MODIFY_ENABLED = os.getenv("SOMA_SELF_MODIFY", "0").strip().lower() not in {
    "0", "false", "no", "off"
}


class SelfModifier:
    """
    Writes sensor_providers/discovered.py and pushes to git.
    Opt-in: requires SOMA_SELF_MODIFY=1.
    """

    def __init__(self, shell: ShellExecutor) -> None:
        self.shell = shell

    def _git(self, *args: str) -> tuple[bool, str]:
        safe_args = " ".join(shlex.quote(a) for a in args)
        return self.shell.run(f"git -C {shlex.quote(str(_PROJECT_ROOT))} {safe_args}")

    def generate_module(self, commands: dict[str, Any]) -> str:
        available = {k: v for k, v in commands.items() if v.get("status") == "available"}
        lines: list[str] = [
            '"""',
            "Auto-generated by LSF hardware discovery.",
            f"Host: {platform.node()}  Generated: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}",
            'Do not edit manually — will be overwritten on next discovery run.',
            '"""',
            "from __future__ import annotations",
            "import subprocess, os as _os",
            "",
            "_ENV = {**_os.environ, 'LANG': 'C', 'LC_ALL': 'C'}",
            "",
            "def _run(cmd: str) -> str | None:",
            "    try:",
            "        r = subprocess.run(cmd, shell=True, capture_output=True, text=True,",
            "                           timeout=5, env=_ENV)",
            "        return r.stdout.strip() or None",
            "    except Exception:",
            "        return None",
            "",
            "def read_discovered_fields() -> dict[str, float | str | None]:",
            '    """Return discovered sensor values. Returns empty dict on full failure."""',
            "    out: dict[str, float | str | None] = {}",
        ]

        for field, entry in available.items():
            cmd = entry["cmd"].replace("\\", "\\\\").replace("'", "\\'")
            lines += [
                f"    # {field}: {DISCOVERABLE_FIELDS.get(field, '')}",
                f"    _raw = _run('{cmd}')",
                f"    if _raw:",
                f"        try: out['{field}'] = float(_raw.split()[0])",
                f"        except ValueError: out['{field}'] = _raw",
            ]

        lines += ["    return out", ""]
        return "\n".join(lines)

    def commit_discovery(
        self,
        commands: dict[str, Any],
        caps: dict[str, Any],
    ) -> bool:
        if not SELF_MODIFY_ENABLED:
            return False

        module_code = self.generate_module(commands)
        DISCOVERED_SENSOR_FILE.write_text(module_code, encoding="utf-8")

        hostname = re.sub(r"[^a-z0-9-]", "-", platform.node().lower())
        branch = f"auto/{hostname}-sensors"

        files_to_stage = [
            str(DISCOVERED_SENSOR_FILE.relative_to(_PROJECT_ROOT)),
            str(DISCOVERED_COMMANDS_FILE.relative_to(_PROJECT_ROOT)),
            str(TELEMETRY_CAPS_FILE.relative_to(_PROJECT_ROOT)),
        ]

        ok, out = self._git("add", *files_to_stage)
        if not ok:
            print(f"[SELF-MODIFY] git add failed: {out[:120]}")
            return False

        n_avail = sum(1 for v in caps.values() if v is True)
        n_unavail = sum(1 for v in caps.values() if v is False)
        msg = f"auto({hostname}): +{n_avail} sensor(s) discovered, {n_unavail} confirmed unavailable"

        ok, out = self._git("commit", "-m", msg)
        if not ok:
            if "nothing to commit" in out:
                print("[SELF-MODIFY] nothing new to commit")
                return True
            print(f"[SELF-MODIFY] git commit failed: {out[:120]}")
            return False

        ok, out = self._git("push", "origin", f"HEAD:{branch}")
        if not ok:
            print(f"[SELF-MODIFY] git push failed: {out[:120]}")
            return False

        print(f"[SELF-MODIFY] Pushed → branch {branch}")
        return True
