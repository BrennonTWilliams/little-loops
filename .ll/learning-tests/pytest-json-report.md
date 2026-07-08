---
target: pytest-json-report
date: '2026-07-08'
status: proven
assertions:
- claim: '--json-report-file=PATH writes a JSON file at PATH after pytest runs'
  result: pass
- claim: the JSON output contains a top-level summary object with passed, total, and collected
    keys always present
  result: pass
- claim: 'summary contains a failed key when at least one test fails (but omits it when all tests pass)'
  result: pass
- claim: 'summary.passed + summary.failed + summary.skipped == summary.total (when those keys are present)'
  result: pass
- claim: 'with all tests passing, pytest exits 0 and the JSON report file is written'
  result: pass
- claim: 'with a failing test, the JSON report file is still written, summary.failed >= 1, and pytest exits non-zero'
  result: pass
raw_output_path: .ll/learning-tests/raw/pytest-json-report.txt
---