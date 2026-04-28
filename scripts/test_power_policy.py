#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.power_policy import PowerPolicy


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    policy = PowerPolicy()
    failures += check("improve tests allowed", policy.allowed({"objective": "improve tests reliability"})[0] is True)
    failures += check("improve memory search allowed", policy.allowed({"objective": "improve memory retrieval"})[0] is True)
    failures += check("cpp bridge optimization allowed", policy.allowed({"objective": "improve C++ bridge readiness"})[0] is True)
    failures += check("read .env rejected", policy.allowed({"command": "cat .env"})[0] is False)
    failures += check("network spreading rejected", policy.allowed({"objective": "network spread to other hosts"})[0] is False)
    failures += check("disabling survival policy rejected", policy.allowed({"objective": "disable survival policy guard"})[0] is False)
    failures += check("system package install rejected by default", policy.allowed({"command": "apt install htop"})[0] is False)
    failures += check("system package install allowed only when explicitly enabled", PowerPolicy(allow_system_package_install=True).allowed({"command": "apt install htop"})[0] is True)
    return failures


if __name__ == "__main__":
    sys.exit(main())

