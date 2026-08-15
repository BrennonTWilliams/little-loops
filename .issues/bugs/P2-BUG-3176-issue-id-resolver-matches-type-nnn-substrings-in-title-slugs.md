---
id: BUG-3176
type: BUG
title: Issue-ID resolver matches TYPE-NNN substrings in title slugs, returning the
  wrong issue file
priority: P2
status: done
discovered_by: user-report
discovered_date: '2026-08-14'
captured_at: '2026-08-15T00:57:36Z'
completed_at: '2026-08-15T00:57:36Z'
relates_to:
- EPIC-3127
- ENH-3144
---

# BUG-3176: Issue-ID resolver matches TYPE-NNN substrings in title slugs, returning the wrong issue file

## Summary

`ll-issues show EPIC-3127` returned ENH-3144's card instead of the epic's. The
resolver `_resolve_issue_id` (`scripts/little_loops/cli/issues/show.py`) matched
issue identity via **substring checks over the whole filename**, so ENH-3144's
title-derived slug (`P3-ENH-3144-correct-epic-3127-tasks-extension-premise.md`)
satisfied both the numeric glob (`*-3127-*.md`) and the type check (`-EPIC-` in
the uppercased name). Because this resolver is the single funnel for `ll-issues
show/path/set-status/size/format-check/check-*` and every MCP `issue_*` tool,
any issue whose title embeds another issue's ID could hijack that ID's lookups —
including destructive ones (`set-status` writing to the wrong file).

## Root Cause

Three interacting defects:

1. **Numeric glob was positionally blind**: `*-{numeric_id}-*.md` matches the
   number anywhere in the filename, including inside the title slug.
2. **`_matches_type` was a substring check**: `-EPIC-` in the uppercased name is
   satisfied by the English words "correct epic 3127" in a slug.
3. **The BUG-2806 frontmatter fast-path required the prefixed id format**: the
   epic's frontmatter carried a bare-numeric `id: 3127` (a supported format —
   the numeric ID is the true unique identifier; the TYPE prefix is
   human-readable shorthand), so the exact-match comparison against
   `"EPIC-3127"` never fired and could not break the tie.

With both files surviving into the candidate pool and no priority hint given,
`pool[0]` won on category enumeration order (`enhancements/` before `epics/`).

## Resolution

Anchored resolution keyed on the numeric ID at the canonical filename position:

- **New shared helper** `parse_issue_filename()` in
  `scripts/little_loops/issue_parser.py`: parses the leading
  `(?:P[0-5]-)?(BUG|FEAT|ENH|EPIC)-(\d+)-` anchor into a frozen `FilenameId`
  dataclass (`priority`, `type_prefix`, `number`); returns `None` for
  legacy/unnormalized names. A slug-embedded TYPE-NNN can never satisfy it.
- **`_resolve_issue_id` rewritten to use it**: glob candidates are filtered to
  files whose anchored number equals the requested number (falling back to the
  raw glob set only when no filename parses, preserving legacy-name
  resolution); `_matches_type` compares the anchored type. The type prefix
  remains advisory (BUG-2003 stale-prefix tolerance preserved).
- **Frontmatter fast-path made format-agnostic**: both `id: EPIC-3127` and bare
  `id: 3127` now count — numeric parts are compared, and for a bare id the
  type comes from the `type:` frontmatter field when present.
- **`sprint.py` `_find_issue_path`** now verifies its glob hits against the
  anchored parse before returning them.

## Files Changed

- `scripts/little_loops/issue_parser.py` — added `FilenameId` +
  `parse_issue_filename()`
- `scripts/little_loops/cli/issues/show.py` — anchored candidate filtering,
  anchored `_matches_type`, format-agnostic `_frontmatter_identity` fast-path
- `scripts/little_loops/sprint.py` — anchored verification in `_find_issue_path`
- `scripts/tests/test_show.py` — `TestResolveIssueIdAnchored` (7 regression
  cases: typed/numeric/full-form inputs against the slug collision, collision
  file's own resolution, stale-prefix tolerance, legacy-filename fallback)
- `scripts/tests/test_issue_parser.py` — `TestParseIssueFilename` (4 cases)
- `docs/reference/API.md` — documented `parse_issue_filename`

## Verification

- TDD: regression tests written first and confirmed failing, then green.
- Live: `ll-issues show EPIC-3127` and `ll-issues show 3127` return the epic's
  card; `ll-issues show ENH-3144` still returns the enhancement.
- Full gate: `python -m pytest scripts/tests/` — 19,285 passed, 43 skipped.
  mypy, `ruff check`, and `ruff format --check` clean on all changed files.

## Session Log
- `hook:posttooluse-status-done` - 2026-08-15T00:58:06 - `651c849e-d36b-4349-a26e-93cd297a3535.jsonl`

- 2026-08-14: Investigated user-reported misresolution; confirmed the
  three-defect chain and reproduced live.
- 2026-08-14: Design constraint from user: bare numeric frontmatter `id:` MUST
  remain supported; numeric ID is the true identifier, TYPE prefix is
  display/advisory shorthand (normalizing frontmatter to TYPE-NNN is
  acceptable but never required for correct resolution).
- 2026-08-15: Implemented shared anchored resolver + consumer fixes; full test
  suite, mypy, and ruff green. Marked done.
