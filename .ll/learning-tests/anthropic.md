---
target: anthropic
date: '2026-08-08'
status: proven
assertions:
- claim: anthropic.types.Usage exposes both flat cache_creation_input_tokens/cache_read_input_tokens
    fields and a nested cache_creation object
  result: pass
- claim: Usage.cache_creation and Usage.cache_creation_input_tokens default to None
    when absent from the response, so getattr(usage, "...", None) or 0 remains
    the correct defensive read pattern
  result: pass
- claim: the nested CacheCreation type exposes ephemeral_5m_input_tokens and ephemeral_1h_input_tokens
    (extended-TTL cache breakdown)
  result: pass
- claim: a system content block dict with a cache_control ephemeral marker is accepted
    by the SDK client-side (no validation raise) when building request params
  result: pass
- claim: Usage.model_validate tolerates unknown/future fields (additionalProperties
    allowed) without raising
  result: pass
raw_output_path: .ll/learning-tests/raw/anthropic.txt
---
