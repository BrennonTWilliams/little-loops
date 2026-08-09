---
id: BUG-3112
title: Worktree sessions write session history to a throwaway .ll/history.db
type: BUG
priority: P2
status: done
parent: EPIC-3111
captured_at: '2026-08-08T20:32:03Z'
completed_at: '2026-08-09T14:42:44Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- history
- data-loss
confidence_score: 96
outcome_confidence: 92
score_complexity: 22
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 24
decision_needed: false
reconcile_attempted: true
testable: true
---

# BUG-3112: Worktree sessions write session history to a throwaway `.ll/history.db`

## Summary

Every auto-created worktree gets its own empty `.ll/history.db` instead of
sharing the main repo's. Sub-loop sessions write their session events,
analytics, file events, and pytest-history records into that throwaway DB, which
`cleanup_worktree` deletes along with the worktree directory. Reads inside the
worktree degrade silently for the same reason.

## Steps to Reproduce

1. Run a worktree-scoped loop, e.g. `ll-loop run sprint-refine-and-implement <sprint>`
   (delegates to `auto-refine-and-implement`, whose `delegate` state declares
   `worktree: ${captured.epic_branch.output}`).
2. While the sub-loop is running, inspect `<worktree>/.ll/history.db` — it exists
   and is separate from the main repo's.
3. Let the run complete and the worktree be cleaned up.
4. Query the main repo's history for the sub-loop's session:
   `ll-session search --fts "<something the sub-session did>"`.
5. Observe: no rows. The sub-loop's entire history is gone.

## Current Behavior

`setup_worktree` (`scripts/little_loops/worktree_utils.py:157`) copies git
identity, `copytree`s `.claude/`, and copies `parallel.worktree_copy_files`
(default `[".claude/settings.local.json", ".env"]`). It does not copy
`.ll/history.db` — correctly, since it is gitignored (`.gitignore:102-104`) —
and nothing points the worktree back at the main DB.

Inside the worktree, `.ll/` exists because the repo-root `.ll/` is tracked
(`.gitignore:146` un-ignores `/.ll/`). So `resolve_ll_dir()` succeeds, and
`_resolve_db_path` (`session_store/db.py:68-107`) walks env → config → default
and lands on `<worktree>/.ll/history.db`, creating it on first write.

Consequences:
- **Writes lost**: session lifecycle events, analytics, file/tool events,
  `SQLiteTransport` output (`transport.py:663`), and `pytest_history_plugin`
  test-run records all go to the throwaway DB and die with the worktree.
- **Reads degraded, silently**: the SessionStart project-context digest is
  empty; `ll-messages` falls back to JSONL parsing
  (`user_messages.py:913-923`); `decisions.py:574` takes the
  `scan_completed_issues` filesystem branch instead of
  `scan_completed_issues_from_db`.

## Expected Behavior

A worktree session reads and writes the **main repo's** `.ll/history.db`, so its
history survives teardown and its context reads are as rich as the main tree's.
No `.ll/history.db` is created inside a worktree at all.

## Root Cause

- **File**: `scripts/little_loops/worktree_utils.py`
- **Anchor**: `in function setup_worktree()`
- **Cause**: `setup_worktree` establishes a worktree whose resolved project root
  is the worktree itself, but never propagates a history-DB location. There is
  no `LL_HISTORY_DB` setter anywhere in production code — only readers
  (`session_store/db.py:96`, `hooks/session_start.py:145-146`,
  `hooks/post_commit.py:95`, `pytest_history_plugin.py:45`) — so the
  env-override branch of `_resolve_db_path` is dead in practice and resolution
  falls through to the worktree-local default, anchored on each child process's
  `cwd`.

## Proposed Solution

Point worktree-scoped processes at the main repo's DB rather than copying it,
by **exporting `LL_HISTORY_DB` into the orchestrator's own `os.environ` inside
`setup_worktree()`**, where it is inherited by every descendant process.

Copying is the wrong fix twice over: a `shutil.copy2` of a live WAL SQLite file
without its `-wal`/`-shm` siblings yields a stale or torn snapshot, and even a
clean copy forks the history so the worktree's writes are still discarded at
cleanup. Sharing is what the store is already built for —
`session_store/schema.py:978-979` sets `PRAGMA busy_timeout` and
`journal_mode = WAL` with the comment that "under ll-parallel many processes
contend at once."

### The change

In `setup_worktree()` (`worktree_utils.py:157`), before the worktree is
created:

```python
# BUG-3112: resolve the MAIN repo's history DB while cwd is still the main
# repo, and export it so every descendant of this orchestrator — host-CLI
# sessions, FSM shell actions, hooks, pytest runs — resolves the shared DB
# instead of creating a throwaway <worktree>/.ll/history.db that teardown
# deletes. setdefault: an explicit caller/test override always wins, and a
# nested worktree inherits the outermost repo's DB rather than re-resolving.
from little_loops.session_store.db import resolve_history_db

os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))
```

`worktree_utils.py` already imports `os`; the `session_store.db` import is
function-local to avoid an import cycle, matching `_resolve_db_path`'s own
function-local `from little_loops.paths import resolve_ll_dir`.

For the parent process this is a no-op — it resolves the same path it already
resolves. For every child it is the fix.

### Why this layer and not the host-runner boundary

Every process-spawn path in this codebase composes its child environment from
`os.environ.copy()` (`subprocess_utils.py:421-422`;
`worktree_utils.py:461`; `fsm/executor.py:2132-2137`'s bare `subprocess.Popen`).
Exporting once in the parent therefore reaches **all** of them, including paths
an env-parameter thread cannot reach without bespoke per-site edits:

- `fsm/executor.py:2132-2137` — FSM shell actions run `subprocess.Popen(...,
  cwd=self.working_dir)` (= the worktree) with plain inherited environment and
  **no `HostInvocation` at all**. Any `ll-*` command in a loop's shell action
  writes to the throwaway DB.
- `worker_pool.py:812-814` (`_detect_worktree_model_via_api`) calls
  `build_blocking_json()`, which has no env-parameter surface
  (`host_runner.py:250-259`).
- `runner_spec.py`'s blocking/default-mode path calls
  `resolve_host().build_streaming()` directly, bypassing `run_claude_command()`.
- `verify_epic_branch_before_merge()` (`worktree_utils.py:455-473`) builds its
  own child env inline and never touches a host runner.
- Any spawn site added in future — which would silently regress under a
  per-site scheme.

This is an established idiom here, not a novel mechanism: the same
resolve-once-and-export shape already carries `LL_HANDOFF_THRESHOLD` and
`LL_CONTEXT_LIMIT` (`cli/parallel.py:237,242`, `cli/auto.py:86,91`,
`cli/sprint/run.py:374,378`, `cli/loop/run.py:218,223,226`,
`cli/loop/lifecycle.py:547,552`) and `LL_HOST_CLI` (`host_runner.py:1680`) to
descendant processes.

`setup_worktree()` is the single chokepoint: all four worktree-creating sites
(`fsm/executor.py:942`, `cli/loop/run.py:484`, `worker_pool.py:774`,
`worktree_utils.py:441`) route through it.

### Known precondition

`resolve_history_db()` anchors on `Path.cwd()` via `resolve_ll_dir()`
(`paths.py:45-83`), not on `setup_worktree`'s `repo_path` argument —
`_resolve_db_path` has no root parameter, and a default-shaped path argument
(`<repo>/.ll/history.db`) is re-routed through the env → config → cwd chain
rather than honored verbatim (`_is_default_shaped`, `db.py:18-32`). The export
is therefore correct only while the orchestrator's cwd is inside the main repo.
All four call sites satisfy this today; AC-5 below pins it. Adding a `root`
parameter to `_resolve_db_path` would remove the assumption entirely and is a
reasonable follow-up, but is out of scope here — it changes a shared,
heavily-used resolution chain that the test-suite isolation fixtures depend on.

### Interaction with the test suite

`conftest.py`'s `_isolate_history_db_session` (:553-564) and
`_isolate_history_db` (:580-613) force `LL_HISTORY_DB` for every test, so
`setdefault` no-ops under pytest and cannot leak a real-repo path into a test
process. This also means `_guard_real_history_db` (:617-657) is never tripped
by the new line. The AC-1/AC-2 tests must therefore set `LL_HISTORY_DB`
explicitly (or clear it) rather than relying on ambient state.

### Rejected alternatives

**Copy the DB into the worktree** — rejected; forks history and torn-snapshots
a live WAL file (see above).

**Thread `history_db` through `run_claude_command()` → 5 `build_streaming()`
implementations via a new `_apply_history_db_env()` helper** — the approach
previously selected on this issue, now superseded. It changes a public
signature, spans ~10 edit sites (`subprocess_utils.py`, `host_runner.py` ×5,
`worker_pool.py` ×2, `runner_spec.py`, `issue_manager.py`, `worktree_utils.py`),
collides with in-flight ENH-3095/ENH-3097 on the same `subprocess_utils.py`/
`host_runner.py` line ranges, and **still leaves the four non-host-runner spawn
paths listed above uncovered**. The `os.environ` export subsumes it at one site
with no signature change and no sequencing conflict.

**Origin marker file written into the worktree, read back by
`_resolve_db_path`** — rejected; zero precedent (every analogous marker in this
codebase — `LL_VERIFY_GATE`, `LL_NON_INTERACTIVE`, `LL_AUTOMATION`,
`LL_HANDOFF_THRESHOLD` — is an env var), and it destabilizes the shared
`_resolve_db_path` precedence chain that the conftest isolation fixtures depend
on.

### Verify-gate worktree

Previously tracked as an open decision (share vs. isolate). Under this approach
it is **moot**: `verify_epic_branch_before_merge()` builds its child env as
`env = os.environ.copy()` (`worktree_utils.py:461`) and only overlays additive
keys, so it inherits the shared DB for free with no code change. Sharing was
the selected outcome anyway — the gate's `test_cmd` pytest run writes
`test_run_events` rows via `pytest_history_plugin`, whose `_infer_env_label()`
already anticipates and labels `"worktree"`-origin runs rather than excluding
them, and those rows are silently discarded today. There is no `env.pop(...)`
exclusion idiom anywhere in `scripts/little_loops` to borrow for an isolation
carve-out.

## Program Design

### Types
N/A — no new data shape; this is `os.environ`-style `dict[str, str]` env-var
propagation into an existing resolution chain.

### Signatures
- `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: list[str], logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None` — **signature unchanged** (`worktree_utils.py:157-166`). Gains one statement in its body: `os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))`, placed before worktree creation (i.e. before any `git worktree add`), so resolution happens while the process's cwd is unambiguously the main repo.
- `resolve_history_db(path: Path | str | None = None) -> Path` — thin public wrapper over `_resolve_db_path` (`session_store/db.py:110-118`). Called with no argument; **read-only**, no new parameter.
- `_resolve_db_path(path: Path | str | None = None) -> Path` — **unchanged** (`session_store/db.py:68-107`). For a default-shaped path (`_is_default_shaped`, `:18-32`), precedence is `os.environ["LL_HISTORY_DB"]` (`:96`, wins immediately if truthy) → `history.db_path` config key (`:99-101`) → `resolve_ll_dir()`-anchored default (`:102-107`). This fix makes branch 1 live in worktree children; branches 2 and 3 keep their current behavior everywhere else.

### Call Path
`setup_worktree()` (`worktree_utils.py:157`) sets `os.environ["LL_HISTORY_DB"]`
in the **orchestrator** process → every descendant inherits it, via each spawn
site's existing `os.environ.copy()`:

- `subprocess_utils.py:421-422` (`env = os.environ.copy(); env.update(invocation.env)`)
  → host-CLI sessions, `cwd=worktree_path`
- `fsm/executor.py:2132-2137` (`subprocess.Popen(..., cwd=self.working_dir)`,
  no env argument → full inherit) → FSM shell actions
- `worktree_utils.py:461` (`env = os.environ.copy()`) → verify-gate `test_cmd`
  and its `pytest_history_plugin` writes
- `worker_pool.py:812-814` → `build_blocking_json()` spawn
- hooks and `ll-*` CLIs invoked from inside any of the above → inherit
  transitively

In each child, `_resolve_db_path()` now short-circuits at `:96` on the
inherited env var and returns `<main repo>/.ll/history.db`. Today, with the var
absent, it falls through to `resolve_ll_dir()` anchored on the child's
`cwd` (= the worktree) and returns `<worktree>/.ll/history.db` — the bug.

All four worktree-creating call sites — `fsm/executor.py:942`,
`cli/loop/run.py:484`, `worker_pool.py:774` (`_setup_worktree`), and
`worktree_utils.py:441` (`verify_epic_branch_before_merge`) — route through
`setup_worktree()`, so one export covers all of them.

### Decision Rules
- **`setdefault`, not assignment.** An explicit `LL_HISTORY_DB` (test fixtures,
  user override, an outer worktree that already exported) always wins. A nested
  worktree therefore inherits the outermost repo's DB rather than re-resolving
  against an intermediate worktree.
- **Resolve before `git worktree add`.** After creation, a caller that chdir'd
  into the worktree would resolve the wrong root. Ordering makes the cwd
  precondition (see Proposed Solution) hold at the only moment it matters.
- No new gap kind, gate, or threshold.

## Acceptance Criteria

1. **No worktree-local DB is created.** After `setup_worktree()` +
   a session/loop run inside the worktree, `<worktree>/.ll/history.db` does not
   exist. (Strongest and cheapest assertion — a worktree DB cannot be created
   if resolution never lands there.)
2. **Child processes resolve the main repo's DB.** A subprocess spawned with
   `cwd=<worktree>` and the orchestrator's inherited environment resolves
   `resolve_history_db()` to `<main repo>/.ll/history.db`. Use the
   `python3 -c` env-probe shape from
   `test_worktree_utils.py::test_verify_gate_marker_set_in_child_env` (:556-577).
3. **Rows survive teardown.** Full lifecycle — `setup_worktree` → write a row
   from a process running inside the worktree → `cleanup_worktree` — leaves the
   row queryable from the main repo's DB. Use the inject → subprocess writes →
   read-back shape from
   `test_hooks_integration.py::test_writes_lifecycle_row_on_threshold_crossing`
   (:300-338).
4. **FSM shell actions are covered**, not just host-CLI sessions: a shell action
   executed with `cwd=<worktree>` resolves the main repo's DB. This is the
   coverage the superseded host-runner approach would have missed.
5. **The cwd precondition is pinned**: a test asserts `setup_worktree()`
   resolves against the main repo when invoked from the repo root and from a
   repo subdirectory, and that an already-set `LL_HISTORY_DB` is preserved
   (nested-worktree / explicit-override case).
6. **Concurrency**: N ≥ 4 concurrent writer processes against one shared DB
   complete with zero `sqlite3.OperationalError` ("database is locked"). WAL +
   `busy_timeout` (`schema.py:978-979`) is designed for this; the test pins it.

## Implementation Steps

1. Add the `os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))`
   export to `setup_worktree()` (`worktree_utils.py:157`), before worktree
   creation, with the function-local `session_store.db` import.
2. Add tests for AC-1 through AC-6 in `scripts/tests/test_worktree_utils.py`
   (AC-1/2/3/5) and a small integration test for AC-4 exercising an FSM shell
   action with `working_dir` set to a worktree. AC-6 can be a focused
   concurrency test against a `tmp_path` DB.
3. Document worktree-child inheritance of `LL_HISTORY_DB` in
   `docs/reference/HOST_COMPATIBILITY.md:388` (the env-var table row currently
   describes it only as a test-isolation override).

No other production file changes. In particular: no signature change to
`run_claude_command()`, no `build_streaming()` changes, no `host_runner.py`
helper, no `runner_spec.py`/`issue_manager.py`/`worker_pool.py` edits.

## Integration Map

### Files to Modify
- `scripts/little_loops/worktree_utils.py` (`setup_worktree`, :157) — the sole
  production change

### Dependent Files (behavior changes, no edit required)
- `scripts/little_loops/session_store/db.py` — `_resolve_db_path` /
  `resolve_history_db`; the env branch (`:96`) stops being dead code
- `scripts/little_loops/subprocess_utils.py:421-422` — `env = os.environ.copy();
  env.update(invocation.env)` now carries `LL_HISTORY_DB` for free
- `scripts/little_loops/fsm/executor.py:2132-2137` — bare `subprocess.Popen`
  with `cwd=self.working_dir`; inherits for free
- `scripts/little_loops/worktree_utils.py:455-473`
  (`verify_epic_branch_before_merge`) — `os.environ.copy()` inherits for free
- `scripts/little_loops/parallel/worker_pool.py:812-814`
  (`_detect_worktree_model_via_api`) — inherits for free
- `scripts/little_loops/runner_spec.py` — inherits for free
- `scripts/little_loops/hooks/session_start.py:145-146`,
  `hooks/post_commit.py:95`, `pytest_history_plugin.py:45` — existing readers,
  now actually reachable in worktree sessions

### Similar Patterns
- `LL_HANDOFF_THRESHOLD` / `LL_CONTEXT_LIMIT` export for descendant inheritance
  — `cli/parallel.py:237,242`, `cli/auto.py:86,91`, `cli/sprint/run.py:374,378`,
  `cli/loop/run.py:218,223,226`, `cli/loop/lifecycle.py:547,552`
- `LL_HOST_CLI` export — `host_runner.py:1680`
- `LL_VERIFY_GATE` worktree-scoped marker — `worktree_utils.py:455-461`
  (same-function build-and-consume variant)

### Tests
- `scripts/tests/test_worktree_utils.py::test_verify_gate_marker_set_in_child_env`
  (:556-577) — direct template for AC-2: asserts an env var reached a
  worktree-scoped child via a `python3 -c` probe
- `scripts/tests/test_hooks_integration.py::test_writes_lifecycle_row_on_threshold_crossing`
  (:300-338) — direct template for AC-3: inject `LL_HISTORY_DB`, run a
  subprocess, read rows back from the DB file
- `scripts/tests/test_session_store_db.py::TestDbPathResolution` (:37-135) —
  in-process precedence coverage; the export must not perturb it
- `scripts/tests/conftest.py` — `_isolate_history_db_session` (:553-564),
  `_isolate_history_db` (:580-613), `_guard_real_history_db` (:617-657); see
  **Interaction with the test suite** above
- No existing test combines "worktree" and `LL_HISTORY_DB` (confirmed via
  repo-wide grep) — all six ACs are new coverage

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:388` — `LL_HISTORY_DB` env-var table row

The following were listed under the superseded approach and are **no longer
in scope**, since neither the resolution chain nor any host-runner surface
changes: `docs/reference/CONFIGURATION.md:610,1479`, `docs/ARCHITECTURE.md:785`,
`docs/reference/API.md:8562`.

### Sequencing

ENH-3095 / ENH-3097 (`AutomationContext` threading through
`subprocess_utils.py` / `host_runner.py`) were a merge-conflict risk under the
superseded approach. Under this one there is **no overlap** — this issue touches
only `worktree_utils.py`. No sequencing constraint, no `blocked_by`.

## Impact

- **Priority**: P2 - Silent loss of history on the default automation path; no
  error surfaces
- **Effort**: Small - one line of production code plus tests
- **Risk**: Low-Medium - the code change is minimal and idempotent; the residual
  risk is behavioral, not structural: more concurrent writers on one SQLite
  file (the designed-for case, pinned by AC-6) and the cwd precondition
  documented above (pinned by AC-5)
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Superseded 2026-08-09: the three prior `/ll:confidence-check` passes
(2026-08-08 and 2026-08-09) all scored the host-runner threading approach —
"wide, cross-cutting fanout ... ~9-10 distinct sites", "non-mechanical change
surface with a live sequencing risk" against ENH-3095/3097, `outcome_confidence:
62`. Those risk factors do not describe the current approach, which is one line
in one file with no signature change and no ENH-3095/3097 overlap. The
frontmatter scores (`confidence_score`, `outcome_confidence`,
`score_complexity`, `score_change_surface`) are stale and tool-owned — **re-run
`/ll:confidence-check` before implementing** rather than trusting them._

### Carried-forward note (still valid)

`ll-issues format-check` flags `mislocated_symbol_ref: worktree_copy_files
(claimed in scripts/little_loops/cli/parallel.py)` — verified as a linter false
positive: the prose reference is to the dotted config key
`parallel.worktree_copy_files` (present in `config-schema.json:360`), not a
claim that the symbol lives in `cli/parallel.py`. No action needed.

## Session Log
- `/ll:manage-issue` - 2026-08-09T14:42:44 - `bacf1d76-e8f9-4555-b27d-df46b16e970f.jsonl`
- `/ll:confidence-check` - 2026-08-09T14:12:20 - `bacf1d76-e8f9-4555-b27d-df46b16e970f.jsonl`
- `/ll:ready-issue` - 2026-08-09T14:10:44 - `c110f8a2-c732-4564-9242-5bf38137cbf8.jsonl`
- `/ll:confidence-check` - 2026-08-09T14:03:48 - `6b3b04d3-25c9-43d2-bf5f-32a183518c55.jsonl`
- `/ll:confidence-check` - 2026-08-09T03:38:18 - `a586a544-6525-4902-8718-867d3dbb4200.jsonl`
- `/ll:reconcile-issue` - 2026-08-09T03:30:04 - `83bf90ea-254d-4998-aaa3-1f6e622ec8d9.jsonl`
- `/ll:audit-issue-conflicts` - 2026-08-09T03:26:27 - `39a3fd52-4ea1-4f7e-83e9-1871820dfe65.jsonl`
- `/ll:confidence-check` - 2026-08-09T02:54:13 - `d6eb2d4e-2ab1-4ee2-9817-a4e5989f03cb.jsonl`
- `/ll:confidence-check` - 2026-08-09T02:44:06 - `949315da-0b72-4a22-a42d-0493ed4f18c1.jsonl`
- `/ll:decide-issue` - 2026-08-09T02:03:57 - `b7a1eb33-0bc6-4bb9-a60c-0e95c4863a8d.jsonl`
- `/ll:confidence-check` - 2026-08-09T01:52:31 - `4bfd9abe-af89-4c06-a44b-8c4385814986.jsonl`
- `/ll:decide-issue` - 2026-08-09T01:48:32 - `e99fadf0-4a73-439a-8b6e-81b9493d2612.jsonl`
- `/ll:refine-issue` - 2026-08-09T01:44:04 - `5225f24f-a1c9-4f87-82aa-5db111f5149d.jsonl`
- `/ll:confidence-check` - 2026-08-08T21:32:45 - `3b85ed9c-ef3f-4ce0-b887-f5737d6ea801.jsonl`
- `/ll:wire-issue` - 2026-08-08T21:17:27 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:04:30 - `29dcd8e6-5691-426f-91c4-b6457c12fffb.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

## Resolution

- **Action**: fix
- **Completed**: 2026-08-09
- **Status**: Completed

### Changes Made
- `scripts/little_loops/worktree_utils.py:setup_worktree()`: added
  `os.environ.setdefault("LL_HISTORY_DB", str(resolve_history_db()))` before
  worktree creation, so every descendant process (host-CLI sessions, FSM shell
  actions, hooks, pytest runs) inherits the main repo's `history.db` instead of
  resolving a throwaway `<worktree>/.ll/history.db` that teardown deletes.
- `docs/reference/HOST_COMPATIBILITY.md`: documented the worktree-child
  inheritance behavior in the `LL_HISTORY_DB` env-var table row.
- `scripts/tests/test_worktree_utils.py`: added `TestSetupWorktreeHistoryDbExport`
  covering AC-1, AC-2, AC-3, AC-5, and AC-6.
- `scripts/tests/test_fsm_executor.py`: added
  `test_shell_action_in_worktree_resolves_main_repo_history_db` covering AC-4.

### Verification Results
- Tests: PASS (18747 passed, 43 skipped; 1 pre-existing failure in
  `test_prose_dep_sweep_gate.py::test_no_prose_dependency_drift_in_repo`,
  confirmed present on `main` before this change and unrelated to this issue's
  scope — unrelated issues ENH-3095/FEAT-3122)
- Lint: PASS (`ruff check` on changed files)
- Type check: PASS (`mypy` on `worktree_utils.py`)

---

## Status

**Open** | Created: 2026-08-08 | Priority: P2
