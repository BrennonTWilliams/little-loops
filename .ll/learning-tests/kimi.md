---
target: kimi
date: '2026-08-03'
status: proven
assertions:
- claim: streaming events emitted by `kimi -p ... --output-format stream-json` are JSON objects keyed by "role" (not "type")
  result: pass
- claim: a no-tool-call run's answer arrives as a `role:"assistant"` event with a plain string "content" field
  result: pass
- claim: the stream ends with a `role:"meta"` event carrying `type:"session.resume_hint"` and a `session_id`
  result: pass
- claim: there is no Claude-style terminal `type:"result"` summary event anywhere in the stream
  result: pass
- claim: tool invocations appear as a `role:"assistant"` event with a "tool_calls" array (function name + arguments), not inline content
  result: pass
- claim: tool output arrives as a separate `role:"tool"` event carrying "tool_call_id" and "content"
  result: pass
- claim: '`kimi -p ...` combined with `--yolo` is rejected at startup with `error: Cannot combine --prompt with --yolo.` and a non-zero exit code'
  result: pass
raw_output_path: .ll/learning-tests/raw/kimi.txt
---
