#!/usr/bin/env python3
from __future__ import annotations

import os
import tempfile
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from soma_core.cpp_bridge import CppBridge


def check(name: str, condition: bool, detail: str = "") -> int:
    print(f"{'PASS' if condition else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    return 0 if condition else 1


def main() -> int:
    failures = 0
    with tempfile.TemporaryDirectory() as td:
        missing = CppBridge(binary_path=Path(td) / "latent_somatic")
        status = missing.detect_binary()
        failures += check("missing binary safe", status["status"] == "missing", str(status))
        dummy = Path(td) / "dummy_cpp.sh"
        dummy.write_text("#!/usr/bin/env bash\necho usage\nexit 0\n", encoding="utf-8")
        os.chmod(dummy, 0o755)
        bridge = CppBridge(binary_path=dummy)
        status2 = bridge.detect_binary()
        failures += check("existing dummy reports exists", status2["binary_exists"] is True and status2["status"] == "built", str(status2))
        smoke = bridge.smoke_test()
        failures += check("smoke does not crash", "status" in smoke and "smoke_ok" in smoke, str(smoke))
        bad = Path(td) / "bad_cpp.sh"
        bad.write_text("#!/usr/bin/env bash\nexit 1\n", encoding="utf-8")
        os.chmod(bad, 0o755)
        failed = CppBridge(binary_path=bad).smoke_test()
        failures += check("smoke failure safe", failed["status"] in {"failed", "model_required"}, str(failed))
    return failures


if __name__ == "__main__":
    sys.exit(main())
