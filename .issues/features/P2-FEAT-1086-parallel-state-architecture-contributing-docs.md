---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1083
testable: false
confidence_score: 95
outcome_confidence: 85
---

# FEAT-1086: Parallel State — Architecture and Contributing Docs

## Summary

Update `docs/ARCHITECTURE.md` with a new `## FSM Loop Mode (ll-loop)` section documenting the `parallel:` state type, and update `CONTRIBUTING.md` to add `parallel_runner.py` to the `fsm/` directory tree.

## Parent Issue

Decomposed from FEAT-1083: Parallel State Core Reference Documentation

## Motivation

- `docs/ARCHITECTURE.md` has no FSM state-types section at all — the `parallel:` state type is undiscoverable without reading source code
- `CONTRIBUTING.md` `fsm/` directory tree is missing `parallel_runner.py`, making contributors unaware the file exists
- These are structural/overview documentation gaps that block contributor onboarding

## Current Behavior

- `docs/ARCHITECTURE.md` FSM section does not mention the `parallel:` state type (no FSM state-types section exists)
- `CONTRIBUTING.md:231` `fsm/` directory tree does not list `parallel_runner.py`

## Expected Behavior

- `docs/ARCHITECTURE.md` has a new `## FSM Loop Mode (ll-loop)` section documenting `parallel:` as a state type (fan-out behavior, fields, routing)
- `CONTRIBUTING.md` `fsm/` tree lists `parallel_runner.py`

## Proposed Solution

### `docs/ARCHITECTURE.md`

Insert a new `## FSM Loop Mode (ll-loop)` section after line 451 (before `## Extension Architecture & Event Flow` at line 454). Document the `parallel:` state type:

- Fan-out behavior and purpose
- `items` source (interpolated expression → newline-delimited list)
- Sub-loop invocation (`loop` field)
- Worker control (`max_workers`, `isolation`, `fail_mode`)
- Routing via `on_yes` / `on_partial` / `on_no`
- Reference `ParallelStateConfig` and `ParallelResult` as the schema types (documented in FEAT-1087)
- Cross-reference `docs/generalized-fsm-loop.md` — specifically `## Universal FSM Schema` (line 222) and `### Action Types` (line 226) — rather than duplicating content

Include the following YAML example (modeled after `generalized-fsm-loop.md:191-219` sub-loop composition format):

```yaml
run_tests:
  parallel:
    items: "${context.test_files}"   # newline-delimited list
    loop: run_single_test
    max_workers: 4
    isolation: worktree
    fail_mode: collect
  on_yes: done
  on_partial: report_failures
  on_no: fail
```

Follow the `ParallelStateConfig` Field Reference from FEAT-1083 for field descriptions.

### `CONTRIBUTING.md`

The `fsm/` directory tree is at lines 231–243. The last entry is `└── handoff_handler.py` at line 243. Insert `parallel_runner.py` before it, changing `└──` to `├──` for `handoff_handler.py`:

```
│   ├── parallel_runner.py
│   └── handoff_handler.py
```

## Implementation Steps

1. Update `docs/ARCHITECTURE.md` — insert `## FSM Loop Mode (ll-loop)` section after line 451 with `parallel:` state type description, YAML example, and cross-reference to `docs/generalized-fsm-loop.md`
2. Update `CONTRIBUTING.md` — insert `│   ├── parallel_runner.py` before `└── handoff_handler.py` at line 243, updating `└──` to `├──`

## Integration Map

### Files to Modify

| File | Insertion Point | What to Add |
|------|----------------|-------------|
| `docs/ARCHITECTURE.md` | After line 451 (before `## Extension Architecture`) | New `## FSM Loop Mode (ll-loop)` section with `parallel:` state type |
| `CONTRIBUTING.md` | Line 242 (before `└── handoff_handler.py`) | `│   ├── parallel_runner.py` |

### Read-only Dependencies

- `scripts/little_loops/fsm/parallel_runner.py` — created by FEAT-1075/FEAT-1076 (may not exist yet; write docs against the specified interface)
- `docs/generalized-fsm-loop.md` — cross-reference target; `## Universal FSM Schema` at line 222

### Caveats

- `CONTRIBUTING.md` `fsm/` tree has broader discrepancies beyond `parallel_runner.py` (missing `runners.py`, `types.py`, `fragments.py`; has non-existent `compilers.py`). The task here is only to add `parallel_runner.py` — the broader cleanup is out of scope.
- The `ll-verify-docs` validator scans `ARCHITECTURE.md` and `CONTRIBUTING.md` for count patterns — ensure new FSM section text does not accidentally match `\d+ \w* (commands|agents|skills)` pattern.

## Dependencies

- FEAT-1075/FEAT-1076 should be complete for accurate `parallel_runner.py` content; write against specified interface if not yet merged

## Acceptance Criteria

- `docs/ARCHITECTURE.md` has a new `## FSM Loop Mode (ll-loop)` section documenting `parallel:` state type with fields, YAML example, and cross-reference to `generalized-fsm-loop.md`
- `CONTRIBUTING.md` `fsm/` directory tree includes `parallel_runner.py`

## Impact

- **Priority**: P2
- **Effort**: Small — 2 files, targeted insertions
- **Risk**: Very Low — documentation-only
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`

---

## Session Log
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6db3cacd-18d3-4b5b-9ee4-3154dcc307d7.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
