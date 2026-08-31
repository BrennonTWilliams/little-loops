---
id: ENH-3365
type: ENH
priority: P2
status: done
captured_at: '2026-08-30T23:30:00Z'
completed_at: '2026-08-31T04:01:46Z'
discovered_date: 2026-08-30
discovered_by: audit-loop-run
relates_to:
- BUG-3364
decision_needed: false
confidence_score: 100
outcome_confidence: 71
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
---

# ENH-3365: FSM shell actions should invoke the executor's own Python interpreter, not bare `python3`

## Summary

Shell-action Python heredocs across `scripts/little_loops/loops/*.yaml`
(e.g. `verify` at line 392, `merge_epic_branch` at line 543, `recheck_set`
at line 324 in `auto-refine-and-implement.yaml`) invoke `python3` bare,
relying on whatever interpreter is first on `PATH` at execution time to have
`little_loops` importable. That's not guaranteed to be the same interpreter
the FSM executor itself is running under — a machine can easily have
multiple Python installs on `PATH` (e.g. a pyenv-managed one with
`little_loops` installed editable, and an unrelated system/conda one
without it) — if `PATH` resolves `python3` to the wrong interpreter partway
through a long run, every subsequent heredoc in that run silently crashes
with `ModuleNotFoundError`.

## Current Behavior

Shell-action Python heredocs invoke bare `python3` (e.g. `python3 << 'PYEOF'
... PYEOF`), which PATH-resolves to whatever interpreter is first on the
child process's `PATH` at that moment — not necessarily the interpreter the
FSM executor itself is running under, and not necessarily one with
`little_loops` importable.

## Expected Behavior

Shell-action heredocs invoke `$${LL_PYTHON:-python3}`, where `LL_PYTHON` is
set to `sys.executable` — the exact interpreter running the loop — at the
shell-action spawn sites (`fsm/runners.py` / `runner_spec.py`, see Program
Design), so a heredoc that needs `little_loops` always resolves to an
interpreter that has it installed, regardless of what a bare `python3` on
`PATH` would resolve to.

**Escaping is mandatory**: in loop YAML action strings the bash expansion
must be written `$${LL_PYTHON:-python3}` (double `$`), because the FSM
interpolates the whole action string first and an unescaped
`${LL_PYTHON:-python3}` raises
`InterpolationError: expected namespace.path`
(`scripts/little_loops/fsm/interpolation.py:389-391`; the `$$` escape is
consumed by `ESCAPED_PATTERN` and reaches bash as `${LL_PYTHON:-python3}`).
Every YAML snippet in this issue uses the escaped form deliberately — copy
it verbatim into action strings.

## Evidence

During the `2026-08-30T222734-sprint-refine-and-implement` run, `recheck_set`,
`verify`, and `merge_epic_branch` all crashed with
`ModuleNotFoundError: No module named 'little_loops.config'` /
`'little_loops.worktree_utils'` roughly 2.5 hours in — after `checkout_epic_branch`
had run successfully earlier in the same run using presumably the same shell
environment. This audit independently reproduced the identical failure class
invoking the `ll-loop` CLI itself: one installed entry point on this
machine's `PATH` resolved to a Python without `little_loops` installed
(`ModuleNotFoundError: No module named 'little_loops.cli'`), while a
different entry point on the same `PATH` worked correctly — confirming the
split is a real, reproducible environment hazard, not a one-off fluke. See
[[BUG-3364]] for the specific downstream symptom (crash swallowed as an
empty verdict).

## Proposed Solution

Export `sys.executable` as `LL_PYTHON` into every shell action's environment
at the two decided spawn sites — `DefaultActionRunner.run()`'s shell branch
(`scripts/little_loops/fsm/runners.py:305`) and
`runner_spec.py::_run_cmd()` (lines 242-248) — via the existing
`project_child_env(extra={"LL_PYTHON": sys.executable})` idiom (see Program
Design; `fsm/executor.py` itself is NOT modified), and update loop YAML
heredocs to invoke
`$${LL_PYTHON:-python3}` instead of bare `python3`. This guarantees any
Python heredoc a loop runs uses the exact interpreter running the loop
itself — the one guaranteed to have `little_loops` importable — regardless
of what a bare `python3` on `PATH` resolves to at that moment.

## Scope Boundaries

- Does not change how `python3` is resolved for anything outside FSM shell
  actions (CLI entry points, hooks, `ll-*` scripts) — those already run under
  whatever interpreter invoked them directly.
- Does not attempt to fix or normalize `PATH` itself; `LL_PYTHON` is an
  additive override loop YAMLs must reference explicitly
  (`$${LL_PYTHON:-python3}`), not a `PATH` rewrite.
- **Migration scope (decided)**: this issue migrates the `LL_PYTHON` export
  itself (both spawn sites — see Decision Rules) **plus every `python3`
  invocation in `scripts/little_loops/loops/*.yaml` whose payload imports
  `little_loops`** — the actual hazard class. Bare-stdlib `python3`
  one-liners (`-c` json/text munging etc.) work under any interpreter and
  are NOT migrated here; sweeping the remaining ~155 heredocs / ~100
  `-c`/`-m` invocations to the escaped `$${LL_PYTHON:-python3}` form is a
  separate follow-up ENH to file at implementation time.

## Program Design

### Signatures

- `project_child_env(invocation=None, *, extra=None)` (`host_runner.py:1853`) — the single chokepoint every task-path shell-action `subprocess.*` spawn already routes through.
- `run(action, timeout, is_slash_command, on_output_line=None)` (`runners.py:117`, `DefaultActionRunner`) — its shell branch (`runners.py:305`) is where `project_child_env()` is called and where `LL_PYTHON` must be merged into `extra`.

### Call Path

`DefaultActionRunner.run` -> `project_child_env` (`extra={"LL_PYTHON": sys.executable}`) -> subprocess `env=` -> loop YAML heredoc `$${LL_PYTHON:-python3}`.

### Decision Rules

- **Clobber semantics (decided): always set.** `project_child_env()`'s merge
  order means `extra={"LL_PYTHON": sys.executable}` overrides any
  `LL_PYTHON` already present in `os.environ`. That is intentional: a
  stale/wrong inherited interpreter path is exactly the hazard this fix
  removes, and deterministic behavior (FSM shell actions always see the
  executor's own interpreter) beats honoring an ambient value. This is
  compatible with the hook-adapter shims' consumer contract
  (`PY="${LL_PYTHON:-...}"` — they treat any provided value as
  authoritative); it does narrow user-side `LL_PYTHON` overrides to
  non-FSM contexts, which the API.md update must state.
- **Both spawn sites (decided): in scope.** `runner_spec.py::_run_cmd()`
  (line 231, `env=project_child_env()` at 242-248) gets the same
  `extra={"LL_PYTHON": sys.executable}` as `fsm/runners.py:305` — one extra
  kwarg keeps the two task-path `bash -c` spawns consistent, and the
  `docs/reference/API.md:9946-9962` prose covers both anyway.
- **Escaping rule**: every YAML-side reference is written
  `$${LL_PYTHON:-python3}`; the unescaped form is an FSM
  `InterpolationError` (see Expected Behavior).

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- A second, independent bare `bash -c` FSM shell spawn also routes through `project_child_env()` with no `invocation`/`extra`: `_run_cmd(spec: ActionSpec)` in `scripts/little_loops/runner_spec.py:231`, `subprocess.Popen(["bash", "-c", spec.target], ..., env=project_child_env())` at lines 242-248. Resolved during review: this second site IS in scope — see Decision Rules.
- `project_child_env()`'s actual merge order (confirmed by reading its body, `host_runner.py:1853-1883`): `env = os.environ.copy()` then merge `invocation.env` (if an `invocation` is given) then merge `extra` (if given), each layer overriding the previous on key collision. Since the shell branch currently calls `project_child_env()` with zero arguments, today's shell action gets exactly `os.environ.copy()`.
- `LL_PYTHON` is not a new name in this codebase — it is already load-bearing in the hook-adapter shim subsystem (`hooks/adapters/*/*.sh`, `scripts/little_loops/hooks/adapters/*/`), which resolves its own interpreter via `PY="${LL_PYTHON:-$(command -v python3 || command -v python || echo python)}"` (`hooks/adapters/claude-code/stop.sh:11`; the exact chain is asserted more loosely — just `"LL_PYTHON" in body` — by `scripts/tests/test_kimi_adapter.py:80-83`). That is a probe-chain-with-fallback contract, not necessarily `sys.executable` specifically — a different producer for the same variable name that this fix should confirm doesn't conflict.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` shell
  branch, `env=project_child_env()` call at line 305 → needs
  `extra={"LL_PYTHON": sys.executable}`
- `scripts/little_loops/runner_spec.py` — `_run_cmd()`'s
  `env=project_child_env()` at lines 242-248 → same `extra=` kwarg (in
  scope per Decision Rules)
- `scripts/little_loops/loops/*.yaml` — only invocations whose payload
  imports `little_loops` (per Scope Boundaries), migrated to the escaped
  `$${LL_PYTHON:-python3}` form. For context, the full surface is 155 bare
  `python3 <<` heredocs across 39 files plus ~100 `-c`/`-m` invocations
  across 16 more — the remainder is a follow-up ENH

### Dependent Files (Callers/Importers)
- `scripts/tests/test_enh3184_spawn_site_guard.py` — AST-based guard that
  statically pins the exact spawn count per task-path module
  (`_TASK_PATH_MODULES["little_loops/fsm/runners.py"] = (1, 0)`) and
  asserts every `subprocess.(run|Popen|check_output|call)` in that module
  resolves to a `project_child_env(...)` call. Adding an `extra=` kwarg to
  an existing call does not change this count, but the guard should be
  re-run after the change.

### Conventions in Force
- The established idiom for injecting a one-off env var into a
  `project_child_env()`-routed spawn is
  `project_child_env(extra={"SOME_VAR": value})` — five existing call sites
  already follow this shape: `cli/loop/_helpers.py:2159` (`LL_HOST_CLI`),
  `worktree_utils.py:571` (`LL_VERIFY_GATE`), `git_operations.py:728`
  (`GIT_INDEX_FILE`), `mcp_call.py:199`, `parallel/worker_pool.py:859`.
- `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` (MR-11) documents a related
  existing idiom for threading an FSM-context value into a heredoc:
  `LL_ARG_<NAME>=${context.x:shell} python3 << 'PYEOF' ...
  os.environ["LL_ARG_<NAME>"]`. This is the shape `$${LL_PYTHON:-python3}`
  would extend, but for selecting the interpreter itself rather than
  passing a value into it.
- **Naming collision risk**: `LL_PYTHON` is not a new name in this
  codebase — it is already load-bearing in the hook-adapter shim subsystem
  (`hooks/adapters/claude-code/*.sh`,
  `scripts/little_loops/hooks/adapters/*/`), which resolves its own
  interpreter via `PY="${LL_PYTHON:-$(command -v python3 || command -v
  python || echo python)}"` (documented in
  `hooks/adapters/opencode/README.md`, `hooks/adapters/omp/README.md`;
  asserted in `scripts/tests/test_kimi_adapter.py:80-83`). That contract is
  a probe-chain-with-fallback, not necessarily `sys.executable`
  specifically — a different producer for the same variable name that this
  fix should confirm doesn't conflict.

### Tests
- `scripts/tests/test_host_runner.py::TestProjectChildEnv` (lines 97-165) —
  existing coverage for `project_child_env()`'s merge/override semantics
- `scripts/tests/test_fsm_runners.py` — covers `DefaultActionRunner`'s
  shell branch (`test_shell_popen_starts_new_session`,
  `test_shell_runs_in_working_dir`) but has no existing test asserting on
  the environment dict passed to the shell subprocess — the natural home
  for a new regression test asserting `LL_PYTHON` is present and equals
  `sys.executable`

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:9946-9962` — the `project_child_env()` reference
  entry explicitly states both task-path `bash -c` spawn sites
  (`fsm/runners.py`'s `DefaultActionRunner` shell branch and
  `runner_spec.py::_run_cmd()`) "never construct a `HostInvocation` at
  all" and call `project_child_env()` "with no arguments" — that claim
  goes stale for whichever site(s) this issue updates to pass
  `extra={"LL_PYTHON": sys.executable}` and needs updating alongside the
  code change [Agent 2 finding, confirmed via `ll-code`/grep]

## Sequencing

Implement **before [[BUG-3364]]** (that issue declares `depends_on` on this
one). BUG-3364's regression test forces a heredoc crash; writing it against
the pre-`LL_PYTHON` heredocs would mean rewriting it when this change lands.

## Impact

- **Priority**: P2 — this is the root cause behind [[BUG-3364]]'s specific
  crash and is not scoped to one state; every `python3`-invoking shell
  action in every loop YAML shares the same hazard.
- **Effort**: Small — one executor-side env var plus a mechanical
  find/replace across loop YAMLs.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-08-31 — based on codebase analysis:_

- The "mechanical follow-up" scope is larger than a single find/replace: 155 bare `python3 <<` heredoc invocations exist across 39 distinct loop YAML files under `scripts/little_loops/loops/` (not limited to `auto-refine-and-implement.yaml`), plus roughly 100 additional non-heredoc bare `python3` invocations (`-c`/`-m` forms) across 16 more files. Resolved during review: this issue migrates only the invocations that import `little_loops`; the full sweep is a follow-up ENH (see Scope Boundaries).

## Resolution

Both task-path `bash -c` spawn sites now pass `extra={"LL_PYTHON": sys.executable}`
through `project_child_env()`:

- `scripts/little_loops/fsm/runners.py:305` (`DefaultActionRunner.run()` shell branch)
- `scripts/little_loops/runner_spec.py:248` (`_run_cmd()`)

All 15 `python3 <<` heredocs that `import little_loops` across the 7 files identified
in scope (`assumption-firewall.yaml`, `auto-refine-and-implement.yaml`,
`lib/policy-router.yaml`, `migrate-sdk-version.yaml`, `oracles/enumerate-and-prove.yaml`,
`sft-corpus.yaml`, `workflow-generator.yaml`) now invoke `$${LL_PYTHON:-python3}`.

Added regression tests asserting `env["LL_PYTHON"] == sys.executable` at both spawn
sites (`test_fsm_runners.py::test_shell_sets_ll_python_env`,
`test_runner_spec.py::test_cmd_dispatch_sets_ll_python_env`). Fixed six existing
`test_builtin_loops.py` test helpers that extract a raw action string and run it via
`bash -c` directly (bypassing the FSM's real `interpolate()` call) — they now undo the
`$${` → `${` escape themselves via a new `_unescape_ll_python()` helper, matching what
`interpolation.py`'s `ESCAPED_PATTERN` does at runtime. Also corrected a stale
quote/file attribution in this issue's own "Codebase Research Findings" (line 148) that
`ll-verify-evidence` flagged. `docs/reference/API.md`'s `project_child_env` entry
updated to document the `LL_PYTHON` convention and narrowed non-FSM override scope.

Full suite: `python -m pytest scripts/tests/` — all green except 3 pre-existing
`test_cli_harness.py::TestReadTargetHistory`/`TestTargetHistoryRegression` failures
confirmed failing on `main` before this change (unrelated `history_judged_runs` KeyError).

**Note:** mid-implementation, a concurrent process operating on this same working
directory committed this exact implementation as `553079f6d` (plus an unrelated
`bed29940a` BUG-3367 docs commit) before this session reached Phase 5. This session's
remaining work — the six test-helper escape fixes, the evidence-gate attribution fix,
and this Resolution — lands as a new commit on top rather than re-doing what's already
on `main`.

## Status

**Open** | Created: 2026-08-30 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-08-31T04:01:27 - `0712b8b1-eba4-4dd0-9d5a-30b279c36d04.jsonl`
- `/ll:ready-issue` - 2026-08-31T03:37:38 - `d3fa0ee5-3d96-476c-a86f-50795f749f97.jsonl`
- `/ll:confidence-check` - 2026-08-31T03:11:18 - `29e8f5ee-bb5d-4aac-ae78-4403d15301ef.jsonl`
- `/ll:wire-issue` - 2026-08-31T02:33:50 - `80c0d0f5-6988-4121-a3c7-d08dabaee7ea.jsonl`
- `/ll:refine-issue` - 2026-08-31T02:30:14 - `80c0d0f5-6988-4121-a3c7-d08dabaee7ea.jsonl`
- `/ll:format-issue` - 2026-08-31T02:10:25 - `816b6544-6e69-4192-a4ac-f797f3d82975.jsonl`
