---
id: FEAT-1970
title: eval-export CLI scaffold and selection filters
type: FEAT
priority: P3
status: open
parent: FEAT-1969
relates_to:
- FEAT-1969
- FEAT-1968
- FEAT-1920
- EPIC-1918
labels:
- ll-logs
- eval
- harness
depends_on:
- FEAT-1968
size: Large
confidence_score: 98
outcome_confidence: 92
score_complexity: 25
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 25
---

# FEAT-1970: eval-export CLI scaffold and selection filters

## Summary

Add the `eval-export` subcommand entry to `ll-logs` in `scripts/little_loops/cli/logs.py`.
Wire `_cmd_eval_export` as the handler and implement the selection filter flags
(`--skill`, `--issue`, `--limit`, `--out`, `--json`) so the CLI interface is
complete and parseable before the mapping logic lands in FEAT-1971.

## Use Case

A developer landing on FEAT-1971 to implement the eval-export mapping logic opens
`scripts/little_loops/cli/logs.py`, finds `_cmd_eval_export` already wired and all
five filter flags registered, and can immediately run
`ll-logs eval-export --skill foo --limit 5` to validate flag parsing before writing
any mapping code.

## Parent Issue

Decomposed from FEAT-1969: eval-export implementation — subcommand, mapping, tests, docs

## Prerequisite

**Blocked by FEAT-1968** — do not start until FEAT-1968 is `done` and its decisions
are recorded in `.ll/decisions.yaml`.

## Motivation

Separates the CLI surface from the mapping logic (FEAT-1971) so each can be reviewed,
tested, and merged independently. Having the parser scaffold in place first gives
FEAT-1971's author immediate flag-validation feedback without touching parser wiring,
and keeps the subcommand interface frozen as a contract between the two issues.

## Current Behavior

`ll-logs` has no `eval-export` subcommand.

## Expected Behavior

`ll-logs eval-export --help` shows the full flag reference. The command parses
all flags without error; the handler stub may emit a "not yet implemented" message
or no output until FEAT-1971 fills in the mapping body.

## Proposed Solution

### Step 1 — Add subcommand scaffold

In `scripts/little_loops/cli/logs.py`, add `eval-export` to `_build_parser` following
the same pattern as `_cmd_extract`, `_cmd_discover`, `_cmd_tail`. Wire `_cmd_eval_export`
as the handler with a stub body.

### Step 2 — Implement selection filters

Add arguments to the `eval-export` subparser:
- `--skill NAME` — filter by skill name
- `--issue ID` — filter by issue ID in session context
- `--limit N` — cap output records (0 = unlimited)
- `--out PATH` — write to file; default stdout
- `--json` — JSON output vs YAML (default YAML)

## API/Interface

```
ll-logs eval-export [--skill NAME] [--issue ID] [--limit N] [--out PATH] [--json]
```

| Flag | Type | Default | Description |
|------|------|---------|-------------|
| `--skill NAME` | str | None | Filter by skill name |
| `--issue ID` | str | None | Filter by issue ID in session context |
| `--limit N` | int | 0 | Cap output records (0 = unlimited) |
| `--out PATH` | str | stdout | Write output to file |
| `--json` | flag | YAML | JSON output instead of YAML |

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `eval-export` parser entry and `_cmd_eval_export` stub

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/logs.py` — `_build_parser` dispatches to `_cmd_eval_export` via subparser `set_defaults(func=...)`
- FEAT-1971 will fill in the body of `_cmd_eval_export`; no external callers at this stage

### Similar Patterns
- `_cmd_extract`, `_cmd_discover`, `_cmd_tail` in `cli/logs.py` — follow same subcommand handler shape

### Tests
- `scripts/tests/test_ll_logs.py` — add test cases for `eval-export --help` and flag parsing

### Documentation
- N/A — CLI help text is self-documenting via argparse

### Configuration
- N/A

## Implementation Steps

1. Add `eval-export` subparser in `_build_parser` with all five filter flags.
2. Add stub `_cmd_eval_export(args)` handler that prints a "not yet implemented" message.
3. Verify `ll-logs eval-export --help` shows flag reference without error.

## Acceptance Criteria

- `ll-logs eval-export --help` shows all five flags with descriptions.
- `ll-logs eval-export --skill foo` runs without crashing (stub output or no-op is acceptable).
- No regressions to existing `ll-logs` subcommands.

## Impact

- **Priority**: P3
- **Effort**: Small — parser wiring only, no business logic
- **Risk**: Very Low — purely additive; no changes to existing subcommand behavior
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 86/100 → HIGH CONFIDENCE

### Concerns
- **FEAT-1968 is open**: The issue explicitly states "do not start until FEAT-1968 is done and its decisions are recorded in `.ll/decisions.yaml`." FEAT-1968 status is `open`. Practically, the 5 CLI flags are already fully enumerated in FEAT-1970 and don't depend on FEAT-1968's design decisions, so the implementation itself is unblocked — but the stated prerequisite is not yet cleared.

## Session Log
- `/ll:format-issue` - 2026-06-06T03:18:03 - `28c795c0-5fbc-487e-9101-6182dd58a8a0.jsonl`
- `/ll:issue-size-review` - 2026-06-05T21:48:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bad2c36-ed0d-4b74-bdd5-ccfd01530ea6.jsonl`
- `/ll:confidence-check` - 2026-06-05T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f4f2a58f-fea9-4b2e-bd0f-cce4ab995bec.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/63c68e86-a5ce-425d-a9d8-0f5ffadec88b.jsonl`
