# ENH-337: map-dependencies skill should delegate to dependency_mapper.py - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-337-map-dependencies-skill-should-use-dependency-mapper-module.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

- `dependency_mapper.py` has full Python implementation but no CLI entry point
- `map-dependencies` skill reimplements all algorithms as prose instructions
- `analyze-history` skill correctly wraps `ll-history` CLI — this is the pattern to follow

## Desired End State

1. `dependency_mapper.py` has a `main()` function with `analyze` and `validate` subcommands
2. `pyproject.toml` registers `ll-deps` entry point
3. Skill delegates to `ll-deps` CLI instead of reimplementing logic

## What We're NOT Doing

- Not changing underlying algorithms in dependency_mapper.py
- Not adding new analysis features
- Not modifying other skills

## Implementation Phases

### Phase 1: Add main() CLI to dependency_mapper.py

Add `main()` function with argparse supporting:
- `ll-deps analyze` — full analysis (overlaps + validation), outputs markdown
- `ll-deps validate` — validation only
- Options: `--issues-dir`, `--format` (text/json), `--graph` (include ASCII graph)

Follow the `ll-workflows` pattern (main() in module itself, not cli.py) since this is a standalone module.

### Phase 2: Register ll-deps in pyproject.toml

Add: `ll-deps = "little_loops.dependency_mapper:main"`

### Phase 3: Rewrite map-dependencies skill

Simplify to invoke CLI and handle user interaction (proposal confirmation + apply).

### Phase 4: Add CLI tests

Add tests for argument parsing and basic integration.

### Phase 5: Update help.md

Add `ll-deps` CLI reference.

## Testing Strategy

- Unit tests for argument parsing
- Integration test for main() with tmp_path issues
- Existing tests remain unchanged
