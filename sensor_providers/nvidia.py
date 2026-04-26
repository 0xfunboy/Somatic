from __future__ import annotations

import csv
import shutil
import subprocess
from io import StringIO

from .base import rounded


class NvidiaSMIProvider:
    def __init__(self):
        self.binary = shutil.which("nvidia-smi")

    def read(self) -> dict[str, float | None]:
        data = {
            "gpu_temp": None,
            "gpu_power_w": None,
            "gpu_util_percent": None,
            "gpu_memory_percent": None,
            "gpu_memory_used_mb": None,
            "gpu_memory_total_mb": None,
        }
        if not self.binary:
            return data

        query = ",".join(
            [
                "temperature.gpu",
                "utilization.gpu",
                "utilization.memory",
                "memory.used",
                "memory.total",
                "power.draw",
            ]
        )
        try:
            proc = subprocess.run(
                [self.binary, f"--query-gpu={query}", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=1.5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return data

        if proc.returncode != 0 or not proc.stdout.strip():
            return data

        try:
            rows = list(csv.reader(StringIO(proc.stdout.strip())))
        except csv.Error:
            return data

        if not rows:
            return data

        values = rows[0]
        if len(values) != 6:
            return data

        def maybe(value: str) -> float | None:
            value = value.strip()
            if not value or value.lower() == "n/a":
                return None
            try:
                return float(value)
            except ValueError:
                return None

        temp, util_gpu, util_mem, mem_used, mem_total, power = [maybe(item) for item in values]
        mem_pct = None
        if mem_used is not None and mem_total not in (None, 0):
            mem_pct = (mem_used / mem_total) * 100.0

        data["gpu_temp"] = rounded(temp, 2)
        data["gpu_power_w"] = rounded(power, 2)
        data["gpu_util_percent"] = rounded(util_gpu, 2)
        data["gpu_memory_percent"] = rounded(mem_pct, 2)
        data["gpu_memory_used_mb"] = rounded(mem_used, 2)
        data["gpu_memory_total_mb"] = rounded(mem_total, 2)
        return data
