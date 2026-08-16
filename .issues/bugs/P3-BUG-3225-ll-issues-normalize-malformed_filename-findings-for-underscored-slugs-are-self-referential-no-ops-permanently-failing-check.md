---
id: BUG-3225
type: BUG
title: 'll-issues normalize: malformed_filename findings for underscored slugs are
  self-referential no-ops, permanently failing --check'
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-16'
captured_at: '2026-08-16T23:38:23Z'
labels:
- issue-management
- normalize-issues
---

# BUG-3225: ll-issues normalize: malformed_filename findings for underscored slugs are self-referential no-ops, permanently failing --check

## Summary

`ll-issues normalize`'s `malformed_filename` finding is a self-referential no-op for any issue whose slug contains an underscore: `is_normalized()` (`scripts/little_loops/issue_parser.py:135`) requires the slug to match `[a-z0-9-]+`, which rejects underscores, but the "fix" computed for the finding (`_slug_for()` → `slugify()`, `scripts/little_loops/issue_parser.py:1634`) uses `re.sub(r"[^\w\s-]", "", text)`, and `\w` includes underscores — so `slugify()` never strips them. `proposed_path` therefore equals `path` for every affected file, `--auto` correctly detects the no-op and skips applying it (`applied: []`), but the finding is reported every run with no way to clear it.

## Current Behavior

On the little-loops corpus itself, `ll-issues normalize` reports ~29 `malformed_filename` findings, nearly all of them files with a legitimately-formed filename whose slug happens to contain an underscore (e.g. `P2-BUG-3216-ll-logs-telemetry-digest-refresh_corpus-passes-unregistered-quiet-and-omits-required-extract-target-loop-dies-on-first-state.md`). `--auto` is a no-op for these (`applied: 0`), and per the `--check`/`--strict` table in `commands/normalize-issues.md`, `malformed_filename` gates non-strict `--check` — so any project with an underscored slug in its history fails the deterministic FSM gate permanently, with no fix available.

## Expected Behavior

Either `is_normalized()`'s slug pattern should accept underscores (matching what `slugify()` actually produces), or `slugify()`/`_slug_for()` should strip underscores (matching what `is_normalized()` requires) so the two functions agree and `malformed_filename` findings are always resolvable by `--auto`.

## Proposed Solution

Prefer widening `_NORMALIZED_RE` to allow underscores (`[a-z0-9_-]+`) over tightening `slugify()`, since `slugify()` is the general-purpose slug function used elsewhere (title→filename generation) and existing filenames across the corpus already contain underscores by convention (e.g. `history_session_guidemd`, `subagent_runs`) — retroactively stripping them via `--auto` would trigger a large one-time mass-rename with no functional benefit.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Root Cause

Two independent normalizations of "slug" drifted apart:
- `_NORMALIZED_RE`'s slug group: `[a-z0-9-]+` (no underscore)
- `slugify()`'s character filter: `re.sub(r"[^\w\s-]", "", text)` (`\w` = `[a-zA-Z0-9_]`, underscore survives)

## Status

**Open** | Created: 2026-08-16 | Priority: P3
