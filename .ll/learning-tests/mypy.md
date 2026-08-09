---
target: mypy
date: '2026-08-07'
status: proven
assertions:
- claim: clean module makes mypy exit 0 (success message on stdout)
  result: pass
- claim: a type error makes mypy exit 1
  result: pass
- claim: a nonexistent file argument makes mypy exit 2 (fatal error, distinct from
    type-error exit 1)
  result: pass
- claim: normal mypy output (version banner, success message, diagnostics) goes to
    stdout; stderr stays empty when piped
  result: pass
- claim: 'default diagnostic format is "path:line: error: message [error-code]" (no
    column number, error-code suffix shown)'
  result: pass
- claim: '[tool.mypy] in pyproject.toml is auto-discovered without --config-file (show_column_numbers=true
    takes effect)'
  result: pass
- claim: '--warn-unused-ignores flags a redundant # type: ignore comment as an error'
  result: pass
- claim: --ignore-missing-imports suppresses "cannot find implementation or library
    stub" errors for a missing module
  result: pass
raw_output_path: .ll/learning-tests/raw/mypy.txt
proven_package: mypy
proven_version: 1.10.1
---
