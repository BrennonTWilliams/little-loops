---
id: ENH-2101
title: Resolve one level of from: inheritance in _load_loop_meta so inherited metadata shows in ll-loop list
type: ENH
priority: P4
status: open
captured_at: '2026-06-12T14:10:00Z'
discovered_date: '2026-06-12'
discovered_by: fsm-loop-audit
parent: EPIC-1811
---

# ENH-2101: Resolve `from:` inheritance in `_load_loop_meta`

## Summary

`_load_loop_meta` (`scripts/little_loops/cli/loop/info.py:31-50`) reads raw YAML and never resolves `from: lib/apo-base` inheritance, so metadata defined only in the parent template (e.g. `category:`) is invisible to `ll-loop list` and README tooling. The 2026-06-12 audit worked around this by adding explicit `category:` to `apo-beam`, `apo-textgrad`, and `rn-plan-apo`, but the root cause remains: any future loop relying on inherited metadata will silently show as uncategorized.

## Expected Behavior

`_load_loop_meta` follows one level of `from:` (matching the executor's resolution path for lib templates) and merges parent metadata under child overrides, so `ll-loop list` shows inherited `category`/`labels` without requiring duplication in every child.

## Implementation notes

- One level is sufficient — the corpus has no chained `from:`; keep it cheap (this runs per-file for `ll-loop list`).
- Reuse the existing template-resolution helper used by the loader if one is importable without pulling the full FSM build; otherwise a minimal "read parent YAML, dict-merge metadata keys" is fine.
- Optionally remove the now-redundant explicit `category:` lines from the three apo-family loops once inheritance works (or keep them — explicit beats implicit; decide in implementation).

## Acceptance Criteria

- [ ] A child loop with `from: lib/apo-base` and no explicit `category:` shows the parent's category in `ll-loop list`
- [ ] Unit test covering metadata inheritance in `scripts/tests/` (cli loop info tests)
- [ ] `python -m pytest scripts/tests/` passes
