# AVATAR ACTIONS

## Action schema

```json
{
  "type": "avatar|silent|speech",
  "name": "action_name",
  "intensity": 0.5,
  "reason": "brief causal explanation",
  "visible": true,
  "target": "avatar|internal|memory|goals|system",
  "duration_ms": 3000
}
```

## Silent (internal) actions

| Name | Trigger | Effect |
|---|---|---|
| `observe` | Always | Continuous somatic observation |
| `reflect_silently` | Policy=reflection | Reflection cycle |
| `store_memory` | After learning | Write to memory |
| `update_goal` | Drive active | Update goal evidence |
| `update_self_model` | After reflection | Write self_model.json |
| `change_attention` | Drive shift | Redirect attention |
| `reduce_tick_rate` | Thermal/energy stress | Slow tick rate |
| `increase_tick_rate` | Curiosity high | Speed up tick rate |
| `mark_uncertainty` | Knowledge gap | Log uncertainty |
| `track_thermal_baseline` | Observe mode | Accumulate temp history |
| `track_load_baseline` | Observe mode | Accumulate CPU history |
| `track_disk_baseline` | Observe mode | Accumulate disk history |

## Visible (avatar) actions

| Name | Trigger affect | CSS/animation hint |
|---|---|---|
| `neutral_idle` | Default | Slow pulse, neutral glow |
| `attend_user` | User present | Alert posture, cyan glow |
| `cold_closed` | cold ≥ 0.60 | Contracted, dim blue |
| `heat_open` | heat ≥ 0.65 | Expanded, warm orange glow |
| `fatigue_slow` | fatigue ≥ 0.65 | Slow motion, dim |
| `instability_corrective` | instability ≥ 0.55 | Corrective micro-motion |
| `low_power_still` | energy_low ≥ 0.60 | Minimal animation, green dim |
| `curious_focus` | curiosity ≥ 0.55 | Alert, sharp cyan |
| `discomfort_shift` | Compound discomfort | Shift posture |
| `relief_soften` | Stress resolved | Soften glow, relax |
| `thinking_idle` | Policy=reflection | Slow breathing pulse |
