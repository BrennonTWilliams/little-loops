---
id: BUG-3401
type: BUG
title: Unmocked cmd_resume tests bind live sockets in the real .ll/ and fail after the third bind per process
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-07'
captured_at: '2026-09-07T23:44:14Z'
confidence_score: 90
outcome_confidence: 49
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 10
score_change_surface: 0
learning_tests_required:
- pytest
reconcile_attempted: true
---

# BUG-3401: Unmocked cmd_resume tests bind live sockets in the real .ll/ and fail after the third bind per process

## Summary

> **Premise corrected 2026-09-08 (manual review, reproduced on `main`):** stale `.ll/events-*.sock` files are a *symptom*, not the trigger. `scripts/tests/test_cli_loop_lifecycle.py` fails identically (34 failures, `-n 0` and default xdist addopts alike) on a completely clean `.ll/`. The real cause is that every unmocked `cmd_resume(...)` call binds a real `UnixSocketTransport` in the repo's `.ll/` and never closes it, so live listeners accumulate *inside the test process* and the third bind per worker raises. The original stale-file narrative below is kept for history but is superseded by this section and the corrected Current Behavior / Steps to Reproduce.

Since commit `90c1e137` (2026-09-07 17:30, "feat(events): enable socket events transport") this repo's own `.ll/ll-config.json` sets `events.transports: ["socket"]`. `cmd_resume` (`cli/loop/lifecycle.py:713`) does `config = BRConfig(Path.cwd())`, so every test that calls it for real without mocking `little_loops.config.BRConfig` loads that config and `wire_transports()` binds a real socket at cwd-relative `.ll/events.sock`. Because those tests mock `PersistentExecutor`, the `executor.close_transports()` in the `finally` (`lifecycle.py:765`) is a MagicMock no-op and the listener stays live for the rest of the process. `test_cli_loop_lifecycle.py` has been deterministically red on `main` since that commit, independent of stale files.

Originally observed 2026-09-07 while verifying the EPIC-3212 merge, where it was misattributed to leftover socket files (`lsof -U` was empty only because the listeners die with the pytest process, leaving orphan files behind).

## Current Behavior

Within one pytest worker process, each real (unmocked-`BRConfig`) `cmd_resume` call reaches `wire_transports()` → `UnixSocketTransport.__init__` → `_claim_socket_path(Path(".ll/events.sock"))`:

1. **First call** probes `.ll/events.sock` → ABSENT (or RECLAIMABLE if a stale file is present; it is unlinked) → binds it. The listener is never closed.
2. **Second call** probes `.ll/events.sock` → LIVE (our own process is listening) → falls back to `.ll/events-<pid>.sock` → binds it. Never closed.
3. **Third and every later call** finds both paths LIVE and `_claim_socket_path` raises:
   ```
   RuntimeError: UnixSocketTransport: pid-suffixed path .ll/events-<pid>.sock is claimed by a live listener, which cannot happen for a distinct live process
   ```

Every subsequent unmocked `cmd_resume` test in that worker fails. Under `--dist loadfile` the whole file lands on one worker, so the count is stable at 34. The orphaned `.ll/events.sock` / `.ll/events-<pid>.sock` files left after the run are the artifact that prompted the original (incorrect) stale-file hypothesis; `_claim_socket_path` reclaims them correctly on the next run, so they do not themselves cause failures.

Side effect worth noting: `TestCmdResumeBackground::test_foreground_internal_*` patches `little_loops.cli.loop.lifecycle.os.getpid` to `99999`. That is the global `os` module, so `_claim_socket_path`'s suffixed bind produces `.ll/events-99999.sock`. Harmless once the transport is mocked, but it explains that oddly-named orphan.

- ~~Some socket-transport test (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) binds `UnixSocketTransport` against the real project `.ll/` directory~~ — disproven by refine pass (both files bind under `short_tmp_path` and close).
- ~~The failure is order- and state-dependent~~ — it is deterministic on a clean tree.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator and codebase-analyzer agents traced the two named candidate files and the `wire_transports()` call path itself, refining the leak hypothesis:

Every direct `UnixSocketTransport(...)` construction in `test_transport.py` and `test_feat3323_sse_bridge.py` (the two files this issue names as candidates) already binds under a `short_tmp_path` fixture (`tempfile.mkdtemp(prefix="ll-")`, not the real project `.ll/`) with a matching `.close()` in every case — confirmed by exhaustive grep across both files. Neither named candidate file's own transport tests appear to be the leak source as originally hypothesized.

The more likely mechanism, found by tracing `wire_transports()` itself (`scripts/little_loops/transport.py:1876-1917`): its `log_dir` parameter defaults to `Path(".ll")` **relative to the process's current working directory** when not explicitly passed (`base = log_dir if log_dir is not None else Path(".ll")`, line 1896) — this is a documented, intentional default for production use (real `ll-loop`/`ll-parallel` invocations run from a project root and are meant to write into that project's real `.ll/`). The three production call sites — `cmd_resume` (`cli/loop/lifecycle.py:737`), `cmd_run` (`cli/loop/run.py:623`), `main_parallel` (`cli/parallel.py:322`) — all call `wire_transports(bus, config.events)` with **no `log_dir` argument**. `EventsConfig.transports` defaults to an empty list (`config/features.py:1342`), so this only matters when something enables the `"socket"` transport. This repo's own `.ll/ll-config.json` does exactly that (`"events": {"transports": ["socket"]}`) — a test path that ends up consulting the real project's own config (rather than a fully isolated tmp-path config) while calling `cmd_resume`/`cmd_run`/`main_parallel` for real, without also passing an isolated `log_dir`, would write `.ll/events.sock` at the real repo root exactly as observed. This is a plausible, code-verified mechanism, not a confirmed root cause — the specific test/fixture combination that omits the `log_dir` override was not identified by this pass and needs runtime confirmation (e.g. bisecting with `-p no:randomly` or instrumenting `wire_transports` during a full-suite run).

## Steps to Reproduce

1. On `main` at or after `90c1e137`, ensure `.ll/` has no `events*.sock` files (`rm -f .ll/events*.sock`) to rule out the stale-file hypothesis.
2. Run `python -m pytest scripts/tests/test_cli_loop_lifecycle.py -n 0 -p no:randomly`.
3. Observe (verified 2026-09-08): `34 failed, 104 passed`. The first failure is the **third** unmocked `cmd_resume` test in collection order (`TestCmdResume::test_resume_with_minutes_duration`), raising `RuntimeError: ... pid-suffixed path .ll/events-<pid>.sock is claimed by a live listener`. The same 34 fail under the default `-n logical --dist loadfile` addopts.
4. After the run, `.ll/events.sock` and `.ll/events-<pid>.sock` (plus `events-99999.sock`) exist as orphans — the artifact previously mistaken for the cause.

## Expected Behavior

- No test loads this repo's real `.ll/ll-config.json` or binds a socket in the checkout's real `.ll/`; every `cmd_resume`/`cmd_run`/`main_parallel`/`_cmd_sprint_run` test either mocks `BRConfig` + `wire_transports` or runs under an isolated cwd/config.
- `scripts/tests/test_cli_loop_lifecycle.py` is green on a clean tree, and two consecutive full-suite runs in the same checkout are both green with no manual cleanup.
- ~~Ideally `_claim_socket_path()` treats a listener-less socket as stale~~ — already implemented and pinned by tests (see wiring pass); no change needed.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator confirmed no `.ll/` cleanliness fixture exists today and identified the nearest sibling fixture to model one after:

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Contested fixture-shape precedent, not resolved by codebase convention alone**: the dominant existing pattern for isolating `BRConfig`/`wire_transports()` specifically in CLI-entrypoint tests is per-test `patch("little_loops.config.BRConfig", ...)` inside each test's own `with (...)` block, not a shared fixture — confirmed at 13+ call sites: `TestCmdResumeCircuitWiring`/`TestCmdResumeTransportWiring` (`test_cli_loop_lifecycle.py:2196-2376`, 5 occurrences) and `test_cli_loop_worktree.py` (8 occurrences: lines 830, 866, 901, 962, 992, 1104, 1193, 1303). This is distinct from the `_guard_real_history_db`/`_isolate_session_log_dir` choke-point-fixture precedent already cited above, which addresses a different call path (DB/home resolution, not `BRConfig` config loading).
- **Counter-precedent for consolidation**: this codebase has replaced N per-test patches with one new suite-wide autouse fixture before, when the same leak affected many call sites of the same kind — `_restore_cmd_run_env_vars` + `_CMD_RUN_ENV_VARS` (`conftest.py:1060-1078`) scrubs 8 env vars across the whole suite in one autouse fixture rather than patching each `cmd_run()`-adjacent test individually (BUG-2011 follow-up). This is a real precedent for the "one new fixture" branch the wiring pass left open, standing alongside the per-test-patch precedent above — the two disagree and neither is dispositive.
- **Autouse is deliberately rejected here when some tests need the un-patched default**: `docs/development/TESTING.md:523` states this explicitly for `stable_snapshot_env` (applied via `@pytest.mark.usefixtures(...)`, never autouse, "to avoid interfering with tests that assert both color-on and color-off behaviour"). Relevant if any test in this suite intentionally exercises the real `BRConfig`/socket-transport wiring path — none currently identified, but worth checking before making a new fixture autouse.
- **Blanket cwd-isolation was already tried and rejected for a sibling leak**: per-test `monkeypatch.chdir(tmp_path)` is the dominant, near-universal convention for isolating `Path.cwd()`-relative resolution elsewhere in this suite (20+ call sites each in `test_pre_compact.py`, `test_cli_ctx_stats.py`, `test_hooks_integration.py`, plus `test_cli_e2e.py`'s `e2e_project_dir` fixture) — but a blanket autouse `chdir(tmp_path)` fixture was explicitly considered and scored 3/12 (rejected) in the sibling BUG-1995's own Decision Rationale, because some test files are deliberately CWD-dependent (`test_adapt_agents_for_codex.py`, `test_cli_docs.py`) and `hooks/user_prompt_submit.py:67` resolves its own config via a bare `Path.cwd()` that a blanket chdir would silently redirect mid-suite. This forecloses "autouse-chdir every test" as a codebase-consistent fix here.
- No prior fix exists in this codebase for `.ll/` socket-file pollution specifically — searched repo-wide for prior resolved issues/fixtures addressing `.sock` leaks; none found (consistent with `docs/reference/CONFIGURATION.md:1622-1656` already documenting this as a known, currently unaddressed gap).

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- **Guard-only precedent is incomplete as a template**: `_guard_real_history_db` (`conftest.py:952-993`) is never used alone for its own resource — its actual sibling is `_isolate_history_db_session` (`conftest.py:888-899`, session-scoped, sets `LL_HISTORY_DB` to a `tmp_path_factory`-backed dir) plus a function-scoped `_isolate_history_db` (915-949). The established shape for isolating a real resource in this codebase composes a **redirect** (env-var override so legitimate opens land in an isolated tmp path) with a **guard** (choke-point patch + assert that fails any open that still reaches the real path) — not a guard by itself. `_guard_real_socket_transport` (Program Design) matches only the guard half of this pair; there is no proposed redirect half for `BRConfig`/`Path.cwd()` in the 9 vulnerable `cmd_resume` tests, which is exactly the AC-bullet-1 fix Implementation Steps #2 leaves open.
- **No shared config-mock builder exists**: every `patch("little_loops.config.BRConfig", ...)` call site (`TestCmdResumeCircuitWiring`/`TestCmdResumeTransportWiring`, `test_cli_loop_worktree.py`) constructs its own `MagicMock()`/`mock_config` inline — confirmed by exhaustive search of both files. A per-test-patch fix for the 9 vulnerable tests would mean 9 more hand-built mocks with no factory to reuse, not a one-line change per site.
- **Autouse-fixture precedent (`_isolate_history_db_session`) sets env for the *entire session*, not per-test** — if the AC-bullet-1 fix follows this redirect shape (e.g. an autouse fixture setting `LL_HISTORY_DB`-style env var or monkeypatching `BRConfig`'s resolved project root), it would need its own resource-specific variable/patch target, since no `BRConfig`- or `cwd`-specific env var or fixture exists today (confirmed: zero `BRConfig` references and no `monkeypatch.chdir` fixture in `conftest.py`).
- No existing "run pytest twice back-to-back" test or CI gate exists anywhere in this codebase (repo-wide search, unfiltered) — Acceptance Criteria bullet 3 (`python -m pytest scripts/tests/` run twice back-to-back is green both times) would be validated manually, not by an existing automated double-invocation harness.

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

- Session-scoped choke-point guards in this codebase share one construction: a raw `pytest.MonkeyPatch()` instance is created directly (never the function-scoped `monkeypatch` fixture, which is unavailable at session scope) and undone via `mp.undo()` in a `finally` block after `yield` — confirmed in all three existing session-scoped guards: `_guard_real_history_db` (`conftest.py:952-993`), `_install_no_live_host_cli` (`conftest.py:353-397`), `_collapse_rate_limit_ladder` (`conftest.py:451`).
- This codebase has two disagreeing shapes for wrapping a constructor as a choke point, and neither has been applied to a class other than its own original target: `_GuardedPopen` (`conftest.py:303-322`) subclasses `subprocess.Popen` and calls `super().__init__(*args, **kwargs)` to continue after its check; separately, three test-body-local wrappers (`test_ll_loop_execution.py:715-744`, `test_fsm_executor.py:12256-12285`, `test_ll_loop_commands.py:6465-6476`) save the original unbound method as a closure variable (`original_init = Cls.__init__`) and call it directly via `unittest.mock.patch.object(Cls, "__init__", replacement_fn)` rather than subclassing. No `conftest.py` fixture currently patches an `__init__` method directly (only a free function `sqlite3.connect`, or the `_GuardedPopen` class-swap) — a guard on `UnixSocketTransport.__init__` has no exact precedent for which of these two mechanics to follow.
- No `functools.wraps` is used with any `__init__` wrapper anywhere in this codebase (repo-wide search, no hits) — all three test-body-local wrappers above call the saved original directly with no wrapping decoration.
- `TestCmdResumeCircuitWiring`/`TestCmdResumeTransportWiring`'s `mock_config` field-assignment block (`commands.rate_limits.circuit_breaker_enabled`, `circuit_breaker_path`, `extensions = {}`, `events = MagicMock(transports=[])`, `design_tokens.enabled = False`) is byte-for-byte repeated across all 5 of its `BRConfig`-patching call sites (`test_cli_loop_lifecycle.py:2213-2229, 2251-2267, 2291-2307, 2329-2345, 2358-2374`) with no shared fixture or factory extracting it. Of the file's 38 `cmd_resume(...)` call sites, only these 5 patch `little_loops.config.BRConfig`; the other 33 — including the 9 confirmed-vulnerable tests — mock only `load_loop`/`StatePersistence`/`PersistentExecutor`.

### Files to Modify
- `scripts/tests/conftest.py` — no existing fixture guards `.ll/` socket-file cleanliness (confirmed absent). Existing session-scoped isolation fixtures to model after: `_isolate_history_db_session` (~888) and `_guard_real_history_db` (~952-993), which patches `little_loops.session_store.sqlite3.connect` as a choke point and asserts the resolved path is never the real DB — its docstring explicitly notes this **replaced** an earlier before/after directory-snapshot approach because a snapshot can't attribute a leak to the offending test and isn't immune to concurrent external writers. Program Design's `_guard_real_socket_transport` is shaped directly after this fixture (choke-point patch on `UnixSocketTransport.__init__`, not a snapshot-diff) — an earlier draft of this issue proposed a snapshot-diff shape here; that has been corrected to match this precedent.
- `scripts/tests/test_cli_loop_lifecycle.py` — the 9 confirmed-vulnerable tests (named in Implementation Steps / Wiring Phase) need `little_loops.config.BRConfig`/`wire_transports` mocked (mirroring `TestCmdResumeCircuitWiring`, 2196-2274) unless covered instead by a new `conftest.py` isolation fixture.
- `scripts/little_loops/transport.py` — **no change needed** (wiring pass confirmation): `_claim_socket_path()` (line 1559) / `_probe_socket_path()` (line 1529) already reclaim a listener-less stale socket correctly, pinned by `test_init_unlinks_stale_socket_file`/`test_bound_but_dead_socket_file_is_reclaimed`/`test_stale_pid_suffixed_path_is_reclaimed`. Cited here only as the reference for how `wire_transports()`'s `log_dir` default (line 1896) participates in the leak (see Current Behavior).

### Dependent Files (Callers/Importers)
- Every direct `UnixSocketTransport(...)` construction in `scripts/tests/test_transport.py` and `scripts/tests/test_feat3323_sse_bridge.py` already binds under each file's own `short_tmp_path` fixture (`tempfile.mkdtemp(prefix="ll-")`) with a matching `.close()` — confirmed by exhaustive grep, not a leak source as originally hypothesized.
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeTransportWiring`-style tests (~2277-2376) patch `little_loops.transport.wire_transports` entirely (`MagicMock(transports=[])`), never constructing a real socket. Hundreds of other real (non-mocked) `cmd_resume(...)`/`cmd_run(...)` calls exist in this file (lines 621-1524+) with `tmp_path` as the project-root argument — these are real invocations whose internal `wire_transports()` call still defaults `log_dir` to cwd-relative `.ll` regardless of the `tmp_path` project root passed to `cmd_resume` itself, if `config.events.transports` ends up containing `"socket"`.
- `scripts/tests/test_cli_e2e.py` — `e2e_project_dir` fixture (line 28) uses `tempfile.TemporaryDirectory()`, not the real repo `.ll/`; `test_ll_parallel_wires_transports` patches `wire_transports` entirely.

_Wiring pass added by `/ll:wire-issue`:_
- **Root cause confirmed and localized.** The full chain: `cmd_resume` (`cli/loop/lifecycle.py:713`) does `config = BRConfig(Path.cwd())` — loading the **entire config object**, not just `log_dir`, from process cwd, independent of the `tmp_path`/`project_root` argument passed to `cmd_resume` for everything else. `cmd_run` (`cli/loop/run.py:230`) and `main_parallel` (`cli/parallel.py:195-196`, `project_root = args.config or Path.cwd()`) do the same. During `python -m pytest scripts/tests/`, cwd is the repo root, so any test that doesn't mock `little_loops.config.BRConfig` loads this repo's real `.ll/ll-config.json` (`events.transports: ["socket"]`), and `wire_transports()`'s `log_dir` default (`transport.py:1896`) then binds a real socket at the real repo `.ll/`.
- **Vulnerable test list — CORRECTED 2026-09-08.** The wiring pass's list of 9 was wrong by ~4x. Empirically (clean `.ll/`, `-n 0 -p no:randomly`), **34 tests fail**, and since the first two binds per process succeed silently, the true exposure is every real `cmd_resume` call that reaches `wire_transports()` — roughly 36 tests spanning `TestCmdResume`, `TestCmdResumeBackground` (its foreground-path tests: `test_no_background_flag_runs_foreground`, `test_foreground_internal_registers_pid_cleanup`, `test_foreground_internal_does_not_overwrite_parent_pid`, `test_plain_foreground_resume_pid_passed_to_signal_handler`, `test_resume_registers_signal_handlers`), `TestDesignTokensOptOut` (all `test_resume_*design_tokens*` cases incl. 6 parametrized), `TestCmdResumeMultiInstance`, `TestCmdResumeInterrupted`, the exit-code tests (`test_nonzero_exit_for_limit_termination[*]`, `test_zero_exit_for_graceful_termination[*]`, `test_failure_terminal_returns_distinct_exit_code`, `test_unknown_terminated_by_returns_1`), `test_resume_wires_display_callback_to_event_bus`, and `test_workdir_vanished_returns_exit_code_1`. Full failing list from the reproduction:
  `test_context_overrides_applied_to_fsm test_design_guidance_context_injected_via_cmd_resume test_design_tokens_context_injected_via_cmd_resume test_failure_terminal_returns_distinct_exit_code test_foreground_internal_does_not_overwrite_parent_pid test_foreground_internal_registers_pid_cleanup test_input_hash_injected_via_cmd_resume test_interrupted_instance_is_resumable test_no_background_flag_runs_foreground test_nonzero_exit_for_limit_termination[max_steps|system_signal|timeout|user_stopped] test_plain_foreground_resume_pid_passed_to_signal_handler test_resume_auto_selects_latest_when_multiple_resumable test_resume_awaiting_continuation test_resume_default_loads_design_tokens test_resume_non_terminal_returns_1 test_resume_registers_signal_handlers test_resume_succeeds_with_single_resumable test_resume_use_design_tokens_false_skips_loading test_resume_use_design_tokens_string_falsy_values_skip_loading[|0|false|False|no|off] test_resume_wires_display_callback_to_event_bus test_resume_with_minutes_duration test_unknown_terminated_by_returns_1 test_workdir_vanished_returns_exit_code_1 test_zero_exit_for_graceful_termination[handoff|interrupted|terminal]`
  plus the two that "pass" only because they are the first two binds (`test_nothing_to_resume_returns_1`, `test_resume_success`). The exact set of passers shifts with `pytest-randomly` ordering.
- **Confirmed safe** (return before the `wire_transports()` call is reached): `test_file_not_found_returns_1`, `test_validation_error_returns_1`, `test_context_invalid_format_raises_system_exit`, the `background=True` tests in `TestCmdResumeBackground` (return via `run_background`; **not** the whole class, as an earlier pass claimed), and all `cmd_run` tests in this file (`TestCmdRunHandoffThreshold`, `TestCmdRunYAMLConfigOverrides` — `_make_args()` defaults `dry_run=True`).
- **Existing safe precedent already in the same file**: `TestCmdResumeCircuitWiring` (2196-2274) does `patch("little_loops.config.BRConfig", return_value=mock_config)` with `mock_config.events = MagicMock(transports=[])`, in addition to patching `wire_transports` — the belt-and-suspenders shape the fix should apply to the vulnerable tests above.
- A **4th production `wire_transports()` call site**, not in the issue's original 3: `scripts/little_loops/cli/sprint/run.py:797,801` (`_cmd_sprint_run`'s per-wave wiring) — also calls with no `log_dir` argument and is exposed to the same mechanism if a sprint-run test doesn't mock `BRConfig`.
- `scripts/little_loops/__init__.py:75,142` — re-exports `wire_transports` (not a call site, but part of its public-import surface).
- **One other real (non-mocked) `wire_transports` exposure, confirmed safe**: `test_cli_e2e.py:306-345` `test_ll_parallel_dry_run` calls `main_parallel()` for real, but `monkeypatch.chdir(e2e_project_dir)` (line 317) redirects cwd to an isolated tempdir first — not a leak source.
- **No test-isolation convention exists for `BRConfig`/cwd today**: `scripts/tests/conftest.py` has zero references to `BRConfig` and no `chdir`/`monkeypatch.chdir` fixture — unlike the existing choke-point isolations for `LL_HISTORY_DB` (`_isolate_history_db_session`, conftest.py:888) and `Path.home` (`_isolate_session_log_dir`, conftest.py:1013). This is the structural gap the fix needs to close, either via a `conftest.py` guard/isolation fixture or by threading an isolated config/log_dir through the three (now four) production call sites.
- No gitignore entry or cleanup mechanism exists anywhere for `.sock` files (confirmed by repo-wide search) — `docs/reference/CONFIGURATION.md:1622-1656` already documents this as a known, accepted gap.

### Conventions in Force
- **Choke-point interception beats snapshot-diff** for this codebase's own established preference: `_guard_real_history_db` (`conftest.py:952-993`) patches the single function every real DB-open routes through and asserts at the moment of the violation; its docstring states this replaced "the previous mtime/size snapshot" approach specifically because a snapshot can't attribute a leak to the offending test and isn't safe against concurrent external writers (live `ll-auto`/`ll-loop` runs touching the same file). This is a documented precedent against the issue's own proposed `assert_ll_clean_after_session` snapshot shape — an implementer should read this docstring before choosing a mechanism.
- **Real-Transport-lifecycle convention**: every real `UnixSocketTransport`/`LocalBridgeTransport`/`SseBridge` construction anywhere in the test suite uses inline `try/finally: t.close()`, never a `yield`-based pytest fixture — there is no existing Transport-lifecycle fixture to reuse; a new one would be the first of its kind.
- **Stale-resource reclaim strategies disagree by resource type**: `_claim_socket_path`/`_probe_socket_path` (`transport.py`) reclaims by *connecting* to classify a socket as listener-less (no pid metadata exists on a socket file), whereas every other stale-reclaim path in the codebase (`fsm/concurrency.py::_process_alive`, `worktree_utils.py::_pid_is_live`, `cli/queue.py::_verify_owner_alive`) trusts a **recorded pid field** in the artifact and asks the OS via `os.kill(pid, 0)`. These are not interchangeable without adding a pid field to the socket-adjacent metadata — relevant if the "ideally `_claim_socket_path()` treats a listener-less socket as stale" hardening in Expected Behavior is pursued.
- `short_tmp_path` is duplicated (not imported) between `test_transport.py` and `test_feat3323_sse_bridge.py` deliberately, per an inline comment citing ruff F811 and "no existing precedent for cross-module fixture re-export" — a third consumer of this fixture should follow the same duplicate-don't-import convention unless that precedent changes.

### Tests
- `scripts/tests/test_transport.py:57-69` / `scripts/tests/test_feat3323_sse_bridge.py:56-70` — `short_tmp_path` fixture, the template for any new test needing an isolated AF_UNIX-safe socket directory (macOS `sun_path` 104-char limit is why `tmp_path` itself isn't used directly — see `docs/reference/API.md:10924,10929`, `BUG-1638`).

_Wiring pass added by `/ll:wire-issue`:_
- **Correction to Expected Behavior bullet 3**: the "ideally `_claim_socket_path()` treats a listener-less socket as stale and reclaims it" hardening already exists and is already pinned by tests — `test_init_unlinks_stale_socket_file` (test_transport.py:417), `test_bound_but_dead_socket_file_is_reclaimed` (:698), `test_stale_pid_suffixed_path_is_reclaimed` (:787) all assert exactly this reclaim behavior today. The opposite case (a genuinely live socket is never evicted) is pinned by `test_eaddrinuse_on_configured_path_falls_back_to_suffixed` (:807) and `test_failed_bind_does_not_unlink_winners_socket` (:835). No code change is needed for this bullet — only the test-hygiene fix (isolating `BRConfig`/cwd) is required to close this bug.
- `conftest.py:952-993` `_guard_real_history_db` (the issue's own cited template): session-scoped + autouse, patches `little_loops.session_store.sqlite3.connect` as the choke point, raises via a plain `assert` inside the wrapped `connect` call (attributes the failure to the offending test at the moment of violation), uses a raw `pytest.MonkeyPatch()` instance undone in `finally` (the function-scoped `monkeypatch` fixture is unavailable at session scope). Companion `_isolate_history_db_session` (:888) is a redirect style (sets `LL_HISTORY_DB` env var) rather than a guard style — both are available models for the new socket fixture.
- **xdist caveat, now moot for the chosen shape**: the sibling `_fail_on_live_host_cli` fixture is deliberately function-scoped, not session-scoped, because (per its own docstring, conftest.py:404-409) `pytest_sessionfinish` "cannot reliably fail the run under the default `-n logical` addopts — xdist workers do not propagate a worker-mutated `session.exitstatus` to the controller." This caveat applies to a session-end snapshot check; it does not apply to `_guard_real_socket_transport`'s choke-point-at-violation-time shape (Program Design), which raises synchronously inside the patched `UnixSocketTransport.__init__` call on the worker that made it — same reliability profile as `_guard_real_history_db`.
- Every other test file referencing `wire_transports` (`test_cli_loop_queue.py:79,573,603,634,664`, `test_sprint_integration.py:570`, `test_cli_sprint.py:1158`, `test_cli_loop_worktree.py:835,871,967,998,1109,1202,1309`, `test_cross_host_baseline.py:176,206`) already mocks it explicitly at every real call site — confirmed clean, no fix needed there.

_Wiring pass added by `/ll:wire-issue`, round 2:_
- No new vulnerable test files exist beyond the 9 already confirmed (re-checked): `test_ll_loop_commands.py`/`test_ll_loop_program_md.py`'s `cmd_run(...)` calls all pass `dry_run=True` (returns before `wire_transports()`); `test_sprint.py`'s `_cmd_sprint_run(...)` calls are all preceded by `monkeypatch.chdir(tmp_path)`; `test_cli.py`/`test_parallel_cli.py`'s `main_parallel()` calls pass an isolated `--config` whose `make_project`-built config never sets `events.transports` (defaults to `[]`, a no-op `wire_transports()` loop). No new production `wire_transports(` call sites exist beyond the already-known 4 (repo-wide grep confirms exactly 4 hits).
- `scripts/tests/test_conftest_cap.py` — precedent for self-testing a new `conftest.py` fixture directly: `TestNoLiveHostCLIGuard` drives `_install_no_live_host_cli.__wrapped__()`'s raw generator (`next(gen)` / assert patched state / `pytest.raises(StopIteration): next(gen)`) instead of running it through pytest's fixture machinery. A `_guard_real_socket_transport` self-test should follow this shape and add a `TestGuardRealSocketTransport`-style class here; no such self-test exists yet. Same file's docstring notes a caveat that applies equally: its standalone-loaded `conftest` module is a separate collector instance from the live plugin's, so seeding one has no effect on the other.
- No `@pytest.mark.parametrize`-over-mock-setup or multi-target `@pytest.fixture(autouse=True)` precedent exists anywhere in `scripts/tests/` for systematizing the 9-test copy-paste fix (Implementation Steps #2) — nearest analog is a single-target autouse class fixture (`test_subprocess_mocks.py:27-31` `_patch_resolve_host`, `test_orchestrator.py:547-553`/`1086-1092` `_no_real_process_sweep`). If the fixture route is chosen over per-test patching, this is the closest existing shape to follow, not an exact template.
- Do not use the `no_parallel` marker to dodge any xdist cross-worker concern for the new guard or its self-test: under this suite's default `-n logical --dist loadfile` addopts, `no_parallel`-marked tests are skipped by workers and never run by the controller (`pytest_collection_modifyitems`; documented precedent at `test_worktree_utils.py:1471-1480`) — a guard relying on it would be silently dormant in CI. `_guard_real_socket_transport`'s choke-point-at-violation-time shape needs no such marker (each xdist worker gets its own independent monkeypatch instance, same reliability profile as `_guard_real_history_db`).

### Documentation
- `docs/reference/CONFIGURATION.md:1622-1656` — already documents, as a known and accepted limitation, that orphaned `events-<pid>.sock` files "are not swept by this or any other mechanism" and accumulate in `.ll/` across crashes. This confirms the sibling half of the bug (stale files from crashed producers, not just from the test suite) is a pre-existing, documented gap this issue's optional `_claim_socket_path()` hardening would also close.
- `docs/ARCHITECTURE.md:617-620` — table of which CLI entry points call `wire_transports()`/`close_transports()`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:628` — the "UnixSocketTransport — concurrent-producer path claiming (BUG-3324)" prose paragraph is the documented source of truth for the probe/reclaim contract confirmed still-correct above; no update needed unless `_claim_socket_path`'s classification logic itself changes.
- `CONTRIBUTING.md` / `docs/development/TROUBLESHOOTING.md` — searched directly, no existing mention of stale-socket cleanup or `.ll/` test-isolation conventions in either; a "two consecutive full-suite runs must both be green" convention (Acceptance Criteria bullet 2) would be a natural, currently-absent addition to `CONTRIBUTING.md`'s testing section once this fix lands.
- `hooks/scripts/session-cleanup.sh` (`Stop` hook) already sweeps specific `.ll/` files (`rm -f .ll/.ll-lock .ll/ll-context-state.json`, line 38) but does not include `.ll/events*.sock`. This hook only fires on Claude Code session lifecycle events, not between manual `pytest` invocations, so it cannot substitute for the `conftest.py` fixture; not needed since the `_claim_socket_path` hardening it might have motivated already exists per above.

_Wiring pass added by `/ll:wire-issue`, round 2:_
- `docs/development/TESTING.md` (~line 1051-1065) — has a `### Live Host-CLI Spawn Guard` subsection documenting FEAT-3329's autouse choke-point guard, but no equivalent subsection exists yet for `_guard_real_history_db` (the fixture `_guard_real_socket_transport` is modeled after) or its `### Key Fixtures` table. Optional, not required by any test or convention — adding a matching subsection for the new fixture would be consistent with the "Live Host-CLI Spawn Guard" precedent, but inconsistent with `_guard_real_history_db` itself never having been documented there.
- CI cannot reproduce this bug's "two consecutive runs in the same checkout" condition: both `unit-tests` and `conformance` jobs use `actions/checkout@v4`, which cleans the workspace before each run (`.github/workflows/ci.yml` G3 comment) — confirms Acceptance Criteria bullet 3 stays a manual/local verification, not something CI enforces or could regress-guard.

### Configuration

_Wiring pass added by `/ll:wire-issue`, round 2:_
- `scripts/little_loops/config-schema.json:1629-1655` — schema definition for `events.transports` (default `[]`) and `events.socket.path` (default `.ll/events.sock`); more precise than the existing `docs/reference/CONFIGURATION.md` citation. No change expected — cited as the schema source of truth.
- `scripts/little_loops/config/features.py:1334-1342` — `EventsConfig` dataclass (`transports: list[str] = field(default_factory=list)`), the object `wire_transports()`'s caller-side `config.events` resolves to. No change expected.
- `.ll/ll-config.json:114-118` — this repo's own live project config sets `"events": {"transports": ["socket"]}`, exactly the config the leaking tests pick up when `BRConfig(Path.cwd())` resolves against the real repo root with no isolation — the concrete "smoking gun" confirming the mechanism, not a file the fix modifies.

## Program Design

### Types

- N/A — no new data types; fix is test-hygiene plus an optional hardening tweak to existing logic.

### Signatures

- `_claim_socket_path(preferred: Path) -> Path` (existing, `scripts/little_loops/transport.py`) — stale-vs-live probe; already correctly reclaims a listener-less stale socket (confirmed by wiring pass), no change needed.
- `_guard_real_socket_transport() -> Generator[None, None, None]` (new, session-scoped autouse fixture in `scripts/tests/conftest.py`, named and shaped after `_guard_real_history_db`, ~952-993) — patches `UnixSocketTransport.__init__` (`scripts/little_loops/transport.py:170`), the single choke point every real socket bind routes through (`self._server.bind(str(claimed))`, lines 201/214), and asserts the resolved path never falls under the real project `.ll/`. Raises at the moment of the violating bind call, attributing the failure to the offending test — a choke-point guard, not a snapshot-diff (see Conventions in Force).

### Call Path

`scripts/tests/conftest.py::_guard_real_socket_transport` (session-scoped autouse fixture) -> wraps `little_loops.transport.UnixSocketTransport.__init__` as a choke point -> on each real construction, asserts the bind path resolved by `_claim_socket_path()` never falls under the real project `.ll/` -> raises immediately on violation (offending test attributed at the point of the bad bind, mirroring `_guard_real_history_db`'s `sqlite3.connect` patch); offending tests (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) instead bind under `tmp_path` via `short_tmp_path` and `.close()` in teardown -> `_claim_socket_path()` continues to correctly reclaim any listener-less stale socket it does encounter (unchanged, already pinned by existing tests).

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

1. Root cause confirmed (wiring pass, mechanism corrected 2026-09-08): `cmd_resume` (`cli/loop/lifecycle.py:713`), `cmd_run` (`cli/loop/run.py:230`), `main_parallel` (`cli/parallel.py:195-196`), and `cli/sprint/run.py:797,801` each build `BRConfig(Path.cwd())` directly, loading this repo's real `.ll/ll-config.json` (`events.transports: ["socket"]`) whenever a test calls one of them for real without mocking `BRConfig`; `wire_transports()`'s `log_dir` then defaults to cwd-relative `.ll` (`transport.py:1896`), binding a real socket that the mocked executor never closes. Live listeners accumulate per process; the third bind raises (see Current Behavior). The `test_transport.py`/`test_feat3323_sse_bridge.py` candidates named in the original bug report are confirmed not the source.
2. **Decision made (2026-09-08): use a fixture, not per-test patches.** With ~36 exposed tests across six classes, per-test `BRConfig` patching (option A) is the wrong shape. Add one autouse fixture — module-level in `test_cli_loop_lifecycle.py` is sufficient, or `conftest.py` if it should also cover `test_cli_loop_worktree.py`-style files — that patches `little_loops.config.BRConfig` to return a `MagicMock` config with `events = MagicMock(transports=[])`, `extensions = {}`, `commands.rate_limits.circuit_breaker_enabled = False`, `design_tokens.enabled = False` (the block already duplicated 5× at `test_cli_loop_lifecycle.py:2213-2374`; extract it into the fixture and delete the copies), and also patches `little_loops.transport.wire_transports`. Tests that intentionally exercise design-token loading (`TestDesignTokensOptOut`) must still be able to override `design_tokens` on the returned mock — verify they pass with the fixture before finalizing. Existing tests that build their own `mock_config` keep working because an inner `patch(...)` wins over the fixture's.
3. Add `_guard_real_socket_transport` (Program Design) — a choke-point guard, not a snapshot-diff, mirroring `_guard_real_history_db` (`conftest.py:952-993`) which replaced an earlier directory-snapshot approach for the sibling history-DB leak (its docstring explains why). It patches `UnixSocketTransport.__init__` (`transport.py:170`), the single point every real socket bind routes through, and asserts the resolved path is never under the real project `.ll/`. This makes any future unmocked entry-point test fail at the offending bind instead of three tests later with an unrelated `RuntimeError`.
4. `python -m pytest scripts/tests/test_cli_loop_lifecycle.py` is green on a clean tree, then `python -m pytest scripts/tests/` twice back-to-back is green both times; verified per the Acceptance Criteria.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Isolate every unmocked `cmd_resume` test in `test_cli_loop_lifecycle.py` (~36 tests; corrected list in Integration Map → Dependent Files) via the autouse fixture decided in Implementation Steps #2 — not per-test patches.
- Inject at `cli/loop/lifecycle.py:713`, `cli/loop/run.py:230`, `cli/parallel.py:195-196`, and the newly-found 4th call site `cli/sprint/run.py:797,801`: consider whether `BRConfig` should accept/propagate an isolated `project_root` consistently, or whether a `conftest.py` autouse fixture (isolating `BRConfig`/cwd, mirroring `_guard_real_history_db`'s choke-point-patch shape or `_isolate_history_db_session`'s env-redirect shape) is the more scoped fix — the issue's own Program Design already favors the choke-point-guard approach for this reason.
- Do NOT implement Expected Behavior bullet 3's `_claim_socket_path` hardening as new work — it already exists and is pinned by `test_init_unlinks_stale_socket_file`, `test_bound_but_dead_socket_file_is_reclaimed`, `test_stale_pid_suffixed_path_is_reclaimed` (test_transport.py:417,698,787). Re-verify these five tests stay green after the fix, but no new hardening code is needed for this bullet.
- Program Design's `_guard_real_socket_transport` is a choke-point-at-violation-time fixture (patches `UnixSocketTransport.__init__`, not a session-end snapshot), so it does not inherit the xdist caveat documented in `_fail_on_live_host_cli`'s docstring (conftest.py:404-409) — no further design work needed on this point.

## Impact

- **Priority**: P3 as filed, but note the corrected picture: this is a **deterministic red file on `main`** since `90c1e137` (2026-09-07), not an intermittent state-dependent flake. Every local-editable consuming project runs its tooling against this tree, and `test_cli_loop_lifecycle.py` currently fails 34/138 on every run. Consider promoting to P2.
- **Effort**: Small - one autouse config-isolation fixture in `test_cli_loop_lifecycle.py` (dedupe the 5 existing `mock_config` copies into it), one choke-point guard in `conftest.py`, one self-test.
- **Risk**: Low - test-only change; no production code touched.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Every unmocked `cmd_resume` test in `test_cli_loop_lifecycle.py` (the ~36 enumerated in Integration Map → Dependent Files) is covered by an autouse fixture that mocks `little_loops.config.BRConfig` (with `events.transports = []`) and `little_loops.transport.wire_transports`, instead of loading this repo's real `.ll/ll-config.json` via `Path.cwd()`.
- [ ] The 5 duplicated inline `mock_config` blocks in `TestCmdResumeCircuitWiring`/`TestCmdResumeTransportWiring` are replaced by that fixture (or a factory it exposes).
- [ ] Add `_guard_real_socket_transport` in `conftest.py` (session-scoped autouse choke-point on `UnixSocketTransport.__init__`) that fails loudly, attributed to the offending test, if any test binds a socket under the real project `.ll/`; with a `TestGuardRealSocketTransport` self-test in `test_conftest_cap.py`.
- [ ] `rm -f .ll/events*.sock && python -m pytest scripts/tests/test_cli_loop_lifecycle.py -n 0` is green (was `34 failed, 104 passed` before the fix) and leaves no `.ll/events*.sock` behind.
- [ ] `python -m pytest scripts/tests/` run twice back-to-back in the same checkout is green both times.
- [ ] `test_init_unlinks_stale_socket_file`, `test_bound_but_dead_socket_file_is_reclaimed`, `test_stale_pid_suffixed_path_is_reclaimed`, `test_eaddrinuse_on_configured_path_falls_back_to_suffixed`, `test_failed_bind_does_not_unlink_winners_socket` remain green (no `transport.py` change).

## Relates To

- BUG-3324 (socket claim/eviction logic), FEAT-3323 (SSE bridge tests)

## Status

**Open** | Created: 2026-09-07 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-08_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 49/100 → LOW

### Gaps to Address
- The `missing_behavior_parity` gap (no `### Behavior Parity` subsection for `scripts/tests/conftest.py`) caps Issue Well-Specified at 10/20 even though the rest of the issue is unusually thorough — add a short `### Behavior Parity` note on how `_guard_real_socket_transport` composes with `_guard_real_history_db`/`_isolate_history_db_session` (both live in the same file) before implementing.

### Outcome Risk Factors
- Wide blast radius: 9 confirmed-vulnerable tests in `test_cli_loop_lifecycle.py` plus 4 production `wire_transports()` call sites (`cli/loop/lifecycle.py:713`, `cli/loop/run.py:230`, `cli/parallel.py:195-196`, `cli/sprint/run.py:797,801`) all need correct treatment — 13 distinct sites raises the odds of a missed one even though the wiring pass already enumerated them by name (re-verified against current code this pass — all four call sites and line numbers still match exactly).
- Not a uniform mechanical substitution (Pattern A, not B): each vulnerable test's mock setup differs and the production call sites would each need site-specific judgment if touched, so there is no enumerated-fanout verification chain to lean on — the 13-site blast radius scores 0/25 on Change Surface.
- Implementation Steps #2 still leaves the mechanism for fixing the 9 vulnerable tests themselves genuinely open (per-test `BRConfig`/`wire_transports` patching vs. a new isolation fixture) — distinct from `_guard_real_socket_transport`, which is only the safety-net guard (AC bullet 2), not the fix for the leak in those 9 tests (AC bullet 1). Resolve this before implementing to pin down the actual diff shape.

_Previous pass (2026-09-07) flagged a self-contradiction in Program Design: the named signature/Call Path described a before/after `.ll/` snapshot-diff while Implementation Steps #3 explicitly called for a choke-point guard instead, citing `_guard_real_history_db`'s precedent against snapshot-diff. Program Design has been corrected — `assert_ll_clean_after_session` replaced with `_guard_real_socket_transport`, a choke-point patch on `UnixSocketTransport.__init__` — and Architecture Compliance now scores 20/20 (was 10/20), raising the readiness tier from PROCEED WITH CAUTION to PROCEED. Outcome Confidence is unaffected — the newly-fixed contradiction didn't touch Complexity, Test Coverage, or Change Surface, and Ambiguity's score is held down by the separate, still-open per-test-vs-fixture decision noted above._

## Session Log
- manual review - 2026-09-08 - premise corrected (reproduced 34 failures on clean .ll/); vulnerable list expanded 9→~36; fixture-vs-per-test decision resolved (fixture); ACs rewritten
- `/ll:wire-issue` - 2026-09-08T03:07:52 - `10d02141-1a61-4549-ac75-31b74fcc4540.jsonl`
- `/ll:refine-issue` - 2026-09-08T02:58:59 - `10d02141-1a61-4549-ac75-31b74fcc4540.jsonl`
- `/ll:decide-issue` - 2026-09-08T02:54:02 - `db8f4456-9d33-4a56-83a5-6fd56728c61f.jsonl`
- `/ll:refine-issue` - 2026-09-08T02:52:56 - `db8f4456-9d33-4a56-83a5-6fd56728c61f.jsonl`
- `/ll:confidence-check` - 2026-09-08T02:48:32 - `dbbb8e28-65c6-4fbb-8510-be5c16cd4905.jsonl`
- `/ll:confidence-check` - 2026-09-08T02:39:08 - `dbbb8e28-65c6-4fbb-8510-be5c16cd4905.jsonl`
- `/ll:reconcile-issue` - 2026-09-08T02:34:55 - `b8eed052-472d-4853-95f4-c43278b4b785.jsonl`
- `/ll:refine-issue` - 2026-09-08T02:29:19 - `0d9d417d-c803-47ff-911c-f30e17e5343e.jsonl`
- `/ll:confidence-check` - 2026-09-08T02:21:36 - `8a6cd350-cac1-4f1e-a42b-0221ef8ee56a.jsonl`
- `/ll:wire-issue` - 2026-09-08T02:00:49 - `2d920f5a-2d4d-4a14-9303-a5bfb4bae86a.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:56:23 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:07:35 - `a2e8c1bc-23e1-4b7e-a7d7-ca1d7c6bb1b1.jsonl`
