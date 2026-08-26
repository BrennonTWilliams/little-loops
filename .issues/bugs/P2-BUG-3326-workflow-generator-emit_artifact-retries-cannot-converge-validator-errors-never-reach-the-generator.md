---
id: BUG-3326
type: BUG
title: 'workflow-generator emit_artifact retries cannot converge: validator errors
  never reach the generator'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T17:33:29Z'
---

# BUG-3326: workflow-generator emit_artifact retries cannot converge: validator errors never reach the generator

## Summary

`workflow-generator`'s `emit_artifact` retry loop cannot converge on deterministic
faults. `validate_artifact` runs `ll-loop validate` and discards its stderr, and
`emit_artifact`'s prompt reads only `intent.yaml` and `graph-routed.yaml` — so the
validator's error text never reaches the generator. All three retries re-read
identical unchanged inputs and produce byte-identical output.

Observed in run `2026-08-26T171218-workflow-generator`: iterations 14 and 17 failed
with the same 12 errors, ~$0.15 and ~4 minutes spent on draws from an unchanged
distribution. `max_emit_retries` only buys anything for *nondeterministic* emission
errors.

## Current Behavior

```yaml
validate_artifact:
  action: |
    ll-loop validate "${captured.run_dir.output}/workflow.yaml"
```

stderr goes to the runner log; nothing is persisted for the next `emit_artifact`
pass to read.

## Expected Behavior

1. `validate_artifact` tees `ll-loop validate` stderr to
   `${captured.run_dir.output}/.emit_errors.txt` while preserving its exit status
   (the `exit_code` evaluator depends on it).
2. `emit_artifact`'s prompt instructs: if `.emit_errors.txt` exists and is
   non-empty, read it first and fix every listed error specifically.
3. `count_emit_retry` routes by fault class rather than unconditionally back to
   `emit_artifact` — an error matching `\.evaluate:` belongs to `attach_evaluators`,
   not the emitter, and the existing `on_no: attach_evaluators` edge already exists
   to carry it.

Point (3) is the substantive design work. Point (1) has a trap: capturing stderr
must not swallow the exit code (`cmd 2>file` then `exit $?`, not a pipeline).

## Motivation

[Why this issue matters - business value, user impact, technical debt cost]

## Proposed Solution

TBD - requires investigation

## Integration Map

### Files to Modify
- TBD - requires codebase analysis

### Dependent Files (Callers/Importers)
- TBD - use grep to find references

### Similar Patterns
- TBD - search for consistency

### Tests
- TBD - identify test files to update

### Documentation
- TBD - docs that need updates

### Configuration
- N/A or list config files

## Implementation Steps

1. [Major phase 1]
2. [Major phase 2]
3. [Verification approach]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Notes

Companion to the gate-completeness fix already landed on `validate_evaluators`,
which moves *evaluator* faults upstream so they never reach this retry. This issue
covers the residual fault classes that legitimately belong to `emit_artifact`.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §2.5, §5 R3.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2
