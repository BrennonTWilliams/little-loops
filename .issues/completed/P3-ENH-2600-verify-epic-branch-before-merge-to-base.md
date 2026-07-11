---
id: ENH-2600
type: enhancement
status: done
priority: P3
captured_at: '2026-07-11T14:29:14Z'
discovered_date: 2026-07-11
discovered_by: capture-issue
relates_to:
- ENH-2601
confidence_score: 98
outcome_confidence: 66
score_complexity: 5
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
size: Very Large
---

# ENH-2600: Verify epic-branch tests/lint before merge-to-base or PR-open

## Summary

When `parallel.epic_branches.enabled` is `true`, the worker pool merges (or opens
a PR for) the shared `epic/<EPIC-ID>-<slug>` integration branch back to
`base_branch` once an EPIC's last child completes. That decision is gated only
by `_verify_work_was_done` (`scripts/little_loops/parallel/worker_pool.py`,
~line 1200-1220), which checks that non-issue files changed — it does not run
the project's test suite or linter. A whole EPIC's integration branch can
therefore auto-merge to `base_branch` (or open a PR) without ever running
`python -m pytest scripts/tests/` (or the configured `project.test_cmd` /
`lint_cmd`) against the merged result.

## Current Behavior

EPIC-branch completion (`epic_branches.merge_to_base_on_complete: true`, the
default) merges/opens-PR based solely on a changed-files check.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ Correction: the merge/PR-open decision itself is **not** made by
> `_verify_work_was_done`. That function (`scripts/little_loops/parallel/worker_pool.py:1200-1238`)
> only runs once per completed child issue (called at `worker_pool.py:596-598`)
> and checks that non-excluded files changed — it has no epic-level scope.
> The actual epic-completion gate is `_maybe_complete_epic()` in
> `scripts/little_loops/parallel/orchestrator.py:1208-1295`, invoked from
> `_on_worker_complete()` at `orchestrator.py:1104-1110` after every worker
> finishes. Its only checks before dispatching to merge/PR are: (1) config
> flags `epic_branches.merge_to_base_on_complete`/`.open_pr` enabled
> (line 1227-1231), (2) all EPIC children `done` via
> `compute_epic_progress()` (line 1260-1273), (3) no unresolved failed
> children (line 1275-1285), (4) not already merged this run
> (`self._merged_epic_branches`, line 1287-1290). No test/lint command is
> invoked anywhere in this path.
>
> Merge itself happens in `_merge_epic_branch_to_base()`
> (`orchestrator.py:1297-1336`) via `self._git_lock.run(["merge", "--no-ff", epic_branch, ...])`
> — note the main repo worktree stays checked out on `base_branch` the whole
> run (per the function's own docstring), so **no checkout of the epic
> branch tip exists today**; a new verify step would need to create one
> (e.g. a scratch worktree) rather than reuse an existing checkout.
> PR-open is `_open_pr_for_epic_branch()` (`orchestrator.py:1338-1390`), a
> `gh pr create` call gated by a `gh auth status` check.
>
> Failure surfacing gap: neither `_merge_epic_branch_to_base` nor
> `_open_pr_for_epic_branch` write into `self._worker_errors` or
> `state.failed_issues` on failure today — they only `logger.warning(...)`.
> A new verify-before-merge gate should populate one of those structures so
> the failure is visible in `_report_results()` (`orchestrator.py:1463-1553`)
> and persisted across resume, not just log-only.

## Expected Behavior

Before the EPIC-branch merge-to-base (or PR-open) step, run the project's
configured `test_cmd` (and optionally `lint_cmd`) against the epic branch
tip. Block the merge (or PR-open) and flag the EPIC as needing manual
attention on failure, matching how `epic_branches` is already documented as a
higher-trust integration surface than per-worker merges.

## Motivation

`epic_branches` exists specifically to give EPICs a single, reviewable
integration surface (docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch).
An unverified auto-merge undermines that: base_branch can receive an EPIC's
combined changes with no automated evidence they pass tests, silently
regressing `base_branch` for anyone who pulls next.

## Proposed Solution

Reuse existing config rather than adding new surface (`project.test_cmd` /
`project.lint_cmd` already exist in `.ll/ll-config.json`). In the epic
completion path (`docs/development/MERGE-COORDINATOR.md:149-158`,
`_maybe_complete_epic`), before merging/opening a PR:

1. Run `project.test_cmd` against the epic branch tip (worktree or a
   throwaway checkout).
2. Optionally run `project.lint_cmd`.
3. On failure, skip the merge/PR-open, leave the epic branch as-is, and
   surface the failure in the run summary / TUI so it's visibly blocked
   rather than silently merged.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Closest existing Python pattern to model after**:
  `_run_per_worktree_proof_first_gate()` (`scripts/little_loops/parallel/worker_pool.py:63-132`)
  — config-gated (`br_config.learning_tests.enabled`,
  `parallel_config.skip_learning_gate` short-circuit `return True`), shells
  out with `subprocess.run(cmd, capture_output=True, text=True, cwd=worktree_path)`,
  returns a plain `bool` (proceed/blocked) and logs the reason via
  `logger.warning`/`logger.info`. A new `_verify_epic_branch_before_merge()`
  (or similar) should follow this exact shape: config short-circuit → run
  command against a checked-out epic-branch worktree → bool return.
- **No existing Python call site invokes `project.test_cmd`/`.lint_cmd`
  directly** — every current consumer resolves and shells these out from
  FSM YAML (`scripts/little_loops/loops/oracles/code-run-gate.yaml`
  `run_test`/`run_lint` states, lines 193-241 and 273-298) via inline
  `python3 -c` config reads, not a Python subprocess call. This ENH would be
  the first direct-Python consumer of these two `ProjectConfig` fields
  (`scripts/little_loops/config/core.py:142-143`).
- **Checkout mechanism**: `setup_worktree()`
  (`scripts/little_loops/worktree_utils.py:63-159`) always creates a *new*
  branch (`git worktree add -b <new-branch> <path> [<base_branch>]`) — no
  existing call site checks out an *existing* branch (like `epic/<id>-<slug>`)
  in place. The verify step will need either a bare
  `git worktree add <path> <epic_branch>` (no `-b`) or to pass
  `base_branch=epic_branch` with a disposable branch name, then
  `cleanup_worktree()` (`worktree_utils.py:161-201`) to tear it down
  afterward regardless of pass/fail.

## Implementation Steps

1. Locate the epic completion path in `scripts/little_loops/parallel/worker_pool.py`
   (`_maybe_complete_epic` / equivalent) and `docs/development/MERGE-COORDINATOR.md`.
2. Add a verify-before-merge step that shells out to `project.test_cmd`
   (and `lint_cmd` if configured) against the epic branch tip.
3. Wire failure to block merge/PR-open and record the reason on the
   `WorkerResult`/summary output.
4. Update `docs/development/MERGE-COORDINATOR.md` and
   `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch` to document the
   new gate.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Correction**: `_maybe_complete_epic` actually lives in
   `scripts/little_loops/parallel/orchestrator.py:1208-1295`, not
   `worker_pool.py` (see Current Behavior note above). Insert the new verify
   call between the idempotency gate (line 1287-1290) and the
   merge/PR dispatch (line 1292-1295) — i.e. only verify once per branch,
   matching the existing `self._merged_epic_branches` dedup.
2. Add a helper (e.g. `_verify_epic_branch_before_merge(epic_id, epic_branch) -> bool`)
   modeled on `_run_per_worktree_proof_first_gate`
   (`worker_pool.py:63-132`): check a new config flag first, then create a
   scratch worktree checked out to `epic_branch` tip (via
   `setup_worktree`/`cleanup_worktree` in `worktree_utils.py`, since no
   existing checkout of the epic branch exists — see Proposed Solution
   note), run `project.test_cmd` (and `project.lint_cmd` if configured)
   with `cwd=<worktree_path>`, then always `cleanup_worktree(...)`
   regardless of outcome.
3. On failure, `return` from `_maybe_complete_epic` before the
   merge/PR dispatch, and populate `self._worker_errors[epic_id]` (or a new
   epic-scoped structure) so the failure surfaces in `_report_results()`
   (`orchestrator.py:1463-1553`) — today neither `_merge_epic_branch_to_base`
   nor `_open_pr_for_epic_branch` write any structured failure record on
   error, only `logger.warning(...)` (this is itself a pre-existing gap
   worth closing alongside the new gate).
4. Add the new flag (e.g. `epic_branches.verify_before_merge`) to
   `EpicBranchesConfig` in **both** places that currently duplicate it:
   `scripts/little_loops/parallel/types.py:311-334` and
   `scripts/little_loops/config/automation.py:40-59`, plus the
   `config-schema.json` `epic_branches` block (lines 412-438). Default the
   flag to `False` — the existing `TestEpicCompletionMerge` suite in
   `test_orchestrator.py` has no `test_cmd`/`lint_cmd` subprocess mocks, so
   a `True` default breaks multiple passing tests (see Tests section).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included
in the implementation:_

5. Wire the new field through the config bridge in
   `scripts/little_loops/config/core.py` `_build_parallel_epic_branches`
   (~513-534) — the conversion is explicit field-by-field, so the new flag
   must be added there too or it's silently dropped at runtime.
6. Populate a structured failure record that `_report_results()`
   (`orchestrator.py:1463-1553`) actually surfaces. Confirmed:
   `self._worker_errors[epic_id]` alone is **not** sufficient —
   `_report_results()` only reports failures for entries present in
   `self.queue.failed_ids` (~1496-1500), and there's no existing
   epic-branch-keyed reporting block. Either add `epic_id` to
   `queue.failed_ids`, or add a new dedicated report block modeled on the
   existing `stash_warnings` pattern (sourced from
   `self.merge_coordinator.stash_pop_failures`, ~1564-1575).
7. Update `scripts/tests/test_config_schema.py`
   `test_parallel_epic_branches_in_schema` (~744-770),
   `scripts/tests/test_config.py` (`test_epic_branches_*`, ~419-449,
   ~811-815, ~970-1021), and `scripts/tests/test_parallel_types.py`
   (~767-770, ~1043-1060) with new-field assertions so the existing
   exhaustive per-field test pattern stays accurate.
8. Update `docs/reference/API.md` (`EpicBranchesConfig` dataclass block,
   ~3299-3319), `docs/reference/CONFIGURATION.md` (config table,
   ~364-367), `docs/ARCHITECTURE.md` (~463-470), and
   `skills/configure/show-output.md` (~54-57) to include the new field —
   in addition to the already-planned `MERGE-COORDINATOR.md` /
   `SPRINT_GUIDE.md` updates.

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/orchestrator.py` — `_maybe_complete_epic`
  (1208-1295), `_merge_epic_branch_to_base` (1297-1336),
  `_open_pr_for_epic_branch` (1338-1390) — insert/wire the new verify gate
  and failure surfacing here, not in `worker_pool.py`
- `scripts/little_loops/parallel/types.py` — `EpicBranchesConfig` (311-334),
  add new config field
- `scripts/little_loops/config/automation.py` — `EpicBranchesConfig`
  duplicate (40-59), keep in lockstep per existing dual-representation
  pattern (see `config/core.py:513-532` `_build_parallel_epic_branches`)
- `scripts/little_loops/config-schema.json` — `epic_branches` schema block
  (412-438). Note: this block sets `additionalProperties: false`
  (confirmed by `test_parallel_epic_branches_in_schema`), so this is a hard
  validation gate, not just documentation drift — a config setting the new
  field will be rejected if the property isn't declared here first.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/core.py` — `_build_parallel_epic_branches`
  (~513-534) does an explicit field-by-field conversion
  (`enabled=src.enabled, prefix=src.prefix,
  merge_to_base_on_complete=src.merge_to_base_on_complete,
  open_pr=src.open_pr`) from the `config/automation.py` dataclass to the
  `parallel/types.py` runtime dataclass. This bridge must add
  `verify_before_merge=src.verify_before_merge` explicitly or the new flag
  will silently be dropped at runtime regardless of what's configured — the
  two dataclasses being "in lockstep" is not itself sufficient. [Agent 2
  finding]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/parallel.py`, `scripts/little_loops/cli/sprint/run.py`
  construct `ParallelOrchestrator`/`ParallelConfig` and would pick up the
  new flag automatically via existing config plumbing — no direct changes
  expected unless a new CLI override flag is added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/merge_coordinator.py` — `MergeCoordinator`
  handles merge operations generally; check for any epic-branch-merge
  coupling beyond what `orchestrator.py` already owns directly. [Agent 1
  finding]
- `scripts/little_loops/parallel/worker_pool.py` — imports
  `EpicBranchesConfig` and owns `_run_per_worktree_proof_first_gate` (the
  pattern this issue models the new gate on); no functional change
  expected but confirm no other epic-branch coupling here. [Agent 1
  finding]

### Reusable Utilities
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` (63-159),
  `cleanup_worktree()` (161-201) for checking out/tearing down the epic
  branch tip in a scratch worktree
- `scripts/little_loops/parallel/git_lock.py` — `GitLock.run(...)`, the
  thread-safe subprocess wrapper already used by
  `_merge_epic_branch_to_base`; any new git operation (e.g. `rev-parse` to
  resolve the epic branch tip) should go through this, not bare
  `subprocess.run`

### Tests
- `scripts/tests/test_orchestrator.py` — `TestEpicCompletionMerge` class
  (~1329-1527) and its `make_epic_orchestrator` fixture
  (~149-230) already exercise `_maybe_complete_epic`'s merge/PR/idempotency
  paths via a `_capture_git()` helper that stubs `orch._git_lock.run`; add
  new test cases here for the verify-gate blocking a merge on a failing
  `test_cmd`, and for the idempotent-single-verify-per-branch behavior
  (existing `test_idempotent_across_calls` pattern, ~1505-1517). The
  `make_epic_orchestrator` factory's kwargs (`enabled`, `merge_to_base`,
  `open_pr`) will also need a new `verify_before_merge`/`test_cmd`/`lint_cmd`
  kwarg to construct verify-gate scenarios. **If the new field defaults to
  `True`** (not `False`, matching sibling `enabled`), every existing test
  in this class that reaches the merge/PR path
  (`test_merges_epic_branch_when_all_children_done`,
  `test_opens_pr_when_open_pr_true`, `test_idempotent_across_calls`) breaks
  because none currently mock a `test_cmd`/`lint_cmd` subprocess call — in
  particular `test_opens_pr_when_open_pr_true` (~1465) already patches
  `little_loops.parallel.orchestrator.subprocess.run` with a `gh`-only
  fake that returns `returncode=1` for anything else, which would collide
  with a verify-gate subprocess call through the same patch target. [Agent
  3 finding — default the flag to `False` to avoid a breaking change to
  this suite, consistent with the "additive gate" Risk note below]
- `scripts/tests/test_worker_pool.py` (~3170-3409) — the actual class name
  is `TestPerWorktreeProofFirstGate` (not `TestProofFirstGate`), covering
  `_run_per_worktree_proof_first_gate` (imported inline per-test); model
  new verify-gate unit tests after this class's conventions: patch
  `subprocess.run` at the **module** path
  (`little_loops.parallel.orchestrator.subprocess.run` for the new gate,
  since it lives in `orchestrator.py` per this issue's own correction, not
  `worker_pool.py`), assert on `call_args[0][0]` for the constructed
  command, and assert the boolean gate return value. [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — `test_parallel_epic_branches_in_schema`
  (~744-770) asserts type/default for all four existing `epic_branches`
  sub-properties field-by-field; extend with the same assertion shape for
  `verify_before_merge`. This is the test to keep in sync with the hard
  `additionalProperties: false` schema gate noted above. [Agent 3 finding]
- `scripts/tests/test_config.py` — `test_epic_branches_defaults` (~419-425),
  `test_epic_branches_from_dict` (~427-441),
  `test_epic_branches_partial_dict_uses_defaults` (~443-449), a
  dict-roundtrip assertion (~811-815), and three `create_parallel_config`
  override tests (~970-1021) all enumerate `EpicBranchesConfig` fields
  explicitly; each needs a new assertion for `verify_before_merge` to stay
  exhaustive (they won't fail without it, but will silently not cover the
  new field). [Agent 2 finding]
- `scripts/tests/test_parallel_types.py` — a defaults test (~767-770) and a
  dict-conversion roundtrip test (~1043-1060) with the same explicit
  per-field pattern on the runtime-side `EpicBranchesConfig`; same
  exhaustiveness gap as `test_config.py` above. [Agent 2 finding]
- `scripts/tests/test_worktree_utils.py` — currently covers only
  `detect_default_branch()`; `setup_worktree()`/`cleanup_worktree()`
  themselves have **zero direct unit-test coverage** in this file. Since
  `setup_worktree()` always creates a new branch via `["worktree", "add",
  "-b", branch_name, ...]` (no existing call site or test checks out an
  *already-existing* branch tip), the new verify-worktree call has no test
  precedent to extend — write a new test here for whatever
  checkout-existing-branch mechanism is chosen (new `setup_worktree`
  parameter, or bare `git worktree add <path> <existing-branch>` call).
  [Agent 3 finding]

### Documentation
- `docs/development/MERGE-COORDINATOR.md` (epic completion path,
  lines 149-158)
- `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — § `EpicBranchesConfig` dataclass code block
  (~3299-3319) reproduces all four fields with inline comments
  (`merge_to_base_on_complete: bool = True  # merge EPIC branch to base
  after last child`); needs a fifth field/comment line. Also
  `ParallelOrchestrator.__init__`/`create_parallel_config` prose
  (~295-306) enumerates `prefix`/`merge_to_base_on_complete`/`open_pr` as
  the fields `dataclasses.replace` preserves — incomplete once a fourth
  field exists. [Agent 2 finding]
- `docs/reference/CONFIGURATION.md` — config-reference table (~364-367)
  has one row per `epic_branches.*` field; needs a new row for
  `epic_branches.verify_before_merge`. [Agent 2 finding]
- `docs/ARCHITECTURE.md` (~463-470) — prose describing epic-branch
  completion flow ("merges... optionally opening a PR...") should mention
  the new verify gate as part of the completion sequence. [Agent 2
  finding]
- `skills/configure/show-output.md` (~54-57) — a per-field template block
  rendering each `epic_branches.*` field with its default
  (`epic_branches.merge_to_base_on_complete: {{...}} (default: true)`),
  used by `/ll:configure`'s output; needs a new
  `epic_branches.verify_before_merge:` line to keep the rendered config
  summary in sync with the schema. [Agent 2 finding]
- `skills/configure/areas.md` — matched the same `epic_branches` grep as
  `show-output.md`; check for a similar settings-area enumeration that may
  need the new field added. [Agent 2 finding]

## Impact

- **Priority**: P3 — not urgent, but a real correctness gap in a mechanism
  designed to be the trusted integration surface for EPIC work.
- **Effort**: Small-medium — one new gated step in an existing completion
  path, reusing existing config fields.
- **Risk**: Low — additive gate; default-off failure mode (block, don't
  auto-fix) avoids surprising behavior changes for existing users.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/development/MERGE-COORDINATOR.md | Epic completion / merge-to-base flow this gate slots into |
| docs/guides/SPRINT_GUIDE.md | Per-EPIC integration branch user-facing docs |

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-11_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 66/100 → MODERATE

### Outcome Risk Factors
- Broad enumeration across ~18 sites (5 code/config files, 6 test files, 7 doc files) — many are mechanical additions, but the sheer count raises the chance one is missed on the first pass.
- The scratch-worktree checkout mechanism for the existing epic-branch tip (a new `setup_worktree` parameter vs. a bare `git worktree add <path> <existing-branch>` call) is left as an implementation choice with no existing call-site precedent — `setup_worktree()` today always creates a *new* branch.
- The new checkout path has zero existing unit-test coverage to model against (`test_worktree_utils.py` only covers `detect_default_branch()`), so the new tests here are original rather than adapted from a working example.

## Session Log
- `/ll:confidence-check` - 2026-07-11T14:29:14Z - `000ba01e-76b0-4308-a39e-fdaf76f9715c.jsonl`
- `/ll:wire-issue` - 2026-07-11T14:43:33 - `a902e10b-5af4-4ae1-b8bc-e8ff3d28bde3.jsonl`
- `/ll:refine-issue` - 2026-07-11T14:37:39 - `33e3487d-9c22-4564-a0ba-33d654174507.jsonl`
- `/ll:capture-issue` - 2026-07-11T14:29:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad4feb6f-5337-496b-9c18-ce805ea7bc9f.jsonl`
- `/ll:issue-size-review` - 2026-07-11 - `2385c5ce-bdf9-4918-95d8-8118da444ec1.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-11
- **Reason**: Issue too large for single session (score 11/11, Very Large)

### Decomposed Into
- ENH-2602: Add `epic_branches.verify_before_merge` config flag
- ENH-2603: Run test/lint gate before epic-branch merge-to-base and surface failures

---

## Status

- [x] Decomposed
