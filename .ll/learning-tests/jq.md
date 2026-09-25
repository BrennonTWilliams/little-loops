---
target: jq
date: '2026-09-24'
status: proven
assertions:
- claim: jq -r '.field // 0' outputs the field value as a raw string, falling back to 0 when missing or null
  result: pass
- claim: jq -r '.field // "false"' outputs the field value as a raw string, falling back to literal "false" when missing or null
  result: pass
- claim: jq -e returns exit code 1 when the filter evaluates to null or false
  result: pass
- claim: jq -e returns exit code 4 when the filter produces no output
  result: pass
- claim: jq empty on an unquoted bare word (invalid JSON) exits 5, not 1
  result: pass
- claim: jq empty on a quoted JSON string exits 0
  result: pass
- claim: jq -r '[(.a // {} | keys), (.b // {} | keys)] | flatten | unique | join(",")' produces a comma-separated list of unique keys from two objects
  result: pass
- claim: jq -r '.nested.field.path' navigates nested objects via dot notation
  result: pass
- claim: The // operator treats false as missing and returns the fallback
  result: pass
- claim: jq exits 2 when the input file is missing
  result: pass
- claim: jq exits 3 on a filter compile error
  result: pass
raw_output_path: .ll/learning-tests/raw/jq.txt
---
