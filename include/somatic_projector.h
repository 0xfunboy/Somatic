#pragma once
#include <torch/torch.h>
#include <torch/script.h>
#include <optional>
#include "hw_interface.h"

// Dimensionality constants — update to match the target LLM.
static constexpr int SENSOR_DIM   = HardwareState::DIM;  // 11
static constexpr int HIDDEN_1     = 256;
static constexpr int HIDDEN_2     = 1024;
static constexpr int LLM_EMB_DIM  = 4096; // LLaMA-3 8B / 70B share this

// MLP: R^SENSOR_DIM → R^LLM_EMB_DIM
// No final activation so the output can roam freely in the LLM's embedding space.
// Layer norm on output keeps the L2 norm comparable to real text token embeddings
// and prevents the somatic vector from dominating cross-attention.
struct SomaticProjectorImpl : torch::nn::Module {
    torch::nn::Linear    fc1{nullptr}, fc2{nullptr}, fc3{nullptr};
    torch::nn::LayerNorm ln{nullptr};

    SomaticProjectorImpl();
    torch::Tensor forward(torch::Tensor x);
};
TORCH_MODULE(SomaticProjector);

// project_state: if a trained JIT module is provided, use it (preferred);
// otherwise fall back to the untrained nn::Module (random output, for dev).
torch::Tensor project_state(const HardwareState& state,
                            const torch::Device& device,
                            torch::jit::Module* jit_proj,
                            SomaticProjector* nn_proj = nullptr);
