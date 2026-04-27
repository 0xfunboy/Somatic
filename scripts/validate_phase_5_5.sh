#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== Soma Phase 5.5 Validation ==="
echo ""

echo "[1] Python syntax checks..."
python3 -m py_compile server.py
for f in soma_core/*.py; do python3 -m py_compile "$f"; done
for f in sensor_providers/*.py; do python3 -m py_compile "$f" 2>/dev/null || true; done
echo "    PASS"

echo "[2] Import checks..."
python3 -c "
from soma_core import CFG, GoalStore, SomaMemory, ReflectionEngine, SomaMind
from soma_core.drives import compute_drives
from soma_core.policy import select_policy
from soma_core.actions import select_actions
from soma_core.growth import compute_growth
from soma_core.trace import CognitiveTrace
from soma_core.llm_core import call_llm
print('  All soma_core imports: OK')
"

echo "[3] Feature gate defaults..."
python3 -c "
from soma_core.config import CFG
assert not CFG.discovery_enabled, 'discovery must be off by default'
assert not CFG.capability_learning_enabled, 'capability_learning must be off by default'
assert not CFG.shell_exec_enabled, 'shell_exec must be off by default'
assert not CFG.self_modify_enabled, 'self_modify must be off by default'
assert not CFG.cns_pulse_enabled, 'cns_pulse must be off by default'
assert CFG.volition_enabled, 'volition must be on by default'
assert CFG.cognitive_trace_enabled, 'cognitive_trace must be on by default'
print('  All gates: OK')
"

echo "[4] Data files..."
REQUIRED=(
  "data/mind/self_model.json"
  "data/mind/goals.json"
  "data/mind/reflections.jsonl"
  "data/mind/cognitive_trace.jsonl"
  "data/mind/body_memory.jsonl"
  "data/mind/operator_memory.jsonl"
)
for f in "${REQUIRED[@]}"; do
  if [ -f "$f" ]; then
    echo "    EXIST: $f"
  else
    echo "    MISSING: $f"
    exit 1
  fi
done

echo "[5] Docs..."
DOCS=(
  "docs/simulator.html"
  "docs/DEVELOPMENT_TODO.md"
)
for f in "${DOCS[@]}"; do
  [ -f "$f" ] && echo "    EXIST: $f" || echo "    MISSING: $f"
done

echo "[6] Volitional loop smoke test..."
python3 -c "
import time
from soma_core.goals import GoalStore
from soma_core.memory import SomaMemory
from soma_core.reflection import ReflectionEngine
from soma_core.mind import SomaMind

m = SomaMemory(); g = GoalStore(); r = ReflectionEngine(m, g)
mind = SomaMind(g, m, r)

snap = {
    'timestamp': time.time(), 'scenario': 'nominal',
    'provider': {'name': 'test', 'is_real': True, 'source_quality': 0.8},
    'sensors': {'temp_si':42.,'voltage':12.,'current_ma':500.,'temp_ml':38.,'temp_mr':39.,
                'ax':0.,'ay':0.,'az':9.8,'gx':0.,'gy':0.,'gz':0.},
    'system': {'cpu_percent':25.,'cpu_temp':45.,'memory_percent':55.,'source_quality':0.8,
               'cpu_power_w':None,'gpu_util_percent':None,'battery_percent':None,'ac_online':None},
    'affect': {'cold':0.1,'heat':0.2,'energy_low':0.1,'fatigue':0.15,
               'instability':0.05,'curiosity':0.6,'knowledge_gap':0.4},
    'homeostasis': {'drives':{},'dominant':[{'name':'self_knowledge','intensity':0.6}],
                    'stability_margin':0.95,'thermal_margin':0.9,'energy_margin':0.95,
                    'power_source':'ac','body_orientation':'upright'},
    'policy': {'mode':'nominal'},'llm': {'available':False,'mode':'off'},
    'derived': {'thermal_stress':0.1,'energy_stress':0.05,'instability':0.05,'comfort':0.9},
    'machine_vector': [],'projector': {'available':False,'mode':'analytic','norm':0.,'top_dims':[],'top_vals':[]},
    'actuation': {},'summary': 'nominal',
    'tensor': {'heatmap':[],'norm':0.,'mean':0.,'std':1.,'top_dims':[],'top_vals':[],'seg_energy':[],'projector_ms':0.}
}

ms = mind.tick(snap)
assert ms['volition_enabled'], 'volition must be enabled'
assert ms['active_goal_id'], 'must have an active goal'
assert 'drives' in ms, 'must have drives'
assert 'growth' in ms, 'must have growth'
assert 'trace' in ms, 'must have trace'
print(f'  Mind tick: OK — goal={ms[\"active_goal_id\"]} policy={ms[\"policy_mode\"]} stage={ms[\"growth\"][\"stage\"]}')
"

echo ""
echo "=== ALL CHECKS PASSED ==="
