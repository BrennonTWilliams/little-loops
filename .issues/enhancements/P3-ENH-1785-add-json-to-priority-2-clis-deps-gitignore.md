---
id: ENH-1785
title: Add --json to Priority 2 CLIs (deps validate, gitignore)
type: enh
status: open
priority: P3
parent: ENH-1780
labels:
- cli
- agent-composability
---

# ENH-1785: Add --json to Priority 2 CLIs (deps validate, gitignore)

## Summary

Add `--json` flag support to `ll-deps validate` and `ll-gitignore`. Each follows the mechanical pattern: add `--json` to the argparse subparser using the shared `add_json_arg()` helper from ENH-1783, branch on `args.json` to call `print_json()`, and add JSON output tests.

## Parent Issue

Decomposed from ENH-1780: Add --json flag consistently across all ll-* CLIs

## Proposed Solution

Follow the existing `--json` pattern (consistent across 15+ subcommands):
- Argument: `parser.add_argument("-j", "--json", action="store_true", help="Output as JSON")` (via `add_json_arg()`)
- Branching: `if getattr(args, "json", False): print_json(data); return 0`
- Output: `print_json()` at `scripts/little_loops/cli/output.py:114`

### ll-deps validate
Output validation results as structured JSON. Follow pattern from `ll-verify-docs` in `docs.py:87-94` (format-function dispatch). Verify `--json` on `validate` does not conflict with `--format json` on `analyze`.

### ll-gitignore
Output suggestion data as structured JSON.

## Files to Modify

- `scripts/little_loops/cli/deps.py` — validate subcommand (line 141)
- `scripts/little_loops/cli/gitignore.py` — dry-run/apply output

## Pre-requisite

- ENH-1783: `add_json_arg()` shared helper must exist before starting this work.

## Tests

Per CLI verification checklist:
- `--json` flag appears in `--help` output
- Short flag `-j` works equivalently
- Valid JSON output (parse with `json.loads()`)
- No ANSI escape codes in JSON output
- Exit code is 0

Test files to update:
- `scripts/tests/test_dependency_mapper.py` — JSON output tests for `validate --json` in `TestMainCLI` (line 1299). Verify no conflict with `analyze --format json`. Existing test at line 1499 (`test_validate_json_output_includes_new_fields`) uses `--format json` on `analyze` — verify no interaction.
- `scripts/tests/test_gitignore_cmd.py` — JSON output tests for dry-run/apply. Follow Pattern B (capsys + `json.loads()`).

## Implementation Steps

1. Add `--json` to `ll-deps validate` in `deps.py:141` — output validation results as structured JSON.
2. Add `--json` to `ll-gitignore` in `gitignore.py` — output suggestion data as JSON.
3. Add JSON output tests to `test_dependency_mapper.py` — test `validate --json`. Verify no conflict with `analyze --format json`.
4. Add JSON output tests to `test_gitignore_cmd.py` — test dry-run and apply with `--json`.
5. Verify each CLI: `--json` in help, `-j` short flag, parseable JSON, no ANSI codes, exit 0.

## Impact

- **Priority**: P3
- **Effort**: Small-Medium — 2 CLIs, each mechanical
- **Risk**: Low — additive, opt-in, default output unchanged
- **Breaking Change**: No

## Session Log
- `/ll:issue-size-review` - 2026-05-28T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dc1fcf00-8ef7-4a3a-94b4-7099b5095eec.jsonl`
