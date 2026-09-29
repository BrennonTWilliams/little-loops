---
target: Qwen Code
date: '2026-09-28'
status: proven
assertions:
- claim: --version prints a bare semver string
  result: pass
- claim: --yolo is hidden from --help
  result: fail
- claim: --output-format choices are text, json, stream-json
  result: pass
- claim: there is no --agent CLI flag
  result: pass
- claim: stream-json first event is type=system subtype=init
  result: pass
- claim: stream-json final event is type=result with string result 'pong'
  result: pass
- claim: init event qwen_code_version equals --version output
  result: pass
- claim: --json-schema puts the validated JSON as a string in the final result field
  result: pass
raw_output_path: .ll/learning-tests/raw/qwen-code.txt
---
