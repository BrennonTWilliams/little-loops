---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# FEAT-345: Add `ll-loop show` command for loop inspection

## Summary

Add a new `ll-loop show <loop>` subcommand that displays a loop's metadata, states & transitions, a text-art diagram of the FSM, and a ready-to-use `ll-loop run ...` command for copy/paste execution.

## Current Behavior

`ll-loop` has `run`, `list`, and other subcommands but no way to inspect a specific loop's structure without manually reading the YAML file.

## Expected Behavior

Running `ll-loop show <loop-name>` displays:
1. Loop name and metadata (description, paradigm, variables, etc.)
2. States and their transitions in a structured table/list
3. A text-art diagram of the FSM (ASCII state machine visualization)
4. A `ll-loop run ...` command the user can copy/paste to execute the loop

## Motivation

Users need a quick way to understand a loop's structure before running it. Currently they must read raw YAML files, which is tedious and error-prone. A `show` command provides at-a-glance understanding and lowers the barrier to using loops.

## Use Case

A developer has several loop YAML files in their `loops/` directory. Before running one, they want to see what it does — its states, transitions, and parameters. They run `ll-loop show sprint-execution` and get a clear overview plus a ready-to-run command.

## Acceptance Criteria

- `ll-loop show <name>` loads and displays the named loop YAML
- Output includes loop name, description, and key metadata fields
- Output includes a list/table of all states with their transitions and evaluators
- Output includes a text-art FSM diagram showing state flow
- Output includes a copyable `ll-loop run <name>` command with any required arguments
- Handles missing/invalid loop names with clear error messages
- Works with loops in the configured loops directory

## API/Interface

```python
# CLI interface
# ll-loop show <loop-name>
# ll-loop show loops/sprint-execution.yaml  (also accept path)
```

## Proposed Solution

Add `show` subcommand to `scripts/little_loops/cli/loop.py` following the existing `list`/`status` pattern:

1. **Add to `known_subcommands` set** and create parser with a positional `loop` argument (name or path)
2. **Implement `cmd_show()`** that:
   - Resolves loop name to YAML file (reuse `resolve_loop_path()` or similar from `cmd_run`)
   - Loads and parses the YAML with existing FSM loader
   - Renders metadata (name, description, paradigm, variables)
   - Renders states/transitions as a formatted table
   - Generates ASCII FSM diagram (simple box-and-arrow style using string formatting)
   - Prints a copyable `ll-loop run <name>` command
3. **Dispatch** in the main `if/elif` block at the bottom of `main_loop()`

```python
# ASCII diagram example output:
# [start] --> [implement] --> [test] --> [review] --> [done]
#                  |                        |
#                  +--- (fail) ---<---------+
```

Key functions to reuse:
- Loop resolution logic from `cmd_run()` or `cmd_list()` for finding YAML files
- `yaml.safe_load()` for parsing (already used throughout)

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop.py` - Add `show` subcommand to ll-loop CLI

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/` - FSM loader/parser used to read loop YAML

### Similar Patterns
- `ll-loop list` command pattern for CLI subcommand structure

### Tests
- `scripts/tests/test_cli.py` or new `scripts/tests/test_loop_show.py`

### Documentation
- `docs/API.md` - Add `show` subcommand docs
- README if ll-loop CLI usage is documented there

### Configuration
- N/A

## Implementation Steps

1. Add `show` subcommand parser to ll-loop CLI
2. Implement loop YAML loading and metadata extraction
3. Implement state/transition table rendering
4. Implement ASCII FSM diagram generation
5. Compose output with run command suggestion
6. Add tests and error handling

## Impact

- **Priority**: P3 - Quality-of-life improvement, not blocking
- **Effort**: Medium - Diagram generation requires some work
- **Risk**: Low - Additive feature, no breaking changes
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | FSM system design |
| architecture | docs/API.md | CLI tool reference |

## Labels

`feature`, `captured`, `cli`, `ll-loop`

## Session Log
- `/ll:capture_issue` - 2026-02-11T00:00:00Z - `~/.claude/projects/<project>/09f8643a-95e5-4842-b201-dae40adfb54e.jsonl`
- `/ll:refine_issue` - 2026-02-11 - `~/.claude/projects/<project>/dbd89ffd-0647-4b4f-a35c-b8b09dd4813c.jsonl`
- `/ll:manage_issue` - 2026-02-11 - `~/.claude/projects/<project>/311ea8fc-ed1c-4a87-aab3-fe7b1501ab13.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/loop.py`: Added `show` subcommand with metadata display, states/transitions table, ASCII FSM diagram, and run command output
- `scripts/tests/test_ll_loop_commands.py`: Added TestCmdShow with 3 tests (metadata, diagram, error case)

### Verification Results
- Tests: PASS
- Lint: PASS
- Types: PASS

---

## Status

**Completed** | Created: 2026-02-11 | Completed: 2026-02-11 | Priority: P3
