---
id: FEAT-1920
title: "ll-logs eval-export: sessions to ll-harness fixtures"
type: FEAT
priority: P3
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918]
labels: [captured, ll-logs, eval, harness]
---

# FEAT-1920: ll-logs eval-export — sessions to ll-harness fixtures

## Summary

Add `ll-logs eval-export` to harvest real `(issue → skill invocation → outcome)`
tuples from the log corpus and emit them as `ll-harness` / `create-eval-from-issues`
fixtures. Real session inputs become golden eval inputs instead of synthetic prompts.

## Current Behavior

Eval harnesses (`ll-harness`, `/ll:create-eval-from-issues`) are seeded from issue
text or hand-authored prompts. The richest possible eval inputs — prompts that
actually drove a skill in a real session — sit unused in the logs.

## Expected Behavior

`ll-logs eval-export [--skill NAME] [--issue ID] [--limit N] [--out PATH] [--json]`
selects log records where a target skill was invoked, captures the surrounding
input context and observed outcome, and writes them in the fixture format
`ll-harness` consumes. Optionally filter by skill or issue.

## Motivation

Closes the loop on the CLAUDE.md mandate that meta-loops "measure externally":
real transcripts are the external ground truth. Also lets prompt changes be
regression-tested by replaying historical inputs through `ll-harness`.

## Proposed Solution

Add `eval-export` to `cli/logs.py`, reusing the shared ll-invocation extractor
(ENH-1919). Map each captured invocation to a fixture record; emit a file
`ll-harness` / `create-eval-from-issues` can load directly.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `eval-export` subcommand handler and `_build_parser` entry

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py` — defines the fixture schema that `eval-export` must emit
- ENH-1919 shared invocation extractor (in `cli/logs.py` or adjacent module) — primary data source
- `skills/create-eval-from-issues/` — consumes emitted fixture files

### Similar Patterns
- `_cmd_extract`, `_cmd_discover`, `_cmd_tail` in `scripts/little_loops/cli/logs.py` — follow same subcommand handler shape

### Tests
- `scripts/tests/test_ll_logs.py` — add round-trip test: emit fixtures via `eval-export`, load under `ll-harness`

### Documentation
- `docs/reference/API.md` — update `ll-logs` section with `eval-export` subcommand and flags

### Configuration
- N/A

## Implementation Steps

1. Confirm the fixture schema `ll-harness` expects (read `cli/harness.py`).
2. Add `eval-export` subcommand + selection filters in `cli/logs.py`.
3. Map invocation+context+outcome → fixture record; write to `--out`.
4. Tests over a fixture corpus; round-trip through `ll-harness`.

## Use Case

A maintainer edits the `refine-issue` prompt and wants confidence it didn't
regress. They run `ll-logs eval-export --skill refine-issue --out evals/refine.yaml`,
then replay through `ll-harness` to compare behavior before/after.

## Acceptance Criteria

- Exported fixtures load and run under `ll-harness` without manual editing.
- `--skill` / `--issue` filters select the expected records.

## API/Interface

`ll-logs eval-export` — new subcommand emitting ll-harness-compatible fixtures.

## Edge Cases

- Sessions with no extractable outcome → skipped (logged count).
- Redaction of any sensitive prompt content before writing fixtures.

## Impact

- **Priority**: P3 — quality-of-life improvement for eval workflows; not on the critical path
- **Effort**: Medium — new subcommand with filtering logic, fixture mapping, and round-trip tests; reuses ENH-1919 extractor
- **Risk**: Low — purely additive; no changes to existing `ll-logs` subcommands or harness behavior
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md` (ll-harness, ll-logs)

## Labels

captured, ll-logs, eval, harness

## Status

open

## Session Log
- `/ll:format-issue` - 2026-06-04T03:08:23 - `15dd654f-1592-42bb-8073-e029440f9e86.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
