---
id: BUG-3738
type: BUG
title: 'link-epics --apply writes a placeholder child bullet, misplaces it in irregular
  ## Children sections, and churns orphan frontmatter'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-05'
captured_at: '2026-10-05T18:53:54Z'
labels:
- issues
- link-epics
---

# BUG-3738: link-epics --apply writes a placeholder child bullet, misplaces it in irregular ## Children sections, and churns orphan frontmatter

## Summary

`ll-issues link-epics --mode assign --apply` (`apply_assignment()` in `scripts/little_loops/cli/issues/link_epics.py`) writes a malformed EPIC-side `## Children` entry and places it by a rule that breaks on any non-flat Children section. It also rewrites untouched frontmatter formatting on the orphan.

## Current Behavior

Observed in a real run on a downstream project's issue tree:

1. **Placeholder instead of the child's title.** The bullet is hard-coded as `- **ENH-NNN** — (added by link-epics --apply)`, so every applied link leaves a line that a person has to fix by hand. `create.py`'s `_append_child_to_epic_children()` already writes `- **ID** — <title> (open)`.
2. **Extra blank line.** `stripped + sep + "\n" + bullet` puts a blank line between the last existing child and the new bullet, which splits the list in two.
3. **Wrong insertion point in irregular sections.** `_section_bounds()` ends the section at the next `## ` heading only, so the bullet goes at the very end of everything under `## Children`. That includes `### ` subsections (for example a "Spoke follow-through" note), dependency-note bullets, and wrapped multi-line bullets. In a manual run using the same "end of section" rule, the new line landed in the middle of a wrapped bullet, and the bullet's continuation line ended up hanging under the new child.
4. **Stray `## Children` at end of file.** When an EPIC has no `## Children` heading (some EPICs track children through `parent:` frontmatter only), apply adds a new `## Children` section after `## Status` / `## Session Log`.
5. **Frontmatter churn.** `update_frontmatter()` re-dumps the whole block: `goals: [2]` becomes a block list and long `title:` values get line-wrapped, even though only `parent:`/`epic:` changed.

## Expected Behavior

- The bullet carries the child's title (taken from its `# ID: title` H1, or from frontmatter `title:`) in the same `- **ID** — title (open)` shape that `ll-issues create --parent` writes.
- No blank line between the new bullet and the previous child.
- The insertion point is right after the last top-level child bullet (`^- \*\*(BUG|FEAT|ENH)-\d+\*\*`) and any indented continuation lines it has, and before any `###` subsection or prose.
- If the EPIC has no `## Children` section, either skip the body write (the frontmatter link alone is enough, as with `create.py`) or add the section before `## Status`. Never add it at the end of the file.
- Only the `parent:` and `epic:` lines change in the orphan's frontmatter.

## Proposed Solution

Move `_append_child_to_epic_children()` into a shared helper and make it aware of child bullets and continuation lines. Have both `create --parent` and `link-epics --apply` call it. For the orphan side, use a line-level frontmatter insert (for example, add `parent:`/`epic:` before the closing fence) rather than `update_frontmatter()`'s re-dump.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Steps to Reproduce

1. Make an EPIC whose `## Children` list is followed by a `### Notes` subsection that contains a wrapped `- ...` bullet.
2. Make an orphan ENH with `goals: [2]` in flow style.
3. Run `ll-issues link-epics --mode assign --apply --threshold 0`.
4. The new bullet lands under `### Notes`, after a blank line, with the placeholder title, and the orphan's `goals:` has been reformatted.

## Root Cause

`apply_assignment()` builds its own bullet and its own section bounds instead of reusing `create.py`'s child-wiring helper, and it writes through a full YAML re-dump.

## Acceptance Criteria

- [ ] Applied bullets carry the child title; the placeholder string is gone from the codebase.
- [ ] Tests in `test_link_epics_cli.py` for: a `###` subsection after the list, a wrapped multi-line last bullet, a missing `## Children` heading, and an existing child list (no blank line added).
- [ ] An orphan with flow-style `goals:` and a long `title:` keeps both lines byte-identical after apply.

## Status

**Open** | Created: 2026-10-05 | Priority: P3
