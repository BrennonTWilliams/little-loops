---
id: ENH-2319
title: Make learning-test target detection just-in-time and consistent across runners
type: ENH
priority: P2
status: open
captured_at: '2026-06-26T22:27:56Z'
discovered_date: '2026-06-26'
discovered_by: capture-issue
relates_to:
- FEAT-1282
- ENH-2209
- ENH-2210
- ENH-2219
- ENH-2242
- BUG-2320
labels:
- captured
- learning-tests
- explore-api
- automation
- runners
confidence_score: 98
outcome_confidence: 82
score_complexity: 17
score_test_coverage: 22
score_ambiguity: 23
score_change_surface: 20
---

# ENH-2319: Make learning-test target detection just-in-time and consistent across runners

## Summary

`/ll:explore-api` auto-invocation is solid *when* an issue's
`learning_tests_required` frontmatter list is populated — but that field is
filled only **eagerly**, by `refine-issue` / `wire-issue` / `scope-epic`. An
issue that goes `capture → implement` (skipping refinement) has an empty field,
so every gate finds zero targets and passes silently: the "need" for an API
proof is never detected, and `explore-api` never fires. Detection should be
**just-in-time** at the gate, derived from the issue text, not contingent on
whether a refine step happened to run first. This issue introduces a shared
`resolve_learning_targets()` helper and threads it through the two runner paths
that lack consistent just-in-time behavior (`ll-auto`, `ll-sprint`). The third
runner (`ll-parallel`) is fixed separately in BUG-2320.

## Current Behavior

Target detection is field-dependent and the three runners disagree on the
empty-field case:

- **`ll-auto` has no learning gate at all.** `scripts/little_loops/cli/auto.py`
  (`main_auto`) and the `AutoManager` per-issue flow (ready-issue →
  `/ll:manage-issue` → verify) contain zero references to learning tests. Its
  only coverage is whatever `ready-issue` does, which is itself **field-only**
  (`commands/ready-issue.md` acts only "if `learning_tests_required` exists in
  frontmatter"). An unrefined issue under `ll-auto` reaches implementation with
  no assumption firewall.
- **`ll-sprint` already extracts just-in-time, but via an inline crutch.**
  `_run_learning_gate_preflight` (`scripts/little_loops/cli/sprint/run.py:164`)
  does `targets = info.learning_tests_required` when populated, else falls back
  to `extract_learning_targets(info.path.read_text())` — guarded by a
  `TODO(stale-after-ENH-2209): remove fallback once all active sprint issues
  have been re-refined`. That TODO frames just-in-time extraction as a temporary
  migration aid rather than the permanent correctness guarantee it should be.
- **`extract_learning_targets()`** already exists
  (`scripts/little_loops/learning_tests/extractor.py:69`) and is the LLM-based
  extractor behind ENH-2209's auto-population. The just-in-time capability is
  present; it is simply not wired everywhere.

Net effect: defense-in-depth silently degrades to nothing for any issue that
reaches a runner without having been refined.

## Expected Behavior

- A single shared helper resolves an issue's learning targets the same way
  everywhere: return `learning_tests_required` when populated, else extract them
  from the issue text just-in-time.
- `ll-auto` runs a per-issue learning gate between the ready and implement
  phases, at parity with `ll-parallel`/`ll-sprint`, with a `--skip-learning-gate`
  bypass flag (matching sprint's existing flag).
- `ll-sprint` resolves targets through the shared helper; the inline fallback and
  its `TODO(stale-after-ENH-2209)` are removed — just-in-time extraction is
  permanent, not a migration crutch.
- Whether or not an issue was refined, a runner detects unproven external-API
  assumptions from the issue text and routes them through `/ll:explore-api`
  before implementation begins.

## Success Metrics

- `resolve_learning_targets()` unit tests pass: 3 cases (populated field
  short-circuits extraction; empty field triggers JIT extraction; `OSError` → `[]`)
- `ll-auto` per-issue learning gate fires for an unrefined issue whose text
  contains API assumptions, and skips implementation when the gate returns `blocked`
- `--skip-learning-gate` flag in `ll-auto` correctly bypasses the gate
- `ll-sprint` existing learning gate tests pass unchanged (regression parity)
- All three runners produce identical gate behavior for the same unrefined issue

## Motivation

The whole learning-test system exists to stop agents from writing production
code against unverified API assumptions. That guarantee currently has a hole the
size of "any issue you didn't refine first" — which includes the common
`capture-issue → ll-auto` path. Making detection just-in-time closes the hole at
its root instead of relying on every issue passing through refinement, and
collapsing three divergent code paths onto one helper removes the per-runner
drift that produced the inconsistency in the first place.

## Proposed Solution

Add `resolve_learning_targets(issue, *, llm_call=None)` near
`extract_learning_targets` in `scripts/little_loops/learning_tests/extractor.py`
(or a small `gate.py`-adjacent module if a cleaner home exists):

- If `issue.learning_tests_required` is a non-empty list, return it.
- Otherwise read the issue file text and return
  `extract_learning_targets(text, llm_call=llm_call)`.
- Tolerate `OSError` (unreadable file) by returning `[]`, matching the current
  sprint fallback's behavior.

Then:

1. **`ll-auto`**: in the `AutoManager` per-issue flow, after the ready verdict
   and before `/ll:manage-issue`, resolve targets via the helper; when non-empty
   and `learning_tests.enabled` and not `--skip-learning-gate`, run the existing
   `proof-first-task` loop (`ll-loop run proof-first-task --context
   issue_file=<path>`) exactly as `ll-parallel` does, and skip implementation if
   the gate returns `blocked`.
2. **`ll-sprint`**: replace the inline `learning_tests_required`-or-extract block
   in `_run_learning_gate_preflight` with a call to the shared helper; delete the
   `TODO(stale-after-ENH-2209)`.

Prefer factoring the gate-invocation itself (the `ll-loop run proof-first-task`
subprocess + result classification) into a shared function so `ll-auto`,
`ll-parallel` (BUG-2320), and `ll-sprint` call one code path, not three.

## API/Interface

New functions introduced in `scripts/little_loops/learning_tests/extractor.py`
(or an adjacent `gate.py` module):

```python
def resolve_learning_targets(
    issue: IssueInfo,
    *,
    llm_call: Callable | None = None,
) -> list[str]:
    """Return learning-test targets for an issue.

    Returns `issue.learning_tests_required` when non-empty (field-first).
    Falls back to JIT extraction from issue text via `extract_learning_targets`.
    Returns [] on OSError (unreadable issue file).
    """
```

Optional shared gate-runner (preferred — collapses three divergent subprocess paths):

```python
def run_learning_gate_for_issue(
    issue_path: Path,
    *,
    skip: bool = False,
) -> Literal["passed", "blocked", "skipped"]:
    """Invoke proof-first-task loop for an issue and return the gate verdict.

    `skip=True` short-circuits to "skipped" (honours --skip-learning-gate).
    """
```

CLI change: add `--skip-learning-gate` flag to `ll-auto` (mirrors sprint's existing flag).

## Integration Map

- **Files to modify**:
  - `scripts/little_loops/learning_tests/extractor.py` — add
    `resolve_learning_targets()`.
  - `scripts/little_loops/learning_tests/gate.py` — add
    `run_learning_gate_for_issue()` shared subprocess wrapper (currently holds
    staleness utilities `is_record_stale`, `format_nudge_message`; preferred
    home per Codebase Research Findings).
  - `scripts/little_loops/cli/auto.py` and/or
    `scripts/little_loops/issue_manager.py` (`AutoManager`) — add the per-issue
    gate + `--skip-learning-gate` arg (`scripts/little_loops/cli_args.py`).
  - `scripts/little_loops/cli/sprint/run.py:164` — route through the helper,
    drop the TODO crutch.
- **Dependent / sibling**:
  - `scripts/little_loops/parallel/worker_pool.py:63`
    (`_run_per_worktree_proof_first_gate`) — BUG-2320 migrates it onto the same
    helper; coordinate so both land on one shared gate-runner.
- **Loops**: `proof-first-task`, `assumption-firewall`, `ready-to-implement-gate`
  (`scripts/little_loops/loops/`) — consumed unchanged.
- **Config**: reuses `learning_tests.enabled`; no new config keys.

### Tests

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_learning_tests_extractor.py` — existing file covers
  `TestExtractLearningTargets`; add new `TestResolveLearningTargets` class
  with 3 test cases: populated `learning_tests_required` field short-circuits
  extraction (returns field value without calling `extract_learning_targets`);
  `None` field triggers JIT extraction via `extract_learning_targets`; `OSError`
  on file read → returns `[]`. Follow `_make_llm()` factory pattern in that file.
  [new tests to write]
- `scripts/tests/test_issue_manager.py` — existing file has `TestDecisionNeededGate`
  pattern (line 3466) to follow; add new `TestAutoManagerLearningGate` class for
  ll-auto gate path: blocked gate verdict → skip implement phase; `--skip-learning-gate`
  → bypass gate and proceed to implement; gate not invoked when `learning_tests.enabled`
  is false. Subprocess mock path: `"little_loops.learning_tests.gate.subprocess.run"`
  (since `run_learning_gate_for_issue` lives in `gate.py` — the subprocess call is
  inside that function, not inside `issue_manager.py`). For `blocked` state simulation,
  write `.loops/.running/proof-first-task.state.json` with
  `{"current_state": "blocked", "status": "completed"}` in `tmp_path` (project root,
  not a worktree path) — mirrors the exact pattern in `TestPerWorktreeProofFirstGate`.
  [new tests to write]
- `scripts/tests/test_sprint_integration.py:TestSprintPreflightGate` — existing
  tests for `_run_learning_gate_preflight` (line 1932); those that mock or assert
  the inline `extract_learning_targets` fallback path (the `TODO(stale-after-ENH-2209)`
  block at sprint/run.py:196–204) will break when the block is replaced by the shared
  helper call; update to mock `resolve_learning_targets` instead of
  `extract_learning_targets` directly.
  [existing tests to update]
- `scripts/tests/test_worker_pool.py:TestPerWorktreeProofFirstGate` — **BUG-2320
  coordination**: tests `test_gate_skipped_when_no_learning_tests_required` and
  `test_gate_resolves_targets_jit_when_field_none` currently patch
  `"little_loops.learning_tests.extractor.extract_learning_targets"` directly from
  the worker pool; when BUG-2320 migrates `_run_per_worktree_proof_first_gate` to
  call `resolve_learning_targets()`, those patch paths will stop intercepting and
  `mock_extract.assert_called_once()` will fail. Coordinate with BUG-2320 to update
  these patches when that PR lands.
  [existing tests to update — owned by BUG-2320, flag the dependency]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/API.md` — `main_auto()` entry (line 3346) is currently a stub
  ("Entry point for ll-auto command"); update to document the new
  `--skip-learning-gate` parameter matching the `skip_learning_gate` docs under
  `create_parallel_config` (line 323). Also add `resolve_learning_targets` and
  `run_learning_gate_for_issue` to the `little_loops.learning_tests` section
  (line 5540). [file to modify]
- `.claude/CLAUDE.md` — `ll-auto` entry (line 220) currently reads "Process all
  backlog issues sequentially in priority order" with no flags listed; update to
  mention `--skip-learning-gate` bypass flag, matching the pattern of `ll-init`
  which lists `--yes`, `--dry-run`, `--plan`/`apply`, `--hosts`. [file to modify]
- `docs/guides/LEARNING_TESTS_GUIDE.md` — line 308 explicitly states "ll-auto has
  no learning gate at all" — this claim becomes false after ENH-2319 lands; update
  to reflect that all three runners now have JIT detection via the shared helper.
  [file to modify]
- `docs/guides/SPRINT_GUIDE.md` — line 29 lists `ll-auto` as "Sequential, unordered
  queue; simplest setup, no dependencies needed" without mentioning learning gate;
  line 208 shows `--skip-learning-gate` for sprint; add equivalent `ll-auto` example.
  [file to modify — advisory]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`add_skip_learning_gate_arg()` already exists — no new arg needed:**
- `scripts/little_loops/cli_args.py` already has `add_skip_learning_gate_arg(parser)`.
  Sprint (`cli/sprint/__init__.py:137`) and parallel (`cli/parallel.py:162`) already call it.
  Implementation Step 3 is: import and call the existing function in `cli/auto.py`, not create one.

**`_read_loop_final_state()` is needed for correct classification:**
- `scripts/little_loops/parallel/worker_pool.py:45` — private helper reads
  `<cwd>/.loops/.running/<loop>.state.json` to distinguish `"blocked"` from `"done"` exit states.
  Since `proof-first-task` exits 0 for all terminal states, exit-code alone is insufficient.
  For ll-auto (no worktree), `cwd` is the project root. Either extract this helper to
  `learning_tests/gate.py` as part of the shared `run_learning_gate_for_issue()`, or
  re-implement inline. Extracting is preferred to avoid a third copy.

**`IssueInfo.learning_tests_required` sentinel: `None` vs `[]`:**
- `scripts/little_loops/issue_parser.py:271` — field is `list[str] | None = None`.
  `None` means "not yet populated" (triggers JIT extraction).
  `[]` is an empty list meaning "proven empty / no external deps" — must NOT trigger JIT.
  The `resolve_learning_targets()` condition must be `if issue.learning_tests_required is not None`
  (not a truthiness check), matching the existing inline blocks in sprint and parallel.

**`gate.py` home for `run_learning_gate_for_issue()`:**
- `scripts/little_loops/learning_tests/gate.py` exists but currently holds only staleness
  utilities (`is_record_stale`, `format_nudge_message`). It is the cleanest home for the
  shared `run_learning_gate_for_issue()` subprocess wrapper.

**Insertion point in `process_issue_inplace()`:**
- `scripts/little_loops/issue_manager.py:827` — the decision gate (`decide-issue`) lives here,
  between Phase 1 (`ready-issue`) and Phase 2 (`manage-issue`). The learning gate should be
  inserted immediately after the decision gate (if any) and before Phase 2.
  The sequence becomes: `ready-issue` → `decide-issue` (if decision_needed) →
  **`run_learning_gate_for_issue()`** (new) → `manage-issue`.

**Test class anchors to follow:**
- `scripts/tests/test_sprint_integration.py:TestSprintPreflightGate` (line 1932) — sprint gate
  tests; use `_make_issue_info()` factory (line 1911) and `lt_enabled_config` fixture (line 1891)
  as templates for ll-auto gate tests.
- `scripts/tests/test_worker_pool.py:TestPerWorktreeProofFirstGate` (line 2992) — parallel gate
  tests; same factory pattern as `_make_issue_info()` but as instance method.
- Extractor mock path: `"little_loops.learning_tests.extractor.extract_learning_targets"`.
- Subprocess mock path for auto tests: `"little_loops.issue_manager.subprocess.run"` (or wherever
  `run_learning_gate_for_issue` is imported from in that module).

**Duplicate JIT block to collapse (verbatim, for reference):**
- Sprint: `scripts/little_loops/cli/sprint/run.py:196–204` (with `TODO(stale-after-ENH-2209)`)
- Parallel: `scripts/little_loops/parallel/worker_pool.py:83–91` (with comment referencing ENH-2319)
  Both blocks are identical — `resolve_learning_targets()` replaces both.

## Implementation Steps

1. Add `resolve_learning_targets()` with unit tests (field short-circuit,
   extraction fallback, `OSError` → `[]`).
2. (Optional but preferred) Factor a shared `run_learning_gate_for_issue()` that
   wraps the `proof-first-task` subprocess + result classification; place in
   `scripts/little_loops/learning_tests/gate.py` (preferred home per Codebase
   Research Findings; add `_read_loop_final_state` extraction here too).
3. Wire the gate into the `ll-auto` per-issue flow between ready and implement;
   add `--skip-learning-gate` by calling `add_skip_learning_gate_arg()` in `cli/auto.py`.
4. Repoint `ll-sprint`'s `_run_learning_gate_preflight` onto the shared helper;
   remove the `TODO(stale-after-ENH-2209)`.
5. Tests for the `ll-auto` gate path (add `TestAutoManagerLearningGate` to
   `test_issue_manager.py`); update sprint gate tests (`TestSprintPreflightGate`)
   for changed mock target; update `ll-auto` docs/CLI help.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `scripts/tests/test_learning_tests_extractor.py` — add `TestResolveLearningTargets`
   class with 3 unit tests for `resolve_learning_targets`.
7. Update `docs/reference/API.md` — add `--skip-learning-gate` to `main_auto()` entry;
   add `resolve_learning_targets` and `run_learning_gate_for_issue` under `little_loops.learning_tests` section.
8. Update `.claude/CLAUDE.md` — add `--skip-learning-gate` to the `ll-auto` entry (line 220).
9. Update `docs/guides/LEARNING_TESTS_GUIDE.md` — revise line 308 ("ll-auto has no
   learning gate at all") to reflect the new parity across all three runners.
10. Update `docs/guides/SPRINT_GUIDE.md` — add `ll-auto --skip-learning-gate` example
    alongside the existing sprint example at line 208.

## Scope Boundaries

- **Out of scope**: Migrating `ll-parallel`'s `_run_per_worktree_proof_first_gate`
  onto the shared helper — tracked separately in BUG-2320 to keep this PR focused.
- **Out of scope**: Changes to `proof-first-task`, `assumption-firewall`, or
  `ready-to-implement-gate` loops — consumed unchanged.
- **Out of scope**: Backfilling `learning_tests_required` on existing unrefined
  issues — JIT extraction handles them at runtime without backfill.
- **Out of scope**: Changes to `ready-issue` gate logic — that gate remains field-only.
- **Out of scope**: New config keys — this reuses `learning_tests.enabled`.

## Impact

- **Priority**: P2 — closes a silent hole in the learning-test guarantee for the
  common `capture-issue → ll-auto` path; blocked by no other open work.
- **Effort**: Small — `resolve_learning_targets()` is ~15 LOC; gate wiring in
  `ll-auto` follows the pattern already in `ll-sprint`; sprint change is a
  simplification (net removal of a TODO crutch).
- **Risk**: Low — JIT extraction already runs in sprint today; this generalizes a
  proven path rather than introducing a new mechanism.
- **Breaking Change**: No — `--skip-learning-gate` provides an opt-out for callers
  that cannot tolerate the gate pause; sprint behavior is unchanged in outcome.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `.claude/CLAUDE.md` (CLI Tools, `ll-learning-tests`) | Registry + gate overview |
| `skills/explore-api/SKILL.md` | Four-phase proof lifecycle invoked at the gate |
| `docs/reference/API.md` | `little_loops.learning_tests` module reference |

## Labels

- captured
- learning-tests
- automation

## Session Log
- `/ll:confidence-check` - 2026-06-26T22:00:00Z - `7a5637ae-9124-4731-93ea-c7fd3f704c74.jsonl`
- `/ll:confidence-check` - 2026-06-26T00:00:00Z - `0ed4e422-dbd2-4b65-8f8d-67a06e3ee290.jsonl`
- `/ll:wire-issue` - 2026-06-27T04:32:02 - `3b7d4f6a-f81f-49e3-945a-7a65004e0fa5.jsonl`
- `/ll:refine-issue` - 2026-06-27T04:23:56 - `b6aa1e1f-003f-4499-8b9c-5f36a757715d.jsonl`
- `/ll:format-issue` - 2026-06-26T22:33:10 - `a4d7e1fc-3146-4ce2-8076-73b85d7fcb8e.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:27:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`

---

## Status

**Open** | Created: 2026-06-26 | Priority: P2
