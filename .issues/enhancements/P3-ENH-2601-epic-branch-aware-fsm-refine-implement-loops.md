---
id: ENH-2601
type: enhancement
status: open
priority: P3
captured_at: '2026-07-11T14:29:14Z'
discovered_date: 2026-07-11
discovered_by: capture-issue
relates_to:
- ENH-2600
confidence_score: 96
outcome_confidence: 80
score_complexity: 14
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
decision_needed: false
---

# ENH-2601: FSM refine/implement loops are unaware of epic_branches and lack a post-implement verify state

## Summary

The FSM loops that do deep refine+implement for an EPIC's children
(`auto-refine-and-implement.yaml`, `sprint-refine-and-implement.yaml`,
delegating to `autodev.yaml`) accept `scope: EPIC-NNN` but operate entirely
in whatever branch/worktree is currently checked out — they never check out
or create the `epic/<EPIC-ID>-<slug>` branch that `parallel.epic_branches`
defines, and none of them has an FSM state that runs verification
(tests/lint or `/ll:verify-issues`) after implementation. Today the only way
to combine `epic_branches` with these loops is to manually
`git checkout epic/<EPIC-ID>-<slug>` first and run the loop by hand, with no
verify step at the end.

## Current Behavior

- `auto-refine-and-implement.yaml` delegates to `loop: autodev` and goes
  straight to `finalize` — no verify state.
- `sprint-refine-and-implement.yaml` delegates to `auto-refine-and-implement`
  — same gap, one level removed.
- `autodev.yaml` shells to `ll-auto --only "$CURRENT"` per issue; any
  verification is internal to `ll-auto`'s Python, not a distinct, auditable
  FSM state.
- None of the three loops read or act on `parallel.epic_branches.enabled` /
  `parallel.epic_branches.prefix`.

## Expected Behavior

1. When `scope` resolves to an EPIC and `parallel.epic_branches.enabled` is
   `true`, the loop checks out (creating if necessary) the
   `epic/<EPIC-ID>-<slug>` branch before delegating to autodev, so refine +
   implement work for all children lands on the shared integration branch
   instead of whatever branch happened to be checked out.
2. After the autodev delegate step (and before `finalize`), add a verify
   state that runs the project's `test_cmd` (and optionally `lint_cmd`, or
   delegates to `/ll:verify-issues`) against the resulting branch, recording
   the verdict in `summary.json` alongside the existing closure verdict.

## Motivation

Without this, "refine, implement, and verify all children of an EPIC on a
shared branch" (the more thorough alternative to the worker pool's
refine-lite pass, see [[ENH-2600]] for that path's own gap) requires manual,
undocumented steps and has no automated correctness check at the end —
defeating much of the point of running the deeper FSM loop instead of the
lighter worker-pool flow.

## Proposed Solution

### Option A — Create-without-switching (mirrors worker-pool precedent)

> **Selected:** Option A — preserves the documented main-tree invariant and reuses the proven `_ensure_epic_branch` git mechanic; Option B directly contradicts that invariant with no existing rollback precedent.

`checkout_epic_branch` uses `git branch <name> <base>` only — creates the
branch without switching the working-directory checkout, matching
`_ensure_epic_branch` (`scripts/little_loops/parallel/worker_pool.py:1707-1743`).
Since `auto-refine-and-implement.yaml` has no worktree isolation, the
`delegate` (autodev) step must then be made branch-aware itself — e.g. by
passing the branch name through to `ll-auto`/`ll-parallel` so per-issue work
lands there, or by adding a worktree at the epic branch for the duration of
`delegate`. Preserves the existing invariant (documented in
`orchestrator.py`'s `_merge_epic_branch_to_base` docstring) that the main
working tree stays on `base_branch` throughout automated runs.

### Option B — Checkout-and-switch (literal reading of Expected Behavior #1)

`checkout_epic_branch` runs `git checkout -b <name> <base>` (or
`git checkout <name>` if it already exists), switching the actual
working-directory branch before `delegate` runs. Simpler: `autodev`/`ll-auto`
need no branch-awareness — they operate on whatever's checked out. But this
is a more intrusive operation than any existing epic-branch code path (no
other FSM loop or `WorkerPool` code switches the main repo's branch — grep
confirms) and temporarily changes the user's active git branch for the
duration of the loop run, with no automatic restore if the loop errors mid-run.

- Add a `checkout_epic_branch` (or similarly named) state at the start of
  `auto-refine-and-implement.yaml`, gated on `scope` resolving to an EPIC ID
  and `parallel.epic_branches.enabled`. Reuse the existing branch-naming
  logic (`{prefix}{epic_id.lower()}-{slug}`) rather than reimplementing it —
  check for a shared helper in `scripts/little_loops/config/automation.py` /
  wherever `_build_parallel_epic_branches` composes branch names
  (docs/reference/API.md:3306).
- Add a `verify` state after the `delegate` (autodev) state, before
  `finalize`, running `project.test_cmd` and folding pass/fail into
  `summary.json`.
- Propagate through `sprint-refine-and-implement.yaml` since it's a thin
  delegator.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-11.

**Selected**: Option A — Create-without-switching (mirrors worker-pool precedent)

**Reasoning**: Option A reuses the proven `_ensure_epic_branch` git mechanic
(`git branch <name> <base>`, no checkout — `worker_pool.py:1707-1743`) and
preserves the invariant documented in `orchestrator.py`'s
`_merge_epic_branch_to_base` docstring that the main repo never checks out an
epic branch. Option B has zero existing precedent anywhere in the codebase
for switching the main working tree's branch, no rollback/restore-on-error
mechanism to recover a stranded checkout, and directly contradicts that
documented invariant. Option A's remaining gap — making `delegate` itself
branch-aware, since `ll-auto`/`autodev.yaml` currently has no branch/worktree
parameter — is new plumbing either way, but it's additive rather than
invariant-breaking.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A — Create-without-switching | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| B — Checkout-and-switch | 0/3 | 2/3 | 1/3 | 0/3 | 3/12 |

**Key evidence**:
- Option A: `_ensure_epic_branch` (`worker_pool.py:1707-1743`) is a direct,
  provable precedent for the create-without-switch git mechanic; the
  downstream "make `delegate` branch-aware" half has no existing free-function
  or CLI-flag precedent and must be built new, and `autodev.yaml`'s
  `singleton: true` gate is explicitly justified by a single shared main-tree
  checkout assumption a worktree-per-delegate approach would need to reconcile
  with.
- Option B: no FSM loop or `WorkerPool` code anywhere switches the main
  repo's branch (`git checkout -b`/`git checkout <branch>` returns zero
  matches across `scripts/little_loops/loops/**/*.yaml`); it directly
  contradicts the `_merge_epic_branch_to_base` docstring invariant and has no
  uncommitted-changes guard or error-triggered restore pattern to build on.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

> ⚠ `_build_parallel_epic_branches` does not exist in the codebase (grep
> confirms no such symbol) and `docs/reference/API.md:3306` does not document
> it — this reference is stale. The actual branch-naming/creation logic to
> reuse is spread across four methods on `WorkerPool`
> (`scripts/little_loops/parallel/worker_pool.py`):
> - `_resolve_branch_targets(self, issue: IssueInfo) -> tuple[str, str]`
>   (lines 1615–1641) — assembles the name: `branch = f"{prefix}{epic_id.lower()}-{slug}"`
>   where `prefix = self.parallel_config.epic_branches.prefix`.
> - `_find_nearest_epic_ancestor` (lines 1643–1653) — delegates to the
>   free function `little_loops.issue_progress.find_nearest_epic_ancestor`.
> - `_load_epic_slug` (lines 1682–1705) — scans `.issues/**/P?-{epic_id}-*.md`
>   via `IssueParser(self.br_config).parse_file()`, returns
>   `little_loops.issue_parser.slugify(info.title)` or falls back to
>   `epic_id.lower()`.
> - `_ensure_epic_branch(self, branch: str)` (lines 1707–1743) — idempotent:
>   local `rev-parse --verify` check → remote `ls-remote --heads` check →
>   create via `git branch <name> <base_branch>`.
>
> All four are pure enough to reconstruct standalone in an FSM shell action
> (no live `WorkerPool` instance required) via:
> ```python
> from little_loops.issue_progress import build_parent_map, find_nearest_epic_ancestor
> from little_loops.issue_parser import find_issues, IssueParser, slugify
> ```
> — the same idiom `resolve_set` already uses for `SprintManager`/`BRConfig`.
>
> **Design consideration**: `_ensure_epic_branch` uses `git branch <name>
> <base>`, **not** `git checkout -b` — it creates the branch without
> switching. In the parallel-execution path this is intentional: the main
> repo stays on `base_branch` throughout a run (documented in
> `orchestrator.py`'s `_merge_epic_branch_to_base` docstring), and each
> worker's isolated *worktree* is what actually checks out the epic branch.
> `auto-refine-and-implement.yaml` has no worktree isolation — it runs
> directly in the current working tree — so implementing "checks out
> (creating if necessary)" as literally described in Expected Behavior #1
> means switching the user's actual working-directory branch, which is a
> different (more intrusive) operation than anything the parallel path does
> today. Confirm this is the intended behavior before implementing, since it
> diverges from the existing epic-branch precedent.
>
> No existing FSM loop YAML contains a `git checkout -b` or `git branch`
> state (grep across `scripts/little_loops/loops/**/*.yaml` for `checkout -b`
> returned no matches); `worktree-health.yaml`'s `prune_branches`/
> `check_branches` states only list/prune, they don't create/checkout.
>
> There is no `${config.*}` FSM templating namespace — confirmed via
> `scripts/little_loops/fsm/interpolation.py`'s `InterpolationContext`
> (only `context`/`captured`/`env`). Reading
> `parallel.epic_branches.enabled`/`.prefix` (or `project.test_cmd`) inside a
> state must follow the established idiom of an inline `python3 -c "..."`
> snippet that loads `.ll/ll-config.json` directly, e.g. the `check-tests`
> state in `scripts/little_loops/loops/fix-quality-and-tests.yaml:56-76`:
> ```yaml
> check-tests:
>   fragment: shell_exit
>   timeout: 600
>   action: |
>     CMD=$(python3 -c "
>     import json, pathlib
>     p = pathlib.Path('.ll/ll-config.json')
>     cfg = json.loads(p.read_text()) if p.exists() else {}
>     raw = cfg.get('project', {}).get('test_cmd')
>     print(raw if raw else 'pytest')
>     ")
>     set -o pipefail
>     eval "$CMD" 2>&1 | tee ${context.run_dir}/ll-test-results.txt
>   on_yes: done
>   on_no: fix-tests
>   on_error: fix-tests
> ```
> `dead-code-cleanup.yaml`'s `verify_tests` state (lines 67–82) is a leaner
> variant of the same pattern. Both use `fragment: shell_exit` to turn the
> shell exit code into yes/no/error routing — the new `verify` state should
> follow the same fragment.

### Codebase Research Findings (delegate branch-awareness mechanism)

_Added by `/ll:refine-issue --auto` — resolves the Confidence Check's open risk
factor ("no single mechanism is chosen yet" for making `delegate`
branch-aware):_

> **Mechanism selected by research: worktree-per-delegate, not a branch flag
> on `ll-auto`.**
>
> `ll-auto`'s CLI surface (`add_common_auto_args`,
> `scripts/little_loops/cli_args.py:432-450`) has no `--branch`/`--worktree`/
> `--cwd` flag today, and `--config` only repoints `BRConfig`'s project root
> (`scripts/little_loops/cli/auto.py`'s `main_auto()`) — it does not
> `os.chdir()` or affect git checkout. `AutoManager`
> (`scripts/little_loops/issue_manager.py:1103`, `run()` at line 1282) calls
> `check_git_status()` and all per-issue git operations against the ambient
> working directory with no branch/cwd override parameter anywhere in its
> constructor or call chain.
>
> Two candidate mechanisms were compared:
> - **(a) New `--branch` flag on `ll-auto`, operating in the current tree** —
>   would require new branch/cwd plumbing built from scratch inside
>   `AutoManager`/`issue_manager.py` (no existing hook point), and to actually
>   land commits on the right branch `ll-auto` would need to `git checkout
>   <branch>` internally — which mutates the shared main tree's checkout for
>   the run's duration. That is exactly the rejected **Option B** pattern
>   (checkout-and-switch) this issue's own decision record already ruled out
>   for having "no rollback/restore-on-error mechanism" and contradicting the
>   `_merge_epic_branch_to_base` main-tree-never-checks-out-epic-branch
>   invariant.
> - **(b) Dedicated worktree for the epic branch, running `loop: autodev`
>   there** — reuses `worktree_utils.setup_worktree()`
>   (`scripts/little_loops/worktree_utils.py:63`), a plain-argument free
>   function (`repo_path`, `worktree_path`, `branch_name`, `git_lock`,
>   `base_branch`) already pool-independent and already used standalone by
>   three separate callers (`ll-parallel`, `ll-sprint`, and `ll-loop` per its
>   own module docstring). `scripts/little_loops/cli/loop/run.py` (~line 303)
>   already has a `getattr(args, "worktree", False)` hook point, meaning the
>   FSM runner already has *some* notion of running a loop against an
>   alternate working directory — an existing extension point option (a) has
>   no equivalent for.
>
> **Selected: (b).** It reuses two already-standalone, already
> multiply-proven code paths (`worktree_utils.setup_worktree`/
> `cleanup_worktree`, and the branch-naming/creation methods on `WorkerPool`
> — `_resolve_branch_targets`, `_find_nearest_epic_ancestor`,
> `_load_epic_slug`, `_ensure_epic_branch`, all confirmed instance-state-free
> and reconstructable without a live `WorkerPool`), and it preserves the
> main-tree-never-checks-out-epic-branch invariant exactly the way
> `_ensure_epic_branch` does today: the worktree is what checks out the
> branch, not the main repo. Option (a) would either repeat the rejected
> checkout-switch pattern or require inventing new branch/cwd-aware code
> throughout `AutoManager` with no existing precedent.
>
> **Residual gap, out of scope for this issue**: `autodev.yaml`'s
> `singleton: true` gate (`scripts/little_loops/loops/autodev.yaml` ~line 26,
> justified by BUG-2526 to prevent two concurrent `ll-auto --only` runs from
> corrupting shared `.auto-manage-state.json`/git state) is enforced purely
> by loop name in `LockManager.find_conflict()`
> (`scripts/little_loops/fsm/concurrency.py:268-285`), not scoped by
> worktree/branch. A worktree-per-delegate design does not remove this gate —
> it still blocks a second, independent `autodev` run system-wide, even one
> targeting a different epic's worktree. That's fine for this issue (only one
> `checkout_epic_branch` → `delegate` sequence runs per
> `auto-refine-and-implement` invocation), but means this change does **not**
> unlock concurrent multi-epic `autodev` runs; making the singleton gate
> worktree/branch-scoped would be separate follow-on work if that's ever
> desired.

## Implementation Steps

1. Identify the shared branch-naming helper used by `epic_branches`
   (`docs/reference/API.md:3306`, `_build_parallel_epic_branches`) and confirm
   it's importable/callable from a loop's shell action.
2. Add an opt-in checkout/create-epic-branch state to
   `auto-refine-and-implement.yaml`, gated on scope + config.
3. Add a verify state (shell action running `project.test_cmd`) between
   `delegate` and `finalize`.
4. Update `summary.json` schema to include the verify verdict.
5. Update `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch` and the
   loop's own header comment to document the new epic-branch-aware mode.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

`auto-refine-and-implement.yaml`'s state chain today is:
`init` → `resolve_set` → `delegate` → (`record_error`) → `finalize` → `done`.
Exact insertion points (`scripts/little_loops/loops/auto-refine-and-implement.yaml`):

- **`resolve_set`** (lines 72–122) already resolves `context.scope` once,
  up front, via `SprintManager(config=BRConfig(Path.cwd())).load_or_resolve(arg)`
  (lines 84–101) into a flat comma-separated `captured.issue_set` — this
  confirms the branch checkout belongs here (once), not inside autodev's
  per-issue loop. Currently `on_yes: delegate`; redirect to
  `on_yes: checkout_epic_branch` and give the new state `next: delegate`
  (or its own `on_yes`/`on_error`, since `resolve_set` is a
  `check_semantic`/routed state — check its exact `fragment`/routing keys
  before wiring).
- **`delegate`** (lines 124–139): `loop: autodev` with
  `with: {input: "${captured.issue_set.output}", skip_learning_gate: "${context.skip_learning_gate}"}`.
  Currently `on_success: finalize`, `on_failure: finalize`,
  `on_error: record_error`. Insert the new `verify` state by redirecting
  `on_success`/`on_failure` to `verify`, with `verify` itself routing to
  `finalize` on all outcomes (pass/fail folded into `summary.json`, not
  used to short-circuit finalize's own ledger-based verdict computation).
- **`finalize`** (lines 151–300): computes `VERDICT` from ledger counts
  (lines 277–289) and writes via a single `printf` (lines 291–292):
  ```
  printf '{"verdict":"%s","closed":%s,"not_closed":%s,"skipped":%s,"errored":%s,"skipped_breakdown":%s,"gate_blocked":%s,"decision_unresolved":%s,"parked_rate":%s}\n' \
    "$VERDICT" "$CLOSED" "$NOT_CLOSED" "$SKIP" "$ERR" "$SKIPPED_BREAKDOWN" "$GATE_BLOCKED" "$DECISION_UNRESOLVED" "$PARKED_RATE" > "$RUN_DIR/summary.json"
  ```
  Extend this printf with a `"verify_verdict":"%s"` field, sourced by
  reading an artifact file the new `verify` state writes under
  `${context.run_dir}` (matching the existing pattern of composing multiple
  ledger-file reads — `autodev-passed.txt`, `autodev-skipped.txt`, etc. —
  into one JSON object).

`sprint-refine-and-implement.yaml` needs **no branch-checkout logic of its
own** — it forwards `context.sprint_name` straight through as
`with: {scope: "${context.sprint_name}", ...}` to
`auto-refine-and-implement`'s `context.scope` (confirmed: `delegate` state,
lines 19–32), so a scope value of `EPIC-NNN` passes through unchanged and
the new checkout state fires automatically once added upstream. Its
`read_outcome` state (lines 34–44) already `cat`s the child's
`summary.json` back out, so the new `verify_verdict` field surfaces
automatically with no wrapper-side change needed.

No dedicated test class exists yet in `scripts/tests/test_builtin_loops.py`
for either loop (only generic coverage). Model the new "verify state exists
and routes correctly" test after the existing per-loop class pattern
(`LOOP_FILE` + `data` fixture + `test_required_states_exist` +
per-state `on_success`/`on_failure`/`on_error` routing assertions), e.g.
`TestEvaluationQualityLoop` (lines 598–701) or the `run_all` routing
assertion in `TestIssueRefinementAlias` (lines 961–967).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

6. Extend `TestAutoRefineAndImplementLoop` and `TestSprintRefineAndImplementLoop`
   in `scripts/tests/test_builtin_loops.py` (these already exist — do not
   create new test classes) — add `"checkout_epic_branch"` and `"verify"` to
   `test_required_states_exist`'s `required` set, update
   `test_delegate_crash_routes_to_record_error` (lines 1972-1979) to expect
   `delegate.on_success`/`on_failure == "verify"` instead of `"finalize"`,
   and add an additive-key test for `verify_verdict` in `summary.json`
   following the `gate_blocked`/`decision_unresolved` pattern (lines 2266-2321).
7. Update `docs/guides/LOOPS_REFERENCE.md`'s ASCII FSM-flow diagrams and prose
   for both loops to include the new `checkout_epic_branch` and `verify`
   states.
8. Update `skills/audit-loop-run/SKILL.md` Step 6a ("Summary Cross-Check") to
   document the new `verify_verdict` field alongside the existing additive-key
   list (`skipped_breakdown`, `gate_blocked`, `parked_rate`).
9. Update `scripts/little_loops/loops/README.md:33`'s catalog description of
   `auto-refine-and-implement` to mention epic-branch checkout and the verify
   step.
10. Add a CHANGELOG.md entry under the next dated release section (not
    `[Unreleased]`, per project convention).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/auto-refine-and-implement.yaml`
- `scripts/little_loops/loops/sprint-refine-and-implement.yaml`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/autodev.yaml` (delegate target, unchanged)

### Similar Patterns
- `_maybe_complete_epic` epic-branch resolution used by the worker pool
  (`scripts/little_loops/parallel/worker_pool.py`) — reuse its branch-naming
  logic rather than duplicating it.

### Tests
- `scripts/tests/` — loop validation coverage
  (`ll-loop validate`) plus a test asserting the new verify state exists and
  routes correctly.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:1877-2421` — `TestAutoRefineAndImplementLoop`
  **already exists** (contradicts this issue's earlier claim of "no dedicated
  test class exists yet") with ~30 tests covering `init`/`resolve_set`/
  `delegate`/`record_error`/`finalize`. **Extend this class**, don't create a
  new one. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:2423-2475` — `TestSprintRefineAndImplementLoop`
  **already exists**, 5 tests covering the alias/delegation pattern. Extend
  this class for any `sprint-refine-and-implement.yaml` assertions. [Agent 3
  finding]
- `scripts/tests/test_builtin_loops.py:1972-1979` —
  `test_delegate_crash_routes_to_record_error` **will break**: it asserts
  `delegate.on_success == "finalize"` and `delegate.on_failure == "finalize"`.
  Once `delegate` is rewired to route through the new `verify` state, both
  assertions must be updated to `"verify"`. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:1898-1910` — `test_required_states_exist`
  needs `"checkout_epic_branch"` and `"verify"` added to its `required` set
  once those states land. [Agent 3 finding]
- `scripts/tests/test_builtin_loops.py:2266-2321` — reference pattern for
  adding the new `verify_verdict` key to `summary.json` tests: mirrors how
  `skipped_breakdown`/`gate_blocked`/`decision_unresolved` were added
  (existence test + count-surfaces test + zero-when-absent test). Follow this
  additive-key convention rather than changing the printf's existing shape.
  [Agent 3 finding]
- No dedicated unit tests exist for `_ensure_epic_branch`,
  `_find_nearest_epic_ancestor`, or `_load_epic_slug` individually in
  `test_worker_pool.py` (only `_resolve_branch_targets` has coverage, lines
  3416-3602) — if any of this logic is extracted into a shared helper for the
  new `checkout_epic_branch` state, it needs fresh unit tests; there's no
  existing template to mirror beyond `_resolve_branch_targets`'s test class
  shape. [Agent 3 finding]
- Reference patterns to follow: `TestEvaluationQualityLoop`
  (`test_builtin_loops.py:598-701`) for the `LOOP_FILE`/`data` fixture +
  `test_required_states_exist` shape (already reused in
  `TestAutoRefineAndImplementLoop`); `TestIssueRefinementAlias.test_run_all_routes_all_outcomes_to_done`
  (`test_builtin_loops.py:961-967`) for the per-field `on_success`/
  `on_failure`/`on_error` routing-assertion pattern to mirror when asserting
  `delegate`'s new routing to `verify`. [Agent 3 finding]

### Documentation
- `docs/guides/SPRINT_GUIDE.md#per-epic-integration-branch`

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_REFERENCE.md` — contains full prose + ASCII "FSM flow"
  diagrams for both loops (`### sprint-refine-and-implement`,
  `### auto-refine-and-implement`) enumerating the exact state sequence
  (`delegate → read_outcome/record_crash → done`;
  `init → resolve_set → delegate → finalize → done`). Both diagrams go stale
  once `checkout_epic_branch` and `verify` are added — needs updating. [Agent
  2 finding]
- `skills/audit-loop-run/SKILL.md` (Step 6a "Summary Cross-Check") —
  enumerates specific `summary.json` keys by name for these two loops
  (`closed`, `skipped_breakdown`, `gate_blocked`, `parked_rate`) and
  documents the additive-field convention explicitly ("these three keys are
  additive; older `summary.json` files ... will lack them"). This is the
  natural site to document the new `verify_verdict` field, following its own
  stated pattern. [Agent 2 finding]
- `scripts/little_loops/loops/README.md:33` — one-line catalog description of
  `auto-refine-and-implement` doesn't mention epic-branch checkout or a
  verify step; minor drift once the states are added. [Agent 2 finding]
- `CHANGELOG.md` — per established project convention, a new entry belongs
  under a new dated release section, not `[Unreleased]`. [Agent 2 finding]
- Confirmed **no changes needed** (read-only prior art / already complete):
  `docs/development/MERGE-COORDINATOR.md` and `docs/reference/CONFIGURATION.md`
  document the existing `ll-parallel`/`WorkerPool` consumer of `epic_branches`
  only — canonical reference for the branch-naming convention being mirrored,
  not a file this issue needs to edit. `scripts/little_loops/config-schema.json`'s
  `epic_branches` object is already fully defined (`enabled`, `prefix`,
  `merge_to_base_on_complete`, `open_pr`) — no schema changes needed since the
  new states only read existing config fields. [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/parallel/worker_pool.py:1615–1743` — corrected
  target: `_resolve_branch_targets`, `_find_nearest_epic_ancestor`,
  `_load_epic_slug`, `_ensure_epic_branch` (no `_maybe_complete_epic` in
  this file — that lives in `orchestrator.py`, see below).
- `scripts/little_loops/parallel/orchestrator.py:1208–1336` —
  `_maybe_complete_epic` (completion trigger, calls `_merge_epic_branch_to_base`
  or `_open_pr_for_epic_branch`) and `_merge_epic_branch_to_base` (its
  docstring documents the "main repo never checks out the epic branch"
  invariant referenced under Proposed Solution above).
- `scripts/little_loops/config/automation.py` — `EpicBranchesConfig`
  dataclass (`enabled`, `prefix`, `merge_to_base_on_complete`, `open_pr`
  fields) and `ParallelAutomationConfig`.
- `scripts/little_loops/issue_progress.py` — `find_nearest_epic_ancestor`,
  `build_parent_map` (free functions, importable standalone).
- `scripts/little_loops/issue_parser.py` — `slugify`, `find_issues`,
  `IssueParser` (free functions/class, importable standalone).
- `scripts/little_loops/loops/fix-quality-and-tests.yaml:56-76` (`check-tests`
  state) and `scripts/little_loops/loops/dead-code-cleanup.yaml:67-82`
  (`verify_tests` state) — reference patterns for the new `verify` state:
  `fragment: shell_exit`, inline-Python config read, `set -o pipefail` +
  `tee ${context.run_dir}/...` to capture output.
- `scripts/little_loops/fsm/interpolation.py` — confirms no `${config.*}`
  templating namespace exists; config values must be read via inline Python
  against `.ll/ll-config.json`, not FSM interpolation.
- `scripts/tests/test_worker_pool.py` (~lines 3416–3602) — existing unit
  tests for `_resolve_branch_targets`, useful as a reference if any part of
  the branch-naming logic gets extracted into a shared helper module.
- `scripts/tests/test_builtin_loops.py` — no existing test class for
  `auto-refine-and-implement.yaml` or `sprint-refine-and-implement.yaml`;
  add one following the established `LOOP_FILE`/`data` fixture pattern.

## Impact

- **Priority**: P3 — no active user blocked, but closes a real functionality
  gap between two shipped features that are documented as if they compose.
- **Effort**: Medium — touches loop YAML control flow (new states, routing)
  plus a shared branch-naming helper; larger than [[ENH-2600]].
- **Risk**: Low-medium — new states are additive and gated behind existing
  config; default (`epic_branches.enabled: false`) behavior is unchanged.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| docs/guides/SPRINT_GUIDE.md | Per-EPIC integration branch user-facing docs |
| docs/reference/API.md | `_build_parallel_epic_branches` branch-naming helper |

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-11_

**Readiness Score**: 96/100 → PROCEED
**Outcome Confidence**: 76/100 → MODERATE

The previously flagged open decision (Option A vs. Option B) was resolved by
`/ll:decide-issue` on 2026-07-11 in favor of Option A — this re-check reflects
that resolution. State-chain claims (`resolve_set`/`delegate`/`finalize` line
ranges, `on_yes: delegate` at line 120, `on_success`/`on_failure: finalize` at
137–138) and test-class claims (`TestAutoRefineAndImplementLoop` at line 1877,
`test_delegate_crash_routes_to_record_error` at line 1972,
`TestSprintRefineAndImplementLoop` at line 2423) were spot-checked against the
current codebase and confirmed accurate.

### Outcome Risk Factors
- ~~Option A's own scoring notes that the "make `delegate` branch-aware" half
  is still described as alternatives ("passing the branch name through to
  `ll-auto`/`ll-parallel`" **or** "adding a worktree at the epic branch") —
  no single mechanism is chosen yet. Pick one before implementing
  `checkout_epic_branch`/`delegate`'s branch-aware wiring.~~ **Resolved by
  `/ll:refine-issue --auto` research (2026-07-11)**: worktree-per-delegate
  selected over a branch flag on `ll-auto` — see "Codebase Research Findings
  (delegate branch-awareness mechanism)" above. `ll-auto` has no cwd/branch
  override surface to build on, whereas `worktree_utils.setup_worktree()` is
  already a standalone, thrice-proven free function and `ll-loop run.py`
  already has a `worktree` arg hook point.
- Moderate depth on the routing rewire: `delegate`'s `on_success`/
  `on_failure` targets change from `finalize` to `verify`, and
  `test_delegate_crash_routes_to_record_error` must be updated in lockstep —
  a missed test update would pass locally but silently break routing
  assertions elsewhere in the same test module.

## Session Log
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `a9ba0748-bc8c-4087-8f47-2ec3d3701d19.jsonl`
- `/ll:refine-issue` - 2026-07-11T15:29:35 - `bfcd3543-700a-432c-862f-c761278d305f.jsonl`
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `23b4bb5a-ecba-4362-88e9-909c549f5c36.jsonl`
- `/ll:decide-issue` - 2026-07-11T15:16:48 - `706d6654-db64-40df-b677-8a48bde3af79.jsonl`
- `/ll:refine-issue` - 2026-07-11T15:12:47 - `706d6654-db64-40df-b677-8a48bde3af79.jsonl`
- `/ll:confidence-check` - 2026-07-11T00:00:00 - `a037043a-980c-469e-a388-346e3be56fb4.jsonl`
- `/ll:wire-issue` - 2026-07-11T15:03:19 - `e0bf89ca-4b80-4a16-b3ef-934e7b0d1d70.jsonl`
- `/ll:refine-issue` - 2026-07-11T14:57:39 - `25c52cc1-8aa6-4aae-a372-86bac559283c.jsonl`
- `/ll:capture-issue` - 2026-07-11T14:29:14Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ad4feb6f-5337-496b-9c18-ce805ea7bc9f.jsonl`

---

## Status

- [ ] Not started
