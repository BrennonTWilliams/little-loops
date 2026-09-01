---
target: opencode
date: '2026-08-31'
status: proven
assertions:
- claim: 'opencode run --format json emits NDJSON events, each a JSON object with
    a "type" key'
  result: pass
- claim: 'a step_finish event (part.type == "step-finish") carries per-step token
    usage nested at part.tokens'
  result: pass
- claim: 'part.tokens includes input, output, reasoning, and a nested cache object
    with read/write sub-fields'
  result: pass
- claim: part.cost is a numeric dollar-cost field present alongside part.tokens
    on the same step_finish event
  result: pass
- claim: the step_finish event includes a model identifier field
  result: fail
raw_output_path: .ll/learning-tests/raw/opencode.txt
---
