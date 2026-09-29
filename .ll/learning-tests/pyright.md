---
target: pyright
date: '2026-09-26'
status: proven
assertions:
- claim: --outputjson emits JSON with top-level keys version, time, generalDiagnostics, summary
  result: pass
- claim: summary has errorCount, warningCount, informationCount, filesAnalyzed
  result: pass
- claim: each diagnostic has file, severity, message, range, and rule for rule-based checks
  result: pass
- claim: severity is one of "error", "warning", "information"
  result: untested
- claim: exit code is 1 when errors are found
  result: pass
- claim: exit code is 0 on a clean file
  result: pass
- claim: range uses zero-based line/character under start/end
  result: pass
raw_output_path: .ll/learning-tests/raw/pyright.txt
---
