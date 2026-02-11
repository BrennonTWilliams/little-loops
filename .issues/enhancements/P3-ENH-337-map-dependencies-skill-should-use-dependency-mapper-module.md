---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# ENH-337: map-dependencies skill should delegate to dependency_mapper.py

## Summary

The `map-dependencies` skill re-implements dependency analysis logic (file overlap detection, dependency validation, cycle detection) entirely in prompt instructions rather than calling the existing `scripts/little_loops/dependency_mapper.py` Python module. This duplicates logic and risks drift between the two implementations.

## Current Behavior

- `dependency_mapper.py` contains a full Python implementation of file overlap detection, semantic conflict scoring, dependency validation, and cycle detection
- The `map-dependencies` skill (`skills/map-dependencies/SKILL.md`) describes the same algorithms as prose instructions for Claude to follow manually via tool calls
- Neither references the other — they are completely disconnected
- `dependency_mapper.py` has no CLI entry point in `pyproject.toml`

## Expected Behavior

The skill should delegate to the Python module (following the pattern of `analyze-history` skill which correctly wraps `ll-history` CLI). This means:
1. `dependency_mapper.py` gets a CLI entry point (e.g., `ll-deps`)
2. The skill invokes `ll-deps` via Bash and interprets results
3. Single source of truth for the analysis algorithms

## Motivation

The `analyze-history` skill demonstrates the correct integration pattern: skill wraps CLI tool. Having duplicate logic means bug fixes to the Python module won't be reflected in the skill's behavior and vice versa.

## Proposed Solution

1. Add CLI entry point `ll-deps` in `pyproject.toml` pointing to `dependency_mapper` module
2. Add a `main()` function to `dependency_mapper.py` with subcommands: `analyze`, `validate`
3. Simplify `map-dependencies` skill to invoke `ll-deps analyze` and `ll-deps validate`, then present results

### Implementation Steps

1. Add `main()` CLI to `dependency_mapper.py` with argparse
2. Register `ll-deps` in `pyproject.toml` `[project.scripts]`
3. Rewrite skill to call CLI and format output
4. Update `help.md` to reference `ll-deps` CLI

## Impact

- **Scope**: `dependency_mapper.py`, `skills/map-dependencies/SKILL.md`, `pyproject.toml`
- **Severity**: Medium — prevents logic drift between Python module and skill

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | System design patterns |
| architecture | docs/API.md | Python module reference |

## Labels

`enhancement`, `integration`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P3
