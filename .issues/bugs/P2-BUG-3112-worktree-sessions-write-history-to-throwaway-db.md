---
id: BUG-3112
title: Worktree sessions write session history to a throwaway .ll/history.db
type: BUG
priority: P2
status: open
parent: EPIC-3111
captured_at: '2026-08-08T20:32:03Z'
discovered_date: 2026-08-08
discovered_by: capture-issue
labels:
- worktree
- history
- data-loss
confidence_score: 95
outcome_confidence: 62
score_complexity: 14
score_test_coverage: 19
score_ambiguity: 19
score_change_surface: 10
decision_needed: false
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
`_resolve_db_path` (`session_store/db.py:68-104`) walks env → config → default
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

## Root Cause

- **File**: `scripts/little_loops/worktree_utils.py`
- **Anchor**: `in function setup_worktree()`
- **Cause**: `setup_worktree` establishes a worktree whose resolved project root
  is the worktree itself, but never propagates a history-DB location. There is
  no `LL_HISTORY_DB` setter anywhere in the codebase — only readers
  (`session_store/db.py:96`, `hooks/session_start.py:167`,
  `hooks/post_commit.py:95`) — so the env-override branch of `_resolve_db_path`
  is dead in practice and resolution falls through to the worktree-local default.

## Proposed Solution

Point worktree-scoped processes at the main repo's DB rather than copying it.

Copying is the wrong fix twice over: a `shutil.copy2` of a live WAL SQLite file
without its `-wal`/`-shm` siblings yields a stale or torn snapshot, and even a
clean copy forks the history so the worktree's writes are still discarded at
cleanup.

Sharing is what the store is already built for — `session_store/schema.py:978-979`
sets `PRAGMA busy_timeout` and `journal_mode = WAL` with the comment that "under
ll-parallel many processes contend at once."

Set `LL_HISTORY_DB=<main repo>/.ll/history.db` in the environment handed to
worktree-scoped sessions. Decide between:

### Approach A — Env Injection (Selected)

> **Selected:** Option A — env-injection at the host-runner/`run_claude_command`
> boundary matches the codebase's existing `_apply_automation_env`/
> `LL_VERIFY_GATE` idiom and slots directly into existing table-driven and
> per-runner test shapes; Option B introduces a wholly new marker-file
> resolution mechanism with no precedent and higher regression risk against
> the shared `_resolve_db_path` chain.

Injecting it at the three worktree-creating call sites (`fsm/executor.py:942`,
`cli/loop/run.py:484`, `parallel/worker_pool.py:774`).

**Preferred** — the smaller, more explicit change.

### Approach B — Origin Marker File (Rejected)

Having `setup_worktree` record the origin repo path in the worktree (e.g.
alongside the `.ll-session-<pid>` marker) and resolving from there in
`_resolve_db_path`.

The verify-gate worktree's DB-sharing behavior was a separate decision,
resolved below — see **Verify-Gate Worktree Decision**.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

_Added by `/ll:refine-issue` — 2026-08-09 — based on codebase analysis:_

`codebase-pattern-finder` traced how this codebase has previously threaded a new
env-var marker through `HostInvocation.env`/`build_streaming()`/`run_claude_command()`
— the same boundary `LL_HISTORY_DB` must cross:

- **Shared-helper convention exists for one marker, is contested for another.**
  `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE` go through one shared function,
  `_apply_automation_env(env, automation_profile)` (`host_runner.py:1547-1562`),
  called once from each of the 5 concrete `build_streaming()` implementations
  (`ClaudeCodeRunner` :353, `CodexRunner` :644, `GeminiRunner` :1034, `OmpRunner`
  :1219, `KimiRunner` :1412). `GIT_DIR`/`GIT_WORK_TREE`, by contrast, is
  inconsistently sourced: `GeminiRunner._worktree_env()` (`host_runner.py:963-980`)
  is called cross-class by `OmpRunner` and `KimiRunner`, while `ClaudeCodeRunner`
  and `CodexRunner` inline the identical parse logic in their own
  `build_streaming()` bodies instead of calling it. Both shapes — one shared
  helper called everywhere, and one helper called by some runners while others
  duplicate the logic — coexist today; which shape `LL_HISTORY_DB` follows is
  an open choice, not settled by precedent.
- **`run_claude_command()` has no env-passthrough parameter.** It builds
  `env = os.environ.copy(); env.update(invocation.env)` internally
  (`subprocess_utils.py:414-415`). The only way a new var reaches the spawned
  process through this path is by making it appear inside `HostInvocation.env`,
  i.e. inside a `build_streaming()` implementation — there is no shortcut at
  the `run_claude_command()` call sites themselves.
- **A same-function, build-and-consume-locally marker also exists as precedent**,
  separate from the `HostInvocation.env` path: `verify_epic_branch_before_merge()`
  (`worktree_utils.py:455-473`) does `env = os.environ.copy(); env["LL_VERIFY_GATE"] = "1"`
  directly ahead of its own `subprocess.run(...)`, bypassing `run_claude_command()`
  entirely. Its inline comment explicitly names this as mirroring the
  `LL_NON_INTERACTIVE` marker idiom.
- **Test shape precedent — table-driven vs. per-class.** `TestAutomationProfileEnvAcrossRunners`
  (`test_host_runner.py:51-82`) is `@pytest.mark.parametrize` across all 5 concrete
  runner classes, asserting one env-var contract holds uniformly — the docstring
  states this shape exists specifically to keep the 5 runners "from drifting apart
  again (BUG-3058 precedent)." `test_build_streaming_worktree_env`, by contrast,
  is repeated independently per runner class (`:810`, `:975`, `:1129`). Both
  shapes are established in this file; a table-driven test is the shape this
  codebase uses when it wants drift across runners to fail loudly.
- **Inject → subprocess writes → read-back-from-file is an existing test shape
  for `LL_HISTORY_DB` specifically**: `test_writes_lifecycle_row_on_threshold_crossing`
  (`test_hooks_integration.py:300-338`) sets `env["LL_HISTORY_DB"] = str(db_path)`,
  runs a real subprocess, then queries rows back out of that DB file — the
  closest existing analogue to the AC-level integration test this issue's
  Implementation Steps already call out as missing.
- **No existing shared helper composes the `os.environ.copy()` base itself** —
  every concrete `build_streaming()` and `verify_epic_branch_before_merge()`
  builds its own base `env` dict inline; `subprocess_utils.py:414-415` is the
  one place that composes `HostInvocation.env` onto the ambient environment for
  host-CLI spawns specifically.

### Codebase Research Findings — correction to injection-point choice

`codebase-analyzer` traced the actual env flow for all three call sites named
above under option (a) (`fsm/executor.py:942`, `cli/loop/run.py:484`,
`parallel/worker_pool.py:774`) and found none of them builds a subprocess
`env` dict — all three are `setup_worktree()`/`_setup_worktree()` calls that
only create the worktree directory/branch. The actual point where a child
process's environment is assembled is **downstream**, inside
`run_claude_command()` (`subprocess_utils.py:320-341`), which has no
`env`/`env_overrides` parameter today — it builds
`env = os.environ.copy(); env.update(invocation.env)` internally
(`subprocess_utils.py:414-415`) from `HostInvocation.env`, which each host
runner populates inside its own `build_streaming()` (e.g.
`ClaudeCodeRunner.build_streaming()`, `host_runner.py:~347`).

Concretely, option (a) as stated ("injecting it at the three
worktree-creating call sites") cannot work as a same-function edit at those
three lines — `setup_worktree()` itself has no env to inject into. The
env-var must instead be threaded either through a new parameter on
`run_claude_command()` (and each `HostRunner.build_streaming()` /
`HostInvocation.env` that feeds it), or added to `HostInvocation.env`
directly at the point each host runner already builds it. `worker_pool.py`
has a second, independent env-build path in `_detect_worktree_model_via_api`
(`worker_pool.py:812-814`) that would need the same var added separately.

Existing precedent for a worktree-scoped env-var marker: `LL_VERIFY_GATE`
injection in `verify_epic_branch_before_merge`
(`worktree_utils.py:455-461`) — `env: dict[str, str] = os.environ.copy();
env["LL_VERIFY_GATE"] = "1"`, built and consumed in the same function. No
call site in this codebase resolves parent-repo identity via a marker file
left in the worktree; every existing analogous case (`LL_VERIFY_GATE`,
`LL_NON_INTERACTIVE`, `LL_AUTOMATION`) uses an env-var marker, consistent
with option (a)'s general approach — only the specific three line numbers
cited need correction, not the approach itself.

### Decision Rationale

**Selected: Option A** — thread `LL_HISTORY_DB` into the environment at the
host-runner/`run_claude_command` boundary (per the corrected call-site
analysis above: `HostInvocation.env` inside each `build_streaming()`, plus
`worker_pool.py:812-814` and `runner_spec.py`'s direct-call path), rather
than having `setup_worktree()` write an origin-repo marker file for
`_resolve_db_path` to read back (Option B).

Option A matches two established idioms in this codebase — the shared
`_apply_automation_env` helper called identically across all 5
`build_streaming()` implementations, and the single-function
`env["LL_VERIFY_GATE"] = "1"` pattern in `verify_epic_branch_before_merge()`
— and slots directly into existing test shapes (`TestAutomationProfileEnvAcrossRunners`'s
table-driven cross-runner assertions, the per-runner `test_build_streaming_worktree_env`
template, and the inject-subprocess-read-back shape in
`test_writes_lifecycle_row_on_threshold_crossing`). Option B would introduce
a wholly new marker-file resolution mechanism with zero precedent in this
codebase (every existing analogous marker — `LL_VERIFY_GATE`,
`LL_NON_INTERACTIVE`, `LL_AUTOMATION` — is an env var, not a file), requires
more edit sites (writer + reader + verify-gate branch decision) than Option
A's single injection point, and risks destabilizing the shared, heavily-used
`_resolve_db_path` precedence chain that the `conftest.py` history-DB
isolation fixtures already depend on.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 2 | 0 |
| Simplicity | 2 | 1 |
| Testability | 3 | 1 |
| Risk | 1 | 0 |
| **Total** | **8/12** | **2/12** |

Key evidence: `_apply_automation_env` (`host_runner.py:1547-1562`, called at
5 sites) and `LL_VERIFY_GATE` (`worktree_utils.py:455-473`) are the only
existing precedents for a worktree/host-scoped env-var marker, both env-based;
no existing code resolves parent-repo identity via a marker file left in a
worktree. Option A's residual risk is coordination with in-flight
ENH-3095/ENH-3097 (same `subprocess_utils.py`/`host_runner.py` line ranges
via a competing `AutomationContext` mechanism) — already flagged in this
issue's wiring section, not a new concern raised by this decision.

### Verify-Gate Worktree Decision

The verify-gate worktree (`worktree_utils.py:445`) deliberately runs with
`LL_VERIFY_GATE=1` and `copy_files=[]` — isolated from a normal worktree's
setup. Whether it should also share the main repo's `LL_HISTORY_DB` (per
Approach A above) or keep writing to its own throwaway DB is still an open
decision, unresolved.

### Option A

> **Selected:** Option A — `verify_epic_branch_before_merge` already builds
> its child env via `env = os.environ.copy()` and only *adds* keys
> (`LL_VERIFY_GATE`, `PYTHONPATH`, xdist/fuzz vars); there is zero precedent
> anywhere in this codebase for popping/excluding an inherited env var, so
> sharing requires no new code, while excluding would introduce a
> first-of-its-kind conditional read of `LL_VERIFY_GATE` to suppress
> propagation.

Share the main repo's `LL_HISTORY_DB` with the verify-gate worktree too, same
as every other worktree-scoped process under this issue's fix — one env-var
rule, no special case.

### Option B

Keep the verify-gate worktree isolated from the shared history DB — do not
set `LL_HISTORY_DB` when `LL_VERIFY_GATE=1`, preserving its current
deliberately-sandboxed behavior.

### Decision Rationale — Verify-Gate Worktree Decision

**Selected: Option A** — share `LL_HISTORY_DB` with the verify-gate worktree,
no special case.

`verify_epic_branch_before_merge()` (`worktree_utils.py:461`) already builds
its child env as `env = os.environ.copy()` and only overlays additive keys
(`LL_VERIFY_GATE`, `PYTHONPATH`, xdist/fuzz vars) — there is no existing
`env.pop(...)`/exclusion idiom anywhere in `scripts/little_loops` to borrow
for an isolation carve-out. `LL_VERIFY_GATE`'s only established consumer
(`test_wiring_skills_and_commands.py`, per BUG-2649) uses it purely as a test
self-quarantine marker, never to gate env-var propagation, so Option B would
be a first-of-its-kind use of that flag. The verify-gate's own `test_cmd`
pytest run already writes into `resolve_history_db()` via
`pytest_history_plugin.py`'s `LLHistoryPlugin._record()` — the exact chain
this issue fixes — and is silently discarded today; the plugin's
`_infer_env_label()` already anticipates and labels `"worktree"`-origin runs
rather than excluding them, so sharing fixes the same data-loss failure mode
BUG-3112 documents for sessions, for verify-gate's `test_run_events` rows too.
`setup_worktree()` also already forwards git identity and `.claude/` into the
verify-gate worktree unconditionally, independent of `copy_files=[]` — "fully
isolated except for `copy_files`" is not how the verify-gate worktree
actually behaves today, so a DB-sharing carve-out would be inconsistent with
its existing partial-inheritance shape.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 1 |
| Simplicity | 3 | 1 |
| Testability | 2 | 2 |
| Risk | 2 | 2 |
| **Total** | **10/12** | **6/12** |

Key evidence: no codebase precedent excludes an inherited env var for
isolation; `LL_VERIFY_GATE` has one production consumer and it is a test
self-quarantine flag, not a side-effect suppressor; the general
`copy_files`-based worktree setup already excludes `history.db*`/`queue.db*`
from the *copy* mechanism (a separate concern from *sharing* via env var,
which this fix relies on instead of copying). Residual risk: verify-gate runs
may write more `test_run_events` rows into the shared DB than a normal
session (repeated merge-gate attempts), a volume consideration rather than a
correctness one — WAL + `busy_timeout` (`schema.py:978-979`) is already
designed for concurrent writers.

## Program Design

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Types
N/A — no new data shape; this is `os.environ`-style `dict[str, str]` env-var propagation onto existing structures.

### Signatures
- `setup_worktree(repo_path: Path, worktree_path: Path, branch_name: str, copy_files: list[str], logger: Logger, git_lock: GitLock, base_branch: str | None = None, checkout_existing: bool = False) -> None` — `worktree_utils.py:157-166`. Returns `None`; cannot carry an origin-repo path back to its caller. `repo_path` is already held by each of the three call sites before they call it.
- `_resolve_db_path(path: Path | str | None = None) -> Path` — `session_store/db.py:68-107`. For a default-shaped path, precedence is `os.environ.get("LL_HISTORY_DB")` (line 96, wins immediately if truthy) → `history.db_path` config key via `_config_db_path()` (lines 99-101) → `resolve_ll_dir()`-anchored default (lines 102-107). `resolve_ll_dir()` (`paths.py:45-83`) defaults `start=Path.cwd()`, so with subprocess `cwd` set to the worktree, an unset `LL_HISTORY_DB` resolves to the worktree's own `.ll/history.db`.
- `resolve_history_db() -> Path` — `session_store/db.py:110-118`, thin public wrapper over `_resolve_db_path`.
- `run_claude_command(...)` — `subprocess_utils.py:320-341`. **No `env`/`env_overrides` parameter.** Internally builds `env = os.environ.copy(); env.update(invocation.env)` (lines 414-415) — no caller can inject an additional var through this function's current public signature.
- `HostInvocation.env: dict[str, str]` — `host_runner.py:162` (`field(default_factory=dict)`), populated per-host inside each runner's `build_streaming()` (e.g. `ClaudeCodeRunner.build_streaming()` ~line 347).

### Call Path
`fsm/executor.py:942 setup_worktree()` (creates the worktree only; builds no env) → `FSMExecutor(working_dir=worktree_path)` (lines 1001-1012) → child executor's subprocess actions → `run_claude_command()` (`subprocess_utils.py:320`) → `env = os.environ.copy(); env.update(invocation.env)` (`subprocess_utils.py:414-415`) → spawned CLI process, `cwd=worktree_path`, `LL_HISTORY_DB` absent → `_resolve_db_path()` falls through to the worktree-local `.ll/history.db`.

`cli/loop/run.py:484 setup_worktree()` → loop runs via the same FSM executor with `working_dir=_worktree_path` → identical downstream env-build gap.

`parallel/worker_pool.py:774 _setup_worktree()` → `WorkerPool._run_claude_command()` (`worker_pool.py:885-934`) → `run_claude_command`/`_run_claude_base` → identical downstream env-build gap.

### Decision Rules
N/A — no new gap kind, gate, or threshold; this is env-variable propagation into an existing resolution chain that already treats `LL_HISTORY_DB` as authoritative.

## Implementation Steps

1. Choose the injection strategy (env at call sites vs. origin-marker resolution).
2. Thread `LL_HISTORY_DB` into the environment for worktree-scoped child
   processes, ensuring it survives into host CLI invocations via
   `subprocess_utils`.
3. Confirm concurrent-writer behavior under ll-parallel with multiple worktrees
   sharing one DB (WAL + `busy_timeout` should cover it; verify no
   `database is locked` under realistic worker counts).
4. Decide and document the verify-gate worktree's behavior.
5. Test: assert that a session run with cwd inside a worktree resolves the main
   repo's DB path and that rows written there are visible from the main tree
   after `cleanup_worktree`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Check `.issues/enhancements/P3-ENH-3095-...` and `P3-ENH-3097-...` status
  before starting — both touch the identical `subprocess_utils.py`/
  `host_runner.py` line ranges via an `AutomationContext` dataclass; confirm
  whether to sequence around them or thread `LL_HISTORY_DB` independently
- Add `LL_HISTORY_DB` handling to `runner_spec.py`'s blocking/default-mode
  path, which calls `resolve_host().build_streaming()` directly and bypasses
  `run_claude_command()`
- Add `LL_HISTORY_DB` to `worker_pool.py:812-814`
  (`_detect_worktree_model_via_api`), the second independent env-build path
- Verify the fix resolves the main-repo path explicitly rather than reading
  ambient `os.environ["LL_HISTORY_DB"]`, since `conftest.py`'s
  `_isolate_history_db*` fixtures already force that var for every test run
- Update `test_build_streaming_worktree_env` (`test_host_runner.py:810,975,1129`)
  and `test_invocation_env_overrides_os_environ`
  (`test_subprocess_utils.py:2371-2403`) with `LL_HISTORY_DB` assertions
- Update the fixed-signature mock in
  `test_worker_pool.py::TestWorkerPoolClaudeCommand::test_run_claude_command_tracks_process`
  (:2822-2860) if a new kwarg is added to `_run_claude_base`
- Add a new integration test: worktree lifecycle end-to-end (`setup_worktree`
  → run session → `cleanup_worktree`) asserting history rows persist in the
  main repo's DB — no existing test covers this
- Update `docs/reference/HOST_COMPATIBILITY.md:388`,
  `docs/reference/CONFIGURATION.md:610,1479`, `docs/ARCHITECTURE.md:785`, and
  `docs/reference/API.md:8562` to describe worktree-child inheritance of
  `LL_HISTORY_DB`

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py` (:942)
- `scripts/little_loops/cli/loop/run.py` (:484)
- `scripts/little_loops/parallel/worker_pool.py` (:774, and :812-814 for the
  second, independent env-build path in `_detect_worktree_model_via_api`)
- `scripts/little_loops/worktree_utils.py` (:157, and :445 for the verify gate)
- `scripts/little_loops/subprocess_utils.py` (`run_claude_command`, :320-341,
  :414-415 env build) — this is the actual downstream env-assembly point per
  the Proposed Solution correction above, not `setup_worktree()` itself
  _[Wiring pass added by `/ll:wire-issue`]_
- `scripts/little_loops/host_runner.py` (`HostInvocation.env`,
  `_apply_automation_env` ~:1547, and each `HostRunner.build_streaming()`)
  _[Wiring pass added by `/ll:wire-issue`]_

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store/db.py` — `_resolve_db_path` / `resolve_history_db`
- `scripts/little_loops/subprocess_utils.py` — env passed to host CLI
- `scripts/little_loops/hooks/session_start.py`, `hooks/post_commit.py` — existing `LL_HISTORY_DB` readers

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py` — wraps `run_claude_command`/
  `run_with_continuation`; needs the same env-threading if reachable from a
  worktree session
- `scripts/little_loops/runner_spec.py` — three forwarding call sites; one
  (blocking/default mode) calls `resolve_host().build_streaming()` directly,
  bypassing `run_claude_command()` entirely, so it needs its own check
- `scripts/little_loops/fsm/runners.py` — imports `subprocess_utils`, calls
  `run_claude_command`
- `scripts/tests/conftest.py` — `_isolate_history_db_session` (:553-564) and
  `_isolate_history_db` (:580-613) already force `LL_HISTORY_DB` into
  `os.environ`/`monkeypatch` for every test; the fix must resolve the
  main-repo path explicitly rather than reading ambient `os.environ`, or it
  will silently no-op under the test suite. `_guard_real_history_db`
  (:617-657) asserts no `sqlite3.connect` resolves to the real
  `.ll/history.db` — new injection code must not trip this guard during tests.

### Related In-Flight Issues (potential sequencing conflict)

_Wiring pass added by `/ll:wire-issue`:_
- `.issues/enhancements/P3-ENH-3095-add-automationcontext-dataclass-and-thread-through-hostrunner-build-streaming.md`
  and `.issues/enhancements/P3-ENH-3097-thread-automationcontext-through-run-claude-command-and-callers.md`
  touch the identical call chain (`subprocess_utils.py` env-build block, all
  7 runner `build_streaming()` signatures, `fsm/executor.py` baseline-arm/
  `extra_kwargs` sites, `worker_pool.py:924-934`) via a different mechanism —
  an `AutomationContext` dataclass replacing `automation_profile: str | None`.
  `AutomationContext`'s 3 fields (`profile`, `idle_timeout`,
  `disable_background_tasks`) have no general-purpose env-override slot, so
  `LL_HISTORY_DB` does not drop into it as currently scoped. No hard
  `blocked_by` is required, but landing order affects merge-conflict risk on
  shared line ranges — check ENH-3095/ENH-3097 status before starting.

### Similar Patterns
- `LL_VERIFY_GATE` env propagation in `worktree_utils.py:458-461` — the existing
  precedent for handing a worktree-scoped process an env override

### Tests
- `scripts/tests/` — worktree_utils and session_store resolution coverage

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_worktree_utils.py::test_verify_gate_marker_set_in_child_env`
  (:556-577) — direct template: asserts an env var reached a worktree-scoped
  child process via a `python3 -c` probe as `test_cmd`
- `scripts/tests/test_hooks_integration.py::test_writes_lifecycle_row_on_threshold_crossing`
  (:300-338) — closest end-to-end analogue: sets `LL_HISTORY_DB` in env, runs
  a subprocess, reads rows back from the DB file
- `scripts/tests/test_session_store_db.py::TestDbPathResolution` (:37-135) —
  in-process precedence coverage via `monkeypatch.setenv("LL_HISTORY_DB", ...)`
- `scripts/tests/test_subprocess_utils.py::test_invocation_env_overrides_os_environ`
  (:2371-2403) and `test_empty_ll_automation_beats_ambient_env` (:2405-2446) —
  assert the exact `env = os.environ.copy(); env.update(invocation.env)`
  contract; add a companion test once `HostInvocation.env` carries
  `LL_HISTORY_DB`
- `scripts/tests/test_host_runner.py::test_build_streaming_worktree_env`
  (:810, :975, :1129, one per runner class) — direct template for a new
  `LL_HISTORY_DB` assertion in `build_streaming()`, same fixture shape as the
  existing `GIT_DIR`/`GIT_WORK_TREE` worktree-env checks
- `scripts/tests/test_worker_pool.py::TestWorkerPoolClaudeCommand::test_run_claude_command_tracks_process`
  (:2822-2860) — mocks `_run_claude_base` with a fixed, non-`**kwargs`
  signature; will break with `TypeError` if a new env-carrying kwarg is added
  without updating this mock
- New test needed (no existing coverage): an integration test exercising the
  full worktree lifecycle (`setup_worktree` → run session → `cleanup_worktree`)
  asserting history rows persist in the main repo's DB after cleanup — this
  is the AC-level regression test for this bug
- `scripts/little_loops/parallel/worker_pool.py:812-814`
  (`_detect_worktree_model_via_api`) has no existing env-path test coverage

### Documentation
- `docs/reference/CLI.md` and the worktree copy-semantics doc (ENH-3115)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/HOST_COMPATIBILITY.md:388` — `LL_HISTORY_DB` env-var table
  row, currently describes it only for test isolation
- `docs/reference/CONFIGURATION.md:610,1479` — env-var precedence note under
  `events.sqlite` / `history.db_path`
- `docs/ARCHITECTURE.md:785` — `cli_event_context()` row notes it "Honors
  `LL_HISTORY_DB` env var for path override"
- `docs/reference/API.md:8562` — `session_store` module doc's precedence
  chain (env → config → default); doesn't currently describe worktree-child
  inheritance

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-08 — based on codebase analysis:_

### Codebase Research Findings — additional target files and test precedent

`codebase-pattern-finder` identified the actual env-injection surface as
`scripts/little_loops/subprocess_utils.py` (`run_claude_command`, no `env`
passthrough today) and `scripts/little_loops/host_runner.py` (each
`HostRunner.build_streaming()` populates `HostInvocation.env`), not the three
`setup_worktree()` call sites themselves (see Proposed Solution findings
above for the full trace). `scripts/little_loops/parallel/worker_pool.py`
has a second, independent env-build path at `_detect_worktree_model_via_api`
(`worker_pool.py:812-814`) that would also need `LL_HISTORY_DB` added if that
code path can run inside a worktree.

- `scripts/little_loops/subprocess_utils.py` (`:320-341` `run_claude_command`, `:414-415` env build) — no existing env-merge helper to reuse; env construction is inline
- `scripts/little_loops/host_runner.py` (`:347` `ClaudeCodeRunner.build_streaming`, `:963-980` `GeminiRunner._worktree_env`, `:1547-1562` `_apply_automation_env`) — the one existing shared env-building helper (`_apply_automation_env`) sets `LL_AUTOMATION`/`LL_AUTOMATION_PROFILE`; no equivalent shared helper exists for a general worktree-scoped env base, so the "extract a helper" convention exists but is applied inconsistently across host-runner classes

### Tests (additional precedent, not currently worktree+history_db specific)
- `scripts/tests/test_worktree_utils.py::test_verify_gate_marker_set_in_child_env` (`:556-577`) — asserts env-var presence via a `python3 -c "...os.environ.get(...)..."` subprocess `test_cmd`
- `scripts/tests/test_hooks_integration.py::test_writes_lifecycle_row_on_threshold_crossing` (`:300-338`) — closer analogue for `LL_HISTORY_DB` itself: builds `env = os.environ.copy(); env["LL_HISTORY_DB"] = str(db_path)`, runs the hook script as a real subprocess with that env, then reads rows back from `db_path` — inject → subprocess writes → read back from the injected path
- `scripts/tests/test_session_store_db.py` (`TestDbPathResolution`, `:37-135`) — in-process precedence tests via `monkeypatch.setenv("LL_HISTORY_DB", ...)`, not worktree-specific
- No existing test combines "worktree" and `LL_HISTORY_DB` (confirmed via repo-wide grep) — worktree-scoped propagation is currently untested

## Impact

- **Priority**: P2 - Silent loss of history on the default automation path; no error surfaces
- **Effort**: Small - Env injection at three call sites plus tests
- **Risk**: Medium - Increases concurrent-writer contention on one SQLite file, which is the designed-for case but not currently exercised at this breadth
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Confidence Check Notes

_Added by `/ll:confidence-check` — 2026-08-09:_

**Readiness: 95/100** — PROCEED. **Outcome Confidence: 62/100** — below the
configured `outcome_threshold` (65).

### Outcome Risk Factors

- **Wide, cross-cutting fanout (Complexity: 14/25 — Breadth 5/12, Depth
  9/13)**: the fix touches ~9-10 distinct sites spanning subsystems —
  `subprocess_utils.py` (new env-passthrough on `run_claude_command`),
  `host_runner.py` (per-host `build_streaming()` changes across multiple
  runner classes), `worker_pool.py` (two independent env-build paths),
  `runner_spec.py`, `fsm/runners.py`, `issue_manager.py`, and
  `worktree_utils.py`. Each site is a contained, local logic change (not
  purely mechanical — `run_claude_command`'s signature itself changes), but
  the number of independently-editable call paths raises the chance of a
  missed site.
- **Residual ambiguity, narrower than before (Ambiguity: 19/25)**:
  `/ll:decide-issue` has resolved both open decisions previously flagged here
  — the injection-strategy choice (Option A, verified against the actual
  `run_claude_command`/`HostInvocation.env` call chain) and the verify-gate
  worktree's DB-sharing behavior (Option A: share, no special case). No
  undocumented judgment calls remain in the issue body; the residual risk is
  purely implementation care in applying an already-decided approach across
  many sites, not unresolved design.
- **Non-mechanical change surface with a live sequencing risk (Change
  Surface: 10/25)**: this is per-site behavioral work, not a uniform
  substitution — `run_claude_command`'s signature change and each host
  runner's `build_streaming()` need separate, non-identical edits. ENH-3095
  and ENH-3097 (confirmed still `open` as of 2026-08-09) touch the exact same
  `subprocess_utils.py`/`host_runner.py` line ranges via a competing
  `AutomationContext` mechanism — landing order affects merge-conflict risk,
  though no hard `blocked_by` is declared.

Test coverage is solid (19/25) — six existing tests are named as direct
templates covering most touched modules, and the one missing integration
test (worktree lifecycle → history persists after cleanup) is explicitly
called out as new AC-level coverage to add.

## Session Log
- `/ll:confidence-check` - 2026-08-09T02:44:06 - `949315da-0b72-4a22-a42d-0493ed4f18c1.jsonl`
- `/ll:decide-issue` - 2026-08-09T02:03:57 - `b7a1eb33-0bc6-4bb9-a60c-0e95c4863a8d.jsonl`
- `/ll:confidence-check` - 2026-08-09T01:52:31 - `4bfd9abe-af89-4c06-a44b-8c4385814986.jsonl`
- `/ll:decide-issue` - 2026-08-09T01:48:32 - `e99fadf0-4a73-439a-8b6e-81b9493d2612.jsonl`
- `/ll:refine-issue` - 2026-08-09T01:44:04 - `5225f24f-a1c9-4f87-82aa-5db111f5149d.jsonl`
- `/ll:confidence-check` - 2026-08-08T21:32:45 - `3b85ed9c-ef3f-4ce0-b887-f5737d6ea801.jsonl`
- `/ll:wire-issue` - 2026-08-08T21:17:27 - `5955cc74-6f18-496f-9ff9-59d7e836977d.jsonl`
- `/ll:refine-issue` - 2026-08-08T21:04:30 - `29dcd8e6-5691-426f-91c4-b6457c12fffb.jsonl`
- `/ll:capture-issue` - 2026-08-08T20:35:50 - `cf0cb0be-6bdf-436b-b626-68fabe345e75.jsonl`

---

## Status

**Open** | Created: 2026-08-08 | Priority: P2
