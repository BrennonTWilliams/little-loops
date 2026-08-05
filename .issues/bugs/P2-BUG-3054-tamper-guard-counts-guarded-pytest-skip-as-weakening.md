---
id: BUG-3054
title: Tamper guard counts conditional pytest.skip() guards as test weakening
type: BUG
priority: P2
status: done
testable: true
discovered_by: run-forensics
discovered_date: 2026-08-05
captured_at: '2026-08-05T05:42:22Z'
completed_at: '2026-08-05T05:42:22Z'
relates_to:
- BUG-2954
- ENH-2964
- BUG-2957
- ENH-3046
- BUG-3058
labels:
- automation
- tamper-guard
- false-positive
---

# BUG-3054: Tamper guard counts conditional pytest.skip() guards as test weakening

## Summary

`measure_test_strength()` counts any `ast.Call` whose final attribute is `skip`
as a skip marker, identically to an `@pytest.mark.skip` decorator. A defensive
`pytest.skip()` inside an `if` guard — the standard way to skip when a fixture
file isn't present in a given checkout — therefore reads as test tampering.

Because `_weakened()` is an OR over three clauses, a single added guard vetoes a
change even when assertions and test-function counts both rise. Under the
default `tamper_guard.policy: fail`, that veto blocks `ll-auto` from marking an
otherwise complete issue as done.

## Steps to Reproduce

1. Take a test file with no skip markers.
2. Add a new test containing an environment guard:
   ```python
   if not candidates:
       pytest.skip("fixture not present in this checkout")
   ```
   plus new assertions and new `test_*` functions — a strictly additive edit.
3. Run the guard over the before/after pair:
   ```python
   from little_loops.test_tamper_guard import is_weakening
   is_weakening(before_src, after_src, "scripts/tests/test_x.py")
   ```
4. Observe `True`, despite the file having gained coverage and lost nothing.

Live instance: the `ll-auto --only ENH-3046` run of 2026-08-04 22:17. The
implement phase added `TestCheckFormatGapsSoftDepHardEdge` to
`scripts/tests/test_issue_parser.py` with two guarded skips. Measured across
that diff: assertions 382 → 385, test functions 227 → 230, skip markers 0 → 2.

## Current Behavior

`scripts/little_loops/test_tamper_guard.py:275-280` (pre-fix):

```python
elif isinstance(node, ast.Call):
    name = _call_name(node.func)
    if name.startswith("assert") or name == "raises":
        assertions += 1
    elif name == "skip":
        skip_markers += 1
```

Two consequences:

- **Nesting is ignored.** A skip reached only under `if`/`try`/loop/`with` is
  counted the same as one on the always-executed path.
- **The match is too broad.** Any `*.skip(...)` call qualifies, so an unrelated
  `runner.skip(...)` or `queue.skip(...)` inflates the count.

The ENH-2964 cross-file netting cannot compensate: `_subtract()` only lowers
`before`, and `before.skip_markers` is already 0, so
`after.skip_markers > adjusted_before.skip_markers` stays true. The skip clause
is structurally un-nettable.

Downstream, `work_verification.py:_run_non_fsm_tamper_guard` logs
`Tamper guard (fail) failed: [...] not resolved` and `issue_manager.py`
logs `REFUSING to mark <ID> as completed: tamper guard vetoed the changes`.

## Expected Behavior

A `pytest.skip()` reached only under a conditional is an environment guard, not
a disabled test, and must not count. A `pytest.skip()` on an always-executed
path does neuter its test and must still count, alongside the
`skip`/`skipif`/`xfail` decorators. Only `pytest.skip` and a bare imported
`skip` qualify; other `*.skip()` calls are unrelated APIs.

Concretely, for the ENH-3046 diff: `is_weakening` returns `False` for all three
touched test files.

## Root Cause

The metric was specified in BUG-2954 as an aggregate per-file count and never
distinguished reachability. Counting `pytest.skip()` calls at all was a
deliberate addition (a bare skip at the top of a body is a real neutering
vector), but it was implemented as a flat `ast.walk` match with no notion of
whether the call sits on a conditional branch.

## Program Design

Skip-call counting moves out of the flat walk into a reachability-aware helper.

### Signatures

- `_is_pytest_skip(func: ast.expr) -> bool` — new, `test_tamper_guard.py`.
- `_count_unconditional_skip_calls(node: ast.AST) -> int` — new, `test_tamper_guard.py`.
- `measure_test_strength(source: str, path: str) -> TestStrength | None` — existing, `test_tamper_guard.py:235`; call-branch removed from its walk.
- `_CONDITIONAL_NODES: tuple[type[ast.AST], ...]` — new module constant.

### Call Path

`is_weakening` (`test_tamper_guard.py:297`) -> `measure_test_strength` (`test_tamper_guard.py:235`) -> `_count_unconditional_skip_calls`; verdict consumed by `_weakened` (`test_tamper_guard.py:287`) and `filter_weakening_findings` (`test_tamper_guard.py:333`), reported through `_run_non_fsm_tamper_guard` (`work_verification.py:76`).

`_count_unconditional_skip_calls` recurses via `ast.iter_child_nodes`, returning
early on any node in `_CONDITIONAL_NODES`, so only always-executed statements are
visited. Decorator counting in `measure_test_strength` is unchanged; the call
branch is removed from the walk and replaced by a single
`skip_markers += _count_unconditional_skip_calls(tree)` after it.

`_is_pytest_skip` narrows the match: an `ast.Attribute` must have
`value` = `Name(id="pytest")`, or the node must be a bare `Name(id="skip")`.

## Implementation Steps

1. Add `_CONDITIONAL_NODES`, `_is_pytest_skip`, and
   `_count_unconditional_skip_calls` to `scripts/little_loops/test_tamper_guard.py`.
2. Remove the `elif name == "skip"` branch from `measure_test_strength`'s walk;
   add the helper call before the `TestStrength` construction.
3. Update the `measure_test_strength` docstring, which documented the old
   unconditional-count behavior.
4. Add cases to `scripts/tests/test_test_tamper_guard.py`: conditional guard,
   try-block guard, unconditional body skip, non-pytest `*.skip()`, and an
   end-to-end `is_weakening` assertion on the ENH-3046 shape.

## Impact

Blocked completion of a fully correct `ll-auto` run. The implementation, tests,
lint, and types were all green; 21.6 minutes of work was left uncommitted with
the issue still `status: open`, and the issue was marked to be skipped on future
runs.

Severity is amplified by the interaction with TDD mode: the guard's stated
purpose is catching an agent that weakens tests to make them pass, so a false
positive here directly penalizes the additive-test behavior the project wants.

## Resolution

Fixed in `scripts/little_loops/test_tamper_guard.py`. Verified against the exact
commit that triggered the veto (`48c5e7e5`, ENH-3046):

| file | assertions | test fns | skips | weakening |
|---|---|---|---|---|
| `test_issue_parser.py` | 382 → 385 | 227 → 230 | 0 → 0 | False |
| `test_ll_issues_format_check.py` | 139 → 147 | 61 → 65 | 0 → 0 | False |
| `test_refine_issue_command.py` | 59 → 64 | 48 → 51 | 0 → 0 | False |

The pre-existing `test_counts_asserts_test_functions_and_skip_markers` case
(unconditional `pytest.skip('nope')` plus an `@pytest.mark.skip` decorator) still
reports 2, confirming real neutering is undiminished.

## Status

**Completed** — 2026-08-05

## Session Log
- `hook:posttooluse-status-done` - 2026-08-05T05:43:13 - `fb7ca535-1f06-49a2-8ac3-7943736f7215.jsonl`

- run-forensics - 2026-08-05 - Root-caused from the failed `ll-auto --only
  ENH-3046` run; fix and tests applied.
