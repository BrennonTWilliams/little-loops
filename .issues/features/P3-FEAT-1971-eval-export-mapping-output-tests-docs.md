---
id: FEAT-1971
title: eval-export invocation mapping, output, tests, and docs
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
- FEAT-1970
size: Very Large
confidence_score: 70
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-1971: eval-export invocation mapping, output, tests, and docs

## Summary

Complete the `ll-logs eval-export` implementation using the fixture schema, outcome
definition, and input-context spec resolved in FEAT-1968. Fills in the
`_cmd_eval_export` stub from FEAT-1970 with: invocation→fixture mapping logic,
redaction, output serialization (YAML/JSON), round-trip tests, and API.md docs.

## Parent Issue

Decomposed from FEAT-1969: eval-export implementation — subcommand, mapping, tests, docs

## Prerequisites

**Blocked by FEAT-1968** — fixture schema, outcome definition, and redaction approach
must be recorded in `.ll/decisions.yaml` before the mapping logic can be finalized.

**Blocked by FEAT-1970** — the `_cmd_eval_export` stub and parser must exist before
the body can be filled in.

## Current Behavior

After FEAT-1970 merges, `ll-logs eval-export` parses flags but produces no output.

## Expected Behavior

`ll-logs eval-export [--skill NAME] [--issue ID] [--limit N] [--out PATH] [--json]`
selects log records where the target skill was invoked, captures the input context and
observed outcome per the spec in FEAT-1968, and writes them as `ll-harness`-compatible
fixture records. A maintainer can run the command, get a fixture file, and pass it
directly to `ll-harness` without manual editing.

## Proposed Solution

### Step 1 — Read FEAT-1968 decisions

Read `.ll/decisions.yaml` and confirm the fixture schema, outcome definition,
input-context spec, and redaction rules from FEAT-1968 before writing any code.

### Step 2 — Implement invocation → fixture mapping

Apply the input-context extraction rule and outcome definition from FEAT-1968 decisions.
For each qualifying invocation record: build a fixture dict with the fields confirmed
in FEAT-1968, apply redaction, and append to output. Skip records with no extractable
outcome (log the skipped count at the end).

Use the ENH-1919 invocation extractor from `cli/logs.py` as the data source.

### Step 3 — Write output

Serialize to `--out` path (or stdout) in the format `ll-harness` expects (YAML default,
JSON with `--json`). Confirm the output loads cleanly under `ll-harness` before writing
tests.

### Step 4 — Tests

In `scripts/tests/test_ll_logs.py`, add:
- Unit test: a synthetic invocation record → expected fixture dict (mapping logic)
- Round-trip test: invoke `eval-export` on a minimal fixture corpus, load the output
  under `ll-harness` (dry run / schema validation), assert no errors

### Step 5 — Documentation

In `docs/reference/API.md`, update the `ll-logs` section: add `eval-export` subcommand
description, flag reference table, example output fixture, and a note about the
prerequisite ENH-1919 extractor.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/logs.py` — fill in `_cmd_eval_export` body with mapping, redaction, output
- `scripts/tests/test_ll_logs.py` — add unit and round-trip tests
- `docs/reference/API.md` — add eval-export section under ll-logs

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/harness.py` — fixture schema source of truth (read only)
- ENH-1919 invocation extractor in `cli/logs.py` — primary data source

## Implementation Steps

1. Read FEAT-1968 decisions from `.ll/decisions.yaml`; confirm fixture schema, outcome definition, input-context spec, redaction rules.
2. Implement mapping + redaction body in `_cmd_eval_export`.
3. Apply redaction per FEAT-1968 spec; skip no-outcome records with logged count.
4. Serialize output (YAML/JSON) to `--out` or stdout.
5. Add unit + round-trip tests in `test_ll_logs.py`.
6. Update `docs/reference/API.md` with eval-export documentation.

## Edge Cases

- Sessions with no extractable outcome → skipped; print count at end.
- Redaction: apply documented pattern list from FEAT-1968; skip record if unredactable sensitive content is detected.
- `--out` path directory does not exist → create parent dirs or fail with a clear message.
- `--limit 0` → treat as unlimited.

## Acceptance Criteria

- `ll-logs eval-export --skill refine-issue --out /tmp/evals.yaml` produces a valid fixture file.
- The fixture file loads under `ll-harness` without manual editing.
- `--skill` / `--issue` filters select the expected records.
- Sessions with no extractable outcome are skipped with a logged count.
- Unit + round-trip tests pass under `python -m pytest scripts/tests/test_ll_logs.py`.
- `docs/reference/API.md` documents the new subcommand.

## Impact

- **Priority**: P3 — quality-of-life improvement for eval workflows
- **Effort**: Medium — mapping logic, redaction, output, tests, docs
- **Risk**: Low — fills in stub handler; no changes to existing ll-logs subcommands or harness behavior
- **Breaking Change**: No

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-05_

**Readiness Score**: 70/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 71/100 → MODERATE

### Concerns
- **Criterion 5 = 0**: Both explicit prerequisites are still open. FEAT-1968 has not recorded fixture schema, outcome definition, input-context spec, or redaction rules to `.ll/decisions.yaml`. FEAT-1970 has not created the `_cmd_eval_export` stub in `logs.py`. Step 1 of the implementation plan cannot execute until both are done.
- **Ambiguity risk (C = 10/25)**: The core artifact of this issue — the fixture dict structure and redaction pattern — is unknown until FEAT-1968 resolves. Implementing the mapping body before FEAT-1968 decisions are finalized risks rework.

### Outcome Risk Factors
- **Upstream design unresolved**: The fixture schema, outcome definition, and redaction rules are all pending FEAT-1968. The mapping body cannot be finalized without these — expect re-work if FEAT-1968 decisions diverge from assumptions.
- **Scaffold not yet present**: FEAT-1970's `_cmd_eval_export` stub has not been implemented. FEAT-1971's integration map targets "fill in" the body, which requires the scaffold to exist first.

## Session Log
- `/ll:issue-size-review` - 2026-06-05T21:48:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5bad2c36-ed0d-4b74-bdd5-ccfd01530ea6.jsonl`
- `/ll:confidence-check` - 2026-06-05T22:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
