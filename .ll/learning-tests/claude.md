---
target: claude
date: '2026-08-10'
status: proven
assertions:
- claim: anthropic.Anthropic() raises anthropic.AnthropicError immediately at construction
    (not lazily) when no credentials are available
  result: fail
- claim: anthropic.AuthenticationError is a subclass of anthropic.APIError
  result: pass
- claim: anthropic.APIConnectionError is a subclass of anthropic.APIError
  result: pass
- claim: anthropic.RateLimitError is a subclass of anthropic.APIError
  result: pass
- claim: 'anthropic.Anthropic(auth_token=..., default_headers={"anthropic-beta": "oauth-2025-04-20"})
    constructs without error and without a network call'
  result: pass
- claim: passing both api_key and auth_token to anthropic.Anthropic() does not raise
    at construction time
  result: pass
raw_output_path: .ll/learning-tests/raw/claude.txt
---
