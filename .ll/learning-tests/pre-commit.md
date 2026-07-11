---
target: pre-commit
date: '2026-07-10'
status: proven
assertions:
- claim: "pre-commit run --files <path> exits 0 when a repo:local language:system hook entry exits 0"
  result: pass
- claim: "pre-commit run --files <path> exits 1 when a repo:local language:system hook entry exits non-zero"
  result: pass
- claim: "the files regex ^\\.ll/decisions\\.yaml$ matches only .ll/decisions.yaml at repo root (does not match other.yaml)"
  result: pass
- claim: "pass_filenames: false causes pre-commit to invoke entry with argv count = 0"
  result: pass
- claim: "pass_filenames: true (default) causes pre-commit to invoke entry with argv count = 1, appending matched filename"
  result: pass
- claim: "language: system resolves entry via PATH; missing binary fails with clear 'Executable X not found' error"
  result: pass
- claim: "hook config requires a `name:` field (Missing required key: name error otherwise)"
  result: pass
raw_output_path: .ll/learning-tests/raw/pre-commit.txt
---