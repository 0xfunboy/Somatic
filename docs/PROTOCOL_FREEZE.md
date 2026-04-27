# SOMA WEBSOCKET PROTOCOL — FROZEN SCHEMA

Version: 5.5
Backend: Python (server.py + soma_core)
Future: C++ soma_daemon (same schema)

## Tick payload (`type: "tick"`)

```json
{
  "type": "tick",
  "timestamp": 0.0,
  "provider": {"name": "linux", "is_real": true, "source_quality": 0.8},
  "sensors": {"voltage": 12.0, "current_ma": 500.0, "temp_si": 42.0},
  "system": {"cpu_percent": 25.0, "cpu_temp": 45.0, "memory_percent": 55.0},
  "derived": {"thermal_stress": 0.1, "energy_stress": 0.05, "instability": 0.02, "comfort": 0.9},
  "projector": {"available": false, "mode": "analytic", "norm": 0.0},
  "affect": {"heat": 0.1, "cold": 0.0, "energy_low": 0.0, "fatigue": 0.1, "curiosity": 0.5},
  "homeostasis": {"dominant": [{"name": "self_knowledge", "intensity": 0.6}]},
  "policy": {"mode": "observe_and_learn", "urgency": 0.2},
  "llm": {"available": false, "mode": "off"},
  "drives": {"self_knowledge": 0.6, "caution": 0.4, "dominant": "self_knowledge"},
  "mind": {
    "volition_enabled": true,
    "active_goal_id": "understand_own_body",
    "active_goal_title": "Understand my machine body",
    "active_goal_progress": 0.12,
    "dominant_drive": "self_knowledge",
    "policy_mode": "observe_and_learn",
    "silent_actions": ["observe", "track_thermal_baseline"],
    "visible_action": "curious_focus",
    "last_reflection_at": 0.0,
    "last_learned": "",
    "llm_live": false,
    "growth": {"growth_score": 0.05, "stage": "early_self_observation"}
  },
  "growth": {"growth_score": 0.05, "stage": "early_self_observation"},
  "trace": [{"timestamp": 0.0, "phase": "perception", "summary": "...", "level": "info"}]
}
```

## Chat request (`type: "chat"`)
```json
{"type": "chat", "text": "user message"}
```

## Chat reply (`type: "chat_reply"`)
```json
{
  "type": "chat_reply",
  "text": "Soma response",
  "llm": {"available": false, "mode": "fallback"},
  "mind": {}, "growth": {}, "trace": []
}
```

## Autonomous event (`type: "autonomous_event"`)
```json
{
  "type": "autonomous_event",
  "text": "I have learned a new baseline.",
  "event": "body_pattern_learned",
  "affect": {}, "actions": [], "mind": {}, "growth": {}, "trace": []
}
```

## Rules
- All float values rounded to 3 decimal places
- All IDs are stable string keys
- No private LLM chain-of-thought in any payload
- `trace` contains only observable runtime trace events
- Future C++ daemon must emit identical schema
