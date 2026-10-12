model_high="qwen/qwen3.8-27b"
model_low="qwen/qwen3.8-flash"

# 1. Force the subagent override to enforce Qwen Flash
export CLAUDE_CODE_SUBAGENT_MODEL="${model_low}"
export CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1

# 2. Map all native Claude conversation tiers directly to your high-tier model
export ANTHROPIC_DEFAULT_SONNET_MODEL="${model_high}"
export ANTHROPIC_DEFAULT_HAIKU_MODEL="${model_low}"   # Or model_high depending on task preference
export ANTHROPIC_DEFAULT_OPUS_MODEL="${model_high}"

# 3. Clean environment safety check
export ANTHROPIC_API_KEY=""

ori claude --model ${model_high}
