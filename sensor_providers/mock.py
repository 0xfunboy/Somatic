from __future__ import annotations

import math
import random
import time

from .base import SensorProvider, clamp, normalize_snapshot, rounded

SCENARIOS = {
    "nominal": dict(
        volt=(11.4, 12.2),
        curr=(1800, 2200),
        tsi=(40, 55),
        tml=(36, 48),
        tmr=(36, 48),
        ax=(-0.2, 0.2),
        ay=(-0.2, 0.2),
        az=(-9.9, -9.7),
        gx=(-0.02, 0.02),
        gy=(-0.02, 0.02),
        gz=(-0.01, 0.01),
    ),
    "lowbatt": dict(
        volt=(10.0, 10.8),
        curr=(2800, 3400),
        tsi=(50, 65),
        tml=(45, 55),
        tmr=(45, 55),
        ax=(-0.1, 0.1),
        ay=(-0.1, 0.1),
        az=(-9.85, -9.75),
        gx=(-0.01, 0.01),
        gy=(-0.01, 0.01),
        gz=(-0.01, 0.01),
    ),
    "overheat": dict(
        volt=(11.6, 12.0),
        curr=(3500, 4500),
        tsi=(78, 90),
        tml=(70, 85),
        tmr=(68, 80),
        ax=(-0.1, 0.1),
        ay=(-0.1, 0.1),
        az=(-9.82, -9.78),
        gx=(-0.01, 0.01),
        gy=(-0.01, 0.01),
        gz=(-0.01, 0.01),
    ),
    "fall": dict(
        volt=(11.5, 12.1),
        curr=(1500, 2000),
        tsi=(42, 50),
        tml=(38, 46),
        tmr=(38, 46),
        ax=(-2.0, 2.0),
        ay=(3.0, 6.0),
        az=(-5.0, -2.0),
        gx=(1.5, 3.5),
        gy=(0.5, 1.5),
        gz=(-0.5, 0.5),
    ),
    "spin": dict(
        volt=(11.3, 11.9),
        curr=(2200, 3000),
        tsi=(50, 60),
        tml=(45, 55),
        tmr=(45, 55),
        ax=(-1.0, 1.0),
        ay=(-1.0, 1.0),
        az=(-9.9, -9.7),
        gx=(-0.1, 0.1),
        gy=(-0.1, 0.1),
        gz=(2.5, 4.5),
    ),
    "heavyload": dict(
        volt=(11.0, 11.5),
        curr=(4500, 6000),
        tsi=(65, 78),
        tml=(60, 75),
        tmr=(60, 75),
        ax=(-1.5, 1.5),
        ay=(-0.8, 0.8),
        az=(-9.9, -9.7),
        gx=(-0.1, 0.1),
        gy=(-0.2, 0.2),
        gz=(-0.05, 0.05),
    ),
    "cold": dict(
        volt=(11.9, 12.4),
        curr=(600, 1200),
        tsi=(10, 22),
        tml=(8, 18),
        tmr=(8, 18),
        ax=(-0.15, 0.15),
        ay=(-0.15, 0.15),
        az=(-9.88, -9.76),
        gx=(-0.03, 0.03),
        gy=(-0.03, 0.03),
        gz=(-0.02, 0.02),
    ),
}


def lerp(a: float, b: float, alpha: float) -> float:
    return a + (b - a) * alpha


def rnd(lo: float, hi: float) -> float:
    return lo + random.random() * (hi - lo)


class MockSensorProvider(SensorProvider):
    name = "mock"
    is_real = False

    def __init__(self):
        self.scenario = "nominal"
        self.t = 0.0
        self.last_read = time.monotonic()
        self.state = {
            "voltage": 11.8,
            "current_ma": 2000.0,
            "temp_si": 45.0,
            "temp_ml": 40.0,
            "temp_mr": 40.0,
            "ax": 0.0,
            "ay": 0.0,
            "az": -9.81,
            "gx": 0.0,
            "gy": 0.0,
            "gz": 0.0,
        }

    def supports_scenarios(self) -> bool:
        return True

    def set_scenario(self, scenario: str) -> bool:
        if scenario not in SCENARIOS:
            return False
        self.scenario = scenario
        return True

    def read(self) -> dict[str, object]:
        now = time.monotonic()
        dt = clamp(now - self.last_read, 0.02, 1.0)
        self.last_read = now
        self.t += dt

        c = SCENARIOS.get(self.scenario, SCENARIOS["nominal"])
        alpha = 0.04
        t_now = self.t
        s = self.state

        s["voltage"] = lerp(s["voltage"], rnd(*c["volt"]) + 0.15 * math.sin(t_now * 0.3), alpha)
        s["current_ma"] = lerp(s["current_ma"], rnd(*c["curr"]), alpha)
        s["temp_si"] = lerp(s["temp_si"], rnd(*c["tsi"]) + 2.0 * math.sin(t_now * 0.08), 0.02)
        s["temp_ml"] = lerp(s["temp_ml"], rnd(*c["tml"]) + math.sin(t_now * 0.07), 0.02)
        s["temp_mr"] = lerp(s["temp_mr"], rnd(*c["tmr"]) + math.cos(t_now * 0.07), 0.02)
        s["ax"] = lerp(s["ax"], rnd(*c["ax"]) + 0.3 * math.sin(t_now * 2.1), 0.08)
        s["ay"] = lerp(s["ay"], rnd(*c["ay"]) + 0.3 * math.cos(t_now * 1.9), 0.08)
        s["az"] = lerp(s["az"], rnd(*c["az"]) + 0.15 * math.sin(t_now * 0.5), 0.05)
        s["gx"] = lerp(s["gx"], rnd(*c["gx"]) + 0.01 * math.sin(t_now * 3.0), 0.06)
        s["gy"] = lerp(s["gy"], rnd(*c["gy"]) + 0.01 * math.cos(t_now * 2.8), 0.06)
        s["gz"] = lerp(s["gz"], rnd(*c["gz"]) + 0.005 * math.sin(t_now * 1.2), 0.06)

        return normalize_snapshot(
            {
                "core": {key: rounded(value, 3) for key, value in s.items()},
                "scenario": self.scenario,
                "system": {
                    "source_quality": 0.12,
                    "source_quality_label": "synthetic",
                },
                "raw": {"scenario": self.scenario},
            },
            provider=self.name,
            is_real=self.is_real,
            scenario=self.scenario,
        )
