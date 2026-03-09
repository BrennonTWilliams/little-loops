---
discovered_date: 2026-03-09
discovered_by: capture-issue
---

# ENH-663: Add `--json` flag to `ll-` CLI list commands

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

- [ ] `ll-issues list --json` outputs a valid JSON array; each element contains at minimum `id`, `priority`, `type`, `title`, `path`
- [ ] `ll-loop list --json` outputs a valid JSON array; each element contains at minimum `name`, `path`
- [ ] `ll-sprint list --json` outputs a valid JSON array; each element contains at minimum `name`, `path`
- [ ] Default (no `--json`) output is unchanged for all three commands
- [ ] Exit code is 0 on success for both modes
- [ ] Unit tests cover `--json` path for each command

## Related Files

| File | Role |
|------|------|
| `scripts/little_loops/cli/issues/list_cmd.py` | `ll-issues list` implementation |
| `scripts/little_loops/cli/loop/__init__.py` | `ll-loop list` implementation |
| `scripts/little_loops/cli/sprint/__init__.py` | `ll-sprint list` implementation |
| `scripts/little_loops/cli/output.py` | Shared output helpers |
| `scripts/tests/test_cli.py` | Existing CLI tests |

---

## Session Log
- `/ll:capture-issue` - 2026-03-09T23:47:50Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d305cad5-64a5-4cef-bf3e-f1c6e65b32db.jsonl`
