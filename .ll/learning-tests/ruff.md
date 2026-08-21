---
target: ruff
date: '2026-08-20'
status: proven
assertions:
- claim: ruff check exits 0 when no lint violations are found
  result: pass
- claim: ruff check exits 1 when violations are found (not a crash)
  result: pass
- claim: ruff check --output-format=json emits a JSON array of violation objects
  result: pass
- claim: each JSON violation object has a code key and a filename key
  result: pass
- claim: ruff format --check exits 0 when files are already formatted, non-zero when reformatting is needed
  result: pass
- claim: ruff format --check does not modify files on disk
  result: pass
raw_output_path: .ll/learning-tests/raw/ruff.txt
---
