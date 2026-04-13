---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1078
testable: false
confidence_score: 95
outcome_confidence: 63
---

# FEAT-1082: Parallel State Documentation

## Summary

Update all documentation touchpoints to describe the `parallel:` state type, `ParallelStateConfig`, and `ParallelResult`: architecture docs, API reference, loops guide, loops README, CONTRIBUTING.md, and create-loop skill docs.

## Parent Issue

Decomposed from FEAT-1078: Parallel State Wiring, Display, and Docs

## Current Behavior

- `docs/ARCHITECTURE.md` FSM section does not mention the `parallel:` state type
- `docs/reference/API.md` has no `ParallelStateConfig` or `ParallelResult` entries in the schema reference
- `docs/guides/LOOPS_GUIDE.md:1653` "Composable Sub-Loops" section and comparison table (lines 1695–1700) describe only `loop:` and inline states; no `parallel:` row or YAML example
- `scripts/little_loops/loops/README.md:148` "Composing Loops" section references only the `loop:` field; no `parallel:` fan-out pattern
- `CONTRIBUTING.md:231` `fsm/` directory tree does not list `parallel_runner.py`
- `skills/create-loop/reference.md:686` `loop:` field section has no adjacent `parallel:` documentation
- `skills/create-loop/loop-types.md:978` sub-loop composition section describes `loop:` as the only child mechanism; `parallel:` is absent

## Expected Behavior

- `docs/ARCHITECTURE.md` documents `parallel:` state type in the FSM section
- `docs/reference/API.md` includes `ParallelStateConfig` and `ParallelResult` in the schema reference
- `LOOPS_GUIDE.md` comparison table includes a `parallel:` row with YAML example
- `loops/README.md` "Composing Loops" section describes `parallel:` fan-out alongside `loop:`
- `CONTRIBUTING.md` `fsm/` tree lists `parallel_runner.py`
- `skills/create-loop/reference.md` documents `parallel:` field alongside `loop:`
- `skills/create-loop/loop-types.md` presents `parallel:` as a peer concurrent fan-out mechanism

## Use Case

A loop author wants to fan out processing across multiple items concurrently using the `parallel:` state type. They look up the architecture docs, API reference, and loops guide to understand the available fields (`items`, `loop`, `max_workers`, `isolation`, `fail_mode`) and model a `parallel:` state in their loop YAML. They also check `skills/create-loop` for inline authoring guidance. Without any documentation, they have no way to discover that `parallel:` exists or how to configure it — the feature is effectively invisible.

## Proposed Solution

### `docs/ARCHITECTURE.md`

Add a `parallel:` state type entry to the FSM section. Describe: fan-out behavior, `items` source, sub-loop invocation, `max_workers`, `isolation`, `fail_mode`. Reference `ParallelStateConfig` and `ParallelResult` as the schema types.

### `docs/reference/API.md`

Add `ParallelStateConfig` and `ParallelResult` to the schema reference section. Document fields: `items`, `loop`, `max_workers`, `isolation`, `fail_mode`. Include type signatures and brief descriptions for each field.

### `docs/guides/LOOPS_GUIDE.md`

- Add `parallel:` row to the state type comparison table at lines 1695–1700 (alongside existing `loop:` row)
- Add YAML example demonstrating a `parallel:` state in the "Composable Sub-Loops" section at line 1653

### `scripts/little_loops/loops/README.md`

- Extend the "Composing Loops" section at line 148 to describe `parallel:` fan-out pattern alongside the existing `loop:` sub-loop description
- Include a minimal YAML snippet showing `parallel:` usage

### `CONTRIBUTING.md`

- Add `parallel_runner.py` to the `fsm/` directory tree listing at line 231

### `skills/create-loop/reference.md`

- Add `parallel:` field documentation at line 686, immediately after the `loop:` field section
- Document fields: `items`, `loop`, `max_workers`, `isolation`, `fail_mode`

### `skills/create-loop/loop-types.md`

- Extend the sub-loop composition section at line 978 to present `parallel:` as a peer concurrent fan-out mechanism alongside `loop:` (sequential single-loop invocation)

## Implementation Steps

1. Update `docs/ARCHITECTURE.md` — add `parallel:` state type to FSM section
2. Update `docs/reference/API.md` — add `ParallelStateConfig` and `ParallelResult` schema entries
3. Update `docs/guides/LOOPS_GUIDE.md` — add `parallel:` table row and YAML example
4. Update `scripts/little_loops/loops/README.md` — add `parallel:` to Composing Loops section
5. Update `CONTRIBUTING.md` — add `parallel_runner.py` to `fsm/` tree
6. Update `skills/create-loop/reference.md` — add `parallel:` field docs
7. Update `skills/create-loop/loop-types.md` — add `parallel:` mechanism description

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/generalized-fsm-loop.md` — (a) add `parallel:` row to "Common Loop Patterns" table at lines 37-43; (b) add new "Parallel Fan-Out" section after the Sub-Loop Composition section (line ~218); (c) add `parallel` field to the Universal FSM Schema state definition block at line ~261
9. Update `skills/create-loop/SKILL.md` — add `**Parallel fan-out** — not a wizard type; use \`parallel:\` field in YAML` to the type mapping section at lines 82-90, alongside the existing sub-loop composition note
10. Review `skills/create-loop/templates.md` — check whether YAML templates exist for sub-loop/composition types; add a `parallel:` fan-out template if so

## Integration Map

### Files to Modify

| File | Insertion Point | What to Add |
|------|----------------|-------------|
| `docs/ARCHITECTURE.md` | New `## FSM Loop Mode (ll-loop)` section (no FSM section exists; add after line 451 or before `## Extension Architecture`) | `parallel:` state type description |
| `docs/reference/API.md` | Line 3791 — after `loop:` and `context_passthrough:` fields in `StateConfig` block; add `parallel` field inline comment + new `ParallelStateConfig` and `ParallelResult` classes after `StateConfig` block (~line 3797) | `parallel` field in `StateConfig`; two new dataclass blocks |
| `docs/guides/LOOPS_GUIDE.md` | Line 1699 — add `parallel:` row to the "When to Use Sub-Loops vs. Inline States" table (between `Sub-loop (loop:)` and `Inline states` rows); add new `## Parallel Fan-Out (parallel:)` section after line 1689 context-passthrough section | One table row + new section with YAML example |
| `scripts/little_loops/loops/README.md` | Line 161 — end of "Composing Loops" section; extend with `parallel:` fan-out description + YAML snippet | One paragraph + YAML block |
| `CONTRIBUTING.md` | Line 243 — after `└── handoff_handler.py` in `fsm/` tree | `│   ├── parallel_runner.py` entry |
| `skills/create-loop/reference.md` | After line 731 — end of `#### loop (Optional)` field block | New `#### parallel (Optional)` field block in same format |
| `skills/create-loop/loop-types.md` | After line 1014 — end of Sub-Loop Composition section | New `## Parallel Fan-Out` section as a peer mechanism |
| `docs/generalized-fsm-loop.md` | Lines 37-43 (pattern table), 191-218 (section 6 end), line 261 (Universal FSM Schema state definition) | Add `parallel:` to "Common Loop Patterns" table; add new "Parallel Fan-Out" section after Sub-Loop Composition; add `parallel` field to schema definition block |
| `skills/create-loop/SKILL.md` | Lines 82-90 — "Type Mapping" note section | Add: `**Parallel fan-out** — not a wizard type; use \`parallel:\` field in YAML (see \`reference.md\`)` alongside existing sub-loop composition note |
| `skills/create-loop/templates.md` | Review all state-type templates for completeness | Add a `parallel:` fan-out YAML template if composition types have templates |

_Wiring pass added by `/ll:wire-issue`:_

### Read-only Dependencies

**Note: Neither file exists yet** — both are upstream dependencies that must be complete before documentation can reference exact line numbers:
- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` will be added by FEAT-1074 (not yet present; `schema.py` currently ends at line 632 with no parallel types)
- `scripts/little_loops/fsm/parallel_runner.py` — entire file will be created by FEAT-1075/FEAT-1076 (file does not exist)

Documentation can be written against the specified interface from FEAT-1074/1075 issues (see Codebase Research Findings below).

### Dependent Files (Callers/Importers)

N/A — documentation files are not imported by code

### Similar Patterns

- `skills/create-loop/reference.md:684–731` — `#### loop (Optional)` block: the exact format to replicate for `parallel:`
- `skills/create-loop/loop-types.md:976–1014` — Sub-Loop Composition section: the exact format to replicate for parallel fan-out
- `docs/guides/LOOPS_GUIDE.md:1653–1689` — Composable Sub-Loops section: the format for YAML examples and section intro

### Tests

N/A — documentation-only; no test files require updates. `ll-check-links` covers `docs/**/*.md` for HTTP URLs and will scan the modified doc files, but no content-assertion tests exist for any of the seven target files.

### Configuration

N/A — no configuration files affected by this issue directly.

_Wiring pass added by `/ll:wire-issue`:_

**Conditional on FEAT-1081 (CLI Display):** If FEAT-1081 adds a `glyphs.parallel` display badge, two additional files need updating:
- `docs/reference/CONFIGURATION.md:454-459` — `loops.glyphs` table currently lists six state badge keys (`prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route`); a `glyphs.parallel` row must be added
- `config-schema.json:658-669` — `loops.glyphs` object has `additionalProperties: false`; a `"parallel"` string property must be added or users setting `glyphs.parallel` in `ll-config.json` will get a schema validation error

These changes belong to FEAT-1081 scope if it introduces the glyph, or should be tracked as a follow-up. Do not block FEAT-1082 on them.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis of FEAT-1074 and FEAT-1075 issue specs:_

#### `ParallelStateConfig` — Complete Field Specification

From `.issues/features/P2-FEAT-1074-parallel-state-schema-and-validation.md` (planned for `schema.py`):

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `items` | `str` | required | Interpolated expression resolving to a newline-delimited list of items |
| `loop` | `str` | required | Name of the sub-loop to run per item (resolved via `.loops/<name>.yaml`) |
| `max_workers` | `int` | `4` | Maximum concurrent workers |
| `isolation` | `str` | `"worktree"` | Isolation mode: `"worktree"` (git-isolated) or `"thread"` (shared working dir) |
| `fail_mode` | `str` | `"collect"` | Error behavior: `"collect"` (all workers run to completion) or `"fail_fast"` (cancel remaining on first failure) |
| `context_passthrough` | `bool` | `False` | When `True`, passes parent captured context into each worker's sub-loop initial context |

Mutual exclusions: `parallel` + `action`, `parallel` + `loop`, `parallel` + `next` are all invalid combinations.

#### `ParallelResult` — Complete Field Specification

From `.issues/features/P2-FEAT-1075-parallel-runner-module.md` (planned for `parallel_runner.py`):

| Field | Type | Description |
|-------|------|-------------|
| `succeeded` | `list[str]` | Items that reached terminal state named `"done"` |
| `failed` | `list[str]` | Items that did not reach `"done"` (error, timeout, signal, handoff, non-done terminal) |
| `all_captures` | `list[dict]` | Per-worker `captured` dicts, indexed by item order |
| `verdict` | `str` | `"yes"` (all succeeded), `"no"` (all failed), `"partial"` (mixed) |

#### Routing Conventions

Parallel states route via: `on_yes` (all succeeded), `on_partial` (mixed), `on_no` (all failed).
Captures flow back via: `${captured.<state_name>.results}` — contains `all_captures`.

#### ARCHITECTURE.md — No Existing FSM State-Type Section

`docs/ARCHITECTURE.md` has no "FSM Loop Mode" or state-types section. Sections are: Sequential Mode, Parallel Mode, Extension Architecture, Class Relationships, Configuration Flow, etc. A new `## FSM Loop Mode (ll-loop)` section needs to be created. The `fsm/` directory entry is at `ARCHITECTURE.md:254` and no state type documentation exists anywhere in the file.

#### `docs/reference/API.md` StateConfig Block

The `StateConfig` dataclass block is at `API.md:3777–3795`. The `loop:` field is at line 3791 and `context_passthrough:` at line 3792. The `parallel` field should be added at line 3793 (after `context_passthrough`) as:
```python
    parallel: ParallelStateConfig | None = None  # Fan-out: run sub-loop concurrently over items
```
New `ParallelStateConfig` and `ParallelResult` class blocks should be added immediately after the `StateConfig` block (after line 3797).

#### `CONTRIBUTING.md` fsm/ Tree

The `fsm/` directory tree in `CONTRIBUTING.md:231–243` lists 11 files. The last entry is `└── handoff_handler.py` at line 243. `parallel_runner.py` should be inserted before it (changing `└──` to `├──` for `handoff_handler.py`).

## Dependencies

- FEAT-1074 and FEAT-1076 should be complete for accurate documentation (field names, semantics, fail modes)
- Can be merged independently if documentation is clearly marked as describing planned behavior

## Acceptance Criteria

- `docs/ARCHITECTURE.md` documents `parallel:` state type
- `docs/reference/API.md` includes `ParallelStateConfig` and `ParallelResult`
- `LOOPS_GUIDE.md` comparison table includes `parallel:` row
- `create-loop` skill docs describe `parallel:` alongside `loop:`
- `CONTRIBUTING.md` lists `parallel_runner.py` in the `fsm/` tree

## Impact

- **Priority**: P2 — documentation gap makes `parallel:` state invisible to developers; blocks correct usage of an implemented feature
- **Effort**: Small — Documentation-only; no code changes
- **Risk**: Very Low — No code modified; documentation-only
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`

---

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-13T00:01:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847acfcb-8aba-4124-8dc8-a98c7902e550.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a4f936ed-2c70-4384-91f8-15f6bc968b95.jsonl`
- `/ll:wire-issue` - 2026-04-12T23:55:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fb4b73df-7e24-44b9-b58d-111baf90419f.jsonl`
- `/ll:refine-issue` - 2026-04-12T23:48:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4f8fc4b9-85b6-49cc-a00d-2972dff4910b.jsonl`
- `/ll:format-issue` - 2026-04-12T23:44:10 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a1579f05-6671-426a-84dc-53dcd5dd8fe1.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/77a4f6c6-909a-4d66-84d7-1e952b12aed8.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847acfcb-8aba-4124-8dc8-a98c7902e550.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-12
- **Reason**: Issue too large for single session (score 11/11 — 10 documentation files across 3 distinct domains)

### Decomposed Into
- FEAT-1083: Parallel State Core Reference Documentation (ARCHITECTURE.md, API.md, CONTRIBUTING.md)
- FEAT-1084: Parallel State Loop Usage Documentation (LOOPS_GUIDE.md, README.md, generalized-fsm-loop.md)
- FEAT-1085: Parallel State Create-Loop Skill Documentation (reference.md, loop-types.md, SKILL.md, templates.md)

---

**Decomposed** | Created: 2026-04-12 | Priority: P2
