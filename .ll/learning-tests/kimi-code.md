---
target: kimi-code
date: '2026-09-12'
status: proven
assertions:
- claim: kimi --version prints a bare semver string (matches \d+\.\d+\.\d+)
  result: pass
- claim: kimi -p "<prompt>" --output-format stream-json emits a final JSONL line
    with "type":"session.resume_hint"
  result: pass
- claim: a no-tool run's stream-json output contains a "role":"assistant" line
    with content
  result: pass
- claim: the stream contains no "type":"result" summary event (unlike Claude Code)
  result: pass
- claim: combining -p with --yolo is rejected with a non-zero exit and a stderr
    error message
  result: pass
raw_output_path: .ll/learning-tests/raw/kimi-code.txt
---
