#include "llm_bridge.h"
#include "somatic_projector.h"  // for LLM_EMB_DIM constant
#include <llama.h>
#include <cstring>
#include <cstdio>
#include <stdexcept>

// ---------------------------------------------------------------------------
// Construction / teardown
// ---------------------------------------------------------------------------

LLMBridge::LLMBridge(const LLMConfig& cfg) : cfg_(cfg) {}

LLMBridge::~LLMBridge() {
    if (sampler_) { llama_sampler_free(sampler_); }
    if (ctx_)     { llama_free(ctx_); }
    if (model_)   { llama_model_free(model_); }
    llama_backend_free();
}

bool LLMBridge::init() {
    llama_backend_init();

    llama_model_params mparams = llama_model_default_params();
    mparams.n_gpu_layers       = cfg_.n_gpu_layers;

    model_ = llama_model_load_from_file(cfg_.model_path.c_str(), mparams);
    if (!model_) {
        fprintf(stderr, "[LLM] Failed to load model: %s\n", cfg_.model_path.c_str());
        return false;
    }

    llama_context_params cparams = llama_context_default_params();
    cparams.n_ctx     = cfg_.n_ctx;
    cparams.n_batch   = cfg_.n_batch;
    cparams.n_threads = cfg_.n_threads;
    // embeddings=true lets us retrieve hidden states for the embed_text() helper.
    cparams.embeddings = true;

    ctx_ = llama_init_from_model(model_, cparams);
    if (!ctx_) {
        fprintf(stderr, "[LLM] Failed to create context\n");
        return false;
    }

    n_embd_ = llama_model_n_embd(model_);
    if (n_embd_ != LLM_EMB_DIM) {
        fprintf(stderr, "[LLM] WARNING: model n_embd=%d, projector target=%d — "
                        "retrain projector or adjust LLM_EMB_DIM\n",
                n_embd_, LLM_EMB_DIM);
    }

    // Build a greedy-ish sampler chain: temperature → top-p → dist sampler
    sampler_ = llama_sampler_chain_init(llama_sampler_chain_default_params());
    llama_sampler_chain_add(sampler_, llama_sampler_init_temp(cfg_.temp));
    llama_sampler_chain_add(sampler_, llama_sampler_init_top_p(cfg_.top_p, 1));
    llama_sampler_chain_add(sampler_, llama_sampler_init_dist(LLAMA_DEFAULT_SEED));

    return true;
}

// ---------------------------------------------------------------------------
// Internal batch helpers
// ---------------------------------------------------------------------------

// Injects n_tokens consecutive embedding vectors (each of size n_embd) into the
// KV cache starting at pos_offset, using seq_id.
// This is the critical injection point: we pass raw floats, not token IDs.
void LLMBridge::decode_batch_embd(const float* embd_data, int n_tokens, int n_embd,
                                   int seq_id, int pos_offset) {
    llama_batch batch = llama_batch_init(n_tokens, n_embd, 1);
    batch.n_tokens = n_tokens;

    for (int i = 0; i < n_tokens; ++i) {
        memcpy(batch.embd + i * n_embd, embd_data + i * n_embd,
               n_embd * sizeof(float));
        batch.pos[i]           = pos_offset + i;
        batch.n_seq_id[i]      = 1;
        batch.seq_id[i][0]     = seq_id;
        batch.logits[i]        = 0;  // don't need logits for embedding tokens
    }
    // Last embedding token: we do NOT need logits here either (it's somatic root).

    if (llama_decode(ctx_, batch) != 0) {
        fprintf(stderr, "[LLM] llama_decode (embd) failed\n");
    }
    llama_batch_free(batch);
}

void LLMBridge::decode_batch_tokens(const std::vector<int32_t>& tokens,
                                     int seq_id, int pos_offset) {
    llama_batch batch = llama_batch_init(static_cast<int>(tokens.size()), 0, 1);
    batch.n_tokens = static_cast<int32_t>(tokens.size());

    for (int i = 0; i < batch.n_tokens; ++i) {
        batch.token[i]         = tokens[i];
        batch.pos[i]           = pos_offset + i;
        batch.n_seq_id[i]      = 1;
        batch.seq_id[i][0]     = seq_id;
        batch.logits[i]        = 0;
    }
    // Request logits only for the last token (where we sample from).
    batch.logits[batch.n_tokens - 1] = 1;

    if (llama_decode(ctx_, batch) != 0) {
        fprintf(stderr, "[LLM] llama_decode (tokens) failed\n");
    }
    llama_batch_free(batch);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

std::string LLMBridge::generate(const float* somatic_vec, int emb_dim,
                                 const std::string& user_prompt) {
    if (emb_dim != n_embd_) {
        return "ERROR: somatic vector dimension mismatch";
    }

    llama_memory_clear(llama_get_memory(ctx_), /*data=*/true);

    // --- Step 1: Inject somatic vector as position 0 (the "body root" token) ---
    decode_batch_embd(somatic_vec, 1, n_embd_, 0 /*seq_id*/, 0 /*pos*/);

    // --- Step 2: Tokenise user prompt and decode into KV cache (positions 1…N) ---
    const llama_vocab* vocab = llama_model_get_vocab(model_);

    // Estimate token count conservatively
    int max_tokens = static_cast<int>(user_prompt.size()) + 16;
    std::vector<llama_token> prompt_tokens(max_tokens);
    int n_prompt = llama_tokenize(vocab,
                                  user_prompt.c_str(),
                                  static_cast<int32_t>(user_prompt.size()),
                                  prompt_tokens.data(), max_tokens,
                                  /*add_special=*/true,
                                  /*parse_special=*/true);
    if (n_prompt < 0) {
        return "ERROR: tokenisation failed";
    }
    prompt_tokens.resize(n_prompt);

    std::vector<int32_t> token_ids(prompt_tokens.begin(), prompt_tokens.end());
    decode_batch_tokens(token_ids, 0 /*seq_id*/, 1 /*pos — offset by 1 for somatic token*/);

    // --- Step 3: Autoregressive generation ---
    std::string result;
    int pos = 1 + n_prompt;

    for (int i = 0; i < cfg_.max_new_tokens; ++i) {
        llama_token new_token = llama_sampler_sample(sampler_, ctx_, -1);
        llama_sampler_accept(sampler_, new_token);

        if (llama_vocab_is_eog(vocab, new_token)) break;

        // Decode token to string
        char piece[128] = {};
        int n = llama_token_to_piece(vocab, new_token, piece, sizeof(piece), 0, true);
        if (n > 0) result.append(piece, n);

        // Feed new token back into KV cache
        decode_batch_tokens({static_cast<int32_t>(new_token)}, 0, pos++);
        // Restore logits request for next sample
        // (decode_batch_tokens sets logits[last]=1 already)
    }

    return result;
}

std::vector<float> LLMBridge::embed_text(const std::string& text) {
    const llama_vocab* vocab = llama_model_get_vocab(model_);
    int max_t = static_cast<int>(text.size()) + 16;
    std::vector<llama_token> toks(max_t);
    int n = llama_tokenize(vocab, text.c_str(), static_cast<int32_t>(text.size()),
                           toks.data(), max_t, true, true);
    if (n < 0) return {};
    toks.resize(n);

    llama_memory_clear(llama_get_memory(ctx_), /*data=*/true);
    std::vector<int32_t> ids(toks.begin(), toks.end());
    decode_batch_tokens(ids, 0, 0);

    // Pull the hidden state for the last token as the text embedding
    float* embd = llama_get_embeddings_seq(ctx_, 0);
    if (!embd) return {};
    return std::vector<float>(embd, embd + n_embd_);
}
