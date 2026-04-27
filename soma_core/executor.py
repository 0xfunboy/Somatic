"""
soma_core/executor.py — Autonomous shell executor with survival policy enforcement.

All LLM-proposed commands pass through this before execution.
Policy: denylist + resource guard + scope guard. Never a command whitelist.

Trace phases emitted: command_proposed, command_risk_check, command_executed,
                      command_blocked, skill_learned
"""

from __future__ import annotations

import os
import re
import shlex
import shutil
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from soma_core.trace import CognitiveTrace
    from soma_core.memory import SomaMemory

_REPO_ROOT = Path(__file__).parent.parent.resolve()

# ── denylist ──────────────────────────────────────────────────────────────────

# Any command token (first word of any pipeline stage, including after sudo) → blocked
_BLOCKED_TOKENS: frozenset[str] = frozenset({
    "shutdown", "poweroff", "halt",
    "mkfs", "wipefs", "fdisk", "parted", "gparted",
    "shred", "wipe", "srm",
    "passwd", "chpasswd", "usermod", "userdel", "useradd",
    "adduser", "deluser", "visudo",
    "killall", "pkill",
    "crontab",
    "format",
})

# Command prefixes that match any variant (e.g. mkfs.ext4, mkfs.xfs)
_BLOCKED_TOKEN_PREFIXES: tuple[str, ...] = (
    "mkfs.", "wipefs", "gparted",
)

# Substring appearing anywhere in the command → always blocked
_BLOCKED_SUBSTRINGS: tuple[str, ...] = (
    ":(){ :|:",            # fork bomb core
    "--no-preserve-root",  # rm without root safety
    ".env",                # .env file access
    "id_rsa",              # SSH private keys
    "id_ed25519",
    "id_dsa",
    "SOMA_DEEPSEEK_API_KEY",
    "SOMA_OPENAI_API_KEY",
    "OPENAI_API_KEY",
    "DEEPSEEK_API_KEY",
)

# Path prefixes that must never be written to or deleted
_WRITE_PROTECTED_PREFIXES: tuple[str, ...] = (
    "/etc/", "/bin/", "/sbin/", "/usr/", "/lib/", "/lib64/",
    "/boot/", "/snap/", "/var/lib/dpkg", "/var/lib/apt",
)

# Block-device write patterns (dd/redirect to raw disks)
_BLOCK_DEVICE_WRITE = re.compile(
    r"(of=|>\s*)/dev/(sd[a-z]|nvme\d|hd[a-z]|vd[a-z]|xvd[a-z]|mapper/)"
)

# Recursive rm pattern
_RM_RECURSIVE = re.compile(r"\brm\b\s+\S*-\S*[rR]\S*|\brm\b\s+--recursive\b")

# apt/dpkg mutation subcommands and flags — blocked unless package_mutation_enabled
_APT_MUTATION_SUBCOMMANDS: frozenset[str] = frozenset({
    "install", "remove", "purge", "upgrade", "full-upgrade", "autoremove",
})
_DPKG_MUTATION_FLAGS: frozenset[str] = frozenset({
    "-i", "--install", "-r", "--remove", "-p", "--purge",
})

# Write operators targeting protected paths
_WRITE_TO_PROTECTED = re.compile(
    r"(>>?\s*|tee\s+)(" + "|".join(re.escape(p) for p in _WRITE_PROTECTED_PREFIXES) + r")"
)
_DESTRUCTIVE_ON_PROTECTED = re.compile(
    r"\b(rm|mv|chmod|chown)\b\s+\S*\s+.*(" + "|".join(re.escape(p) for p in _WRITE_PROTECTED_PREFIXES) + r")"
    r"|" +
    r"\b(rm|mv|chmod|chown)\b\s+(" + "|".join(re.escape(p) for p in _WRITE_PROTECTED_PREFIXES) + r")"
)


def _split_stages(cmd: str) -> list[str]:
    """Split command into pipeline/semicolon stages for per-stage token checks."""
    return [s.strip() for s in re.split(r"[|;&]", cmd) if s.strip()]


def _effective_tokens(stage: str) -> list[str]:
    """Return the effective command token(s) of a pipeline stage, stripping sudo/env/time wrappers."""
    try:
        parts = shlex.split(stage, posix=False)
    except ValueError:
        parts = stage.split()
    # Strip common privilege/wrapper prefixes to get to the actual command
    _WRAPPERS = {"sudo", "env", "time", "doas", "sg", "nice", "ionice"}
    tokens = []
    i = 0
    while i < len(parts):
        tok = Path(parts[i].strip("\"'")).name.lower()
        tokens.append(tok)
        if tok in _WRAPPERS:
            i += 1  # continue to check next token too
        else:
            break
    return tokens


class CommandBlocked(Exception):
    """Raised when a command is rejected by the survival policy."""
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class AutonomousShellExecutor:
    """
    LLM-proposed command executor with survival policy enforcement.

    propose() is the public entry point: propose → risk check → execute → trace → learn.
    run_raw() enforces the same safety policy but skips trace/skill update (internal use).
    """

    def __init__(
        self,
        trace: "CognitiveTrace",
        memory: "SomaMemory",
        *,
        timeout_s: float = 30.0,
        max_output_chars: int = 12000,
        min_free_disk_gb: float = 5.0,
        max_memory_pct: float = 85.0,
        max_cpu_load: float = 6.0,
        package_mutation_enabled: bool = False,
    ) -> None:
        self._trace = trace
        self._memory = memory
        self.timeout_s = timeout_s
        self.max_output_chars = max_output_chars
        self.min_free_disk_gb = min_free_disk_gb
        self.max_memory_pct = max_memory_pct
        self.max_cpu_load = max_cpu_load
        self.package_mutation_enabled = package_mutation_enabled

    # ── public interface ──────────────────────────────────────────────────────

    def propose(
        self,
        cmd: str,
        *,
        reason: str = "",
        expected_effect: str = "",
        risk_level: str = "unknown",
    ) -> tuple[bool, str, str]:
        """
        Full pipeline: propose → risk check → execute → trace → learn.
        Returns (success, stdout, stderr).
        """
        self._trace.emit(
            "command_proposed",
            f"Proposed: {cmd[:120]}",
            inputs={"cmd": cmd[:200], "reason": reason[:200], "expected_effect": expected_effect[:200]},
            outputs={"risk_level": risk_level},
            level="info",
        )

        try:
            self._risk_check(cmd)
        except CommandBlocked as exc:
            self._trace.emit(
                "command_blocked",
                f"Blocked: {exc.reason[:200]}",
                inputs={"cmd": cmd[:200]},
                outputs={"reason": exc.reason},
                level="warning",
            )
            return False, "", f"BLOCKED: {exc.reason}"

        self._trace.emit(
            "command_risk_check",
            f"Risk check passed. Executing with timeout={self.timeout_s}s",
            inputs={"cmd": cmd[:120]},
            outputs={"timeout_s": self.timeout_s},
            level="info",
        )

        success, stdout, stderr = self._execute(cmd)

        self._trace.emit(
            "command_executed",
            f"{'OK' if success else 'FAIL'}: {cmd[:80]} → {(stdout or stderr)[:80]}",
            inputs={"cmd": cmd[:200]},
            outputs={"success": success, "stdout_chars": len(stdout), "stderr": stderr[:200]},
            level="info" if success else "warning",
        )

        if success:
            skill_key = self._skill_key(cmd)
            self._memory.confirm_capability(skill_key)
            self._trace.emit(
                "skill_learned",
                f"Skill confirmed: {skill_key}",
                outputs={"cmd": cmd[:100], "skill": skill_key},
                level="info",
            )

        return success, stdout, stderr

    def run_raw(self, cmd: str) -> tuple[bool, str, str]:
        """
        Safety-checked execution without trace or skill update.
        Used by hardware discovery and other internal callers.
        """
        try:
            self._risk_check(cmd)
        except CommandBlocked as exc:
            return False, "", f"BLOCKED: {exc.reason}"
        return self._execute(cmd)

    # ── survival policy ───────────────────────────────────────────────────────

    def _risk_check(self, cmd: str) -> None:
        """Raise CommandBlocked if the command violates the survival policy."""
        # 1. Fork bomb
        if ":(){ :|:" in cmd:
            raise CommandBlocked("fork bomb pattern detected")

        # 2. Always-blocked substrings
        for sub in _BLOCKED_SUBSTRINGS:
            if sub in cmd:
                raise CommandBlocked(f"forbidden content: '{sub}'")

        # 3. Forbidden command tokens in every pipeline stage (incl. after sudo)
        for stage in _split_stages(cmd):
            for tok in _effective_tokens(stage):
                if tok in _BLOCKED_TOKENS:
                    raise CommandBlocked(f"forbidden command: '{tok}'")
                if any(tok.startswith(pfx) for pfx in _BLOCKED_TOKEN_PREFIXES):
                    raise CommandBlocked(f"forbidden command variant: '{tok}'")

        # 4. Block-device write
        if _BLOCK_DEVICE_WRITE.search(cmd):
            raise CommandBlocked("write to block device is forbidden")

        # 5. Write or destructive ops on system paths
        if _WRITE_TO_PROTECTED.search(cmd):
            raise CommandBlocked("redirect/tee to write-protected system path")
        if _DESTRUCTIVE_ON_PROTECTED.search(cmd):
            raise CommandBlocked("destructive operation on write-protected system path")

        # 6. Recursive rm outside the repo
        if _RM_RECURSIVE.search(cmd):
            if not self._rm_confined_to_repo(cmd):
                raise CommandBlocked("recursive rm outside repo root is forbidden")

        # 7. apt/dpkg mutation gate
        if not self.package_mutation_enabled:
            self._check_package_mutation(cmd)

        # 8. Resource guard
        self._resource_guard()

    def _rm_confined_to_repo(self, cmd: str) -> bool:
        """Return True only if all rm targets resolve inside the repo."""
        try:
            parts = shlex.split(cmd)
        except ValueError:
            parts = cmd.split()
        # Skip "rm" and flags, collect path-like arguments
        paths = [
            p for p in parts[1:]
            if not p.startswith("-") and p not in ("rm",)
        ]
        if not paths:
            return False
        repo = str(_REPO_ROOT)
        for p in paths:
            try:
                if p.startswith("/"):
                    resolved = str(Path(p).resolve())
                else:
                    resolved = str((_REPO_ROOT / p).resolve())
                if not resolved.startswith(repo):
                    return False
            except Exception:
                return False
        return True

    def _check_package_mutation(self, cmd: str) -> None:
        """Block apt/dpkg mutations unless package_mutation_enabled."""
        _WRAPPERS = {"sudo", "env", "time", "doas", "sg", "nice", "ionice"}
        for stage in _split_stages(cmd):
            try:
                parts = shlex.split(stage, posix=False)
            except ValueError:
                parts = stage.split()
            # Skip privilege wrappers to reach the actual command
            i = 0
            while i < len(parts) and Path(parts[i].strip("\"'")).name.lower() in _WRAPPERS:
                i += 1
            if i >= len(parts):
                continue
            cmd_name = Path(parts[i].strip("\"'")).name.lower()
            rest = parts[i + 1:]
            if cmd_name in ("apt", "apt-get"):
                subcmd = next(
                    (p.strip("\"'").lower() for p in rest if not p.startswith("-")),
                    None,
                )
                if subcmd in _APT_MUTATION_SUBCOMMANDS:
                    raise CommandBlocked(
                        f"system package mutation blocked (SOMA_SYSTEM_PACKAGE_MUTATION=0): "
                        f"'{cmd_name} {subcmd}'"
                    )
            elif cmd_name == "dpkg":
                flags = {p.strip("\"'").lower() for p in rest if p.startswith("-")}
                blocked = flags & _DPKG_MUTATION_FLAGS
                if blocked:
                    raise CommandBlocked(
                        f"system package mutation blocked (SOMA_SYSTEM_PACKAGE_MUTATION=0): "
                        f"dpkg {' '.join(sorted(blocked))}"
                    )

    def _resource_guard(self) -> None:
        """Raise CommandBlocked if system resources are critically constrained."""
        try:
            disk = shutil.disk_usage("/home/funboy")
            free_gb = disk.free / (1024 ** 3)
            if free_gb < self.min_free_disk_gb:
                raise CommandBlocked(
                    f"disk space critical: {free_gb:.1f} GB free, minimum {self.min_free_disk_gb} GB"
                )
        except OSError:
            pass

        try:
            import psutil  # type: ignore
            mem = psutil.virtual_memory()
            if mem.percent > self.max_memory_pct:
                raise CommandBlocked(
                    f"memory pressure {mem.percent:.0f}% exceeds limit {self.max_memory_pct:.0f}%"
                )
            load1, _, _ = os.getloadavg()
            if load1 > self.max_cpu_load:
                raise CommandBlocked(
                    f"CPU load {load1:.1f} exceeds limit {self.max_cpu_load:.1f}"
                )
        except (ImportError, AttributeError, OSError):
            pass

    # ── execution ─────────────────────────────────────────────────────────────

    def _execute(self, cmd: str) -> tuple[bool, str, str]:
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=self.timeout_s,
                cwd=str(_REPO_ROOT),
                env={**os.environ, "LANG": "C", "LC_ALL": "C"},
            )
            stdout = result.stdout.strip()[: self.max_output_chars]
            stderr = result.stderr.strip()[:1024]
            return result.returncode == 0, stdout, stderr
        except subprocess.TimeoutExpired:
            return False, "", f"TIMEOUT after {self.timeout_s}s"
        except Exception as exc:
            return False, "", str(exc)[:256]

    def _skill_key(self, cmd: str) -> str:
        try:
            first = shlex.split(cmd)[0]
        except Exception:
            first = cmd.split()[0] if cmd.split() else cmd[:20]
        return Path(first).name[:40]
