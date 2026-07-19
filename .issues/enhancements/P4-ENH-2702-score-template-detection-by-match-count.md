---
id: ENH-2702
title: Score template detection by match count instead of first-alphabetical
type: ENH
priority: P4
status: open
captured_at: '2026-07-19T00:00:00Z'
discovered_date: 2026-07-19
discovered_by: capture-issue
parent: EPIC-2700
labels:
- init
- cli
- detection
---

# ENH-2702: Score template detection by match count instead of first-alphabetical

## Summary

`detect_project_type()` (scripts/little_loops/init/detect.py:124-211) treats
detection as boolean: a template matches if *any one* of its `_meta.detect`
globs hits, and on multi-match the winner is simply the first alphabetically
(`matches[0]`, detect.py:202-204). There is no scoring or specificity
weighting; `detect_exclude` is the only disambiguation mechanism and must be
hand-maintained pairwise (today it only covers typescript-vs-javascript).

## Current Behavior

- A polyglot repo with both `Cargo.toml` and `pyproject.toml` resolves to
  whichever template sorts first alphabetically, regardless of which stack
  dominates.
- Adding any new template with an overlapping detect set requires remembering
  to add `detect_exclude` entries or accepting alphabetical accidents.

## Expected Behavior

Among matching templates, the winner is the one with the strongest evidence:
score = number of `detect` globs that matched, with an optional
`_meta.priority` weight as tie-breaker. `detect_exclude` keeps working as a
hard veto. Ties after scoring fall back to the current alphabetical order so
existing behavior is preserved where evidence is equal.

## Proposed Solution

- In the match loop, count matched globs per template instead of
  short-circuiting on `any()`.
- Sort matches by `(-match_count, -meta.get("priority", 0), filename)` and
  return the head.
- Print the runner-up on multi-match (`Detected: Python (Generic) —
  3/3 indicators; also matched: Rust (1/2)`), so the choice is visible and
  overridable rather than silent.
- Consider a `--type <template>` CLI override flag for explicit selection
  (useful for polyglot repos regardless of scoring quality).

## Acceptance Criteria

- Fixture: repo with `pyproject.toml` + `setup.py` + `requirements.txt` and a
  lone `go.mod` resolves to python-generic (3 matches beat 1), not
  alphabetical `go.json`.
- typescript/javascript exclusion behavior is unchanged (existing tests pass).
- Multi-match prints the alternatives considered.
- `python -m pytest scripts/tests/` exits 0.

## Scope Boundaries

- **In**: scoring within the existing single-winner model; visibility of the
  decision.
- **Out**: multi-template / polyglot merged configs (a repo still gets exactly
  one template); template content changes.

## Impact

- **Priority**: P4 — least urgent in the epic; `detect_exclude` already covers
  the one real collision shipped today. Value grows with template count.
- **Effort**: Small.
- **Risk**: Low — tie behavior preserves current ordering.

## Status

**Open** | Created: 2026-07-19 | Priority: P4
