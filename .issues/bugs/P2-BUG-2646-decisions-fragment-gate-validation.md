---
id: BUG-2646
title: Extend decisions validation gates (PreToolUse, pre-commit,
  `ll-verify-decisions`) to the fragment path
type: BUG
status: open
priority: P2
parent: BUG-2642
discovered_date: '2026-07-15'
discovered_by: issue-size-review
---

# BUG-2646: Extend decisions validation gates to the fragment path

## Summary

Decomposed from BUG-2642 (Option A: append-only fragment files). Depends on
BUG-2644 (fragment storage layer) landing first. The three-tier decisions
validation gate (PreToolUse hook, pre-commit hook, `ll-verify-decisions`) is
keyed to the literal `.ll/decisions.yaml` path and a narrower exception
catch; once fragment writes exist under `.ll/decisions.d/`, they bypass
validation entirely unless each gate learns the new path and error type.
This is a genuinely separate subsystem (hooks + pre-commit config, not the
core read/write layer) and is independently testable, so it is split out
rather than folded into BUG-2644.

## Parent Issue

Decomposed from BUG-2642: Concurrent `.ll/decisions.yaml` appends collide on
ARCHITECTURE-NNN id and block EPIC merges.

## Depends On

BUG-2644 must land first — these gates validate the fragment format that
BUG-2644 introduces.

## Scope

- `scripts/little_loops/cli/verify_decisions.py` — `_run()` (~line 60)
  currently catches only `(yaml.YAMLError, KeyError, ValueError)`; a
  directory-union reader over `.ll/decisions.d/*.json` must either normalize
  `json.JSONDecodeError` into a caught type or this except clause must
  broaden, or the three-tier gate silently stops catching malformed
  fragments. Also resolves `_DEFAULT_LOG_PATH` (~line 35) singularly — must
  validate the whole fragment directory.
- `hooks/scripts/check-decisions-yaml.sh` — path-match guard (~lines 80–89)
  only fires on Write/Edit to `.ll/decisions.yaml` exactly; add a second path
  pattern for `.ll/decisions.d/*.json` and a Write-only (no Edit diff)
  staging path for write-once fragments.
- `hooks/hooks.json` (~lines 57–61) — registers `check-decisions-yaml.sh` as
  the PreToolUse Write|Edit hook; widen the registration matcher to match the
  new path pattern.
- `.pre-commit-config.yaml` — `ll-verify-decisions` hook entry
  `files: ^\.ll/decisions\.yaml$` (~lines 8–12) won't match new fragment
  files; add `^\.ll/decisions\.d/.*\.json$` (or make the validator
  directory-aware) so fragments are validated pre-commit.

## Tests

- `scripts/tests/test_decisions_yaml_gate.py`,
  `scripts/tests/test_decisions_yaml_pre_commit_gate.py`,
  `scripts/tests/test_check_decisions_yaml_hook.py` — each currently keyed to
  the single-file `.ll/decisions.yaml` assumption; add cases for
  `.ll/decisions.d/*.json` writes (valid fragment passes, malformed fragment
  blocks).
- `scripts/tests/test_verify_decisions.py` — add a malformed-fragment case
  exercising the broadened/normalized exception handling in `_run()`.

## Status

**Open** | Created: 2026-07-15 | Priority: P2

## Session Log
- `/ll:issue-size-review` - 2026-07-15T00:00:00 - `1e8c4ff4-aeb1-4a0e-ae31-59bf29c066dd.jsonl`
