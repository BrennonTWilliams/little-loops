---
target: jsonschema
date: '2026-09-25'
status: proven
assertions:
- claim: validate() returns None on valid input
  result: pass
- claim: validate() raises ValidationError on invalid input
  result: pass
- claim: ValidationError exposes .message, .path (deque) and .validator
  result: pass
- claim: iter_errors yields all errors rather than stopping at the first
  result: pass
- claim: best_match picks a single error from many
  result: pass
- claim: Draft202012Validator.check_schema raises SchemaError for an invalid schema
  result: pass
- claim: additionalProperties false rejects unknown keys with validator additionalProperties
  result: pass
raw_output_path: .ll/learning-tests/raw/jsonschema.txt
---
