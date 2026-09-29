---
target: JSON Schema
date: '2026-09-28'
status: proven
assertions:
- claim: type integer accepts 1.0 but rejects 1.5 (draft 2020-12)
  result: pass
- claim: a bool is not valid as type integer or type number
  result: pass
- claim: unknown keywords are ignored and the schema still passes check_schema
  result: pass
- claim: format is not asserted by default but is asserted when a format_checker is supplied
  result: pass
- claim: properties and required are ignored for non-object instances
  result: pass
- claim: additionalProperties false inside an allOf branch does not see sibling-branch properties
  result: pass
- claim: sibling keywords next to $ref are ignored in draft-07 but evaluated in draft 2020-12
  result: pass
- claim: validator_for selects Draft7Validator for the project config-schema.json, which is itself a valid schema
  result: pass
raw_output_path: .ll/learning-tests/raw/json-schema.txt
---
