---
id: ENH-2678
title: Wire go-no-go correction_penalty into scoring + add ll-config get CLI
status: open
priority: P3
type: ENH
discovered_date: 2026-07-18
discovered_by: ll:decide-issue
labels:
- history-db
- config
decision_needed: false
parent: ENH-2677
relates_to:
- ENH-2677
---

# ENH-2678: Wire go-no-go correction_penalty into scoring + add ll-config get CLI

## Summary

Follow-up to ENH-2677, which was closed as substantially already implemented
(schema, `HistoryConfig` dataclass, `BRConfig.history` property, and the
`analysis.evolution.*` → `history.evolution.*` namespace migration were all
already done under prior ENH-1913/1907/1914 work). Two concrete gaps remained
unaddressed and are scoped here.

## Problem

1. **`correction_penalty` is not consumed at runtime.** `GoNoGoConfig.correction_penalty`
   (`scripts/little_loops/config/features.py:989`, default `-0.2`) is
   schema-exposed and round-tripped in `to_dict()`
   (`scripts/little_loops/config/core.py:745`), but `skills/go-no-go/SKILL.md:145`
   only references it as prose (`{{config.history.go_no_go.correction_penalty}}`)
   describing what the judge agent *should* weigh. No Python code path reads
   `.history.go_no_go.correction_penalty` and applies it to a score.

2. **No `ll-config get <key>` CLI.** `scripts/pyproject.toml`'s
   `[project.scripts]` has no `ll-config` entry point and no `main_config`-style
   function exists under `little_loops.cli`. The closest primitive is
   `BRConfig.resolve_variable(var_path: str)`
   (`scripts/little_loops/config/core.py:830-852`), which walks a dot-path
   through `to_dict()` but is currently only consumed internally by
   `scripts/little_loops/skill_expander.py` for template variable substitution
   — not exposed as a standalone CLI a skill could shell out to.

## Additional scope note

`skills/analyze-history/SKILL.md:143,158` still references the stale
`analysis.evolution.*` namespace in prose and should be updated to
`history.evolution.*` as part of this issue (found during ENH-2677's
decision review).

## Proposed Implementation

1. Add a `main_config()` CLI entry point (`ll-config`) wrapping
   `BRConfig.resolve_variable()`, following the `AnalyticsCaptureConfig`/
   `HistoryConfig` "config-or-default, never-raise" contract. Register it in
   `scripts/pyproject.toml`'s `[project.scripts]`.
2. Wire `GoNoGoConfig.correction_penalty` into the go-no-go skill's actual
   scoring path — either via a Python entry point the skill shells out to
   (matching the `history.* is read only in Python, never in markdown skills`
   convention from ENH-2677), or by having the judge agent's prompt read the
   resolved value through the new `ll-config get` CLI.
3. Update `skills/analyze-history/SKILL.md:143,158` from `analysis.evolution.*`
   to `history.evolution.*`.

## Test patterns to follow

- `scripts/tests/test_config.py:3230-3362` — `TestHistoryConfig` /
  `TestGoNoGoConfig` 3-test shape (`test_defaults`, `test_per_key_override`,
  `test_unknown_key_ignored`).
- `scripts/tests/test_config_schema.py:388-522` — schema-declaration tests.

## Status

**Open** | Created: 2026-07-18 | Priority: P3

## Session Log
- `/ll:decide-issue` (via ENH-2677) - 2026-07-18 - created as follow-up to closing ENH-2677
