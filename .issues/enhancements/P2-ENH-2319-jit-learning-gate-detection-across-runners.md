---
id: ENH-2319
title: 'Make learning-test target detection just-in-time and consistent across runners'
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
- **Tests**: `scripts/tests/` — add coverage for `resolve_learning_targets`
  (populated field short-circuits extraction; empty field triggers extraction;
  `OSError` → `[]`) and for the `ll-auto` gate (blocked → skip implement,
  `--skip-learning-gate` → bypass).
- **Config**: reuses `learning_tests.enabled`; no new config keys.

## Implementation Steps

1. Add `resolve_learning_targets()` with unit tests (field short-circuit,
   extraction fallback, `OSError` → `[]`).
2. (Optional but preferred) Factor a shared `run_learning_gate_for_issue()` that
   wraps the `proof-first-task` subprocess + result classification.
3. Wire the gate into the `ll-auto` per-issue flow between ready and implement;
   add `--skip-learning-gate`.
4. Repoint `ll-sprint`'s `_run_learning_gate_preflight` onto the shared helper;
   remove the `TODO(stale-after-ENH-2209)`.
5. Tests for the `ll-auto` gate path; update `ll-auto` docs/CLI help.

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
- `/ll:format-issue` - 2026-06-26T22:33:10 - `a4d7e1fc-3146-4ce2-8076-73b85d7fcb8e.jsonl`
- `/ll:capture-issue` - 2026-06-26T22:27:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b5f4713-4801-485e-9909-111bcbcf1d9a.jsonl`

---

## Status

**Open** | Created: 2026-06-26 | Priority: P2
