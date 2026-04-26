# WebSocket Protocol

The frontend must not depend on Python-specific internals.

The protocol is designed so that the current Python runtime and a future C++ daemon can emit the same payload family.

## Message Types

- `init`
- `tick`
- `chat`
- `chat_reply`
- `autonomous_event`

## Tick

Server -> browser:

```json
{
  "type": "tick",
  "timestamp": 1234567890.0,
  "provider": {
    "name": "linux",
    "is_real": true,
    "source_quality": 0.72
  },
  "sensors": {
    "voltage": 12.0,
    "current_ma": 250.0,
    "temp_si": 57.0,
    "temp_ml": 45.0,
    "temp_mr": 44.0,
    "ax": 0.0,
    "ay": 0.0,
    "az": -9.81,
    "gx": 0.0,
    "gy": 0.0,
    "gz": 0.0
  },
  "system": {
    "cpu_percent": 34.0,
    "cpu_count_logical": 16,
    "cpu_count_physical": 8,
    "cpu_freq_mhz": 4450.0,
    "cpu_per_core_percent": [18.0, 29.0, 25.0, 31.0],
    "memory_percent": 61.2,
    "memory_used_gb": 19.1,
    "memory_total_gb": 31.2,
    "memory_available_gb": 12.1,
    "swap_percent": 8.0,
    "cpu_temp": 57.0,
    "cpu_temp_sensors_c": [57.0, 53.0, 51.0],
    "cpu_power_w": 38.5,
    "disk_used_percent": 54.2,
    "disk_busy_percent": 12.4,
    "disk_read_mb_s": 44.8,
    "disk_write_mb_s": 13.2,
    "disk_temp": 42.0,
    "net_down_mbps": 18.7,
    "net_up_mbps": 4.3,
    "gpu_temp": null,
    "gpu_util_percent": null,
    "gpu_power_w": null,
    "gpu_memory_percent": null,
    "battery_percent": null,
    "ac_online": null,
    "fan_rpm": null,
    "fan_sensors_rpm": null,
    "thermal_sensors_c": [57.0, 42.0],
    "source_quality": 0.72,
    "source_quality_label": "partial"
  },
  "derived": {
    "thermal_stress": 0.4,
    "energy_stress": 0.2,
    "instability": 0.0,
    "comfort": 0.7,
    "fatigue": 0.22,
    "curiosity": 0.61,
    "cold": 0.0
  },
  "projector": {
    "available": true,
    "mode": "torchscript",
    "dim": 4096,
    "norm": 10.2,
    "top_dims": [1, 22, 303],
    "top_vals": [0.8, -0.6, 0.4],
    "machine_fusion_enabled": true,
    "machine_fusion_gain": 1.0,
    "machine_vector_norm": 4.3,
    "machine_fusion_mode": "learned",
    "machine_fusion_delta_norm": 3.02
  },
  "machine_vector": {
    "dim": 128,
    "norm": 4.3,
    "preview": [0.11, -0.03, 0.07],
    "vector": [0.11, -0.03, 0.07],
    "top_features": [["memory_percent", 0.612], ["cpu_temp", 0.57]],
    "features": {
      "cpu_percent": 0.34,
      "memory_percent": 0.612
    }
  },
  "homeostasis": {
    "drives": {
      "cooling": 0.4,
      "energy_recovery": 0.2,
      "stability": 0.0,
      "rest": 0.22,
      "warmth": 0.0,
      "exploration": 0.61
    },
    "dominant": [
      {"name": "exploration", "intensity": 0.61},
      {"name": "cooling", "intensity": 0.4},
      {"name": "rest", "intensity": 0.22}
    ]
  },
  "policy": {
    "mode": "explore",
    "dominant_drive": "exploration",
    "goals": ["sample_environment", "maintain_dialogue", "expand_memory_trace"],
    "target_hz": 5.0,
    "speech_profile": "expressive",
    "risk": 0.35,
    "comfort": 0.70
  },
  "actuation": {
    "enabled": true,
    "transport": "file",
    "policy_mode": "explore",
    "commands": [
      {"channel": "posture", "value": "attend_user"},
      {"channel": "fan_target", "value": 0.15},
      {"channel": "compute_governor", "value": "performance"}
    ]
  },
  "llm": {
    "available": false,
    "mode": "fallback",
    "provider": "fallback",
    "model": null
  },
  "affect": {
    "cold": 0.0,
    "heat": 0.4,
    "energy_low": 0.2,
    "fatigue": 0.22,
    "instability": 0.0,
    "curiosity": 0.61
  },
  "actions": [
    {
      "type": "animation",
      "name": "attend_user",
      "intensity": 0.61
    }
  ]
}
```

`init`, `tick`, `chat_reply`, and `autonomous_event` all carry the same base family:

- `provider`
- `sensors`
- `system`
- `derived`
- `projector`
- `machine_vector`
- `homeostasis`
- `policy`
- `actuation`
- `llm`
- `affect`
- `actions`

## Chat Request

Browser -> server:

```json
{
  "type": "chat",
  "text": "What are you feeling?"
}
```

## Chat Reply

Server -> browser:

```json
{
  "type": "chat_reply",
  "text": "I feel warm but stable.",
  "llm": {
    "available": true,
    "mode": "deepseek",
    "provider": "deepseek",
    "model": "gemini-web",
    "latency_ms": 432.1
  },
  "affect": {
    "cold": 0.0,
    "heat": 0.6,
    "energy_low": 0.1,
    "fatigue": 0.2,
    "instability": 0.0,
    "curiosity": 0.7
  },
  "actions": [
    {
      "type": "animation",
      "name": "warm_idle",
      "intensity": 0.6
    }
  ]
}
```

The reply also carries the same `provider`, `sensors`, `system`, `derived`, and `projector` payload family as `tick`.

If the remote model returns malformed JSON but still returns text, the server may recover speech while marking the LLM state as fallback/recovered.

## Autonomous Event

Server -> browser:

```json
{
  "type": "autonomous_event",
  "event": "thermal_rise",
  "text": "Thermal stress rising. I am redirecting attention toward cooling.",
  "affect": {
    "cold": 0.0,
    "heat": 0.78,
    "energy_low": 0.21,
    "fatigue": 0.55,
    "instability": 0.03,
    "curiosity": 0.42
  },
  "actions": [
    {
      "type": "animation",
      "name": "warm_idle",
      "intensity": 0.78
    }
  ]
}
```

Autonomous events are event-based, not periodic spam.
