---
id: ENH-3302
type: ENH
title: Guard epic branch reuse against staleness relative to fork base
priority: P2
status: done
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T19:19:05Z'
completed_at: '2026-08-23T23:39:19Z'
decision_needed: false
confidence_score: 95
outcome_confidence: 73
score_complexity: 12
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 19
---

# ENH-3302: Guard epic branch reuse against staleness relative to fork base

## Summary

`_ensure_epic_branch` (`scripts/little_loops/parallel/worker_pool.py:1938`) is strictly create-if-missing: when `git rev-parse --verify <branch>` succeeds it reuses the existing `epic/*` integration branch as-is — no fast-forward, no merge of the fork base, not even a warning that the branch is behind. A branch held open by a failed merge becomes a frozen snapshot: every later run attaches sub-loop worktrees (`fsm/executor.py:961`, `checkout_existing=True`) to that stale tree.

**The same create-if-missing logic exists a second time**, as inline Python in the
`checkout_epic_branch` state of `scripts/little_loops/loops/auto-refine-and-implement.yaml:182-283`
(rev-parse → ls-remote → `git branch <branch> <base>`, then `delegate` attaches a `worktree:` to
the result). **This YAML path — not `WorkerPool` — is the one the observed incident went through**
(the run dir's `epic-branch-name.txt` is written only by that state). Both sites must share the
fix.

Observed 2026-08-23: `epic/epic-3041-host-agnostic-advisor` was created 2026-08-08 off then-current main (`d93ce3e8f`) and held open when its merge verify failed. This morning's `sprint-refine-and-implement` run reused it ~448 commits behind main. The worktree's stale `.issues/` tree (predating main's issue re-anchoring, commit `731af505` era) caused 5 of 8 skips (`refine_failed` — "FEAT-3118 does not exist", "depends_on unknown issue FEAT-3120") and 11 false-negative verify failures (all pass on current main). Run: `.loops/runs/sprint-refine-and-implement-20260823T093038/`.

## Current Behavior

Docstring of the reuse path (`worker_pool.py:1939`):

```
Lazily create ``branch`` off ``base`` if it does not exist yet.
```

Steps: in-memory cache hit → local `rev-parse --verify` hit → remote `ls-remote` hit → else `git branch <branch> <base>`. All three "exists" paths return with zero staleness inspection.

## Expected Behavior

On a reuse hit, a shared `worktree_utils.ensure_epic_branch()` helper (called from both
`WorkerPool._ensure_epic_branch` and the `checkout_epic_branch` YAML state) measures how far the
branch is behind its resolved fork base and, whenever `N > 0`, logs a warning naming the branch,
base ref, and commit count. With `refresh_on_reuse: merge` (**the default**), it additionally
merges the base into the epic branch (via a scratch worktree — see Proposed Solution) before any
worker dispatches or sub-loop worktree attaches; a merge conflict aborts the merge (clean tree,
branch SHA unchanged) and degrades to warn without aborting the run. `warn` measures and logs
only (no git state changed). `off` disables the check entirely. `N == 0` short-circuits: no
merge, no event, no artifact.

Surfacing differs by call site: `WorkerPool` emits a `parallel.epic_branch_stale` event; the
YAML path (no `EventBus` in an inline action) writes `${context.run_dir}/epic-branch-stale.txt`
and logs to stderr.

## Motivation

Branch persistence across runs is by design (an epic integration branch accumulates children until the epic merges), but silent staleness turns a single held-open merge into a cascade: refine failures, bogus dependency-graph errors, verify false negatives, and (see the companion BUG) issue-ID collisions. The failure is invisible until a human diffs the branch point.

Scope note: `merge` mode refreshes the stale tree but does not address *why* the branch was held
open (its own merge-to-base failed verify). Unwedging the epic itself is out of scope here — see
the companion BUG and the epic-merge verify path; nobody should expect this guard to resolve the
original wedge, only to stop it from silently poisoning later runs.

## Scope Boundaries

Out of scope for this issue (already decided in Proposed Solution / Decision Rules, called out here
per the required section):

- **Remote-hit reuse path** (`ls-remote` hit, no local ref) — `rev-list --count` can't resolve
  `<branch>` locally without a prior `git fetch`; left unchanged, limitation noted in the docstring.
- **Unwedging the epic branch itself** — the reason a branch is held open (its own merge-to-base
  failing verify) is not addressed here; see the companion BUG and the epic-merge verify path.
- **Numeric staleness threshold config** — no `commits_behind` tuning knob; any `N > 0` triggers
  the warn/merge response, `refresh_on_reuse: off` is the only opt-out.

## Proposed Solution

**Shared helper (2026-08-23 review decision).** Extract the exists-check + staleness + optional
merge into one free function in `worktree_utils.py`, alongside `resolve_epic_base` /
`resolve_epic_branch_name` that both call sites already import:

```python
@dataclass(frozen=True)
class EpicBranchStatus:
    branch: str
    base: str
    created: bool                # True on the create path; staleness fields are then 0/"created"
    commits_behind: int
    action: Literal["created", "fresh", "warned", "merged", "merge_conflict", "off"]
    detail: str | None = None    # conflict file list / merge stderr on merge_conflict

def ensure_epic_branch(
    branch: str, base: str, *, repo_path: Path, git_lock: GitLock, logger: Logger,
    remote_name: str, refresh_on_reuse: str, run_dir: Path | None = None,
) -> EpicBranchStatus: ...
```

`WorkerPool._ensure_epic_branch` becomes a thin wrapper (cache check → helper → emit event from
the returned status). The `checkout_epic_branch` state in `auto-refine-and-implement.yaml`
replaces its inline rev-parse/ls-remote/branch block with one call, passing
`run_dir=Path("${context.run_dir}")` and `refresh_on_reuse=epic_cfg.refresh_on_reuse`, and
writes `epic-branch-stale.txt` from the status when `action` is `warned`/`merge_conflict`. Also
fix the stale `worker_pool.py:1707-1743` line citation at `auto-refine-and-implement.yaml:184`.

Because the YAML path has a real `run_dir`, the ENH-2643 conflict-artifact persistence pattern
(`merge-conflicts.txt` / `merge-detail.txt` / `merge-returncode.txt`, `worktree_utils.py:672-684`)
**is** in scope for the helper when `run_dir` is passed — `WorkerPool` passes `None` and gets
the event payload instead.

Staleness is measured on the local-hit reuse path (remote-hit path excluded — see caveat below),
using the `base` value already passed in from `_resolve_branch_targets`'s `resolve_epic_base()`
call (`worker_pool.py:1865`) — the accurate fork base already reaches this method, so no
additional base-resolution work is needed.

Measure with `self._git_lock.run(["rev-list", "--count", f"{branch}..{base}"], cwd=self.repo_path,
timeout=10)`, following the existing local-op timeout convention in this method (10s for
read-only local plumbing, `worker_pool.py:1956`). No existing `rev-list --count` call in the
codebase measures this direction (base-ahead-of-branch) — the two existing uses
(`orchestrator.py:516-521`, `cli/loop/run.py:516`) measure the opposite (branch-ahead-of-base),
so this is new code, not an extension of a shared helper.

**Remote-hit path caveat**: on the remote-only-exists path (`ls-remote` hit, no local ref),
`rev-list --count <branch>..<base>` fails — `<branch>` does not resolve locally, and `ls-remote`
does not update remote-tracking refs, so `<remote>/<branch>` may not resolve either without a
prior `git fetch`. `merge` mode would additionally need a local branch created from the remote
ref first. **Decision: scope the staleness guard to the local-hit path only.** The observed
failure was a local branch; the remote-hit path adds a fetch + ref-naming + branch-creation
surface for no demonstrated need. Leave the remote-hit path unchanged and note the limitation in
the docstring.

**Threshold decision: `N > 0`, no numeric config knob.** Any commit count behind base is worth a
log line; the observed failure was ~448 commits (no plausible tuning range), and a numeric field
would add a fifth declaration site (two dataclasses + bridge + schema + docs) for no known use
case. `refresh_on_reuse: off` is the opt-out.

**Default decision: `merge`, not `warn` (2026-08-23 review).** Every reuse site is unattended
(`WorkerPool` workers, the autonomous YAML loop); a warning nobody reads mid-run yields the exact
incident outcome plus one log line. The base→epic merge is inevitable — it must happen before the
epic can land — so `merge` only moves it earlier, to the point where a fresh tree matters, and
surfaces latent conflicts while the run can still skip cleanly instead of producing false-negative
verifies. Its worst case *is* `warn` mode (conflict → `merge --abort` → clean tree → warn +
signal → proceed). "Default changes no git state" is not a principle this subsystem holds:
`_ensure_epic_branch` already creates branches and `merge_epic_branch_to_base` already merges and
deletes them; mutating `epic/*` is its job. The happy-path delta is one merge commit on an
`epic/*` branch that exists to accumulate commits; `base` is never touched.

Caveat to make visible: an epic branch left in `merge_conflict` fallback is *still stale* and the
run still proceeds on it — that is the one case where a human must intervene, so the
`merge_conflict` action must be prominent in the run summary / `epic-branch-stale.txt`, not just
a log line.

**Merge mechanics: scratch worktree required.** `merge_epic_branch_to_base()` works because the
main repo is already checked out on the merge *target* (`base_branch`, per its own docstring).
The reversed merge this issue needs — base *into* `epic/*` — targets a branch that is not
checked out anywhere (the main repo stays on base throughout a run), and plain `git merge` only
operates on HEAD. A fast-forward-only ref update (`git fetch . <base>:<branch>`) refuses in the
normal case, since a held-open epic branch has its own commits. So `merge` mode must:
`setup_worktree(..., checkout_existing=True)` on the epic branch (the verify gate's existing
pattern, `worktree_utils.py:159` / `run_epic_verify_gate`), run `git merge --no-edit <base>`
inside it following `merge_epic_branch_to_base()`'s conflict-detect → `merge --abort` →
return-`False` skeleton (`worktree_utils.py:612-689`), then `cleanup_worktree(...,
delete_branch=False)` in a `finally`. Note: `WorkerPool` has no `run_dir` attribute (only
`run_id`, `worker_pool.py:152-170`), so on the `WorkerPool` path conflict detail goes into the
event payload and log line; the ENH-2643 artifact persistence fires only when the helper is
given a `run_dir` (the YAML path).

Two mechanics the reversed-`TestMergeEpicBranchToBase` precedent already handles — cite, don't
rediscover: (a) the merge must pass both `--no-edit` and an explicit
`-m "Merge <base> into <branch> (ENH-3302 refresh)"`, mirroring `merge_epic_branch_to_base()`, so
no editor is invoked under automation; (b) test repos need a committer identity
(`user.name`/`user.email`) for the merge commit to succeed.

Per-run semantics: `WorkerPool._epic_branches_created` caches the check once per pool instance,
and `checkout_epic_branch` runs once per loop run — so the guard fires **once per run per
branch**, at branch first-touch, on both paths. Do not add a per-dispatch re-check.

**Event contract** (`WorkerPool` path; applies in both `warn` and `merge` modes — the event is
the run-summary signal, not a merge-mode extra; the YAML path has no `EventBus` and uses
`epic-branch-stale.txt` + stderr with the same fields instead): emit `parallel.epic_branch_stale` (namespaced for
`EventBus.register("parallel.*")` glob filtering, matching `parallel.worker_completed`) with
payload `{branch, base, commits_behind, mode, action: "warned"|"merged"|"merge_conflict"}` so
run summaries and audit tooling can distinguish warned / merged / conflict-degraded outcomes.

Gate the response on a new `refresh_on_reuse: warn|merge|off` field, added consistently across
all four sites this codebase requires for any `EpicBranchesConfig` field: the runtime dataclass
(`types.py:322`), its automation-config mirror (`config/automation.py:57`), the hand-written
bridge that translates between them (`_build_parallel_epic_branches()`, `config/core.py:690`),
and the JSON schema block (`config-schema.json:404`, `additionalProperties: false` requires the
new key be declared explicitly). Follow `test_config.py:451-485`'s existing parity/defaults/
round-trip test shape for the new field.

In `merge` mode, reconcile using the same merge/conflict-detect/abort/return-`False` skeleton
`merge_epic_branch_to_base()` already implements (`worktree_utils.py:612-689`) — note the merge
direction is reversed from that function (this issue merges base into the epic branch, not epic
branch into base), so the skeleton is a shape to follow, not a function to call directly.

**Option A**: Emit the staleness/reconcile outcome only via `self.logger`, following the existing
logging convention `_resolve_branch_targets` already uses for analogous "detected X, took action
Y" messages (`worker_pool.py:1806-1810`). No `WorkerPool` constructor change needed —
`WorkerPool` holds no `_event_bus` reference today (`worker_pool.py:145-197`).

**Option B**: Thread `event_bus` into `WorkerPool.__init__` (mirroring how `ParallelOrchestrator`
already passes it to other collaborators, e.g. `orchestrator.py:1113`, `:1544`) and emit an
`parallel.epic_branch_stale` event via `EventBus.emit()` (`events.py:117-138`), following the plain-dict
`{"event", "ts", ...payload}` shape used at `orchestrator.py:1280-1291`. This additionally
requires registering the new event type in two more registries this codebase enforces by test:
`SCHEMA_DEFINITIONS` (`generate_schemas.py:600`, count-asserted by
`test_generate_schemas.py:17-19`) and `DES_VARIANTS` (`observability/schema.py`,
coverage-asserted by `test_des_schema.py:30-66`).

> **Selected:** Option B — direct precedent for every piece of the mechanism (constructor-injected
> `event_bus`, `EventBus.emit()` dict shape, `SCHEMA_DEFINITIONS`/`DES_VARIANTS` registration), and
> it's the only option that satisfies the issue's own requirement that run summaries and `ll-loop`
> audit tooling be able to surface the staleness event structurally.

**Recommended**: Option B — the issue's own Expected Behavior/Motivation explicitly asks for a
structured event "so run summaries and `ll-loop` audit tooling can surface it," which a log line
alone does not satisfy; the extra registry updates are mechanical and test-guided.

### Decision Rationale

**Selected**: Option B (event bus + structured `parallel.epic_branch_stale` event)

Option B scores higher primarily on Consistency and Testability: every element of the mechanism
(constructor-injected `event_bus`, `EventBus.emit()`'s plain-dict shape, `SCHEMA_DEFINITIONS` and
`DES_VARIANTS` registration) has a direct, current precedent in `orchestrator.py` and
`generate_schemas.py`, and the resulting event is trivially assertable the way
`parallel.worker_completed` already is. Option A is simpler and requires no constructor change,
but it leaves the issue's own stated consumer — "run summaries and `ll-loop` audit tooling" —
unserved, since nothing in this codebase parses `WorkerPool` log lines structurally, and
`test_worker_pool.py` has no `caplog` convention to build on.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 3 |
| Simplicity | 3 | 1 |
| Testability | 1 | 3 |
| Risk | 2 | 2 |
| **Total** | **8/12** | **9/12** |

Key evidence: `WorkerPool.__init__` (`worker_pool.py:145-197`) holds no `_event_bus` today, unlike
`ParallelOrchestrator` (`orchestrator.py:99,111,122`); the sibling class already solves the
identical "surface a detected condition to tooling" problem via `EventBus.emit()`
(`orchestrator.py:1280-1291`, `:1831-1842`). `SCHEMA_DEFINITIONS` is count-asserted
(`test_generate_schemas.py:19`, currently 41) and `DES_VARIANTS` coverage-asserted
(`test_des_schema.py:37-54`) — both must be updated in lockstep with the new event type, which is
mechanical but not optional.

## Program Design

### Types
N/A — no new data type; a new field is added to two existing dataclasses
(`EpicBranchesConfig` in both `parallel/types.py:322` and `config/automation.py:57`).

### Signatures
- `worktree_utils.ensure_epic_branch(branch: str, base: str, *, repo_path: Path, git_lock: GitLock, logger: Logger, remote_name: str, refresh_on_reuse: str, run_dir: Path | None = None) -> EpicBranchStatus` — new shared helper (see Proposed Solution).
- `WorkerPool._ensure_epic_branch(self, branch: str, base: str) -> None` — existing signature at
  `worker_pool.py:1938`, becomes a wrapper over the helper; no signature change needed since `base`
  (the resolved fork base) is already passed in by the sole caller.
- `GitLock.run(args: list[str], cwd: Path, timeout: float = 30, ...) -> subprocess.CompletedProcess[str]` — existing signature at
  `git_lock.py:81`, the call surface a new `["rev-list", "--count", f"{branch}..{base}"]`
  invocation would use.

### Call Path
`_resolve_branch_targets` (`worker_pool.py:1871`) -> `_ensure_epic_branch(branch, base)`
(`worker_pool.py:1938`) -> [new, local-hit path only] `git rev-list --count <branch>..<base>` via
`self._git_lock.run(...)` -> (if `refresh_on_reuse == "merge"` and count > 0)
`setup_worktree(..., checkout_existing=True)` on the epic branch -> `git merge --no-edit <base>`
inside the scratch worktree, conflict-detect/abort skeleton per `merge_epic_branch_to_base()`
(`worktree_utils.py:612`) -> `cleanup_worktree(..., delete_branch=False)` in a `finally` ->
[new] `parallel.epic_branch_stale` emission via `EventBus.emit()` (both `warn` and `merge`
modes; see Event contract in Proposed Solution).

### Decision Rules
- Gap kind: staleness threshold and reconcile mode.
- Exact input: `git rev-list --count <branch>..<base>` result `N` (commits `base` has that
  `branch` lacks).
- Threshold: **DECIDED — `N > 0`, no numeric config knob.** Any staleness warrants the log
  line/event; the observed failure was ~448 commits with no plausible tuning range, and a
  numeric field would add a fifth declaration site for no known use case. `refresh_on_reuse:
  off` is the opt-out.
- Default: **DECIDED — `merge`** (see "Default decision" in Proposed Solution). `warn` is the
  no-git-state-change opt-down; `off` the opt-out.
- Call sites: **both** `WorkerPool._ensure_epic_branch` and the `checkout_epic_branch` YAML state
  go through `worktree_utils.ensure_epic_branch()`; the YAML path is the primary target.
- Mode values: `warn|merge|off` (issue-proposed) — no existing schema enum in this codebase uses
  `merge` as a value; the two closest precedents disagree on vocabulary
  (`code_query.staleness`: `strict|warn|off`, `config-schema.json:1396-1401`; `tamper_guard.mode`:
  `off|warn|block`, `config-schema.json:1167-1170`). Keep `warn|merge|off`: `merge` is a
  genuinely new action neither precedent vocabulary covers.
- Scope: local-hit reuse path only. The remote-hit path (`ls-remote` hit, no local ref) cannot
  run the check as written (`<branch>` unresolvable locally; `ls-remote` does not update
  remote-tracking refs) and stays unchanged — limitation noted in the docstring.
- Escape hatch: on merge conflict in `merge` mode, fall back to warn without aborting the run
  (per Desired Behavior) — this is exactly the shape `merge_epic_branch_to_base()` already
  implements (conflict -> `git merge --abort` -> return `False` -> caller logs, doesn't raise),
  executed inside the scratch worktree.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` — new `EpicBranchStatus` dataclass + `ensure_epic_branch()`
  free function (exists-check, staleness, optional scratch-worktree merge, optional ENH-2643
  artifacts); lives beside `resolve_epic_base` (69) / `merge_epic_branch_to_base` (612).
- `scripts/little_loops/parallel/worker_pool.py` — `_ensure_epic_branch` (1938-1977): becomes
  cache-check → `ensure_epic_branch()` → event emission; staleness applies on the local-hit reuse
  path only; the remote-hit path stays unchanged (see Decision Rules — no local ref to measure or
  merge against).
- `scripts/little_loops/loops/auto-refine-and-implement.yaml` — `checkout_epic_branch` (182-283):
  replace the inline rev-parse/ls-remote/branch block with `ensure_epic_branch(...,
  run_dir=run_dir)`; write `epic-branch-stale.txt` on `warned`/`merge_conflict`; fix the stale
  `worker_pool.py:1707-1743` citation at `:184`. `finalize` should surface `merge_conflict`
  prominently in the run summary.
- `scripts/little_loops/parallel/types.py` — `EpicBranchesConfig` (322-349): add `refresh_on_reuse`
  field alongside `enabled`, `prefix`, `merge_to_base_on_complete`, `open_pr`, `verify_before_merge`.
- `scripts/little_loops/config/automation.py` — a second, separately-declared
  `EpicBranchesConfig`-shaped dataclass (57-81) with its own `from_dict()`; must gain the same
  field independently — it is not the same class as `types.py`'s.
- `scripts/little_loops/config/core.py` — `_build_parallel_epic_branches()` (690-712), the
  hand-written bridge translating the automation-side dataclass fields to the runtime-side
  dataclass field by field; must add the new field to this translation explicitly.
- `scripts/little_loops/config-schema.json` — `parallel.epic_branches` object (404-435,
  `additionalProperties: false` at 434) — add a `refresh_on_reuse` property entry.

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py:1871` — `_resolve_branch_targets`, the sole
  caller of `_ensure_epic_branch`; resolves `epic_base` via `resolve_epic_base` (1865) and
  `branch` via `resolve_epic_branch_name` (1864) before calling it.
- `scripts/little_loops/parallel/orchestrator.py:39` — imports `worker_pool`.
- `scripts/little_loops/parallel/__init__.py:33` — imports `worker_pool`.
- `scripts/tests/test_worker_pool.py:34`, `scripts/tests/test_cli_loop_worktree.py:19` — test
  importers of `worker_pool`.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/parallel/orchestrator.py:133-143` — `Orchestrator.__init__` constructs
  `WorkerPool(parallel_config, br_config, self.logger, self.repo_path, self._git_lock, run_id=...,
  driver=...)` with no `event_bus` argument, even though `self._event_bus` is already set at
  `orchestrator.py:122` (from the `event_bus: EventBus | None = None` constructor param at
  `:99`). If Option B adds an `event_bus` param to `WorkerPool.__init__`, this is the one
  production call site that must pass `event_bus=self._event_bus` or the new `parallel.epic_branch_stale`
  event never reaches the Orchestrator's bus/transports. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/parallel.py:206,288` — two more `WorkerPool(...)` construction sites
  (`--cleanup` and `--prune-merged-branches` CLI branches), both positional, neither with an
  `EventBus` in scope; safe as long as the new `event_bus` param is appended last with a
  `None` default (matching the existing `run_id`/`driver` convention). [Agent 1 + Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:202,248,636,696` — inline FSM Python
  action blocks import and call `resolve_epic_base(...)` / `merge_epic_branch_to_base(...)`
  directly from `worktree_utils`, duplicating logic parallel to `_ensure_epic_branch` outside
  `worker_pool.py`; comments at lines 25/184 reference `_ensure_epic_branch` by name.
  **IN SCOPE — primary target (2026-08-23 review):** this is the path the observed incident took;
  the `checkout_epic_branch` state (`:182-283`) must call the shared `ensure_epic_branch()`
  helper. [Agent 1 finding; escalated on review]
- `scripts/little_loops/cli/sprint/run.py:265-283` — `_run_epic_base_preflight` (FEAT-2652)
  performs a different, earlier-timing epic-base validation (asserts a declared `base_branch:`
  frontmatter ref exists pre-dispatch) — not a required change, but the nearest existing
  precedent for "epic base validation failing the run" if staleness ever needs a pre-dispatch
  check rather than only the first-worker-touch check this issue implements. [Agent 2 finding]

### Conventions in Force
- Commit-count comparisons between two refs use `git rev-list --count <a>..<b>` through the
  shared `GitLock` wrapper, parsed as `int(...) if returncode == 0 else 0` — evidence:
  `orchestrator.py:516-521` (`_inspect_worktree`), `cli/loop/run.py:516`. Both existing uses
  measure branch-ahead-of-base; neither measures the base-ahead-of-branch direction this issue
  needs.
- A config knob on `EpicBranchesConfig` is declared in four places plus a dedicated
  parity/defaults/round-trip test, not just the dataclass + schema — evidence: `types.py:322-349`,
  `config/automation.py:57-81`, `config/core.py:690-712` (bridge), `config-schema.json:404-435`,
  `test_config.py:451-485`.
- Enum-style mode config fields exist in two disagreeing shapes in this schema:
  `strict|warn|off` (`code_query.staleness`, `config-schema.json:1396-1401` — the closest
  staleness-specific precedent) vs `off|warn|block` (`tamper_guard.mode`,
  `config-schema.json:1167-1170`). No existing enum uses `merge` as a value.
- Structured events go through `EventBus.emit()` with a plain dict (`"event"`, `"ts"`, payload
  keys) — evidence: `orchestrator.py:1280-1291`, `:1831-1842` — and every event type must
  additionally register in `SCHEMA_DEFINITIONS` (`generate_schemas.py:600`, count-asserted by
  `test_generate_schemas.py:17-19`) and `DES_VARIANTS` (`observability/schema.py`,
  coverage-asserted by `test_des_schema.py:30-66`). `WorkerPool` itself holds no `_event_bus`
  reference today, unlike `ParallelOrchestrator` — evidence: `worker_pool.py:145-197`.
- A working merge-with-conflict-fallback skeleton already exists: `merge_epic_branch_to_base()`
  (`worktree_utils.py:612-689`) runs `git merge --no-ff`, detects conflicts via
  `git diff --diff-filter=U`, runs `git merge --abort` on failure, and returns `False` rather than
  raising. Its merge direction is the opposite of what this issue needs, so it is a shape to
  follow, not a function to call as-is.

### Tests
- No existing unit test targets `_ensure_epic_branch` by name in `test_worker_pool.py` (confirmed
  by search — implementation-only matches).
- Git-repo-fixture convention: per-file local `_git()`/`_init_repo()` helper pairs (not shared
  across files) drive real temp git repos rather than mocking subprocess — evidence:
  `test_worktree_utils.py:35-52` (uses shared `copy_git_template` from `tests/helpers.py`).
  `test_worktree_utils.py:610-756` (`TestMergeEpicBranchToBase`) is the direct precedent for
  testing a merge+conflict scenario against a real repo, including the clean-tree-after-abort
  assertion.
- `test_config.py:451-485` (`test_epic_branches_defaults`, `test_epic_branches_from_dict`,
  `test_epic_branches_partial_dict_uses_defaults`), `:889-895` (round-trip through `to_dict()`),
  `:1247-1301` (`create_parallel_config` override tests) — pattern to replicate for the new field.
- `test_config_schema.py:1048` (`test_parallel_epic_branches_in_schema`) — schema-declares-the-key
  assertion to extend.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_generate_schemas.py:17-19` (`test_all_41_event_types_defined`, hard literal
  `== 41`), `:21-66` (`test_expected_event_types_present`, literal 41-string `expected` set),
  `:72-76` and `:78-83` (`test_creates_41_files`, `test_creates_output_dir_if_missing`, both
  hardcode `== 41`) — **four separate hardcoded `41`s in this one file**, all must bump to 42 in
  lockstep when `parallel.epic_branch_stale` is added to `SCHEMA_DEFINITIONS`
  (`generate_schemas.py:600-612`); the issue's Conventions section cites only the count-assert
  test, missing the other three. [Agent 3 + Agent 2 finding, confirmed]
- `scripts/tests/test_des_schema.py:43-54` (`test_variants_cover_all_schema_definitions`) — will
  fail with an explicit "entries missing from DES_VARIANTS" message naming `parallel.epic_branch_stale`
  until a matching `DESVariant` subclass (model: `ParallelWorkerCompletedVariant`,
  `observability/schema.py:489-495`) is added to the `DES_VARIANTS` tuple
  (`observability/schema.py:690`, "Channel B: EventBus-emitted" section, `:631-690`). [Agent 3
  finding]
- `scripts/tests/test_orchestrator.py:2706-2735` (`test_on_worker_complete_emits_event_on_success`)
  and its sibling `test_on_worker_complete_no_emission_without_event_bus` (`:2766`) — direct
  precedent to model the new `parallel.epic_branch_stale` emission test after: construct an `EventBus`,
  `bus.register(lambda e: received.append(e))`, assert on `event["event"] ==
  "parallel.epic_branch_stale"` and payload keys, plus a no-bus-attached negative case. [Agent 3 finding]
- `scripts/tests/test_subprocess_mocks.py:599,652,700,749` — four **positional**
  `WorkerPool(config, br_config, mock_logger, repo_path)` calls; safe only if the new
  `event_bus` param is appended after `driver` with a `None` default (matching how `run_id`/
  `driver` were added previously) — do not insert it earlier in the positional signature.
  [Agent 3 finding, confirmed against current signature at `worker_pool.py:145-154`]
- No test currently targets `_ensure_epic_branch` by name, and `WorkerPool` currently holds zero
  `EventBus`/`event_bus` references anywhere in `worker_pool.py` (confirmed via grep) — both the
  staleness-measurement test and the emission test are net-new, not extensions. Real-repo
  git-fixture precedent: `test_worktree_utils.py:610-756`
  (`TestMergeEpicBranchToBase`, `_repo_with_epic_branch` helper at `:616-623`, conflict +
  clean-tree-after-abort assertion at `:646-671`) — reverse the merge direction per this issue's
  own Program Design note. Contrast: `test_worker_pool.py`'s existing branch-reuse tests (e.g.
  `test_idempotent_creation:4070-4112`) mock `git_lock.run` rather than using a real repo — the
  new staleness test should follow `test_worktree_utils.py`'s real-repo convention instead, since
  a mocked `rev-list --count` return can't exercise the merge-conflict fallback path. [Agent 3
  finding]

### Documentation
- `docs/reference/API.md` — documents `resolve_epic_base` and `merge_epic_branch_to_base`.
- `docs/reference/CONFIGURATION.md`, `docs/ARCHITECTURE.md`, `docs/guides/LOOPS_REFERENCE.md` —
  reference `epic_branches` config.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/EVENT-SCHEMA.md` — the master event catalog, not previously named in this
  issue. A new `parallel.epic_branch_stale` event (Option B) needs an entry in **four** places in this
  one file, using `parallel.worker_completed` as the template: the per-subsystem field table
  (`:1169-1196`), the generated-schema-file directory listing (`:1366`), the
  dots-to-underscores naming table (`:1391`), and the master event-type-to-emitter index
  (`:1501`). [Agent 2 finding]
- `docs/reference/API.md:7862` — separate event-namespace-conventions bullet list
  (`- \`parallel.*\` — parallel orchestrator events (\`parallel.worker_completed\`)`), and
  `docs/reference/API.md:3978-3985` — the `EpicBranchesConfig` field table itself needs a new
  `refresh_on_reuse` row (the issue's existing citation of this file covers only the two
  functions, not this field table). [Agent 2 finding]
- `docs/reference/CONFIGURATION.md:399-402` — confirmed: the `epic_branches.*` key table
  (`enabled`, `prefix`, `merge_to_base_on_complete`, `open_pr`) needs a new
  `epic_branches.refresh_on_reuse` row in the same format. [Agent 2 finding, confirmed]
- `docs/guides/SPRINT_GUIDE.md:333-335` — confirmed: a second, independent copy of the
  `epic_branches.*` key table under "Per-EPIC Integration Branch" needs the same new row.
  [Agent 2 finding, confirmed]
- `skills/configure/areas.md:198,275-283` and `skills/configure/show-output.md:54-58` —
  confirmed: `/ll:configure`'s interactive settings-summary template and question flow
  hardcode the full `epic_branches.*` field list (`enabled`, `prefix`,
  `merge_to_base_on_complete`, `open_pr`, `verify_before_merge`) with inline defaults;
  `refresh_on_reuse` is invisible to users configuring via this skill unless both files are
  extended. Verbatim per-host mirrors exist at `.qwen/skills/configure/{areas,show-output}.md`,
  `.kimi-code/skills/configure/{areas,show-output}.md`,
  `.gemini/skills/configure/{areas,show-output}.md` — extend only if those mirrors are kept in
  sync with `skills/configure/`. [Agent 2 finding, confirmed]

### Configuration
- `scripts/little_loops/config-schema.json` — `parallel.epic_branches` block (404-435).
- `.ll/ll-config.json` — holds live per-project `parallel.epic_branches` settings.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- Event-type naming convention: existing EventBus emissions are namespaced (e.g. `"parallel.worker_completed"`, `orchestrator.py:1282-1289`) and filterable via `EventBus.register`'s glob-pattern support (e.g. `"parallel.*"`, `events.py:81-96`). RESOLVED: the issue now uses `"parallel.epic_branch_stale"` (namespaced) everywhere — event emission, `SCHEMA_DEFINITIONS` key, `DES_VARIANTS`, docs.
- `WorkerPool._epic_branches_created` (a `set[str]`, `worker_pool.py:193`) caches which branches have been confirmed to exist for the lifetime of the `WorkerPool` instance and is never invalidated — a staleness check added to the reuse paths only ever runs once per branch per `WorkerPool` instance/run, not on every dispatch to that branch.
- `_resolve_branch_targets` (`worker_pool.py:1835-1872`) returns `(branch, branch)` to its caller identically whether `_ensure_epic_branch` took the reuse path or the create path — callers have no existing signal to distinguish "branch was just created" from "branch already existed," which any warn/merge response added here must carry itself (e.g. via the new event), not rely on the return value for.
- `merge_epic_branch_to_base()`'s conflict path persists diagnostic artifacts (`merge-conflicts.txt`, `merge-detail.txt`, `merge-returncode.txt`) to `run_dir` when passed (`worktree_utils.py:672-684`, ENH-2643) before aborting — but its sole existing caller (`orchestrator.py:1502-1509`) omits `run_dir`, so this diagnostic persistence never fires in practice today. Confirmed: no `run_dir` is available at the `_ensure_epic_branch` call site (`WorkerPool` holds only `run_id`, `worker_pool.py:152-170`), so this persistence pattern is OUT OF SCOPE — conflict detail goes into the event payload and log line instead.
- `ParallelOrchestrator`'s `MergeCoordinator` collaborator (`orchestrator.py:144-146`) is also constructed with no `event_bus` argument, same as `WorkerPool` — `self._event_bus` is used only inline within `ParallelOrchestrator` methods (passed as a kwarg into the free function `close_issue()` at `orchestrator.py:1106-1116` and `:1537-1547`, or emitted directly via `self._event_bus.emit()`), never threaded into a collaborator's constructor today. `WorkerPool` gaining an `event_bus` param would be the first such collaborator-constructor precedent.

## Implementation Steps

1. Add `EpicBranchStatus` + `ensure_epic_branch()` to `worktree_utils.py`: exists-check (local → remote → create), then on local-hit `git rev-list --count <branch>..<base>`; `N == 0` → `action="fresh"`, return early.
2. Add `refresh_on_reuse` (default `"merge"`) to both `EpicBranchesConfig` dataclasses, the `_build_parallel_epic_branches()` bridge, `config-schema.json`, and the parity/round-trip tests.
3. On `merge` mode and `N > 0`: `setup_worktree(..., checkout_existing=True)` on the epic branch, `git merge --no-edit -m "..." <base>` inside that scratch worktree (a non-checked-out branch cannot be merged into via the git lock alone — `git merge` only operates on HEAD, and ff-only ref updates refuse when the epic branch has its own commits), `cleanup_worktree(..., delete_branch=False)` in a `finally`; conflict → write ENH-2643 artifacts if `run_dir`, `merge --abort`, `action="merge_conflict"`, do not raise.
4. Rewrite `WorkerPool._ensure_epic_branch` as cache → helper → emit `parallel.epic_branch_stale` when `action in {warned, merged, merge_conflict}`, payload `{branch, base, commits_behind, mode, action}`.
5. Rewrite `checkout_epic_branch` in `auto-refine-and-implement.yaml` to call the helper with `run_dir`; write `epic-branch-stale.txt` on `warned`/`merge_conflict`; have `finalize` surface `merge_conflict` in the run summary; fix the `:184` line citation.
6. Tests (real-repo fixture, reversed `TestMergeEpicBranchToBase`): fresh branch → no-op/no event; stale + `warn` → SHA unchanged, event/artifact; stale + `merge` → base merged, one merge commit, base SHA unchanged; conflict → SHA unchanged, clean tree, worktree removed, `merge_conflict` surfaced; `off` → nothing. Plus `test_builtin_loops.py` coverage that the YAML state routes through the helper.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `event_bus: EventBus | None = None` to `WorkerPool.__init__` (`worker_pool.py:145-154`),
  appended after `driver` to stay positional-arg-safe for existing callers.
- Update `Orchestrator.__init__` (`orchestrator.py:133-143`) to pass `event_bus=self._event_bus`
  into its `WorkerPool(...)` construction — otherwise the new event never reaches the
  Orchestrator's bus/transports.
- Add an `parallel.epic_branch_stale` entry to `SCHEMA_DEFINITIONS` (`generate_schemas.py:600-612`,
  modeled on `parallel.worker_completed`), then bump all four hardcoded `41`s in
  `test_generate_schemas.py` (`:17-19`, `:21-66`, `:72-76`, `:78-83`) to 42.
- Add a matching `DESVariant` subclass (modeled on `ParallelWorkerCompletedVariant`,
  `observability/schema.py:489-495`) to the `DES_VARIANTS` tuple (`observability/schema.py:690`).
- Write the emission test modeled on `test_orchestrator.py:2706-2735` /
  `:2766` (with-bus and without-bus cases) and the staleness/merge/conflict test modeled on
  `test_worktree_utils.py:610-756` (real-repo fixture, reversed merge direction).
- Update `docs/reference/EVENT-SCHEMA.md` (4 locations: `:1169-1196`, `:1366`, `:1391`, `:1501`),
  `docs/reference/API.md` (`:3978-3985` field table, `:7862` namespace bullet list),
  `docs/reference/CONFIGURATION.md:399-402`, and `docs/guides/SPRINT_GUIDE.md:333-335` with the
  new `refresh_on_reuse` field / `parallel.epic_branch_stale` event.
- Update `skills/configure/areas.md:198,275-283` and `skills/configure/show-output.md:54-58` so
  `/ll:configure` surfaces `refresh_on_reuse`; sync to per-host mirrors under `.qwen/`,
  `.kimi-code/`, `.gemini/` only if those are otherwise kept current.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- Step 3 understates scope: `EpicBranchesConfig` is declared twice (`scripts/little_loops/parallel/types.py:322` and a separately-maintained `config/automation.py:57`), bridged by hand in `_build_parallel_epic_branches()` (`config/core.py:690-712`). `refresh_on_reuse` must be added to both dataclasses and the bridge function, not just `types.py` + the schema.
- Step 1's `git rev-list --count` direction (`<branch>..<base>`) has no existing helper to reuse — the two existing `rev-list --count` call sites in this codebase (`orchestrator.py:516-521`, `cli/loop/run.py:516`) measure the opposite direction (branch-ahead-of-base) and cannot be adapted by argument order alone without re-verifying their surrounding logic.
- Step 4's merge should follow the skeleton in `merge_epic_branch_to_base()` (`worktree_utils.py:612-689`) for conflict-detect-abort-return-False, but that function merges the epic branch into the base — this issue needs the reverse (base merged into the epic branch), so it is a shape to imitate, not a function to call directly.
- Step 5's event: `WorkerPool` (unlike `ParallelOrchestrator`) holds no `_event_bus` reference today (`worker_pool.py:145-197`), and a genuinely new `EventBus`-emitted event type must also be registered in `SCHEMA_DEFINITIONS` (`generate_schemas.py:600`, count-asserted by `test_generate_schemas.py:17-19`) and `DES_VARIANTS` (`observability/schema.py`, coverage-asserted by `test_des_schema.py:30-66`) — see Proposed Solution → Option A/B for the two viable routes and their cost difference.

## Impact

- **Priority**: P2 - Silent staleness turned one held-open merge into 5/8 skips + 11 false-negative verify failures in a real run; recurrence is likely whenever an epic merge verify fails.
- **Effort**: Medium - Core logic is small, but the config field spans four declaration sites, the event spans two test-enforced registries, and docs/skills span ~6 files.
- **Risk**: Low-Medium - Default `merge` adds at most one merge commit on an existing `epic/*` branch and never touches base; conflict degrades to warn with a clean tree (verified by the reversed `TestMergeEpicBranchToBase` case). `warn` is available for anyone wanting a no-mutation default.
- **Breaking Change**: No - New optional config field; `WorkerPool.__init__` gains a trailing keyword param with `None` default. Behavioral change: reused epic branches now receive base merges by default.

## Desired Behavior

On the local "exists" path (remote-hit path excluded — see Decision Rules), measure staleness against the resolved fork base (`worktree_utils.resolve_epic_base`, ENH-2656): `git rev-list --count <branch>..<base>`. Then either:

- **Warn** (minimum): log + emit `parallel.epic_branch_stale` (`epic branch <branch> is N commits behind <base>`) whenever `N > 0`, and

- **Reconcile by default** (config-gated, `parallel.epic_branches.refresh_on_reuse: warn|merge|off`, default `merge`): merge the base into the branch (via a scratch worktree — see Proposed Solution) before dispatching workers / attaching the sub-loop worktree; on merge conflict, fall back to warn + surface `merge_conflict` prominently in the run summary rather than proceeding silently.

Both `WorkerPool._ensure_epic_branch` and `auto-refine-and-implement.yaml`'s `checkout_epic_branch` state get this behavior via the shared `worktree_utils.ensure_epic_branch()` helper.

## Affected Files

- `scripts/little_loops/parallel/worker_pool.py` (`_ensure_epic_branch`)
- `scripts/little_loops/parallel/types.py` (`EpicBranchesConfig`)
- `scripts/little_loops/config-schema.json`
- `scripts/tests/test_worker_pool.py` (or wherever `_ensure_epic_branch` is covered)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-23 — based on codebase analysis:_

- `scripts/little_loops/config/automation.py` (`EpicBranchesConfig`, 57-81) — separate dataclass mirroring `types.py`'s; the current Affected Files list omits it.
- `scripts/little_loops/config/core.py` (`_build_parallel_epic_branches()`, 690-712) — hand-written bridge between the two `EpicBranchesConfig` dataclasses; the current Affected Files list omits it.
- `scripts/tests/test_config.py`, `scripts/tests/test_config_schema.py` — existing parity/defaults/round-trip and schema-declaration tests for `epic_branches` fields that a new field must extend.

## Acceptance Criteria

- [ ] `worktree_utils.ensure_epic_branch()` exists and is the sole implementation of the exists-check/staleness/merge logic; both `WorkerPool._ensure_epic_branch` and `auto-refine-and-implement.yaml`'s `checkout_epic_branch` call it (no duplicated rev-parse/ls-remote/branch block remains in the YAML)
- [ ] Reusing an epic branch N>0 commits behind its fork base (local-hit path) logs a visible warning including N and the base ref, on both call paths
- [ ] `WorkerPool` path: a `parallel.epic_branch_stale` event is emitted in both `warn` and `merge` modes with payload `{branch, base, commits_behind, mode, action}`; no emission when `off` or when N=0
- [ ] YAML path: `${context.run_dir}/epic-branch-stale.txt` is written with the same fields on `warned`/`merge_conflict`; `finalize` surfaces `merge_conflict` in the run summary
- [ ] Default `refresh_on_reuse: merge` merges the base into the branch via a scratch worktree before worker dispatch / worktree attach; clean merge yields exactly one merge commit on the epic branch and leaves the base SHA unchanged; conflict aborts the merge (epic branch SHA unchanged, clean tree, worktree removed) and degrades to warn without aborting the run
- [ ] `refresh_on_reuse: warn` changes no git state; `off` performs no measurement, emission, or artifact
- [ ] N=0 short-circuits: no merge, no event, no artifact
- [ ] `python -m pytest scripts/tests/` passes

## Related Key Documentation

| Document | Category | Relevance |
|----------|----------|-----------|
| docs/ARCHITECTURE.md | architecture | Parallel orchestration / epic-branch lifecycle design |
| docs/reference/API.md | architecture | `worktree_utils` (`resolve_epic_base`, `setup_worktree`) and worker-pool surfaces |

## Status

**Open** | Created: 2026-08-23 | Priority: P2

## Confidence Check Notes

**Readiness: 95/100** (PROCEED) | **Outcome Confidence: 61/100** (risk factors below threshold)

### Outcome Risk Factors
- ~~**Threshold value undecided**~~ RESOLVED (2026-08-23 review): threshold is `N > 0` with no
  numeric config knob — see Program Design → Decision Rules.
- ~~**Fix scoped to the wrong path**~~ RESOLVED (2026-08-23 manual review): the observed incident
  went through `auto-refine-and-implement.yaml`'s `checkout_epic_branch`, not `WorkerPool`; the
  issue now mandates a shared `worktree_utils.ensure_epic_branch()` helper called from both.
- ~~**Default `warn` ineffective for unattended runs**~~ RESOLVED (2026-08-23 manual review):
  default is `merge`; rationale in Proposed Solution → "Default decision".
- **Wide fanout across subsystems**: the change spans git-op logic, a config field declared in
  two separately-maintained dataclasses plus a hand-written bridge, new EventBus wiring into a
  class (`WorkerPool`) that has none today, two mandatory test-registry updates
  (`SCHEMA_DEFINITIONS`/`DES_VARIANTS`, each with hardcoded counts to bump), and ~4 documentation
  files with multiple locations apiece. High file/registry count raises the chance of a missed
  site even with the wiring pass already enumerating them.
- **Event-bus wiring is net-new for `WorkerPool`**: unlike `ParallelOrchestrator`, `WorkerPool`
  holds no `_event_bus` reference today; correctly threading it through `__init__`, the
  `Orchestrator` construction site, and the two CLI construction sites (`cli/parallel.py:206,288`)
  without breaking existing positional-arg callers (`test_subprocess_mocks.py`) is a real risk of
  a mechanical slip.
- Minor: `unapplied_decision` flags `_resolve_branch_targets` as a rejected-option identifier
  still present in Proposed Solution/Program Design — appears to be a heuristic false positive
  (it's a caller reference, not one of the Option A/B alternatives), not an actual unapplied
  decision; left unresolved as advisory-only per skill policy (does not escalate to STOP).

_/ll:confidence-check — 2026-08-23_

## Session Log
- `/ll:manage-issue` - 2026-08-23T23:39:19 - `3a3fd195-a606-4714-b96c-def6d1615433.jsonl`
- `/ll:ready-issue` - 2026-08-23T23:04:19 - `aa35c4eb-f11f-4207-b414-76abb4bf11bc.jsonl`
- `/ll:ready-issue` - 2026-08-23T23:03:59 - `aa35c4eb-f11f-4207-b414-76abb4bf11bc.jsonl`
- `/ll:confidence-check` - 2026-08-23T22:41:37 - `7bda0207-9380-42da-8921-b7a6588dcc63.jsonl`
- manual review (shared helper, YAML path in scope, default `merge`) - 2026-08-23T21:30:00 - `9c4139c2-0aa3-4509-a4fa-9201f472ecc2.jsonl`
- `/ll:refine-issue` - 2026-08-23T20:53:23 - `08e63d9a-b62a-416e-9aee-3952a5c2db98.jsonl`
- `/ll:confidence-check` - 2026-08-23T20:43:03 - `36a136c9-6c59-4cf6-b7d4-c0e4e7645a9e.jsonl`
- `/ll:wire-issue` - 2026-08-23T20:40:50 - `d137b866-3013-4a7f-ba4f-5c7273420ea9.jsonl`
- `/ll:decide-issue` - 2026-08-23T20:31:30 - `7746b0e5-5986-4ac4-ae25-f7097ddec171.jsonl`
- `/ll:refine-issue` - 2026-08-23T20:27:05 - `06850cef-a170-4bbc-9f5e-f738e036bbe7.jsonl`
- `/ll:capture-issue` - 2026-08-23T19:19:40 - `0e2d1ba2-9c47-49de-b246-1efb9ad7b60c.jsonl`
