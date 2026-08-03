---
target: jq
date: '2026-08-03'
status: proven
assertions:
- claim: jq -r '.field // 0' outputs the field value as a raw string, falling back to 0 when missing/null
  result: pass
- claim: jq -r '.field // "false"' outputs the field value as a raw string, falling back to literal "false" when missing/null
  result: pass
- claim: jq -e returns exit code 1 when the filter evaluates to null or false
  result: pass
- claim: jq empty rejects loosely-typed JSON (e.g., bare strings) by exiting non-zero
  result: pass
- claim: jq -r '[(.a // {} | keys), (.b // {} | keys)] | flatten | unique | join(",")' produces a comma-separated list of unique values from two object key arrays
  result: pass
- claim: jq -r '.nested.field.path' navigates nested objects via dot notation
  result: pass
- claim: jq empty returns exit code 1 (not 5) for bare strings (claim-4a specific exit code value)
  result: fail
raw_output_path: .ll/learning-tests/raw/jq.txt
---
