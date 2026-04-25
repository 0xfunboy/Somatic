#include <iostream>
#include <thread>
#include <chrono>
#include <atomic>
#include <csignal>
#include <torch/torch.h>
#include <torch/script.h>

#include "hw_interface.h"
#include "somatic_projector.h"
#include "llm_bridge.h"

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------

static std::atomic<bool> g_running{true};

void signal_handler(int) { g_running.store(false); }

// Hard-realtime survival callback — called from HWInterface's sensor thread.
// Must be lock-free: no heap alloc, no printf (use write(2) if needed).
void on_survival_event(const HardwareState& s) {
    // TODO: trigger motor-shutdown GPIO, activate buzzer, etc.
    // This executes in the hardware polling thread at 100 Hz — do not block.
    (void)s;
}

// ---------------------------------------------------------------------------
// Cognitive loop (5 Hz — LLM-rate limited)
// ---------------------------------------------------------------------------

void cognitive_loop(HWInterface& hw,
                    torch::jit::Module* jit_proj,
                    SomaticProjector* nn_proj,
                    LLMBridge& llm,
                    const torch::Device& device) {
    // A minimal user prompt that asks the system to introspect.
    // In production this comes from a real IO channel (serial, socket, etc.)
    const std::string user_prompt =
        "Describe your current physical condition in one sentence.";

    while (g_running.load()) {
        auto t0 = std::chrono::steady_clock::now();

        // 1. Get latest sensor snapshot (non-blocking — data is always fresh from hw thread)
        HardwareState state = hw.snapshot();

        // 2. Project physical state → latent vector on device
        torch::Tensor somatic = project_state(state, device, jit_proj, nn_proj);
        // somatic: [1, LLM_EMB_DIM] on GPU (or CPU if no CUDA)

        // 3. Move to CPU and get raw pointer for llama.cpp (expects host float*)
        auto somatic_cpu = somatic.squeeze(0).to(torch::kCPU).contiguous();
        const float* sv  = somatic_cpu.data_ptr<float>();

        // 4. LLM inference with somatic vector injected as token-0
        std::string response = llm.generate(sv, LLM_EMB_DIM, user_prompt);

        std::cout << "[SOMA] V=" << state.voltage
                  << "V T=" << state.temp_silicon << "°C "
                  << "acc=[" << state.acc_x << "," << state.acc_y << "," << state.acc_z << "]\n"
                  << "[LLM]  " << response << "\n\n";

        // 5. Sleep to maintain 5 Hz cognition rate, accounting for inference time
        auto elapsed = std::chrono::steady_clock::now() - t0;
        auto sleep_ns = std::chrono::milliseconds(200) - elapsed;
        if (sleep_ns.count() > 0)
            std::this_thread::sleep_for(sleep_ns);
    }
}

// ---------------------------------------------------------------------------
// main
// ---------------------------------------------------------------------------

int main(int argc, char** argv) {
    std::signal(SIGINT,  signal_handler);
    std::signal(SIGTERM, signal_handler);

    // --- Device selection ---
    torch::Device device = torch::cuda::is_available()
                         ? torch::Device(torch::kCUDA, 0)
                         : torch::Device(torch::kCPU);
    std::cout << "[INIT] LibTorch device: "
              << (device.is_cuda() ? "CUDA" : "CPU") << "\n";

    // --- LLM config ---
    LLMConfig llm_cfg;
    llm_cfg.model_path    = (argc > 1) ? argv[1] : "models/llama3-8b-q4.gguf";
    llm_cfg.n_gpu_layers  = 99;
    llm_cfg.max_new_tokens = 128;

    LLMBridge llm(llm_cfg);
    if (!llm.init()) {
        std::cerr << "[INIT] LLM init failed — check model path: "
                  << llm_cfg.model_path << "\n";
        return 1;
    }
    std::cout << "[INIT] LLM ready\n";

    // --- SomaticProjector ---
    // Try to load a trained TorchScript module (saved by train_projector.py).
    // Fall back to an untrained nn::Module if no weights are available.
    const std::string weights_path = "weights/somatic_projector.pt";
    std::unique_ptr<torch::jit::Module> jit_proj;
    std::unique_ptr<SomaticProjector>   nn_proj_holder;

    try {
        jit_proj = std::make_unique<torch::jit::Module>(
            torch::jit::load(weights_path, device));
        jit_proj->eval();
        std::cout << "[INIT] Loaded TorchScript projector from " << weights_path << "\n";
    } catch (const std::exception& e) {
        std::cout << "[INIT] No trained weights (" << e.what()
                  << ") — projector output is random noise.\n"
                  << "       Run train/train_projector.py first for aligned inference.\n";
        nn_proj_holder = std::make_unique<SomaticProjector>();
        (*nn_proj_holder)->to(device);
        (*nn_proj_holder)->eval();
    }

    torch::jit::Module* jit_proj_ptr = jit_proj.get();
    SomaticProjector*   nn_proj_ptr  = nn_proj_holder.get();

    // --- Hardware interface ---
    HWInterface hw(on_survival_event);
    hw.start();
    std::cout << "[INIT] HW interface started (real=" << hw.is_hardware_available() << ")\n";

    // --- Cognitive loop ---
    cognitive_loop(hw, jit_proj_ptr, nn_proj_ptr, llm, device);

    hw.stop();
    std::cout << "[EXIT] Clean shutdown\n";
    return 0;
}
