---
id: BUG-2265
title: ll-issues set-status --cascade follows relates_to/blocked_by and mutates unrelated
  issues
type: bug
status: done
priority: P2
discovered_date: 2026-06-24
discovered_by: planning-assessment
labels:
- bug
- ll-issues
- cascade
- data-safety
---

# BUG-2265: `set-status --cascade` follows `relates_to` and cancels unrelated issues

## Summary

`ll-issues set-status <EPIC> cancelled --cascade --cascade-to cancelled`
cascades to issues linked via **`relates_to`** (and likely `blocked_by`), not
only true `parent:` children. This silently mutates unrelated, in-flight
issues — including other epics.

## Reproduction (observed 2026-06-24)

Cancelling **EPIC-1713** (Pi parity), whose frontmatter contained
`relates_to: [EPIC-1622, EPIC-1463, FEAT-992, FEAT-1480]`, produced:

```
EPIC-1713: open → cancelled
  Cascading to 6 active children (default: cancelled):
    EPIC-1463 → cancelled   ← WRONG: Codex epic, related-only, production
    EPIC-1622 → cancelled   ← related-only (separately intended, but not a child)
    FEAT-1480 → cancelled   ← related-only (was an EPIC-1622 child)
    FEAT-1714 → cancelled   ← correct (parent: EPIC-1713)
    FEAT-1715 → cancelled   ← correct
    FEAT-1716 → cancelled   ← correct
```

EPIC-1463's only true children were FEAT-1714/1715/1716. EPIC-1463 (Codex) is a
sibling/related epic and must not have been touched; it had to be manually
restored to `open`.

## Impact

- **Data safety**: cancelling/closing one epic can silently flip the status of
  unrelated epics and issues that merely appear in `relates_to`/`blocked_by`.
- The cascade summary calls them "active children", masking that they are not
  parent-children — easy to miss.
- Mitigating factor: the cascade did **not** recurse into the wrongly-cancelled
  epic's own children (EPIC-1463's children stayed open), so blast radius is one
  hop, but that hop can hit anything in the link graph.

## Expected Behavior

`--cascade` should traverse **only** `parent:` → child edges (issues whose
`parent:` equals the epic being closed), recursively. `relates_to` and
`blocked_by` are non-hierarchical association edges and must never trigger a
status mutation.

## Suspected Location

`scripts/little_loops/cli/issues.py` (or the issues service layer) —
`set-status` cascade child-discovery. Likely collects "children" by unioning
`parent`, `relates_to`, and/or `blocked_by` reverse-links instead of `parent`
alone.

## Acceptance Criteria

1. `set-status <EPIC> <status> --cascade` mutates only issues with
   `parent: <EPIC>` (transitively), never `relates_to`/`blocked_by` neighbors.
2. A regression test: an epic with a `relates_to` pointing at another epic, when
   cancelled with `--cascade`, leaves the related epic untouched.
3. The cascade summary labels the set accurately ("N parent-children").

## Impact Assessment

- **Effort**: S — likely a single child-discovery query fix + test.
- **Risk**: Medium if unfixed — silent cross-issue data corruption during
  routine epic closure.
- **Breaking Change**: No (restores intended semantics).

## Status

**Open** | Created: 2026-06-24 | Priority: P2
