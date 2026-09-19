---
target: node:test
date: '2026-09-18'
status: proven
assertions:
- claim: node --test exits 0 when all tests pass and 1 when any test fails
  result: pass
- claim: an .mjs file can import test from node:test and use node:assert/strict
  result: pass
- claim: 'a test with {skip: true} does not fail the run and is counted as skipped'
  result: pass
- claim: an async test that throws/rejects fails the run
  result: pass
- claim: multiple test files passed as arguments all run and their counts aggregate
  result: pass
- claim: 'piped (non-TTY) output includes TAP summary lines "# pass N" / "# fail N" (actual on Node 26: "ℹ pass N")'
  result: fail
raw_output_path: .ll/learning-tests/raw/nodetest.txt
---
