from __future__ import annotations

import os

from .base import CORE_FIELDS, DEFAULT_SENSOR_STATE, DEFAULT_SYSTEM_STATE, SensorProvider
from .endpoint import EndpointSensorProvider
from .linux_system import LinuxSystemProvider
from .mock import MockSensorProvider


def create_provider(name: str | None = None) -> SensorProvider:
    provider_name = (name or os.getenv("SOMA_SENSOR_PROVIDER", "mock")).strip().lower()

    if provider_name == "mock":
        return MockSensorProvider()
    if provider_name == "linux":
        return LinuxSystemProvider()
    if provider_name == "endpoint":
        return EndpointSensorProvider(os.getenv("SOMA_SENSOR_ENDPOINT", ""))

    raise ValueError(
        f"Unsupported SOMA_SENSOR_PROVIDER={provider_name!r}. "
        "Use one of: mock, linux, endpoint."
    )


def create_sensor_provider(name: str | None = None) -> SensorProvider:
    return create_provider(name)


__all__ = [
    "CORE_FIELDS",
    "DEFAULT_SENSOR_STATE",
    "DEFAULT_SYSTEM_STATE",
    "SensorProvider",
    "MockSensorProvider",
    "LinuxSystemProvider",
    "EndpointSensorProvider",
    "create_provider",
    "create_sensor_provider",
]
