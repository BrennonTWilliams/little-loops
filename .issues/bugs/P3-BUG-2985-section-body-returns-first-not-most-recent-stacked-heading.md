---
id: BUG-2985
title: _section_body returns the first matching heading, not the most recent, on issues with stacked repeat sections
type: BUG
priority: P3
captured_at: "2026-08-02T01:30:00Z"
discovered_date: 2026-08-02
discovered_by: capture-issue
labels:
- issue-parser
- set-flags
- confidence-check
---

# BUG-2985: _section_body returns the first matching heading, not the most recent, on issues with stacked repeat sections

## Summary

`_section_body_with_offset()` (`scripts/little_loops/issue_parser.py:199-214`)
locates a `## heading` section with a single `re.search()` call, which always
returns the **first** match in the document. Most `## heading` names are
unique per file, so this is harmless — but `## Confidence Check Notes` is
appended fresh by every `/ll:confidence-check` run without removing prior
occurrences (see `commands`/`skills/confidence-check` Phase 4.5), so an issue
that has been through multiple confidence-check passes accumulates several
stacked `## Confidence Check Notes` sections. Any reader of that heading gets
the **oldest, most stale** occurrence instead of the current one.

## Current Behavior

`ll-issues set-flags <ID>` (no `--from-notes`) calls
`apply_flags_from_notes()` (`scripts/little_loops/cli/issues/set_flags.py:238`),
which does:

```python
notes = _section_body(content, "Confidence Check Notes") or ""
```

`_section_body` → `_section_body_with_offset` (`issue_parser.py:207-213`) runs
`re.search(r"^##\s+Confidence Check Notes\s*$", content, re.MULTILINE)` — the
**first** regex match — then bounds the body at the next `^##\s` line. On an
issue with several stacked `## Confidence Check Notes` sections (one per
historical confidence-check run), this returns the body of the **first**
(oldest) one, not the most recently appended one.

Reproduced live on `ENH-2866`
(`.issues/enhancements/P2-ENH-2866-record-dequeue-time-commit-sha-at-orchestrator-dequeue-and-worktree-creation.md`),
which has five stacked `## Confidence Check Notes` sections. Its oldest
section (from 2026-07-30) contains the phrase "open decision" describing a
scope question that was fully resolved in a later pass (with decision
fragments `61df2043`/`4f66ef35` recorded and `decision_needed` cleared). Every
subsequent `/ll:confidence-check` run whose own (current, no-open-decisions)
notes should leave `decision_needed` untouched instead re-triggers the
`decision_needed: true` flag by matching stale phrasing several sections
above the current one. This has now recurred at least twice on this same
issue (2026-08-01 and 2026-08-02), each requiring a manual frontmatter
correction, per its own `## Session Log`.

## Expected Behavior

`_section_body`/`_section_body_with_offset`, and any caller that expects "the
current state of this section" (`apply_flags_from_notes` being the clearest
example), should resolve the **last** occurrence of a repeatable heading, not
the first. For headings that only ever appear once (the common case), this is
a no-op change in behavior.

## Root Cause

`issue_parser.py:208`:

```python
match = re.search(pattern, content, re.MULTILINE)
```

`re.search` returns the first match. There is no `finditer`/loop to find the
last match, and no caller passes an intent flag distinguishing "first
occurrence" from "most recent occurrence" semantics. `## Confidence Check
Notes` is the one common heading in this codebase's issue template that is
designed to be appended repeatedly (Phase 4.5 of `skills/confidence-check`
always inserts a fresh section rather than replacing the existing one), which
makes it the heading most exposed to this defect.

## Proposed Solution

Change `_section_body_with_offset` to find the **last** match of the heading
pattern before computing the body span, e.g. iterate `re.finditer(...)` and
keep the final match, then apply the existing next-`##`-line bounding logic
from that match's end. This fixes every caller uniformly (`set_flags.py:273`,
plus the other `_section_body`/`_section_body_with_offset` call sites at
`issue_parser.py:435`, `:744`, `:812`, `:821`) without needing per-caller
opt-in, since "most recent occurrence" is the correct read for every existing
caller — none of them currently rely on first-match semantics for a
multi-occurrence heading (only `## Confidence Check Notes` triggers the
distinction in practice today).

## Program Design

### Signatures

- `_section_body_with_offset(content: str, heading: str) -> tuple[str, int] | None`
  (`scripts/little_loops/issue_parser.py:199`) — change the match-selection
  from first-match (`re.search`) to last-match (iterate `re.finditer` and take
  the final result), keeping the same next-`##`-line bounding logic and return
  contract.

### Call Path

`ll-issues set-flags` → `apply_flags_from_notes()`
(`cli/issues/set_flags.py:238`) → `_section_body(content, "Confidence Check Notes")`
(`issue_parser.py:217`) → `_section_body_with_offset()` (`issue_parser.py:199`, fixed here)

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_parser.py` — `_section_body_with_offset()`

### Dependent Files (Callers)
- `scripts/little_loops/cli/issues/set_flags.py:273` — the caller that
  surfaced this bug
- `scripts/little_loops/issue_parser.py:435`, `:744`, `:821` — other
  `_section_body`/`_section_body_with_offset` callers; verify none depend on
  first-match semantics for a repeatable heading (none currently do, since no
  other common heading is appended repeatedly)

### Tests
- `scripts/tests/test_issue_parser.py` — add a case with two stacked
  identical `## Confidence Check Notes` (or any other) headings, asserting
  `_section_body`/`_section_body_with_offset` returns the **last** one's body
- `scripts/tests/test_set_flags.py` (or wherever `apply_flags_from_notes` is
  tested) — add a regression case modeled on `ENH-2866`: an issue with two
  stacked `## Confidence Check Notes` sections where only the first contains
  decision-flag-triggering phrasing; assert `set-flags` does NOT set the flag

## Impact

Low blast radius (one function, five call sites, only one heading type
currently exposed) but directly undermines the "set-only, CLI is the source
of truth" contract `/ll:confidence-check` Phase 4.6 relies on: a false
positive here forces a manual frontmatter correction every time an issue with
a long confidence-check history gets re-checked, which is exactly the kind of
silent drift the CLI-as-source-of-truth design was meant to prevent.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Session Log
- `/ll:capture-issue` - 2026-08-02T01:26:17 - `b10f0b3a-574a-4cd1-aefd-c6a613922849.jsonl`
