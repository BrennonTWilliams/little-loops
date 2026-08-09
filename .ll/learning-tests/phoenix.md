---
target: phoenix
date: '2026-08-08'
status: proven
assertions:
- claim: openinference.semconv.trace.SpanAttributes.OPENINFERENCE_SPAN_KIND exists
    and equals "openinference.span.kind"
  result: pass
- claim: openinference.semconv.trace.OpenInferenceSpanKindValues.LLM.value equals
    "LLM"
  result: pass
- claim: openinference-instrumentation-anthropic exposes an AnthropicInstrumentor
    class that can be instantiated
  result: pass
- claim: The openinference-instrumentation-anthropic package's usage-attribute extraction
    (_get_token_counts in _utils.py) maps an Anthropic SDK Usage object's underscore-named
    cache_read_input_tokens field to the dotted OpenInference attribute llm.token_count.prompt_details.cache_read
    (SpanAttributes.LLM_TOKEN_COUNT_PROMPT_DETAILS_CACHE_READ), not a gen_ai.* key
  result: pass
- claim: SpanAttributes.LLM_PROVIDER and SpanAttributes.LLM_SYSTEM are literal strings
    "llm.provider" and "llm.system"
  result: pass
raw_output_path: .ll/learning-tests/raw/phoenix.txt
---
