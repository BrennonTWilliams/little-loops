---
id: BUG-3229
type: BUG
title: 'll-sprint: _find_issue_path''s glob requires a priority prefix, so an unprefixed
  issue file reports "not found" while ll-issues list shows it'
priority: P2
status: open
discovered_by: little-loops-hermes-audit
discovered_date: '2026-08-16'
labels:
- sprint
- issue-management
testable: true
---

# BUG-3229: ll-sprint: _find_issue_path's glob requires a priority prefix, so an unprefixed issue file reports "not found" while ll-issues list shows it

## Summary

`SprintManager._find_issue_path` (`scripts/little_loops/sprint.py:426`) locates issue files with `issue_dir.glob(f"*-{issue_id}-*.md")` (line 443). That pattern requires a literal `-` before the ID, so it matches `P2-BUG-002-slug.md` but **cannot** match `BUG-002-slug.md` — `*` may match empty, but the `-` preceding the ID is literal and has nothing to match against.

`IssueParser`'s own discovery has no such requirement: `ll-issues list` finds unprefixed files and renders them normally (defaulting them to P5). The two disagree, so an issue that is visibly present in the backlog is invisible to every sprint operation that resolves IDs through `_find_issue_path` — `validate_issues` (line 470), `load_issue_infos` (line 492), and EPIC synthesis (line 311).

The user is not left in silence, but the diagnosis they are given is false, and in the EPIC case it names the wrong noun entirely.

## Current Behavior

Probed live against a scratch project containing exactly two bug files — `BUG-001-no-priority-prefix.md` and `P2-BUG-002-has-prefix.md` — and one epic, `EPIC-100-unprefixed-epic.md`.

`ll-issues list` sees all three:

```
Bugs (2)
  P2  BUG-002  An issue with a priority prefix
  P5  BUG-001  An issue with no priority prefix

Epics (1)
  P5  EPIC-100  An epic with no priority prefix
```

`ll-sprint create probe --issues BUG-001,BUG-002` reports the existing file as missing:

```
[..] Issue IDs not found: BUG-001
[..] Created sprint: probe
[..]   Issues: BUG-001, BUG-002
[..]   Invalid issues: BUG-001
```

`ll-sprint show probe` then plans one issue instead of two and reports `Sprint health: WARNING -- 1 issue(s) not found on disk`.

The EPIC path is the worst presentation. `ll-sprint show EPIC-100` prints:

```
[..] Sprint not found: EPIC-100
```

`load_or_synthesize` (line 311) gets `None` from `_find_issue_path` and returns `None` at line 313, which the caller renders as a missing **sprint**. The epic is right there in `ll-issues list`; nothing in the message points at the epic file, let alone at its filename.

## Expected Behavior

An issue file that `ll-issues list` displays should resolve for every sprint operation, regardless of whether its filename carries a priority prefix. Failing that, the diagnostic should name the real cause ("found `BUG-001-no-priority-prefix.md`, but its filename has no `P<n>-` prefix") rather than asserting the issue does not exist — and the EPIC path should not report a missing *sprint* for a present epic.

## Steps to Reproduce

1. In a project with `.issues/bugs/`, create `BUG-001-no-priority-prefix.md` with valid frontmatter (`id: BUG-001`, `type: BUG`, `status: open`) and a normally-named control, `P2-BUG-002-has-prefix.md`.
2. Run `ll-issues list` — both are listed.
3. Run `ll-sprint create probe --issues BUG-001,BUG-002` — observe `Issue IDs not found: BUG-001` and `Invalid issues: BUG-001`.
4. Run `ll-sprint show probe` — observe a one-issue execution plan and a `WARNING -- 1 issue(s) not found on disk` health line.
5. Create `.issues/epics/EPIC-100-unprefixed-epic.md` with `relates_to: [BUG-002]`.
6. Run `ll-sprint show EPIC-100` — observe `Sprint not found: EPIC-100`, naming the wrong noun for an epic that `ll-issues list` displays.

## Proposed Solution

Resolve through the parser's own discovery rather than an independently-derived glob. `load_or_synthesize` already imports `find_issues` from `little_loops.issue_parser` four lines below the `_find_issue_path` call that failed (line 316) — the function that *would* have found the file is already on hand at the call site.

The narrow fix is to widen the glob to `f"*{issue_id}-*.md"` and keep the existing anchored `parse_issue_filename` re-check (lines 444-451), which already exists to reject a slug that merely embeds another issue's `TYPE-NNN`. That re-check is what makes widening safe: the glob becomes a cheap prefilter and the anchored parse stays the arbiter.

Either way the sprint-side resolver and `IssueParser` should agree on what counts as an issue file, since disagreement between them is the whole defect.

Whatever the resolution, the EPIC branch should distinguish "no such epic" from "epic found but unusable" so `ll-sprint show EPIC-100` stops reporting a missing sprint for an epic that exists.

## Impact

- **Priority**: P2 — Not a silent data loss (a warning is printed), but a false diagnosis on a path users act on: they are told an issue does not exist while `ll-issues list` shows it, so the natural next step is to re-create an issue that is already there. The EPIC case misdirects entirely, pointing at sprints rather than at the epic file.
- **Effort**: Small — one glob pattern, plus a message change on the EPIC branch if that is taken.
- **Risk**: Low for the glob widening, because the anchored `parse_issue_filename` re-check at lines 444-451 already guards the false-positive case that motivated the narrow pattern.
- **Breaking Change**: No — strictly widens what resolves. Files that resolve today continue to.

## Root Cause

Two independent definitions of "an issue file on disk" drifted apart:

- `_find_issue_path` (`sprint.py:443`): `glob(f"*-{issue_id}-*.md")` — requires a prefix token before the ID.
- `IssueParser` / `find_issues`: no prefix requirement; a missing priority prefix is tolerated and defaulted to P5 at display time.

The glob's leading `*-` encodes an assumption that every issue filename is normalized to `P<n>-TYPE-NNN-slug.md`. `ll-issues normalize` exists precisely because that is not guaranteed, and `ll-issues list` renders unprefixed files as first-class — so the assumption is not one the rest of the system makes.

## Notes

Found while auditing `little-loops-hermes`, which shells out to these CLIs; the defect is entirely upstream and reproduces with the CLIs alone.

## Status

**Open** | Created: 2026-08-16 | Priority: P2
