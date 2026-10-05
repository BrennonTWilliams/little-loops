---
id: ENH-3677
type: ENH
title: Hoist the shared remote history-backend test fixture into conftest.py
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:30:36Z'
reconcile_attempted: true
blocks:
- ENH-3657
- ENH-3700
- ENH-3658
- ENH-3682
- ENH-3668
- ENH-3728
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3677: Hoist the shared remote history-backend test fixture into conftest.py

## Summary

Hoist the `remote` test fixture (HranaStub + libsql `ll-config.json` + `chdir` + cache clears + `delenv("LL_HISTORY_DB")` + `remote_telemetry.reset_for_tests()` in teardown) into `scripts/tests/conftest.py` and delete the six per-file copies. Split out of the 2026-09-29 pre-implementation review of ENH-3657/ENH-3658: both plan many remote-stub tests, and BUG-3652 (landed `62ac0fc89`) did not hoist the fixture — it added a sixth copy.

## Current Behavior

The fixture is copied in `test_remote_operation_matrix.py:29`, `test_remote_hooks.py:29`, `test_libsql_backend.py:66` (plus a separate `stub` fixture), `test_remote_doctor.py:35`, `test_remote_ingestion_telemetry.py:57` and `test_remote_callers_bug3652.py:67`. The copies differ (telemetry reset, `LL_NON_INTERACTIVE` handling). `conftest.py` has none.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-30 — based on codebase analysis:_

- **Reconciled difference table** (verified against the six bodies). Shared by all: env `LL_HISTORY_AUTH_TOKEN`/`LL_HISTORY_URL` set, `LL_HISTORY_DB` deleted, libsql `history.backend` block (`url_env: LL_HISTORY_URL`, `project_id: "acme-api"`) written to `.ll/ll-config.json`, `chdir(tmp_path)`, verification + backend-config caches cleared, `migrate_remote(...)` run, stub stopped in teardown. Per-file `TOKEN = "sentinel-token-DO-NOT-LEAK"`.
  - **Material — `LL_MACHINE_ID="machine-a"`** (ingestion only): `TestRemoteIngestion` asserts watermark key `last_raw_event_ts:machine-a`; `TestMachineId` mutates it further.
  - **Material — `telemetry_timeout_ms: 1500`** in the written config (ingestion only): equals `DEFAULT_TELEMETRY_TIMEOUT_MS` in `targets.py`, so dropping it is behaviour-neutral unless a test asserts the key is present.
  - **Material — telemetry reset**: hooks and doctor reset before yield only; ingestion and bug3652 also in `finally`; matrix and libsql not at all. Tests in hooks/ingestion/bug3652 assert warn-once counts (`<= 1` / exactly 1 WARNING).
  - **Material — `delenv("LL_NON_INTERACTIVE")`** (hooks, bug3652): gates the backfill spawn in `little_loops/hooks/session_start.py`; `TestSessionStart.test_never_asks_the_worker_to_rebuild_a_remote_store` asserts one spawn. `LL_NON_INTERACTIVE` is not in conftest's `_CMD_RUN_ENV_VARS`, so nothing global clears it.
  - **Structural — libsql copy** takes a sibling `stub` fixture (which migrates and stamps the schema *before* the config is written and chdir happens) and does not create/stop the stub itself. Its `remote` config also carries `auth_token_env: "LL_HISTORY_AUTH_TOKEN"` (equals `DEFAULT_TOKEN_ENV`, so behaviour-neutral) and it has an autouse `_token_env`. No test in the file requests both `stub` and `remote` today (searched by signature); a hoisted self-contained `remote` would create a *different* stub from the file-local `stub`, so that invariant must hold.
  - **Drift, no dependent test found**: `mkdir()` vs `mkdir(exist_ok=True)`; `finally` vs post-yield teardown; libsql annotated `-> HranaStub` on a generator; unused `url` param on bug3652's `_write_remote_config`.
- **Rewrite-in-test pattern**: several tests rewrite `.ll/ll-config.json` mid-test through file-local helpers (`_write` in doctor, `_write_config` in libsql/ingestion, `_write_remote_config` in bug3652) and clear the backend-config cache themselves; those helpers and their call sites are independent of the fixture body.

## Expected Behavior

One shared fixture in `conftest.py`; each remote test file requests it by pytest fixture resolution, without importing another test module or adding copies. Keep the direct-backend `stub` fixture separate. Reset caches and remote telemetry before and after each shared-fixture use, including setup failure.

**Variant decisions (2026-10-04):** the shared fixture does not set `LL_MACHINE_ID` or clear `LL_NON_INTERACTIVE`. In ingestion tests, layer `LL_MACHINE_ID="machine-a"` through a distinctly named file-local variant fixture depending on `remote`; hooks and bug3652 tests that need interactive spawning similarly clear `LL_NON_INTERACTIVE` in a distinct variant. Request these variants only where needed so unrelated tests do not acquire a server/tmp-path cost. No variant is named `remote`, creates its own stub, or repeats config/migration/cache setup. Keep the ingestion helper's timeout override where tests change it; its baseline 1500ms equals the shared default. Retain the independent direct-backend `stub` and libsql `_token_env` fixture.

Start the stub inside a cleanup scope covering **all** subsequent config/env setup and migration before `yield`, not just the test body. Use `finally` to stop it and clear verification/backend/telemetry caches even if setup fails; monkeypatch restores cwd/env at fixture teardown. Dedicated fixture tests cover one successful lifecycle and an injected setup/migration failure, using an isolated monkeypatch context and asserting restoration/no leftover server. Do not add lifecycle assertions to every consumer test.

## Scope Boundaries

- **In scope**: one shared `remote` fixture in `scripts/tests/conftest.py`; migrating the six existing copies to it.
- **Out of scope**: writing new remote-stub tests (ENH-3657, ENH-3658), changing `HranaStub`, any non-test code.

## Behavior Parity

The six migrated test files keep the same remote configuration, temporary cwd, cache isolation, telemetry reset, and file-specific environment variants. The separate direct-backend `stub` fixture remains available. A test's result must not change merely because its `remote` setup moved to `conftest.py`.

## Proposed Solution

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-30 — based on codebase analysis:_

**Conventions in force** (evidence, not templates):
- conftest fixtures are plain `@pytest.fixture` functions with a docstring naming the motivating issue, env changes via `monkeypatch`, heavy/optional imports inside the fixture body, and no `from tests.*` imports at conftest top level (`scripts/tests/conftest.py`; `_clear_doctor_catalog_probe_cache`, `_guard_real_history_db`). `HranaStub` is reached as `tests.hrana_stub`; a conftest fixture will need a function-body import (or an established alternative) to respect that rule.
- Cache-reset fixtures clear both before and after `yield` (`_clear_doctor_catalog_probe_cache`, `_reset_deprecated_key_warnings`), matching the issue's "before and after" requirement.
- `_isolate_history_db` (autouse) deliberately avoids `tmp_path` unless the test requests it, because per-test dir creation drove the macOS beachball load; the shared `remote` requests `tmp_path` and must not turn that into a suite-wide autouse cost — keep it opt-in by name.
- pytest resolves the closest fixture: any file-local `def remote(` silently shadows conftest's, so a leftover copy passes tests while defeating the hoist. No gate enforces the AC "no `def remote(`" today (no AST scan for shadowed fixtures exists; `test_remote_callers_bug3652.py` uses an `ast.Call` scan only for `resolve_history_db()` callers).
- Suite runs `-n logical --dist loadfile`: module-level caches are per-worker; the stub binds `127.0.0.1:0`, so a shared fixture creates no cross-worker collision.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-30 — based on codebase analysis:_

- **Files to modify (test-only)**: `scripts/tests/conftest.py` (gains the shared `remote`; no `remote`/`stub` exists there today, so no name collision) and the six copies — `test_remote_operation_matrix.py:30`, `test_remote_hooks.py:29`, `test_libsql_backend.py:67`, `test_remote_doctor.py:35`, `test_remote_ingestion_telemetry.py:58`, `test_remote_callers_bug3652.py:67`.
- **Dependents inside the six files**: `test_remote_hooks.py::TestDeadEndpointDegrades.dead` (class-level fixture at :158) requests `remote`, rewrites the config, calls `remote.stop()` and returns it; it must keep working against the shared fixture. `test_libsql_backend.py::TestConnection.conn` and several `TestReadOnly`/`TestConnection` tests use the local `stub` directly (without `remote`) and stay on it.
- **Consumers waiting on this**: ENH-3657, ENH-3700, ENH-3658, ENH-3682 and ENH-3728 (frontmatter `blocks`); deferred ENH-3668 also cites it. ENH-3729's general SFT failure-routing tests are backend-independent and need no fixture edge. ENH-3680 is cancelled and requires no fixture or spool work. BUG-3659 is closed; repointing its historical fixture note is optional.
- **Stub location**: `HranaStub` lives in `scripts/tests/hrana_stub.py` (`class HranaStub(http.server.ThreadingHTTPServer)`; `.start()`, `.stop()`, `.url`, `.requests`, `.fail_next`, `.delay`, `.db`). All eight consumers import it as `from tests.hrana_stub import HranaStub`.
- **Cache/reset entry points** (public, already called by every copy): `little_loops.session_store.db.clear_backend_config_cache`, `little_loops.session_store.remote_schema.clear_verification_cache`, `little_loops.session_store.remote_telemetry.reset_for_tests`.
- **Same-shape setups that are NOT `remote` copies** (out of scope): `stub` fixtures in `test_remote_schema.py:38`, `test_hrana_client.py:39`, `test_libsql_backend.py:40`; autouse `_fresh` in `test_libsql_integration.py:74` and `_reset` in `test_remote_schema.py`. Unrelated `stub` fixtures (`_Stub`) in `test_autodev_proof_reentry.py:78`, `test_advise_ready_gate.py:81`.
- **Docs**: `docs/development/TESTING.md` § "Built-in Fixtures (from `conftest.py`)" (~:186) lists conftest fixtures and has no `HranaStub`/`remote` entry.

_Added by `/ll:refine-issue` — 2026-09-30 — based on codebase analysis:_

- **Re-verified 2026-09-29 (gap analysis)**: exactly six `def remote(` fixtures exist under `scripts/tests` (`test_remote_operation_matrix.py:30`, `test_remote_hooks.py:29`, `test_libsql_backend.py:67`, `test_remote_doctor.py:35`, `test_remote_ingestion_telemetry.py:58`, `test_remote_callers_bug3652.py:67`); no `remote` or `stub` fixture is defined in any of the three conftests (`scripts/tests/conftest.py`, `conformance/conftest.py`, `spike/action_stall_run_scope/conftest.py`), so no collision at any conftest level. `test_libsql_backend.py:67` is the only copy that is not self-contained (takes the local `stub` at `:40`).
- **Stale wiring-note target**: BUG-3659 is `status: done`, so the Dependent Files/Documentation notes above that ask to repoint its `test_remote_hooks.py::remote` references describe a closed record. Editing it is optional and not needed for the acceptance criteria.
- **Consumer chain**: ENH-3657/3700/3658/3682 use this fixture; ENH-3682 additionally depends on external ENH-3720's deadline primitive. ENH-3668 is deferred and ENH-3684/3685 reach it transitively. ENH-3680 is cancelled, with remote writes intentionally skipped; no spool prerequisite is to be re-added.
- **Non-fixture `remote` names are safe**: `test_session_store_backend.py` (`:311`, `:328`, `:353`) and `spike/session_store_backend_dialect/test_backend.py:94` bind `remote` as a local variable, not a fixture request, so a conftest-level fixture does not affect them.
- **`test_libsql_integration.py`** (`_fresh` autouse at `:72`, `_target` at `:48`) resets the same caches but builds no stub or config; it is not a `remote` copy and stays untouched.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/conftest.py` — `_isolate_history_db` (autouse) sets `LL_HISTORY_DB` from `tmp_path` when `"tmp_path" in request.fixturenames` (transitive, so the shared `remote` requesting `tmp_path` behaves like each copy). Autouse runs before requested fixtures, so the shared body's `delenv("LL_HISTORY_DB")` must stay inside `remote`, never in callers [Agent 2 finding]
- `scripts/tests/conftest.py` — `_guard_real_history_db` replaces `sqlite3.connect`; will not trip on remote setup (`HranaStub.__init__` connects to `":memory:"`, resolved under the `chdir`'d cwd, not the real DB) [Agent 2 finding]
- `scripts/tests/test_conftest_cap.py` — `exec_module`s `conftest.py` a second time as `conftest_under_test`; module-level imports added to conftest run again there, so `HranaStub` and `little_loops.session_store.*` imports stay in the fixture body [Agent 2 finding]
- `scripts/tests/test_remote_operation_matrix.py` — helper `TestRemoteOperationMatrix._messages(stub)` and `TestRejectedOperations` take the yielded stub as a plain argument / snapshot `len(remote.requests)`; unaffected by the hoist provided `remote` still yields the started `HranaStub` [Agent 1 finding]
- `scripts/tests/test_remote_ingestion_telemetry.py` — helper `_meta(stub, key)` (:104) and `TestTelemetryBudget` tests call file-local `_write_config(tmp_path, timeout_ms=...)`; keep the helper local [Agent 1/3 finding]
- `scripts/tests/test_remote_callers_bug3652.py` — helper `_count(stub, table)` (:88) takes the yielded stub as an argument [Agent 1 finding]
- `scripts/tests/test_remote_schema.py` — `project(self, stub, tmp_path, monkeypatch)` at :217 is a `remote`-shaped fixture under another name; not a `def remote(` copy, so out of scope, but a follow-up hoist candidate [Agent 1 finding]
- Closed BUG-3659's fixture reference can optionally be repointed; no historical issue edit is required to complete this test-only change. ENH-3657 already commits to the shared fixture and no longer contains the old per-file-copy STOP alternative.

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_conftest_cap.py` — new `TestRemoteFixture`: no test covers the fixture itself. Follow the `TestNoLiveHostCLIGuard` / `TestGuardRealSocketTransport` pattern — drive `conftest.remote.__wrapped__(tmp_path, monkeypatch)` with `next(gen)`, assert `LL_HISTORY_DB` deleted, libsql `history.backend` block written, cwd is `tmp_path`, caches and remote telemetry cleared, then `pytest.raises(StopIteration)` on teardown with the stub stopped [Agent 3 finding]
- `scripts/tests/` (new gate file, e.g. `test_no_shadowed_remote_fixture.py`) — the AC "no file-local `def remote(`" has no automated check. Reuse the `test_remote_callers_bug3652.py` gate shape (`ast.parse`/`ast.walk`, planted-source detector self-tests such as `test_detector_rejects_a_stray_pre_resolve`): flag any `ast.FunctionDef` named `remote` decorated `pytest.fixture` / `pytest.fixture(...)` outside `conftest.py`. A plain grep also matches non-fixture helpers [Agent 3 finding]
- `scripts/tests/test_remote_hooks.py` — session-start tests need `LL_NON_INTERACTIVE` deleted in their file-local variant. Dead-endpoint consumers can still stop the shared stub early; fixture teardown remains idempotent, as today.
- `scripts/tests/test_remote_ingestion_telemetry.py` — `TestRemoteIngestion.test_watermark_is_per_machine_and_the_global_key_is_untouched` and `test_another_machines_progress_does_not_skip_older_transcripts` need `LL_MACHINE_ID="machine-a"` layered file-locally; `test_a_warm_file_cache_skips_the_verification_round_trip` / `test_a_stale_file_cache_entry_is_ignored` rely on the fixture's cache clears + `migrate_remote` before `yield` [Agent 3 finding]
- `scripts/tests/test_remote_doctor.py` — `_write(...)` helper is reused mid-test (~:99, ~:113); `TestNoTokenLeaks` and `TestHistoryDbProbe` call `remote.stop()` directly [Agent 3 finding]
- `scripts/tests/test_libsql_backend.py` — `TestSchemaSeam.test_ensure_db_refuses_a_remote_target_before_any_mutation`, `test_connect_with_a_default_shaped_path_reaches_the_remote_store`, `test_config_is_cached_per_process` use `remote` alone; `test_local_md_frontmatter_overrides_the_endpoint`, `TestConnection.conn`, `TestReadOnly` use the local `stub` alone; autouse `_token_env` stays local [Agent 3 finding]
- Request-count assertions across the six files are relative (`before = len(x.requests)` … `== before` / `< 20`); none pins an absolute count including the fixture's migration traffic, so migration ordering cannot break them. Only `test_literal_prefilter_keeps_the_scan_bounded` reads `remote.requests[-1]["body"]` [Agent 2 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/development/TESTING.md` — also `### Key Fixtures` (~:1052) describes other conftest fixtures (live-spawn guard, rate-limit backoff collapse); the `remote` entry can cross-reference it alongside the § Built-in Fixtures (~:186) line [Agent 1 finding]
- Closed BUG-3659 fixture-reference cleanup is optional (see Dependent Files).

## Program Design

### Codebase Research Findings

### Types
- `remote: Iterator[HranaStub]` — function-scoped generator fixture yielding the started `HranaStub` from `tests.hrana_stub`; conftest's existing generator fixtures annotate with `collections.abc` generators, and `Iterator` is not yet imported there.

### Signatures
- `HranaStub(token: str)` — `.start()` returns the running stub; `.stop()`, `.url`, `.requests`, `.db` are the attributes the six files consume.
- `clear_backend_config_cache() -> None` — `little_loops.session_store.db`; invalidates the per-process `.ll/` config cache.
- `clear_verification_cache() -> None` — `little_loops.session_store.remote_schema`; clears the verified-schema memo.
- `reset_for_tests() -> None` — `little_loops.session_store.remote_telemetry`; clears the warn-once set.
- `migrate_remote(client: HranaClient, project_id: str)` — `little_loops.session_store.remote_schema`; run against the stub after the caches are cleared.

### Call Path
`remote` (conftest) -> `HranaStub` -> `migrate_remote` -> per-file tests via `remote.requests` / `remote.db` / `remote.stop()`; teardown `HranaStub.stop` -> `clear_verification_cache` -> `reset_for_tests` -> `clear_backend_config_cache`.

### Decision Rules
- Variant ownership is fixed by Expected Behavior: machine identity and interactive-spawn settings remain in distinct file-local variants; shared setup owns server/config/migration and cache/telemetry cleanup. No production decision logic changes.

## Implementation Steps

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-30 — based on codebase analysis:_

1. `scripts/tests/conftest.py` provides one `remote` fixture whose observable contract matches the union of the five self-contained copies (same env, config shape, chdir, cache clears, migration, yielded `HranaStub`), with caches and remote telemetry reset before and after use.
2. Each of the six files resolves `remote` from conftest; `grep -rn "def remote(" scripts/tests` returns only the conftest definition. The libsql file's dependence on its pre-migrating `stub` is resolved without introducing a second stub per test.
3. Apply the named variant ownership above; do not introduce another fixture named `remote`. Cover successful setup/teardown and setup failure with the dedicated fixture tests, preserving existing watermark/warn-once assertions.
4. Verification: `python -m pytest scripts/tests/test_remote_operation_matrix.py scripts/tests/test_remote_hooks.py scripts/tests/test_libsql_backend.py scripts/tests/test_remote_doctor.py scripts/tests/test_remote_ingestion_telemetry.py scripts/tests/test_remote_callers_bug3652.py` passes, then the full `python -m pytest scripts/tests/`.
5. `docs/development/TESTING.md` § Built-in Fixtures gains a one-line entry for the shared `remote` so ENH-3657/ENH-3658 authors find it.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `TestRemoteFixture` to `scripts/tests/test_conftest_cap.py` — drive `remote.__wrapped__` inside a separate monkeypatch context; assert successful teardown and injected setup-failure cleanup (stub stopped, caches/telemetry cleared, cwd/env restored after the context)
- Add a shadow gate under `scripts/tests/` — AST scan for a `pytest.fixture`-decorated `def remote` outside `conftest.py`, with planted-source detector tests; this automates the "no file-local `def remote(`" acceptance criterion
- Keep `HranaStub` and `little_loops.session_store.*` imports inside the conftest fixture body (`test_conftest_cap.py` re-executes conftest as `conftest_under_test`); keep `delenv("LL_HISTORY_DB")` inside the shared body (autouse `_isolate_history_db` sets it first)
- No closed-issue edit or obsolete ENH-3657 STOP-note removal is required; the current active plans already request the shared fixture.

## Impact

- **Priority**: P3 - unblocks ENH-3657/ENH-3658 test work; no user-facing change
- **Effort**: Small - move one fixture, reconcile six copies
- **Risk**: Low - test-only
- **Breaking Change**: No

## Acceptance Criteria

- [ ] A single `remote` fixture lives in `scripts/tests/conftest.py`; the six copies are removed.
- [ ] Reconciled differences (cache/telemetry reset before and after, file-local `LL_MACHINE_ID` / `LL_NON_INTERACTIVE` setup, separate direct-backend `stub` fixture) are covered; all six files still pass unchanged in behavior.
- [ ] No test file retains a file-local `def remote(` that would shadow the conftest fixture.
- [ ] Config/migration setup failure stops the started server and clears process caches/telemetry; successful use and failed setup both restore cwd/env at monkeypatch teardown. Material variant fixtures reuse exactly one stub and only requested tests incur its cost.
- [ ] `python -m pytest scripts/tests/` passes.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-30 — based on codebase analysis:_

- [ ] Tests that rely on warn-once counts (`TestDeadEndpointDegrades` in hooks, `TestBestEffortNeverAborts` in ingestion, `TestStartupUnderRemote` in bug3652) and the `LL_MACHINE_ID` watermark tests (`TestRemoteIngestion`, `TestMachineId`) pass with the shared fixture plus only file-local variant setup.
- [ ] `test_libsql_backend.py` keeps its local `stub`; no test there ends up holding two different stubs.

## Related

- BUG-3652 (landed without hoisting), ENH-3657, ENH-3658, ENH-3682 (blocked by this).

## Status

**Open** | Created: 2026-09-30 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-29_

Prior 100/67 scores and `verify_verdict: VALID` were cleared on 2026-10-04 because the variant/setup-failure contract was amended. Re-run `/ll:confidence-check` before implementation; this review supplies a plan, not passing test evidence.

### Outcome Risk Factors
- Moderate per-site complexity: the shared `remote` body must reconcile five self-contained copies plus the non-self-contained libsql copy (depends on a sibling `stub`); a wrong split of variant setup (`LL_MACHINE_ID`, `LL_NON_INTERACTIVE`, telemetry reset ordering) silently changes warn-once and watermark test results.
- Broad surface across the six test files and ENH-3657/3700/3658/3682 consumers: a leftover file-local `remote` shadows conftest — mitigate with the existing planned AST gate.
- Keep the independent libsql `stub` for direct-backend tests; remote consumers and variants must not request a second server. Cleanup must cover migration/setup failures before yield.

## Session Log
- EPIC-3693 review #3 - 2026-10-05 - six copies and variant/cleanup plan confirmed; backend-independent ENH-3729 removed from blocks, ENH-3728 remains a fixture consumer; no new fixture scope or implementation
- EPIC-3693 pre-implementation review + `/ll:advise` (claude-opus-5-5, user_requested) - 2026-10-04 - variant ownership and setup-failure cleanup pinned; stale scores and cancelled/obsolete obligations removed; implementation not performed
- `/ll:confidence-check` - 2026-09-30T01:48:11 - `6908c6b4-43de-49c6-9aef-d5ca638f2e23.jsonl`
- `/ll:verify-issues` - 2026-09-30T01:46:55 - `a8f35c73-fb24-46d4-8418-8a00777bdfc0.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-09-30T01:45:10 - `98953e2d-0704-4cf3-bbca-372fe552a96f.jsonl`
- `/ll:verify-issues` - 2026-09-30T01:42:47 - `b7cb4c11-1b6b-4e0d-8bbf-cb7896f36873.jsonl`
- `/ll:reconcile-issue` - 2026-09-30T01:41:02 - `27af6ead-a19f-4c2f-9aea-970d32411f57.jsonl`
- `/ll:wire-issue` - 2026-09-30T01:38:22 - `4babb2c7-5543-48eb-ab87-06a8cb535e79.jsonl`
- `/ll:refine-issue` - 2026-09-30T01:34:22 - `06d66ff5-29b0-412a-b67d-fc50c52bb2be.jsonl`
