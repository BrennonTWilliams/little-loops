---
id: BUG-3739
type: BUG
title: Frontmatter keys placed after the closing fence are silently ignored, and link-epics
  re-proposes Children-listed and intentionally-parentless issues as orphans
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:54:03Z'
labels:
- issues
- link-epics
- frontmatter
---

# BUG-3739: Frontmatter keys placed after the closing fence are silently ignored, and link-epics re-proposes Children-listed and intentionally-parentless issues as orphans

## Summary

Frontmatter keys written just below the closing `---` fence (for example `parent: EPIC-NNN`, `epic:`, `parentless_reason:`) are silently treated as body text. Nothing flags them, so a parent decision recorded there is invisible to every tool. `link-epics` then proposes the same issue as an orphan on every run, and it also ignores the intentional-parentless markers even when they sit in the right place.

## Current Behavior

Observed on a downstream project: a triage pass (an agent editing files by hand) linked four orphans to EPICs and marked three as intentionally parentless. All seven `key: value` lines were inserted on the line *after* the closing fence:

```
goals: [3, 7]
---
parent: EPIC-NNN
epic: EPIC-NNN

# FEAT-NNN: ...
```

What happened next:
- `parse_frontmatter()` never sees the keys, so `is_orphan()` reports all seven as orphans.
- The EPICs' `## Children` sections already listed the four linked children. That is exactly category (b) in `ll-issues epic-consistency` ("body-listed, no parent: backref"), but nothing ran that check, and `link-epics` does not consult it.
- Two weeks later, `link-epics --mode assign` proposed the four as orphans again. A follow-up manual review also missed the misplaced `parentless_reason:` lines and linked an issue to the very EPIC its recorded reason called "deliberately the wrong home".
- Separately, `is_orphan()` checks only `parent`/`epic`. It ignores `standalone: true` / `standalone_reason:` / `parentless_reason:` even when they are in the frontmatter, so deliberate "no parent" decisions get proposed again on every run.

## Expected Behavior

- A `key: value` line that matches a known issue frontmatter key and sits directly after the closing fence (before the first H1 or blank-line-separated prose) is reported as an error that names the file and the key, with a fix that moves it into the block.
- `link-epics` does not propose an orphan that an EPIC's `## Children` already lists. It reports it as category-(b) drift, with a suggestion to add the `parent:` backref.
- `is_orphan()` excludes issues marked `standalone: true` or that carry a `parentless_reason:`. Both `--json` modes report how many were skipped as intentional.

## Proposed Solution

1. Add a check (in `ll-issues verify` / the issue-format lint, with a `--fix` that moves the lines into the block) for known frontmatter keys right after the closing fence.
2. In `link_epics.py`, add the intentional markers to `is_orphan()`, and subtract the IDs listed in any EPIC's `## Children` (reusing `epic_consistency._parse_children_body`) from the candidate set, reporting them separately.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

1. In any issue, move `parent: EPIC-NNN` to the line after the closing `---`.
2. Make sure that EPIC's `## Children` lists the issue.
3. Run `ll-issues link-epics --mode assign --json`: the issue appears as an orphan.
4. Add `parentless_reason: ...` inside the frontmatter of a different orphan and run again: it is still proposed.

## Root Cause

The frontmatter parser rightly stops at the closing fence, but there is no lint for frontmatter-shaped lines that land just past it. `link-epics` builds its orphan set only from frontmatter `parent`/`epic` and does not cross-check EPIC bodies or the intentional-parentless markers.

## Acceptance Criteria

- [ ] The lint flags `parent:` / `epic:` / `parentless_reason:` / `standalone:` placed after the closing fence, and `--fix` moves them inside.
- [ ] `link-epics` skips issues with `standalone: true` or `parentless_reason:` and reports a skipped-intentional count.
- [ ] `link-epics` reports a Children-listed-but-no-backref issue as drift instead of proposing it as an orphan.
- [ ] Tests cover each case in `test_link_epics_cli.py` and the lint's test module.

## Status

**Open** | Created: 2026-10-05 | Priority: P3
