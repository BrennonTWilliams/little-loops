---
id: FEAT-2561
title: "shared EPIC-ancestor helper \u2014 promote find_nearest_epic_ancestor to module\
  \ scope"
type: FEAT
priority: P3
status: done
captured_at: '2026-07-09T00:00:00Z'
completed_at: '2026-07-09T22:37:26Z'
discovered_date: 2026-07-09
discovered_by: confidence-check-decomposition
labels:
- parallel
- epics
- refactor
- git
parent: EPIC-2451
relates_to:
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
- FEAT-2562
blocked_by: []
unblocks:
- FEAT-2449
- FEAT-2562
decision_needed: false
confidence_score: 100
outcome_confidence: 91
score_complexity: 21
score_test_coverage: 24
score_ambiguity: 24
score_change_surface: 22
---

# FEAT-2561: shared EPIC-ancestor helper — promote find_nearest_epic_ancestor to module scope

## Summary

Prerequisite child extracted from FEAT-2449 (decomposed via
`/ll:confidence-check` on 2026-07-09). Today the only code path that maps an
issue to its nearest EPIC ancestor is a **private WorkerPool method**
(`_find_nearest_epic_ancestor` at `worker_pool.py:1643`). FEAT-2449's
partial-failure gate and FEAT-2562's `_inspect_worktree` epic-awareness both
need the same mapping from inside `orchestrator.py` — and reaching into
`self.worker_pool._find_nearest_epic_ancestor(...)` couples the orchestrator to a
private WorkerPool internal.

This child promotes the parent-chain walk to **module-level functions in
`scripts/little_loops/issue_progress.py`** (the natural home — it already builds
parent maps internally in `compute_epic_progress` and is imported broadly), then
rewires `WorkerPool` to delegate to them with **no behavior change**. Landing this
first turns FEAT-2449's cross-module reach into a clean shared-helper call and
lets FEAT-2562 consume the same function.

## Parent Issue

Decomposed from FEAT-2449 on 2026-07-09 via `/ll:confidence-check` (outcome
70/100 → the partial-failure gate's reach into WorkerPool internals was the main
Complexity/Change-surface drag). EPIC-2451 (Per-EPIC integration branch strategy)
is the parent EPIC and remains the coordination container.

## Scope

1. **`find_nearest_epic_ancestor()` module function**
   (`scripts/little_loops/issue_progress.py`) — a pure, cycle-guarded walk:
   ```python
   def find_nearest_epic_ancestor(
       issue: IssueInfo,
       parent_map: dict[str, str | None],
   ) -> str | None:
       """Walk issue.parent upward; return nearest EPIC-* ID or None."""
   ```
   Lift the walk body verbatim from `worker_pool.py:1650-1660` (the
   `seen`-guarded `while current and current not in seen` loop that returns the
   first `current.split("-", 1)[0] == "EPIC"`). No filesystem access — the caller
   supplies `parent_map`.

2. **`build_parent_map()` module function**
   (`scripts/little_loops/issue_progress.py`) — construct `{issue_id: parent_id}`
   from an in-memory issue list:
   ```python
   def build_parent_map(
       all_issues: list[IssueInfo],
   ) -> dict[str, str | None]:
   ```
   This is the in-memory analog of the map `compute_epic_progress` already builds
   at `issue_progress.py:106` — factor that inline construction out to call this
   function (DRY), so the two stay in lockstep.

3. **`WorkerPool` delegates (no behavior change)** — rewire
   `WorkerPool._find_nearest_epic_ancestor` (`worker_pool.py:1643`) to call the
   module `find_nearest_epic_ancestor(issue, self._build_parent_map())`.
   `_build_parent_map` (`worker_pool.py:1662`) keeps its **disk-scanning** shape
   and the instance-level `_parent_map_cache` (WorkerPool has no in-memory issue
   list — it scans `.issues/` directly), so this method is retained; only the walk
   is delegated. The public/observed behavior of `_resolve_branch_targets`
   (`worker_pool.py:1615`) is unchanged.

   > **Design note**: the shared function is the *walk* (the actual duplicated
   > logic and the piece the orchestrator needs), not the map source. WorkerPool
   > builds its map from disk; the orchestrator builds its map from
   > `self._issue_info_by_id.values()` via `build_parent_map`. Both then call the
   > identical walk. This is the minimal extraction that removes the private-method
   > reach without forcing WorkerPool to change how it sources issues.

4. **Tests** —
   - `scripts/tests/test_issue_progress.py` — new unit tests for the two module
     functions using the existing `_make_issue` helper
     (`test_issue_progress.py:12-64`, canonical `IssueInfo`-with-`parent`-chain
     synthesizer):
     - `test_find_nearest_epic_ancestor_direct_parent` (child → EPIC)
     - `test_find_nearest_epic_ancestor_multi_hop` (grandchild → sub-FEAT → EPIC)
     - `test_find_nearest_epic_ancestor_no_epic` (chain with no EPIC → None)
     - `test_find_nearest_epic_ancestor_cycle_guard` (A→B→A → None, no hang)
     - `test_build_parent_map_shape` (list → `{id: parent}` dict)
   - `scripts/tests/test_worker_pool.py` — **no-regression pass**: the existing
     `_resolve_branch_targets` / epic-ancestor tests (e.g.
     `TestUpdateBranchBase` epic triad at `test_worker_pool.py:1831-1909`) must
     stay green unchanged, proving delegation preserved behavior.

## Out of Scope (belongs to the consumers)

- Any use of the helper in the partial-failure gate / EPIC-completion detection —
  **FEAT-2449**.
- Any use of the helper in `_inspect_worktree` — **FEAT-2562**.
- Changing how `compute_epic_progress` walks children (`_issue_descends_to`,
  `issue_progress.py:67-80`) — that transitive descent-to-a-**specific**-EPIC
  check (an upward walk that returns a boolean, not the nearest ancestor) is a
  different operation and is not touched here. (Note: despite the "descends_to"
  name, the implementation walks `parent` **upward** — same direction as the
  nearest-ancestor walk, different terminal condition.)

## Acceptance Criteria

- [ ] `find_nearest_epic_ancestor(issue, parent_map)` and
      `build_parent_map(all_issues)` exist as module-level functions in
      `issue_progress.py`.
- [ ] `WorkerPool._find_nearest_epic_ancestor` delegates to the module walk;
      `_build_parent_map` retains its disk-scan + `_parent_map_cache`.
- [ ] `compute_epic_progress` builds its parent map via the new
      `build_parent_map` (no duplicated inline construction).
- [ ] New `test_issue_progress.py` tests cover direct/multi-hop/no-epic/cycle
      cases + map shape.
- [ ] Existing `test_worker_pool.py` epic-resolution tests pass unchanged
      (behavior-preserving delegation).
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation (2 files):**
- `scripts/little_loops/issue_progress.py` (2 new module fns + DRY the inline
  parent-map build in `compute_epic_progress`)
- `scripts/little_loops/parallel/worker_pool.py` (`_find_nearest_epic_ancestor`
  delegates)

**Tests (1 file):**
- `scripts/tests/test_issue_progress.py` (5 new unit tests)

**Estimated file count:** 2 implementation + 1 test = **3 files**.

## Integration Map

- **Files to Modify**: `issue_progress.py`, `worker_pool.py`
- **Dependent Files (future consumers)**: `parallel/orchestrator.py`
  (FEAT-2449 partial-failure gate + FEAT-2562 `_inspect_worktree`)
- **Similar Patterns**: `cli/issues/list_cmd.py::_find_epic_ancestor`
  (`:203-211`) — the original cycle-guarded EPIC-ancestor walk the WorkerPool
  method was modeled on; consider whether that consumer can also delegate (nice-
  to-have, not required for this child).
- **Tests**: `test_issue_progress.py`, no-regression on `test_worker_pool.py`

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_

The DRY change to `compute_epic_progress` (factoring the inline `parent_map`
build at `issue_progress.py:106` out to `build_parent_map`, which retains
`None`-valued parents instead of dropping them) shifts `parent_map`'s shape.
These three call sites consume `compute_epic_progress` — none read `parent_map`
directly (only `EpicProgress` fields), so the shift is behavior-preserving, but
each is a **verify-no-regression** target for the None-retention change:
- `cli/issues/epic_progress.py::cmd_epic_progress` (`:46`) — the `ll-issues
  epic-progress` command. [Agent 1/2 finding]
- `cli/issues/list_cmd.py` (`:63-75`) — `--parent` filter descendant resolution
  (ENH-2481). [Agent 1/2 finding]
- `cli/issues/list_cmd.py` (`:242-249`) — `--group-by epic` progress-badge cache
  (BUG-2480). [Agent 1/2 finding]

> Behavior-preserving rationale: `_issue_descends_to` reads the map via
> `parent_map.get(issue_id)` and its `while current` loop treats a `None` value
> identically to a missing key, so retaining `None` entries does not change the
> walk. Keep the AC's "no duplicated inline construction" but assert this
> equivalence in the DRY step.

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-epic/SKILL.md` (`:72-73`) — cites `compute_epic_progress()`
  with a **hard line anchor** (`scripts/little_loops/issue_progress.py:87`).
  Inserting the two new module functions above `compute_epic_progress` will shift
  its line number; update this anchor (or reverify) after the extraction. [Agent 2
  finding]
- `docs/reference/API.md` (`:74`) — one-line module summary for
  `little_loops.issue_progress`. Advisory: if the table's convention is to list
  public functions, add `find_nearest_epic_ancestor`/`build_parent_map`; no change
  if it stays module-level prose. [Agent 2 finding]
- `.ll/decisions.yaml` — `ARCH-170` (BUG-2441) is the standing "extract one shared
  EPIC-membership helper" decision this child fulfills. Consider recording an
  `outcome` via `ll-issues decisions outcome ARCH-170 …` once FEAT-2561 lands
  (note `list_cmd.py::_find_epic_ancestor`, named in the rule's rationale, remains
  un-migrated here — out of scope). [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- **Anchor correction (affects AC + Scope §4):** the WorkerPool "epic triad"
  cited as the no-regression net at `test_worker_pool.py:1831-1909` is actually
  `TestUpdateBranchBase`, which **pre-seeds `_worker_epic_branches` directly and
  does not exercise `_find_nearest_epic_ancestor`/`_build_parent_map`** — it is
  unaffected by this refactor. The real regression net for the delegated walk is
  **`TestResolveBranchTargets` (`test_worker_pool.py:3415-3604`)**, esp.
  `test_nested_epic_flattens_to_nearest` (`:3521`, multi-hop flatten) and
  `test_idempotent_creation` (`:3561`, validates `_parent_map_cache`). Both must
  pass unchanged. [Agent 3 finding]
- `scripts/tests/test_issues_cli.py` — regression net for
  `list_cmd::_find_epic_ancestor` (the third structurally-identical walk):
  `test_list_group_by_epic_*` and `test_list_parent_includes_transitive_grandchild`
  (`:939-1141`). No update needed for this issue; relevant only if the nice-to-have
  `list_cmd` delegation is pursued later. [Agent 3 finding]
- `scripts/tests/test_orchestrator.py::TestOnWorkerComplete` (`:2062-2115`) — the
  only orchestrator-level `epic_branch` test; it stubs resolution by setting
  `WorkerResult.epic_branch` literally, so it does not exercise the walk end-to-end
  (no true orchestrator→WorkerPool file-scan round-trip test exists). Informational
  — flags the integration-coverage gap the future consumers (FEAT-2449/2562) will
  close. [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — verified against the codebase 2026-07-09:_

- **Anchor corrected**: `cli/issues/list_cmd.py::_find_epic_ancestor` is a nested
  function at **`:203-211`** (not `:195-203`); it closes over a `_parent_map`
  built inline at `list_cmd.py:201` rather than taking it as a parameter. Its walk
  is byte-identical in shape to `WorkerPool._find_nearest_epic_ancestor`
  (`seen`-guarded, `current.split("-", 1)[0] == "EPIC"`), so it is a genuine
  delegation candidate — but it would need the `parent_map` supplied as an
  argument (or a `build_parent_map`-fed map), matching the new module signature.
- **Third duplication site**: `issue_progress.py::_issue_descends_to`
  (`:67-80`) is the *same* cycle-guarded upward walk, differing only in its
  terminal check — it returns `True` when the chain reaches a **specific**
  `epic_id`, rather than returning the *nearest* EPIC ancestor. It is **not**
  a `find_nearest_epic_ancestor` caller and stays out of scope (see Out of Scope),
  but it is worth noting there are now **three** structurally-identical walks
  (`list_cmd`, `worker_pool`, `issue_progress`) all citing the same source
  pattern in their docstrings.
- **`compute_epic_progress` map build confirmed**: the inline construction is a
  single dict comprehension — `parent_map = {i.issue_id: i.parent for i in
  all_issues if i.parent}` at `issue_progress.py:106` — consumed by
  `_issue_descends_to` at `:110`. Note it currently filters out `None` parents
  (`if i.parent`); the proposed `build_parent_map` signature returns
  `dict[str, str | None]` (retaining `None` values), so factoring this out must
  either preserve the `None`-drop or confirm `_issue_descends_to`/`.get()`
  callers tolerate the extra `None`-valued keys (they do — `.get()` returns the
  `None` value and the `while current` guard halts). Keep the AC's "no duplicated
  inline construction" but verify the shape shift is behavior-preserving.
- **`IssueInfo` source**: `little_loops.issue_parser.IssueInfo`
  (`@dataclass`, `issue_parser.py:551`) with `parent: str | None = None`
  (`:591`); imported under `TYPE_CHECKING` in `issue_progress.py:10`.

## Blocks

- FEAT-2449 (partial-failure gate uses the shared walk)
- FEAT-2562 (`_inspect_worktree` maps worktree issue-ID → EPIC via the shared walk)

## Resolution

Implemented 2026-07-09 via `/ll:manage-issue`. Promoted the EPIC-ancestor
parent-chain walk to two module-level functions in
`scripts/little_loops/issue_progress.py`:

- `find_nearest_epic_ancestor(issue, parent_map)` — the walk lifted verbatim from
  `WorkerPool._find_nearest_epic_ancestor` (starts from `issue.parent`,
  cycle-guarded, returns first `EPIC-*` ancestor). Pure, no filesystem access.
- `build_parent_map(all_issues)` — in-memory `{issue_id: parent}` builder that
  **retains** `None`-valued parents (matching the disk-scan builder's shape).

`WorkerPool._find_nearest_epic_ancestor` now delegates to the module walk,
supplying `self._build_parent_map()` (its disk-scan + `_parent_map_cache`
retained). `compute_epic_progress` now builds its parent map via
`build_parent_map` (DRY; the inline `if i.parent` filter is gone). The
`None`-retention shift is behavior-preserving: `_issue_descends_to` /
`.get()` treat a `None` value identically to a missing key (its type annotation
was widened to `dict[str, str | None]`).

**Verification:** 10 new unit tests in `test_issue_progress.py`
(direct/multi-hop/no-epic/cycle/no-parent + map shape) pass;
`TestResolveBranchTargets` regression net (incl. `test_nested_epic_flattens_to_nearest`,
`test_idempotent_creation`) passes unchanged; full suite `14422 passed, 36 skipped`;
mypy + ruff clean. Doc anchor in `skills/review-epic/SKILL.md` updated (`:87` → `:120`).

Out of scope (per issue): `list_cmd.py::_find_epic_ancestor` delegation and
consumer wiring (FEAT-2449 / FEAT-2562).

## Session Log
- `/ll:manage-issue` - 2026-07-09T22:36:55 - `d0494f45-9e7a-424d-b1d7-57ca522cf905.jsonl`
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `bcca02d5-1fc9-4422-a6c5-6879845c5159.jsonl`
- `/ll:wire-issue` - 2026-07-09T22:00:36 - `de14ada0-187e-4c4d-aee7-ce2c6cdb932a.jsonl`
- `/ll:refine-issue` - 2026-07-09T21:49:11 - `0f3a1cee-ab11-494d-a96b-0436370c2e78.jsonl`
- `/ll:confidence-check` - 2026-07-09T00:00:00 - `b4b437e8-ceeb-4657-a600-ad4fd9cabd3d.jsonl` (decomposition of FEAT-2449)
