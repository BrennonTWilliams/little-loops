---
id: BUG-3401
type: BUG
title: Stale .ll/events-*.sock left by suite makes cmd_resume tests fail on the next
  run
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
---

# BUG-3401: Stale .ll/events-*.sock left by suite makes cmd_resume tests fail on the next run

## Summary

Running the full unit suite on a tree where `.ll/events-*.sock` files already exist produces 35 failures in `scripts/tests/test_cli_loop_lifecycle.py` (the `cmd_resume` transport tests). The files are left behind by the suite's own earlier socket-transport tests, so a second consecutive run of `python -m pytest scripts/tests/` in the same checkout is red while a run after `rm .ll/events-*.sock` is green.

Observed 2026-09-07 while verifying the EPIC-3212 merge. `.ll/events.sock` and `.ll/events-<pid>.sock` were present with no live process holding them (`lsof -U` empty).

## Current Behavior

- Some socket-transport test (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) binds `UnixSocketTransport` against the real project `.ll/` directory instead of `tmp_path`, or binds it there and never calls `close()`, so the socket file survives the test session.
- On the next run, `_claim_socket_path()` in `scripts/little_loops/transport.py` treats the stale file as a possible live listener (BUG-3324 sibling logic), pushes the transport onto an `events-<pid>.sock` sibling path, and the `cmd_resume` tests that assert on the wiring/teardown path fail.
- The failure is order- and state-dependent, so it looks like a regression in whatever branch was merged last. It cost an investigation cycle on EPIC-3212 before it was traced to the leftover files.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

Codebase-locator and codebase-analyzer agents traced the two named candidate files and the `wire_transports()` call path itself, refining the leak hypothesis:

Every direct `UnixSocketTransport(...)` construction in `test_transport.py` and `test_feat3323_sse_bridge.py` (the two files this issue names as candidates) already binds under a `short_tmp_path` fixture (`tempfile.mkdtemp(prefix="ll-")`, not the real project `.ll/`) with a matching `.close()` in every case — confirmed by exhaustive grep across both files. Neither named candidate file's own transport tests appear to be the leak source as originally hypothesized.

The more likely mechanism, found by tracing `wire_transports()` itself (`scripts/little_loops/transport.py:1876-1917`): its `log_dir` parameter defaults to `Path(".ll")` **relative to the process's current working directory** when not explicitly passed (`base = log_dir if log_dir is not None else Path(".ll")`, line 1896) — this is a documented, intentional default for production use (real `ll-loop`/`ll-parallel` invocations run from a project root and are meant to write into that project's real `.ll/`). The three production call sites — `cmd_resume` (`cli/loop/lifecycle.py:737`), `cmd_run` (`cli/loop/run.py:623`), `main_parallel` (`cli/parallel.py:322`) — all call `wire_transports(bus, config.events)` with **no `log_dir` argument**. `EventsConfig.transports` defaults to an empty list (`config/features.py:1342`), so this only matters when something enables the `"socket"` transport. This repo's own `.ll/ll-config.json` does exactly that (`"events": {"transports": ["socket"]}`) — a test path that ends up consulting the real project's own config (rather than a fully isolated tmp-path config) while calling `cmd_resume`/`cmd_run`/`main_parallel` for real, without also passing an isolated `log_dir`, would write `.ll/events.sock` at the real repo root exactly as observed. This is a plausible, code-verified mechanism, not a confirmed root cause — the specific test/fixture combination that omits the `log_dir` override was not identified by this pass and needs runtime confirmation (e.g. bisecting with `-p no:randomly` or instrumenting `wire_transports` during a full-suite run).

## Steps to Reproduce

1. In a clean checkout, run `python -m pytest scripts/tests/` once — it passes and leaves `.ll/events.sock` and/or `.ll/events-<pid>.sock` behind (the socket-transport tests bind against the real project `.ll/` instead of `tmp_path`, or never call `close()`).
2. Without removing those files, run `python -m pytest scripts/tests/` again in the same checkout.
3. Observe: 35 failures in `scripts/tests/test_cli_loop_lifecycle.py` (`cmd_resume` transport tests) — `_claim_socket_path()` treats the stale, listener-less socket file as live and pushes the transport onto an `events-<pid>.sock` sibling path, breaking the wiring/teardown assertions.

## Expected Behavior

- No test writes into the checkout's real `.ll/`; socket-transport tests bind under `tmp_path` (or monkeypatch the project root) and close the transport in teardown.
- Two consecutive full-suite runs in the same checkout are both green with no manual cleanup.
- Ideally `_claim_socket_path()`'s stale-vs-live probe treats a socket with no listener as stale and reclaims it, so a crashed producer does not poison later runs either.

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

### Files to Modify
- `scripts/tests/conftest.py` — no existing fixture guards `.ll/` socket-file cleanliness (confirmed absent). Existing session-scoped isolation fixtures to model after: `_isolate_history_db_session` (~888) and `_guard_real_history_db` (~952-993), which patches `little_loops.session_store.sqlite3.connect` as a choke point and asserts the resolved path is never the real DB — its docstring explicitly notes this **replaced** an earlier before/after directory-snapshot approach because a snapshot can't attribute a leak to the offending test and isn't immune to concurrent external writers. This is directly relevant to the issue's own proposed `assert_ll_clean_after_session` shape (a snapshot-diff), which this codebase already tried and moved away from for a sibling problem.
- `scripts/little_loops/transport.py` — `_claim_socket_path()` (line 1559) and `_probe_socket_path()` (line 1529) are the existing stale-vs-live probe; `wire_transports()` (line 1876) is where the `log_dir`-default-to-cwd mechanism lives (see Current Behavior finding above).

### Dependent Files (Callers/Importers)
- Every direct `UnixSocketTransport(...)` construction in `scripts/tests/test_transport.py` and `scripts/tests/test_feat3323_sse_bridge.py` already binds under each file's own `short_tmp_path` fixture (`tempfile.mkdtemp(prefix="ll-")`) with a matching `.close()` — confirmed by exhaustive grep, not a leak source as originally hypothesized.
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeTransportWiring`-style tests (~2277-2376) patch `little_loops.transport.wire_transports` entirely (`MagicMock(transports=[])`), never constructing a real socket. Hundreds of other real (non-mocked) `cmd_resume(...)`/`cmd_run(...)` calls exist in this file (lines 621-1524+) with `tmp_path` as the project-root argument — these are real invocations whose internal `wire_transports()` call still defaults `log_dir` to cwd-relative `.ll` regardless of the `tmp_path` project root passed to `cmd_resume` itself, if `config.events.transports` ends up containing `"socket"`.
- `scripts/tests/test_cli_e2e.py` — `e2e_project_dir` fixture (line 28) uses `tempfile.TemporaryDirectory()`, not the real repo `.ll/`; `test_ll_parallel_wires_transports` patches `wire_transports` entirely.

_Wiring pass added by `/ll:wire-issue`:_
- **Root cause confirmed and localized.** The full chain: `cmd_resume` (`cli/loop/lifecycle.py:713`) does `config = BRConfig(Path.cwd())` — loading the **entire config object**, not just `log_dir`, from process cwd, independent of the `tmp_path`/`project_root` argument passed to `cmd_resume` for everything else. `cmd_run` (`cli/loop/run.py:230`) and `main_parallel` (`cli/parallel.py:195-196`, `project_root = args.config or Path.cwd()`) do the same. During `python -m pytest scripts/tests/`, cwd is the repo root, so any test that doesn't mock `little_loops.config.BRConfig` loads this repo's real `.ll/ll-config.json` (`events.transports: ["socket"]`), and `wire_transports()`'s `log_dir` default (`transport.py:1896`) then binds a real socket at the real repo `.ll/`.
- **Exact vulnerable test list** in `scripts/tests/test_cli_loop_lifecycle.py` (reach the real `wire_transports()` call, mock only `load_loop`/`StatePersistence`/`PersistentExecutor`, never `BRConfig` or `wire_transports`): `test_nothing_to_resume_returns_1` (639-657), `test_resume_success` (659-684), `test_resume_with_minutes_duration` (686-723), `test_resume_awaiting_continuation` (725-761), `test_resume_non_terminal_returns_1` (~763), `test_context_overrides_applied_to_fsm` (859-884), `test_design_tokens_context_injected_via_cmd_resume` (921-948), `test_design_guidance_context_injected_via_cmd_resume` (950-977), `test_input_hash_injected_via_cmd_resume` (979-1010).
- **Confirmed safe** (return before the `wire_transports()` call is reached): `test_file_not_found_returns_1` (612-624), `test_validation_error_returns_1` (626-637), `test_context_invalid_format_raises_system_exit` (886-901), all of `TestCmdResumeBackground` (1011-1269, `background=True` returns via `run_background` before the wire block), and all `cmd_run` tests in this file (`TestCmdRunHandoffThreshold` 1348-1441, `TestCmdRunYAMLConfigOverrides` 1628-1724 — `_make_args()` defaults `dry_run=True`, which returns before `wire_transports`).
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
- **xdist caveat on session-scoped assertion**: the sibling `_fail_on_live_host_cli` fixture is deliberately function-scoped, not session-scoped, because (per its own docstring, conftest.py:404-409) `pytest_sessionfinish` "cannot reliably fail the run under the default `-n logical` addopts — xdist workers do not propagate a worker-mutated `session.exitstatus` to the controller." If the new `.ll/` cleanliness guard is modeled as a session-end snapshot check rather than a choke-point-at-violation-time check (like `_guard_real_history_db`), it inherits this same xdist-reliability caveat.
- Every other test file referencing `wire_transports` (`test_cli_loop_queue.py:79,573,603,634,664`, `test_sprint_integration.py:570`, `test_cli_sprint.py:1158`, `test_cli_loop_worktree.py:835,871,967,998,1109,1202,1309`, `test_cross_host_baseline.py:176,206`) already mocks it explicitly at every real call site — confirmed clean, no fix needed there.

### Documentation
- `docs/reference/CONFIGURATION.md:1622-1656` — already documents, as a known and accepted limitation, that orphaned `events-<pid>.sock` files "are not swept by this or any other mechanism" and accumulate in `.ll/` across crashes. This confirms the sibling half of the bug (stale files from crashed producers, not just from the test suite) is a pre-existing, documented gap this issue's optional `_claim_socket_path()` hardening would also close.
- `docs/ARCHITECTURE.md:617-620` — table of which CLI entry points call `wire_transports()`/`close_transports()`.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md:628` — the "UnixSocketTransport — concurrent-producer path claiming (BUG-3324)" prose paragraph is the documented source of truth for the probe/reclaim contract confirmed still-correct above; no update needed unless `_claim_socket_path`'s classification logic itself changes.
- `CONTRIBUTING.md` / `docs/development/TROUBLESHOOTING.md` — searched directly, no existing mention of stale-socket cleanup or `.ll/` test-isolation conventions in either; a "two consecutive full-suite runs must both be green" convention (Acceptance Criteria bullet 2) would be a natural, currently-absent addition to `CONTRIBUTING.md`'s testing section once this fix lands.
- `hooks/scripts/session-cleanup.sh` (`Stop` hook) already sweeps specific `.ll/` files (`rm -f .ll/.ll-lock .ll/ll-context-state.json`, line 38) but does not include `.ll/events*.sock`. This hook only fires on Claude Code session lifecycle events, not between manual `pytest` invocations, so it cannot substitute for the `conftest.py` fixture; not needed since the `_claim_socket_path` hardening it might have motivated already exists per above.

## Program Design

### Types

- N/A — no new data types; fix is test-hygiene plus an optional hardening tweak to existing logic.

### Signatures

- `_claim_socket_path(preferred: Path) -> Path` (existing, `scripts/little_loops/transport.py`) — stale-vs-live probe to harden against a listener-less socket file.
- `assert_ll_clean_after_session() -> None` (new, session-scoped autouse fixture in `scripts/tests/conftest.py`) — fails the session if any test leaves files under the real `.ll/`.

### Call Path

`scripts/tests/conftest.py::assert_ll_clean_after_session` (autouse fixture) -> snapshot `.ll/` contents before/after the session -> fail loudly on new files; offending tests (candidates: `scripts/tests/test_transport.py`, `scripts/tests/test_feat3323_sse_bridge.py`) -> `UnixSocketTransport(...)` bound under `tmp_path` -> `.close()` in teardown -> `_claim_socket_path()` reclaims a listener-less stale socket instead of treating it as live.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-08 — based on codebase analysis:_

1. Confirm the actual leaking call path: run the full suite once, then re-run with a temporary instrumentation of `wire_transports()` (or a `strace`/`opensnoop`-style trace) to catch which call constructs `.ll/events.sock` at the real repo root without an isolated `log_dir` — the `test_transport.py`/`test_feat3323_sse_bridge.py` candidates named in the original bug report are not the source (see Current Behavior → Codebase Research Findings); the more likely mechanism is a real, non-mocked `cmd_resume`/`cmd_run`/`main_parallel` invocation combined with a config where `events.transports` includes `"socket"`, since `wire_transports()`'s `log_dir` defaults to cwd-relative `Path(".ll")` (`transport.py:1896`) whenever the caller omits it, which all three production call sites do by design.
   > ⚠ Superseded — leak source confirmed by wire-issue pass (see Integration Map)
2. Fix the confirmed offending test(s) to either isolate `log_dir` (mirroring `short_tmp_path`, `test_transport.py:57-69`) or ensure `config.events.transports` excludes `"socket"` in that fixture's config, plus `.close()`/teardown per the existing inline `try/finally` convention (no `yield`-fixture precedent exists for this in the codebase).
3. Add a choke-point guard, not a snapshot-diff — this codebase already tried and replaced a directory-snapshot approach for a sibling problem (`_guard_real_history_db`, `conftest.py:952-993`, docstring explains why); the equivalent for sockets would intercept the actual socket-bind/connect call and assert the resolved path is never under the real project `.ll/`.
4. `python -m pytest scripts/tests/` run twice back-to-back in a clean checkout is green both times; verified per the existing Acceptance Criteria.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Fix or isolate the 9 confirmed vulnerable tests in `test_cli_loop_lifecycle.py` (`test_nothing_to_resume_returns_1`, `test_resume_success`, `test_resume_with_minutes_duration`, `test_resume_awaiting_continuation`, `test_resume_non_terminal_returns_1`, `test_context_overrides_applied_to_fsm`, `test_design_tokens_context_injected_via_cmd_resume`, `test_design_guidance_context_injected_via_cmd_resume`, `test_input_hash_injected_via_cmd_resume`) — either by adding a `BRConfig`/`wire_transports` patch (mirroring `TestCmdResumeCircuitWiring`, conftest.py-adjacent pattern at test_cli_loop_lifecycle.py:2196-2274) or via a new session-wide isolation fixture.
- Inject at `cli/loop/lifecycle.py:713`, `cli/loop/run.py:230`, `cli/parallel.py:195-196`, and the newly-found 4th call site `cli/sprint/run.py:797,801`: consider whether `BRConfig` should accept/propagate an isolated `project_root` consistently, or whether a `conftest.py` autouse fixture (isolating `BRConfig`/cwd, mirroring `_guard_real_history_db`'s choke-point-patch shape or `_isolate_history_db_session`'s env-redirect shape) is the more scoped fix — the issue's own Program Design already favors the choke-point-guard approach for this reason.
- Do NOT implement Expected Behavior bullet 3's `_claim_socket_path` hardening as new work — it already exists and is pinned by `test_init_unlinks_stale_socket_file`, `test_bound_but_dead_socket_file_is_reclaimed`, `test_stale_pid_suffixed_path_is_reclaimed` (test_transport.py:417,698,787). Re-verify these five tests stay green after the fix, but no new hardening code is needed for this bullet.
- If a new session-scoped autouse `.ll/` cleanliness fixture is added, be aware of the xdist caveat documented in `_fail_on_live_host_cli`'s docstring (conftest.py:404-409) — a session-end check may not reliably fail the run under `-n logical`; prefer the choke-point-at-violation-time shape (`_guard_real_history_db`) if reliability under xdist matters.

## Impact

- **Priority**: P3 - test-hygiene defect; no production impact, but it manufactures false regressions and cost an investigation cycle during the EPIC-3212 merge review.
- **Effort**: Small - locate the offending test(s), move them to `tmp_path`, add teardown, add a `.ll/` cleanliness guard.
- **Risk**: Low - test-only change; the optional `_claim_socket_path()` hardening is a small, separately testable tweak.
- **Breaking Change**: No

## Acceptance Criteria

- [ ] Identify the test(s) that create `.ll/events*.sock` in the repo root; fix them to use `tmp_path` and to close the transport in teardown.
- [ ] Add a session-scoped guard (fixture or `conftest.py` check) that fails loudly if a test leaves files in the real `.ll/` directory.
- [ ] `python -m pytest scripts/tests/` run twice back-to-back in a clean checkout is green both times.
- [ ] The 35 `cmd_resume` failures reproduce with a hand-placed stale `.ll/events.sock` before the fix and do not after.

## Relates To

- BUG-3324 (socket claim/eviction logic), FEAT-3323 (SSE bridge tests)

## Status

**Open** | Created: 2026-09-07 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-07_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 49/100 → LOW

### Outcome Risk Factors
- Wide blast radius: 9 confirmed-vulnerable tests in `test_cli_loop_lifecycle.py` plus 4 production `wire_transports()` call sites (`cli/loop/lifecycle.py:713`, `cli/loop/run.py:230`, `cli/parallel.py:195-196`, `cli/sprint/run.py:797,801`) all need correct treatment — 13 distinct sites raises the odds of a missed one even though the wiring pass already enumerated them by name.
- The implementation shape is left genuinely open: the wiring pass explicitly offers two different fixes (patch `BRConfig`/`wire_transports` in each of the 9 vulnerable tests individually, vs. a single new session-wide `conftest.py` isolation fixture) without resolving which to use — that judgment call affects both the breadth of the change and how the 9 tests get closed out.
- The `missing_behavior_parity` gap (no `### Behavior Parity` subsection for `scripts/tests/conftest.py`) caps Issue Well-Specified at 10/20 even though the rest of the issue is unusually thorough — worth a short explicit note on how the new fixture composes with `_guard_real_history_db`/`_isolate_history_db_session` before implementation.

## Session Log
- `/ll:confidence-check` - 2026-09-08T02:21:36 - `8a6cd350-cac1-4f1e-a42b-0221ef8ee56a.jsonl`
- `/ll:wire-issue` - 2026-09-08T02:00:49 - `2d920f5a-2d4d-4a14-9303-a5bfb4bae86a.jsonl`
- `/ll:refine-issue` - 2026-09-08T00:56:23 - `c12a8469-1c0e-4551-abdc-a66d5e5d6bda.jsonl`
- `/ll:format-issue` - 2026-09-08T00:07:35 - `a2e8c1bc-23e1-4b7e-a7d7-ca1d7c6bb1b1.jsonl`
