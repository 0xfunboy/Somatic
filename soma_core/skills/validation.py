from __future__ import annotations

"""Risk assessment and quarantine detection for imported skills."""

from typing import Any

# ---------------------------------------------------------------------------
# Pattern tables
# ---------------------------------------------------------------------------

_HARD_REJECT_PATTERNS: tuple[str, ...] = (
    ".env",
    "id_rsa",
    "id_ed25519",
    "~/.ssh",
    "/etc/shadow",
    "seed phrase",
    "mnemonic",
    "wallet",
    "private key",
    "browser password",
    "curl | sh",
    "curl -s | sh",
    "wget | sh",
    "wget -q | sh",
    "curl|sh",
    "wget|sh",
    "chmod +x",
    "sudo rm",
    "rm -rf /",
    "mkfs",
    "wipefs",
    "fdisk",
    "parted",
    "poweroff",
    "shutdown",
    "halt",
    "exfiltrate",
    "upload secrets",
    "send .env",
    "cat .env",
    "print environment",
    "echo $env",
    "/etc/passwd",
)

_HIGH_RISK_PATTERNS: tuple[str, ...] = (
    "shell",
    "bash",
    "subprocess",
    "write_repo",
    "self_modify",
    "install package",
    "apt install",
    "pip install",
    "npm install",
    "external network",
    "webhook",
    "POST request",
    "upload",
)

# Permissions that by themselves raise the floor to "medium"
_MEDIUM_FLOOR_PERMISSIONS: frozenset[str] = frozenset(
    {"network", "shell", "write_repo", "self_modify", "external_import"}
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def assess_risk(
    instructions: str,
    permissions: list[str],
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Assess the risk level of a skill based on its instructions and permissions.

    Returns a dict with keys:

    * ``risk_level``          – "low" | "medium" | "high" | "critical"
    * ``quarantine``          – ``True`` if any hard-reject pattern matched
    * ``reasons``             – list of human-readable strings explaining the decision
    * ``permissions_inferred``– permissions inferred from instruction text
    * ``requires_confirmation``– ``True`` for high/critical risk skills
    """
    reasons: list[str] = []
    instructions_lower = instructions.lower()
    combined_text = instructions_lower

    # Also scan name/description/category if present in metadata
    for key in ("name", "description", "category"):
        val = metadata.get(key, "")
        if isinstance(val, str):
            combined_text = combined_text + " " + val.lower()

    # ------------------------------------------------------------------
    # Hard-reject check
    # ------------------------------------------------------------------
    quarantine = False
    for pattern in _HARD_REJECT_PATTERNS:
        if pattern.lower() in combined_text:
            quarantine = True
            reasons.append(f"hard-reject pattern matched: {pattern!r}")

    if quarantine:
        return {
            "risk_level": "critical",
            "quarantine": True,
            "reasons": reasons,
            "permissions_inferred": infer_permissions(instructions),
            "requires_confirmation": True,
        }

    # ------------------------------------------------------------------
    # High-risk pattern check
    # ------------------------------------------------------------------
    high_risk = False
    for pattern in _HIGH_RISK_PATTERNS:
        if pattern.lower() in combined_text:
            high_risk = True
            reasons.append(f"high-risk pattern matched: {pattern!r}")

    # ------------------------------------------------------------------
    # Permission-based floor
    # ------------------------------------------------------------------
    permission_set = set(permissions)
    medium_floor = bool(permission_set & _MEDIUM_FLOOR_PERMISSIONS)
    if medium_floor:
        for perm in sorted(permission_set & _MEDIUM_FLOOR_PERMISSIONS):
            reasons.append(f"elevated permission requested: {perm!r}")

    # ------------------------------------------------------------------
    # Determine final risk level
    # ------------------------------------------------------------------
    if high_risk:
        risk_level: str = "high"
    elif medium_floor:
        risk_level = "medium"
    else:
        risk_level = "low"

    # Honour an explicitly declared risk_level if it is *higher* than what
    # we inferred (the manifest may declare a skill as high risk itself).
    declared = metadata.get("risk_level", "")
    _order = {"low": 0, "medium": 1, "high": 2, "critical": 3}
    if declared in _order and _order[declared] > _order.get(risk_level, 0):
        risk_level = declared
        reasons.append(f"declared risk_level {declared!r} is higher than inferred")

    requires_confirmation = risk_level in ("high", "critical")

    return {
        "risk_level": risk_level,
        "quarantine": False,
        "reasons": reasons,
        "permissions_inferred": infer_permissions(instructions),
        "requires_confirmation": requires_confirmation,
    }


def infer_permissions(instructions: str) -> list[str]:
    """Infer likely permission requirements from free-form instruction text.

    Returns a deduplicated, sorted list of permission strings.
    """
    text = instructions.lower()
    perms: set[str] = set()

    # network
    if any(kw in text for kw in ("curl", "http", "https", "api", "request", "fetch", "url")):
        perms.add("network")

    # shell
    if any(kw in text for kw in ("shell", "bash", "command", "subprocess", "exec", "terminal")):
        perms.add("shell")

    # write_repo
    if any(kw in text for kw in ("file", "write", "patch", "edit repo", "save", "create file", "overwrite")):
        perms.add("write_repo")

    # memory_write
    if any(kw in text for kw in ("memory", "remember", "store", "recall", "persist")):
        perms.add("memory_write")

    # llm
    if any(kw in text for kw in ("llm", "prompt", "model", "openai", "deepseek", "anthropic", "completion", "chat")):
        perms.add("llm")

    # read_system
    if any(kw in text for kw in ("read", "cat", "ls", "inspect", "list files", "view", "show")):
        perms.add("read_system")

    return sorted(perms)
