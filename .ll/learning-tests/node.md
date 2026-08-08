---
target: node
date: '2026-08-08'
status: proven
assertions:
- claim: node --version prints a string prefixed with v followed by semver (v<major>.<minor>.<patch>)
  result: pass
- claim: the built-in node:test module is importable without any external package
  result: pass
- claim: a failing node:test assertion causes the process to exit with a non-zero exit code
  result: pass
- claim: a passing node:test run exits with code 0
  result: pass
- claim: node:test output (default TAP reporter) includes "# pass" and "# fail" counters in stdout
  result: pass
- claim: node:assert/strict throws an AssertionError (not just any Error) on a failed strictEqual
  result: pass
raw_output_path: .ll/learning-tests/raw/node.txt
---
