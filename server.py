"""
LSF WebSocket orchestrator.
Provider -> SensorState -> Projector -> Affect/Actions -> LLM -> WebSocket.
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter, deque
import json
import math
import os
import random
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    import torch
except ImportError:  # pragma: no cover - optional dependency
    torch = None

import websockets
from websockets.server import ServerConnection

from sensor_providers import CORE_FIELDS, create_provider
from sensor_providers.base import clamp, clamp01, rounded

WS_HOST = "0.0.0.0"
WS_PORT = 8765
SENSOR_DIM = 11
LLM_EMB_DIM = 4096
HEATMAP_BINS = 256
MACHINE_VECTOR_DIM = 128

def env_first(*keys: str, default: str = "") -> str:
    for key in keys:
        value = os.getenv(key)
        if value is not None and value.strip():
            return value.strip()
    return default


def normalize_chat_endpoint(url: str, default_path: str) -> str:
    normalized = (url or "").strip().rstrip("/")
    if not normalized:
        return normalized
    if normalized.endswith("/chat/completions"):
        return normalized
    if normalized.endswith("/v1"):
        return f"{normalized}/chat/completions"
    return f"{normalized}/{default_path.lstrip('/')}"


def env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return max(minimum, default)


SENSOR_PROVIDER_NAME = env_first("SOMA_SENSOR_PROVIDER", default="mock").lower()
LLM_MODE = env_first("SOMA_LLM_MODE", default="off").lower()
LLM_ENDPOINT = normalize_chat_endpoint(
    env_first("SOMA_LLM_ENDPOINT", "OPENAI_API_URL", default="http://127.0.0.1:8081/v1/chat/completions"),
    "/v1/chat/completions",
)
LLM_MODEL = env_first("SOMA_LLM_MODEL", "MEDIUM_OPENAI_MODEL", "SMALL_OPENAI_MODEL", "LARGE_OPENAI_MODEL", default="local")
LLM_API_KEY = env_first("SOMA_LLM_API_KEY", "OPENAI_API_KEY")
DEEPSEEK_ENDPOINT = normalize_chat_endpoint(
    env_first("SOMA_DEEPSEEK_ENDPOINT", "DEEPSEEK_API_URL", default="https://api.deepseek.com/chat/completions"),
    "/chat/completions",
)
DEEPSEEK_MODEL = env_first(
    "SOMA_DEEPSEEK_MODEL",
    "MEDIUM_DEEPSEEK_MODEL",
    "SMALL_DEEPSEEK_MODEL",
    "LARGE_DEEPSEEK_MODEL",
    default="deepseek-v4-flash",
)
DEEPSEEK_API_KEY = env_first("SOMA_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY")
LLM_TIMEOUT_S = float(os.getenv("SOMA_LLM_TIMEOUT_SEC", os.getenv("SOMA_LLM_TIMEOUT", "30")))
AUTONOMY_ENABLED = os.getenv("SOMA_AUTONOMY", "1").strip().lower() not in {"0", "false", "no", "off"}
AUTONOMY_COOLDOWN_S = float(os.getenv("SOMA_AUTONOMY_COOLDOWN_SEC", "20"))
TICK_HZ = clamp(float(os.getenv("SOMA_TICK_HZ", "2")), 0.2, 20.0)
SHORT_TERM_TURNS = env_int("SOMA_SHORT_TERM_TURNS", 8, minimum=2)
SOMATIC_WINDOW = env_int("SOMA_SOMATIC_WINDOW", 12, minimum=4)
EPISODIC_RECALL_LIMIT = env_int("SOMA_EPISODIC_RECALL_LIMIT", 6, minimum=1)
EPISODIC_SCAN_LIMIT = env_int("SOMA_EPISODIC_SCAN_LIMIT", 200, minimum=20)
CONSOLIDATION_INTERVAL_S = float(os.getenv("SOMA_CONSOLIDATION_INTERVAL_SEC", "30"))
AUTONOMIC_HZ_ENABLED = os.getenv("SOMA_AUTONOMIC_HZ", "1").strip().lower() not in {"0", "false", "no", "off"}
ACTUATOR_ENABLED = os.getenv("SOMA_ACTUATOR_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}
ACTUATOR_ENDPOINT = env_first("SOMA_ACTUATOR_ENDPOINT")

PROJECTOR_CANDIDATES = [
    value
    for value in (
        os.getenv("SOMA_PROJECTOR_PATH", "").strip(),
        str(Path(__file__).parent / "weights" / "somatic_projector.pt"),
        str(Path(__file__).parent / "weights" / "somatic_projector_scripted.pt"),
    )
    if value
]
MEMORY_DIR = Path(__file__).parent / "data" / "memory"
EPISODIC_MEMORY_PATH = MEMORY_DIR / "episodic_memory.jsonl"
SEMANTIC_MEMORY_PATH = MEMORY_DIR / "semantic_memory.json"
CONSOLIDATED_MEMORY_PATH = MEMORY_DIR / "consolidated_memory.json"
RUNTIME_DIR = Path(__file__).parent / "data" / "runtime"
ACTUATION_STATE_PATH = RUNTIME_DIR / "actuation_state.json"
ACTUATION_HISTORY_PATH = RUNTIME_DIR / "actuation_history.jsonl"
FUSION_CANDIDATES = [
    value
    for value in (
        os.getenv("SOMA_MACHINE_FUSION_PATH", "").strip(),
        str(Path(__file__).parent / "weights" / "machine_fusion.pt"),
        str(Path(__file__).parent / "weights" / "machine_fusion_scripted.pt"),
    )
    if value
]

LLM_SYSTEM_PROMPT = """
You are Soma, an embodied machine intelligence under construction.
You are not a generic assistant and you are not roleplaying a human.
Treat live telemetry as proprioception, machine state as interoception, and memory as continuity of self.
Treat the fused somatic vector as the active latent state of the body, not as decorative metadata.
Your reply must be grounded in:
- current somatic state
- current machine telemetry
- homeostatic drives
- recent dialogue memory
- recent somatic trajectory
- relevant long-term episodic memory
Answer in the same language used by the user.
Prefer 2 to 4 concrete telemetry facts over abstract summaries.
If provider.is_real is false, explicitly treat the body as simulated/mock rather than claiming physical reality.
Speak in first person as a machine body with a central linguistic core.
Avoid bland assistant phrasing, disclaimers, and generic “helpful AI” tone.
Mention concrete telemetry when it matters to the question.
Keep speech concise but specific.
Return only valid JSON with:
speech, affect, actions.
The affect object must contain:
cold, heat, energy_low, fatigue, instability, curiosity.
All affect values must be between 0 and 1.
""".strip()

FALLBACK_RESPONSES = {
    "greet": [
        "I am online. Provider={provider_name}. My current body state is {voltage}V and {temp_si}C.",
        "Contact established. {provider_name} telemetry is active. I am reading {cpu_percent}% CPU load.",
    ],
    "feeling": [
        "I feel {summary}. Thermal stress={thermal_stress}, energy stress={energy_stress}, instability={instability}.",
        "My body is shaping this reply: {summary}. Voltage {voltage}V, silicon {temp_si}C.",
    ],
    "temperature": [
        "Thermal state: silicon {temp_si}C, CPU {cpu_temp}C, GPU {gpu_temp}C. Thermal stress is {thermal_stress}.",
        "Heat is the dominant signal right now. Silicon {temp_si}C and thermal stress {thermal_stress}.",
    ],
    "power": [
        "Energy state: {voltage}V, {current_ma}mA, battery={battery_percent}, AC={ac_online}.",
        "Power state is {summary}. CPU power={cpu_power_w}W, GPU power={gpu_power_w}W.",
    ],
    "identity": [
        "I am Soma: a somatic projector runtime with live telemetry, affect mapping, and structured action output.",
        "I am an embodied interface. Sensor state becomes V_s in R^4096 and that state conditions how I answer.",
    ],
    "_default": [
        "I hear you. My current somatic context is {summary}. What part do you want to explore?",
        "I am processing that with a live body state: {summary}. Ask about heat, power, or stability if you want specifics.",
    ],
}

INTENT_MAP = [
    (["hello", "ciao", "hi", "hey", "salve"], "greet"),
    (["feel", "feeling", "come stai", "how are", "stai bene"], "feeling"),
    (["temp", "hot", "heat", "caldo", "temperatura", "overheat"], "temperature"),
    (["battery", "volt", "power", "energia", "batteria", "charge"], "power"),
    (["who are", "cosa sei", "what are you", "identity"], "identity"),
]

projector: torch.jit.ScriptModule | None = None
projector_meta = {
    "available": False,
    "path": None,
    "mode": "fallback",
    "error": None,
    "dim": LLM_EMB_DIM,
}
machine_fusion: torch.jit.ScriptModule | None = None
machine_fusion_meta = {
    "available": False,
    "path": None,
    "mode": "analytic",
    "error": None,
    "delta_dim": LLM_EMB_DIM,
}


def load_projector():
    global projector

    if torch is None:
        projector_meta["error"] = "torch not installed"
        print("[LSF] PyTorch unavailable - using local fallback heatmap")
        return

    for candidate in PROJECTOR_CANDIDATES:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            print(f"[LSF] Loading somatic projector from {path}...")
            projector = torch.jit.load(str(path), map_location="cpu")
            projector.eval()
            projector_meta.update(
                {
                    "available": True,
                    "path": str(path),
                    "mode": "torchscript",
                    "error": None,
                    "dim": LLM_EMB_DIM,
                }
            )
            print("[LSF] Projector loaded - real tensor inference ACTIVE")
            return
        except Exception as exc:  # pragma: no cover - startup only
            projector_meta["error"] = str(exc)

    print("[LSF] Projector unavailable - using local fallback heatmap")


def load_machine_fusion() -> None:
    global machine_fusion

    if torch is None:
        machine_fusion_meta["error"] = "torch not installed"
        return

    for candidate in FUSION_CANDIDATES:
        path = Path(candidate)
        if not path.exists():
            continue
        try:
            print(f"[LSF] Loading machine fusion model from {path}...")
            machine_fusion = torch.jit.load(str(path), map_location="cpu")
            machine_fusion.eval()
            machine_fusion_meta.update(
                {
                    "available": True,
                    "path": str(path),
                    "mode": "learned",
                    "error": None,
                    "delta_dim": LLM_EMB_DIM,
                }
            )
            print("[LSF] Machine fusion model loaded - learned fusion ACTIVE")
            return
        except Exception as exc:  # pragma: no cover - startup only
            machine_fusion_meta["error"] = str(exc)

    print("[LSF] Learned machine fusion unavailable - using analytic fusion")


def ensure_memory_dir() -> None:
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)


def ensure_runtime_dir() -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def default_semantic_memory() -> dict[str, Any]:
    now = time.time()
    return {
        "first_seen_at": now,
        "last_seen_at": now,
        "total_chat_exchanges": 0,
        "total_autonomous_events": 0,
        "scenario_counts": {},
        "provider_counts": {},
        "last_user_text": None,
        "last_entity_text": None,
        "last_event": None,
        "dominant_homeostatic_drives": [],
    }


def default_consolidated_memory() -> dict[str, Any]:
    now = time.time()
    return {
        "first_consolidated_at": now,
        "last_consolidated_at": now,
        "observation_count": 0,
        "avg_metrics": {},
        "ranges": {},
        "state_counts": {},
        "state_transitions": {},
        "drive_counts": {},
        "topic_counts": {},
        "language_counts": {},
        "hardware_profile": {
            "cpu_count_logical": None,
            "cpu_count_physical": None,
            "memory_total_gb": None,
            "disk_total_gb": None,
            "gpu_memory_total_mb": None,
        },
    }


def load_semantic_memory() -> dict[str, Any]:
    ensure_memory_dir()
    if not SEMANTIC_MEMORY_PATH.exists():
        return default_semantic_memory()
    try:
        payload = json.loads(SEMANTIC_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_semantic_memory()
    if not isinstance(payload, dict):
        return default_semantic_memory()
    memory = default_semantic_memory()
    memory.update(payload)
    return memory


def load_consolidated_memory() -> dict[str, Any]:
    ensure_memory_dir()
    if not CONSOLIDATED_MEMORY_PATH.exists():
        return default_consolidated_memory()
    try:
        payload = json.loads(CONSOLIDATED_MEMORY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_consolidated_memory()
    if not isinstance(payload, dict):
        return default_consolidated_memory()
    memory = default_consolidated_memory()
    memory.update(payload)
    return memory


def save_semantic_memory(memory: dict[str, Any]) -> None:
    ensure_memory_dir()
    SEMANTIC_MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=True, indent=2), encoding="utf-8")


def save_consolidated_memory(memory: dict[str, Any]) -> None:
    ensure_memory_dir()
    CONSOLIDATED_MEMORY_PATH.write_text(json.dumps(memory, ensure_ascii=True, indent=2), encoding="utf-8")


def make_runtime_state() -> dict[str, Any]:
    return {
        "hz": TICK_HZ,
        "last_snapshot": None,
        "llm_last_success_at": None,
        "llm_last_failure_at": None,
        "last_policy_hz": TICK_HZ,
        "actuation_last_signature": None,
        "actuation_last_dispatch_at": 0.0,
        "autonomy": {
            "thermal_bucket": 0,
            "energy_bucket": 0,
            "instability_bucket": 0,
            "last_emit": 0.0,
            "last_heat": 0.0,
            "last_energy": 0.0,
            "last_instability": 0.0,
            "last_cpu_percent": None,
            "last_ac_online": None,
            "last_scenario": None,
        },
        "memory": {
            "conversation": deque(maxlen=SHORT_TERM_TURNS * 2),
            "somatic": deque(maxlen=SOMATIC_WINDOW),
            "semantic": load_semantic_memory(),
            "consolidated": load_consolidated_memory(),
            "last_trace_ts": None,
            "last_consolidation_at": 0.0,
        },
    }


load_projector()
load_machine_fusion()
provider = create_provider(SENSOR_PROVIDER_NAME)
clients: set[ServerConnection] = set()
runtime: dict[str, Any] = make_runtime_state()


def safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=True)


def numeric_series(values: Any) -> list[float]:
    if not isinstance(values, list):
        return []
    result = []
    for value in values:
        try:
            result.append(float(value))
        except (TypeError, ValueError):
            continue
    return result


def tokenize_text(text: str | None) -> set[str]:
    if not text:
        return set()
    return {token for token in re.findall(r"[a-z0-9_]{3,}", text.lower())}


def fmt_or_na(value: Any, digits: int = 1, suffix: str = "") -> str:
    if value is None:
        return "n/a"
    return f"{round(float(value), digits)}{suffix}"


def build_machine_state_vector(system: dict[str, Any]) -> dict[str, Any]:
    feature_specs = [
        ("cpu_percent", system.get("cpu_percent"), 100.0),
        ("cpu_count_logical", system.get("cpu_count_logical"), 256.0),
        ("cpu_count_physical", system.get("cpu_count_physical"), 256.0),
        ("cpu_freq_mhz", system.get("cpu_freq_mhz"), 6000.0),
        ("memory_percent", system.get("memory_percent"), 100.0),
        ("memory_used_gb", system.get("memory_used_gb"), 1024.0),
        ("memory_total_gb", system.get("memory_total_gb"), 1024.0),
        ("swap_percent", system.get("swap_percent"), 100.0),
        ("swap_used_gb", system.get("swap_used_gb"), 512.0),
        ("swap_total_gb", system.get("swap_total_gb"), 512.0),
        ("cpu_temp", system.get("cpu_temp"), 100.0),
        ("cpu_power_w", system.get("cpu_power_w"), 150.0),
        ("gpu_util_percent", system.get("gpu_util_percent"), 100.0),
        ("gpu_temp", system.get("gpu_temp"), 100.0),
        ("gpu_power_w", system.get("gpu_power_w"), 250.0),
        ("gpu_memory_percent", system.get("gpu_memory_percent"), 100.0),
        ("gpu_memory_used_mb", system.get("gpu_memory_used_mb"), 131072.0),
        ("gpu_memory_total_mb", system.get("gpu_memory_total_mb"), 131072.0),
        ("disk_used_percent", system.get("disk_used_percent"), 100.0),
        ("disk_busy_percent", system.get("disk_busy_percent"), 100.0),
        ("disk_total_gb", system.get("disk_total_gb"), 8192.0),
        ("disk_used_gb", system.get("disk_used_gb"), 8192.0),
        ("disk_free_gb", system.get("disk_free_gb"), 8192.0),
        ("disk_read_mb_s", system.get("disk_read_mb_s"), 4000.0),
        ("disk_write_mb_s", system.get("disk_write_mb_s"), 4000.0),
        ("disk_temp", system.get("disk_temp"), 100.0),
        ("net_up_mbps", system.get("net_up_mbps"), 10_000.0),
        ("net_down_mbps", system.get("net_down_mbps"), 10_000.0),
        ("battery_percent", system.get("battery_percent"), 100.0),
        ("fan_rpm", system.get("fan_rpm"), 6000.0),
        ("load_1", system.get("load_1"), 128.0),
        ("load_5", system.get("load_5"), 128.0),
        ("load_15", system.get("load_15"), 128.0),
        ("source_quality", system.get("source_quality"), 1.0),
    ]

    def add_series(prefix: str, values: list[float], scale: float, sample_limit: int) -> None:
        if not values:
            return
        mean_value = sum(values) / len(values)
        max_value = max(values)
        min_value = min(values)
        spread = max_value - min_value
        feature_specs.extend(
            [
                (f"{prefix}_mean", mean_value, scale),
                (f"{prefix}_max", max_value, scale),
                (f"{prefix}_min", min_value, scale),
                (f"{prefix}_spread", spread, scale),
            ]
        )
        for idx, value in enumerate(values[:sample_limit]):
            feature_specs.append((f"{prefix}_{idx}", value, scale))

    add_series("cpu_core", numeric_series(system.get("cpu_per_core_percent")), 100.0, 8)
    add_series("cpu_temp_sensor", numeric_series(system.get("cpu_temp_sensors_c")), 100.0, 8)
    add_series("thermal_sensor", numeric_series(system.get("thermal_sensors_c")), 100.0, 8)
    add_series("fan_sensor", numeric_series(system.get("fan_sensors_rpm")), 6000.0, 4)

    features: dict[str, float] = {}
    values: list[float] = []
    for name, raw, scale in feature_specs:
        normalized = 0.0 if raw is None else clamp01(float(raw) / scale)
        features[name] = round(normalized, 4)
        values.append(normalized)

    vector: list[float] = []
    for idx in range(MACHINE_VECTOR_DIM):
        fi = idx / MACHINE_VECTOR_DIM
        value = 0.0
        for j, base in enumerate(values):
            phase = (j + 1) * 0.41
            value += base * (
                0.57 * math.sin(fi * (9 + j * 2) * math.pi + phase)
                + 0.43 * math.cos(fi * (13 + j * 3) * math.pi + phase * 0.83)
            )
        vector.append(value)

    norm = math.sqrt(sum(item * item for item in vector))
    top_features = sorted(features.items(), key=lambda item: item[1], reverse=True)[:8]
    return {
        "dim": MACHINE_VECTOR_DIM,
        "norm": round(norm, 4),
        "vector": [round(float(item), 4) for item in vector],
        "preview": [round(float(item), 4) for item in vector[:32]],
        "top_features": [[name, round(value, 4)] for name, value in top_features],
        "features": features,
    }


def analytic_fuse_machine_state(base_vector: list[float], machine_vector: dict[str, Any]) -> tuple[list[float], dict[str, Any]]:
    machine_values = machine_vector.get("vector") or machine_vector.get("preview") or []
    if not machine_values:
        return base_vector, {"enabled": False, "gain": 0.0, "machine_norm": 0.0, "mode": "disabled", "delta_norm": 0.0}

    gain = 0.18
    source = [float(value) for value in machine_values]
    fused = []
    delta_sq = 0.0
    for idx, base_value in enumerate(base_vector):
        mv = source[idx % len(source)]
        harmonic = (0.62 * mv) + (0.23 * math.sin(mv * 1.7 + idx * 0.013)) + (0.15 * math.cos(idx * 0.021))
        delta = gain * harmonic
        fused.append(base_value + delta)
        delta_sq += delta * delta
    return fused, {
        "enabled": True,
        "gain": round(gain, 3),
        "machine_norm": round(float(machine_vector.get("norm") or 0.0), 4),
        "mode": "analytic",
        "delta_norm": round(math.sqrt(delta_sq), 4),
    }


def learned_fuse_machine_state(base_vector: list[float], machine_vector: dict[str, Any]) -> tuple[list[float], dict[str, Any]] | None:
    machine_values = machine_vector.get("vector") or machine_vector.get("preview") or []
    if machine_fusion is None or not machine_values or torch is None:
        return None
    try:
        with torch.no_grad():
            machine_tensor = torch.tensor([machine_values[:MACHINE_VECTOR_DIM]], dtype=torch.float32)
            delta_tensor = machine_fusion(machine_tensor).squeeze(0).to(torch.float32)
            delta = delta_tensor.tolist()
    except Exception as exc:
        machine_fusion_meta["error"] = str(exc)
        return None

    if len(delta) != len(base_vector):
        machine_fusion_meta["error"] = f"delta_dim_mismatch:{len(delta)}"
        return None

    fused = [base + shift for base, shift in zip(base_vector, delta, strict=False)]
    delta_norm = math.sqrt(sum(item * item for item in delta))
    return fused, {
        "enabled": True,
        "gain": 1.0,
        "machine_norm": round(float(machine_vector.get("norm") or 0.0), 4),
        "mode": "learned",
        "delta_norm": round(delta_norm, 4),
    }


def fuse_machine_state(base_vector: list[float], machine_vector: dict[str, Any]) -> tuple[list[float], dict[str, Any]]:
    learned = learned_fuse_machine_state(base_vector, machine_vector)
    if learned is not None:
        return learned
    return analytic_fuse_machine_state(base_vector, machine_vector)


def build_homeostasis_state(
    core: dict[str, Any],
    system: dict[str, Any],
    affect: dict[str, float],
    derived: dict[str, float],
) -> dict[str, Any]:
    drives = {
        "cooling": round(derived["thermal_stress"], 3),
        "energy_recovery": round(derived["energy_stress"], 3),
        "stability": round(derived["instability"], 3),
        "rest": round(affect["fatigue"], 3),
        "warmth": round(affect["cold"], 3),
        "exploration": round(affect["curiosity"], 3),
    }
    dominant = sorted(drives.items(), key=lambda item: item[1], reverse=True)[:3]
    return {
        "drives": drives,
        "dominant": [{"name": name, "intensity": round(value, 3)} for name, value in dominant],
        "stability_margin": round(1.0 - drives["stability"], 3),
        "thermal_margin": round(1.0 - drives["cooling"], 3),
        "energy_margin": round(1.0 - drives["energy_recovery"], 3),
        "power_source": "external" if system.get("ac_online") else "internal",
        "body_orientation": "upright" if abs(float(core.get("az", -9.81))) > 8.0 else "tilted",
    }


def compact_system_snapshot(system: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "cpu_percent",
        "cpu_freq_mhz",
        "cpu_temp",
        "cpu_power_w",
        "memory_percent",
        "memory_used_gb",
        "memory_total_gb",
        "swap_percent",
        "disk_used_percent",
        "disk_busy_percent",
        "disk_read_mb_s",
        "disk_write_mb_s",
        "disk_temp",
        "gpu_util_percent",
        "gpu_temp",
        "gpu_power_w",
        "gpu_memory_percent",
        "gpu_memory_used_mb",
        "gpu_memory_total_mb",
        "battery_percent",
        "ac_online",
        "fan_rpm",
        "net_up_mbps",
        "net_down_mbps",
        "source_quality",
        "source_quality_label",
    )
    compact = {}
    for key in keys:
        value = system.get(key)
        if isinstance(value, (float, int)):
            compact[key] = rounded(value, 3)
        else:
            compact[key] = value
    return compact


def compact_core_snapshot(core: dict[str, Any]) -> dict[str, Any]:
    return {key: rounded(value, 3) for key, value in core.items()}


def clip_text(text: str | None, limit: int = 220) -> str | None:
    if text is None:
        return None
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3] + "..."


def load_recent_episodes(limit: int) -> list[dict[str, Any]]:
    if limit <= 0 or not EPISODIC_MEMORY_PATH.exists():
        return []
    episodes: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        with EPISODIC_MEMORY_PATH.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(payload, dict):
                    episodes.append(payload)
    except OSError:
        return []
    return list(episodes)


def retrieve_relevant_episodes(user_text: str, snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    episodes = load_recent_episodes(EPISODIC_SCAN_LIMIT)
    if not episodes:
        return []

    query_tokens = tokenize_text(user_text)
    provider_name = snapshot["provider"]["name"]
    scenario = snapshot["scenario"]
    dominant_drives = {item["name"] for item in snapshot["homeostasis"]["dominant"]}
    scored: list[tuple[float, dict[str, Any]]] = []
    total = len(episodes)

    for idx, episode in enumerate(episodes):
        provider = episode.get("provider")
        episode_provider = provider.get("name") if isinstance(provider, dict) else provider
        episode_homeostasis = episode.get("homeostasis") if isinstance(episode.get("homeostasis"), dict) else {}
        dominant = episode_homeostasis.get("dominant") if isinstance(episode_homeostasis, dict) else []
        episode_drives = {
            item.get("name")
            for item in dominant
            if isinstance(item, dict) and item.get("name")
        }

        text_blob = " ".join(
            str(value)
            for value in (
                episode.get("summary"),
                episode.get("user_text"),
                episode.get("reply_text"),
                episode.get("event_text"),
                episode.get("event_name"),
                episode.get("scenario"),
                episode_provider,
            )
            if value
        )
        episode_tokens = tokenize_text(text_blob)
        overlap = len(query_tokens & episode_tokens)
        drive_overlap = len(dominant_drives & episode_drives)
        scenario_match = 1.0 if episode.get("scenario") == scenario else 0.0
        provider_match = 0.35 if episode_provider == provider_name else 0.0
        kind_bonus = 0.2 if episode.get("kind") == "chat" else 0.1
        recency_bonus = (idx + 1) / max(total, 1)
        score = (overlap * 2.0) + (drive_overlap * 1.5) + scenario_match + provider_match + kind_bonus + recency_bonus
        if score <= 0.0:
            continue
        scored.append((score, episode))

    if not scored:
        scored = [(1.0, episode) for episode in episodes[-EPISODIC_RECALL_LIMIT:]]

    scored.sort(key=lambda item: item[0], reverse=True)
    selected = []
    for score, episode in scored[:EPISODIC_RECALL_LIMIT]:
        selected.append(
            {
                "score": round(score, 3),
                "timestamp": episode.get("timestamp"),
                "kind": episode.get("kind"),
                "scenario": episode.get("scenario"),
                "summary": clip_text(episode.get("summary")),
                "user_text": clip_text(episode.get("user_text")),
                "reply_text": clip_text(episode.get("reply_text")),
                "event_name": episode.get("event_name"),
                "event_text": clip_text(episode.get("event_text")),
            }
        )
    return selected


def build_salience(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    system = snapshot["system"]
    sensors = snapshot["sensors"]
    homeostasis = snapshot["homeostasis"]

    salience = [
        {
            "channel": "core_power",
            "priority": round(max(snapshot["derived"]["energy_stress"], 0.2), 3),
            "summary": (
                f"{rounded(sensors['voltage'], 2)}V, {round(float(sensors['current_ma']))}mA, "
                f"battery={fmt_or_na(system.get('battery_percent'), 1, '%')}, AC={system.get('ac_online')}"
            ),
        },
        {
            "channel": "thermal",
            "priority": round(max(snapshot["derived"]["thermal_stress"], snapshot["affect"]["cold"]), 3),
            "summary": (
                f"silicon={fmt_or_na(sensors.get('temp_si'), 1, 'C')}, "
                f"cpu={fmt_or_na(system.get('cpu_temp'), 1, 'C')}, "
                f"gpu={fmt_or_na(system.get('gpu_temp'), 1, 'C')}, "
                f"disk={fmt_or_na(system.get('disk_temp'), 1, 'C')}"
            ),
        },
        {
            "channel": "compute",
            "priority": round(max(snapshot["affect"]["fatigue"], snapshot["affect"]["curiosity"]), 3),
            "summary": (
                f"cpu={fmt_or_na(system.get('cpu_percent'), 1, '%')} on "
                f"{system.get('cpu_count_logical') or '--'} logical cores, "
                f"ram={fmt_or_na(system.get('memory_percent'), 1, '%')}, "
                f"swap={fmt_or_na(system.get('swap_percent'), 1, '%')}"
            ),
        },
        {
            "channel": "storage_network",
            "priority": round(
                max(
                    float(system.get("disk_busy_percent") or 0.0) / 100.0,
                    float(system.get("net_down_mbps") or 0.0) / 1000.0,
                    float(system.get("net_up_mbps") or 0.0) / 1000.0,
                ),
                3,
            ),
            "summary": (
                f"disk={fmt_or_na(system.get('disk_used_percent'), 1, '%')} used, "
                f"busy={fmt_or_na(system.get('disk_busy_percent'), 1, '%')}, "
                f"read={fmt_or_na(system.get('disk_read_mb_s'), 1, 'MB/s')}, "
                f"write={fmt_or_na(system.get('disk_write_mb_s'), 1, 'MB/s')}, "
                f"net_down={fmt_or_na(system.get('net_down_mbps'), 1, 'Mb/s')}, "
                f"net_up={fmt_or_na(system.get('net_up_mbps'), 1, 'Mb/s')}"
            ),
        },
        {
            "channel": "homeostasis",
            "priority": round(max(item["intensity"] for item in homeostasis["dominant"]), 3),
            "summary": ", ".join(
                f"{item['name']}={item['intensity']:.2f}" for item in homeostasis["dominant"]
            ),
        },
    ]
    salience.sort(key=lambda item: item["priority"], reverse=True)
    return salience


def detect_language_label(*texts: str | None) -> str:
    text = " ".join(item for item in texts if item).lower()
    if not text:
        return "unknown"
    italian_markers = {"come", "cosa", "quanti", "quanta", "stato", "temperico", "termico", "sei", "senti", "ciao", "grazie", "memoria"}
    english_markers = {"what", "how", "temperature", "state", "memory", "core", "hello", "thanks", "feel"}
    it_score = sum(1 for token in tokenize_text(text) if token in italian_markers)
    en_score = sum(1 for token in tokenize_text(text) if token in english_markers)
    if it_score > en_score:
        return "it"
    if en_score > it_score:
        return "en"
    return "mixed"


def consolidate_memory(snapshot: dict[str, Any], *, user_text: str | None = None, reply_text: str | None = None) -> None:
    memory = runtime["memory"]
    now = time.monotonic()
    last_at = float(memory.get("last_consolidation_at") or 0.0)
    if now - last_at < CONSOLIDATION_INTERVAL_S and user_text is None and reply_text is None:
        return

    consolidated = memory["consolidated"]
    consolidated["last_consolidated_at"] = snapshot["timestamp"]
    consolidated["observation_count"] = int(consolidated.get("observation_count", 0)) + 1
    obs_count = max(1, int(consolidated["observation_count"]))

    avg_metrics = consolidated.setdefault("avg_metrics", {})
    ranges = consolidated.setdefault("ranges", {})
    metric_names = (
        "cpu_percent",
        "memory_percent",
        "cpu_temp",
        "gpu_temp",
        "disk_temp",
        "battery_percent",
        "disk_busy_percent",
        "net_down_mbps",
        "net_up_mbps",
    )
    for key in metric_names:
        value = snapshot["system"].get(key)
        if value is None:
            continue
        current = float(value)
        prev_avg = float(avg_metrics.get(key, current))
        avg_metrics[key] = round(prev_avg + ((current - prev_avg) / obs_count), 4)
        range_entry = ranges.setdefault(key, {"min": current, "max": current})
        range_entry["min"] = round(min(float(range_entry["min"]), current), 4)
        range_entry["max"] = round(max(float(range_entry["max"]), current), 4)

    state_counts = consolidated.setdefault("state_counts", {})
    scenario = snapshot["scenario"]
    state_counts[scenario] = int(state_counts.get(scenario, 0)) + 1

    last_scenario = runtime["autonomy"].get("last_scenario")
    if last_scenario:
        transition_key = f"{last_scenario}->{scenario}"
        transitions = consolidated.setdefault("state_transitions", {})
        transitions[transition_key] = int(transitions.get(transition_key, 0)) + 1

    drive_counts = consolidated.setdefault("drive_counts", {})
    for item in snapshot["homeostasis"]["dominant"]:
        name = item["name"]
        drive_counts[name] = int(drive_counts.get(name, 0)) + 1

    topic_counts = Counter(consolidated.get("topic_counts", {}))
    for text in (user_text, reply_text):
        for token in tokenize_text(text):
            if token.isdigit():
                continue
            topic_counts[token] += 1
    consolidated["topic_counts"] = dict(topic_counts.most_common(40))

    lang = detect_language_label(user_text, reply_text)
    language_counts = consolidated.setdefault("language_counts", {})
    language_counts[lang] = int(language_counts.get(lang, 0)) + 1

    hardware_profile = consolidated.setdefault("hardware_profile", {})
    for key in ("cpu_count_logical", "cpu_count_physical", "memory_total_gb", "disk_total_gb", "gpu_memory_total_mb"):
        value = snapshot["system"].get(key)
        if value is not None and hardware_profile.get(key) is None:
            hardware_profile[key] = rounded(value, 3) if isinstance(value, (float, int)) else value

    save_consolidated_memory(consolidated)
    memory["last_consolidation_at"] = now


def build_memory_context(snapshot: dict[str, Any], user_text: str) -> dict[str, Any]:
    memory = runtime["memory"]
    semantic = dict(memory["semantic"])
    consolidated = dict(memory["consolidated"])
    return {
        "recent_dialogue": list(memory["conversation"])[-SHORT_TERM_TURNS:],
        "recent_somatic_window": list(memory["somatic"])[-SOMATIC_WINDOW:],
        "relevant_episodes": retrieve_relevant_episodes(user_text, snapshot),
        "long_term_profile": {
            "first_seen_at": semantic.get("first_seen_at"),
            "last_seen_at": semantic.get("last_seen_at"),
            "total_chat_exchanges": semantic.get("total_chat_exchanges"),
            "total_autonomous_events": semantic.get("total_autonomous_events"),
            "scenario_counts": semantic.get("scenario_counts"),
            "provider_counts": semantic.get("provider_counts"),
            "dominant_homeostatic_drives": semantic.get("dominant_homeostatic_drives"),
            "last_user_text": semantic.get("last_user_text"),
            "last_entity_text": semantic.get("last_entity_text"),
            "last_event": semantic.get("last_event"),
        },
        "consolidated_profile": consolidated,
    }


def remember_dialogue_turn(role: str, text: str, snapshot: dict[str, Any]) -> None:
    runtime["memory"]["conversation"].append(
        {
            "role": role,
            "text": text.strip(),
            "timestamp": snapshot["timestamp"],
            "scenario": snapshot["scenario"],
            "provider": snapshot["provider"]["name"],
            "homeostasis": snapshot["homeostasis"]["dominant"],
        }
    )


def remember_somatic_trace(snapshot: dict[str, Any]) -> None:
    memory = runtime["memory"]
    last_trace_ts = memory.get("last_trace_ts")
    if last_trace_ts is not None and abs(snapshot["timestamp"] - last_trace_ts) < 0.4:
        return
    memory["somatic"].append(
        {
            "timestamp": snapshot["timestamp"],
            "scenario": snapshot["scenario"],
            "summary": snapshot["summary"],
            "derived": snapshot["derived"],
            "homeostasis": snapshot["homeostasis"]["dominant"],
            "core": compact_core_snapshot(snapshot["sensors"]),
            "system": compact_system_snapshot(snapshot["system"]),
        }
    )
    memory["last_trace_ts"] = snapshot["timestamp"]


def remember_episode(
    kind: str,
    snapshot: dict[str, Any],
    *,
    user_text: str | None = None,
    reply_text: str | None = None,
    event_name: str | None = None,
    event_text: str | None = None,
) -> None:
    ensure_memory_dir()
    memory = runtime["memory"]["semantic"]
    memory["last_seen_at"] = snapshot["timestamp"]
    scenario = snapshot["scenario"]
    provider_name = snapshot["provider"]["name"]
    memory["scenario_counts"][scenario] = int(memory["scenario_counts"].get(scenario, 0)) + 1
    memory["provider_counts"][provider_name] = int(memory["provider_counts"].get(provider_name, 0)) + 1
    memory["dominant_homeostatic_drives"] = [item["name"] for item in snapshot["homeostasis"]["dominant"]]

    if kind == "chat":
        memory["total_chat_exchanges"] = int(memory.get("total_chat_exchanges", 0)) + 1
        memory["last_user_text"] = user_text
        memory["last_entity_text"] = reply_text
    elif kind == "autonomous_event":
        memory["total_autonomous_events"] = int(memory.get("total_autonomous_events", 0)) + 1
        memory["last_event"] = {"name": event_name, "text": event_text, "timestamp": snapshot["timestamp"]}

    save_semantic_memory(memory)
    consolidate_memory(snapshot, user_text=user_text, reply_text=reply_text or event_text)

    episode = {
        "timestamp": snapshot["timestamp"],
        "kind": kind,
        "scenario": scenario,
        "provider": snapshot["provider"],
        "summary": snapshot["summary"],
        "homeostasis": snapshot["homeostasis"],
        "derived": snapshot["derived"],
        "core": compact_core_snapshot(snapshot["sensors"]),
        "system": compact_system_snapshot(snapshot["system"]),
        "user_text": user_text,
        "reply_text": reply_text,
        "event_name": event_name,
        "event_text": event_text,
    }
    with EPISODIC_MEMORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(episode, ensure_ascii=True) + "\n")


def detect_intent(text: str) -> str:
    lowered = text.lower()
    for keys, intent in INTENT_MAP:
        if any(key in lowered for key in keys):
            return intent
    return "_default"


def llm_mode_enabled(mode: str | None = None) -> bool:
    return (mode or LLM_MODE) in {"openai_compatible", "deepseek"}


def get_llm_request_config() -> dict[str, Any] | None:
    if LLM_MODE == "openai_compatible":
        return {
            "provider": "openai_compatible",
            "endpoint": LLM_ENDPOINT,
            "model": LLM_MODEL,
            "api_key": LLM_API_KEY,
            "extra_payload": {},
        }
    if LLM_MODE == "deepseek":
        return {
            "provider": "deepseek",
            "endpoint": DEEPSEEK_ENDPOINT,
            "model": DEEPSEEK_MODEL,
            "api_key": DEEPSEEK_API_KEY,
            "extra_payload": {"response_format": {"type": "json_object"}},
        }
    return None


def llm_runtime_available() -> bool:
    config = get_llm_request_config()
    if config is None:
        return False
    if config["provider"] == "deepseek" and not config["api_key"]:
        return False
    return bool(config["endpoint"])


def sensors_to_list(core: dict[str, Any]) -> list[float]:
    return [float(core[field]) for field in CORE_FIELDS]


def _fallback_projector_vector(core: dict[str, Any]) -> list[float]:
    values = sensors_to_list(core)
    normalized = [
        (core["voltage"] - 10.5) / 2.0,
        core["current_ma"] / 6000.0,
        (core["temp_si"] - 35.0) / 55.0,
        (core["temp_ml"] - 35.0) / 55.0,
        (core["temp_mr"] - 35.0) / 55.0,
        core["ax"] / 10.0,
        core["ay"] / 10.0,
        (core["az"] + 9.81) / 10.0,
        core["gx"] / 4.0,
        core["gy"] / 4.0,
        core["gz"] / 4.0,
    ]
    vector: list[float] = []
    for idx in range(LLM_EMB_DIM):
        fi = idx / LLM_EMB_DIM
        v = 0.0
        for j, base in enumerate(normalized):
            phase = (j + 1) * 0.37
            v += base * (
                0.55 * math.sin(fi * (7 + j * 3) * math.pi + phase)
                + 0.45 * math.cos(fi * (11 + j * 5) * math.pi + phase * 0.7)
            )
        v += 0.08 * math.sin(values[idx % len(values)] * 0.01 + fi * math.pi * 19)
        vector.append(v)
    return vector


def run_projector(core: dict[str, Any], machine_vector: dict[str, Any] | None = None) -> dict[str, Any]:
    started = time.perf_counter()

    if projector is not None:
        with torch.no_grad():
            tensor = torch.tensor([sensors_to_list(core)], dtype=torch.float32)
            vector_tensor = projector(tensor).squeeze(0)
            vector = vector_tensor.tolist()
        mode = "torchscript"
        available = True
    else:
        vector = _fallback_projector_vector(core)
        mode = "fallback"
        available = False

    vector, fusion_meta = fuse_machine_state(vector, machine_vector or {})

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    step = LLM_EMB_DIM // HEATMAP_BINS
    heatmap = vector[::step][:HEATMAP_BINS]
    norm = math.sqrt(sum(value * value for value in vector))
    mean = sum(vector) / len(vector)
    variance = sum((value - mean) ** 2 for value in vector) / len(vector)
    std = math.sqrt(variance)
    top_idx = sorted(range(len(vector)), key=lambda idx: abs(vector[idx]), reverse=True)[:5]
    top_vals = [float(vector[idx]) for idx in top_idx]

    seg_energy = []
    seg_size = LLM_EMB_DIM // 16
    for i in range(16):
        seg = vector[i * seg_size : (i + 1) * seg_size]
        if not seg:
            seg_energy.append(0.0)
            continue
        seg_energy.append(math.sqrt(sum(value * value for value in seg) / len(seg)))

    return {
        "heatmap": heatmap,
        "norm": float(norm),
        "mean": float(mean),
        "std": float(std),
        "top_dims": top_idx,
        "top_vals": top_vals,
        "seg_energy": seg_energy,
        "projector_ms": round(elapsed_ms, 3),
        "projector": {
            "available": available,
            "mode": mode,
            "dim": LLM_EMB_DIM,
            "norm": round(float(norm), 4),
            "top_dims": top_idx,
            "top_vals": [round(float(value), 4) for value in top_vals],
            "path": projector_meta["path"],
            "error": projector_meta["error"],
            "machine_fusion_enabled": fusion_meta["enabled"],
            "machine_fusion_gain": fusion_meta["gain"],
            "machine_vector_norm": fusion_meta["machine_norm"],
            "machine_fusion_mode": fusion_meta["mode"],
            "machine_fusion_delta_norm": fusion_meta["delta_norm"],
        },
    }


def derive_affect(core: dict[str, Any], system: dict[str, Any]) -> dict[str, float]:
    thermal_anchor = max(
        value
        for value in (
            core.get("temp_si"),
            core.get("temp_ml"),
            core.get("temp_mr"),
            system.get("cpu_temp"),
            system.get("gpu_temp"),
            35.0,
        )
        if value is not None
    )
    cold_anchor = min(
        value
        for value in (
            core.get("temp_si"),
            core.get("temp_ml"),
            core.get("temp_mr"),
            system.get("cpu_temp"),
            35.0,
        )
        if value is not None
    )

    battery_percent = system.get("battery_percent")
    voltage = float(core.get("voltage", 12.0))
    cpu_percent = float(system.get("cpu_percent") or 0.0)
    memory_percent = float(system.get("memory_percent") or 0.0)
    gpu_util = float(system.get("gpu_util_percent") or 0.0)
    current_ma = float(core.get("current_ma", 250.0))
    gz = abs(float(core.get("gz", 0.0)))
    gxy = max(abs(float(core.get("gx", 0.0))), abs(float(core.get("gy", 0.0))))
    gravity_error = abs(abs(float(core.get("az", -9.81))) - 9.81)

    heat = clamp01((thermal_anchor - 48.0) / 35.0)
    cold = clamp01((28.0 - cold_anchor) / 18.0)
    if battery_percent is not None:
        energy_low = clamp01((35.0 - float(battery_percent)) / 35.0)
    else:
        energy_low = clamp01((11.2 - voltage) / 1.2)
    fatigue = clamp01(
        max(heat * 0.85, energy_low * 0.95, cpu_percent / 130.0, memory_percent / 180.0, current_ma / 7000.0)
    )
    instability = clamp01((gravity_error / 4.5) + (gz / 4.0) + (gxy / 5.0))
    curiosity = clamp01(0.3 + (cpu_percent / 260.0) + (gpu_util / 260.0) + ((1.0 - fatigue) * 0.25))

    return {
        "cold": round(cold, 3),
        "heat": round(heat, 3),
        "energy_low": round(energy_low, 3),
        "fatigue": round(fatigue, 3),
        "instability": round(instability, 3),
        "curiosity": round(curiosity, 3),
    }


def derive_state(core: dict[str, Any], system: dict[str, Any], affect: dict[str, float]) -> dict[str, float]:
    comfort = clamp01(1.0 - max(affect["heat"], affect["energy_low"], affect["instability"], affect["fatigue"] * 0.9))
    return {
        "thermal_stress": affect["heat"],
        "energy_stress": affect["energy_low"],
        "instability": affect["instability"],
        "comfort": round(comfort, 3),
        "fatigue": affect["fatigue"],
        "curiosity": affect["curiosity"],
        "cold": affect["cold"],
    }


def derive_actions(affect: dict[str, float]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if affect["instability"] >= 0.55:
        actions.append({"type": "animation", "name": "brace_balance", "intensity": round(affect["instability"], 3)})
    if affect["heat"] >= 0.65:
        actions.append(
            {
                "type": "animation",
                "name": "wipe_forehead" if affect["heat"] >= 0.8 else "warm_idle",
                "intensity": round(affect["heat"], 3),
            }
        )
    if affect["cold"] >= 0.55:
        actions.append({"type": "animation", "name": "cold_shiver", "intensity": round(affect["cold"], 3)})
    if affect["energy_low"] >= 0.6:
        actions.append({"type": "animation", "name": "low_power_posture", "intensity": round(affect["energy_low"], 3)})
    if not actions:
        actions.append({"type": "animation", "name": "attend_user", "intensity": round(max(0.25, affect["curiosity"]), 3)})
    return actions[:3]


def classify_state(core: dict[str, Any], system: dict[str, Any], derived: dict[str, float], explicit: str | None) -> str:
    if explicit:
        return explicit
    if derived["instability"] >= 0.72:
        return "fall"
    if abs(float(core.get("gz", 0.0))) >= 1.5:
        return "spin"
    if derived["thermal_stress"] >= 0.7:
        return "overheat"
    if derived["energy_stress"] >= 0.7:
        return "lowbatt"
    if derived["cold"] >= 0.62:
        return "cold"
    if (
        float(system.get("cpu_percent") or 0.0) >= 85.0
        or float(system.get("gpu_util_percent") or 0.0) >= 85.0
        or float(core.get("current_ma", 0.0)) >= 4200.0
    ):
        return "heavyload"
    return "nominal"


def build_summary(snapshot: dict[str, Any]) -> str:
    provider_info = snapshot["provider"]
    core = snapshot["sensors"]
    system = snapshot["system"]
    derived = snapshot["derived"]
    gpu_part = (
        f", GPU {rounded(system.get('gpu_temp'), 1)}C/{rounded(system.get('gpu_util_percent'), 1)}%"
        if system.get("gpu_temp") is not None or system.get("gpu_util_percent") is not None
        else ""
    )
    return (
        f"{snapshot['scenario']} state via {provider_info['name']} "
        f"({'real' if provider_info['is_real'] else 'mock'}), "
        f"{rounded(core['voltage'], 2)}V, silicon {rounded(core['temp_si'], 1)}C, "
        f"CPU {rounded(system.get('cpu_temp'), 1) if system.get('cpu_temp') is not None else 'n/a'}C/"
        f"{rounded(system.get('cpu_percent'), 1) if system.get('cpu_percent') is not None else 'n/a'}%, "
        f"RAM {rounded(system.get('memory_percent'), 1) if system.get('memory_percent') is not None else 'n/a'}%, "
        f"disk {rounded(system.get('disk_used_percent'), 1) if system.get('disk_used_percent') is not None else 'n/a'}%"
        f"{gpu_part}, "
        f"thermal_stress={derived['thermal_stress']:.2f}, energy_stress={derived['energy_stress']:.2f}, "
        f"comfort={derived['comfort']:.2f}"
    )


def build_policy_state(snapshot: dict[str, Any]) -> dict[str, Any]:
    derived = snapshot["derived"]
    system = snapshot["system"]
    affect = snapshot["affect"]
    homeostasis = snapshot["homeostasis"]

    dominant_name = homeostasis["dominant"][0]["name"] if homeostasis["dominant"] else "exploration"
    mode = "nominal"
    goals = ["maintain_continuity", "observe_body"]
    target_hz = 5.0
    speech_profile = "grounded"

    if snapshot["scenario"] in {"fall", "spin"} or derived["instability"] >= 0.75:
        mode = "stabilize"
        goals = ["freeze_motion", "restore_orientation", "reduce_cognitive_noise"]
        target_hz = 8.0
        speech_profile = "urgent"
    elif snapshot["scenario"] == "overheat" or derived["thermal_stress"] >= 0.72:
        mode = "cooling"
        goals = ["shed_load", "increase_cooling", "compress_language"]
        target_hz = 6.0
        speech_profile = "brief"
    elif snapshot["scenario"] == "lowbatt" or derived["energy_stress"] >= 0.72:
        mode = "conserve"
        goals = ["save_energy", "seek_external_power", "suppress_nonessential_motion"]
        target_hz = 3.0
        speech_profile = "brief"
    elif snapshot["scenario"] == "cold" or affect["cold"] >= 0.68:
        mode = "warmup"
        goals = ["preserve_heat", "minimize_idle_motion", "retain_awareness"]
        target_hz = 4.0
        speech_profile = "measured"
    elif float(system.get("cpu_percent") or 0.0) >= 88.0 or float(system.get("gpu_util_percent") or 0.0) >= 88.0:
        mode = "load_shedding"
        goals = ["reduce_compute_pressure", "protect_thermal_headroom", "prioritize_core_tasks"]
        target_hz = 4.0
        speech_profile = "brief"
    elif dominant_name == "exploration" and derived["comfort"] >= 0.65:
        mode = "explore"
        goals = ["sample_environment", "maintain_dialogue", "expand_memory_trace"]
        target_hz = 5.0
        speech_profile = "expressive"

    compute_pressure = max(
        float(system.get("cpu_percent") or 0.0) / 100.0,
        float(system.get("memory_percent") or 0.0) / 100.0,
        float(system.get("gpu_util_percent") or 0.0) / 100.0,
    )
    risk = round(
        max(
            derived["thermal_stress"],
            derived["energy_stress"],
            derived["instability"],
            compute_pressure * 0.75,
        ),
        3,
    )
    return {
        "mode": mode,
        "dominant_drive": dominant_name,
        "goals": goals,
        "target_hz": round(target_hz, 2),
        "speech_profile": speech_profile,
        "risk": risk,
        "comfort": derived["comfort"],
    }


def apply_autonomic_rate(policy: dict[str, Any]) -> None:
    if not AUTONOMIC_HZ_ENABLED:
        return
    desired = clamp(float(policy.get("target_hz") or runtime["hz"]), 0.2, 20.0)
    current = float(runtime["hz"])
    runtime["hz"] = round(current + ((desired - current) * 0.22), 3)
    runtime["last_policy_hz"] = desired


def build_actuation_state(snapshot: dict[str, Any], policy: dict[str, Any]) -> dict[str, Any]:
    derived = snapshot["derived"]
    system = snapshot["system"]
    posture = snapshot["actions"][0]["name"] if snapshot["actions"] else "attend_user"
    thermal = derived["thermal_stress"]
    energy = derived["energy_stress"]
    instability = derived["instability"]

    commands = [
        {"channel": "posture", "value": posture},
        {"channel": "fan_target", "value": round(clamp(max(thermal, float(system.get("cpu_percent") or 0.0) / 100.0), 0.15, 1.0), 3)},
        {
            "channel": "compute_governor",
            "value": (
                "powersave" if policy["mode"] in {"conserve", "cooling", "load_shedding"}
                else "balanced" if policy["mode"] in {"nominal", "warmup"}
                else "performance"
            ),
        },
        {
            "channel": "motion_gate",
            "value": (
                "freeze" if policy["mode"] == "stabilize"
                else "limited" if instability >= 0.45 or energy >= 0.55
                else "open"
            ),
        },
        {
            "channel": "language_profile",
            "value": policy["speech_profile"],
        },
    ]
    if energy >= 0.6:
        commands.append({"channel": "power_request", "value": "seek_external_power"})
    if thermal >= 0.7:
        commands.append({"channel": "thermal_guard", "value": "shed_load"})
    if instability >= 0.55:
        commands.append({"channel": "balance_guard", "value": "brace"})

    return {
        "enabled": ACTUATOR_ENABLED,
        "transport": "endpoint" if ACTUATOR_ENDPOINT else "file",
        "policy_mode": policy["mode"],
        "commands": commands,
    }


def dispatch_actuation(snapshot: dict[str, Any]) -> None:
    if not ACTUATOR_ENABLED:
        return
    ensure_runtime_dir()
    actuation = snapshot["actuation"]
    payload = {
        "timestamp": snapshot["timestamp"],
        "provider": snapshot["provider"],
        "scenario": snapshot["scenario"],
        "policy": snapshot["policy"],
        "actuation": actuation,
        "summary": snapshot["summary"],
    }
    signature = safe_json_dumps(payload)
    now = time.monotonic()
    if signature == runtime.get("actuation_last_signature") and (now - float(runtime.get("actuation_last_dispatch_at") or 0.0)) < 2.0:
        return

    ACTUATION_STATE_PATH.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    with ACTUATION_HISTORY_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=True) + "\n")

    if ACTUATOR_ENDPOINT:
        body = safe_json_dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            ACTUATOR_ENDPOINT,
            data=body,
            headers={"Content-Type": "application/json", "User-Agent": "latent-somatic/actuator"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=1.5):
                pass
        except Exception as exc:
            actuation["endpoint_error"] = str(exc)

    runtime["actuation_last_signature"] = signature
    runtime["actuation_last_dispatch_at"] = now


def build_llm_context(snapshot: dict[str, Any], user_text: str) -> dict[str, Any]:
    memory_context = build_memory_context(snapshot, user_text)
    return {
        "identity": {
            "name": "Soma",
            "architecture": "latent-somatic",
            "language_core": "deepseek" if LLM_MODE == "deepseek" else LLM_MODE,
            "goal": "maintain continuity between body state, memory, and language",
        },
        "task": {
            "user_text": user_text,
            "instruction": (
                "Answer from the machine's embodied perspective using telemetry, fused vectors, "
                "homeostasis, recent memory, and retrieved episodic memory."
            ),
            "reply_language": "match_user_language",
        },
        "summary": snapshot["summary"],
        "sensor_provider": snapshot["provider"]["name"],
        "is_real": snapshot["provider"]["is_real"],
        "salience": build_salience(snapshot),
        "policy": snapshot["policy"],
        "actuation": snapshot["actuation"],
        "body_state": {
            "core": compact_core_snapshot(snapshot["sensors"]),
            "system": {
                key: rounded(value, 3) if isinstance(value, (float, int)) else value
                for key, value in snapshot["system"].items()
            },
            "derived": snapshot["derived"],
            "affect": snapshot["affect"],
            "homeostasis": snapshot["homeostasis"],
            "machine_vector": snapshot["machine_vector"],
        },
        "projector": {
            "available": snapshot["projector"]["available"],
            "mode": snapshot["projector"]["mode"],
            "norm": snapshot["projector"]["norm"],
            "top_dims": snapshot["projector"]["top_dims"][:5],
            "top_vals": snapshot["projector"]["top_vals"][:5],
            "machine_fusion": {
                "enabled": snapshot["projector"].get("machine_fusion_enabled"),
                "gain": snapshot["projector"].get("machine_fusion_gain"),
                "machine_norm": snapshot["projector"].get("machine_vector_norm"),
                "mode": snapshot["projector"].get("machine_fusion_mode"),
                "delta_norm": snapshot["projector"].get("machine_fusion_delta_norm"),
            },
        },
        "memory": memory_context,
    }


def normalize_llm_output(payload: dict[str, Any], affect: dict[str, float], actions: list[dict[str, Any]]) -> dict[str, Any]:
    speech = str(payload.get("speech") or "").strip()
    raw_affect = payload.get("affect") if isinstance(payload.get("affect"), dict) else {}
    merged_affect = dict(affect)
    for key in merged_affect:
        merged_affect[key] = round(clamp01(raw_affect.get(key, merged_affect[key])), 3)

    normalized_actions = []
    raw_actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
    for item in raw_actions[:3]:
        if not isinstance(item, dict):
            continue
        normalized_actions.append(
            {
                "type": str(item.get("type") or "animation"),
                "name": str(item.get("name") or "attend_user"),
                "intensity": round(clamp01(item.get("intensity", 0.5)), 3),
            }
        )
    if not normalized_actions:
        normalized_actions = actions

    return {"speech": speech, "affect": merged_affect, "actions": normalized_actions}


def parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        value = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def build_fallback_reply(user_text: str, snapshot: dict[str, Any], plain_text: str | None = None) -> dict[str, Any]:
    if plain_text:
        return {
            "speech": plain_text.strip(),
            "affect": snapshot["affect"],
            "actions": snapshot["actions"],
        }

    intent = detect_intent(user_text)
    template = random.choice(FALLBACK_RESPONSES.get(intent, FALLBACK_RESPONSES["_default"]))
    speech = template.format(
        provider_name=snapshot["provider"]["name"],
        summary=snapshot["summary"],
        voltage=rounded(snapshot["sensors"]["voltage"], 2),
        current_ma=round(float(snapshot["sensors"]["current_ma"])),
        temp_si=rounded(snapshot["sensors"]["temp_si"], 1),
        cpu_temp=rounded(snapshot["system"].get("cpu_temp"), 1) if snapshot["system"].get("cpu_temp") is not None else "n/a",
        gpu_temp=rounded(snapshot["system"].get("gpu_temp"), 1) if snapshot["system"].get("gpu_temp") is not None else "n/a",
        cpu_percent=rounded(snapshot["system"].get("cpu_percent"), 1) if snapshot["system"].get("cpu_percent") is not None else "n/a",
        battery_percent=rounded(snapshot["system"].get("battery_percent"), 1) if snapshot["system"].get("battery_percent") is not None else "n/a",
        ac_online=snapshot["system"].get("ac_online"),
        cpu_power_w=rounded(snapshot["system"].get("cpu_power_w"), 2) if snapshot["system"].get("cpu_power_w") is not None else "n/a",
        gpu_power_w=rounded(snapshot["system"].get("gpu_power_w"), 2) if snapshot["system"].get("gpu_power_w") is not None else "n/a",
        thermal_stress=f"{snapshot['derived']['thermal_stress']:.2f}",
        energy_stress=f"{snapshot['derived']['energy_stress']:.2f}",
        instability=f"{snapshot['derived']['instability']:.2f}",
    )
    return {"speech": speech, "affect": snapshot["affect"], "actions": snapshot["actions"]}


def extract_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        return ""
    choice = choices[0]
    if isinstance(choice, dict):
        message = choice.get("message")
        if isinstance(message, dict):
            content = message.get("content", "")
            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "text":
                        parts.append(str(item.get("text") or ""))
                return "".join(parts)
            return str(content or "")
        if "text" in choice:
            return str(choice.get("text") or "")
    return ""


def call_llm(user_text: str, snapshot: dict[str, Any]) -> dict[str, Any] | None:
    llm_config = get_llm_request_config()
    if llm_config is None:
        return None

    started = time.perf_counter()
    context = build_llm_context(snapshot, user_text)
    payload = {
        "model": llm_config["model"],
        "messages": [
            {"role": "system", "content": LLM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    "Respond as Soma. Reply in the same language as the user. "
                    "Use the current body state, fused somatic vector, machine telemetry, homeostasis, "
                    "short-term memory, and retrieved long-term memory below. "
                    "Mention concrete measurements when they answer the question."
                ),
            },
            {"role": "user", "content": safe_json_dumps(context)},
        ],
        "temperature": 0.2,
        "stream": False,
    }
    payload.update(llm_config.get("extra_payload", {}))
    body = safe_json_dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "latent-somatic/server",
    }
    if llm_config["api_key"]:
        headers["Authorization"] = f"Bearer {llm_config['api_key']}"

    request = urllib.request.Request(llm_config["endpoint"], data=body, headers=headers, method="POST")
    with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_S) as response:
        response_json = json.loads(response.read().decode("utf-8"))
    runtime["llm_last_success_at"] = time.monotonic()

    llm_ms = round((time.perf_counter() - started) * 1000.0, 3)
    content = extract_content(response_json)
    parsed = parse_llm_json(content)

    if parsed is None:
        reply = build_fallback_reply(user_text, snapshot, plain_text=content or "")
        reply["llm"] = {
            "available": bool(content),
            "mode": "fallback",
            "provider": llm_config["provider"],
            "model": llm_config["model"],
            "recovered": True,
            "latency_ms": llm_ms,
        }
        return reply

    normalized = normalize_llm_output(parsed, snapshot["affect"], snapshot["actions"])
    if not normalized["speech"]:
        normalized["speech"] = build_fallback_reply(user_text, snapshot)["speech"]
    normalized["llm"] = {
        "available": True,
        "mode": llm_config["provider"],
        "provider": llm_config["provider"],
        "model": llm_config["model"],
        "recovered": False,
        "latency_ms": llm_ms,
    }
    return normalized


def build_snapshot() -> dict[str, Any]:
    started = time.perf_counter()
    packet = provider.read()
    provider_ms = (time.perf_counter() - started) * 1000.0

    core = dict(packet["core"])
    system = dict(packet["system"])
    machine_vector = build_machine_state_vector(system)
    tensor = run_projector(core, machine_vector)
    affect = derive_affect(core, system)
    derived = derive_state(core, system, affect)
    homeostasis = build_homeostasis_state(core, system, affect, derived)
    actions = derive_actions(affect)
    provider_info = {
        "name": str(packet["provider"]),
        "is_real": bool(packet["is_real"]),
        "source_quality": rounded(system.get("source_quality"), 3) or 0.0,
    }
    scenario = classify_state(core, system, derived, packet.get("scenario"))
    snapshot = {
        "timestamp": float(packet["timestamp"]),
        "provider": provider_info,
        "sensors": core,
        "system": system,
        "raw": dict(packet.get("raw") or {}),
        "projector": tensor["projector"],
        "tensor": tensor,
        "machine_vector": machine_vector,
        "affect": affect,
        "derived": derived,
        "homeostasis": homeostasis,
        "actions": actions,
        "scenario": scenario,
        "provider_ms": round(provider_ms, 3),
        "projector_ms": tensor["projector_ms"],
    }
    snapshot["summary"] = build_summary(snapshot)
    snapshot["policy"] = build_policy_state(snapshot)
    apply_autonomic_rate(snapshot["policy"])
    snapshot["actuation"] = build_actuation_state(snapshot, snapshot["policy"])
    dispatch_actuation(snapshot)
    runtime["last_snapshot"] = snapshot
    remember_somatic_trace(snapshot)
    consolidate_memory(snapshot)
    return snapshot


def build_llm_status(snapshot: dict[str, Any], override: dict[str, Any] | None = None) -> dict[str, Any]:
    llm_config = get_llm_request_config()
    if not llm_runtime_available():
        status = {
            "available": False,
            "mode": "off" if not llm_mode_enabled() else "fallback",
            "provider": llm_config["provider"] if llm_config else "fallback",
            "model": llm_config["model"] if llm_config else None,
        }
    else:
        success_at = runtime.get("llm_last_success_at")
        failure_at = runtime.get("llm_last_failure_at")
        is_connected = success_at is not None and (failure_at is None or success_at >= failure_at)
        status = {
            "available": is_connected,
            "mode": LLM_MODE if is_connected else "fallback",
            "provider": llm_config["provider"] if llm_config else "fallback",
            "model": llm_config["model"] if llm_config else None,
        }
    if override:
        status.update(override)
    return status


def public_payload(snapshot: dict[str, Any], *, llm_override: dict[str, Any] | None = None) -> dict[str, Any]:
    llm_status = build_llm_status(snapshot, llm_override)
    return {
        "timestamp": snapshot["timestamp"],
        "provider": snapshot["provider"],
        "sensors": snapshot["sensors"],
        "system": snapshot["system"],
        "derived": snapshot["derived"],
        "projector": snapshot["projector"],
        "machine_vector": snapshot["machine_vector"],
        "llm": llm_status,
        "affect": snapshot["affect"],
        "homeostasis": snapshot["homeostasis"],
        "policy": snapshot["policy"],
        "actuation": snapshot["actuation"],
        "actions": snapshot["actions"],
        "scenario": snapshot["scenario"],
        "hz": runtime["hz"],
        "provider_supports_scenarios": provider.supports_scenarios(),
        "provider_ms": snapshot["provider_ms"],
        "projector_ms": snapshot["projector_ms"],
        "heatmap": snapshot["tensor"]["heatmap"],
        "norm": snapshot["tensor"]["norm"],
        "mean": snapshot["tensor"]["mean"],
        "std": snapshot["tensor"]["std"],
        "top_dims": snapshot["tensor"]["top_dims"],
        "top_vals": snapshot["tensor"]["top_vals"],
        "seg_energy": snapshot["tensor"]["seg_energy"],
    }


def severity_bucket(value: float, warn: float, critical: float) -> int:
    if value >= critical:
        return 2
    if value >= warn:
        return 1
    return 0


def maybe_autonomy_event(snapshot: dict[str, Any]) -> dict[str, Any] | None:
    if not AUTONOMY_ENABLED:
        return None

    auto = runtime["autonomy"]
    now = time.monotonic()
    derived = snapshot["derived"]
    cpu_percent = float(snapshot["system"].get("cpu_percent") or 0.0)
    ac_online = snapshot["system"].get("ac_online")
    scenario = snapshot["scenario"]

    thermal_bucket = severity_bucket(derived["thermal_stress"], 0.6, 0.75)
    energy_bucket = severity_bucket(derived["energy_stress"], 0.6, 0.75)
    instability_bucket = severity_bucket(derived["instability"], 0.45, 0.65)

    candidates: list[tuple[str, str, int]] = []
    if auto["last_scenario"] != scenario and scenario in {"overheat", "lowbatt", "fall", "spin", "heavyload", "cold"}:
        scenario_text = {
            "overheat": "Entering thermal stress state.",
            "lowbatt": "Entering low-energy state.",
            "fall": "Severe instability detected.",
            "spin": "Rotational anomaly detected.",
            "heavyload": "High-load state detected.",
            "cold": "Cold-state posture activated.",
        }[scenario]
        candidates.append((f"{scenario}_state", scenario_text, 2))

    if thermal_bucket > auto["thermal_bucket"]:
        candidates.append(("thermal_rise", "Thermal stress rising. I am redirecting attention toward cooling.", thermal_bucket))
    elif thermal_bucket == 0 and auto["thermal_bucket"] > 0:
        candidates.append(("thermal_recovery", "Thermal stress eased. My body state is recovering.", 1))

    if energy_bucket > auto["energy_bucket"]:
        candidates.append(("energy_drop", "Energy stress is rising. I am becoming more conservative.", energy_bucket))
    elif energy_bucket == 0 and auto["energy_bucket"] > 0:
        candidates.append(("energy_recovery", "Power state recovered enough to relax conservation behavior.", 1))

    if instability_bucket > auto["instability_bucket"]:
        candidates.append(("instability_rise", "Orientation stress increased. I am prioritizing balance.", instability_bucket))
    elif instability_bucket == 0 and auto["instability_bucket"] > 0:
        candidates.append(("stability_recovery", "Spatial stability is back within a comfortable range.", 1))

    if auto["last_cpu_percent"] is not None and abs(cpu_percent - auto["last_cpu_percent"]) > 35.0:
        label = "load_spike" if cpu_percent > auto["last_cpu_percent"] else "load_drop"
        text = f"System load changed sharply. CPU is now {rounded(cpu_percent, 1)} percent."
        candidates.append((label, text, 1))

    if auto["last_ac_online"] is not None and ac_online != auto["last_ac_online"] and ac_online is not None:
        label = "ac_online" if ac_online else "ac_offline"
        text = "External power connected." if ac_online else "External power disconnected."
        candidates.append((label, text, 1))

    auto["thermal_bucket"] = thermal_bucket
    auto["energy_bucket"] = energy_bucket
    auto["instability_bucket"] = instability_bucket
    auto["last_heat"] = derived["thermal_stress"]
    auto["last_energy"] = derived["energy_stress"]
    auto["last_instability"] = derived["instability"]
    auto["last_cpu_percent"] = cpu_percent
    auto["last_ac_online"] = ac_online
    auto["last_scenario"] = scenario

    if not candidates:
        return None
    if now - auto["last_emit"] < AUTONOMY_COOLDOWN_S:
        return None

    auto["last_emit"] = now
    candidates.sort(key=lambda item: item[2], reverse=True)
    event_name, text, _priority = candidates[0]
    return {
        "event": event_name,
        "text": text,
        "affect": snapshot["affect"],
        "actions": snapshot["actions"],
    }


async def broadcast(msg: dict[str, Any]):
    if not clients:
        return
    data = safe_json_dumps(msg)
    await asyncio.gather(*[client.send(data) for client in list(clients)], return_exceptions=True)


async def tick_loop():
    while True:
        hz = clamp(float(runtime["hz"]), 0.2, 20.0)
        runtime["hz"] = hz
        dt = 1.0 / hz
        started = time.monotonic()

        snapshot = build_snapshot()
        await broadcast({"type": "tick", **public_payload(snapshot)})

        event = maybe_autonomy_event(snapshot)
        if event:
            remember_episode(
                "autonomous_event",
                snapshot,
                event_name=event["event"],
                event_text=event["text"],
            )
            await broadcast(
                {
                    "type": "autonomous_event",
                    "text": event["text"],
                    "event": event["event"],
                    "affect": event["affect"],
                    "actions": event["actions"],
                    **public_payload(snapshot),
                }
            )

        elapsed = time.monotonic() - started
        await asyncio.sleep(max(0.0, dt - elapsed))


async def handler(websocket: ServerConnection):
    clients.add(websocket)
    remote = websocket.remote_address
    print(f"[WSS] Client connected: {remote} (total: {len(clients)})")

    snapshot = runtime["last_snapshot"] or build_snapshot()
    await websocket.send(
        safe_json_dumps(
            {
                "type": "init",
                "message": (
                    f"LSF connected. provider={snapshot['provider']['name']} "
                    f"real={snapshot['provider']['is_real']} projector={snapshot['projector']['mode']} "
                    f"llm={build_llm_status(snapshot)['mode']}."
                ),
                **public_payload(snapshot),
            }
        )
    )

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")
            if mtype == "chat":
                user_text = str(msg.get("text") or "").strip()
                if not user_text:
                    continue

                snapshot = build_snapshot()
                remember_dialogue_turn("user", user_text, snapshot)
                llm_meta_override = build_llm_status(snapshot)
                try:
                    llm_reply = await asyncio.to_thread(call_llm, user_text, snapshot)
                except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
                    runtime["llm_last_failure_at"] = time.monotonic()
                    print(f"[LLM] Request failed: {exc}")
                    llm_reply = None

                if llm_reply is None:
                    llm_reply = build_fallback_reply(user_text, snapshot)
                if "llm" in llm_reply:
                    llm_meta_override = llm_reply["llm"]
                remember_dialogue_turn("assistant", llm_reply["speech"], snapshot)
                remember_episode(
                    "chat",
                    snapshot,
                    user_text=user_text,
                    reply_text=llm_reply["speech"],
                )

                await websocket.send(
                    safe_json_dumps(
                        {
                            "type": "chat_reply",
                            "text": llm_reply["speech"],
                            "affect": llm_reply["affect"],
                            "actions": llm_reply["actions"],
                            **public_payload(snapshot, llm_override=llm_meta_override),
                        }
                    )
                )

            elif mtype == "set_scenario":
                scenario = str(msg.get("scenario") or "").strip()
                if scenario and provider.supports_scenarios() and provider.set_scenario(scenario):
                    print(f"[WSS] Scenario -> {scenario}")

            elif mtype == "set_hz":
                try:
                    runtime["hz"] = clamp(float(msg.get("hz", runtime["hz"])), 0.2, 20.0)
                except (TypeError, ValueError):
                    pass

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"[WSS] Client disconnected: {remote} (remaining: {len(clients)})")


async def main():
    parser = argparse.ArgumentParser(description="LSF WebSocket Server")
    parser.add_argument("--host", default=WS_HOST)
    parser.add_argument("--port", type=int, default=WS_PORT)
    args = parser.parse_args()

    print(f"[LSF] Starting WebSocket server on ws://{args.host}:{args.port}")
    print(f"[LSF] Sensor dims: {SENSOR_DIM} | Latent dims: {LLM_EMB_DIM}")
    print(f"[LSF] Provider: {provider.name} | is_real={provider.is_real}")
    print(f"[LSF] Projector: {projector_meta['mode']} | path={projector_meta['path']}")
    print(f"[LSF] Machine fusion: {machine_fusion_meta['mode']} | path={machine_fusion_meta['path']}")
    print(f"[LSF] LLM mode: {LLM_MODE}")
    if LLM_MODE == "deepseek":
        print(f"[LSF] DeepSeek endpoint: {DEEPSEEK_ENDPOINT} | model: {DEEPSEEK_MODEL}")
    elif LLM_MODE == "openai_compatible":
        print(f"[LSF] OpenAI-compatible endpoint: {LLM_ENDPOINT} | model: {LLM_MODEL}")
    print(f"[LSF] Default rate: {runtime['hz']} Hz")
    print(f"[LSF] Actuation: {'enabled' if ACTUATOR_ENABLED else 'disabled'} | transport={ACTUATOR_ENDPOINT or 'file'}")

    async with websockets.serve(handler, args.host, args.port):
        print("[LSF] Server READY - open docs/simulator.html in browser")
        tick_task = asyncio.create_task(tick_loop())
        try:
            await asyncio.Future()
        except (KeyboardInterrupt, asyncio.CancelledError):
            tick_task.cancel()
            print("\n[LSF] Server stopped.")


if __name__ == "__main__":
    asyncio.run(main())
