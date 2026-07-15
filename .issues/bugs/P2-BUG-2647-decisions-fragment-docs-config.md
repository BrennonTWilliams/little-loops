---
id: BUG-2647
title: Update docs and config schema for `.ll/decisions.d/` fragment storage
type: BUG
status: open
priority: P2
parent: BUG-2642
discovered_date: '2026-07-15'
discovered_by: issue-size-review
---

# BUG-2647: Update docs and config schema for `.ll/decisions.d/` fragment storage

## Summary

Decomposed from BUG-2642 (Option A: append-only fragment files). Depends on
BUG-2644 (fragment storage layer). Docs, config schema, and skill/command
bodies that frame `.ll/decisions.yaml` as a single `cat`/`grep`-able file
need updating once storage splits across a legacy file + a fragment
directory; and `decisions.log_path` gains a sibling `.ll/decisions.d/`
directory that may need independent config surfacing.

## Parent Issue

Decomposed from BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on
ARCHITECTURE-NNN id and block EPIC merges.

## Depends On

BUG-2644 must land first — docs should describe the shipped storage layout,
not a speculative one.

## Scope

### Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md` — storage-layout / id-scheme change.
- `docs/development/MERGE-COORDINATOR.md`, `docs/ARCHITECTURE.md`,
  `docs/reference/API.md` — merge path / decisions API changes.
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — documents `check-decisions-yaml.sh`;
  update for the fragment-write path (post BUG-2646).
- `docs/reference/CONFIGURATION.md` — documents the `decisions.log_path`
  config key (default `.ll/decisions.yaml`); note the derived/added
  `.ll/decisions.d/` directory.
- `docs/reference/CLI.md`, `docs/reference/COMMANDS.md` — `ll-issues
  decisions` flag surface / storage-file references.
- `CONTRIBUTING.md` — references the decisions.yaml validation / pre-commit
  flow.
- `CHANGELOG.md` — user-facing storage-format change; add a concrete
  `## [X.Y.Z]` section entry (not `[Unreleased]`).
- `.claude/CLAUDE.md` — the `ll-issues` / `ll-verify-decisions` surface notes.
- Skill/command bodies that frame `.ll/decisions.yaml` as a single
  `cat`/`grep`-able file: `skills/decide-issue/SKILL.md`,
  `skills/capture-issue/SKILL.md`, `skills/go-no-go/SKILL.md`,
  `skills/wire-issue/static-coupling-layer.md`, `commands/verify-issues.md`,
  `commands/ready-issue.md` — scan for singular-file framing that breaks
  until fragments are compacted.
- `.gitignore` (~lines 126–130) — the `!/.ll/` un-ignore already tracks a new
  `.ll/decisions.d/` subdir (no new rule strictly needed), but the
  explanatory comment ("`.ll/decisions.yaml` is a curated, committed
  artifact") goes stale once storage splits; update it.

### Configuration
- `scripts/little_loops/config-schema.json` — `decisions` block
  (~lines 568–585) declares only `log_path` + `auto_generate`; add a
  `fragment_dir` (or equivalent) property only if `.ll/decisions.d/` needs
  independent configuration rather than derived from `log_path`'s parent.
- `scripts/little_loops/config/core.py` (`DecisionsConfig` dataclass) +
  `scripts/little_loops/config/features.py` — mirror any new schema key.

## Tests

- `scripts/tests/test_config_schema.py` — update if the `decisions` schema
  block changes.
- `ll-check-links` — run to confirm no broken links introduced by doc edits.

## Status

**Open** | Created: 2026-07-15 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-15T00:00:00 - `1e8c4ff4-aeb1-4a0e-ae31-59bf29c066dd.jsonl`
