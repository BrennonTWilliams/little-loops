---
target: phoenix
date: '2026-07-05'
status: proven
assertions:
- claim: Arize Phoenix's native span schema is OpenInference, not OTel GenAI — LLM
    token counts are llm.token_count.prompt / llm.token_count.completion / llm.token_count.total,
    not gen_ai.usage.input_tokens / gen_ai.usage.output_tokens
  result: pass
- claim: openinference.semconv.trace.SpanAttributes exposes LLM_TOKEN_COUNT_PROMPT,
    LLM_TOKEN_COUNT_COMPLETION, LLM_TOKEN_COUNT_TOTAL
  result: pass
- claim: OpenInference defines a cache-read token attribute analogous to gen_ai.usage.cache_read_input_tokens,
    as llm.token_count.prompt_details.cache_read (with sibling cache_write/cache_input)
  result: pass
- claim: arize-phoenix installs a runnable phoenix CLI entry point backing 'phoenix
    serve'
  result: pass
- claim: Phoenix can also ingest raw OTel gen_ai.* GenAI-convention spans directly
    without an OpenInference shim — 'phoenix serve' (arize-phoenix 17.18.0) normalizes
    gen_ai.usage.input_tokens -> llm.token_count.prompt and gen_ai.usage.output_tokens
    -> llm.token_count.completion on ingest (live OTLP test). Version-sensitive; older
    Phoenix may lack this translation layer
  result: pass
- claim: 'CAVEAT (live, 17.18.0): Phoenix extracts cache tokens ONLY from the DOTTED
    OTel semconv names gen_ai.usage.cache_read.input_tokens / gen_ai.usage.cache_creation.input_tokens
    (the values of GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS etc). The UNDERSCORE spelling
    gen_ai.usage.cache_read_input_tokens (Anthropic API field name, as specified in
    FEAT-2478) is silently dropped. input/output token names happen to match; cache
    names do not.'
  result: pass
- claim: 'The gen_ai->OpenInference normalization module (phoenix/trace/gen_ai/conversion.py)
    first shipped in arize-phoenix 15.10.0 (absent in 15.9.0), by dep-independent file-presence
    bisect. Functional normalization confirmed live on 17.18.0. Safe _HAS_PHOENIX guard
    floor: arize-phoenix >= 15.10.0.'
  result: pass
raw_output_path: .ll/learning-tests/raw/phoenix.txt
---
