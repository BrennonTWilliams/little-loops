---
discovered_date: "2026-04-12"
discovered_by: issue-size-review
parent_issue: FEAT-1082
testable: false
confidence_score: 93
outcome_confidence: 71
---

# FEAT-1083: Parallel State Core Reference Documentation

## Summary

Update `docs/ARCHITECTURE.md`, `docs/reference/API.md`, and `CONTRIBUTING.md` to document the `parallel:` state type, `ParallelStateConfig`, and `ParallelResult` schema types.

## Motivation

- The `parallel:` state type is a significant new FSM capability with no existing reference documentation
- Without docs, contributors must read source code to understand `items`, `fail_mode`, `isolation`, and routing fields — there is no self-serve path
- Blocks adoption of parallel state in new loops; developers cannot configure it correctly without guessing at field names and defaults
- Completes the documentation deliverable for FEAT-1082 (Parallel State Documentation)

## Parent Issue

Decomposed from FEAT-1082: Parallel State Documentation

## Current Behavior

- `docs/ARCHITECTURE.md` FSM section does not mention the `parallel:` state type (no FSM state-types section exists at all)
- `docs/reference/API.md` has no `ParallelStateConfig` or `ParallelResult` entries in the schema reference
- `CONTRIBUTING.md:231` `fsm/` directory tree does not list `parallel_runner.py`

## Expected Behavior

- `docs/ARCHITECTURE.md` has a new `## FSM Loop Mode (ll-loop)` section documenting `parallel:` as a state type (fan-out behavior, fields, routing)
- `docs/reference/API.md` includes `parallel` field in `StateConfig` and new `ParallelStateConfig` and `ParallelResult` dataclass blocks
- `CONTRIBUTING.md` `fsm/` tree lists `parallel_runner.py`

## Proposed Solution

### `docs/ARCHITECTURE.md`

Create a new `## FSM Loop Mode (ll-loop)` section (insert after line 451 / before `## Extension Architecture & Event Flow` at line 454). Document `parallel:` state type:
- Fan-out behavior and purpose
- `items` source (interpolated expression → newline-delimited list)
- Sub-loop invocation (`loop` field)
- Worker control (`max_workers`, `isolation`, `fail_mode`)
- Routing via `on_yes` / `on_partial` / `on_no`
- Reference `ParallelStateConfig` and `ParallelResult` as the schema types

### `docs/reference/API.md`

The `StateConfig` dataclass block is at `API.md:3773–3795`. The `loop:` field is at line 3791, `context_passthrough:` at line 3792, `agent:` at line 3793, and `tools:` at line 3794; the block closes at line 3795. (The issue was originally drafted before `agent` and `tools` were added, making the prior line numbers stale.)

1. Add `parallel` field after `tools` (before the closing ` ``` ` at line 3795):
   ```python
       parallel: ParallelStateConfig | None = None  # Fan-out: run sub-loop concurrently over items
   ```
2. After the alias note at line 3797 (before `#### EvaluateConfig` at line 3799), add new `ParallelStateConfig` and `ParallelResult` dataclass blocks documenting all fields with type signatures and descriptions.

### `CONTRIBUTING.md`

The `fsm/` directory tree at lines 231–243 lists 11 files. The last entry is `└── handoff_handler.py` at line 243. Insert `parallel_runner.py` before it, changing `└──` to `├──` for `handoff_handler.py`.

## Implementation Steps

1. Update `docs/ARCHITECTURE.md` — add `## FSM Loop Mode (ll-loop)` section with `parallel:` state type description
2. Update `docs/reference/API.md` — add `parallel` field to `StateConfig`, then `ParallelStateConfig` and `ParallelResult` blocks
3. Update `CONTRIBUTING.md` — insert `parallel_runner.py` into `fsm/` tree listing

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

4. Update `docs/reference/API.md:3651–3665` — add `little_loops.fsm.parallel_runner` row to the **Submodule Overview Table** (defer until FEAT-1075 merges; the module won't exist until then)
5. Update `docs/reference/API.md:3669–3686` — add `ParallelStateConfig` and `ParallelResult` to the **Quick Import block** listing importable FSM symbols

## Integration Map

### Files to Modify

| File | Insertion Point | What to Add |
|------|----------------|-------------|
| `docs/ARCHITECTURE.md` | After line 451 (before `## Extension Architecture`) | New `## FSM Loop Mode (ll-loop)` section with `parallel:` state type |
| `docs/reference/API.md` | After `tools` at line 3794 (before closing ` ``` ` at line 3795); before `#### EvaluateConfig` at line 3799 | `parallel` field inline; new `ParallelStateConfig` and `ParallelResult` class blocks |
| `CONTRIBUTING.md` | Line 242 (before `└── handoff_handler.py`) | `│   ├── parallel_runner.py` |

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`ParallelStateConfig` / `ParallelResult` do not yet exist** — `scripts/little_loops/fsm/schema.py` has no `parallel` field in `StateConfig` and no `ParallelStateConfig` or `ParallelResult` class. Zero mentions of "parallel" anywhere in `fsm/`. Write docs against the interface specified in this issue; verify against schema.py once FEAT-1074 merges.

**`parallel_runner.py` does not yet exist** — The actual `fsm/` files on disk are: `__init__.py`, `schema.py`, `executor.py`, `concurrency.py`, `evaluators.py`, `interpolation.py`, `validation.py`, `persistence.py`, `signal_detector.py`, `handoff_handler.py`, `runners.py`, `fragments.py`, `types.py`.

**`API.md` `StateConfig` block is pre-existing-stale** — The block at lines 3773–3795 is already missing `action_type`, `params`, `on_partial`, `on_blocked`, `max_retries`, `on_retry_exhausted`, and `extra_routes` relative to `schema.py:StateConfig`. **Scope decision**: this issue's task is to add `parallel` only; fixing the broader stale fields is out of scope here but should be tracked separately.

**`CONTRIBUTING.md` `fsm/` tree has broader discrepancies** — Beyond the missing `parallel_runner.py`, the tree also lists `compilers.py` (line 235) which does **not** exist on disk, and is missing `runners.py`, `types.py`, and `fragments.py` which **do** exist. The issue's task is to add `parallel_runner.py` only; the broader tree cleanup is out of scope.

**`docs/generalized-fsm-loop.md`** exists as a deep FSM reference doc. The new `## FSM Loop Mode (ll-loop)` section in `ARCHITECTURE.md` should cross-reference it rather than duplicate its content.

**Line numbers confirmed accurate (2026-04-12 re-verify)** — `docs/reference/API.md` `StateConfig` block is still at lines 3773–3795; `EvaluateConfig` starts at line 3799. Wiring step 4 Submodule Overview Table is at lines **3651–3666** (not 3651-3665 as originally stated). Wiring step 5 Quick Import block is at lines **3667–3687**; `ParallelStateConfig` and `ParallelResult` should be added under the `# Schema` comment line alongside `FSMLoop, StateConfig, EvaluateConfig, RouteConfig, LLMConfig`.

**`generalized-fsm-loop.md` cross-reference target** — The right section to link to from `ARCHITECTURE.md` is `## Universal FSM Schema` (line 222) and its `### Action Types` subsection (line 226). If/when `generalized-fsm-loop.md` is extended to document `parallel:`, it would go there; the `ARCHITECTURE.md` cross-reference should point to that doc section.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_create_extension_wiring.py` — existing wiring-verification pattern (reads real doc files from disk); new test class could assert `ParallelStateConfig`, `ParallelResult`, and `parallel_runner.py` appear in expected docs (optional; follow that file's pattern)
- **Runtime validators** (not tests, but relevant): `ll-verify-docs` scans `docs/ARCHITECTURE.md` and `CONTRIBUTING.md` for `commands`/`agents`/`skills` count patterns — ensure new FSM section text does not accidentally match `\d+ \w* (commands|agents|skills)` pattern; `ll-check-links` crawls all three modified files — all added cross-references to `docs/generalized-fsm-loop.md` will be treated as internal links and not fetched

### Read-only Dependencies

- `scripts/little_loops/fsm/schema.py` — `ParallelStateConfig` will be added by FEAT-1074 (may not exist yet; write docs against the specified interface)
- `scripts/little_loops/fsm/parallel_runner.py` — created by FEAT-1075/FEAT-1076 (may not exist yet)

### Similar Patterns

- Existing state type descriptions in `docs/ARCHITECTURE.md` for other modes
- `docs/reference/API.md:3777–3795` — `StateConfig` block format to follow

### Codebase Research Findings — API.md Exact Block Format

_Added by `/ll:refine-issue` — exact `@dataclass` blocks to write in `API.md`, following the `EvaluateConfig`/`RouteConfig` pattern (field + type annotation + inline `#` comment):_

**`ParallelStateConfig` block** (insert as a new `#### ParallelStateConfig` section after `#### EvaluateConfig` / `#### RouteConfig`):

```python
@dataclass
class ParallelStateConfig:
    items: str                                           # Interpolated expression → newline-delimited item list
    loop: str                                            # Sub-loop name (resolved via `.loops/<name>.yaml`)
    max_workers: int = 4                                 # Maximum concurrent workers
    isolation: Literal["worktree", "thread"] = "worktree"  # Worker isolation mode
    fail_mode: Literal["collect", "fail_fast"] = "collect"  # Error behavior: collect all results vs. stop on first failure
    context_passthrough: bool = False                    # Pass parent captured context into each worker's sub-loop
```

> **Mutual exclusions**: `parallel` is incompatible with `action`, `loop` (top-level sub-loop), and `next` in the same state.

**`ParallelResult` block** (insert immediately after `ParallelStateConfig` block as `#### ParallelResult`):

```python
@dataclass
class ParallelResult:
    succeeded: list[str]      # Items that reached terminal state "done"
    failed: list[str]         # Items that did not reach "done"
    all_captures: list[dict]  # Per-worker captured dicts, indexed by item order
    verdict: str              # "yes" (all succeeded), "no" (all failed), "partial" (mixed)
```

> Access results via `${captured.<state_name>.results}` in subsequent states.

**ARCHITECTURE.md YAML example** (model after `generalized-fsm-loop.md:191-219` sub-loop composition format — YAML block + key fields list):

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

### `ParallelStateConfig` Field Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `items` | `str` | required | Interpolated expression resolving to a newline-delimited list of items |
| `loop` | `str` | required | Name of the sub-loop to run per item (resolved via `.loops/<name>.yaml`) |
| `max_workers` | `int` | `4` | Maximum concurrent workers |
| `isolation` | `str` | `"worktree"` | Isolation mode: `"worktree"` or `"thread"` |
| `fail_mode` | `str` | `"collect"` | Error behavior: `"collect"` or `"fail_fast"` |
| `context_passthrough` | `bool` | `False` | Passes parent captured context into each worker's sub-loop initial context |

Mutual exclusions: `parallel` + `action`, `parallel` + `loop`, `parallel` + `next` are all invalid combinations.

### `ParallelResult` Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `succeeded` | `list[str]` | Items that reached terminal state named `"done"` |
| `failed` | `list[str]` | Items that did not reach `"done"` |
| `all_captures` | `list[dict]` | Per-worker `captured` dicts, indexed by item order |
| `verdict` | `str` | `"yes"` (all succeeded), `"no"` (all failed), `"partial"` (mixed) |

Routing conventions: `on_yes` / `on_partial` / `on_no`. Captures: `${captured.<state_name>.results}`.

## Dependencies

- FEAT-1074 (schema) and FEAT-1076 (runner) should be complete for exact line numbers; write against the specified interface if not yet merged

## Use Case

**Who**: Developer or contributor adding a `parallel:` state to an FSM loop YAML

**Context**: When configuring parallel fan-out or reading existing loop configs that use `parallel:`, and needing to know what fields are available, their defaults, and how routing and result capture work

**Goal**: Look up `ParallelStateConfig` and `ParallelResult` fields in the reference docs without reading source code

**Outcome**: Developer correctly configures `items`, `loop`, `max_workers`, `isolation`, `fail_mode`, and routing transitions; understands what `${captured.<state>.results}` returns

## Acceptance Criteria

- `docs/ARCHITECTURE.md` documents `parallel:` state type in a new FSM Loop Mode section
- `docs/reference/API.md` includes `parallel` field in `StateConfig` plus `ParallelStateConfig` and `ParallelResult` class blocks
- `CONTRIBUTING.md` lists `parallel_runner.py` in the `fsm/` directory tree

## Impact

- **Priority**: P2 — Parallel state is the primary new FSM feature; reference docs must ship with the implementation to unblock adopters
- **Effort**: Small — 3 documentation files, targeted insertions
- **Risk**: Very Low — documentation-only
- **Breaking Change**: No

## Labels

`fsm`, `parallel`, `docs`

---

## Session Log
- `/ll:confidence-check` - 2026-04-12T19:21:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/af507141-e237-44c4-86f4-c20c393e747e.jsonl`
- `/ll:refine-issue` - 2026-04-13T00:19:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/df842483-0396-4e4d-ad0e-01b546a41fd1.jsonl`
- `/ll:confidence-check` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/64ed8017-a10a-4a9e-9954-5d3beb6f9e8e.jsonl`
- `/ll:wire-issue` - 2026-04-13T00:13:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a631dce1-2f8a-4459-8742-f86265563643.jsonl`
- `/ll:refine-issue` - 2026-04-13T00:06:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e1f36fa8-ae70-432a-976e-5a3909abedde.jsonl`
- `/ll:format-issue` - 2026-04-13T00:02:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/170bc7ad-db01-4440-a01d-bd81fa955111.jsonl`
- `/ll:issue-size-review` - 2026-04-12T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/847acfcb-8aba-4124-8dc8-a98c7902e550.jsonl`

---

**Open** | Created: 2026-04-12 | Priority: P2
