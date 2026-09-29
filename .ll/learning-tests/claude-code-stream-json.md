---
target: claude-code-stream-json
date: '2026-09-24'
status: proven
assertions:
- claim: every stdout line of `claude -p --output-format stream-json --verbose` is a standalone JSON object with a "type" key
  result: pass
- claim: the last event has type "result" and carries result text, is_error, total_cost_usd, and a usage dict
  result: pass
- claim: assistant events carry message.content as a list of blocks with text blocks
  result: pass
- claim: every event shares the same session_id
  result: pass
- claim: stream-json with --print requires --verbose (exits 1 with an error otherwise)
  result: pass
- claim: the first event is system/init
  result: fail
- claim: the system/init event is preceded by hook_started/hook_response system events when hooks are configured
  result: pass
- claim: result.usage contains input_tokens, output_tokens, cache_read_input_tokens, cache_creation_input_tokens
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code-stream-json.txt
---
