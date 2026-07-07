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
raw_output_path: .ll/learning-tests/raw/anthropic.txt
---
