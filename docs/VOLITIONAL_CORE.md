# VOLITIONAL SOMA CORE

## Architecture

The volitional core implements: body → drives → goals → policy → actions → reflection → memory → growth

### Modules (soma_core/)

| Module | Responsibility |
|---|---|
| `config.py` | Centralized env config, feature gates |
| `types.py` | All runtime typed dicts |
| `goals.py` | Persistent goal store, priority scoring |
| `memory.py` | Namespaced memory: self/body/operator/skills |
| `reflection.py` | Analytical reflection, baseline learning |
| `drives.py` | Drive intensity computation from real state |
| `policy.py` | Policy mode selection |
| `actions.py` | Formal action vocabulary, action selection |
| `growth.py` | Growth score and stage computation |
| `trace.py` | Observable cognitive trace generation |
| `llm_core.py` | LLM abstraction (openai_compatible/deepseek) |
| `mind.py` | SomaMind: main volitional tick loop |

## Feature Gates (defaults)

| Feature | Default | Env var |
|---|---|---|
| volition | ON | `SOMA_VOLITION` |
| cognitive_trace | ON | `SOMA_COGNITIVE_TRACE` |
| discovery | OFF | `SOMA_DISCOVERY` |
| capability_learning | OFF | `SOMA_CAPABILITY_LEARNING` |
| shell_exec | OFF | `SOMA_SHELL_EXEC` |
| self_modify | OFF | `SOMA_SELF_MODIFY` |
| cns_pulse | OFF | `SOMA_CNS_PULSE` |

## Tick Loop (SomaMind.tick)

1. perception → trace
2. body_model → trace
3. somatic_projection → trace
4. compute_drives → trace
5. update_goal_priorities (every N ticks)
6. select_active_goal
7. reflection_due check
8. select_policy
9. select_actions (silent + visible)
10. maybe_reflect (analytical baseline learning)
11. llm_status trace (every 10s)
12. compute_growth
13. return MindState dict

## Growth Stages

- `reflex_shell` — no real sensors
- `early_self_observation` — real sensors, no projector/LLM
- `body_model_learning` — building thermal/load baselines
- `goal_directed_behavior` — goals progressing measurably
- `expressive_embodiment` — avatar tied to internal state
- `autonomous_self_improvement` — sustained self-learning
- `cpp_embodied_runtime_ready` — ready for C++ daemon
