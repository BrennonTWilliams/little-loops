---
id: FEAT-2453
title: "per-EPIC integration branch \u2014 downstream consumer read-sites"
type: FEAT
priority: P3
status: open
captured_at: '2026-07-07T19:55:00Z'
discovered_date: 2026-07-07
discovered_by: confidence-check-decomposition
labels:
- parallel
- sprint
- epics
- git
- worktree
- merge
parent: EPIC-2451
relates_to:
- FEAT-2339
- EPIC-2451
- FEAT-2447
- FEAT-2448
- FEAT-2449
- FEAT-2452
blocked_by:
- FEAT-2452
unblocks:
- FEAT-2449
decision_needed: false
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-2453: per-EPIC integration branch — downstream consumer read-sites

## Summary

Second of two sequenced children of FEAT-2448 (decomposed via
`/ll:confidence-check` on 2026-07-07). This child lands the
**downstream consumer read-sites** that read `result.epic_branch`
(or `branch_state["epic_branch"]`) after the value has been
populated by FEAT-2452's `WorkerResult` field and 12-return
kwarg threading. Each site is a 1-2 line mechanical substitution;
the issue achieves HIGH outcome confidence (86/100) precisely
because the broad fanout was lifted out into FEAT-2452.

Scope:
- **`merge_coordinator.py:624`** — `_process_merge` checkout
  target: `base = result.epic_branch or self.config.base_branch`.
- **`merge_coordinator.py:875`** — `_handle_conflict` rebase
  target: same substitution.
- **`orchestrator.py:1005`** — `branch_state["epic_branch"] =
  result.epic_branch` mutation in `_on_worker_complete` before
  invoking `_open_pr_for_branch`.
- **`orchestrator.py:1142`** — `--base` read site swap.

For full research context see FEAT-2448
(`# Codebase Research Findings`) — anchor drift corrected at
2026-07-07 (the methods cited there are `_process_merge` not
`_process_single_merge`).

## Parent Issue

Decomposed from FEAT-2448 on 2026-07-07 via `/ll:confidence-check`
(outcome 74/100 → split into FEAT-2452 + FEAT-2453 to lift this
piece to HIGH outcome confidence).

EPIC-2451 (Per-EPIC integration branch strategy) is the parent
EPIC and remains the coordination container.

## Scope

1. **`_process_merge` checkout target**
   (`scripts/little_loops/parallel/merge_coordinator.py:577-`,
   line 624) — replace
   `base = self.config.base_branch` with
   `base = result.epic_branch or self.config.base_branch`.
   The substitution is byte-for-byte identical when
   `epic_branch is None` (the default for non-EPIC issues), so
   no behavioral change for the no-op case. The local `result`
   binding is established at line 586
   (`result = request.worker_result`) — `result.epic_branch` is
   in scope at line 624 without any signature change on
   `MergeCoordinator`.

2. **`_handle_conflict` fetch+rebase target**
   (`scripts/little_loops/parallel/merge_coordinator.py:808-`,
   line 875) — same substitution as step 1 at line 875. The
   local `result` binding is established at line 816
   (`result = request.worker_result`). Same no-op behavior
   when `epic_branch is None`.

3. **`_on_worker_complete` branch_state mutation**
   (`scripts/little_loops/parallel/orchestrator.py:1005`,
   inside the `if self.parallel_config.open_pr_for_feature_branches:`
   block at line 1006) — add
   `branch_state["epic_branch"] = result.epic_branch`
   immediately before the call to `_open_pr_for_branch(...)` at
   line 1006. Matches the established
   `branch_state["pushed"] = True` mutation pattern at
   `orchestrator.py:1010`-area.

4. **`_open_pr_for_branch` --base read site**
   (`scripts/little_loops/parallel/orchestrator.py:1142`) —
   replace the
   `self.parallel_config.base_branch`
   read with
   `branch_state.get("epic_branch") or self.parallel_config.base_branch`.
   The function signature at `orchestrator.py:1109-1114`
   (`def _open_pr_for_branch(self, issue_id: str, branch_name: str, branch_state: dict[str, Any]) -> None`)
   does NOT receive a `WorkerResult` object — `branch_state` is
   the existing carrier, populated by step 3.

5. **Tests** —
   - `scripts/tests/test_merge_coordinator.py` — new
     `test_*_epic_branch_*` tests verifying that
     `MergeCoordinator` routes the merge target to the epic
     branch (not `base_branch`) when the issue has a parent
     EPIC and `epic_branches.enabled=True`. Modeled on the
     existing `test_*_untracked_files_error` /
     `test_*_local_changes_error` patterns. At minimum:
     - `test_process_merge_checkout_uses_epic_branch`
       (substitutes line 624 behavior; verify `_process_merge`
       checks out `epic/EPIC-2451-...` not `main`)
     - `test_handle_conflict_rebase_uses_epic_branch`
       (substitutes line 875; verify fetch+rebase targets the
       epic branch)
     - `test_process_merge_falls_back_to_base_branch`
       (verifies the `or` idiom preserves non-EPIC behavior)
   - `scripts/tests/test_orchestrator.py:2008-2052` —
     `test_on_worker_complete_feature_branch_open_pr` already
     uses an inline `fake_subprocess_run` that does NOT
     capture args. Extend the test by:
     - Adding a `captured_args: list[list[str]] = []`
       accumulator
     - Appending `args` inside `fake_subprocess_run` (same
       pattern as `TestUpdateBranchBase` at
       `test_worker_pool.py:1714-1794`)
     - Asserting on the actual `--base` value in the captured
       `gh pr create` args, e.g.
       `assert any("--base" in args and "epic/EPIC-XXXX-..." in args for args in captured_args)`
   - `scripts/tests/test_orchestrator.py:2260-2321` —
     `test_on_worker_complete_feature_branch_pr_url_idempotency`
     has the same `fake_subprocess_run` shape; same args-capture
     enhancement so the idempotency case (existing `pr_url`
     preserved) also asserts on `--base`.

## Out of Scope (deferred)

- `WorkerResult.epic_branch` field declaration + 4-edit pattern —
  **FEAT-2452**.
- 12-return kwarg threading in `_process_issue` —
  **FEAT-2452**.
- `self._worker_epic_branches` instance-state dict +
  `_get_changed_files` / `_update_branch_base` updates —
  **FEAT-2452**.
- The full PR-target decision ("child PR lands on epic branch vs.
  base") — **FEAT-2449**. This child only switches the `--base`
  argument; FEAT-2449 owns the rest of the merge/PR-completion
  lifecycle.
- `test_worker_pool.py`, `test_parallel_types.py`,
  `test_subprocess_mocks.py` WorkerPool-side modifications —
  **FEAT-2452**.
- `IssueProcessingResult.epic_branch` symmetric field
  (out-of-scope per FEAT-2448:1067-1090; relevant only if
  FEAT-2449/2450 extend the in-place path) — **deferred**.
- `docs/reference/API.md:3211-3235` WorkerResult field listing
  (this child doesn't modify `WorkerResult` itself; the API doc
  update is paired with FEAT-2452 / FEAT-2450).

## Acceptance Criteria

- [ ] `_process_merge` checks out against
      `result.epic_branch or self.config.base_branch` at
      `merge_coordinator.py:624` (verified via args-capture).
- [ ] `_handle_conflict` rebases against
      `result.epic_branch or self.config.base_branch` at
      `merge_coordinator.py:875` (verified via args-capture).
- [ ] `_on_worker_complete` mutates
      `branch_state["epic_branch"] = result.epic_branch` at
      `orchestrator.py:1005` (verified by
      `_open_pr_for_branch` seeing the key).
- [ ] `_open_pr_for_branch` reads `--base` from
      `branch_state.get("epic_branch") or self.parallel_config.base_branch`
      at `orchestrator.py:1142` (verified via `--base` value
      captured in `test_orchestrator.py:2008-2052`).
- [ ] With `epic_branches.enabled=False` (default), behavior is
      byte-for-byte identical to today — covered by the
      "falls back to base_branch" tests.
- [ ] `test_merge_coordinator.py` and `test_orchestrator.py`
      new/modified tests pass.
- [ ] Full `python -m pytest scripts/tests/` exits 0.

## Files Touched

**Implementation (2 files):**
- `scripts/little_loops/parallel/merge_coordinator.py` (lines 624
  and 875; both consumers rebind `result = request.worker_result`
  at method head)
- `scripts/little_loops/parallel/orchestrator.py` (line 1005
  mutation + line 1142 read site)

**Tests (2 files):**
- `scripts/tests/test_merge_coordinator.py` (3 new epic-branch
  tests at minimum)
- `scripts/tests/test_orchestrator.py` (args-capture extension
  at lines 2008-2052 and 2260-2321)

**Estimated file count:** 2 implementation + 2 test = **4 files**.

## Decision Rationale

Inherited verbatim from FEAT-2448 (locked in by
`/ll:decide-issue` on 2026-07-07):

### Decision 1 — `_open_pr_for_branch()` epic-branch threading

**Selected:** Option (b) — mutate
`branch_state["epic_branch"] = result.epic_branch` at
`_on_worker_complete` before invocation; read `--base` from
`branch_state.get("epic_branch") or self.parallel_config.base_branch`
at `orchestrator.py:1142`.

**Rejected:** Option (a) — add a new `epic_branch=None` kwarg
to the `_open_pr_for_branch(self, issue_id, branch_name, branch_state)`
signature.

**Reasoning:** `branch_state` is the existing carrier for
cross-call worker state; the codebase already mutates it in place
(`branch_state["pushed"] = True`). Routing `epic_branch` the
same way matches the established pattern and avoids a signature
change on `_open_pr_for_branch`.

### ARCHITECTURE-095 — do NOT extend cleanup gates

Per `.ll/decisions.yaml:3803-3810`, no epic-awareness may be
added to `prune_merged_feature_branches()` at
`worker_pool.py:1772-1790` or to the CLI mode at
`cli/parallel.py:267-287`. Epic `/*` lifecycle is owned
exclusively by FEAT-2449's `delete_epic_branch()` step. This is
out of FEAT-2453's scope but documented here so the implementer
knows not to "fix" the cleanup step.

## Codebase Research Findings

_Anchor verification (2026-07-07). Full research at FEAT-2448._

- **`_process_merge` exists** at
  `merge_coordinator.py:577`. The site at line 624 is
  `base = self.config.base_branch` for the stash-then-checkout-
  pre-merge flow. The local `result` binding is established at
  line 586 (`result = request.worker_result`).

- **`_handle_conflict` exists** at `merge_coordinator.py:808`.
  The site at line 875 is `base = self.config.base_branch` for
  the fetch+rebase retry flow. The local `result` binding is
  established at line 816 (`result = request.worker_result`).

- **`_on_worker_complete` is the single caller of
  `_open_pr_for_branch`** at `orchestrator.py:1006`, inside the
  `if self.parallel_config.open_pr_for_feature_branches:` block
  at line 1005. The `branch_state` dict is constructed at
  lines 980-984 as
  `{"branch_name": ..., "pushed": False, "pr_url": None}` —
  adding `epic_branch` to the dict (or via post-construction
  mutation at step 3) is non-invasive.

- **`ParallelOrchestrator.__init__` constructs WorkerPool +
  MergeCoordinator** at `orchestrator.py:113-118`. No constructor
  signature change needed for FEAT-2453. `MergeCoordinator.__init__`
  at `merge_coordinator.py:44` similarly takes
  `(self, *, config, repo_path, git_lock, logger, ...)` — no
  `WorkerResult.epic_branch` threading needed at construction
  time because `WorkerResult` is passed at merge-request time
  via `MergeRequest.worker_result` (built at
  `merge_coordinator.py:119`).

- **`_open_pr_for_branch` test fixture needs args-capture
  enhancement.** The existing
  `test_on_worker_complete_feature_branch_open_pr` at
  `test_orchestrator.py:2008-2052` uses an inline
  `fake_subprocess_run` that does NOT capture args (returns
  a `CompletedProcess` per command but discards the args).
  Adding a `captured_args: list[list[str]] = []` accumulator
  and an `args` append inside `fake_subprocess_run` is the
  same pattern used by `TestUpdateBranchBase` inline-`captured_cmds`
  tests at `test_worker_pool.py:1714-1794`.

- **Idempotency test at `test_orchestrator.py:2260-2321`** has
  the same `fake_subprocess_run` shape and is the natural
  second place to assert on `--base` (preserves an existing
  `pr_url`; passing the assertion catches a regression where
  epic mode accidentally re-targets an existing PR's base
  branch).

- **Gh-missing test at `test_orchestrator.py:2090-2123`**
  (`test_on_worker_complete_feature_branch_gh_missing`) does
  NOT exercise `--base` (gh is missing before `pr create` is
  reached) — args-capture there is lower priority (optional).

- **`MergeCoordinator` signature unchanged.** Both consumer
  sites at `_process_merge` (line 624) and `_handle_conflict`
  (line 875) receive `result = request.worker_result` at the
  method head (lines 586 and 816 respectively). The
  `or` idiom
  `base = result.epic_branch or self.config.base_branch`
  is byte-for-byte identical to today's behavior when
  `epic_branch is None` (the default for non-EPIC issues), so
  no behavioral change for the no-op case.

### Post-FEAT-2452 Verification (2026-07-09)

_Added by `/ll:refine-issue --auto` — anchors re-checked against the
tree after blocker FEAT-2452 landed (`749b8096`)._

- **Blocker cleared.** FEAT-2452 is `done`/Completed. FEAT-2453 is
  now unblocked; the `result.epic_branch` reads this issue adds have
  a real field to read.
- **Precondition present.** `WorkerResult.epic_branch: str | None =
  None` exists at `types.py:94`, round-trips via `to_dict`
  (`types.py:116`) and `from_dict` (`types.py:140`). No dataclass
  work remains for this child.
- **All anchors stable** despite FEAT-2452's WorkerPool changes —
  line numbers did not drift: `_process_merge`
  (`merge_coordinator.py:577`, `result` bind :586, target :624),
  `_handle_conflict` (:808, `result` bind :816, target :875),
  `_on_worker_complete` (`orchestrator.py:914`), `if
  open_pr_for_feature_branches:` (:1005) → `_open_pr_for_branch(`
  call (:1006), `_open_pr_for_branch` def (:1109), `--base` read
  (:1142). Note the step-3 mutation goes **immediately before the
  call at :1006** (the `if` guard is at :1005).
- **No partial-apply drift.** `git grep epic_branch` returns zero
  hits in `merge_coordinator.py` and `orchestrator.py` — none of the
  four read-sites are present yet, so this is a clean start.
- **Test anchors exact.**
  `test_on_worker_complete_feature_branch_open_pr` (:2008),
  `_gh_missing` (:2090), `_pr_url_idempotency` (:2260) all resolve.

## Wiring Pass — 2026-07-09

_Added by `/ll:wire-issue --auto`. Three parallel tracers (caller/importer,
side-effect surface, test-gap) run against the tree after FEAT-2452 landed.
Net result: **no missing callers, importers, manifests, config-schema, or CLI
coupling** — this is a mechanical 4-site read swap. Two test-plan corrections
and one deferred-doc flag below._

### Tests — new/corrected coverage

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_subprocess_mocks.py` — **not previously listed.**
  Constructs `MergeRequest` and calls `_process_merge` in
  `test_process_merge_uses_merge_request` (line 850) and
  `test_restash_after_pull_with_local_changes` (line 895). Both use a
  mocked-`subprocess.run` argv-capture (`captured_commands`) and filter with
  `config.base_branch in c` **containment** (not strict equality), so neither
  breaks under the `result.epic_branch or self.config.base_branch`
  substitution (epic_branch is `None` in these fixtures → byte-for-byte
  identical). `test_restash_after_pull_with_local_changes`'s mock has an
  implicit `if cmd[:3] == ["git", "checkout", config.base_branch]:` branch
  (line ~941) that would silently fall through if an epic_branch were set —
  harmless here, but note it if an epic-enabled variant is added. Action:
  verify these two pass unchanged (no edit required); optionally add an
  epic-enabled argv-capture variant here.

- **Fixture-model correction for the 3 new `test_merge_coordinator.py`
  tests.** Scope §5 / Confidence-Check Notes say to mirror
  `test_*_untracked_files_error` / `test_*_local_changes_error` at
  `test_merge_coordinator.py:702, 735, 773, 815`. Those anchors use a
  **real temp-git-repo** style (`temp_git_repo` fixture, real `subprocess`
  against the repo, assertions on `test_file.read_text()`,
  `coordinator._stash_active`, `request.retry_count`) — they do **NOT**
  capture git argv, so they cannot verify `epic_branch` was substituted into
  the `checkout`/`rebase` command. The correct template for argv-level epic
  assertions is:
  - **mocked-subprocess argv capture** →
    `test_subprocess_mocks.py::test_process_merge_uses_merge_request`
    (line 850): `captured_commands`, `mock_run` side_effect,
    `checkout_cmds = [c for c in captured_commands if "checkout" in c and <target> in c]`.
  - **epic enabled/skip/fallback triad shape** →
    `test_worker_pool.py::TestUpdateBranchBase` (lines 1831-1909) already has
    the FEAT-2452 analog: `test_update_branch_base_rebases_onto_epic_branch`
    (1831), `_epic_branch_skips_remote_fetch` (1858),
    `_no_epic_branch_uses_base_branch` (1882). Model the three new
    merge_coordinator tests on this triad, not the real-repo anchors.

- **No strict `--base == base_branch` equality break sites** exist anywhere
  in `scripts/tests/`. The three `test_orchestrator.py` sites that set
  `parallel_config.base_branch = "main"` (2017, 2287, 2520) do **not** assert
  on the `--base` argv value today — their `fake_subprocess_run` branches on
  `args[0]=="gh" and args[1]=="pr"` without inspecting `--base`. The planned
  `captured_args` accumulator is therefore purely **additive** (asserts on a
  value nothing currently checks), not a fix to a failing assertion.

- `scripts/tests/test_parallel_types.py::TestMergeRequest` (lines 424-482) —
  constructs `MergeRequest` but never calls `_process_merge`/`_handle_conflict`
  and never touches `worker_result.epic_branch`. Pure dataclass tests; **no
  change needed** (recorded so the implementer doesn't chase it).

### Documentation — deferred (out of scope, flagged only)

_Wiring pass added by `/ll:wire-issue`:_

- `docs/reference/CONFIGURATION.md:363` (`epic_branches.enabled` row) states
  the orchestrator/merge-coordinator path "is not active" until
  FEAT-2448/2449/2450 ship. Landing this child activates the 4 read-sites,
  making that sentence partially stale. **Out of scope here** — the issue
  already defers all doc updates to the paired FEAT-2452/FEAT-2450 pass; noted
  so whoever closes the FEAT-2448/2449/2450 doc pass updates this row.

### Configuration

- No `config-schema.json` changes. `epic_branches.enabled` is already a schema
  key (FEAT-2447/2452 lineage); this issue's read-sites consume runtime
  `result.epic_branch` / `branch_state["epic_branch"]` values, not config keys.
- No template changes (already stamped in FEAT-2447).

### Test files NOT requiring update (verified)

- All `WorkerResult(...)` tests in `test_worker_pool.py:120-149`,
  `test_parallel_types.py:161-359`, `test_subprocess_mocks.py`.
  These belong to **FEAT-2452** (the dataclass piece).

### Verification surface (post-implementation)

- Full `python -m pytest scripts/tests/` exits 0.
- `git grep 'result.epic_branch or self.config.base_branch'`
  matches lines 624, 875 in `merge_coordinator.py` (this issue)
  + 1 site in `worker_pool.py` (FEAT-2452 step 5 rebase
  variant) — total 3 matches.
- `git grep 'branch_state\["epic_branch"\]'` matches the mutation
  at `orchestrator.py:1005` and the read at `orchestrator.py:1142`
  — 2 matches.
- `git grep -E 'epic_branch.*None' scripts/little_loops/` matches
  the field default in `types.py` (FEAT-2452) plus the
  `or self.config.base_branch` substrings across the 3 sites —
  confirms the no-op signal is uniformly anchored.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-07 (post-decomposition)._

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 86/100 → HIGH

### Outcome Risk Factors
- **Idempotent PR re-target edge case**: the
  `test_orchestrator.py:2260-2321` idempotency test exercises
  the path where `pr_url` is already set. The args-capture
  enhancement must assert on `--base` even in the skip-PR-creep
  path — if epic mode accidentally re-targets an existing PR's
  base branch, idempotency silently breaks. Add explicit
  `assert base == "epic/EPIC-XXXX-..."` even in the early-return
  branch.
- **Test-fixture shape parity**: the 3 new merge_coordinator
  tests must mirror the exact `test_*_untracked_files_error` /
  `test_*_local_changes_error` fixture shape (merge request
  object construction, mock subprocess setup, mock logger
  capture). Cross-check `test_merge_coordinator.py:702, 735,
  773, 815` as the canonical pattern.

## Decomposition Rationale

FEAT-2448 was split into FEAT-2452 + FEAT-2453 on 2026-07-07
because the broad-fanout dataclass piece (WorkerPool + 12-return
threading + instance-state dict) sat awkwardly alongside the
clean read-site substitutions. Separating them:

| Issue | A | B | C | D | Total | Tier |
|---|---|---|---|---|---|---|
| FEAT-2448 (unsplit) | 14 | 25 | 25 | 10 | 74 | MODERATE |
| FEAT-2452 (sibling) | 14 | 25 | 25 | 10 | 74 | MODERATE |
| **FEAT-2453** (this) | 18 | 25 | 25 | 18 | **86** | **HIGH** |

FEAT-2453 ships with HIGH outcome confidence; FEAT-2452 inherits
the broad-fanout burden (irreducible without a contract change).

## Session Log
- `/ll:confidence-check` - 2026-07-09T20:00:00 - `88ef04c1-d16c-4a65-873a-b89370dd04c9.jsonl`
- `/ll:wire-issue` - 2026-07-09T19:23:32 - `25450cda-adbf-415b-afa8-1faf98287221.jsonl`
- `/ll:refine-issue` - 2026-07-09T19:01:46 - `08294d04-3d82-48ce-b783-c721bf549a4d.jsonl`

- `/ll:confidence-check` - 2026-07-07T19:55:00 - `51846f72-c135-4aae-98df-cfb6f2d84afe.jsonl` (decomposition re-validation)
- `/ll:confidence-check-decomposition` - 2026-07-07T19:55:00 - `51846f72-c135-4aae-98df-cfb6f2d84afe.jsonl`
