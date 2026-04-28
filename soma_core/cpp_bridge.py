from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Any


class CppBridge:
    def __init__(
        self,
        *,
        enabled: bool = True,
        binary_path: str | Path = "/home/funboy/latent-somatic/build/latent_somatic",
        auto_build: bool = False,
        use_for_projection: bool = False,
    ) -> None:
        self.enabled = enabled
        self.binary_path = Path(binary_path)
        self.auto_build = auto_build
        self.use_for_projection = use_for_projection
        self._status: dict[str, Any] = {
            "enabled": enabled,
            "binary_exists": False,
            "smoke_ok": False,
            "active": False,
            "status": "missing",
            "last_checked_at": 0.0,
            "last_error": "",
        }

    def detect_binary(self) -> dict[str, Any]:
        exists = self.binary_path.exists()
        executable = os.access(self.binary_path, os.X_OK) if exists else False
        status = "built" if exists and executable else "missing"
        self._status.update({
            "binary_exists": exists,
            "executable": executable,
            "status": status,
            "last_checked_at": time.time(),
            "path": str(self.binary_path),
        })
        if not exists:
            self._status["last_error"] = "binary_missing"
        return dict(self._status)

    def build_if_requested(self) -> dict[str, Any]:
        if not self.auto_build:
            return dict(self._status)
        return self.detect_binary()

    def smoke_test(self) -> dict[str, Any]:
        detected = self.detect_binary()
        if not detected.get("binary_exists"):
            detected["smoke_ok"] = False
            detected["status"] = "missing"
            return detected
        try:
            result = subprocess.run(
                [str(self.binary_path), "--help"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            combined = (result.stdout or "") + (result.stderr or "")
            smoke_ok = result.returncode == 0 or "usage" in combined.lower() or "model" in combined.lower()
            self._status.update({
                "smoke_ok": smoke_ok,
                "status": "smoke_ok" if smoke_ok else "failed",
                "last_error": "" if smoke_ok else (combined.strip()[:300] or f"exit={result.returncode}"),
            })
            if "model" in combined.lower() and not smoke_ok:
                self._status["status"] = "model_required"
        except subprocess.TimeoutExpired:
            self._status.update({"smoke_ok": False, "status": "failed", "last_error": "timeout"})
        except Exception as exc:
            self._status.update({"smoke_ok": False, "status": "failed", "last_error": str(exc)[:300]})
        self._status["last_checked_at"] = time.time()
        return dict(self._status)

    def run_projection_once(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        status = self.status()
        if not self.use_for_projection:
            status["active"] = False
            return status
        status["active"] = bool(status.get("smoke_ok"))
        status["status"] = "active" if status["active"] else status.get("status", "failed")
        return status

    def status(self) -> dict[str, Any]:
        if not self._status.get("last_checked_at"):
            return self.detect_binary()
        return dict(self._status)
