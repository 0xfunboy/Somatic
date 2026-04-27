#!/usr/bin/env bash
# Sets up dependencies, builds llama.cpp + C++ binary, and trains SomaticProjector if weights are missing.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LLAMA_DIR="${LLAMA_CPP_ROOT:-/home/funboy/llama.cpp}"
WEIGHTS="${ROOT}/weights/somatic_projector.pt"

echo "=== [1/4] llama.cpp ==="

if [ ! -d "$LLAMA_DIR" ]; then
    echo "Missing llama.cpp checkout at $LLAMA_DIR"
    echo "Set LLAMA_CPP_ROOT or create /home/funboy/llama.cpp before running bootstrap."
    exit 1
fi

CUDA_FLAG="-DGGML_CUDA=OFF"
if command -v nvcc >/dev/null 2>&1; then
    CUDA_FLAG="-DGGML_CUDA=ON"
fi

echo "Using llama.cpp at: $LLAMA_DIR"
echo "CUDA flag: $CUDA_FLAG"

cmake -S "$LLAMA_DIR" -B "$LLAMA_DIR/build" \
    "$CUDA_FLAG" \
    -DCMAKE_BUILD_TYPE=Release \
    -DLLAMA_BUILD_TESTS=OFF \
    -DLLAMA_BUILD_EXAMPLES=OFF \
    -DLLAMA_BUILD_SERVER=OFF

cmake --build "$LLAMA_DIR/build" --config Release -j"$(nproc)"

echo "=== [2/4] Python deps ==="

python3 -m pip install --user --break-system-packages -r "${ROOT}/train/requirements.txt" || \
python3 -m pip install --user -r "${ROOT}/train/requirements.txt"

echo "=== [3/4] Training SomaticProjector ==="

mkdir -p "${ROOT}/weights"

if [ ! -f "$WEIGHTS" ]; then
    python3 "${ROOT}/train/train_projector.py" \
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
echo "C++ binary:"
echo "${ROOT}/build/latent_somatic"
echo ""
echo "Run example:"
echo "${ROOT}/build/latent_somatic /path/to/model.gguf"