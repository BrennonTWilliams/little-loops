---
id: ENH-3018
title: skills/init/SKILL.md cites stale cli.py line numbers for _run_plan/_run_apply
type: ENH
status: open
priority: P4
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
program_design_not_applicable: true
testable: false
labels:
- docs
- skills
- ll-init
---

# ENH-3018: `skills/init/SKILL.md` cites stale `cli.py` line numbers for `_run_plan`/`_run_apply`

## Summary

`skills/init/SKILL.md:140-141` cites hardcoded line ranges for `_run_plan`
(`cli.py:525-593`) and `_run_apply` (`cli.py:597-678`) in
`scripts/little_loops/init/cli.py`. As of this audit, the actual functions are
at `_run_plan` = `cli.py:560-629` and `_run_apply` = `cli.py:632-719` — both
have already drifted from the cited ranges, a concrete example of the
fragile-line-reference pattern this file relies on.

## Current Behavior

`SKILL.md` embeds exact line numbers that will drift every time `cli.py` is
edited above those functions, silently going stale with no test or lint
catching it (this is markdown prose, not code the test suite parses for line
accuracy).

## Scope Boundaries

In scope: `skills/init/SKILL.md:140-141` and a spot-check of other line-number
references in that same file. Out of scope: auditing line-number references
across all other skill files (separate effort if warranted).

## Expected Behavior

References to `_run_plan`/`_run_apply` should point readers to the function by
name (and file) without committing to line numbers that will inevitably drift,
or — if line numbers are valuable for quick navigation — should be
periodically re-verified rather than assumed durable.

## Suggested Fix Direction

Update `SKILL.md:140-141` to the current line numbers as an immediate fix, and
consider dropping line-number citations in favor of `` `cli.py`'s `_run_plan`
function `` style references (function-name-only) to avoid repeat drift. If
other line-number references exist elsewhere in `skills/init/SKILL.md` or
sibling skill files, spot-check those too during implementation.

## Status

**Open** | Created: 2026-08-02 | Priority: P4

## Impact

- **Priority**: P4 — cosmetic/maintainability, not user-facing (this file is
  agent-consumed prompt text, not shipped documentation).
- **Effort**: Trivial.
- **Risk**: None.
- **Breaking Change**: No.
