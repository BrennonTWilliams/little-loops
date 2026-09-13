---
target: qwen
date: '2026-09-12'
status: proven
assertions:
- claim: qwen --version prints a string containing a semantic version number and exits 0
  result: pass
- claim: 'qwen --help documents an --allowed-tools flag (tool allowlist), contradicting
    QwenRunner''s docstring/warning in host_runner.py that qwen has no tool-allowlist
    flag (only --exclude-tools denylist)'
  result: pass
- claim: qwen --help does not document a bare --agent flag
  result: pass
- claim: qwen --yolo --output-format stream-json -p "<prompt>" prints multiple JSON
    objects, one per line (JSONL), not one blob
  result: pass
- claim: each stream-json line is a dict with a type key
  result: pass
- claim: the final stream-json line has type "result"
  result: pass
- claim: using the deprecated -p/--prompt flag emits a deprecation warning on stderr
  result: fail
raw_output_path: .ll/learning-tests/raw/qwen.txt
---
