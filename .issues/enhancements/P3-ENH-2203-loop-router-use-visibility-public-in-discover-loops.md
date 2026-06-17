---
id: ENH-2203
title: "Wire --visibility public into loop-router.yaml discover_loops state"
priority: P3
status: open
type: ENH
relates_to: [ENH-2198, EPIC-2196]
---

## Summary

`loop-router.yaml`'s `discover_loops` state calls `ll-loop list --json` without `--visibility public`, so the dispatch catalog it builds includes `internal` and `example` loops alongside routable `public` ones. ENH-2198 shipped the `--visibility` flag; this issue wires it into the router.

## Motivation

This enhancement ensures the loop-router's dispatch catalog contains only routable (`public`) loops, preventing `internal` sub-loops and `example` reference loops from being incorrectly offered as dispatch targets. The Hermes `ll_route` tool depends on this catalog — without the filter a goal could be routed to a non-dispatchable internal loop, causing silent routing failures.

## Current Behavior

`discover_loops` (loop-router.yaml line 28):
```shell
ll-loop list --json 2>/dev/null | python3 -c "..."
```
The Python inline filter excludes a hardcoded blocklist (`loop-router`, `loop-composer`, `loop-composer-adaptive`, `goal-cluster`, `rn-build`) but passes all other loops — including `internal` and `example` visibility loops — into the catalog that the classifier and dispatcher act on.

## Expected Behavior

```shell
ll-loop list --json --visibility public 2>/dev/null | python3 -c "..."
```
Only loops with `visibility: public` (or no explicit visibility, resolved as public by `is_runnable_loop()`) appear in the catalog. Internal sub-loops and example reference loops are never presented to the classifier or dispatched.

## Acceptance Criteria

- [ ] `discover_loops` calls `ll-loop list --json --visibility public`
- [ ] The hardcoded blocklist can be trimmed — loops previously excluded because they are `internal` no longer need explicit exclusion
- [ ] `ll-loop run loop-router` with a goal that would otherwise match an `internal` loop routes to the best `public` alternative instead
- [ ] No regression on existing `ll-loop run loop-router` invocations

## Scope Boundaries

- **In scope**: Adding `--visibility public` to the `discover_loops` shell action; auditing and removing blocklist entries that are redundant now that `internal` loops are filtered at the CLI level
- **Out of scope**: Changes to `is_runnable_loop()` logic or the `--visibility` flag itself (shipped in ENH-2198); adding new visibility categories; changes to classifier or dispatcher routing logic

## Proposed Solution

Single-line change in `scripts/little_loops/loops/loop-router.yaml` at the `discover_loops` state:

```yaml
  discover_loops:
    action_type: shell
    action: |
      ll-loop list --json --visibility public 2>/dev/null | python3 -c "
      ...
      "
```

After adding `--visibility public`, audit the hardcoded `excludes` set: any loop that was excluded solely because it is `internal` (not because it causes routing loops) can be removed from the blocklist.

## Implementation Steps

1. Edit `discover_loops` state in `scripts/little_loops/loops/loop-router.yaml` — add `--visibility public` to the `ll-loop list --json` call
2. Audit the hardcoded `excludes` set; remove entries excluded solely because they are `internal` (not routing-loop-prevention entries)
3. Run `ll-loop run loop-router` with a goal that previously matched an internal loop; verify it routes to a public alternative
4. Confirm no regression on existing public loop dispatch with a standard test goal

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Edit `discover_loops` fragment in `scripts/little_loops/loops/lib/composer.yaml` (line 29) — add `--visibility public` to the `ll-loop list --json` call (mirrors Step 1; this file is in Files to Modify but was absent from the Steps)
6. Add `test_discover_loops_uses_visibility_public` to `scripts/tests/test_loop_router.py::TestLoopRouterStates` — assert `"--visibility public" in state.get("action", "")` with message `"discover_loops action must include '--visibility public' flag on ll-loop list"`
7. Add `test_discover_loops_fragment_uses_visibility_public` to `scripts/tests/test_loop_composer.py::TestComposerLibFragment` — assert `"--visibility public" in lib_data["fragments"]["discover_loops"].get("action", "")` with analogous message

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/loop-router.yaml` — `discover_loops` state shell action (line 28)
- `scripts/little_loops/loops/lib/composer.yaml` — `discover_loops` fragment shell action (line 29) — structurally identical call; update for consistency

### Dependent Files (Callers/Importers)
- `ll-loop list` CLI — provides `--visibility` flag consumed here (ENH-2198)
- Hermes `ll_route` tool — calls `ll-loop run loop-router` and depends on catalog correctness

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/loop-composer.yaml` — inherits `discover_loops` fragment from `lib/composer.yaml`; indirectly picks up the `lib/composer.yaml` change
- `scripts/little_loops/loops/loop-composer-adaptive.yaml` — same fragment inheritance path

### Similar Patterns
- Other `ll-loop list` usages in loop YAML files that may benefit from `--visibility public`

### Tests
- `scripts/tests/test_loop_router.py` — `TestLoopRouterStates.test_discover_loops_is_shell` (line 102) asserts `"ll-loop list"` in the shell action (will still pass after adding `--visibility public`); `test_discover_loops_excludes_self` (line 110) asserts `"loop-router"` appears in the blocklist. Neither test currently asserts `"--visibility public"` is present — a new assertion is needed here.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_loop_router.py` — NEW: add `test_discover_loops_uses_visibility_public` in `TestLoopRouterStates` asserting `"--visibility public" in state.get("action", "")`; follow single-flag pattern from `test_builtin_loops.py` (e.g. `test_breakdown_issue_action_contains_auto`)
- `scripts/tests/test_loop_composer.py` — NEW: add `test_discover_loops_fragment_uses_visibility_public` in `TestComposerLibFragment` asserting `"--visibility public" in lib_data["fragments"]["discover_loops"].get("action", "")`; existing `test_discover_loops_fragment_excludes_*` tests all survive (they check blocklist strings only, none assert the absence of the flag)
- `scripts/tests/test_goal_cluster.py` — `TestGoalClusterRouterComposerGuard.test_loop_router_excludes_goal_cluster()` reads `discover_loops` action from `loop-router.yaml`; survives unchanged (checks `"goal-cluster" in action` only)
- `scripts/tests/test_rn_build.py` — `test_discover_loops_fragment_excludes_rn_build()` reads `lib/composer.yaml` fragment; survives unchanged (checks `"rn-build" in action` only)

### Documentation
- N/A — internal loop configuration change

### Configuration
- N/A — no config file changes required

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Blocklist trimming caveat (critical):** Implementation Step 2 and Acceptance Criteria #2 say "the hardcoded blocklist can be trimmed." This is only true for loops annotated `visibility: internal`. The five currently hardcoded names (`loop-router`, `loop-composer`, `loop-composer-adaptive`, `goal-cluster`, `rn-build`) are **not** annotated `visibility: internal` in their YAML files — they all default to `public`. After adding `--visibility public`, `ll-loop list --json --visibility public` will still include them in its output; the manual `excludes` set in the shell action must remain for all five. Trimming requires first adding `visibility: internal` to those YAML files (separate step, out of scope per Scope Boundaries).

**Sister file in scope:** `scripts/little_loops/loops/lib/composer.yaml` (line 29) contains the structurally identical `ll-loop list --json` call with the same five-entry hardcoded `excludes` set. This fragment is inherited by `loop-composer.yaml` and `loop-composer-adaptive.yaml`. For consistency, `lib/composer.yaml` line 29 should receive the same `--visibility public` addition. The Integration Map should include this file.

**Functional impact:** The current invocation (`ll-loop list --json`, no flag) and the proposed invocation (`ll-loop list --json --visibility public`) produce **identical output today**, because `cmd_list()` in `scripts/little_loops/cli/loop/info.py` applies the same `visibility == "public"` filter in both the explicit-flag branch and the default/no-flag branch. The change makes intent explicit and forward-proofs the call against future default-behavior changes, but does not alter the catalog produced today. Acceptance Criteria #3 ("verify it routes to a public alternative") cannot be tested by the `--visibility public` change alone — it requires a loop that lacks `visibility: internal` to first have that annotation added so it is suppressed.

**Exact location:** `scripts/little_loops/loops/loop-router.yaml` line 28 — the `ll-loop list --json` shell invocation is the single character-level target for Step 1.

## Impact

- **Priority**: P3 — correctness issue for Hermes `ll_route` tool; low blast radius otherwise since `internal` loops typically also appear in the blocklist today
- **Effort**: XS — one-line change + minor blocklist cleanup
- **Risk**: Low — additive filter; no behavior change for public loops

## Labels

`enhancement`, `loops`, `routing`, `loop-router`

## Status

Open


## Session Log
- `/ll:wire-issue` - 2026-06-17T17:59:03 - `f2b3ef53-2acc-45d4-ad59-26197633fe46.jsonl`
- `/ll:refine-issue` - 2026-06-17T17:50:04 - `caf9feb9-9f53-43b2-8ff0-6d559aabdc0f.jsonl`
- `/ll:format-issue` - 2026-06-17T17:43:15 - `de66b4ba-9ea7-4d59-b95d-7249a74b546e.jsonl`
