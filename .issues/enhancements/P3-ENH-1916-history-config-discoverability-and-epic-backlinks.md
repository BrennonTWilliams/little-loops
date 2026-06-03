---
id: ENH-1916
title: history.*/analytics.* config discoverability + EPIC-1707 back-links
type: ENH
priority: P3
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T21:38:03Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [EPIC-1707, ENH-1913, ENH-1905, ENH-1907, ENH-1909, ENH-1911, ENH-1914, ENH-1915]
depends_on:
- ENH-1913
- ENH-1911
- ENH-1909
labels:
  - history-db
  - configurability
  - docs
---

# ENH-1916: Config discoverability + EPIC-1707 back-links

## Summary

Because there is intentionally no `ll-config get` CLI, the new `history.*` /
`analytics.*` keys are only discoverable if they are documented and surfaced by
`/ll:configure`. This issue closes the discoverability gap and fixes
bidirectional EPIC wiring so dependency/progress tooling counts the new work.

## Motivation

A consistency effort that ships tunable keys nobody can find is consistent in
principle only. Two concrete gaps from the EPIC-1707 audit:

1. **Discoverability**: no consolidated reference of every `history.*` /
   `analytics.*` key, its default, and meaning.
2. **Broken EPIC wiring**: EPIC-1707's `relates_to` does **not** include
   ENH-1909, ENH-1911, or the new children — so `ll-deps` / `epic-progress`
   under-count the work. Child→parent links (added in those issues) must be
   matched by parent→child links.

## Implementation Steps

1. **Bidirectional linking**: update EPIC-1707's `relates_to` to include
   ENH-1909, ENH-1911, ENH-1913 (A), ENH-1914 (E), ENH-1915 (F). (The new
   children created by capture already add themselves; this step covers the
   pre-existing 1909/1911 gap and verifies consistency.)
2. **Config reference**: add a single consolidated `## Configuration` table
   (in docs or the epic) listing every `history.*` and `analytics.*` key, its
   default, and meaning.
3. **`/ll:configure` coverage**: confirm the `configure` skill (`skills/configure/`)
   surfaces the new `history.*` keys. If it enumerates sections dynamically from
   `config-schema.json`, ENH-1913 adding the `history` object is sufficient; if
   it hardcodes a section list, add `history` to that list or the keys stay
   undiscoverable through the tool.

## Acceptance Criteria

- `ll-deps` validates the new dependency edges; EPIC-1707 `relates_to` contains
  every new child (1913, 1914, 1915, 1916) plus 1909 and 1911; no cycles.
- A single reference enumerates all `history.*` / `analytics.*` keys.
- `/ll:configure` lists or validates the new `history.*` keys.

## Success Metrics

- **EPIC dependency completeness**: `ll-deps` reports 0 validation errors; EPIC-1707 `relates_to` contains all 6 child IDs (1909, 1911, 1913, 1914, 1915, 1916).
- **Config key coverage**: reference table lists ≥ all keys added by ENH-1913 with default and description for each.
- **Configure discoverability**: running `/ll:configure` interactively surfaces the `history` section without requiring knowledge of key names.

## Scope Boundaries

- **In scope**: updating EPIC-1707 bidirectional links; authoring a consolidated `history.*` / `analytics.*` config reference; verifying `/ll:configure` coverage of the `history` namespace.
- **Out of scope**: defining new config keys (ENH-1913); changing `config-schema.json` structure; altering how `ll-config get` works (intentionally absent per design).

## API/Interface

N/A — No public API changes. This issue modifies issue metadata (frontmatter links) and documentation only.

## Integration Map

### Files to Modify
- `.issues/epics/P2-EPIC-1707-history-db-as-agent-context-layer.md` — add ENH-1909, ENH-1911, ENH-1913, ENH-1914, ENH-1915, ENH-1916 to `relates_to`
- `docs/` or epic body — add consolidated `## Configuration` table for `history.*` / `analytics.*` keys
- `skills/configure/SKILL.md` (or equivalent) — verify `history` namespace is surfaced

### Dependent Files (Callers/Importers)
- `config-schema.json` — source of truth for `history` object keys (must exist; ENH-1913 prerequisite)
- `scripts/little_loops/configure*.py` (if config skill hardcodes sections) — add `history` to section list

### Tests
- `ll-deps` run: validates new EPIC-1707 edges, no cycles
- Manual: `/ll:configure` session confirms `history.*` keys appear

### Documentation
- Config reference table (new) — enumerate every `history.*` / `analytics.*` key with default + description

## Dependencies

- **Depends on**: ENH-1913 (the `history` schema must exist for `/ll:configure`
  to surface it).

## Session Log
- `/ll:verify-issues` - 2026-06-03T22:42:54 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-03T22:04:03 - `882d6aa0-cbf0-47c3-9d9c-32d8d6c6ef92.jsonl`
- `/ll:format-issue` - 2026-06-03T21:44:12 - `39a37568-d7a7-42c9-8508-05b4e238e1ce.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

open
