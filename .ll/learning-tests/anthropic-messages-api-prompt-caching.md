---
target: Anthropic Messages API prompt caching
date: '2026-10-04'
status: proven
assertions:
- claim: the SDK accepts a cache_control dict on system text blocks, tool definitions,
    and message content blocks, and forwards it unchanged in the POST /v1/messages body
  result: pass
- claim: cache_control.type is only 'ephemeral' and ttl is only '5m' or '1h'; a ttl
    set on a block passes through on the wire
  result: pass
- claim: thinking blocks (ThinkingBlockParam) do not accept cache_control
  result: pass
- claim: messages.create accepts a top-level cache_control param (automatic caching)
    and forwards it on the wire
  result: pass
- claim: no anthropic-beta header is sent for cache_control requests
  result: pass
- claim: the response Usage parses flat cache_creation_input_tokens/cache_read_input_tokens
    and the nested cache_creation ephemeral_5m/ephemeral_1h breakdown
  result: pass
- claim: the SDK does not enforce the breakpoint-count limit client-side (6 breakpoints
    are sent unmodified)
  result: pass
- claim: the server rejects a request with more than 4 cache_control breakpoints
  result: untested
- claim: a repeated identical prefix at or above the model minimum returns cache_read_input_tokens
    greater than 0
  result: untested
- claim: claude-sonnet-5-5 minimum cacheable prefix is 512 tokens and a prefix below
    it is silently not cached
  result: untested
raw_output_path: .ll/learning-tests/raw/anthropic-messages-api-prompt-caching.txt
---
