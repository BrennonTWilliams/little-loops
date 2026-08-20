---
id: ENH-3259
type: ENH
title: Caller suitability gate has no repeatable fixture after ENH-3258 closed
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-20'
captured_at: '2026-08-20T00:19:48Z'
testable: true
program_design_not_applicable: true
relates_to:
- ENH-3258
---

# ENH-3259: Caller suitability gate has no repeatable fixture after ENH-3258 closed

## Summary

The § 8b caller suitability gate (ENH-3258) has no regression protection. It is a
prose rule in a markdown prompt, so it is not pytest-assertable, and the fixture that
validated it was synthetic and deleted after use. A future edit to § 8b — or a
companion-extraction that drops the `Inject at <path>` clause to fit the 500-line cap —
can silently undo it with a green test suite.

## Current Behavior

`python -m pytest scripts/tests/` covers the 500-line cap, companion registration, and
mirror drift. It does not and cannot cover whether wire-issue actually applies the gate.
ENH-3258 Implementation Step 4 is explicitly labelled "post-merge validation, not a
pytest gate."

The validating fixture was ENH-3300, a synthetic issue over real code:
`get_untracked_files()` has exactly one production caller,
`scripts/little_loops/git_operations.py:413`, inside `if untracked_files is None:`
(`:412`), whose enclosing `suggest_gitignore_patterns()` already accepts
`untracked_files: list[str] | None = None`. Both skip conditions fire. It was deleted
after the run, so the fixture no longer exists.

## Expected Behavior

The fixture is preserved and runnable on demand, so the gate can be re-validated after
any edit to § 8b or its companion.

## Motivation

ENH-3258's own risk note says the failure mode is "an LLM under-applying a prose rule
inside a 493-line prompt." That risk does not end at merge — it recurs on every
subsequent edit to the file. The one-shot fixture proved the rule works once; it
provides nothing thereafter.

Both halves need coverage, and they fail differently:
- **Suppression** — no `Update <path>` bullet for the guarded call site.
- **Injection** — an `Inject at <path>` bullet naming the parameter seam. This half was
  added only after the clean fixture showed the rule was purely subtractive, so it is
  the newer and less-exercised of the two.

## Proposed Solution

Preserve the ENH-3300 fixture as an eval task via `/ll:create-eval-from-issues` or
`/ll:verify-issue-loop`, with the issue body checked in as a fixture file rather than
living in `.issues/` (it is not real work and must not appear in the backlog).

The assertion is textual over wire-issue's dry-run output, so it needs an LLM evaluator
or a targeted grep on the emitted Wiring Phase, not an exact-match diff.

## Integration Map

### Files to Modify
- A new fixture file holding the ENH-3300 issue body — location undecided. It must not
  live in `.issues/`, since it is not real work and would pollute the backlog
- A new eval/verification loop YAML, if `/ll:create-eval-from-issues` or
  `/ll:verify-issue-loop` is the chosen mechanism

### Dependent Files (Callers/Importers)
- `skills/wire-issue/SKILL.md` § 8b and
  `skills/wire-issue/caller-suitability-gate.md` — the rule under test. Any edit to
  either is what the fixture exists to catch

### Similar Patterns
- `/ll:create-eval-from-issues` and `/ll:verify-issue-loop` both already generate FSM
  YAML from issue content; check which handles a prose-compliance assertion better
- The ENH-3258 § Session Log entry records the full fixture body, ground truth, and both
  the pass and fail outputs — reuse it rather than reconstructing

### Tests
- Not pytest-assertable by design. The completion gate is the fixture running and
  reproducing the recorded verdict, not a new test in `scripts/tests/`

### Documentation
- None expected unless a new loop is added to the built-in catalog

### Configuration
- N/A

## Implementation Steps

1. Decide where the fixture body lives and whether `/ll:create-eval-from-issues` or
   `/ll:verify-issue-loop` is the right mechanism.
2. Restore the ENH-3300 fixture body from ENH-3258's Session Log, with its recorded
   ground truth: `get_untracked_files()`'s sole production caller is
   `git_operations.py:413`, inside `if untracked_files is None:` (`:412`), enclosed by
   `suggest_gitignore_patterns(untracked_files: list[str] | None = None, ...)`.
3. Assert both halves — no `Update ...git_operations.py` bullet for that call site, and
   an `Inject at ...cli/gitignore.py:55` bullet naming the seam.
4. Run it once against the current tree and confirm it reproduces the recorded PASS.

## Program Design

N/A — `program_design_not_applicable: true`. The deliverable is a fixture body plus an
eval/verification YAML: no types, no signatures, no runtime call path. The one design
fact that matters is the fixture's recorded ground truth, stated in Implementation
Steps step 2.

## Impact

- **Priority**: P3 - the gate works today and the suite stays green; this protects
  against a future regression rather than fixing a present defect
- **Effort**: Small - the fixture body already exists in ENH-3258's Session Log and the
  ground truth is recorded there; the work is choosing a home for it and wiring one eval
  task
- **Risk**: Low - a fixture is additive and touches no production path. The real risk is
  doing nothing: the gate's only validation to date is one manual run
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: making the ENH-3258 gate re-runnable on demand.
- **Out of scope**: changing the gate itself, and asserting the fixture in the pytest
  suite — a prose-compliance check is not a unit test.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-08-20 | Priority: P3
