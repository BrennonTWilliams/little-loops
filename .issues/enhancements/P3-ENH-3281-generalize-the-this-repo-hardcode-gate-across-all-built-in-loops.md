---
id: ENH-3281
type: ENH
title: Generalize the this-repo-hardcode gate across all built-in loops
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-21'
captured_at: '2026-08-21T15:58:33Z'
labels:
- loops
- gate
- hardcode
- test-coverage
- follow-up
relates_to:
- ENH-3277
- BUG-3276
---

# ENH-3281: Generalize the this-repo-hardcode gate across all built-in loops

## Summary

Split out of **ENH-3277** step 6b (2026-08-21). BUG-3276 fixed one built-in loop that hardcoded
this repo's layout; `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
guards that one loop. The defect *class* — a shipped built-in loop hardcoding `scripts/`,
`scripts/tests/`, or `scripts/little_loops/`, live in every `local-editable` consuming project —
has no gate. Promote that assertion to a gate parametrized over all built-in loop files, the same
shape `test_no_inline_project_command_config_read` already uses.

## Current Behavior

`scripts/tests/test_builtin_loops.py`'s `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
asserts over `incremental-refactor.yaml` only. Any other built-in loop may hardcode a this-repo
path without failing anything.

## Expected Behavior

A parametrized gate over `scripts/little_loops/loops/**/*.yaml` fails on a this-repo path in a
state's action body, with a small documented exemption set.

## Motivation

A hardcoded this-repo path in a shipped loop is silent in this repo and broken everywhere else.
`.claude/CLAUDE.md` is explicit that all little-loops projects on this machine are
`local-editable` against this checkout, so a bad path is live in every one of them with no
reinstall step. This is the `_PENDING_CONVERSION` protection applied to the sibling defect class:
ENH-3277 converts the one known instance (`evaluation-quality.yaml:63`), which leaves the class
open to a next instance.

## Proposed Solution

Parametrize over all built-in loop files with an `_EXEMPT`-style set, mirroring
`test_bug3269_test_cmd_resolution_gate.py`.

**Scope the gate to action bodies, not comments.** A naive text match over whole files produces
mostly-illegitimate hits (see the survey below); restricting to `states[*].action` removes two of
the four non-target hits outright and makes the exemption set small enough to be meaningful.

### Exemption survey — verified 2026-08-21

ENH-3277 step 6b claimed *"only legitimate hits to exempt today are `loop-specialist-eval.yaml:12,23`"*.
That was wrong. `grep -rlE "scripts/tests|ruff check scripts|mypy scripts|scripts/little_loops"`
over `scripts/little_loops/loops/**/*.yaml` returns five files:

| File | Hit | Disposition |
|---|---|---|
| `loop-specialist-eval.yaml:12,23` | `scripts/tests/fixtures/fsm/broken-verify-loop.yaml` | **Exempt** — genuine this-repo eval fixture; the loop only makes sense in this repo |
| `cli-anything-bootstrap.yaml:453` | `scripts/little_loops/loops/lib/task-templates/…` | **Exempt** — package-internal path, not a consuming-project layout guess. Arguably should resolve via `importlib.resources` instead, but that is a separate change |
| `oracles/code-run-gate.yaml:407` | source citation inside a comment | **Not a hit** once the gate is scoped to action bodies |
| `harness-single-shot.yaml:60` | `# action: "python -m pytest scripts/tests/ -q --tb=no"` | **Change, do not exempt** — an `# EXAMPLE:` scaffold users clone, so it teaches the anti-pattern (same load-bearing-comment argument ENH-3277 makes for the three `harness-*` fallback comments). Comment-scoping the gate means it will not be caught automatically; fix it by hand in this issue |
| `evaluation-quality.yaml:63` | `ruff check scripts/` | **Already fixed** by ENH-3277 step 5 — verify it is gone before landing the gate |

Net exemption set after this issue: two files.

## Integration Map

### Files to Modify

- `scripts/tests/test_builtin_loops.py` — the incremental-refactor-only assertion it replaces
- a new gate module, or an added parametrized test alongside
  `scripts/tests/test_bug3269_test_cmd_resolution_gate.py`
- `scripts/little_loops/loops/harness-single-shot.yaml:60` — the example-comment fix

### Tests

- The gate itself is the test. Add a negative fixture (a loop YAML with a hardcoded
  `scripts/tests/` path in an action body) asserting the gate fails on it, so the gate cannot
  silently stop matching.

## Implementation Steps

1. Land ENH-3277 step 5 first (or confirm it landed) — otherwise the new gate fails on
   `evaluation-quality.yaml:63` immediately.
2. Fix `harness-single-shot.yaml:60`'s example comment by hand.
3. Write the parametrized gate over `states[*].action` bodies with the two-entry exemption set,
   modeled on `test_bug3269_test_cmd_resolution_gate.py`.
4. Retire or narrow `TestIncrementalRefactorLoop.test_no_state_hardcodes_this_repo_test_path`
   once the general gate subsumes it.
5. Verify `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — no known live defect once ENH-3277 step 5 lands; this is class-closure
  against the next instance
- **Effort**: Small
- **Risk**: Low — test-only; worst case is an over-broad match needing another exemption
- **Breaking Change**: No

## Related Key Documentation

- ENH-3277 — parent; its step 5 converts the one live instance, and its step 6b was this issue
- BUG-3276 — the original single-loop instance and the assertion being generalized

## Status

**Open** | Created: 2026-08-21 | Priority: P3


## Session Log
- `/ll:capture-issue` - 2026-08-21T15:58:40 - `da526826-2179-460f-b823-35695378ac55.jsonl`
