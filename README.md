<div align="center">
  <img src="docs/assets/LSF.png" alt="LSF Logo"/>

  # Project Latent-Somatic Fusion

  **Direct projection of continuous physical state into LLM latent space**

  [![C++](https://img.shields.io/badge/C%2B%2B-20-00599C?style=flat-square&logo=c%2B%2B)](https://isocpp.org/)
  [![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python)](https://python.org)
  [![PyTorch](https://img.shields.io/badge/PyTorch-2.11-EE4C2C?style=flat-square&logo=pytorch)](https://pytorch.org)
  [![llama.cpp](https://img.shields.io/badge/llama.cpp-latest-7C3AED?style=flat-square)](https://github.com/ggml-org/llama.cpp)
  [![CMake](https://img.shields.io/badge/CMake-3.20+-064F8C?style=flat-square&logo=cmake)](https://cmake.org)
  [![License](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
  [![Build](https://img.shields.io/badge/Build-passing-22c55e?style=flat-square)]()
  [![WebSocket](https://img.shields.io/badge/WebSocket-asyncio-0ea5e9?style=flat-square)]()

  ```text
  S ∈ ℝ¹¹  →  φ(S) = Vₛ ∈ ℝ⁴⁰⁹⁶  →  Concat(Vₛ, E_text)  →  LLM forward pass
  ```

  *The body shapes the words.*

</div>

---

## What is this?

An open-hardware, open-source research platform that enables a Large Language Model to **perceive continuous physical reality** — voltage, heat, gravity, rotation — not as text tokens, but as **raw vectors injected directly into the KV cache** via `llama_batch.embd`.

Physical variables alter the LLM's attention mechanism at the embedding level, bypassing the tokenizer entirely. The architecture is aligned with the VLA/sensor-aware LLM research emerging in 2024–2025 (LLaSA, OmniVLA, SensorLLM).

## Architecture

| Layer | Thread | Rate | Technology | Role |
| --- | --- | --- | --- | --- |
| **Autonomous NS** | dedicated | 100 Hz | I²C / Linux | Sensor polling, survival gate |
| **Somatic Projector** | cognitive | 5–20 Hz | LibTorch JIT | MLP: ℝ¹¹ → ℝ⁴⁰⁹⁶ |
| **Cognitive Engine** | cognitive | 5–20 Hz | llama.cpp | LLM inference with somatic injection |
| **WebSocket Server** | async | real-time | Python asyncio | Browser bridge, real tensor stream |

## Sensor Dimensions

| Index | Sensor | Unit | Hardware |
| --- | --- | --- | --- |
| 0 | Voltage | V | BQ34Z100 (BMS) |
| 1 | Current | mA | BQ34Z100 (BMS) |
| 2 | Temp Silicon | °C | TMP117 |
| 3 | Temp Motor L | °C | TMP117 |
| 4 | Temp Motor R | °C | TMP117 |
| 5–7 | Acceleration X/Y/Z | m/s² | ICM-42688-P |
| 8–10 | Gyroscope X/Y/Z | rad/s | ICM-42688-P |

## Quick Start

```bash
# 1. Build llama.cpp
git clone https://github.com/ggml-org/llama.cpp
cmake -S llama.cpp -B llama.cpp/build -DGGML_CUDA=OFF
cmake --build llama.cpp/build -j$(nproc)

# 2. Python environment
pip install torch sentence-transformers websockets pillow \
  --index-url https://download.pytorch.org/whl/cpu

# 3. Train somatic projector
python train/train_projector.py --epochs 200 --output weights/somatic_projector.pt

# 4. Build C++ binary
cmake -S . -B build \
  -DTORCH_DIR=$(python3 -c 'import torch; print(torch.utils.cmake_prefix_path)') \
  -DLLAMA_DIR=../llama.cpp
cmake --build build -j$(nproc)

# 5. Launch production stack (WebSocket server + real projector)
python3 server.py

# 6. Open the interface
cd docs && python3 -m http.server 8080
# → http://localhost:8080/simulator.html
```

## Repository Layout

```text
latent-somatic/
├── src/
│   ├── main.cpp              ← orchestration, 3-layer startup
│   ├── hw_interface.cpp      ← I²C polling (100 Hz) + sinusoidal mock
│   ├── somatic_projector.cpp ← LibTorch MLP forward pass
│   └── llm_bridge.cpp        ← llama_batch.embd injection into KV cache
├── include/                  ← C++ headers
├── train/
│   └── train_projector.py    ← InfoNCE contrastive training (CLIP-style)
├── weights/
│   ├── somatic_projector.pt  ← TorchScript (torch::jit::load in C++)
│   └── somatic_projector_adapter.pth
├── server.py                 ← WebSocket production server (real tensors)
├── docs/
│   ├── index.html            ← technical documentation
│   └── simulator.html        ← interactive entity body + live chat
└── CMakeLists.txt
```

## Key Technical Mechanisms

### Somatic Injection (`llm_bridge.cpp`)
```cpp
// The body root token: no tokenizer, raw float pointer
decode_batch_embd(somatic_vec, 1, n_embd_, seq_id=0, pos=0);
// Text tokens follow at pos=1..N
decode_batch_tokens(token_ids, seq_id=0, pos=1);
// Transformer attends over [Vₛ | text_tokens] natively
```

### Contrastive Training (`train/train_projector.py`)
```python
# InfoNCE symmetric loss (CLIP-style)
# Aligns physical states with semantic descriptions in ℝ⁴⁰⁹⁶
L = InfoNCE(project(sensor_state), text_adapter(text_embedding))
# Temperature τ learned: 14.2 → 17.2 over 200 epochs, best loss 0.93
```

### WebSocket Real-Time Bridge (`server.py`)
```python
# Real projector forward pass streamed to browser
somatic = projector(sensor_tensor)           # ℝ⁴⁰⁹⁶
heatmap = somatic[::16].tolist()            # 256 samples
broadcast({'type': 'tick', 'heatmap': heatmap, 'sensors': S, 'norm': ...})
```

## Related Research

| Paper | Year | Relevance |
| --- | --- | --- |
| **LLaSA** — Sensor-Aware LLM for IMU | 2025 | Identical projection-layer architecture |
| **OmniVLA** — Multi-Sensor Perception | 2025 | Per-sensor MLP → shared token space |
| **SensorLLM** — Aligning LLMs with Sensors | 2024–25 | Contrastive alignment of time-series |
| **LLaVA** — Language and Vision Assistant | 2023 | Same `llama_batch.embd` mechanism |
| **CLIP** — Contrastive Language-Image | 2021 | InfoNCE loss foundation |

## Hardware Bill of Materials

| Component | Part | Interface | Purpose |
| --- | --- | --- | --- |
| Battery Monitor | TI BQ34Z100-G1 | I²C 0x55 | Voltage, current |
| IMU | InvenSense ICM-42688-P | I²C 0x68 | 6-axis motion |
| Thermistor ×3 | TI TMP117 | I²C 0x48-4A | Silicon + motor temps |
| Compute | Raspberry Pi 5 / Jetson | GPIO | CPU/GPU inference |
| Motor Driver | PCA9685 | I²C | PWM actuation |

## Requirements

- **C++**: GCC ≥ 13, CMake ≥ 3.20 (`pip install cmake`)
- **Python**: 3.12+, PyTorch ≥ 2.3, websockets, sentence-transformers
- **Hardware**: Linux I²C bus (optional — mock mode works without)
- **LLM**: Any GGUF model via llama.cpp (optional for WebSocket mode)

---

<div align="center">
  <sub>Project Latent-Somatic Fusion v2.0 · C++ / LibTorch / llama.cpp / PyTorch / WebSocket</sub>
</div>
