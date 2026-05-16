---
id: ENH-1257
type: ENH
priority: P4
status: done
title: "Reassign -q shorthand to --queue in ll-loop run"
captured_at: "2026-04-22T18:42:46Z"
completed_at: "2026-04-22T18:53:41Z"
discovered_date: "2026-04-22"
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 97
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
---

# ENH-1257: Reassign -q shorthand to --queue in ll-loop run

## Summary

In `ll-loop run`, `-q` currently maps to `--quiet`. Reassign `-q` to `--queue` (the more frequently useful flag) and add `--qt` as the new shorthand for `--quiet`.

## Motivation

`--queue` is a more operationally significant flag than `--quiet` — users running concurrent loops need it regularly, while `--quiet` is a display preference. Giving `--queue` the `-q` mnemonic (queue → q) makes it faster to use and mirrors the intuitive mapping. `--qt` is a reasonable compact form for quiet.

## Current Behavior

In `scripts/little_loops/cli/loop/__init__.py:126`:
```python
run_parser.add_argument("--quiet", "-q", action="store_true", help="Suppress progress output")
```
`--queue` at line 144 has no shorthand.

## Expected Behavior

```python
run_parser.add_argument("--quiet", "--qt", action="store_true", help="Suppress progress output")
run_parser.add_argument("--queue", "-q", action="store_true", help="Wait for conflicting loops to finish")
```

## Implementation Steps

1. In `scripts/little_loops/cli/loop/__init__.py`:
   - Change `--quiet` argument: replace `"-q"` with `"--qt"`
   - Change `--queue` argument: add `"-q"` shorthand
2. Search for any tests that pass `-q` to `ll-loop run` and update them to use `--qt` if they mean quiet, or verify they correctly mean queue.
3. Update any docs or help text that references `-q` for quiet.

## Scope Boundaries

- **In scope**: Reassign `-q` from `--quiet` to `--queue` in `ll-loop run`; add `--qt` as shorthand for `--quiet`; update tests that reference `-q` for quiet
- **Out of scope**: Changing `--queue` behavior or semantics; modifying other `ll-loop` subcommands; updating other CLI tools (only `ll-loop run` is affected)

## Impact

- **Priority**: P4 — Ergonomic improvement; `--queue` works today without a shorthand
- **Effort**: Small — Two `add_argument()` edits plus a test grep/update pass
- **Risk**: Low — Isolated to one subparser in `loop/__init__.py`
- **Breaking Change**: Yes — `-q` behavior changes from `--quiet` to `--queue` for existing users

## Labels

`enhancement`, `cli`, `ux`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — `add_argument` calls for `--quiet` and `--queue` in `run_parser`
- `scripts/tests/test_ll_loop_commands.py` — update any `-q` usages that intend `--quiet`

### Dependent Files (Callers/Importers)
- TBD — `grep -r "\-q" scripts/tests/` to find all `-q` invocations in test suite

### Similar Patterns
- TBD — check other CLI subparsers in `scripts/little_loops/cli/` for shorthand assignment patterns

### Tests
- `scripts/tests/test_ll_loop_commands.py` — update `-q` → `--qt` for quiet-intent tests; verify `-q` now exercises queue path
- Any other files under `scripts/tests/` that call `ll-loop run -q`

### Documentation
- N/A — no user-facing docs reference this shorthand explicitly

### Configuration
- N/A

## Status

**Completed** | Created: 2026-04-22 | Completed: 2026-04-22 | Priority: P4

## Resolution

Reassigned `-q` from `--quiet` to `--queue` in `ll-loop run` subparser. Added `--qt` as the new shorthand for `--quiet`. Two-line edit in `scripts/little_loops/cli/loop/__init__.py`; no test updates needed (no existing tests used `-q`). All 5138 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-04-22T18:50:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e4327f67-d43e-4879-b256-fb2979997e69.jsonl`
- `/ll:confidence-check` - 2026-04-22T19:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/28a15bfe-9f80-4203-a735-a265f3ec3df9.jsonl`
- `/ll:format-issue` - 2026-04-22T18:45:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7fbdbe8b-0692-45cd-9da7-60c7a7184dcb.jsonl`
- `/ll:capture-issue` - 2026-04-22T18:42:46Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b42c4ba0-d0fb-45e7-9def-c052cefea186.jsonl`
