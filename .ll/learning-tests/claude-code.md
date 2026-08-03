---
target: claude-code
date: '2026-08-03'
status: proven
assertions:
- claim: claude --version prints a string containing a semantic version number and exits 0
  result: pass
- claim: claude --output-format json -p "<prompt>" prints a single JSON object (not JSONL) to stdout
  result: pass
- claim: that JSON object contains a result key holding the final text response
  result: pass
- claim: claude --output-format stream-json --verbose -p "<prompt>" prints multiple JSON objects, one per line (JSONL), not one blob
  result: pass
- claim: each stream-json line is a dict with a type key
  result: pass
- claim: claude --dangerously-skip-permissions -p "<prompt>" --output-format json exits 0 for a trivial prompt with no side effects
  result: pass
- claim: --json-schema '<schema>' alongside --output-format json constrains the result field to match the given JSON Schema
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code.txt
---
