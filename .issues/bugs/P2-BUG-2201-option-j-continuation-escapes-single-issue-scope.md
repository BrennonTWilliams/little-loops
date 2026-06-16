---
id: BUG-2201
title: Option J continuation escapes single-issue scope and processes backlog
type: BUG
status: done
priority: P2
decision_needed: false
captured_at: '2026-06-16T20:52:46Z'
completed_at: '2026-06-16T22:21:02Z'
discovered_date: '2026-06-16'
discovered_by: capture-issue
confidence_score: 92
outcome_confidence: 81
score_complexity: 19
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 20
---

# BUG-2201: Option J continuation escapes single-issue scope and processes backlog

## Summary

When an `ll-auto --only {id}` session inside `rn-implement` hits the context limit and triggers the Option J guillotine, the spawned continuation session has no scope constraint. It correctly finishes the interrupted issue but then freely picks up unrelated backlog issues and implements them — bypassing any queued loop that was waiting to process those issues.

## Current Behavior

- `rn-implement` runs `ll-auto --only ENH-2177` for a single issue
- The session exhausts its context window → Option J fires, spawning a fresh Claude session via `guillotine-prompt.md` + `/ll:resume`
- The continuation prompt (`issue_manager.py` run_dir path, ~line 340) adds a `sprint_framing` block only when `sprint_context is not None`
- For non-sprint single-issue runs, no scope constraint is emitted → the continuation is free to do anything
- In the observed incident, the continuation completed ENH-2177, then also implemented ENH-2197–2200 (which were queued in a separate `ll-loop run rn-implement ENH-2197,ENH-2198,ENH-2199,ENH-2200 -q`)

## Steps to Reproduce

1. Start `ll-loop run rn-implement` targeting a single issue (e.g., `ll-loop run rn-implement ENH-2177`)
2. Let the Claude session exhaust its context window — Option J fires and spawns a continuation session via `guillotine-prompt.md` + `/ll:resume`
3. Observe: the continuation session correctly finishes the original issue
4. Observe: the continuation session then picks up and implements additional backlog issues (e.g., ENH-2197–2200) without any scope constraint

## Expected Behavior

- The continuation prompt always includes a single-issue scope constraint when the original session was scoped to one issue
- After completing the interrupted issue, the continuation exits immediately without touching the backlog
- The queued loop wakes up and gracefully skips issues already marked `done`

## Root Cause

**`scripts/little_loops/issue_manager.py`** — `run_with_continuation()`, Option J run_dir path (~line 340):

```python
if sprint_context is not None:
    sprint_framing = (
        f"## Sprint Worker Context\n"
        f"You are a sprint worker. Process exactly ONE issue: "
        f"{sprint_context.issue_id}\n"
        ...
    )
```

The sprint framing (which enforces single-issue scope) is gated on `sprint_context is not None`. When invoked from the FSM loop via `ll-auto --only ENH-2177`, `sprint_context` is `None` even though `issue_path` is provided — so no constraint is emitted.

The same gap exists in **`scripts/little_loops/subprocess_utils.py`** — `assemble_guillotine_prompt()` — for the non-loop (non-run_dir) path, which also accepts `sprint_context` but has no `issue_id` fallback.

## Proposed Solution

Two changes, one issue:

### Fix A — Scope constraint in guillotine prompt (`issue_manager.py` + `subprocess_utils.py`)

**`issue_manager.py` run_dir path (~line 340):**
- When `sprint_context is None` but `issue_path is not None`, extract the issue ID from `issue_path` (parse the `id:` frontmatter field or derive from filename)
- Emit an equivalent scope block:
  ```
  ## Scope Constraint
  Complete exactly ONE issue: {issue_id}
  After completing this issue, exit immediately — do NOT process other issues.
  ```

**`subprocess_utils.py` `assemble_guillotine_prompt()`:**
- Add `issue_id: str | None = None` parameter
- When `sprint_context is None` but `issue_id` is provided, emit the same scope block

### Fix B — Pre-flight status check in `rn-implement.yaml`

Before the state that invokes `ll-auto --only {id}`, add a shell pre-check state:
- Read the issue's `status:` frontmatter via `ll-issues show {id} --field status` (or `grep`)
- If `done` or `cancelled`, route directly to `record_outcome` with outcome `IMPLEMENTED` (or `SKIPPED`)
- This makes the queued loop a true no-op for issues already completed out-of-band, regardless of whether Fix A holds

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` (~line 340): add single-issue scope constraint block when `sprint_context is None` and `issue_path is not None`
- `scripts/little_loops/subprocess_utils.py` — `assemble_guillotine_prompt()`: add `issue_id: str | None = None` parameter and emit scope block when `sprint_context` is absent
- `scripts/little_loops/loops/rn-implement.yaml` — add pre-flight status check state before the `ll-auto --only {id}` invocation

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/auto.py` — `main_auto()` (line 89, 101) — the `ll-auto` CLI entry point; parses `--only` into `only_ids` and passes to `AutoManager`; never creates a `sprint_context`, so every `ll-auto --only {id}` run reaches Option J with `sprint_context=None`
- `scripts/little_loops/issue_manager.py` — `AutoManager._process_issue()` (line 1320) → calls `process_issue_inplace()` (line 1343) without passing `sprint_context`; this is the direct upstream caller that leaves the constraint gap
- `scripts/little_loops/issue_manager.py` — `process_issue_inplace()` (line 545, call site lines 862–875) → calls `run_with_continuation(... issue_path=info.path, sprint_context=sprint_context)` where `sprint_context` is always `None` from the `ll-auto` path
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_with_continuation()` (lines 740–910) — separate copy of both J branches; always has a `sprint_context` (built from `SprintWorkerContext(issue_id=..., branch=...)` for every parallel worker), so not affected by this bug but should be reviewed for consistency

### Similar Patterns
- `scripts/little_loops/issue_manager.py:339–349` — `sprint_framing` block in `run_with_continuation()` (run_dir path); the new `elif issue_path is not None:` branch mirrors this exact structure
- `scripts/little_loops/subprocess_utils.py:222–232` — identical `sprint_context` guard in `assemble_guillotine_prompt()` (non-run_dir path); same `elif issue_id is not None:` extension needed here
- `scripts/little_loops/parallel/worker_pool.py:852–862` — third copy of the `sprint_framing` block in `WorkerPool._run_with_continuation()`; already guarded by `sprint_context` that is always set for parallel workers
- `scripts/little_loops/loops/autodev.yaml:299–322` — `implement_current` state: YAML pre-flight that resolves the issue path via `ll-issues path "$ID"` then `grep '^status:'` before calling `ll-auto --only`; Fix B follows this same pattern
- `scripts/little_loops/loops/oracles/implement-issue-chain.yaml:72–83` — `implement_issue` state: glob-based already-done skip (`ls .issues/completed/*$${ISSUE}*`) before `ll-auto --only`; simpler variant of the Fix B pattern

### Tests
- `scripts/tests/test_issue_manager.py` — `TestRunWithContinuation` (lines 1131–1580): all existing Option J tests; add regression test here verifying the guillotine file for a single-issue (`sprint_context=None`, `issue_path` set) contains "Process exactly ONE issue" / "exit immediately"
- `scripts/tests/test_subprocess_utils.py` — `TestAssembleGuillatinePrompt` (lines 1986–2085): all existing `assemble_guillotine_prompt` tests; add test verifying new `issue_id` parameter emits scope constraint when `sprint_context=None`
- `scripts/tests/test_worker_pool.py` — `TestRunWithContinuation` (lines 2337–2653): parallel worker tests; regression-test that worker-pool path is unaffected (sprint_context still takes precedence)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_rn_implement.py` — `TestRoutingStructure` class: three structural tests (`test_every_state_has_outgoing_edge`, `test_all_referenced_targets_exist`, `test_all_states_reachable_from_init`) that automatically BFS-validate every state and routing target in the YAML; they will exercise the new pre-flight state and **fail if `record_outcome` is used as a routing target** (see Configuration note below)
- `scripts/tests/test_rn_implement.py` — new `TestPreFlightStatusCheck` class needed: test state exists, action references `ll-issues show` or `status`, `on_yes` routes to `skip_issue` or `dequeue_next`, `on_no` routes to `run_remediation`, `on_error` fails open to `run_remediation` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — new entry needed for BUG-2201 fix (scope constraint gap in Option J guillotine for single-issue `ll-auto --only` runs)

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- **Routing target correctness**: Implementation Step 3 and Acceptance Criteria both reference routing to `record_outcome` — this state does NOT exist in `rn-implement.yaml`. Existing terminal states are `done`, `failed`, `report`, and issue-routing states (`skip_issue`, `mark_deferred`, `dequeue_next`). The pre-flight `on_yes` route must target an existing state (`skip_issue` or `dequeue_next`), or a new `record_outcome` state must be added to the YAML. `test_all_referenced_targets_exist` in `TestRoutingStructure` will catch this at test time. [Agent 2 finding]

## Implementation Steps

1. **`issue_manager.py:339`** — In `run_with_continuation()` Option J run_dir branch, add `elif issue_path is not None:` after the `if sprint_context is not None:` guard (line 340); extract `issue_id` via `re.search(r'(BUG|FEAT|ENH|EPIC)-\d+', issue_path.name).group()` (pattern from `issue_parser.py:644`); emit `## Scope Constraint` block matching the `sprint_framing` text; pass it into `guillotine_file.write_text()`
2. **`subprocess_utils.py:157`** — Add `issue_id: str | None = None` to `assemble_guillotine_prompt()` signature; in the `sprint_context` guard (lines 222–232), add `elif issue_id is not None:` branch that prepends the `## Scope Constraint` block; update the call site at `issue_manager.py:374–385` to pass `issue_id` derived from `issue_path` when set
3. **`rn-implement.yaml`** — Insert a pre-flight shell state before the `ll-auto --only {id}` invocation; use the `autodev.yaml:299–322` pattern: resolve the path with `ll-issues path "$ID"` then read status with `ll-issues show "$ID" --json | jq -r '.status // "open"'` (the `--field` flag **does not exist** — use `--json | jq -r '.status'` as in `rn-remediate.yaml:212–228`); route `done`/`cancelled` to `skip_issue` or `dequeue_next` (`record_outcome` does not exist in this YAML)
4. **`scripts/tests/test_issue_manager.py`** — Add test to `TestRunWithContinuation` (lines 1131–1580): pass `issue_path=issue_file`, `sprint_context=None`, `run_dir=str(run_dir)`; assert `guillotine_file.read_text()` contains the target issue ID and `"exactly ONE issue"`
5. **`scripts/tests/test_subprocess_utils.py`** — Add test to `TestAssembleGuillatinePrompt` (lines 1986–2085): call `assemble_guillotine_prompt(..., issue_id="ENH-2177", sprint_context=None)`; assert prompt contains issue ID and `"exactly ONE issue"`
6. Run `python -m pytest scripts/tests/test_issue_manager.py scripts/tests/test_subprocess_utils.py -v` to confirm no regressions in existing Option J tests

## Motivation

In the observed incident, a single continuation session implemented four issues that were reserved for a queued loop, causing the queued loop to become a no-op before it ever ran. Fix A removes the root cause; Fix B adds a cheap defensive guard so future out-of-band completions degrade gracefully.

## Acceptance Criteria

- [x] Option J continuation for a single-issue `ll-auto --only {id}` run includes the scope constraint in `guillotine-prompt.md`
- [x] `assemble_guillotine_prompt()` accepts and emits `issue_id` scope when `sprint_context` is absent
- [x] `rn-implement` skips an issue at the pre-flight state if its status is already `done`/`cancelled`, routing to `skip_issue` or `dequeue_next` without calling `ll-auto` (`record_outcome` does not exist in this YAML)
- [x] Existing tests for Option J continuation pass
- [x] New test: Option J prompt for a single-issue run contains "Process exactly ONE issue"

## Impact

- **Priority**: P2 — Continuation sessions can silently process and complete issues reserved for other queued loops, causing those loops to become no-ops and breaking expected execution order
- **Effort**: Small — Two focused additive changes in `issue_manager.py` and `subprocess_utils.py`, plus one new pre-flight state in `rn-implement.yaml`
- **Risk**: Low — Additive-only changes; new scope-constraint block activates only when `sprint_context is None` and `issue_path` is set (the previously uncovered path)
- **Breaking Change**: No

## Labels

`automation`, `continuation`, `scope-guard`, `guillotine`, `ll-auto`, `rn-implement`

## Status

**Open** | Created: 2026-06-16 | Priority: P2

## Session Log
- `/ll:ready-issue` - 2026-06-16T22:04:48 - `d9e5022e-589d-40ea-ba22-5785852c79d1.jsonl`
- `/ll:confidence-check` - 2026-06-16T22:00:00 - `f0bde4d5-c4d6-4c0f-8add-66f7b71dd142.jsonl`
- `/ll:wire-issue` - 2026-06-16T21:19:21 - `deb1b742-9996-4a29-8df2-2e4717ac28da.jsonl`
- `/ll:refine-issue` - 2026-06-16T21:10:27 - `293ff18e-2b7d-4ebc-a77e-84c8686f60ca.jsonl`
- `/ll:format-issue` - 2026-06-16T20:56:37 - `34d3fd47-b826-43e9-9c88-3a6f52440424.jsonl`
- `/ll:capture-issue` - 2026-06-16T20:52:46Z
