#include "somatic_projector.h"

SomaticProjectorImpl::SomaticProjectorImpl() {
    fc1 = register_module("fc1", torch::nn::Linear(SENSOR_DIM, HIDDEN_1));
    fc2 = register_module("fc2", torch::nn::Linear(HIDDEN_1, HIDDEN_2));
    fc3 = register_module("fc3", torch::nn::Linear(HIDDEN_2, LLM_EMB_DIM));
    // LayerNorm over LLM_EMB_DIM keeps L2-norm compatible with text token embeddings.
    ln  = register_module("ln",  torch::nn::LayerNorm(
              torch::nn::LayerNormOptions({LLM_EMB_DIM}).elementwise_affine(true)));
}

torch::Tensor SomaticProjectorImpl::forward(torch::Tensor x) {
    // GELU gives smoother gradients than ReLU for embedding-space projection.
    x = torch::gelu(fc1->forward(x));
    x = torch::gelu(fc2->forward(x));
    x = fc3->forward(x);       // no activation: free range in latent space
    return ln->forward(x);     // normalize so norm ≈ 1, matching token embeddings
}

torch::Tensor project_state(const HardwareState& state,
                            const torch::Device& device,
                            torch::jit::Module* jit_proj,
                            SomaticProjector* nn_proj) {
    float raw[HardwareState::DIM];
    state.to_array(raw);

    torch::NoGradGuard no_grad;
    auto t = torch::from_blob(raw, {1, HardwareState::DIM}, torch::kFloat32)
                 .clone()
                 .to(device);

    if (jit_proj) {
        // Trained TorchScript module — preferred path
        return jit_proj->forward({t}).toTensor();
    }
    // Untrained nn::Module fallback
    return (*nn_proj)->forward(t);
}
