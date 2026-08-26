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

## Steps to Reproduce

1. Run `workflow-generator` on a brief that causes `emit_artifact` to produce a
   `workflow.yaml` with a deterministic structural fault (e.g. a state missing a
   required `evaluate` companion field).
2. `validate_artifact` runs `ll-loop validate` against the emitted artifact; it
   fails and discards stderr.
3. `count_emit_retry` routes back to `emit_artifact` under `max_emit_retries`.
4. Observe: `emit_artifact`'s prompt re-reads only `intent.yaml` and
   `graph-routed.yaml` (unchanged), so each retry regenerates the same fault and
   the loop exhausts its retry budget without converging.

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

`max_emit_retries` is spent budget: on a deterministic fault it burns real
time and API cost (~$0.15 / ~4 min per unproductive retry pair observed in the
source run) while never converging, and the run still fails at the end —
strictly worse than failing fast on the first attempt. Fixing this makes the
retry mechanism actually do what its name promises.

## Proposed Solution

1. `validate_artifact` tees `ll-loop validate` stderr to
   `${captured.run_dir.output}/.emit_errors.txt` while preserving its exit
   status:
   ```yaml
   validate_artifact:
     action: |
       ll-loop validate "${captured.run_dir.output}/workflow.yaml" \
         2> "${captured.run_dir.output}/.emit_errors.txt"; exit $?
   ```
   (`cmd 2>file; exit $?`, not a pipeline — piping through e.g. `tee` would
   swallow the exit code the `exit_code` evaluator depends on.)
2. `emit_artifact`'s prompt instructs: if `.emit_errors.txt` exists and is
   non-empty, read it first and fix every listed error specifically before
   re-emitting.
3. `count_emit_retry` (`scripts/little_loops/loops/workflow-generator.yaml:329`)
   routes by fault class instead of unconditionally back to `emit_artifact`:
   an error matching `\.evaluate:` belongs to `attach_evaluators`, not the
   emitter, and reuses the existing `on_no: attach_evaluators` edge already
   present on `validate_evaluators` (line 231).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/workflow-generator.yaml` — `validate_artifact`
  (line 315), `emit_artifact` (line 280), `count_emit_retry` (line 329)

### Dependent Files (Callers/Importers)
- N/A — loop is invoked by ID via the FSM runner, not imported

### Similar Patterns
- `validate_evaluators` (line 202) already fixed its own gate-gap; its
  fault-class routing to `attach_evaluators` (line 231) is the pattern
  `count_emit_retry` should reuse
- `capture_intent`/`validate_intent` (lines 58, 82) have an analogous
  unfenced-input issue tracked separately in BUG-3327

### Tests
- `scripts/tests/test_builtin_loops.py` — add/extend a case asserting
  `workflow-generator.yaml` validates and that `count_emit_retry`'s routing
  edges cover the `\.evaluate:` fault class

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — if fault-class retry routing
  becomes a documented MR pattern, note it there; otherwise N/A

### Configuration
- N/A

## Program Design

### Signatures

- `validate_artifact() -> int` — shell action, tees `ll-loop validate` stderr
  to `${captured.run_dir.output}/.emit_errors.txt`, preserves exit code
- `count_emit_retry(fault_class: str) -> str` — FSM edge target; currently
  unconditionally `emit_artifact`, gains a fault-class branch to
  `attach_evaluators`

### Call Path

`validate_artifact` (writes `.emit_errors.txt`) -> `count_emit_retry` (reads
fault class) -> `emit_artifact` (reads `.emit_errors.txt`, fixes emitter
faults) **or** `attach_evaluators` (fixes evaluator faults, matching the
`validate_evaluators` precedent at line 231)

## Implementation Steps

1. Add stderr capture to `validate_artifact` with exit-code preservation.
2. Update `emit_artifact`'s prompt to read and address `.emit_errors.txt`.
3. Add fault-class detection and routing to `count_emit_retry`, wiring the
   `\.evaluate:` case to `attach_evaluators`.
4. Verify with `ll-loop validate scripts/little_loops/loops/workflow-generator.yaml`
   and a re-run of the source scenario (or an equivalent fixture) to confirm
   retries now converge or fail fast on genuinely emitter-owned faults.

## Impact

- **Priority**: P2 — retries silently waste cost/time on every workflow-generator
  run that hits a deterministic validator fault, and never actually recovers
- **Effort**: Small — three localized changes to one loop YAML, no new
  primitives needed
- **Risk**: Low — changes are scoped to one loop's shell action and routing
  edge; existing `on_no: attach_evaluators` edge is reused, not invented
- **Breaking Change**: No

## Notes

Companion to the gate-completeness fix already landed on `validate_evaluators`,
which moves *evaluator* faults upstream so they never reach this retry. This issue
covers the residual fault classes that legitimately belong to `emit_artifact`.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §2.5, §5 R3.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P2


## Session Log
- `/ll:format-issue` - 2026-08-26T19:09:04 - `8c47cf34-66af-4a75-8c4b-c7a8efe5d7ec.jsonl`
