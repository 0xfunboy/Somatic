#pragma once
#include <string>
#include <vector>
#include <torch/torch.h>

// Forward declarations from llama.cpp C API
struct llama_model;
struct llama_context;
struct llama_sampler;

struct LLMConfig {
    std::string model_path;
    int n_ctx         = 2048;
    int n_batch       = 512;
    int n_threads     = 8;
    int n_gpu_layers  = 99;   // offload all layers to VRAM
    float temp        = 0.7f;
    float top_p       = 0.95f;
    int max_new_tokens = 256;
};

// Wraps a llama.cpp context and exposes a single method that accepts:
//   somatic_vec — float[LLM_EMB_DIM], the output of SomaticProjector (pre-computed on GPU)
//   user_prompt — raw UTF-8 text string
// The somatic vector is injected as token-0 in the KV cache using llama_batch.embd,
// so the transformer attends over [somatic_token | text_tokens] natively.
class LLMBridge {
public:
    explicit LLMBridge(const LLMConfig& cfg);
    ~LLMBridge();

    // Initialises model + context. Returns false on failure.
    bool init();

    // Full inference pass. somatic_vec must be exactly LLM_EMB_DIM floats.
    // Returns the generated text or an error string prefixed with "ERROR:".
    std::string generate(const float* somatic_vec, int emb_dim,
                         const std::string& user_prompt);

    // Tokenises text and returns the token embeddings matrix [n_tokens × n_embd]
    // so callers can inspect or cache them without running full inference.
    std::vector<float> embed_text(const std::string& text);

private:
    void decode_batch_embd(const float* embd_data, int n_tokens, int n_embd,
                           int seq_id, int pos_offset);
    void decode_batch_tokens(const std::vector<int32_t>& tokens,
                             int seq_id, int pos_offset);

    LLMConfig cfg_;
    llama_model*   model_   = nullptr;
    llama_context* ctx_     = nullptr;
    llama_sampler* sampler_ = nullptr;
    int n_embd_             = 0;
};
