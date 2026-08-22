---
id: BUG-3215
type: BUG
title: issue_parser reads priority from filename prefix only, ignoring frontmatter
  `priority:` — new-style issues all default to P5
priority: P1
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-08-22'
captured_at: '2026-08-22T20:14:04Z'
decision_needed: false
---

# BUG-3215: issue_parser reads priority from filename prefix only, ignoring frontmatter `priority:`

## Summary

`IssueParser._parse_priority()` derives an issue's priority **only** from the
filename prefix (`P#-`), and falls back to the lowest tier when no prefix matches.
It never reads the `priority:` field from frontmatter. New-style issue files — priority
in frontmatter, no `P#-` prefix — therefore all parse as **P5** regardless of their true
priority, silently miscalibrating every prioritization read across the tool.

## Root cause

`scripts/little_loops/issue_parser.py`:

- `_parse_priority(self, filename)` iterates `self.config.issue_priorities` and returns
  the first whose string the filename *starts with* (`filename.startswith(f"{priority}-")`);
  if none match it returns `self.config.issue_priorities[-1]` (lowest tier).
- In the parse path, `priority = self._parse_priority(filename)` runs **before**
  `frontmatter = parse_frontmatter(content)`. The frontmatter is parsed for
  `discovered_by`, `effort`, `impact`, `confidence_score`, etc., but `priority:` is never
  read from it.

## Fix shape

Read `priority` from the frontmatter first; keep the filename-prefix scan as a fallback
for legacy `P#-`-prefixed files. Three lines: parse frontmatter `priority`, prefer it when
present and valid, else fall back to the existing prefix scan.

## Blast radius

Priority feeds `priority_int`, which sorts every issue listing. `issues_query`,
`ll-auto`, `ll-parallel`, `ll-sprint`, and `ll_next` all sort on `priority_int`, so every
one of them is miscalibrated against new-style files: any non-prefixed issue reads as
"lowest priority" and is deprioritized regardless of its declared `priority:` value.

## Acceptance criteria

- A new-style file with `priority: P1` in frontmatter and no filename prefix parses as P1.
- A legacy file with a `P1-` filename prefix still parses as P1 (backward compatible).
- A regression test covers frontmatter-first, prefix-fallback.
