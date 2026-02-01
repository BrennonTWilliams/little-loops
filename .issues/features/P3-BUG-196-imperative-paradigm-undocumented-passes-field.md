# Imperative Paradigm `until.passes` Field is Undocumented

## Type
BUG

## Priority
P3

## Status
OPEN

## Description

The imperative paradigm YAML template includes an `until.passes: true` field, but this field is **never explained** in the question workflow for the `/ll:create_loop` command.

**Generated YAML (lines 647-665):**
```yaml
paradigm: imperative
name: "<loop-name>"
steps:
  - "<step-1>"
  - "<step-2>"
  - "<step-3>"
until:
  check: "<exit-condition-command>"
  passes: true  # <-- Never explained!
  # Include evaluator only if not using default (exit_code):
  evaluator:
    type: "<output_contains|output_numeric|llm_structured>"
```

**Questions asked (lines 610-620):**
```yaml
questions:
  - question: "When should the loop stop?"
    header: "Exit condition"
    multiSelect: false
    options:
      - label: "All checks pass"
      - label: "Tests pass"
      - label: "Custom condition"
```

**Evidence:**
- `commands/create_loop.md:647-665` - Template shows `passes: true`
- `commands/create_loop.md:610-620` - Questions don't explain what `passes` means

**Impact:**
Users will not understand the purpose of the `passes` field. It appears to be a hardcoded value that's never configurable, which is confusing.

## Files Affected
- `commands/create_loop.md`

## Questions
1. What does `passes: true` mean vs `passes: false`?
2. Can this be `false`? If so, when?
3. Should this be a user-facing configuration option?

## Expected Behavior
Either:
1. Document what `passes` means in the template section
2. Make it a configurable option in the question flow
3. Remove it if it's always `true` and not meaningful

## Actual Behavior
The field appears in the template but is never explained or configurable.

## Related Issues
None
