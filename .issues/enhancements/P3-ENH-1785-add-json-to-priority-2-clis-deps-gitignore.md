---
id: ENH-1785
title: Add --json to Priority 2 CLIs (deps validate, gitignore)
type: enh
status: done
priority: P3
parent: ENH-1780
completed_at: '2026-05-28'
labels:
- cli
- agent-composability
---

## Resolution

Added `--json`/`-j` flag support via `add_json_arg()` to two CLIs:
- `ll-deps validate --json` — serializes `ValidationResult` fields (broken_refs, missing_backlinks, cycles, stale_completed_refs, broken_depends_on_refs, broken_relates_to_refs)
- `ll-gitignore --json` — serializes `GitignoreSuggestion` fields (has_suggestions, summary, suggestions with pattern/category/description/files_matched/priority)

No conflict with `ll-deps analyze --format json` (verified by test). 8 new tests added across `test_dependency_mapper.py` and `test_gitignore_cmd.py`.

---

# ENH-1785: Add --json to Priority 2 CLIs (deps validate, gitignore)

## Summary

Add `--json` flag support to `ll-deps validate` and `ll-gitignore`. Each follows the mechanical pattern: add `--json` to the argparse subparser using the shared `add_json_arg()` helper from ENH-1783, branch on `args.json` to call `print_json()`, and add JSON output tests.

## Parent Issue

Decomposed from ENH-1780: Add --json flag consistently across all ll-* CLIs

## Current Behavior

`ll-deps validate` and `ll-gitignore` output human-readable text only. No `--json` flag or structured output format is currently supported, which forces automation pipelines to parse human-readable text.

## Expected Behavior

Both CLIs support `--json` / `-j` flags that produce structured JSON output on stdout, following the same pattern used by 15+ other `ll-*` subcommands (using `add_json_arg()` from ENH-1783 and `print_json()`). Default text output is unchanged; JSON is opt-in.

## Motivation

This enhancement would:
- Improve agent composability by enabling structured output consumption in automation pipelines (ll-auto, ll-parallel, ll-sprint)
- Align these CLIs with the 15+ other `ll-*` subcommands that already support `--json`
- Reduce parsing fragility — agents currently parse human-readable output, which is brittle across format changes

## Proposed Solution

Follow the existing `--json` pattern (consistent across 15+ subcommands):
- Argument: `parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")` (via `add_json_arg()`)
- Branching: `if getattr(args, "json", False): print_json(data); return 0`
- Output: `print_json()` at `scripts/little_loops/cli/output.py:114`

### ll-deps validate
Output validation results as structured JSON. Follow pattern from `ll-verify-docs` in `docs.py:87-94` (format-function dispatch). Verify `--json` on `validate` does not conflict with `--format json` on `analyze`.

### ll-gitignore
Output suggestion data as structured JSON.

## Scope Boundaries

- **In scope**: Adding `--json` flag to `ll-deps validate` and `ll-gitignore` (dry-run and apply output)
- **Out of scope**: Other `ll-deps` subcommands (`analyze` already has `--format json`), other CLIs not in priority 2, changing default output format

## Pre-requisite

- ENH-1783: `add_json_arg()` shared helper must exist before starting this work.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/deps.py` — validate subcommand (line 141)
- `scripts/little_loops/cli/gitignore.py` — dry-run/apply output

### Dependent Files (Callers/Importers)
- N/A — these are CLI entry points; no internal callers beyond argcomplete registration in pyproject.toml

### Similar Patterns
- `scripts/little_loops/cli/docs.py:87-94` — format-function dispatch with `--json`
- 15+ other `ll-*` subcommands using `add_json_arg()` + `print_json()` pattern

### Tests
- `scripts/tests/test_dependency_mapper.py` — JSON output tests for `validate --json` in `TestMainCLI` (line 1299). Verify no conflict with `analyze --format json`. Existing test at line 1499 (`test_validate_json_output_includes_new_fields`) uses `--format json` on `analyze` — verify no interaction.
- `scripts/tests/test_gitignore_cmd.py` — JSON output tests for dry-run/apply. Follow Pattern B (capsys + `json.loads()`).

Verification checklist per CLI:
- `--json` flag appears in `--help` output
- Short flag `-j` works equivalently
- Valid JSON output (parse with `json.loads()`)
- No ANSI escape codes in JSON output
- Exit code is 0

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `--json` to `ll-deps validate` in `deps.py:141` — output validation results as structured JSON.
2. Add `--json` to `ll-gitignore` in `gitignore.py` — output suggestion data as JSON.
3. Add JSON output tests to `test_dependency_mapper.py` — test `validate --json`. Verify no conflict with `analyze --format json`.
4. Add JSON output tests to `test_gitignore_cmd.py` — test dry-run and apply with `--json`.
5. Verify each CLI: `--json` in help, `-j` short flag, parseable JSON, no ANSI codes, exit 0.

## Success Metrics

- All 5 verification checklist items pass for both CLIs (--json in help, -j short flag, valid JSON, no ANSI codes, exit 0)
- Existing tests continue to pass with no regressions

## API/Interface

N/A — No new public API changes. Adds `--json` / `-j` CLI flags to existing subcommands only.

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — 2 CLIs, each mechanical
- **Risk**: Low — additive, opt-in, default output unchanged
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-05-29T04:48:12 - `0b5cfe53-7b19-494a-9182-134b022182d9.jsonl`
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`
