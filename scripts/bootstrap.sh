#!/usr/bin/env bash
# Sets up dependencies, builds the C++ binary, and runs the Python training.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLAMA_DIR="${ROOT}/../llama.cpp"
WEIGHTS="${ROOT}/weights/somatic_projector.pt"

echo "=== [1/4] llama.cpp ==="
if [ ! -d "$LLAMA_DIR" ]; then
    git clone https://github.com/ggml-org/llama.cpp "$LLAMA_DIR"
fi
cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" -DLLAMA_CUDA=ON -DCMAKE_BUILD_TYPE=Release -DLLAMA_BUILD_TESTS=OFF
cmake --build "$LLAMA_DIR/build" --config Release -j"$(nproc)"

echo "=== [2/4] Python deps ==="
pip install -r "${ROOT}/train/requirements.txt" -q

echo "=== [3/4] Training SomaticProjector ==="
if [ ! -f "$WEIGHTS" ]; then
    python "${ROOT}/train/train_projector.py" \
        --epochs 200 \
        --batch-size 32 \
        --output "$WEIGHTS"
else
    echo "Weights already exist at $WEIGHTS — skipping training. Delete to retrain."
fi

echo "=== [4/4] CMake build ==="
TORCH_CMAKE="$(python3 -c 'import torch; print(torch.utils.cmake_prefix_path)')"
cmake -S "$ROOT" -B "$ROOT/build" \
    -DCMAKE_BUILD_TYPE=Release \
    -DTORCH_DIR="$TORCH_CMAKE" \
    -DLLAMA_DIR="$LLAMA_DIR"
cmake --build "$ROOT/build" -j"$(nproc)"

echo ""
echo "=== Done ==="
echo "Run: ${ROOT}/build/latent_somatic /path/to/llama3-8b-q4.gguf"
