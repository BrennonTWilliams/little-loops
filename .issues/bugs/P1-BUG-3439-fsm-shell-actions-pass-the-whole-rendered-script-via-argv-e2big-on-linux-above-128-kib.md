---
id: BUG-3439
type: BUG
title: FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above
  128 KiB
priority: P1
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-10'
captured_at: '2026-09-10T21:15:03Z'
parent: EPIC-3436
decision_needed: false
confidence_score: 100
outcome_confidence: 66
score_complexity: 21
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 10
completed_at: '2026-09-11T02:49:07Z'
closed_reason: already_fixed
---

# BUG-3439: FSM shell actions pass the whole rendered script via argv; E2BIG on Linux above 128 KiB

## Summary

DefaultActionRunner spawns every shell action as ["bash", "-c", action] (fsm/runners.py:348), so any :shell-interpolated capture exceeding Linux MAX_ARG_STRLEN (131072 B) raises OSError Errno 7 in every loop, not just loop-router. Reproduced by test_write_sub_loop_output_survives_oversized_stream (rendered 264085 B). Fix at the runner: write the rendered script to a temp file (`NamedTemporaryFile(delete=False, prefix="ll-action-", suffix=".sh")`, unlinked in the existing `finally`) and spawn `["bash", path]`; mirror in `runner_spec._run_cmd`. Add a runner-level regression test (>131072 B script through `DefaultActionRunner.run` and `_run_cmd`) — the existing loop-router test spawns its own `bash -c` and cannot pin this fix; re-point it through the runner (A4 / BUG-3334 AC14).

## Current Behavior

`DefaultActionRunner.run`'s shell branch builds `cmd = ["bash", "-c", action]` (fsm/runners.py:348) and passes the fully-rendered script as a single argv element to `subprocess.Popen`. Linux caps any single argv/env string at `MAX_ARG_STRLEN` (131072 B, `include/uapi/linux/binfmts.h`), so a rendered action above that raises `OSError: [Errno 7] Argument list too long` at spawn — before the process ever runs, and regardless of the state's `on_error` handling since the failure happens inside the runner call.

The same argv pattern exists in `_run_cmd` (runner_spec.py:323, `["bash", "-c", spec.target]`), giving loop-spec `cmd:` runners the identical exposure.

Correction to the Summary's claim about the executor: `_run_subprocess` (fsm/executor.py:2966) has **no shell path** — it is called only for `mcp-call` commands (executor.py:2480). Executor shell states delegate to `DefaultActionRunner`, so fixing the runner fixes the executor path transitively.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Correction — the "regardless of the state's `on_error` handling" claim does not hold. `_run_action_or_route` (executor.py:3773) wraps `_run_action` in `except Exception` (executor.py:3793-3800): with `state.on_error` defined, an E2BIG `OSError` from the runner emits an `action_error` event and routes to on_error (the action's result is lost, not the loop); only when on_error is absent does it re-raise to `FSMExecutor.run()`'s handler (executor.py:1040-1041) and terminate the run with status `"error"`. The regression test's own docstring (test_loop_router.py:244-248) already describes this routing correctly.
- Neither spawn site passes `stdin=` today — the bash child inherits the ll-loop parent's stdin (runners.py:349-357, runner_spec.py:322-329). Any `stdin=subprocess.DEVNULL` addition is a deliberate behavior change to note in the fix, not a preserve.
- Neither Popen is wrapped in `except OSError`; the only spawn-wrapping except in the family is `run_claude_command`'s broad `except Exception` (subprocess_utils.py:544). Both sites drain via a selector loop registering stdout/stderr only — stdin is never registered, and `communicate()` appears nowhere in fsm/runners.py, fsm/executor.py, or runner_spec.py (the only package uses are cli/queue.py:423/:427). No writer thread or stdin-drain mechanism exists at either site.
- `_run_subprocess` claim verified: generic argv-list runner (executor.py:2966, Popen :2982-2989, inherits os.environ, no cwd), with exactly one production caller — the mcp_tool branch at executor.py:2480 (`["mcp-call", action, json.dumps(params)]`). No shell path; shell states reach a process only via `self.action_runner.run` at executor.py:2586.

## Steps to Reproduce

1. Render any shell action whose interpolated body exceeds 131072 B — e.g. loop-router's `write_sub_loop_output` with a `sub_loop_output` capture of ~216000 B raw (shlex.quote expansion renders it to 264085 B, as in `test_write_sub_loop_output_survives_oversized_stream`, scripts/tests/test_loop_router.py:234).
2. Run the loop on Linux (macOS's per-argv limit is far larger, so the same action passes on darwin — the existing test is not platform-honest about this).
3. `subprocess.Popen(["bash", "-c", action])` raises `OSError: [Errno 7] Argument list too long` at exec time.

## Expected Behavior

A shell action of any renderable size spawns successfully: the runner passes the script body out-of-band (stdin or temp file) rather than as an argv element, so the OS per-argument limit never applies to loop scripts. Streamed captures written to `${context.run_dir}/` survive intact (BUG-3334 AC14), and the regression test states its platform boundary honestly instead of relying on darwin's larger argv limit.

## Proposed Solution

Two viable mechanics (Summary offers both):

1. **Temp file (recommended)** — write the rendered action to a `tempfile.mkstemp(suffix=".sh")` file in the existing try/finally scope, spawn `["bash", str(path)]`, unlink in `finally`. Deadlock-free regardless of size; no pipe-buffer interaction with the selector loop.
2. **stdin (`bash -s`)** — spawn `["bash", "-s"]` and feed `action` via `process.stdin` from a writer thread. Avoids temp files, but a naive inline `stdin.write(action)` deadlocks once the script exceeds the 64 KiB pipe buffer (bash must buffer the whole command line before executing), so it requires the thread.

Either way, mirror the substitution in `_run_cmd` (runner_spec.py:323). `test_write_sub_loop_output_survives_oversized_stream` currently executes its own `subprocess.run(["bash", "-c", rendered])` (test_loop_router.py:262), so it does not exercise the runner and would still E2BIG on Linux after the fix. Re-point its execution through `DefaultActionRunner().run(rendered, timeout=30)` so it becomes a true end-to-end pin, and reword its docstring: "sized well under the real OS ARG_MAX" is true for total ARG_MAX but false for Linux's per-argument `MAX_ARG_STRLEN` — the very limit this bug hits (A4 / BUG-3334 AC14).

Implementation details for the temp-file path (both sites):
- Create the file **inside** the existing `try:` (runners.py:347 / runner_spec.py:321) so the unlink shares the `finally` with `gh_tmp.cleanup()` and runs on success, timeout, and spawn-error paths alike. Wrap the unlink in `except OSError: pass` (route_table.py precedent).
- Write with `mode="w", encoding="utf-8"`; flush/close before spawning. Bash reads script files incrementally, so unlinking only after `wait()` is required (already guaranteed by the finally placement).
- Do **not** add `stdin=subprocess.DEVNULL` — the child inherits the parent's stdin today and nothing in this issue asks to change that.
- No shared constant: inline the prefix/suffix at both sites (fsm/runners.py has no module constants; a cross-module constant has no natural home).
- Add the mirror comment at both sites citing BUG-3439, per the runners.py↔runner_spec.py convention (ENH-3234/3235, BUG-3400 precedent).
- Note for the future, not this fix: env strings share the same `MAX_ARG_STRLEN` cap, so any capture-via-env path would hit the identical wall.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Contested convention (decide knowingly): the issue proposes `tempfile.mkstemp(suffix=".sh")`, but both existing "hand a temp file to a child via argv" precedents use `NamedTemporaryFile(delete=False, prefix="ll-<thing>-", suffix=".ext", mode="w")` + unlink-in-finally — `CodexHost.build_blocking_json` (host_runner.py:921-929; path returned via `HostInvocation.cleanup_paths`, unlinked at :2499-2501) and `route_table.open_in_editor` (route_table.py:634-653, `os.unlink` in finally wrapped `except OSError: pass`). `mkstemp` appears only in the atomic-write pattern (mkstemp followed by an atomic
  os-level rename): state.py:150, file_utils.py:22, fsm/persistence.py:516, fsm/batch_tracker.py:90, et al. No production temp file anywhere uses a `.sh` suffix. Both routes are defensible; they are two coexisting conventions, not one.
- Critical test finding: `test_write_sub_loop_output_survives_oversized_stream` does NOT exercise the runner — it renders through the real `interpolate()` then executes its own `subprocess.run(["bash", "-c", rendered])` (test_loop_router.py:262), per the suite's substitute-then-execute idiom. A runner fix changes none of its mechanics, and on Linux the test's OWN argv spawn hits the same MAX_ARG_STRLEN — so even after the fix it cannot pass on Linux as written. "Keep it as the regression pin" therefore requires either re-pointing its execution through `DefaultActionRunner.run` or accepting it as a darwin-passing pin of the interpolate() render path only; the docstring rewrite alone does not make it a regression pin for this fix.
- Option 2 (stdin/`bash -s`) has no confirming precedent in this codebase: repo-wide, the only `stdin=PIPE` spawns are long-lived request/response protocols (mcp_call.py:213 with `_send_jsonrpc` writer + `_drain_stderr` daemon thread :92-95/:232-238; cli/verify_evidence.py:815-828 `git cat-file --batch`, whose docstring :800-809 documents the interleave-or-deadlock pipe-buffer hazard). Zero `bash -s` sites exist. Option 1 (temp file) is the mechanism the two precedents above confirm.
- Platform-honesty constraint: the suite has no linux/darwin skipif idiom — platform variation is handled by patching `sys.platform` (test_host_guard.py:186-208) and the only platform skip is win32 (test_init_audit_fixes.py:27). The docstring fix is wording only; there is no established skipif pattern to adopt.
- No existing test asserts the production bash argv — every `["bash", "-c", ...]` literal in scripts/tests/ is either a test's own spawn or a mocked `CompletedProcess.args` value (test_ll_loop_execution.py:301 et al.). The argv substitution breaks no assertion; the binding test constraint is the ENH-3184 census table, not argv pins.

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

**Option A**: Temp file — write the rendered action to a tempfile in the existing try/finally scope, spawn `["bash", str(path)]`, unlink in `finally`. Deadlock-free regardless of size; no pipe-buffer interaction with the selector loop. (Exact tempfile API is itself a contested convention: mkstemp vs NamedTemporaryFile(delete=False) — see finding above.)

> **Selected:** Option A — the codebase's established mechanism for handing large payloads to a child (two production precedents), deadlock-free, fully covered by existing test templates.

**Option B**: stdin (`bash -s`) — spawn `["bash", "-s"]` and feed `action` via `process.stdin` from a writer thread. Avoids temp files, but a naive inline `stdin.write(action)` deadlocks once the script exceeds the 64 KiB pipe buffer (bash must buffer the whole command line before executing), so it requires the thread — and no stdin-fed one-shot script precedent exists in this codebase.

**Recommended**: Option A — precedent-backed by the two existing temp-file-via-argv sites (host_runner.py:921-929, route_table.py:634-653); Option B's writer-thread mechanism has no confirming usage site here.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-09-10.

**Selected**: Option A: Temp file

**Reasoning**: The exact mechanism — write tempfile, spawn child on its path, unlink in `finally` on every exit path — has two production precedents (`host_runner.py:921-929` + cleanup at `:2499-2501`; `fsm/route_table.py:634-653`, the latter inside `fsm/` itself), and both fix sites already run a temp-resource try/finally (`gh_tmp`) around the exact Popen being changed. Option B introduces a mechanism with zero confirming usage sites repo-wide (no `bash -s` spawn, no stdin writer thread, no one-shot Python stdin feed; the only `stdin=PIPE` production sites are long-lived request/response protocols that deliberately avoid bulk writes per the deadlock hazard documented at `verify_evidence.py:800-809`), plus a new writer-vs-killpg failure mode on the timeout path that the existing selector loops and mock-based tests would neither exercise nor catch. Implementation note: follow the `NamedTemporaryFile(delete=False, prefix="ll-", suffix=...)` + unlink-in-finally precedent rather than the issue Summary's `mkstemp(suffix=".sh")` spelling — `mkstemp` in this codebase is exclusively the atomic-rename pattern (8 sites, never write-then-spawn).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: Temp file | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B: stdin (`bash -s`) | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Temp file (winner): precedents `host_runner.py:921-929`/`:2499-2501` and `route_table.py:634-653`; existing temp-resource finally at both fix sites (`runners.py:334`/`:462-464`, `runner_spec.py:312`/`:383-385`); full test template chain (cleanup pins `test_host_runner.py:2275-2309`, large-payload direct-drive `test_fsm_executor.py:5968-5986`); no test pins the production bash argv, so the substitution breaks nothing.
- stdin feed via `bash -s` (rejected): confirming shapes only (mcp_call.py daemon stderr-drain thread `:232-238`, TS one-shot feeds, `_stdio_call` test harness `test_mcp_server.py:997-1083`) but no confirming usage site; new concurrency hazard (writer thread blocked in `stdin.write` when `_kill_process_group` fires on timeout) with no production handling pattern to copy.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Files to modify: `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run` shell branch, `cmd = ["bash", "-c", action]` at :348 (Popen :349-357); `scripts/little_loops/runner_spec.py` — `_run_cmd` spawn at :321-323. These two sites are deliberate mirrors — each cites the other by name (runners.py:313-316 calls `_run_cmd` "the sibling `bash -c` call site for the same chokepoint"; `_run_cmd`'s docstring at runner_spec.py:270-284 says "mirrors `fsm/runners.py`'s shell-command branch, BUG-2777"). The convention this codebase holds: every behavioral change to one site's spawn mechanics is mirrored in the other with an issue-ID-citing comment (ENH-3234/3235, BUG-3400 preceded this).
- Temp-file lifetime structure at these exact sites: the shell branch's enclosing `try:` (runners.py:347) has finally-only handlers — `gh_tmp.cleanup()` at :462-464, inner try/finally at :382-430 closing the selector; `_run_cmd` mirrors with try :321 / finally :383-385. A script tempfile's unlink must live on every exit path of that structure.
- Dependent instantiations (behavior must hold for both): `FSMExecutor` sole construction at executor.py:300 (`action_runner or DefaultActionRunner()`); second production instantiation at cli/loop/testing.py:85.
- `run_action` → `_run_cmd` production callers whose uncaught-spawn-OSError behavior this fix changes: cli/harness.py:1246, :1306, :1374, :1428 (SKILL/CMD `_invoke` closures, unguarded); cli/action.py:250, :304; cli/queue.py:593 (drain loop, wrapped in `except Exception` at :594 converting to an entry error result).
- Adjacent same-exposure argv sites NOT covered by the two named fixes (in-scope or not is a scope judgment): loops/rn-build.yaml:1067-1068 (inline-Python `["bash", "-c", command]` inside a loop action); loops/mechanize-skills.yaml:534 (`subprocess.run(cmd, shell=True)`); cli/queue.py:405-408 (`ll-loop run` shell-out carries `loop_input` via argv); `run_claude_command` (whole prompt via argv — subprocess_utils.py:516-527 — but fails soft via `except Exception` at :544 into `CompletedProcess(returncode=1, stderr=...)`).
- Tests holding the spawn contract: scripts/tests/test_fsm_runners.py `TestDefaultActionRunnerShellPath` (:227; asserts `start_new_session` kwarg at :375 and `LL_PYTHON` env at :393 — kwargs only, never argv); scripts/tests/test_runner_spec.py:293 (env `ll-gh-` contents), :289/:370 (`assert_not_called` fail-before-spawn); scripts/tests/test_fsm_executor.py `TestDefaultActionRunnerStderrDrain.test_large_stderr_does_not_deadlock` (:5968-5986 — the existing direct-drive large-payload shape: real `runner.run()`, 131072-byte child stderr write, no platform guard).
- Gate constraint: scripts/tests/test_enh3184_spawn_site_guard.py:25-52 pins exact subprocess call counts per module — `fsm/runners.py (1, 0)`, `runner_spec.py (3, 0)`, `subprocess_utils.py (1, 0)`. An in-place argv substitution keeps the census; extracting the spawn into a shared module or adding a site requires updating that table. Every spawn's `env=` must route through `project_child_env()` or carry an inline `# ll-no-project: <reason>` marker.
- Documentation describing the current `bash -c` spawn mechanics: docs/reference/API.md:10293, :10501-:10505 — needs a line updated if spawn mechanics change.

## Program Design

### Types

- No new types or constants. Prefix/suffix (`"ll-action-"`, `".sh"`) inline at both sites.

### Signatures

- `DefaultActionRunner.run(self, action: str, ...) -> ActionResult` — signature unchanged. Shell branch: `tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False, prefix="ll-action-", suffix=".sh")` written with `action`, closed, then `cmd = ["bash", script_path]`; `os.unlink(script_path)` in the existing `finally` (wrapped `except OSError: pass`). stdin handling unchanged (inherited).
- `_run_cmd(spec: ActionSpec, *, run_id: str | None = None) -> RunnerResult` (runner_spec.py) — signature unchanged; same temp-file substitution for `spec.target`.
- **Required** runner pins (the loop-router test is not a runner pin as written): `TestDefaultActionRunnerShellPath.test_oversized_script_spawns` in `scripts/tests/test_fsm_runners.py` and a sibling in `scripts/tests/test_runner_spec.py` — drive the real spawn with a script whose rendered length is > 131072 B (e.g. a `printf`/heredoc carrying a 140 KiB literal written to a tmp file), assert `exit_code == 0` and written-output equality. Follow the direct-drive shape of `TestDefaultActionRunnerStderrDrain.test_large_stderr_does_not_deadlock` (test_fsm_executor.py:5968-5986). No platform skip: the test passes on darwin before and after the fix and fails on Linux only before it, which is the honest pin.
- Cleanup pin: after `run()` returns (success and timeout paths), no `ll-action-*.sh` remains in `tempfile.gettempdir()` (shape: `test_host_runner.py:2275-2309`).

### Call Path

`FSMExecutor._run_action_or_route` → `DefaultActionRunner.run` (shell branch, fsm/runners.py:348) → `subprocess.Popen(["bash", script_path], ...)`; sibling: `runner_spec._run_cmd` → `subprocess.Popen(["bash", script_path], ...)`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-10 — based on codebase analysis:_

- Dispatch chain confirmed: `FSMExecutor._run_action` (executor.py:2382; interpolate at :2400) → `self.action_runner.run(action, timeout=state.timeout or self.fsm.default_timeout or _wall_fallback, is_slash_command=action_mode == "prompt", scopes=state.scopes, ...)` at executor.py:2586-2601 — shell states arrive with `is_slash_command=False` and `_wall_fallback=3600`. Second production instantiation: cli/loop/testing.py:85.
- `_run_cmd` confirmed: `_run_cmd(spec, *, run_id=None) -> RunnerResult` (runner_spec.py:269-385); its Popen (:321-329) passes NO `cwd=` unlike the FSM site — that asymmetry predates this issue; preserve it unless deliberately changing it.
- Constant-placement constraint: fsm/runners.py has NO module-level constants today (only `_now_ms()` at :39); runner_spec.py holds both private (`_STOCHASTIC_RUNNERS` :79, `_DISPATCH` :424) and public (`DEFAULT_STOCHASTIC_RUNNERS` :87, exported via `__all__`) constants. A shared `_SHELL_SCRIPT_SUFFIX` spanning both modules has no natural home — it would be runners.py's first module constant, live in runner_spec.py, or stay inline at both sites. Module-private constants use leading-underscore UPPER_SNAKE (`_GUILLOTINE_TAIL_CHARS`, subprocess_utils.py:110-116).
- Existing runner tests mock Popen+selector via the `_make_selector_mock_process` / `_make_ready_selector` helpers (test_fsm_runners.py:25-104) and assert kwargs only — a spawn-mechanics change keeps those helpers valid; the optional direct pin already has a shape to follow in `TestDefaultActionRunnerStderrDrain.test_large_stderr_does_not_deadlock` (test_fsm_executor.py:5968-5986).

## Implementation Steps

1. `scripts/little_loops/fsm/runners.py` shell branch (:347-357): inside the existing `try:`, write `action` to a `NamedTemporaryFile(delete=False, prefix="ll-action-", suffix=".sh", mode="w", encoding="utf-8")`, close it, spawn `["bash", path]` with all other Popen kwargs unchanged; unlink in the existing `finally` next to `gh_tmp.cleanup()`. Add a BUG-3439 comment naming `_run_cmd` as the mirror.
2. `scripts/little_loops/runner_spec.py::_run_cmd` (:321-329): identical substitution for `spec.target`; preserve the no-`cwd=` asymmetry. Mirror comment naming `fsm/runners.py`.
3. Confirm `scripts/tests/test_enh3184_spawn_site_guard.py` census is unchanged (`fsm/runners.py (1, 0)`, `runner_spec.py (3, 0)`) — in-place substitution adds no spawn site.
4. Tests: add the two required oversized-script runner pins and the temp-file cleanup pin (Program Design § Signatures). Re-point `test_write_sub_loop_output_survives_oversized_stream` (test_loop_router.py:234-266) to execute via `DefaultActionRunner().run(...)` and reword its docstring to name `MAX_ARG_STRLEN` (131072 B per argv string on Linux) as the limit.
5. Docs: update the three `bash -c` descriptions in `docs/reference/API.md` (:10293, :10501, :10505) to "temp-file script spawn (`bash <path>`)".
6. Verify: `python -m pytest scripts/tests/test_fsm_runners.py scripts/tests/test_runner_spec.py scripts/tests/test_loop_router.py scripts/tests/test_fsm_executor.py scripts/tests/test_enh3184_spawn_site_guard.py scripts/tests/test_host_runner.py`, then the full suite.

### Tests

- `scripts/tests/test_fsm_runners.py` — `TestDefaultActionRunnerShellPath` (:227) currently asserts Popen kwargs only via `_make_selector_mock_process`; those mocks stay valid. New oversized-script + cleanup pins use a real spawn.
- `scripts/tests/test_runner_spec.py` — sibling oversized-script pin for `_run_cmd`; existing `assert_not_called` fail-before-spawn tests (:289, :370) are unaffected because the temp file is created after the scope/gh checks.
- `scripts/tests/test_loop_router.py:234` — re-pointed as above.
- `scripts/tests/test_enh3184_spawn_site_guard.py` — census must stay green without edits.

## Verification Notes

**Verdict: EVIDENCE_UNVERIFIED** (advisory, per BUG-3282 fallback F3 — does not route to `reconcile_issue`)

`ll-verify-evidence` flagged two spans in Steps to Reproduce (line 42) —
`` subprocess.Popen(["bash", "-c", action]) `` and `` OSError: [Errno 7]
Argument list too long `` — as unverifiable against the artifact it
associated them with, `scripts/tests/test_loop_router.py`. On inspection
this reads as a checker-attribution artifact rather than fabricated
evidence: line 42 is an illustrative description of the confirmed production
spawn (`fsm/runners.py:348`) and the literal Linux errno text, not a
verbatim quote the issue attributes to `test_loop_router.py` — the actual
citation of that file (`test_loop_router.py:234`, step 1) is one line
earlier and independently confirmed accurate.

All other checks passed: `fsm/runners.py:348` (`cmd = ["bash", "-c",
action]`) and `runner_spec.py::_run_cmd`'s mirrored shell spawn match the
issue's claims exactly at the cited lines; `test_write_sub_loop_output_survives_oversized_stream`
is confirmed at `test_loop_router.py:234`; parent `EPIC-3436` exists; no
active required decision rules (`ll-issues decisions list` returned no
entries); the Proposed Solution (temp-file spawn, Option A) traced against
the code it touches shows no exception-handler incompatibility, the
affected test is explicitly re-pointed rather than left stale, and the
Integration Map's points are covered by the Implementation Steps/Tests —
no `PROPOSAL_UNSOUND` finding.

## Impact

- **Priority**: P1 - Every FSM loop's shell states fail unconditionally on Linux once any interpolated capture exceeds 128 KiB; Linux is a primary deployment target for automation hosts.
- **Effort**: Small - Two spawn-site substitutions, three runner-level tests, one test re-point, three doc lines; no interpolation, routing, or selector-loop changes.
- **Risk**: Low - Spawn mechanics only; script text, env_allow, cwd, stdin, and process-group semantics are unchanged. `$0`/`BASH_SOURCE` inside the script change from `bash` to the temp path — acceptable for loop scripts, which don't reference them. One temp file per shell action is negligible overhead.
- **Breaking Change**: No

## Status

**Closed - Already Fixed** | Created: 2026-09-10 | Priority: P1

## Resolution

- **Reason**: already_fixed
- **Evidence**: Commit `e4ea5d401` ("fix(fsm): handle oversized shell actions via temp file instead of -c argument", 2026-09-10 21:45:29) already implements this issue's Option A exactly: `DefaultActionRunner.run`'s shell branch (`fsm/runners.py:344-360`) and `runner_spec._run_cmd` (`runner_spec.py:321-329`) both write the rendered script to a `NamedTemporaryFile(prefix="ll-action-", suffix=".sh")` and spawn `["bash", script_path]`, with `os.unlink` in the existing `finally`. No `["bash", "-c", ...]` argv spawn remains at either site. The issue's own required regression tests are present and pass: `TestDefaultActionRunnerShellPath::test_oversized_script_spawns` (test_fsm_runners.py:588), `TestRunActionDispatch::test_cmd_oversized_target_spawns` (test_runner_spec.py:448), and the re-pointed `test_write_sub_loop_output_survives_oversized_stream` (test_loop_router.py) — all 39 tests across `test_fsm_runners.py`, `test_runner_spec.py`, and `test_loop_router.py` pass.

## Session Log
- `/ll:ready-issue` - 2026-09-11T02:48:38 - `1bc329f7-d78a-4be3-a47a-8b7a470fa715.jsonl`
- `/ll:confidence-check` - 2026-09-11T01:54:04 - `a2c01544-4d8b-495a-8672-7b8c21ecfdda.jsonl`
- `/ll:verify-issues` - 2026-09-11T01:50:21 - `f77f88c9-58d9-4ee9-80f3-b9585d4c8714.jsonl`
- `/ll:decide-issue` - 2026-09-10T23:50:48 - `2f1f154f-c743-4a68-8aab-afcd2a716a72.jsonl`
- `/ll:refine-issue` - 2026-09-10T23:16:55 - `4d4128b6-b8af-45c0-91e2-96dbe681ff8a.jsonl`
- `/ll:format-issue` - 2026-09-10T22:00:28 - `bfcda7a0-6b47-49e9-8ffb-70e8847bdc09.jsonl`
- `/ll:scope-epic` - 2026-09-10T21:15:17 - `682b3e5f-a0d1-46f6-bdbe-cb9b462b89a8.jsonl`
