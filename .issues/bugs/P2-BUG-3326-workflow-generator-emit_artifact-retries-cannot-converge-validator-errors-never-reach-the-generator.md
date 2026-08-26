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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- Confirmed current line numbers match the issue exactly: `validate_artifact` (315), `emit_artifact` (280), `count_emit_retry` (329), `validate_evaluators` (202) with its `on_no: attach_evaluators` edge at line 231 (the `attach_evaluators` state header itself is at line 145 — the issue's "line 231" citation refers to the routing edge, not the state header).
- Full state pipeline order (all under `${captured.run_dir.output}`, set in `init` via `capture: run_dir`): `init → capture_intent → validate_intent → sketch_state_graph → validate_sketch → attach_evaluators → validate_evaluators → resolve_routing → validate_routing → emit_artifact → validate_artifact → count_emit_retry`.
- `count_emit_retry`'s current shell action is a pure retry-budget counter (persists `.emit_retry_count`, compares against `${context.max_emit_retries}`, default `3` — defaulted twice: once in `context:` at line 39, once again inline in the shell script). It performs no branching on *why* validation failed — `on_yes: emit_artifact`, `on_no: diagnose`. `diagnose` is a `prompt` state with `next: failed` and no `on_error` handling (contrast: `finalize_await_confirmation` does declare `on_error: failed`).
- `validate_evaluators`'s fault-class routing works because its shell action is a `python3 -c` snippet that imports `NON_LLM_EVALUATOR_TYPES`/`EVALUATOR_REQUIRED_FIELDS` directly from `little_loops.fsm.validation` (not restated), asserts membership/field-completeness, and its single `on_no: attach_evaluators` edge routes straight back to the one state that owns that one fault class — there is no separate "count" state interposed. Reusing this edge for `count_emit_retry` means inserting a classification step between `validate_artifact` and `count_emit_retry` (or inside `count_emit_retry` itself) that greps the captured error text for a fault-class signature before deciding `emit_artifact` vs `attach_evaluators`.

### Convention check — stderr capture and fault-class routing
- No loop YAML in `scripts/little_loops/loops/` uses the literal `cmd 2>file; exit $?` one-liner the issue proposes. Two established idioms exist instead: (a) `cmd 2>&1 | tee file` combined with `set -o pipefail` (e.g. `fix-quality-and-tests.yaml:62-64`, `test-coverage-improvement.yaml`, `dead-code-cleanup.yaml`, `autodev.yaml`, `rn-remediate.yaml`), or (b) stderr-only redirect to a file plus explicit `$?` capture into a shell variable, used when the state needs to branch on the result rather than just log it (e.g. `vega-viz.yaml:298-320`, `cli-anything-bootstrap.yaml:271-279,324-325`). Idiom (b) is the closer structural match to what `validate_artifact` needs (preserve exit code for the `exit_code` evaluator while also persisting stderr for the next state to read).
- Fault-class routing on a retry edge (grep prior output for a discriminator, route on `output_contains`) is an established, repeated pattern elsewhere: `lib/common.yaml:332-354` (`ll_auto_auth_check`), `lib/common.yaml:355-386` (`ll_auto_learning_gate_check`, three-way classification via sequential grep), and `cua-agent-desktop.yaml:344-391` (a full `_check_*`/`_route_*` chain, with an explicit comment noting this exists specifically because a flat retry edge would otherwise mask a distinct fault class).
- Contrast case: `cli-anything-bootstrap.yaml:490-506` (`count-refine-cycle`) is structurally identical to `workflow-generator.yaml`'s current `count_emit_retry` — a flat, fault-agnostic counter with no discrimination. This confirms fault-class discrimination is consistently implemented as an *additional* layer on top of the counter shape, not folded into the counter state itself, in every codebase example that has it.

### Prompt convention — reading a prior error file
- The "if `<path>` exists and is non-empty, read it first" phrasing is an established, near-identical convention repeated verbatim across generator-family loops (`svg-image-generator.yaml:75-76`, `hitl-md.yaml:170`, `openscad-model-generator.yaml:97`, `pixi-data-viz.yaml:133`, `canvas-sketch-generator.yaml:126`, `pixi-generative-art.yaml:101`, `html-website-generator.yaml:70`, `generative-art.yaml:98`) and `rn-refine.yaml:438-441`/`general-task.yaml:987-989` for triage-style reads. `emit_artifact`'s prompt should follow this exact phrasing convention rather than inventing new wording.

### Test shape conventions
- `scripts/tests/test_builtin_loops.py` has two established shapes for this kind of assertion: a static dict-lookup shape for routing-target assertions (`test_shrink_gated_by_context_flag`, `test_promotion_gated_by_auto_promote_flag` — `data["states"][name].get("on_yes"/"on_no")` equality checks), and a behavioral subprocess-execution shape for proving a shell gate's logic actually discriminates (`test_validate_evaluators_enforces_required_companion_fields` — extracts the action string, substitutes a `tmp_path` fixture, runs it via `subprocess.run(["bash", "-c", action], ...)`, asserts on `returncode`/`stderr`). A new test for `count_emit_retry`'s fault-class routing should follow the behavioral shape since the point is proving the grep-based discrimination works, not just that a YAML key has a given value.

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
- `/ll:refine-issue` - 2026-08-26T19:14:21 - `0809cdb6-a88f-42a7-9e51-e57ee8a63f3a.jsonl`
- `/ll:format-issue` - 2026-08-26T19:09:04 - `8c47cf34-66af-4a75-8c4b-c7a8efe5d7ec.jsonl`
