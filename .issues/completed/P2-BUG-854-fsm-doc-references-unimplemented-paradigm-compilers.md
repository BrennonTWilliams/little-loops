---
id: BUG-854
type: BUG
priority: P2
status: completed
title: "generalized-fsm-loop.md documents unimplemented paradigm compilation (compilers.py, ll-loop compile)"
created: 2026-03-21
testable: false
---

## Summary

`docs/generalized-fsm-loop.md` contains a substantial section describing a paradigm compilation system that does not exist in the codebase.

## Current Behavior

The doc (`docs/generalized-fsm-loop.md`) describes functionality that does not exist:

1. **`little_loops/fsm/compilers.py`** — documented as existing with `compile_convergence()` and `compile_invariants()` implementations (doc lines ~253-319), but the file does not exist.
2. **`ll-loop compile` subcommand** — documented as `ll-loop compile convergence -o .loops/convergence.fsm.yaml` (doc line ~1392), but the subcommand is not registered in `scripts/little_loops/cli/loop/__init__.py`.
3. **Paradigm compilation** — convergence, invariants, imperative, and goal-oriented paradigms are described as compiling to FSM YAML via formal Python compilers, but no such system exists.

## Expected Behavior

`docs/generalized-fsm-loop.md` should only document functionality that actually exists. The Paradigm Compilation section should be removed, leaving the "Loop Pattern Examples" section (which documents the direct FSM YAML format that does exist) as the authoritative reference.

## Steps to Reproduce

1. Open `docs/generalized-fsm-loop.md` and search for "Paradigm Compilation".
2. Note the documented `compilers.py` module and `ll-loop compile` subcommand.
3. Check `scripts/little_loops/fsm/` — `compilers.py` is absent.
4. Run `ll-loop --help` — no `compile` subcommand is listed.

## Impact

- **Priority**: P2 — Users reading the doc may attempt to use paradigm syntax or `ll-loop compile`, find it doesn't work, and mistakenly assume a setup problem.
- **Effort**: Small — Pure doc deletion; no code changes required.
- **Risk**: Low — Removing non-functional documentation only.
- **Breaking Change**: No

## Fix

Remove the Paradigm Compilation section entirely. All loop patterns are already documented as direct FSM YAML in the "Loop Pattern Examples" section. Specifically, remove:
- "Paradigm Compilation" heading and rationale (~lines 222-248)
- "Compiler Implementations" code block (~lines 250-319)
- `ll-loop compile` from CLI Interface section (~line 1392)
- "Unit Tests for Compilers" from Testing Strategy (~lines 1525-1548)

## Labels

`documentation`, `doc-accuracy`, `captured`

## Status

**Completed** | Created: 2026-03-21 | Resolved: 2026-03-21 | Priority: P2

## Resolution

Removed the Paradigm Compilation section from `docs/generalized-fsm-loop.md`:
- Deleted `## Paradigm Compilation` section (heading, rationale, architecture diagram, compiler implementations, LLM generation discussion)
- Deleted `ll-loop compile convergence` line from CLI Interface section
- Deleted `### 1. Unit Tests for Compilers` subsection from Testing Strategy
- Removed `test_compilers.py` entry from Test File Organization tree
- Renumbered Testing Strategy subsections 2→1, 3→2, 4→3, 5→4

## Session Log
- `/ll:ready-issue` - 2026-03-21T20:55:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cbe56b19-9356-41bb-9eae-5ef143a22109.jsonl`
- `/ll:manage-issue bug fix BUG-854` - 2026-03-21

