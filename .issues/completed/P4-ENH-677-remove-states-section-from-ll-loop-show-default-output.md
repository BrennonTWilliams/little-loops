---
discovered_date: 2026-03-12T00:00:00Z
discovered_by: capture-issue
---

# ENH-677: Remove States Section from `ll-loop show` Default Output

## Summary

The non-verbose (default) output of `ll-loop show <loop>` includes a "States" section that lists all states with truncated action previews. This adds visual clutter to the compact view without providing enough detail to be useful — the diagram already shows state names and transitions at a glance. Users who want state details should use `--verbose`.

## Current Behavior

Running `ll-loop show <loop>` (without `--verbose`) displays: metadata, description, diagram, **States section with truncated action previews**, and commands. The States section repeats information already visible in the diagram (state names, initial/terminal markers, transitions) while adding truncated action text that is too short to be actionable.

## Expected Behavior

Running `ll-loop show <loop>` (without `--verbose`) displays: metadata, description, diagram, and commands — no States section. The `--verbose` flag continues to show the full States section with complete action text, evaluate config, and transitions.

## Motivation

The compact view is meant for quick orientation — "what does this loop do and how is it structured?" The FSM diagram already answers the structural question (states, transitions, initial/terminal markers). The truncated States section duplicates this while adding noise. Removing it makes the default output tighter and more scannable, especially for loops with many states.

## Proposed Solution

In `scripts/little_loops/cli/loop/info.py`, in `cmd_show()`, gate the States section rendering behind the `verbose` flag. The States section is already rendered in full when `--verbose` is passed; the change is to skip the compact/truncated version when `verbose` is `False`.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/info.py` — `cmd_show()`: wrap the non-verbose States rendering block in `if verbose:`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — dispatches to `cmd_show`, no changes needed

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_ll_loop_commands.py` — update assertions for non-verbose output to confirm States section is absent
- `scripts/tests/test_ll_loop_display.py` — check for any non-verbose output assertions that reference States

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Identify the non-verbose States rendering block in `cmd_show()`
2. Gate it behind `if verbose:`
3. Update test assertions for non-verbose output
4. Verify `--verbose` still shows the full States section

## Scope Boundaries

Out of scope:
- Any changes to the `--verbose` output (States section remains there)
- Changes to the FSM diagram rendering
- Changes to other `ll-loop` subcommands

## Success Metrics

- `ll-loop show <loop>` output contains no "States:" section
- `ll-loop show <loop> --verbose` output still contains the full "States:" section
- All existing tests pass with updated assertions

## Impact

- **Priority**: P4 — Minor UX polish, no functional impact
- **Effort**: Small — Single conditional gate in one function
- **Risk**: Low — Output-only change, no behavioral impact on loop execution
- **Breaking Change**: No (output format change only; no structured consumers)

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI architecture and command structure |

## Labels

`enhancement`, `cli`, `ux`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/028e0b16-2b5a-40d5-aaab-f811b6528c1c.jsonl`
- `/ll:ready-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Resolution

**Completed** on 2026-03-12.

### Changes Made
- `scripts/little_loops/cli/loop/info.py`: Gated state overview table and States section behind `if verbose:` in `cmd_show()`
- Simplified verbose-only rendering by removing non-verbose truncation branches (no longer needed)
- Updated 10 tests in `scripts/tests/test_ll_loop_commands.py` to match new behavior

### Verification
- All 134 loop tests pass
- Linting and type checking pass
- Non-verbose output: metadata, description, diagram, commands (no States section)
- Verbose output: full States section with complete action text, evaluate config, transitions

---

## Status

**Completed** | Created: 2026-03-12 | Completed: 2026-03-12 | Priority: P4
