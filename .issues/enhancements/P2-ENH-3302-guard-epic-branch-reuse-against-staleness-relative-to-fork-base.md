---
id: ENH-3302
type: ENH
title: Guard epic branch reuse against staleness relative to fork base
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-08-23'
captured_at: '2026-08-23T19:19:05Z'
decision_needed: false
confidence_score: 95
outcome_confidence: 61
score_complexity: 12
score_test_coverage: 20
score_ambiguity: 15
score_change_surface: 14
---

# ENH-3302: Guard epic branch reuse against staleness relative to fork base

## Summary

`_ensure_epic_branch` (`scripts/little_loops/parallel/worker_pool.py:1938`) is strictly create-if-missing: when `git rev-parse --verify <branch>` succeeds it reuses the existing `epic/*` integration branch as-is — no fast-forward, no merge of the fork base, not even a warning that the branch is behind. A branch held open by a failed merge becomes a frozen snapshot: every later run attaches sub-loop worktrees (`fsm/executor.py:961`, `checkout_existing=True`) to that stale tree.

Observed 2026-08-23: `epic/epic-3041-host-agnostic-advisor` was created 2026-08-08 off then-current main (`d93ce3e8f`) and held open when its merge verify failed. This morning's `sprint-refine-and-implement` run reused it ~448 commits behind main. The worktree's stale `.issues/` tree (predating main's issue re-anchoring, commit `731af505` era) caused 5 of 8 skips (`refine_failed` — "FEAT-3118 does not exist", "depends_on unknown issue FEAT-3120") and 11 false-negative verify failures (all pass on current main). Run: `.loops/runs/sprint-refine-and-implement-20260823T093038/`.

## Current Behavior

Docstring of the reuse path (`worker_pool.py:1939`):

```
Lazily create ``branch`` off ``base`` if it does not exist yet.
```

Steps: in-memory cache hit → local `rev-parse --verify` hit → remote `ls-remote` hit → else `git branch <branch> <base>`. All three "exists" paths return with zero staleness inspection.

## Expected Behavior

[What should happen instead]

## Motivation

Branch persistence across runs is by design (an epic integration branch accumulates children until the epic merges), but silent staleness turns a single held-open merge into a cascade: refine failures, bogus dependency-graph errors, verify false negatives, and (see the companion BUG) issue-ID collisions. The failure is invisible until a human diffs the branch point.

## Proposed Solution

Add staleness measurement inside `_ensure_epic_branch` (`worker_pool.py:1938`) on both the
local-hit and remote-hit reuse paths, using the `base` value already passed in from
`_resolve_branch_targets`'s `resolve_epic_base()` call (`worker_pool.py:1865`) — the accurate
fork base already reaches this method, so no additional base-resolution work is needed.

Measure with `self._git_lock.run(["rev-list", "--count", f"{branch}..{base}"], cwd=self.repo_path,
timeout=10)`, following the existing local-op timeout convention in this method (10s for
read-only local plumbing, `worker_pool.py:1956`). No existing `rev-list --count` call in the
codebase measures this direction (base-ahead-of-branch) — the two existing uses
(`orchestrator.py:516-521`, `cli/loop/run.py:516`) measure the opposite (branch-ahead-of-base),
so this is new code, not an extension of a shared helper.

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
`epic_branch_stale` event via `EventBus.emit()` (`events.py:117-138`), following the plain-dict
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

**Selected**: Option B (event bus + structured `epic_branch_stale` event)

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
- `WorkerPool._ensure_epic_branch(self, branch: str, base: str) -> None` — existing signature at
  `worker_pool.py:1938`, behavior extended in place; no signature change needed since `base`
  (the resolved fork base) is already passed in by the sole caller.
- `GitLock.run(args: list[str], cwd: Path, timeout: float = 30, ...) -> subprocess.CompletedProcess[str]` — existing signature at
  `git_lock.py:81`, the call surface a new `["rev-list", "--count", f"{branch}..{base}"]`
  invocation would use.

### Call Path
`_resolve_branch_targets` (`worker_pool.py:1871`) -> `_ensure_epic_branch(branch, base)`
(`worker_pool.py:1938`) -> [new] `git rev-list --count <branch>..<base>` via
`self._git_lock.run(...)` -> (if `refresh_on_reuse == "merge"` and count > 0) merge path
analogous to `merge_epic_branch_to_base()` (`worktree_utils.py:612`), direction reversed
(base merged into branch) -> [new] event emission, channel per the Option A/B decision above.

### Decision Rules
- Gap kind: staleness threshold and reconcile mode.
- Exact input: `git rev-list --count <branch>..<base>` result `N` (commits `base` has that
  `branch` lacks).
- Threshold: the issue's Desired Behavior says "above a threshold" but does not name one —
  UNKNOWN, needs an explicit value (e.g. `N > 0` vs a configurable minimum commit count). No
  existing numeric-threshold field on `EpicBranchesConfig` or its siblings to anchor a default
  against.
- Mode values: `warn|merge|off` (issue-proposed) — no existing schema enum in this codebase uses
  `merge` as a value; the two closest precedents disagree on vocabulary
  (`code_query.staleness`: `strict|warn|off`, `config-schema.json:1396-1401`; `tamper_guard.mode`:
  `off|warn|block`, `config-schema.json:1167-1170`).
- Escape hatch: on merge conflict in `merge` mode, fall back to warn without aborting the run
  (per Desired Behavior) — this is exactly the shape `merge_epic_branch_to_base()` already
  implements (conflict -> `git merge --abort` -> return `False` -> caller logs, doesn't raise).

## Integration Map

### Files to Modify
- `scripts/little_loops/parallel/worker_pool.py` — `_ensure_epic_branch` (1938-1977): add the
  staleness check on the local-hit (1952-1960) and remote-hit (1961-1970) reuse paths.
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
  production call site that must pass `event_bus=self._event_bus` or the new `epic_branch_stale`
  event never reaches the Orchestrator's bus/transports. [Agent 1 + Agent 2 finding]
- `scripts/little_loops/cli/parallel.py:206,288` — two more `WorkerPool(...)` construction sites
  (`--cleanup` and `--prune-merged-branches` CLI branches), both positional, neither with an
  `EventBus` in scope; safe as long as the new `event_bus` param is appended last with a
  `None` default (matching the existing `run_id`/`driver` convention). [Agent 1 + Agent 2 finding]
- `scripts/little_loops/loops/auto-refine-and-implement.yaml:202,248,636,696` — inline FSM Python
  action blocks import and call `resolve_epic_base(...)` / `merge_epic_branch_to_base(...)`
  directly from `worktree_utils`, duplicating logic parallel to `_ensure_epic_branch` outside
  `worker_pool.py`; comments at lines 25/184 reference `_ensure_epic_branch` by name. Not
  necessarily in scope to change, but this loop's own epic-branch handling will remain unaware
  of the new staleness guard unless reconciled. [Agent 1 finding]
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
  lockstep when `epic_branch_stale` is added to `SCHEMA_DEFINITIONS`
  (`generate_schemas.py:600-612`); the issue's Conventions section cites only the count-assert
  test, missing the other three. [Agent 3 + Agent 2 finding, confirmed]
- `scripts/tests/test_des_schema.py:43-54` (`test_variants_cover_all_schema_definitions`) — will
  fail with an explicit "entries missing from DES_VARIANTS" message naming `epic_branch_stale`
  until a matching `DESVariant` subclass (model: `ParallelWorkerCompletedVariant`,
  `observability/schema.py:489-495`) is added to the `DES_VARIANTS` tuple
  (`observability/schema.py:690`, "Channel B: EventBus-emitted" section, `:631-690`). [Agent 3
  finding]
- `scripts/tests/test_orchestrator.py:2706-2735` (`test_on_worker_complete_emits_event_on_success`)
  and its sibling `test_on_worker_complete_no_emission_without_event_bus` (`:2766`) — direct
  precedent to model the new `epic_branch_stale` emission test after: construct an `EventBus`,
  `bus.register(lambda e: received.append(e))`, assert on `event["event"] ==
  "epic_branch_stale"` and payload keys, plus a no-bus-attached negative case. [Agent 3 finding]
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
  issue. A new `epic_branch_stale` event (Option B) needs an entry in **four** places in this
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

## Implementation Steps

1. Add staleness measurement in `_ensure_epic_branch` after the local and remote hit paths (worker_pool.py:1953-1970).
2. Thread the resolved base into the check (already available at call sites via `resolve_epic_base`).
3. Add `refresh_on_reuse` to `EpicBranchesConfig` (`scripts/little_loops/parallel/types.py`) + `config-schema.json` + schema-parity defaults.
4. On `merge` mode: `git merge --no-edit <base>` inside a scratch worktree or via the git lock on the branch; conflict → emit event + warn, do not abort the run.
5. Emit a structured event (e.g. `epic_branch_stale`) so run summaries and `ll-loop` audit tooling can surface it.
6. Tests: stale-branch fixture repo — reuse path warns; merge mode fast-forwards; conflict falls back to warn.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `event_bus: EventBus | None = None` to `WorkerPool.__init__` (`worker_pool.py:145-154`),
  appended after `driver` to stay positional-arg-safe for existing callers.
- Update `Orchestrator.__init__` (`orchestrator.py:133-143`) to pass `event_bus=self._event_bus`
  into its `WorkerPool(...)` construction — otherwise the new event never reaches the
  Orchestrator's bus/transports.
- Add an `epic_branch_stale` entry to `SCHEMA_DEFINITIONS` (`generate_schemas.py:600-612`,
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
  new `refresh_on_reuse` field / `epic_branch_stale` event.
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

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Desired Behavior

On the local/remote "exists" paths, measure staleness against the resolved fork base (`worktree_utils.resolve_epic_base`, ENH-2656): `git rev-list --count <branch>..<base>`. Then either:

- **Warn** (minimum): log/emit `epic branch <branch> is N commits behind <base>` above a threshold, and

- **Optionally reconcile** (config-gated, e.g. `parallel.epic_branches.refresh_on_reuse: warn|merge|off`, default `warn`): merge the base into the branch before dispatching workers; on merge conflict, fall back to warn + surface in the run summary rather than proceeding silently.

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

- [ ] Reusing an epic branch N>threshold commits behind its fork base emits a visible warning including N and the base ref
- [ ] `refresh_on_reuse: merge` merges the base into the branch before worker dispatch; clean merge proceeds, conflict degrades to warn without aborting
- [ ] Default behavior (`warn`) changes no git state
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
- **Threshold value undecided**: Program Design → Decision Rules explicitly marks the staleness
  threshold as `UNKNOWN, needs an explicit value` (`N > 0` vs a configurable minimum commit
  count) — no existing numeric-threshold field on `EpicBranchesConfig` to anchor a default
  against. This must be resolved before/during implementation, not deferred.
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
- `/ll:confidence-check` - 2026-08-23T20:43:03 - `36a136c9-6c59-4cf6-b7d4-c0e4e7645a9e.jsonl`
- `/ll:wire-issue` - 2026-08-23T20:40:50 - `d137b866-3013-4a7f-ba4f-5c7273420ea9.jsonl`
- `/ll:decide-issue` - 2026-08-23T20:31:30 - `7746b0e5-5986-4ac4-ae25-f7097ddec171.jsonl`
- `/ll:refine-issue` - 2026-08-23T20:27:05 - `06850cef-a170-4bbc-9f5e-f738e036bbe7.jsonl`
- `/ll:capture-issue` - 2026-08-23T19:19:40 - `0e2d1ba2-9c47-49de-b246-1efb9ad7b60c.jsonl`
