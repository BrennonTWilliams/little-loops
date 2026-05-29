---
id: ENH-1780
title: Add --json flag consistently across all ll-* CLIs
type: enh
status: open
priority: P3
captured_at: "2026-05-29T02:23:45Z"
discovered_date: 2026-05-29
discovered_by: capture-issue
labels:
  - cli
  - agent-composability
  - captured
---

# ENH-1780: Add --json flag consistently across all ll-* CLIs

## Summary

Add `--json` flag support to every `ll-*` CLI command that doesn't yet have it, making all CLIs reliably composable in agent-driven workflows. Modeled after CLI-Anything's universal `--json` contract.

## Current Behavior

Some CLIs support `--json` for structured machine-readable output (`ll-issues list`, `ll-loop list`, `ll-logs discover`), but many commands and CLIs don't. Agents must parse human-formatted text (tables, colored output), which is brittle and breaks when output formatting changes.

## Expected Behavior

Every `ll-*` CLI command that produces output supports a `--json` flag. When passed, the command emits structured JSON to stdout. Human-readable output (tables, colors) remains the default. The contract is: "if it outputs data, it outputs JSON with `--json`."

## Motivation

Agents composing CLI calls need structured, parseable output. CLI-Anything mandates `--json` on every command for this exact reason — it's what makes the generated CLIs "agent-native." In little-loops, the inconsistency forces agents to either:
- Parse human-formatted text (brittle, breaks on formatting changes)
- Skip CLI composition entirely and read files directly (slower, context-heavy)

Quantified: every `ll-*` command without `--json` is a command an agent can't reliably compose into a pipeline.

## Proposed Solution

1. Audit all `ll-*` CLIs for `--json` support gaps. Priority targets based on agent usage:
   - `ll-sprint list/status` — sprint state queries
   - `ll-history` — historical data queries
   - `ll-logs tail` — log streaming output
   - `ll-deps` — dependency graph output
   - `ll-learning-tests list` — registry queries
   - `ll-session recent/search` — session store queries

2. Standardize on a Click decorator or shared option:
   ```python
   # Shared decorator in scripts/little_loops/cli_utils.py
   def json_option(f):
       return click.option("--json", "output_format", flag_value="json",
                           help="Output as JSON")(f)
   ```

3. Add JSON output formatters alongside existing human-readable output in each CLI.

## Integration Map

### Files to Modify
- Each `scripts/little_loops/*.py` CLI that lacks `--json` on data-emitting commands

### Dependent Files (Callers/Importers)
- Any automation scripts that invoke these CLIs and parse output
- `ll-auto`, `ll-parallel`, `ll-sprint` orchestrators that chain CLI calls

### Tests
- Add JSON output assertion tests to existing CLI test files
- Verify `--json` flag help text appears in `--help` output

### Documentation
- `docs/reference/API.md` — document the universal `--json` contract

## Implementation Steps

1. Audit all `ll-*` CLIs: enumerate commands, flag which have `--json`, which don't
2. Create shared `json_option` decorator in `cli_utils.py`
3. Add `--json` to each command, starting with highest agent-usage CLIs
4. Add JSON output tests for each updated command
5. Document the universal `--json` contract

## Impact

- **Priority**: P3 — Not blocking, but reduces agent brittleness across all workflows
- **Effort**: Medium — Many CLIs to touch, but each change is mechanical (add flag + branch on output format)
- **Risk**: Low — Additive change, existing output unchanged, no breaking API surface
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `cli`, `agent-composability`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-05-29T02:23:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8b24cba6-684e-4420-9519-de98c8b4822b.jsonl`

---

**Open** | Created: 2026-05-29 | Priority: P3
