---
id: FEAT-3328
type: FEAT
title: 'Gate-completeness lint: flag intermediate gates that restate a validator rule
  table instead of importing it'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-26'
captured_at: '2026-08-26T17:33:30Z'
---

# FEAT-3328: Gate-completeness lint: flag intermediate gates that restate a validator rule table instead of importing it

## Summary

A meta-loop that gates each lowering pass with an inline `python3 -c` assertion can
restate a validator's rule table instead of importing it. When the restatement is a
proper *subset* of what the terminal gate checks, the intermediate gate does not
merely miss defects — it launders them, giving every downstream pass false
confidence and pushing detection to a point where the retry topology can no longer
reach the state that made the mistake.

This is exactly what happened in `workflow-generator` run `2026-08-26T171218`:
`validate_evaluators` checked `evaluate.type` membership but not required companion
fields, so four states carrying bare `type: output_json` passed the gate, propagated
through two more passes, and first surfaced 4 states downstream as 12 errors at
`validate_artifact` — where `count_emit_retry` routes back to `emit_artifact`, a
state structurally incapable of fixing an `attach_evaluators` defect.

The instance is fixed. This issue is about making the *class* detectable.

## Current Behavior

`fsm/validation` has no lint that inspects intermediate `shell` gate actions
for hardcoded rule restatement. A meta-loop author can write an inline
`python3 -c` gate that hand-lists a literal subset of values (e.g. `{"exit_code",
"regex_match"}`) instead of importing the validator's own exported table
(e.g. `NON_LLM_EVALUATOR_TYPES` in
`scripts/little_loops/fsm/validation/_base.py:66`), and nothing flags the
drift. This is exactly what `validate_evaluators` in
`workflow-generator.yaml` did before it was fixed: it checked
`evaluate.type` membership but not the companion fields
`EVALUATOR_REQUIRED_FIELDS` requires, so four states carrying bare
`type: output_json` passed the gate and the defect surfaced three states
downstream at `validate_artifact` instead.

## Expected Behavior

`fsm/validation` gains a meta-rule (alongside MR-1..MR-6 in
`scripts/little_loops/fsm/validation/meta_rules.py`) that, for a loop whose
terminal gate is a little-loops validator, flags any intermediate
`action_type: shell` state whose action contains `python3` and hardcodes a
literal set/frozenset of values that is a subset of a known exported table's
keys (e.g. a literal evaluator-type set instead of importing
`NON_LLM_EVALUATOR_TYPES`, or literal required-field lists instead of
`EVALUATOR_REQUIRED_FIELDS`). Severity is `warning` — a restatement can be a
deliberate, narrower curated vocabulary — with an escape-hatch comment to
suppress a specific state.

## Use Case

A loop author writing a new intermediate gate for `workflow-generator` (or
any other meta-loop with a terminal validator gate) hardcodes a literal
`{"exit_code", "regex_match"}` check instead of importing
`NON_LLM_EVALUATOR_TYPES`. `ll-loop validate` now emits a `warning` naming
the state and the exported table it should import instead, catching the drift
at authoring time instead of three states downstream at the terminal gate —
the same failure class this issue's Summary describes as already having
happened once.

## Acceptance Criteria

1. `ll-loop validate` flags an `action_type: shell` state whose `python3`
   action contains a literal set/frozenset that is a subset of
   `NON_LLM_EVALUATOR_TYPES` or the keys of `EVALUATOR_REQUIRED_FIELDS`, at
   `warning` severity, naming the state and the exported table to import
   instead.
2. A state with an escape-hatch suppression comment does not raise the
   warning.
3. Running the rule against the current built-in loop set (post-fix) produces
   zero violations — this rule ships as a forward guard, not a fix for an
   existing loop.
4. The rule is documented in
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` § The Design Rules alongside
   MR-1..MR-14, with its own MR number and the retry-reachability item
   (below) captured as a related-but-unmechanized heuristic.

## Motivation

A restated (rather than imported) rule table doesn't just miss defects — when
the restatement is a proper subset of what the terminal gate checks, it
launders them: every downstream pass gets false confidence, and detection
gets pushed to a point where the retry topology can no longer reach the state
that made the mistake (as BUG-3326 describes for the resulting `emit_artifact`
retry). Catching this at lint time, at the state where the drift is
introduced, is strictly cheaper than debugging it after a run fails three
states later.

## Proposed Solution

Add `_validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]` to
`scripts/little_loops/fsm/validation/meta_rules.py`, following the shape of
the existing `_validate_*` MR functions there (e.g.
`_validate_artifact_isolation` for MR-3). Detection sketch:

```python
# For each state with action_type == "shell" whose action contains "python3":
#   parse literal set/frozenset displays via ast (not regex, to avoid
#   false positives on string content)
#   for each known exported table (NON_LLM_EVALUATOR_TYPES,
#   EVALUATOR_REQUIRED_FIELDS.keys()):
#     if the literal's members are a non-empty subset of the table's keys
#     and the action does not already import that table:
#       emit a warning naming the state, the literal, and the table to
#       import instead
#   Skip if the action contains an escape-hatch comment
#   (e.g. `# gate-completeness: intentional-subset`)
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation/meta_rules.py` — new
  `_validate_gate_completeness` function, registered alongside the other
  `_validate_*` MR checks
- `scripts/little_loops/fsm/validation/__init__.py` — export/wire the new
  rule into the validation pipeline (same pattern as `EVALUATOR_REQUIRED_FIELDS`,
  `NON_LLM_EVALUATOR_TYPES` re-exports at lines 47-49, 164-166)
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — add the new rule to § The
  Design Rules (MR-1..MR-14 table) and add the Non-Goal below as a review
  heuristic

### Dependent Files (Callers/Importers)
- `ll-loop validate` CLI — surfaces the new warning through its existing
  output path, no new integration needed

### Similar Patterns
- `_validate_artifact_isolation` (MR-3) and
  `_validate_meta_loop_evaluation` (MR-1/MR-2) in `meta_rules.py` are the
  closest existing shape: FSM-wide static checks returning
  `list[ValidationError]`

### Tests
- `scripts/tests/` — new test(s) for `_validate_gate_completeness`: positive
  case (literal subset of `NON_LLM_EVALUATOR_TYPES` without import triggers
  warning), negative case (import present, or escape-hatch comment present,
  suppresses it), and a full-suite run confirming zero violations against
  current built-in loops

### Documentation
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` — § The Design Rules (new MR
  entry) and a new heuristic note for retry-reachability (see Non-Goal)

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-26 — based on codebase analysis:_

- Confirmed exact shape of `ValidationError`/`ValidationSeverity` in `scripts/little_loops/fsm/validation/_base.py`: `ValidationSeverity` is a two-value `Enum` (`ERROR`, `WARNING`); `ValidationError` is a `@dataclass` with `message: str`, `path: str | None = None`, `severity: ValidationSeverity = ValidationSeverity.ERROR`.
- Confirmed MR registration pipeline: `validate_fsm(fsm, orchestration_request_path=None) -> list[ValidationError]` in `structural_rules.py` calls every `_validate_*` check via `errors.extend(_validate_XXX(fsm))` in a fixed sequence. Adding a new rule requires: (1) implement `_validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]` in `meta_rules.py`, (2) import it into `structural_rules.py`, (3) add its `errors.extend(...)` call inside `validate_fsm()`, (4) re-export the function and any new constants from `scripts/little_loops/fsm/validation/__init__.py` in both the `from ... import (...)` block and `__all__` (matches the issue's own citation of lines 47-49/164-166 for the existing re-exports).
- Confirmed `_validate_artifact_isolation` (MR-3) and `_validate_meta_loop_evaluation` (MR-1/MR-2) shapes as the sibling pattern: both operate on `state.action` as a raw string via compiled module-level `re.Pattern` constants (`_SHARED_TMP_PATH_RE`, `_META_LOOP_ACTION_PATTERNS`) — **no rule in this package uses `ast.parse`, `ast`, or `shlex` on embedded shell/Python bodies today**; every action-text lint (MR-3, MR-5, MR-6, MR-7/9/11 in `shell_safety.py`) is regex-over-raw-string. A new rule wanting more than substring/regex matching on literal set/frozenset syntax would need to introduce its own detection utility — none is currently shared/reusable.
- Confirmed `NON_LLM_EVALUATOR_TYPES` is *derived*, not hand-listed: `frozenset[str] = frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {"llm_structured", "comparator", "contract", "advisor_consult"}` in `_base.py`. This directly supports the issue's rationale — a literal copy of this set drifts silently whenever `EVALUATOR_REQUIRED_FIELDS` changes, since the derived set updates automatically but a pasted literal does not.
- **Escape-hatch convention correction**: no inline source-comment suppression convention (e.g. the issue's proposed `# gate-completeness: intentional-subset`) exists anywhere in `fsm/validation` today. Every existing MR rule's escape hatch is a top-level loop YAML boolean flag instead (e.g. `meta_self_eval_ok`, `shared_state_ok`, `generator_fix_ok`, `partial_route_ok`, all enumerated in `KNOWN_TOP_LEVEL_KEYS` in `_base.py`), referenced directly in the `ValidationError.message` text. A `gate_completeness_ok: true` top-level flag would match established convention; an inline comment marker would be a new, inconsistent suppression mechanism for this codebase.
- `ll-loop validate` severity surfacing (`cmd_validate` in `scripts/little_loops/cli/loop/config_cmds.py`): plain-text mode raises on ERROR only and does not currently print WARNING-severity results in its success path (they're returned but unused); `--json` mode always includes warnings in the `violations` array with `"severity": "warning"` and `"valid": true`. A new WARNING-severity rule will be visible via `--json` immediately but silent in the default CLI success output until/unless that gap is separately addressed.
- Reference implementation already in-repo: `workflow-generator.yaml`'s `validate_evaluators` state is the positive control this rule must not flag (imports `EVALUATOR_REQUIRED_FIELDS`/`NON_LLM_EVALUATOR_TYPES` directly, with an inline comment stating the import-not-restate rationale) — useful as the concrete "correct" fixture for the rule's negative test case.

## Program Design

### Types

- `ValidationError` — existing type returned by all `_validate_*` MR
  functions in `meta_rules.py`; reused, not extended

### Signatures

- `_validate_gate_completeness(fsm: FSMLoop) -> list[ValidationError]`

### Call Path

`_validate_artifact_isolation` (existing MR-3 check, same file, same
`FSMLoop -> list[ValidationError]` shape) is the sibling `_validate_gate_completeness`
is added next to in `meta_rules.py`; the validation pipeline invokes both the
same way: `ll-loop validate` -> validation pipeline
(`scripts/little_loops/fsm/validation/__init__.py`) -> `_validate_gate_completeness`
-> per offending `shell` state, parses the `python3 -c` action body and checks
literal set/frozenset displays against the exported tables in
`scripts/little_loops/fsm/validation/_base.py`

## Implementation Steps

1. Implement `_validate_gate_completeness` in `meta_rules.py`, parsing shell
   action bodies with `ast` to find literal set/frozenset displays.
2. Wire the new check into the validation pipeline in
   `fsm/validation/__init__.py`, following the existing MR registration
   pattern.
3. Add the escape-hatch comment convention and honor it in the check.
4. Add tests: positive (unimported subset triggers warning), negative
   (imported or suppressed), and a full built-in-loop-set run at zero
   violations.
5. Document the new MR rule and the retry-reachability non-goal heuristic in
   `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md`.

## Impact

- **Priority**: P3 — a forward guard against a failure class that has
  occurred once and is now fixed; no current violations, so no urgency, but
  meaningful to prevent recurrence
- **Effort**: Medium — new static-analysis check plus `ast`-based parsing of
  shell action bodies, tests, and doc updates
- **Risk**: Low — additive `warning`-severity check with an escape hatch; does
  not change existing loop behavior or fail builds
- **Breaking Change**: No

## Proposed Rule

**Gate-completeness (MR-rule candidate).** For a loop whose terminal gate is a
little-loops validator, flag any intermediate `shell` gate that hardcodes a literal
set of values which the validator exposes as an importable table — e.g. a literal
evaluator-type set instead of `NON_LLM_EVALUATOR_TYPES`, or literal required-field
lists instead of `EVALUATOR_REQUIRED_FIELDS`. Where the terminal gate exposes its
rules as data, import rather than restate.

Detection sketch: in `fsm/validation`, for each `action_type: shell` state whose
action contains `python3`, look for a literal set/frozenset whose members are a
subset of a known exported table's keys. Severity `warning` is probably right to
start — a restatement is sometimes deliberate (a *narrower* curated vocabulary), so
an escape hatch comment should suppress it.

Current blast radius: `workflow-generator.yaml` was the only built-in doing this,
and it has been fixed, so the rule would ship with zero violations and act purely as
a forward guard.

## Non-Goal (document, don't mechanize)

**Retry reachability** — for each bounded-retry edge, can the state it routes to
actually repair every fault class that triggers it? Real and worth checking, but the
fault-class-to-state mapping is semantic and resists static analysis. Add this to
`docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` as a review heuristic alongside the MR
rule table rather than attempting a lint.

Source: `postmortems/workflow-generator-output-json-gate-gap.md` §6.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-26 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-08-26T19:14:22 - `0809cdb6-a88f-42a7-9e51-e57ee8a63f3a.jsonl`
- `/ll:format-issue` - 2026-08-26T19:09:04 - `8c47cf34-66af-4a75-8c4b-c7a8efe5d7ec.jsonl`
