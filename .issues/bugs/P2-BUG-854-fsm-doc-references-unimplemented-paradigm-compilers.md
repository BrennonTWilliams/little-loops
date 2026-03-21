---
id: BUG-854
type: BUG
priority: P2
status: open
title: "generalized-fsm-loop.md documents unimplemented paradigm compilation (compilers.py, ll-loop compile)"
created: 2026-03-21
---

## Summary

`docs/generalized-fsm-loop.md` contains a substantial section describing a paradigm compilation system that does not exist in the codebase.

## What the Doc Claims

1. **`little_loops/fsm/compilers.py`** exists with `compile_convergence()` and `compile_invariants()` implementations (doc lines ~253-319)
2. **`ll-loop compile` subcommand** exists: `ll-loop compile convergence -o .loops/convergence.fsm.yaml` (doc line ~1392)
3. Paradigms (convergence, invariants, imperative, goal-oriented) compile to FSM YAML via formal Python compilers

## What Actually Exists

- `scripts/little_loops/fsm/compilers.py` — **does not exist**
- `ll-loop compile` — **not registered** as a CLI subcommand (see `scripts/little_loops/cli/loop/__init__.py`)
- The only FSM schema is the direct YAML format; there are no paradigm shortcuts that compile to it

## Impact

Users reading the doc may try to use paradigm syntax or `ll-loop compile` and find it doesn't work.

## Fix Options

**Option A (Preferred if not planned)**: Remove the Paradigm Compilation section entirely. All loop patterns are already documented as direct FSM YAML in the "Loop Pattern Examples" section. Keep that. Remove:
- "Paradigm Compilation" heading and rationale (~lines 222-248)
- "Compiler Implementations" code block (~lines 250-319)
- `ll-loop compile` from CLI Interface section (~line 1392)
- "Unit Tests for Compilers" from Testing Strategy (~lines 1525-1548)

**Option B (If planned for future)**: Add a `> **Note**: Paradigm compilation is planned but not yet implemented.` callout to those sections.
