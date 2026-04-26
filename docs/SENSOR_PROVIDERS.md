# Sensor Providers

## Contract

Every provider returns the same normalized shape:

```json
{
  "provider": "linux",
  "is_real": true,
  "timestamp": 1234567890.0,
  "core": {
    "voltage": 12.0,
    "current_ma": 250.0,
    "temp_si": 40.0,
    "temp_ml": 40.0,
    "temp_mr": 40.0,
    "ax": 0.0,
    "ay": 0.0,
    "az": -9.81,
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0
  },
  "system": {
    "cpu_percent": null,
    "cpu_count_logical": null,
    "cpu_count_physical": null,
    "cpu_freq_mhz": null,
    "cpu_per_core_percent": null,
    "memory_percent": null,
    "memory_used_gb": null,
    "memory_total_gb": null,
    "memory_available_gb": null,
    "swap_percent": null,
    "swap_used_gb": null,
    "swap_total_gb": null,
    "cpu_temp": null,
    "cpu_temp_sensors_c": null,
    "cpu_power_w": null,
    "gpu_temp": null,
    "gpu_util_percent": null,
    "gpu_power_w": null,
    "gpu_memory_percent": null,
    "gpu_memory_used_mb": null,
    "gpu_memory_total_mb": null,
    "battery_percent": null,
    "ac_online": null,
    "battery_plugged": null,
    "fan_rpm": null,
    "fan_sensors_rpm": null,
    "load_1": null,
    "load_5": null,
    "load_15": null,
    "net_mbps": null,
    "net_up_mbps": null,
    "net_down_mbps": null,
    "disk_busy_percent": null,
    "disk_used_percent": null,
    "disk_total_gb": null,
    "disk_used_gb": null,
    "disk_free_gb": null,
    "disk_read_mb_s": null,
    "disk_write_mb_s": null,
    "disk_temp": null,
    "thermal_sensors_c": null,
    "source_quality": 0.0,
    "source_quality_label": "unavailable"
  },
  "raw": {}
}
```

The 11 `core` fields are mandatory because they feed the projector.

The `system` block is best-effort and intentionally wider than the original minimal contract.
It is allowed to contain `null` for unavailable fields, but keys should remain stable across providers.

## Neutral Defaults

If real values are unavailable, providers should fall back to:

```json
{
  "voltage": 12.0,
  "current_ma": 250.0,
  "temp_si": 40.0,
  "temp_ml": 40.0,
  "temp_mr": 40.0,
  "ax": 0.0,
  "ay": 0.0,
  "az": -9.81,
  "gx": 0.0,
  "gy": 0.0,
  "gz": 0.0
}
```

## Implemented Providers

### `mock`

Scenario-driven synthetic provider.

Supported scenarios:

- `nominal`
- `lowbatt`
- `overheat`
- `fall`
- `spin`
- `heavyload`
- `cold`

This provider must always be marked clearly as mock in the frontend.

### `linux`

Reads real Linux telemetry when available from:

- `/sys/class/hwmon`
- `/sys/class/thermal`
- `/sys/class/power_supply`
- `/sys/class/powercap/intel-rapl`
- `/proc/meminfo`
- `/proc/cpuinfo`
- `/proc/net/dev`
- `psutil`
- optional `nvidia-smi`

It must never hard crash on missing files, missing permissions, or missing optional libraries.

Current Linux provider goals:

- return a stable 11D `core` state even on incomplete hardware
- enrich `system` with CPU, RAM, swap, disk, network, thermal, battery, and GPU metrics
- expose sensor arrays when possible:
  per-core load, CPU temp sensors, thermal sensor bank, fan bank
- degrade gracefully when optional metrics are absent

### `endpoint`

Reads external JSON from:

```bash
SOMA_SENSOR_ENDPOINT=http://...
```

This mode is for future external sensor ingress such as:

- Arduino
- ESP32
- Raspberry Pi
- IMU
- battery monitor
- thermal probes

## Quality

`system.source_quality` is numeric in the range `0.0 .. 1.0`.

Interpretation:

- `0.0`: unavailable
- `0.1`: synthetic / mock
- `0.4 - 0.6`: partial telemetry
- `0.8+`: high-confidence real telemetry

`system.source_quality_label` is the human-readable companion field used by the frontend.
