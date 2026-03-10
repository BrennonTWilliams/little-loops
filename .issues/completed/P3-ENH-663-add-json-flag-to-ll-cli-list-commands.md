---
discovered_date: 2026-03-09
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# ENH-663: Add `--json` flag to `ll-` CLI list commands

## Current Behavior

`ll-issues list`, `ll-loop list`, and `ll-sprint list` all output human-readable table or text format only. There is no structured output option, so FSM loops and automation scripts must scrape/parse the human-readable output — which breaks on formatting changes, whitespace tweaks, or column additions.

## Expected Behavior

Each `list` subcommand accepts a `--json` flag. When set, output is a JSON array of objects to stdout (exit 0). Without the flag, existing human-readable table output is unchanged. This provides a stable, structured interface for programmatic consumers.

## Summary

Add a `--json` flag to all `ll-` CLI commands that expose a `list` subcommand, enabling machine-readable output for FSM loop consumption and scripted workflows.

## Motivation

FSM loops and automation scripts currently parse human-readable CLI output via text scraping, which is fragile and breaks on formatting changes. A `--json` flag on `list` commands provides a stable, structured interface for programmatic consumers (loop states, shell pipelines, other tools).

Affected commands:
- `ll-issues list`
- `ll-loop list`
- `ll-sprint list`

## Proposed Solution

Add `--json` flag to each `list` subcommand parser. When set, output a JSON array of objects to stdout (one object per item) and exit with code 0. Human-readable table output remains the default.

### Output contract

Each command should emit a JSON array. Representative schemas:

**`ll-issues list --json`**
```json
[
  {
    "id": "ENH-663",
    "priority": "P3",
    "type": "ENH",
    "title": "Add --json flag to ll- CLI list commands",
    "path": ".issues/enhancements/P3-ENH-663-add-json-flag-to-ll-cli-list-commands.md"
  }
]
```

**`ll-loop list --json`**
```json
[
  {
    "name": "my-loop",
    "path": ".loops/my-loop.yaml",
    "active": false
  }
]
```

**`ll-sprint list --json`**
```json
[
  {
    "name": "sprint-2026-q1",
    "path": ".sprints/sprint-2026-q1.yaml",
    "issues": 8
  }
]
```

## Implementation Steps

1. **`ll-issues list`** (`scripts/little_loops/cli/issues/list_cmd.py`):
   - Add `--json` flag to `cmd_list` argument parser
   - When `--json`: serialize the already-computed issue list to JSON array and print; skip table rendering

2. **`ll-loop list`** (`scripts/little_loops/cli/loop/__init__.py`, list branch at line ~264):
   - Add `--json` flag to `list_parser` (line ~145)
   - Emit loop metadata as JSON array when flag is set

3. **`ll-sprint list`** (`scripts/little_loops/cli/sprint/__init__.py`, list branch at line ~200):
   - Add `--json` flag to `list_parser` (line ~133)
   - Emit sprint metadata as JSON array when flag is set

4. **Shared helper** (optional): Add a `print_json(data)` helper in `scripts/little_loops/cli/output.py` to standardize JSON serialization (use `json.dumps(data, indent=2)`).

5. **Tests**: Add parameterized test cases in `scripts/tests/test_cli.py` verifying each command returns valid JSON with `--json` and that existing table output is unchanged without the flag.

## Acceptance Criteria

- [x] `ll-issues list --json` outputs a valid JSON array; each element contains at minimum `id`, `priority`, `type`, `title`, `path`
- [x] `ll-loop list --json` outputs a valid JSON array; each element contains at minimum `name`, `path`
- [x] `ll-sprint list --json` outputs a valid JSON array; each element contains at minimum `name`, `path`
- [x] Default (no `--json`) output is unchanged for all three commands
- [x] Exit code is 0 on success for both modes
- [x] Unit tests cover `--json` path for each command

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/list_cmd.py` — add `--json` flag to `cmd_list` argument parser, serialize issue list to JSON when set
- `scripts/little_loops/cli/loop/__init__.py` — add `--json` flag to `list_parser`, emit loop metadata as JSON array
- `scripts/little_loops/cli/sprint/__init__.py` — add `--json` flag to `list_parser`, emit sprint metadata as JSON array

### Dependent Files (Callers/Importers)
- FSM loop YAML files that invoke `ll-issues list` or `ll-loop list` (consumers will benefit from `--json` once added)
- `scripts/little_loops/cli/output.py` — optional shared `print_json()` helper

### Similar Patterns
- N/A — no existing `--json` flag on list commands; this is the first instance

### Tests
- `scripts/tests/test_cli.py` — add parameterized test cases for `--json` path on each command; verify table output unchanged without flag

### Documentation
- N/A — CLI `--help` text will reflect the new flag automatically

### Configuration
- N/A

## Scope Boundaries

- Only `list` subcommands for `ll-issues`, `ll-loop`, and `ll-sprint` are in scope
- Other subcommands (`show`, `run`, `create`, etc.) do NOT get `--json` in this issue
- JSON schema is not formally versioned or enforced — it is a stable but informal contract
- No changes to human-readable output format

## Impact

- **Priority**: P3 — Eliminates fragile text-parsing in FSM loop automations; enables reliable scripted workflows
- **Effort**: Small — Additive `--json` flag on three existing argument parsers; no structural changes
- **Risk**: Low — Purely additive; default behavior (no flag) is completely unchanged
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `automation`, `captured`

---

**Completed** | Created: 2026-03-09 | Resolved: 2026-03-09 | Priority: P3

## Resolution

Added `--json` flag to `ll-issues list`, `ll-loop list`, and `ll-sprint list` subcommands. When set, each command outputs a JSON array of objects (one per item) to stdout and exits 0. Default human-readable output is unchanged. A shared `print_json()` helper was added to `cli/output.py`.

Files changed:
- `scripts/little_loops/cli/output.py` — added `print_json(data)` helper
- `scripts/little_loops/cli/issues/__init__.py` — added `--json` flag to `list` parser
- `scripts/little_loops/cli/issues/list_cmd.py` — serialize issues to JSON when flag set
- `scripts/little_loops/cli/loop/__init__.py` — added `--json` flag to `list` parser
- `scripts/little_loops/cli/loop/info.py` — serialize loops to JSON when flag set
- `scripts/little_loops/cli/sprint/__init__.py` — added `--json` flag to `list` parser
- `scripts/little_loops/cli/sprint/manage.py` — serialize sprints to JSON when flag set
- `scripts/tests/test_issues_cli.py` — 3 new tests for `--json` path
- `scripts/tests/test_ll_loop_commands.py` — 3 new tests for `--json` path
- `scripts/tests/test_cli.py` — 2 new tests for sprint `--json` path

## Session Log
- `/ll:capture-issue` - 2026-03-09T23:47:50Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d305cad5-64a5-4cef-bf3e-f1c6e65b32db.jsonl`
- `/ll:format-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:verify-issues` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:confidence-check` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/01f82782-0b8c-4ad7-bf21-b0fbd48b9fa2.jsonl`
- `/ll:ready-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75d05dca-d3c0-4752-915a-468f5a607e15.jsonl`
- `/ll:manage-issue` - 2026-03-09T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
