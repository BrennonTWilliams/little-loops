# Imperative Paradigm `until.passes` Field is Undocumented

## Type
BUG

## Priority
P3

## Status
RESOLVED

## Resolution

The `passes` field has been removed from the `/ll:create-loop` command documentation templates. The field was vestigial - it appeared in YAML examples but was never read or used by the `compile_imperative()` function in `scripts/little_loops/fsm/compilers.py`.

**Changes made:**
- Removed `passes: true` from imperative paradigm template at `commands/create_loop.md:656`
- Removed `passes: true` from example at `commands/create_loop.md:678`

The FSM behavior remains unchanged: successful evaluation transitions to `done`, failure transitions back to `step_0`. This behavior is hardcoded in the compiler and does not require a configuration field.

## Description

The imperative paradigm YAML template includes an `until.passes: true` field, but this field is **never explained** in the question workflow for the `/ll:create-loop` command.

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

## Verification Notes

**Verified: 2026-02-01**

The `passes` field is **completely unused** by the imperative paradigm compiler. The `compile_imperative()` function in `scripts/little_loops/fsm/compilers.py:387-469`:

1. Reads `spec["until"]["check"]` (line 433)
2. Reads `spec["until"].get("evaluator")` (line 436)
3. **Never reads** `spec["until"].get("passes")`

The FSM is compiled with `on_success="done"` and `on_failure="step_0"` regardless of the `passes` value. The `passes: true` in the template is vestigial documentation that has no effect on the compiled FSM.

**Resolution**: The `passes` field should be removed from the YAML template documentation since it serves no functional purpose. The behavior is hardcoded: successful evaluation transitions to `done`, failure transitions back to `step_0`.

---

## Related Issues
None
