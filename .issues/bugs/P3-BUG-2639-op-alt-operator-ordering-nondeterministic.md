---
id: BUG-2639
type: BUG
priority: P3
status: done
captured_at: 2026-07-14 19:59:22+00:00
completed_at: '2026-07-14T20:00:20Z'
discovered_date: 2026-07-14
discovered_by: manage-issue
---

# `_OP_ALT` operator ordering is non-deterministic (flaky edit-routes test)

## Summary

`_COND_PATTERN` in `scripts/little_loops/fsm/route_table.py` was compiled from an
operator alternation whose ordering varied per process, making
`test_ll_loop_edit_routes.py::TestCompoundGridParser::test_cond_pattern_is_derived_not_hardcoded`
flaky — it failed on any run whose `PYTHONHASHSEED` happened to reproduce the
forbidden literal `>=|<=|==|!=|<|>`.

## Root Cause

`route_table.py:385` built the alternation with:

```python
_OP_ALT = "|".join(sorted(_ALL_OPS, key=len, reverse=True))
```

- `_ALL_OPS` (`policy_rules.py:28`) is a `frozenset`:
  `{">=", "<=", "==", "!=", "<", ">"}`.
- `sorted(..., key=len)` is stable only *within* each length group. The relative
  order of the four 2-char ops (and the two 1-char ops) among themselves came
  straight from frozenset iteration order, which Python randomizes per process
  via `PYTHONHASHSEED`.
- So `_COND_PATTERN.pattern` differed on every run (confirmed: 5 seeds produced 5
  distinct orderings).

The regex was always *functionally* correct — longest-match only requires 2-char
ops to precede their 1-char prefixes, which `key=len, reverse=True` guarantees
regardless of intra-length order — so no loop behavior was ever affected. The
only breakage was the flaky test plus a gratuitously non-deterministic compiled
pattern.

`test_cond_pattern_is_derived_not_hardcoded` (added under ENH-2334) asserts the
old hardcoded literal `">=|<=|==|!=|<|>"` does not appear verbatim in
`_COND_PATTERN.pattern`. Whenever the hash seed ordered the 2-char ops as
`>=,<=,==,!=`, the derived pattern coincidentally reproduced that exact literal
and the assertion failed.

## Fix

Add an alphabetical tiebreaker so the ordering is stable across processes
(`route_table.py:385`):

```python
_OP_ALT = "|".join(sorted(_ALL_OPS, key=lambda op: (-len(op), op)))
```

`_OP_ALT` is now `!=|<=|==|>=|<|>` on every seed — deterministic and never equal
to the forbidden literal. Longest-match correctness is unchanged: 2-char ops
still precede their 1-char prefixes.

## Files Modified

- `scripts/little_loops/fsm/route_table.py:383-388` — deterministic secondary
  sort key on `_OP_ALT`, with an explanatory comment.

## Verification

- `_OP_ALT` identical across `PYTHONHASHSEED` 0/1/2/42/777 (`!=|<=|==|>=|<|>`).
- `python -m pytest scripts/tests/test_ll_loop_edit_routes.py` — 69 passed across
  seeds 0/3/42/99 (previously flaky).

## Acceptance Criteria

- [x] `_OP_ALT` / `_COND_PATTERN.pattern` is identical across processes regardless
      of `PYTHONHASHSEED`.
- [x] `test_cond_pattern_is_derived_not_hardcoded` passes deterministically.
- [x] Longest-match parsing preserved (2-char ops precede 1-char prefixes).

## Resolution

Fixed in commit `bd867ce4` (`fix(route-table): make _OP_ALT operator ordering
deterministic`) on branch `fix/bug-2638-next-issues-epic-exclusion`. Discovered
while implementing ENH-2630, where the full test suite drew a hash seed that
tripped the flake.


## Session Log
- `hook:posttooluse-status-done` - 2026-07-14T20:00:10 - `a0565bed-d471-4fab-acb5-39a37fa64c65.jsonl`
