---
discovered_commit: 95d4139206f3659159b727db57578ffb2930085b
discovered_branch: main
discovered_date: 2026-02-24T20:18:21Z
discovered_by: scan-codebase
---

# BUG-477: `ll-messages` epilog documents non-existent `--include-commands` flag

## Summary

The `ll-messages` CLI help epilog at `messages.py:40` documents `--include-commands` as a valid flag, but no such argument is defined in the parser. The actual flag is `--skip-cli` (which does the inverse). Users following the help text example will get an unrecognized argument error.

## Location

- **File**: `scripts/little_loops/cli/messages.py`
- **Line(s)**: 40, 89-98 (at scan commit: 95d4139)
- **Anchor**: `in epilog string` and `parser.add_argument("--skip-cli", ...)`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/95d4139206f3659159b727db57578ffb2930085b/scripts/little_loops/cli/messages.py#L40)
- **Code**:
```python
# Epilog (line 40):
%(prog)s --include-commands           # Include CLI commands

# Actual parser flags (lines 89-98):
parser.add_argument("--skip-cli", action="store_true",
    help="Exclude CLI commands from output (included by default)")
parser.add_argument("--commands-only", action="store_true",
    help="Extract only CLI commands, no user messages")
```

## Current Behavior

The epilog example shows `--include-commands` which is not a registered argument. CLI commands are included by default; the actual flag `--skip-cli` removes them.

## Expected Behavior

The epilog example should reference `--skip-cli` (or another actually-existing flag) to accurately document the tool's behavior.

## Steps to Reproduce

1. Run `ll-messages --help` — see `--include-commands` in examples
2. Run `ll-messages --include-commands` — get `unrecognized arguments` error

## Proposed Solution

Update the epilog example to show `--skip-cli` instead of `--include-commands`:

```python
%(prog)s --skip-cli                   # Exclude CLI commands from output
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — fix epilog example text

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- N/A

### Tests
- N/A

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P3 — User-facing documentation error
- **Effort**: Small — Single line text change
- **Risk**: Low — Documentation fix only
- **Breaking Change**: No

## Labels

`bug`, `cli`, `documentation`, `auto-generated`

## Session Log
- `/ll:scan-codebase` - 2026-02-24T20:18:21Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fa9f831f-f3b0-4da5-b93f-5e81ab16ac12.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
