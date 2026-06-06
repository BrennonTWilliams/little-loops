---
id: FEAT-1969
title: 'eval-export implementation: subcommand, mapping, tests, docs'
type: FEAT
priority: P3
status: done
parent: FEAT-1920
relates_to:
- FEAT-1920
- FEAT-1968
- EPIC-1918
labels:
- ll-logs
- eval
- harness
depends_on:
- FEAT-1968
confidence_score: 68
outcome_confidence: 67
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 10
score_change_surface: 20
size: Very Large
---

# FEAT-1969: eval-export implementation — subcommand, mapping, tests, docs

## Summary

Implement `ll-logs eval-export` in `cli/logs.py` using the fixture schema, outcome
definition, and input-context spec resolved in FEAT-1968. Includes the CLI handler,
selection filters (`--skill`, `--issue`, `--limit`, `--out`, `--json`), invocation→fixture
mapping logic, round-trip tests, and API.md documentation.

## Parent Issue

Decomposed from FEAT-1920: ll-logs eval-export — sessions to ll-harness fixtures

## Prerequisite

**Blocked by FEAT-1968** — do not start until FEAT-1968 is `done` and its decisions
are recorded in `.ll/decisions.yaml`. The fixture schema, outcome definition, and
redaction approach from FEAT-1968 are required inputs for this issue.

## Current Behavior

`ll-logs` has no `eval-export` subcommand. Eval harnesses are seeded from issue text
or hand-authored prompts only.

## Expected Behavior

`ll-logs eval-export [--skill NAME] [--issue ID] [--limit N] [--out PATH] [--json]`
selects log records where the target skill was invoked, captures the input context and
observed outcome per the spec in FEAT-1968, and writes them as `ll-harness`-compatible
fixture records. A maintainer can run the command, get a fixture file, and pass it
directly to `ll-harness` without manual editing.

## Use Case

A skill maintainer wants to build a regression harness for the `refine-issue` skill. They run `ll-logs eval-export --skill refine-issue --out /tmp/evals.yaml` to extract recent log records where that skill was invoked. The command produces a `ll-harness`-compatible fixture file they can pass directly to `ll-harness` for evaluation — without manually authoring test prompts or editing the fixture file.

## Proposed Solution

### Step 1 — Add subcommand scaffold

In `scripts/little_loops/cli/logs.py`, add `eval-export` to `_build_parser` following
the same pattern as `_cmd_extract`, `_cmd_discover`, `_cmd_tail`. Wire `_cmd_eval_export`
as the handler.

### Step 2 — Implement selection filters

Support: `--skill NAME` (filter by skill name), `--issue ID` (filter by issue ID in
session context), `--limit N` (cap output records), `--out PATH` (write to file; default
stdout), `--json` (JSON output vs YAML).

Use the ENH-1919 invocation extractor from `cli/logs.py` as the data source.

### Step 3 — Implement invocation → fixture mapping

Apply the input-context extraction rule and outcome definition from FEAT-1968 decisions.
For each qualifying invocation record: build a fixture dict with the fields confirmed
in FEAT-1968, apply redaction, and append to output. Skip records with no extractable
outcome (log the skipped count at the end).

### Step 4 — Write output

Serialize to `--out` path (or stdout) in the format `ll-harness` expects (YAML default,
JSON with `--json`). Confirm the output loads cleanly under `ll-harness` before writing
tests.

### Step 5 — Tests

In `scripts/tests/test_ll_logs.py`, add:
- Unit test: a synthetic invocation record → expected fixture dict (mapping logic)
- Round-trip test: invoke `eval-export` on a minimal fixture corpus, load the output
  under `ll-harness` (dry run / schema validation), assert no errors

### Step 6 — Documentation

In `docs/reference/API.md`, update the `ll-logs` section: add `eval-export` subcommand
description, flag reference table, example output fixture, and a note about the
prerequisite ENH-1919 extractor.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `eval-export` subcommand handler and parser entry
- `scripts/tests/test_ll_logs.py` — add unit and round-trip tests
- `docs/reference/API.md` — add eval-export section under ll-logs

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py` — fixture schema source of truth (read only)
- ENH-1919 invocation extractor in `cli/logs.py` — primary data source

### Similar Patterns
- `_cmd_extract`, `_cmd_discover`, `_cmd_tail` in `cli/logs.py` — follow same subcommand handler shape

## Implementation Steps

1. Read FEAT-1968 decisions from `.ll/decisions.yaml`; confirm fixture schema, outcome definition, input-context spec, redaction rules.
2. Add `eval-export` to `_build_parser` in `cli/logs.py`.
3. Implement `_cmd_eval_export` with selection filters and invocation→fixture mapping.
4. Apply redaction per FEAT-1968 spec; skip no-outcome records with logged count.
5. Serialize output (YAML/JSON) to `--out` or stdout.
6. Add unit + round-trip tests in `test_ll_logs.py`.
7. Update `docs/reference/API.md` with eval-export documentation.

## Acceptance Criteria

- `ll-logs eval-export --skill refine-issue --out /tmp/evals.yaml` produces a valid fixture file.
- The fixture file loads under `ll-harness` without manual editing.
- `--skill` / `--issue` filters select the expected records.
- Sessions with no extractable outcome are skipped with a logged count.
- Records with unredactable sensitive content are skipped (not written to output).
- `--out` path with non-existent parent directories: parent dirs are created or a clear error message is shown.
- `--limit 0` is treated as unlimited.
- Unit + round-trip tests pass under `python -m pytest scripts/tests/test_ll_logs.py`.
- `docs/reference/API.md` documents the new subcommand.

## Impact

- **Priority**: P3 — quality-of-life improvement for eval workflows
- **Effort**: Medium — new subcommand with filtering, mapping, redaction, tests, docs
- **Risk**: Low — purely additive; no changes to existing ll-logs subcommands or harness behavior
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 68/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 67/100 → LOW

### Concerns
- FEAT-1968 is `Open` — the hard prerequisite for this issue is unmet; issue explicitly states "do not start until FEAT-1968 is `done`"
- No decisions recorded in `.ll/decisions.yaml` from FEAT-1968; fixture schema, outcome definition, and redaction policy are required inputs for Step 3

### Gaps to Address
- Implement and close FEAT-1968 first; record its decisions in `.ll/decisions.yaml`
- Step 3 implementation plan (invocation→fixture mapping) cannot be finalized until FEAT-1968 decisions are available

### Outcome Risk Factors
- Core mapping logic is underspecified — fixture schema and outcome extraction rule are delegated to an incomplete prerequisite; rework risk if FEAT-1968 decisions differ from implicit assumptions in this issue
- Ambiguity in redaction policy (deferred to FEAT-1968) means implementation may need significant revision once that spec is complete

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-06-05
- **Reason**: Issue too large for single session (size score 11/11)

### Decomposed Into
- FEAT-1970: eval-export CLI scaffold and selection filters
- FEAT-1971: eval-export invocation mapping, output, tests, and docs

## Session Log
- `/ll:format-issue` - 2026-06-06T03:18:10 - `28c795c0-5fbc-487e-9101-6182dd58a8a0.jsonl`
- `/ll:issue-size-review` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8be904b6-a889-49bc-bc5f-f854cacc72bb.jsonl`
- `/ll:confidence-check` - 2026-06-05T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8be904b6-a889-49bc-bc5f-f854cacc72bb.jsonl`
- `/ll:issue-size-review` - 2026-06-05T21:48:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bad2c36-ed0d-4b74-bdd5-ccfd01530ea6.jsonl`
