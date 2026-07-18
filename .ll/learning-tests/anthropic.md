---
target: anthropic
date: '2026-07-07'
status: proven
assertions:
- claim: import anthropic exposes anthropic.Anthropic client class
  result: pass
- claim: anthropic.Anthropic() instantiable with zero arguments
  result: pass
- claim: constructed client exposes .messages and .beta namespaced resources
  result: pass
- claim: anthropic exports APIError + AuthenticationError; AuthenticationError subclasses
    APIError
  result: pass
- claim: anthropic.__version__ is a non-empty string parseable by packaging.version.Version
  result: pass
- claim: live messages.create() calls without an API key cannot be exercised in this
    environment (acknowledged constraint, not a runtime claim)
  result: untested
- claim: tools=[...] dict accepts a cache_control key on an individual tool-definition
    block alongside name/description/input_schema
  result: pass
- claim: building request kwargs (model/messages/tools with cache_control on the
    tool block) via the SDK client does not raise client-side before dispatch
  result: pass
- claim: live messages.create() call with cache_control on a tool block (actual
    cache-hit/API-acceptance round-trip) cannot be exercised in this environment
    (no ANTHROPIC_API_KEY available; acknowledged constraint, not a runtime claim)
  result: untested
raw_output_path: .ll/learning-tests/raw/anthropic.txt
---
