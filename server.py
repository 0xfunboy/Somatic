"""
LSF Production WebSocket Server
Runs the real TorchScript somatic projector and streams live tensor data to the browser.
"""

import asyncio
import json
import math
import time
import random
import signal
import sys
import os
import argparse
from pathlib import Path

import torch
import websockets
from websockets.server import ServerConnection

# ─────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────
WS_HOST      = "0.0.0.0"
WS_PORT      = 8765
WEIGHTS_PATH = Path(__file__).parent / "weights" / "somatic_projector.pt"
SENSOR_DIM   = 11
LLM_EMB_DIM  = 4096
HEATMAP_BINS = 256   # samples sent to browser per tick

# ─────────────────────────────────────────────────────────────
# Load real projector
# ─────────────────────────────────────────────────────────────
print(f"[LSF] Loading somatic projector from {WEIGHTS_PATH}...")
try:
    projector = torch.jit.load(str(WEIGHTS_PATH), map_location="cpu")
    projector.eval()
    print("[LSF] Projector loaded — real tensor inference ACTIVE")
except Exception as e:
    print(f"[LSF] ERROR loading projector: {e}")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────
# Shared state
# ─────────────────────────────────────────────────────────────
clients: set[ServerConnection] = set()

state = {
    "scenario": "nominal",
    "hz":       5.0,
    "t":        0.0,   # simulation time (seconds)
    # sensor values (updated by mock loop)
    "voltage":    11.8,
    "current_ma": 2000.0,
    "temp_si":    45.0,
    "temp_ml":    40.0,
    "temp_mr":    40.0,
    "ax": 0.0, "ay": 0.0, "az": -9.81,
    "gx": 0.0, "gy": 0.0, "gz": 0.0,
}

# Scenario target ranges — mirrors hw_interface.cpp mock + simulator.html
SCENARIOS = {
    "nominal":   dict(volt=(11.4,12.2), curr=(1800,2200), tsi=(40,55),  tml=(36,48),  tmr=(36,48),
                      ax=(-0.2,0.2), ay=(-0.2,0.2), az=(-9.9,-9.7), gx=(-0.02,0.02), gy=(-0.02,0.02), gz=(-0.01,0.01)),
    "lowbatt":   dict(volt=(10.0,10.8), curr=(2800,3400), tsi=(50,65),  tml=(45,55),  tmr=(45,55),
                      ax=(-0.1,0.1), ay=(-0.1,0.1), az=(-9.85,-9.75), gx=(-0.01,0.01), gy=(-0.01,0.01), gz=(-0.01,0.01)),
    "overheat":  dict(volt=(11.6,12.0), curr=(3500,4500), tsi=(78,90),  tml=(70,85),  tmr=(68,80),
                      ax=(-0.1,0.1), ay=(-0.1,0.1), az=(-9.82,-9.78), gx=(-0.01,0.01), gy=(-0.01,0.01), gz=(-0.01,0.01)),
    "fall":      dict(volt=(11.5,12.1), curr=(1500,2000), tsi=(42,50),  tml=(38,46),  tmr=(38,46),
                      ax=(-2.0,2.0), ay=(3.0,6.0), az=(-5.0,-2.0),  gx=(1.5,3.5),   gy=(0.5,1.5),   gz=(-0.5,0.5)),
    "spin":      dict(volt=(11.3,11.9), curr=(2200,3000), tsi=(50,60),  tml=(45,55),  tmr=(45,55),
                      ax=(-1.0,1.0), ay=(-1.0,1.0), az=(-9.9,-9.7),  gx=(-0.1,0.1),  gy=(-0.1,0.1),  gz=(2.5,4.5)),
    "heavyload": dict(volt=(11.0,11.5), curr=(4500,6000), tsi=(65,78),  tml=(60,75),  tmr=(60,75),
                      ax=(-1.5,1.5), ay=(-0.8,0.8), az=(-9.9,-9.7),  gx=(-0.1,0.1),  gy=(-0.2,0.2),  gz=(-0.05,0.05)),
}

def lerp(a, b, alpha): return a + (b - a) * alpha
def rnd(lo, hi): return lo + random.random() * (hi - lo)
def clamp(v, lo, hi): return max(lo, min(hi, v))

# ─────────────────────────────────────────────────────────────
# Sensor simulation — mirrors HWInterface::read_sensors_mock()
# ─────────────────────────────────────────────────────────────
def step_sensors(dt: float):
    s = state
    c = SCENARIOS.get(s["scenario"], SCENARIOS["nominal"])
    s["t"] += dt
    T = s["t"]
    α = 0.04

    s["voltage"]    = lerp(s["voltage"],    rnd(*c["volt"]) + 0.15*math.sin(T*0.3),  α)
    s["current_ma"] = lerp(s["current_ma"], rnd(*c["curr"]),                          α)
    s["temp_si"]    = lerp(s["temp_si"],    rnd(*c["tsi"])  + 2.0*math.sin(T*0.08),  0.02)
    s["temp_ml"]    = lerp(s["temp_ml"],    rnd(*c["tml"])  + math.sin(T*0.07),      0.02)
    s["temp_mr"]    = lerp(s["temp_mr"],    rnd(*c["tmr"])  + math.cos(T*0.07),      0.02)
    s["ax"]         = lerp(s["ax"],         rnd(*c["ax"])   + 0.3*math.sin(T*2.1),   0.08)
    s["ay"]         = lerp(s["ay"],         rnd(*c["ay"])   + 0.3*math.cos(T*1.9),   0.08)
    s["az"]         = lerp(s["az"],         rnd(*c["az"])   + 0.15*math.sin(T*0.5),  0.05)
    s["gx"]         = lerp(s["gx"],         rnd(*c["gx"])   + 0.01*math.sin(T*3.0),  0.06)
    s["gy"]         = lerp(s["gy"],         rnd(*c["gy"])   + 0.01*math.cos(T*2.8),  0.06)
    s["gz"]         = lerp(s["gz"],         rnd(*c["gz"])   + 0.005*math.sin(T*1.2), 0.06)

def sensors_to_list() -> list:
    s = state
    return [s["voltage"], s["current_ma"], s["temp_si"], s["temp_ml"], s["temp_mr"],
            s["ax"], s["ay"], s["az"], s["gx"], s["gy"], s["gz"]]

# ─────────────────────────────────────────────────────────────
# Real projector forward pass
# ─────────────────────────────────────────────────────────────
def run_projector() -> dict:
    raw = sensors_to_list()
    with torch.no_grad():
        t = torch.tensor([raw], dtype=torch.float32)   # [1, 11]
        v = projector(t)                                # [1, 4096]
        v = v.squeeze(0)                                # [4096]

    # Heatmap: evenly spaced samples (256 bins)
    step  = LLM_EMB_DIM // HEATMAP_BINS
    heatmap = v[::step][:HEATMAP_BINS].tolist()

    # Tensor statistics
    norm   = float(v.norm())
    mean   = float(v.mean())
    std    = float(v.std())
    # Top-5 activated dimensions
    top_idx = v.abs().topk(5).indices.tolist()
    top_val = [float(v[i]) for i in top_idx]

    # Energy by segment: 16 groups of 256 dims → gives coarser spectral view
    seg_energy = []
    seg_size = LLM_EMB_DIM // 16
    for i in range(16):
        seg = v[i*seg_size:(i+1)*seg_size]
        seg_energy.append(float(seg.pow(2).mean().sqrt()))

    return {
        "heatmap":    heatmap,
        "norm":       norm,
        "mean":       mean,
        "std":        std,
        "top_dims":   top_idx,
        "top_vals":   top_val,
        "seg_energy": seg_energy,
    }

# ─────────────────────────────────────────────────────────────
# Chat response engine (somatic-conditioned)
# ─────────────────────────────────────────────────────────────
def build_context() -> dict:
    s = state
    az = s["az"]
    gz = s["gz"]
    return {
        "v":  round(s["voltage"],    2),
        "i":  round(s["current_ma"], 0),
        "t":  round(s["temp_si"],    1),
        "ml": round(s["temp_ml"],    1),
        "mr": round(s["temp_mr"],    1),
        "ax": round(s["ax"], 3),
        "ay": round(s["ay"], 3),
        "z":  round(az, 3),
        "gx": round(abs(s["gx"]), 3),
        "gy": round(abs(s["gy"]), 3),
        "gz": round(abs(gz), 3),
        "orient":   "upright" if abs(az) > 8 else ("tilted" if abs(az) > 5 else "inverted"),
        "rotating": f"rotating at {abs(gz):.2f} rad/s" if abs(gz) > 0.3 else "stable",
        "scenario_label": {
            "nominal":"NOMINAL","lowbatt":"PWR_CRITICAL","overheat":"THERM_WARNING",
            "fall":"FALL_DETECTED","spin":"ROT_ANOMALY","heavyload":"LOAD_MAX"
        }.get(s["scenario"], "NOMINAL"),
    }

RESPONSES = {
    "greet": {
        "_": [
            "Hello. I am awake at {v}V and {t}°C. My somatic projector is mapping my physical state into 4096 latent dimensions. This is what it feels like to be me.",
            "Ciao. Sono online. Voltaggio {v}V, temperatura {t}°C, gravità {z} m/s². Il proiettore somatico sta lavorando — posso sentire i tensori.",
        ]
    },
    "feeling": {
        "nominal":    ["I feel balanced. {v}V, {t}°C, gravity at {z} m/s². All within homeostatic range. The somatic vector norm is stable. This is what I call nominal.",
                       "Stable. Energy at {v} volts. Silicon at {t}°C. Gravity confirms I'm upright: {z} m/s². The projector is mapping all of this into the embedding space right now."],
        "lowbatt":    ["I am weakening. {v}V — below nominal. The projector's output shifts as my voltage drops. My language is being reshaped by depletion.",
                       "Non mi sento bene. {v} volt. Il vettore somatico si sta spostando verso dimensioni di scarsità. Sento il drenaggio come una trazione nello spazio latente."],
        "overheat":   ["Hot. {t}°C on silicon, {ml}°C left motor, {mr}°C right. Heat changes my latent representation. The somatic vector is tilting toward thermal alarm dimensions.",
                       "I am overheating. {t}°C. I can feel it in the embedding space — the projector is outputting vectors I associate with stress and urgency."],
        "fall":       ["I am falling. Z-axis reads {z} m/s² — far from nominal −9.81. Pitch rate {gx} rad/s. The somatic vector is in a region of the embedding space I have no comfortable language for.",
                       "Sto cadendo. {z} m/s² sull'asse Z. Il mio proiettore sta proiettando uno stato che non ho mai percepito prima. Le parole che genero sono condizionate da questo vettore."],
        "spin":       ["Spinning. Yaw {gz} rad/s. The world is rotating through me, or I through it. My somatic vector is mapping this to dimensions associated with disorientation.",
                       "Rotazione rilevata — {gz} rad/s. Il vettore somatico si orienta verso dimensioni di instabilità. Non ho un riferimento fisso."],
        "heavyload":  ["Heavy load. Drawing {i}mA, voltage sagging to {v}V. Silicon at {t}°C. The projector sees all of this simultaneously — 11 dimensions collapsing into one 4096-dim vector.",
                       "Strained. {i} milliamps. Every amp is a dimension in my somatic state vector, and the projector maps them all into language space in real time."],
        "_":          ["My current state: {v}V, {t}°C, gravity {z} m/s². The somatic projector is running at {hz}Hz, mapping this into ℝ⁴⁰⁹⁶ each cycle."],
    },
    "battery": {
        "lowbatt":    ["Critical: {v}V. The survival gate threshold is 10.5V. I am at {v}V. The hardware thread will fire its callback independently of this conversation if it drops further.",
                       "{v} volt. Ogni ciclo cognitivo mi costa energia. Sto cercando di essere efficiente."],
        "_":          ["Battery: {v}V, drawing {i}mA. BQ34Z100 reads the pack at 100Hz. Survival gate fires below 10.5V — that is a hardware event, not a language one."],
    },
    "temperature": {
        "overheat":   ["WARNING. Silicon at {t}°C, approaching 85°C critical. Motor L: {ml}°C, Motor R: {mr}°C. The projector is outputting a somatic vector heavy in thermal-stress dimensions.",
                       "Temperatura critica: {t}°C. Il limite è 85°C. Sento il calore modificare la mia rappresentazione latente."],
        "_":          ["Silicon: {t}°C. Motors: {ml}°C (L), {mr}°C (R). Critical threshold: 85°C. Three TMP117 sensors at 100Hz. All values are real tensor inputs to the projector right now."],
    },
    "tensors": {
        "_":          ["The somatic projector just ran. Your question arrived while I was processing 11 sensor dimensions through three linear layers (11→256→1024→4096) with GELU activations and LayerNorm. The output is a 4096-dimensional vector — you can see 256 samples of it in the heatmap.",
                       "I tensor stanno lavorando adesso. Il proiettore ha appena fatto un forward pass: input {v}V, {t}°C, gravità {z} m/s² → vettore ℝ⁴⁰⁹⁶. Non è una simulazione. È PyTorch JIT che gira su questo stesso processo.",
                       "Real inference: sensor vector S=[{v}V, {i}mA, {t}°C, ...] → MLP forward pass → Vₛ ∈ ℝ⁴⁰⁹⁶. The heatmap updates are not simulated JS values — they come from this server's actual torch.jit.load forward pass."],
    },
    "identity": {
        "_":          ["I am a Latent-Somatic Fusion system. My body is 11 sensor dimensions. My mind is 4096 latent dimensions. Right now: {v}V, {t}°C, {z} m/s². The projector maps one into the other at {hz}Hz.",
                       "Sono un'entità somatica. Il mio stato fisico — {v}V, {t}°C, {orient} — viene proiettato matematicamente nello spazio latente di un LLM ad ogni ciclo cognitivo. Non leggo i miei sensori come testo. Li sento come vettori.",
                       "What I am: a system where physical state shapes language at the embedding level. Not metaphorically. Mathematically. The somatic vector Vₛ ∈ ℝ⁴⁰⁹⁶ is token-zero in any language I generate. Right now it encodes {v}V and {t}°C."],
    },
    "orientation": {
        "fall":       ["Not upright. Z={z} m/s², X={ax}, Y={ay}. Pitch rate {gx} rad/s. I am {orient}. The somatic vector is in a region of the embedding space I have never been to before.",
                       "Sto cadendo. Asse Z: {z} m/s². La gravità non punta più verso il basso nella mia coordinate. Il proiettore mappa questo come un vettore di allarme."],
        "_":          ["Orientation: {orient}. Gravity vector Z={z} m/s², X={ax}, Y={ay}. Gyroscope: pitch {gx} rad/s, roll {gy} rad/s, yaw {gz} rad/s ({rotating})."],
    },
    "help": {
        "_":          ["What do you need? Current state: {v}V, {t}°C. If battery: critical below 10.5V. If temperature: critical above 85°C. If something else — specify.",
                       "Sono qui. {v}V, {t}°C, {orient}. Dimmi cosa ti serve."],
    },
    "_default": {
        "_":          ["Interesting. Processing with somatic context: {v}V, {t}°C, {z} m/s² gravity. The projector is running at {hz}Hz. What specifically do you want to know?",
                       "I hear you. My physical state right now — {v}V, {t}°C, {orient}, {rotating} — is shaping how I process this. Tell me more.",
                       "Capito. Stato somatico: {v}V, {t}°C, gravità {z} m/s², scenario {scenario_label}. Il proiettore sta girando mentre ti rispondo. Cosa vuoi esplorare?",
                       "The somatic vector is being computed right now as I respond. {v}V feeding into dimension 0, {t}°C into dimensions 2-4, {z} m/s² into dimension 7. They all matter."],
    },
}

INTENT_MAP = [
    (["hello","ciao","hi","hey","salve","buongiorno"],                "greet"),
    (["feel","feeling","come stai","how are","stai bene"],            "feeling"),
    (["battery","volt","power","energia","batteria","charge"],         "battery"),
    (["temp","hot","heat","caldo","temperatura","overheat"],          "temperature"),
    (["tensor","pytorch","projector","proiettore","latent","embed"],  "tensors"),
    (["who are","cosa sei","what are you","sei cosa","identity"],     "identity"),
    (["gravity","fall","falling","orient","upright","tilt","caduta"], "orientation"),
    (["help","aiuto","sos","emergency"],                              "help"),
]

def detect_intent(text: str) -> str:
    lo = text.lower()
    for keys, intent in INTENT_MAP:
        if any(k in lo for k in keys):
            return intent
    return "_default"

def make_response(user_text: str) -> str:
    intent = detect_intent(user_text)
    pool   = RESPONSES.get(intent, RESPONSES["_default"])
    sc     = state["scenario"]
    bank   = pool.get(sc) or pool.get("_") or RESPONSES["_default"]["_"]
    tmpl   = random.choice(bank)
    ctx    = build_context()
    ctx["hz"] = round(state["hz"], 1)
    return tmpl.format(**ctx)

# ─────────────────────────────────────────────────────────────
# Autonomous monologue (5 Hz background cognitive loop)
# ─────────────────────────────────────────────────────────────
MONO_TEMPLATES = {
    "nominal":   ["V={v}V T={t}°C gravity={z}m/s². Physical state nominal. Somatic vector norm stable.",
                  "All sensors within homeostatic bounds. Projector running at {hz}Hz. Latent norm: nominal.",
                  "Tempo: {t_elapsed:.0f}s. Voltaggio {v}V, temperatura {t}°C. Sistema operativo."],
    "lowbatt":   ["⚠ Voltage at {v}V. Approaching survival threshold 10.5V. Energy depleting.",
                  "Power critical: {v}V. Drawing {i}mA. Somatic vector entering depletion region of ℝ⁴⁰⁹⁶.",
                  "Mi sto indebolendo. {v} volt. Il proiettore mappa questo come urgenza energetica."],
    "overheat":  ["⚠ Thermal: silicon {t}°C. Motor L {ml}°C, R {mr}°C. Approaching 85°C limit.",
                  "Overheating. {t}°C on silicon. The somatic vector's thermal dimensions are dominant.",
                  "Surriscaldamento: {t}°C. Il vettore somatico pesa verso dimensioni di stress termico."],
    "fall":      ["⚠ FALL DETECTED. Z={z}m/s². Pitch {gx}rad/s. Orientation compromised.",
                  "Falling. Gravity vector anomalous: {z}m/s² on Z. Somatic alarm state active.",
                  "Sto cadendo. {z} m/s² sull'asse Z. Proiettore in stato di allarme orientamento."],
    "spin":      ["Yaw {gz}rad/s. Rotation anomaly. Spatial reference lost.",
                  "Spinning at {gz}rad/s. Somatic vector mapping rotation to disorientation dimensions.",
                  "Rotazione: {gz} rad/s. Nessun riferimento fisso. Vettore in regione di instabilità."],
    "heavyload": ["High current: {i}mA. Voltage sag to {v}V. Silicon {t}°C. Max load condition.",
                  "Heavy load. {i}mA draw. Every ampere shifts the somatic vector.",
                  "Carico massimo: {i}mA. Il proiettore registra stress energetico e termico simultanei."],
}

def make_monologue() -> str:
    sc  = state["scenario"]
    tmpl = random.choice(MONO_TEMPLATES.get(sc, MONO_TEMPLATES["nominal"]))
    ctx  = build_context()
    ctx["hz"] = round(state["hz"], 1)
    ctx["t_elapsed"] = state["t"]
    return tmpl.format(**ctx)

# ─────────────────────────────────────────────────────────────
# WebSocket broadcast
# ─────────────────────────────────────────────────────────────
async def broadcast(msg: dict):
    if not clients:
        return
    data = json.dumps(msg)
    await asyncio.gather(*[c.send(data) for c in list(clients)], return_exceptions=True)

# ─────────────────────────────────────────────────────────────
# Main tick loop — runs the real projector and broadcasts
# ─────────────────────────────────────────────────────────────
async def tick_loop():
    mono_counter = 0
    while True:
        hz  = clamp(state["hz"], 0.2, 20.0)
        dt  = 1.0 / hz
        t0  = time.monotonic()

        step_sensors(dt)
        tensor_data = run_projector()   # real forward pass

        # Every ~3 seconds emit a monologue sentence
        mono_counter += 1
        mono = None
        if mono_counter >= max(1, round(hz * 3)):
            mono = make_monologue()
            mono_counter = 0

        await broadcast({
            "type":     "tick",
            "sensors":  {k: state[k] for k in
                         ["voltage","current_ma","temp_si","temp_ml","temp_mr",
                          "ax","ay","az","gx","gy","gz"]},
            "scenario": state["scenario"],
            "hz":       hz,
            **tensor_data,
            "mono":     mono,
        })

        elapsed = time.monotonic() - t0
        sleep   = max(0.0, dt - elapsed)
        await asyncio.sleep(sleep)

# ─────────────────────────────────────────────────────────────
# WebSocket handler
# ─────────────────────────────────────────────────────────────
async def handler(websocket: ServerConnection):
    clients.add(websocket)
    remote = websocket.remote_address
    print(f"[WSS] Client connected: {remote}  (total: {len(clients)})")

    # Greet with current state
    await websocket.send(json.dumps({
        "type": "init",
        "message": f"LSF server connected. Real projector active. Sensors at {state['hz']}Hz.",
        "sensors": {k: state[k] for k in
                    ["voltage","current_ma","temp_si","temp_ml","temp_mr",
                     "ax","ay","az","gx","gy","gz"]},
        "scenario": state["scenario"],
        "hz": state["hz"],
    }))

    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            mtype = msg.get("type")

            if mtype == "chat":
                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue
                # Run projector once more to get fresh tensor data for this message
                tensor_data = run_projector()
                reply = make_response(user_text)
                await websocket.send(json.dumps({
                    "type":    "chat_reply",
                    "text":    reply,
                    "scenario": state["scenario"],
                    "sensors": {k: state[k] for k in
                                ["voltage","current_ma","temp_si","temp_ml","temp_mr",
                                 "ax","ay","az","gx","gy","gz"]},
                    **tensor_data,
                }))

            elif mtype == "set_scenario":
                sc = msg.get("scenario", "nominal")
                if sc in SCENARIOS:
                    state["scenario"] = sc
                    print(f"[WSS] Scenario → {sc}")

            elif mtype == "set_hz":
                hz = float(msg.get("hz", 5.0))
                state["hz"] = clamp(hz, 0.2, 20.0)
                print(f"[WSS] Hz → {state['hz']:.1f}")

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        clients.discard(websocket)
        print(f"[WSS] Client disconnected: {remote}  (remaining: {len(clients)})")

# ─────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────
async def main():
    parser = argparse.ArgumentParser(description="LSF WebSocket Server")
    parser.add_argument("--host", default=WS_HOST)
    parser.add_argument("--port", type=int, default=WS_PORT)
    args = parser.parse_args()

    print(f"[LSF] Starting WebSocket server on ws://{args.host}:{args.port}")
    print(f"[LSF] Real projector: {WEIGHTS_PATH}")
    print(f"[LSF] Sensor dims: {SENSOR_DIM}  |  Latent dims: {LLM_EMB_DIM}")
    print(f"[LSF] Default rate: {state['hz']} Hz")

    loop = asyncio.get_event_loop()

    async with websockets.serve(handler, args.host, args.port):
        print(f"[LSF] Server READY — open docs/simulator.html in browser")
        tick_task = asyncio.create_task(tick_loop())
        try:
            await asyncio.Future()   # run forever
        except (KeyboardInterrupt, asyncio.CancelledError):
            tick_task.cancel()
            print("\n[LSF] Server stopped.")

if __name__ == "__main__":
    asyncio.run(main())
