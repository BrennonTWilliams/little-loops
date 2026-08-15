---
id: BUG-3190
type: BUG
title: ARCHITECTURE.md/CONTRIBUTING.md directory trees list stale/partial skills subtree
  and nonexistent paths
priority: P4
status: open
testable: false
discovered_by: ll-issues-create
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:46Z'
---

# BUG-3190: ARCHITECTURE.md/CONTRIBUTING.md directory trees list stale/partial skills subtree and nonexistent paths

## Summary

`/ll:audit-docs` (readme scope, 2026-08-15) found `docs/ARCHITECTURE.md`'s Directory Structure tree still enumerates only a small fraction of the repo's skills, even after the raw skill-count callouts were fixed directly in this audit (69, matching `skills/*/SKILL.md`).

## Current Behavior

- `docs/ARCHITECTURE.md:115-183` (Directory Structure tree, skills subtree) lists only ~26 skill entries and omits most `ll-*`-prefixed companion/mirror skills (skill-companion mirroring, see commit e1737bb2 and CLAUDE.md) plus several standalone skills missing entirely: `rename-loop`, `simplify-loop`, `compact-session`/`ll-compact-session`, `review-epic`, `spike`, `decide-issue`, `wire-issue`, `link-epics`, `scope-epic`, `explore-api`, `verify-issue-loop`.
- `CONTRIBUTING.md:178-214`'s illustrative Project Structure skills subtree has the same gap — lists ~34 of 69 actual entries.
- `CONTRIBUTING.md:164,242-244`: the tree lists a root-level `config-schema.json` file that does not exist — the canonical location is `scripts/little_loops/config-schema.json`. This is the only nonexistent-path finding in this issue.
  - **Verified 2026-08-15, do not "fix" these**: `docs/claude-code/`, `docs/codex/`, and `docs/demo/` all exist and their tree entries are correct. `docs/claude-code/` is git-tracked (`hooks-reference.md`, `plugins-reference.md`, `cli-reference.md`, …); `docs/demo/` exists on disk but is gitignored (`.gitignore:76`), so a `git ls-files`-based check will report it missing. An earlier draft of this issue claimed `docs/claude-code/` and `docs/demo/` were nonexistent; that claim was wrong and removing those entries would be a regression.
- `docs/ARCHITECTURE.md:64`: same stale root-level `config-schema.json` tree entry (parenthetical correctly notes the canonical location, but the tree entry itself implies a root copy exists).

## Expected Behavior

Directory-structure illustrations in both files either enumerate the current skill set accurately or use a representative `...` truncation instead of a stale fixed list, and drop the nonexistent root-level `config-schema.json` tree entry. `docs/claude-code/`, `docs/codex/`, and `docs/demo/` stay as-is.

Prefer the truncation option for the skills subtree: the catalog is 69 entries and growing, so any enumerated list re-staleness is a matter of time. A short representative sample that explicitly shows the `ll-*` bridge-skill pattern, followed by `...`, conveys the shape without incurring maintenance.

## Motivation

A tree that silently omits ~60% of a directory's contents actively misleads a reader trying to understand the skill catalog's shape (e.g. the ll-* bridge-skill pattern is invisible from the tree alone).

## Impact

- **Priority**: P4 — illustrative examples, not load-bearing reference material (the numeric skill counts are already fixed).
- **Effort**: Small — either trim to a representative sample with explicit truncation, or regenerate the full list.
- **Risk**: None — doc-only change.


## Status

**Open** | Created: 2026-08-15 | Priority: P4
