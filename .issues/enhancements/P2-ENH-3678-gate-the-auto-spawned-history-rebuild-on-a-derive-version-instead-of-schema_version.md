---
id: ENH-3678
type: ENH
title: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:00Z'
blocks:
- ENH-3666
- FEAT-3561
confidence_score: 90
verify_verdict: DIRECTIVE_DRIFT
reconcile_attempted: true
outcome_confidence: 64
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
parent: EPIC-3693
epic: EPIC-3693
---

# ENH-3678: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION

## Summary

Stop the SessionStart hook from spawning a full `backfill_worker --rebuild` on every `SCHEMA_VERSION` bump. Gate the auto-rebuild on a dedicated derive version that changes only when parser or `_REBUILD_TABLES` derivation semantics change, add a single-flight guard, and make the auto-spawn opt-in above a store-size threshold. Split out of ENH-3666 after its 2026-09-29 pre-implementation Opus review.

## Current Behavior

`hooks/session_start.py` (~`:213`) adds `--rebuild` whenever `meta.last_rebuild_version < SCHEMA_VERSION` (currently 58). About 20 bumps since June, several of which (e.g. the `harness_events` and harness-column bumps) change no `_REBUILD_TABLES` derivation, each force a full wipe-and-replay of a multi-GB store. There is no single-flight guard: every SessionStart during a multi-minute rebuild spawns another `--rebuild`. A ~9.6 GB store held the write lock for minutes and dropped concurrent `ll-*` telemetry rows.

## Expected Behavior

- A `REBUILD_DERIVE_VERSION` constant in `session_store/lifecycle.py` plus a `rebuild_derive_version` meta key (inline upsert, not in the `usage_derive_` namespace); the hook compares against it instead of `SCHEMA_VERSION`. `rebuild()` stamps it on success alongside `last_rebuild_version`.
- Migration (no write from the hook): `rebuild_needed()` treats "no `rebuild_derive_version` key **and** `last_rebuild_version >= _LEGACY_REBUILD_FLOOR`" (a literal, 58) as the **frozen legacy derive version** (a literal, initially equal to `REBUILD_DERIVE_VERSION`), never the current constant. A floor, not `== 58`: a `SCHEMA_VERSION` bump that lands first (FEAT-3561's `recommendation_events` is queued) leaves stores rebuilt at 59+ unmarked, and an equality rule would force a multi-GB rebuild on each of them, the exact failure this issue exists to prevent. Compare the frozen legacy value with the current version; a store first opened after a future derive-version bump must rebuild. Missing or `< floor` `last_rebuild_version` rebuilds once. Only a successful `rebuild()` writes `rebuild_derive_version` (alongside `last_rebuild_version`); the SessionStart hook never stamps. The floor rule makes the change order-independent with respect to other schema bumps.
- **Bump-rule guard (2026-09-30 review):** a test pins a fingerprint of `_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS`, `_REBUILD_TABLE_PREDICATES`, the rebuild-table DDL **and the source of the parser/replay functions `rebuild()` calls (the `_backfill_*` family)**, so changing any of them without bumping `REBUILD_DERIVE_VERSION` fails. Parser changes are the most common reason derivation changes, so omitting them leaves the guard blind to the common case. If hashing function source proves too noisy (formatting-only edits), pin a hash of `inspect.getsource` normalized through `ast.dump` and document the residual gap. The bump rule alone is human discipline.
- **Failed-rebuild backoff:** record the last failed attempt and skip auto-spawn for a cooldown so a persistently failing rebuild is not retried on every session start. Keep this state in a **sidecar file next to the rebuild lock** (e.g. `<db>.rebuild.lock` contents or `<db>.rebuild-state.json`), **not in `meta`**: `rebuild()` runs in one `BEGIN IMMEDIATE` transaction that rolls back on failure, so a `meta` write from the failing worker is a second contended write on a store that is already the problem.
- Usage-only derivation changes bump `_USAGE_DERIVE_VERSION` (incremental path), **not** `REBUILD_DERIVE_VERSION`. Bump `REBUILD_DERIVE_VERSION` whenever any non-usage `rebuild()` output or selection changes: parser/replay semantics, `_REBUILD_TABLES` or search-index derivation, corrections, summaries, or prompt-opt enrichment. Document and test the bump rule near the constant.
- A single-flight `fcntl.flock` on a dedicated `<db>.rebuild.lock`. Do not reuse `<db>.usage-refresh.lock`: Stop workers take it with blocking `LOCK_EX` and store throttle state in it. **Lock protocol (2026-09-30 Opus review; unproven, see Delivery Slices):** `rebuild()` runs its whole wipe-and-replay in one `BEGIN IMMEDIATE` transaction, so a concurrent worker's incremental ingest cannot write until it commits (it would hit the 5000 ms busy timeout and fail), and the local ingest watermark is one global wall-clock `last_raw_event_ts`, so an early-exiting worker can lose its transcript. Therefore: ingest takes `LOCK_SH` with a **bounded wait** (poll `LOCK_NB` up to a wait budget, then exit leaving the transcript for the next run rather than blocking indefinitely: blocking `LOCK_SH` for the whole multi-minute replay would pile up one detached blocked worker per SessionStart/Stop); replay takes `LOCK_EX`; after acquiring `LOCK_EX` the worker **re-checks `rebuild_needed()`** and skips the replay if another worker already completed it. A direct `ll-session rebuild` uses `LOCK_NB` on the exclusive lock and reports contention instead of silently claiming success.
- Above a size threshold the hook does not auto-spawn `--rebuild`; it reports "rebuild pending" (SessionStart output / `ll-doctor`) and the user runs `ll-session rebuild` explicitly. Document what a pending rebuild means to readers (derived tables — sessions, tool/skill events, summaries, corrections, search index — keep pre-bump derivation until rebuilt; raw events and usage tables stay current). The threshold is a **module constant (1 GB)**, not a config key, to avoid `config-schema.json` / dataclass / `test_config_schema.py` churn; promote it to config only if a user asks.

## Delivery Slices (2026-09-30 Opus review)

Ship as two slices of this one issue (keeps FEAT-3561/ENH-3666 edges intact); convert to separate issues only if they need independent scheduling.

- **3678a — gate (P2, ships first, unblocks FEAT-3561):** `REBUILD_DERIVE_VERSION` + `rebuild_derive_version` meta key, floor-based `rebuild_needed()`, the SessionStart gate swap, the size gate with the "rebuild pending" notice (`ll-doctor` + SessionStart), the fingerprint test, and docs. No lock-protocol change.
- **3678b — single-flight (after the spike):** the flock protocol, failed-rebuild backoff sidecar, and the direct `ll-session rebuild` contention report. Gated on the spike below; ENH-3666's `blocked_by` moves here (3666 is deferred, so this costs nothing today).

**Interim risk accepted:** until 3678b lands, stores under the 1 GB threshold can still see duplicate concurrent `--rebuild` workers. That is acceptable only if those replays are short, which is unmeasured, so record a replay-duration measurement on a sub-1 GB store in the 3678a PR.

**Hook read path:** the hook's `rebuild_needed()` check must open the store read-only (`connect_readonly`), not `connect()`. `connect()` runs `ensure_db`/migrations; the hook already calls `ensure_db` earlier in `handle`, so this is pre-existing, but the new check should not add a second migration-capable open inside the 5 s hook budget.

## Open Questions (2026-09-30 review)

- **Lock protocol is unproven (tracked task: run `/ll:spike` for 3678b; do not start 3678b until the outcome is recorded here).** The `LOCK_SH` ingest / `LOCK_EX` replay / re-check-under-exclusive protocol is Opus's proposal, not yet validated. Before implementing, prove it with a spike (`/ll:spike`) or a test that holds a real replay open while a second worker ingests: confirm the second worker's ingest completes after the replay commits, the re-check skips a second replay, and the watermark advances only on commit. Also confirm the premise that a hook worker usually carries a single transcript (so exiting early would lose it).
- **Stale stores above the threshold.** Above the 1 GB constant, derived tables stay at pre-bump derivation until a manual `ll-session rebuild`. This is accepted; the pending notice and the documented stale-consequence are the mitigation. Revisit the threshold (or promote it to config) only if users report it.

## Scope Boundaries

- **In scope**: `REBUILD_DERIVE_VERSION` + `rebuild_derive_version` meta key, the SessionStart gate, a single-flight flock for `--rebuild`, the size-threshold opt-in and its pending notice.
- **Out of scope**: restructuring `rebuild()` (ENH-3666), telemetry-writer resilience (ENH-3679), remote stores (never rebuild from a hook).

## Impact

- **Priority**: P2 - stops multi-GB full rebuilds (and their write-lock stalls) on schema bumps that change no derivation
- **Effort**: Small - a version constant, one meta key, a flock, and a size gate in the SessionStart hook
- **Risk**: Medium - a wrong legacy-baseline rule could skip a needed rebuild
- **Breaking Change**: No

## Integration Map

- `scripts/little_loops/hooks/session_start.py` (`handle`, ~`:189-214`) — swap the `SCHEMA_VERSION` comparison for `REBUILD_DERIVE_VERSION`; add the size gate and pending notice; keep remote stores and `LL_NON_INTERACTIVE` suppression.
- `scripts/little_loops/session_store/lifecycle.py` — `REBUILD_DERIVE_VERSION`; `rebuild()` stamps `rebuild_derive_version` alongside `last_rebuild_version` (inline meta upsert; not `usage_derive_*`; no migration or `SCHEMA_VERSION` bump).
- `scripts/little_loops/cli/backfill_worker.py` / `session_store/lifecycle.py` — separate incremental ingest from the replay lock so a contending `--rebuild` worker does not discard its transcript; protect direct rebuild calls too.
- `scripts/little_loops/cli/doctor.py` — surface "rebuild pending".
- Tests: `test_hook_session_start.py::TestSessionStartRebuild` (gate), a two-worker flock test (3678b) (one replay, second re-checks under `LOCK_EX`, both transcripts ingested), a fingerprint test for the bump rule, a failed-rebuild cooldown test, a size-gate test, migration tests (unmarked `>= floor` — including a simulated 59/60 store — reads as the frozen legacy value without a write; `57`/missing rebuild; an unmarked store first opened after a simulated future derive bump rebuilds); `test_session_store_usage_refresh.py` asserts no `usage_derive_%` meta keys after refresh — keep the new key out of that namespace.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-10-02 — based on codebase analysis:_

- **Conventions in force (pattern-finder, 2026-10-02):**
  - Derive versions are module-level *string* tags in `session_store/lifecycle.py`, compared by `!=` (equality, never ordered) — evidence: `_USAGE_DERIVE_VERSION` (`lifecycle.py:1037`), reader `lifecycle.py:1076` and `:1480`. `REBUILD_DERIVE_VERSION` must follow this shape (the Program Design `str` type already matches).
  - Meta keys are written by inline `INSERT ... ON CONFLICT(key) DO UPDATE` inside the same transaction as the derived rows; there is no shared meta-setter — evidence: `_set_usage_derive_checkpoint` (`lifecycle.py:1053`) and the `last_rebuild_version` upsert in `rebuild()` (`lifecycle.py:1554`). The new key's stamp belongs in that same transaction so a rolled-back rebuild leaves it unwritten.
  - `last_rebuild_version` is seeded NULL at schema creation (`schema.py` ~`:505`) and readers coerce missing/NULL to 0 (`session_start.py` `int(_row[0]) if (_row and _row[0]) else 0`); `usage_derive_*` keys are unseeded and read with a default. A new unseeded `rebuild_derive_version` key is the second style; `rebuild_needed()` must treat NULL and absent identically.
  - Read-only opens: `Backend.connect_readonly` (`session_store/backend.py:276`, module wrapper `:358`) is the never-creates/never-migrates opener (`PRAGMA query_only`, raises `HistoryUnavailable`) — evidence: callers `lifecycle.usage_source_freshness` and `doctor._history_db_data`. Two other read-only openers disagree: `queries._connect_readonly` (raw `mode=ro` URI) and `history_reader/_base._connect_readonly` (`ensure=True`, so it **migrates**). The "no second migration-capable open" constraint rules out the latter; `usage_source_freshness` also shows the convention of returning an `unknown` status on any exception rather than raising.
  - Flock sidecars live at `<db>.<name>.lock` beside the DB; the lock file may double as JSON state. Two idioms coexist and are contested: blocking `LOCK_EX` with JSON throttle state (`cli/backfill_worker.py:48`, `_run_usage_trigger`) versus polled `LOCK_EX|LOCK_NB` with timeout (`file_utils.acquire_lock`, callers `advisor.py`, `hooks/pre_done.py`, `hooks/pre_compact_handoff.py`, `hooks/edit_batch_nudge.py`). The bounded-wait `LOCK_SH` in the issue's protocol matches the second idiom's polling shape, but `acquire_lock` is exclusive-only, so shared-mode support is a decision for the implementer, not an existing primitive. Darwin flock contention semantics are documented in `test_file_utils.py` (~`:183-240`) and `.ll/learning-tests/fcntl.md`.
  - Failed-attempt cooldown state is a `.ll/*.lock`-style file with a module-level TTL constant and a `_now()` clock seam — evidence: `UNREACHABLE_TTL_S` (`session_store/remote_telemetry.py:38`, use at `:130`). `*.lock` is already gitignored via `init/writers.py`. No rebuild cooldown exists today.
  - Hook notices: stderr lines accumulate as `[little-loops] ...` strings in `feedback_lines` joined into `LLHookResult.feedback`; stdout is the context payload. A module-constant size threshold has precedent (`_LARGE_CONFIG_THRESHOLD`, `session_start.py:51`). No "pending" notice type exists yet.
  - Doctor checks follow one shape: `_<x>_data() -> dict` (`status`, `severity`, `note`), `_print_<x>_section()`, and an `@register_check` returning `CheckResult`; dicts are added to the JSON payload and print list (`cli/doctor.py` ~`:1742`, `:1860`). `_history_db_data` (~`:503`) and `_schema_drift_data` (~`:678`) are the report-only precedents, and a not-yet-created DB reports `unsupported`/`informational` without creating it.
  - **No convention exists** for a source/DDL fingerprint test: repo-wide search found `inspect.getsource` only in structural/AST tests and `hashlib` only over file bytes. The bump-rule guard is a new test kind; `test_session_store_schema.py::test_schema_version_matches_migrations_length` (plain assert on a hand-maintained int) is the nearest "pin" precedent.

_Added by `/ll:refine-issue` — 2026-10-02 — based on codebase analysis:_

- **Test conventions and traps (pattern-finder, 2026-10-02):**
  - Version-gate tests monkeypatch the constant on `lifecycle` and use a real DB (`test_session_store_incremental_usage.py::test_normalizer_version_change_replays_historical_rows`); rollback tests assert the stamp key is *absent* after a failed run (`test_catchup_failure_rolls_back_rows_and_checkpoint`). The "unmarked store first opened after a future derive bump rebuilds" criterion fits this monkeypatch shape.
  - `test_session_store_lifecycle.py::test_rebuild_updates_last_rebuild_version` (~`:1890`) is the existing stamp assertion; `rebuild_derive_version` needs the same coverage beside it.
  - `test_session_store_schema.py` (~`:909-914`) asserts the exact meta key set on a fresh DB (`last_raw_event_ts`, `last_rebuild_version`). Seeding `rebuild_derive_version` at schema creation would break it — an unseeded key (written only by `rebuild()`) keeps it passing and also matches the "hook never stamps" constraint.
  - `TestSessionStartRebuild` (`test_hook_session_start.py:366`) uses a real DB and a `_FakePopen` recording argv: fresh DB spawns `--rebuild`, a DB after `session_store.rebuild(db)` does not. The size gate and pending notice are testable by the same harness. `test_remote_hooks.py:76` proves remote stores never get `--rebuild` via a stub lacking `last_rebuild_version`; it must keep passing.
  - Lock/cooldown tests inject time by monkeypatching `backfill_worker.time.time_ns` / `.sleep` with a `_Clock` (usage-refresh throttle tests), and the failure path there leaves the lock file empty.
  - Doc surfaces that still state the `SCHEMA_VERSION > last_rebuild_version` trigger: `docs/ARCHITECTURE.md` (~`:772`), `docs/reference/API.md`, the `backfill_worker` module docstring, and the static `_USAGE` banner in `hooks/__init__.py` (new hook intents only; not test-enforced).

_Added by `/ll:refine-issue` — 2026-10-02 — based on codebase analysis:_

- **Bump-rule guard — a hash-pin precedent does exist (gap-analysis pass, 2026-10-02; refines the "no convention exists" note above):** the codebase pins a *hash of a guarded constant* beside a pinned version literal in two separate assertions, each naming the identifiers to edit and saying to change them "in the same commit" — evidence: `TestAllowlistVersionLockstep` (`scripts/tests/test_feat3304_artifact_dashboard.py:704`, `PINNED_HASH` at `:712`) guarding `_SHAREABLE_COLUMNS` / `_SHAREABLE_ALLOWLIST_VERSION` in `session_store/queries.py`. It hashes a `repr` of *data*, not function source, so source-text hashing of the `_backfill_*` family remains precedent-free; the failure-message convention (two asserts: "version changed, pins stale" vs "content changed, version not bumped") transfers either way. The checked-in-snapshot shape (`TestSchemaManifest`) is the second precedent and carries its regeneration command in the docstring.
- **Contested: bump rules are usually comment-only.** `_USAGE_DERIVE_VERSION` (`lifecycle.py:1037`), `pii.CREDENTIAL_SCANNER_VERSION`, and `VERIFIER_COMPAT_VERSION` (`cli/verify_evidence.py`) carry a "Bump when …" comment and no failing test; only the allowlist version is test-enforced. Annotation convention: a comment block directly above the constant opening with "Bump when …" and stating the effect of a mismatch (`lifecycle.py` ~`:1035`, `queries.py` above `_SHAREABLE_COLUMNS`). Type annotation on such constants is inconsistent (`: int` present on two, absent on `_USAGE_DERIVE_VERSION`/`SCHEMA_VERSION`).
- **Pending/stale state is exposed as a three-valued status with a reason code, never a bare bool, in the nearest precedent** — `usage_source_freshness` (`lifecycle.py`) returns `fresh`/`stale`/`unknown` plus a `reason`, maps any read failure to `unknown`, and compares a meta value against a module constant with `!=`. Counter-examples return bool (`learning_tests/gate.py:is_record_stale`, paired with a separate `describe_staleness` string describer). `RefreshResult.needs_rebuild` (`session_store/usage_refresh.py`) documents that no durable rebuild-pending state is stored — pending is derived on demand, which is the same property the issue's hook/doctor "rebuild pending" notice has. The issue's `rebuild_needed() -> bool` signature therefore sits on the minority side of this convention; the hook and doctor both need to distinguish "stale by derive version" from "pending by size gate", which a bare bool cannot carry.
- **Size measurement has no shared helper and no `-wal` precedent.** Each site inlines `db_path.stat().st_size` behind an `exists()` guard on the main DB file only (retention gate `lifecycle.py` ~`:1904`; `recompress()` ~`:958`/`:993`). Units disagree: the retention gate divides by `1024 * 1024`, `recompress` by `1_000_000`. The only existing history-DB size threshold is the config-driven `RetentionConfig.min_db_size_mb: int = 800` (`config/features.py:1519`, default repeated in `from_dict` `:1527`), used solely by the prune gate — unrelated to, and distinct from, the issue's 1 GB module constant; "1 GB" needs a stated unit (GiB vs 10^9 bytes) and a stated decision on whether `-wal` bytes count, since a store mid-write can have a large uncheckpointed WAL.
- **Comparison-site audit:** the hook's inline compare (`hooks/session_start.py:213`, reading `last_rebuild_version` at `:208-212`) is the only reader of `last_rebuild_version` outside tests, so the gate swap is a one-site change. Other `SCHEMA_VERSION` comparisons are not rebuild gating and must stay untouched: `issue_history/workspace_quality.py` (`schema_skew`), `cli/artifact/dashboard.py` (source-version warning), `cli/session.py:_main_migrate`, `cli/doctor.py:_schema_drift_data`. Additional stale-wording site beyond the Wiring lists: the `also_rebuild` docstrings of `backfill_incremental` (`lifecycle.py` ~`:1708`) and `backfill` (~`:1626`) state the old trigger.
- **Ordering fact for FEAT-3561:** `SCHEMA_VERSION == 58` is hard-coded as a literal in ~34 assertions (`test_session_store_schema.py` ×28, `test_session_store_writers.py` ×5, `test_assistant_messages.py` ×1), with no shared constant; FEAT-3561's bump to 59 will touch all of them independent of this issue, and many carry stale names (e.g. `test_schema_version_is_seven`). Not this issue's scope, but a `rebuild_needed` migration test parameterized over 57–60 must set the version through `meta` rather than rely on `SCHEMA_VERSION`.

### Files to Modify (wiring additions)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/__init__.py` — import `REBUILD_DERIVE_VERSION` / `rebuild_needed` from `lifecycle` (top-of-file import block, ~`:96`) **and** add them to `__all__`; `TestPackageReexportSurface::test_all_and_required_private_names_resolve` fails if only one is done. `_REBUILD_TABLE_PREDICATES` is *not* re-exported, so the fingerprint test must import it from `lifecycle` directly [Agent 1/2 finding]
- `scripts/little_loops/cli/session.py` — `main_session`, `command == "rebuild"` arm (`rebuild(args.db, config=config)`, ~`:1016`) is where the 3678b contention report attaches; it has no `HistoryError` handler on this arm today (only `_main_migrate` and the `refresh` arm catch it), so a lock-contention path needs a new exit/return shape. Also `rebuild_parser` help/epilog (`_build_parser`, ~`:270`) and the `refresh` hint `Run ll-session rebuild ...` (~`:840`) if wording changes [Agent 2 finding]
- `scripts/little_loops/session_store/lifecycle.py` — comment/docstring of `rebuild()` ("Updates the `last_rebuild_version` meta key to `SCHEMA_VERSION`") goes stale; update with the new stamp. `rebuild()` is also reached by `backfill(also_rebuild=True)` (~`:1744`) and `backfill_incremental(also_rebuild=True)` (~`:1680`) and by `ll-session backfill --rebuild` / `refresh --rebuild` (`cli/session.py` ~`:819`, `:883`, `:959`, `:982`, `:995`), so a lock placed *inside* `rebuild()` affects all of them while one placed only in `backfill_worker.main` or the `rebuild` CLI arm does not — decide placement explicitly for 3678b [Agent 2 finding]
- `scripts/little_loops/cli/backfill_worker.py` — module docstring (`:11`, "SCHEMA_VERSION has changed since the last rebuild") and `hooks/session_start.py` comment (`:189-190`, "ENH-2581: pass --rebuild only when SCHEMA_VERSION has advanced") both state the old trigger; update with the swap. `main` has no argparse (ad hoc `"--rebuild" in args` + `skip_next` loop, ~`:120-206`), so any new flag is hand-added there [Agent 1/2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/session_store/writers.py` — **the `_backfill_*` family the fingerprint must cover lives here, not in `lifecycle.py`**: `_backfill_tool_events`, `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_skill_events`, `_backfill_usage_events`, `_backfill_prompt_opt`, `_backfill_commit_events`, `_backfill_subagent_runs`, `_backfill_snapshots`, `_backfill_issues_and_snapshots`, `_backfill_loops`, `_backfill_learning_test_events`. `lifecycle.py` holds only `_backfill_sessions` (`:723`), `_backfill_raw_events` (`:800`) and `_compact_sessions` (`:530`). Parser reach is wider still: `session_store/sessions.py` (`iter_events`, per-host dispatch), the host normalizers (`qwen.py`, `gemini.py`, `omp.py`, `CodexNormalizer`), and `mine_corrections_from_messages` / `_iter_events*` in `writers.py` — pick and document the fingerprint boundary [Agent 1/2 finding]
- `scripts/little_loops/session_store/writers.py:_backfill_usage_events` — overlaps the issue's rule that usage-only derivation changes bump `_USAGE_DERIVE_VERSION`, not `REBUILD_DERIVE_VERSION`; hashing it into the rebuild fingerprint would force a rebuild bump for a usage-only change. Decide whether it is excluded or the rule is restated [Agent 2 finding]
- `scripts/little_loops/fsm/continuity.py` — calls `_backfill_messages` / `_backfill_assistant_messages` directly (`:64-65`); reached by a `_backfill_*` source fingerprint but is not a rebuild caller [Agent 1 finding]
- `scripts/little_loops/session_store/usage_refresh.py` — `refresh_raw_events` deletes `usage_derive_*` keys on source replacement and never touches `last_rebuild_version`/`rebuild_derive_version`; imports `_backfill_raw_events` (`:118`); docstring (`:109`) says a failed rebuild "must be retried explicitly" — keep consistent with the cooldown semantics [Agent 1/2 finding]
- `scripts/little_loops/hooks/usage_stop.py` — second spawner of `little_loops.cli.backfill_worker` (`--usage-trigger`, `:40`); shares `backfill_worker.main` and `<db>.usage-refresh.lock`, and its `refresh_usage_source` writes to the DB a rebuild holds `BEGIN IMMEDIATE` on. `--usage-trigger` already rejects `--rebuild`; keep that and do not share the new rebuild lock file with it [Agent 1/2 finding]
- `scripts/little_loops/file_utils.py:acquire_lock` (`:122`) — exclusive-only polled `LOCK_EX|LOCK_NB`; callers `hooks/drift_check.py:88`, `hooks/pre_compact.py:164`. No `LOCK_SH` use exists anywhere in `scripts/little_loops` (searched), so the bounded `LOCK_SH` wait is new primitive code [Agent 1/3 finding]
- `scripts/little_loops/init/writers.py:_GITIGNORE_ENTRIES` (`:106-108`) — `.ll/history.db*` and `.ll/*.lock` already cover `<db>.rebuild.lock` and a `<db>.rebuild-state.json` sidecar for consuming projects; this repo's own `.gitignore` has `.ll/*.lock` and only exact `.ll/history.db{,-shm,-wal}` entries, so a `.rebuild-state.json` sidecar name would match no rule here — prefer the `.lock` suffix or add a `.gitignore` line. `text_utils.py:DEFAULT_UNTRACKED_BY_DESIGN` (`:184`) is pinned to `_GITIGNORE_ENTRIES` by `test_config.py:377` [Agent 1/2 finding]
- `scripts/little_loops/hooks/session_start.py:handle` — the remote guard (`raise RuntimeError("remote store: never rebuild from a hook")`, ~`:202`) must stay ahead of any new read-only open or lock/sidecar creation [Agent 1/2 finding]
- Not coupled (searched, no hits): `skills/`, `commands/`, `agents/`, `loops/`, `.loops/` YAML, `hooks/hooks.json`, host adapters under `hooks/adapters/**` (all route through `hooks/session_start.py:handle`), `config-schema.json`, `hooks/__init__.py:_USAGE` (no new intent) [Agent 1/2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Existing tests that may break / need updating**
- `scripts/tests/test_hook_session_start.py::TestAutomationPruningStayInTurn::test_pruning_gate_injects_stay_in_turn_instruction` (`result.feedback is None`, ~`:603`) — a "rebuild pending" notice must be suppressed on the automation-pruning path or this fails; `TestAmbientAutomationEnvHermeticity::test_suite_passes_with_ambient_ll_automation` re-runs the whole file under `LL_AUTOMATION=1` [Agent 3 finding]
- `scripts/tests/test_hook_session_start.py::TestSessionStartRebuild::test_rebuild_flag_added_on_fresh_db` / `test_rebuild_flag_omitted_when_already_current` (`:389`, `:398`, `rebuild(in_tmp / ".ll" / "history.db")` at `:404`) — update to the derive-version gate (a fresh DB has no `rebuild_derive_version`) [Agent 1 finding]
- `scripts/tests/test_remote_callers_bug3652.py::_CALLER_ALLOWLIST` (`:97`) and `test_allowlist_has_no_stale_entries` — a new doctor data function calling `resolve_history_db()` needs an allowlist entry (existing: `("cli/doctor.py", "_schema_drift_data")`); `rebuild_needed` inside `session_store/` is exempt [Agent 2/3 finding]
- `scripts/tests/test_history_store_chokepoint_gate.py::test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist` — AST-bans `sqlite3.connect(`; `rebuild_needed`, the hook and the doctor check must open via `connect_readonly` [Agent 1/3 finding]
- `scripts/tests/test_enh3184_spawn_site_guard.py` — pins `(spawns, exemptions)` per module (`session_store/lifecycle.py` `(1, 0)`, `cli/doctor.py` `(2, 2)`); any new `subprocess.*` call there fails it (do not spawn the worker from `ll-doctor`) [Agent 3 finding]
- `scripts/tests/test_remote_hooks.py::TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` (`:308-312`) — remote refusal (`except HistoryUnsupported` in `backfill_worker.main`) must happen **before** the `<db>.rebuild.lock` is opened/created; `TestSessionStart::test_does_not_migrate_a_remote_store_on_start` asserts no `begin immediate` reaches the remote stub [Agent 2/3 finding]
- `scripts/tests/test_remote_operation_matrix.py::TestRejectedOperations` (`:68`, `:97`, `:103`) — `lifecycle.rebuild()` / `backfill_incremental(also_rebuild=True)` must still raise `HistoryUnsupported(operation="rebuild")` with no new request, and `rebuild(tmp_path / "scratch.db")` under libsql must still succeed [Agent 2 finding]
- `scripts/tests/test_enh_3166_qwen_normalizer.py::TestBackfillWorkerHost::test_flags_are_position_insensitive` (`:691`) — the only test running the real `--rebuild` argv through `worker_main` over a real DB asserting `sessions == 1`; any lock/re-check wrapper must keep it passing [Agent 3 finding]
- `scripts/tests/test_ll_session.py::TestRebuildSubcommand` (`:1204`; `test_rebuild_parsed_from_argv`, `test_rebuild_invokes_session_store_rebuild`, `test_rebuild_json_flag`) — all patch `little_loops.cli.session.rebuild` with a plain counts dict and assert `messages=3` / `"tools"`; a contention path with a different call shape needs these updated [Agent 2/3 finding]
- `scripts/tests/test_backfill_worker_usage_trigger.py::test_cli_requires_explicit_supported_trigger` — `--usage-trigger` + `--rebuild` must keep returning 1 [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py::test_structurally_matching_over_stamp_is_clamped` (`:2382`, asserts `last_rebuild_version` NULL/absent after clamp) — breaks if `ensure_db`/migrations start seeding or stamping the new key; safe if only `rebuild()` stamps [Agent 3 finding]
- `scripts/tests/test_session_store_schema.py::test_meta_seeds_present` (`:900`) — correction to the Research Findings note above: its query is filtered (`WHERE key IN ('last_raw_event_ts', 'last_rebuild_version')`), so seeding `rebuild_derive_version` would **not** break it; keep the key unseeded anyway because the hook-never-stamps rule and the NULL/absent equivalence already require it [Agent 2 finding]
- `scripts/tests/test_session_store_lifecycle.py::TestRebuild::test_rebuild_updates_last_rebuild_version` (`:1890`, `int(value) == SCHEMA_VERSION`) — keep `last_rebuild_version == SCHEMA_VERSION` stamped (the legacy floor depends on it); add the sibling `rebuild_derive_version` assertion beside it [Agent 3 finding]
- Every test calling `rebuild(db)` now also stamps the new key; none assert its absence (`test_enh3532_codex_rollout_usage.py`, `test_claude_usage_producer.py`, `test_enh3534_host_usage_dispatch.py`, `test_enh3543_usage_coverage.py`, `test_session_discovery.py`, `test_enh_omp_normalizer.py`, `test_enh_3393_gemini_normalizer.py`) — no change expected [Agent 1/2 finding]
- `scripts/tests/test_session_store_schema.py::TestPackageReexportSurface::test_all_and_required_private_names_resolve` — passes only if the new exports are imported and listed in `__all__` together [Agent 2/3 finding]

**New tests to write**
- `lifecycle.rebuild_needed`: unmarked at 57/58/59/60, NULL vs absent key, equal, behind, future bump via `monkeypatch.setattr(lifecycle, "REBUILD_DERIVE_VERSION", ...)`, DB absent, remote refuses, and a byte-identical-before/after read-only check modeled on `test_session_store_backend.py::TestConnectReadonlyStrict::test_existing_store_is_byte_identical_before_and_after` — in `test_session_store_lifecycle.py` near `TestRebuild` [Agent 3 finding]
- Failed-rebuild stamp absence: model on `TestBackfillUsageEvents::test_rebuild_failure_rolls_back_usage_delete` (patches `_backfill_sessions` to raise) and assert `rebuild_derive_version` is absent after the rollback [Agent 3 finding]
- Hook gate + size gate + pending notice: reuse `TestSessionStartRebuild._setup` and the inline `_FakePopen` argv recorder (`monkeypatch.setattr("little_loops.hooks.session_start.subprocess.Popen", ...)`); the notice goes through `feedback_lines` [Agent 3 finding]
- Doctor "rebuild pending": data function + `@register_check` with `severity="informational"` (a `severity == "error"` + `unsupported` result changes exit codes via `_exit_code_for`), absent-DB case (`test_cli_doctor_install_checks.py::TestHistoryDb` style, `_bootstrap_at(db, version)` helper), remote "not applicable" case, and add the new function to `test_remote_doctor.py::TestNoTokenLeaks::test_no_doctor_surface_echoes_the_token`; `test_stray_ll_regression.py::test_ll_doctor_from_subdirectory_creates_no_stray_ll` must keep passing (root-resolved, read-only, creates nothing) [Agent 2/3 finding]
- Fingerprint test: closest precedent is the checked-in-snapshot pattern in `test_session_store_schema.py::TestSchemaManifest::test_schema_manifest_matches_checked_in_file` (docstring carries the regeneration command; snapshot `session_store/schema_manifest.json`) — pin the hash beside it with a regeneration hint. Source-text precedents: `inspect.getsource` in `test_preparation_policy.py::test_policy_never_writes_the_spike_counter`, `ast.parse` in `test_sprint.py`; no existing test hashes Python source [Agent 3 finding]
- 3678b worker tests: `LOCK_SH` bounded ingest vs `LOCK_EX` replay using same-process threads (Darwin separate `open()`s contend per `.ll/learning-tests/fcntl.md`) with `Event`/`Barrier` as in `test_file_utils.py::test_timeout_raises_when_held` and `test_exclusive_acquisition_one_wins`; cooldown sidecar via `_Clock` (`test_backfill_worker_usage_trigger.py`) asserting the sidecar JSON; a `--rebuild` argv test through `backfill_worker.main`; `ll-session rebuild` contention report with the lock held. No `LOCK_SH` test exists today [Agent 3 finding]
- Gap: the hook → `backfill_worker --rebuild` → `rebuild()` chain is only tested in pieces (`TestSessionStartRebuild` argv, `TestBackfillWorkerHost` real run); the 3678a replay-duration measurement belongs with a real-DB run, not a new unit test [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/ARCHITECTURE.md` — second site beyond `~:772`: the v19 schema-table row (`raw_events`, ~`:695`) says "a new `last_rebuild_version` key gates the `SessionStart` hook's opt-in-on-migration `--rebuild` pass"; and the `ll-doctor --json` payload key list (~`:922`) if the doctor surface adds a key [Agent 2 finding]
- `docs/reference/API.md` — `rebuild()` prose (~`:10158`, "Updates the `last_rebuild_version` meta key to `SCHEMA_VERSION`"), plus one-line `rebuild` descriptions (~`:5104`, `:9959`) and the reprice-on-rebuild note (~`:12637`); document `rebuild_needed()` / `REBUILD_DERIVE_VERSION` if exported [Agent 2 finding]
- `docs/reference/CLI.md` — `ll-doctor` "always runs 7 default install-surface checks" count and name list (~`:494`) and `--json` key list (~`:497`) if a check is added; `ll-session rebuild` table row (~`:4397`), `rebuild` flags block (~`:4514`) for the contention report [Agent 2 finding]
- `docs/reference/HOST_COMPATIBILITY.md` (~`:885`) and `docs/codex/usage.md` (~`:173`) — `ll-doctor` install-surface check lists; `test_wiring_guides_and_meta.py` pins only the token `install-surface`, not the list [Agent 2 finding]
- `docs/guides/BUILTIN_HOOKS_GUIDE.md` — SessionStart section (`:52` table row, `:153` worker description, `:157` "You see" — add the `[little-loops] ... rebuild pending` line) [Agent 2 finding]
- `docs/guides/HISTORY_SESSION_GUIDE.md` — "rebuild is safe and repeatable" callout (~`:190-204`) and the `--json` note (~`:226`) in addition to the pending-rebuild explanation [Agent 2 finding]
- All of the above fall under the docs-audience gate (`test_docs_audience_gate.py`): end-user shape, no `scripts/tests/` or `scripts/little_loops/` paths [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- No `config-schema.json` / `test_config_schema.py` change needed with the 1 GB module constant; `scripts/little_loops/init/writers.py:_GITIGNORE_ENTRIES` already covers `.lock` sidecars (see Dependent Files for the `.rebuild-state.json` naming caveat) [Agent 2 finding]

## Implementation Steps

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/little_loops/session_store/__init__.py` — import and `__all__`-list `REBUILD_DERIVE_VERSION` / `rebuild_needed` together
- Define the fingerprint boundary over `session_store/writers.py` `_backfill_*` (plus `lifecycle._backfill_sessions`/`_compact_sessions`) and decide the `_backfill_usage_events` / `_USAGE_DERIVE_VERSION` overlap before writing the test
- Inject at `cli/session.py:main_session` `rebuild` arm — add the contention path with an explicit exit shape (no `HistoryError` handler exists on this arm); update `TestRebuildSubcommand`
- Keep the remote refusal in `backfill_worker.main` and `session_start.handle` ahead of any lock/sidecar creation or read-only open
- Suppress the pending notice on the automation-pruning path; update `TestAutomationPruningStayInTurn` only if the suppression is deliberately not applied
- Open through `connect_readonly` only in `rebuild_needed`, the hook and the doctor check (chokepoint gate); allowlist a new doctor `resolve_history_db()` site in `_CALLER_ALLOWLIST`
- Add the doctor "rebuild pending" check (`_<x>_data` / `_print_<x>_section` / `@register_check`, `severity="informational"`) and its payload key in `_print_report`; extend `TestNoTokenLeaks`
- Update stale trigger wording in `hooks/session_start.py` (`:189-190`), `backfill_worker.py` docstring (`:11`), `lifecycle.rebuild` docstring, `docs/ARCHITECTURE.md` (`~:695`, `~:772`, `~:922`), `docs/reference/API.md` (`~:10158`), `docs/reference/CLI.md` (`~:494`, `~:4514`), `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`
- 3678b: decide lock placement (inside `rebuild()` vs only in `backfill_worker.main`/CLI arm) given `backfill(also_rebuild=)`, `backfill_incremental(also_rebuild=)`, `refresh --rebuild` all reach `rebuild()`; name the sidecar with a `.lock` suffix (or add a `.gitignore` line) so it is ignored in this repo

## Program Design

### Types

- `REBUILD_DERIVE_VERSION: str` constant in `little_loops.session_store.lifecycle`; `rebuild_derive_version` `meta` key (inline upsert, string value).

### Signatures

- `rebuild_needed(db: Path | str) -> bool` — opens the store read-only; True when `rebuild_derive_version != REBUILD_DERIVE_VERSION` after applying the implicit frozen-legacy rule for an unmarked `>= _LEGACY_REBUILD_FLOOR` store; version identifiers are compared for equality, not ordered as strings. Replaces the inline `SCHEMA_VERSION` comparison in `hooks/session_start.py`.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → `rebuild_needed` → size gate → detached `little_loops.cli.backfill_worker` `--rebuild` → incremental ingest → dedicated nonblocking replay lock → `rebuild` (or a named pending/contended outcome).

## Acceptance Criteria

- [ ] An unmarked store at `last_rebuild_version >= 58` (tested at 58, 59 and 60) is read as the fixed legacy derive version (no write); `57`/missing rebuilds once. When the current derive version is subsequently bumped, that same unmarked legacy store rebuilds rather than being treated as current.
- [ ] A `SCHEMA_VERSION` bump that does not change derivation does not trigger a rebuild; a `REBUILD_DERIVE_VERSION` bump does.
- [ ] Two concurrent `--rebuild` workers perform exactly one replay (the second re-checks `rebuild_needed()` under the exclusive lock and skips); each worker's transcript is ingested (the second waits under `LOCK_SH`/`LOCK_EX` rather than exiting). A direct `ll-session rebuild` reports contention. Stop usage-refresh workers use their existing lock without sharing the rebuild lock file.
- [ ] The lock-protocol open question is resolved by a spike or test before **3678b** starts, and the outcome is recorded here. Ingest workers use a bounded `LOCK_SH` wait (no unbounded pile-up of blocked workers).
- [ ] The SessionStart hook writes no meta stamp; `rebuild_derive_version` is written only by a successful `rebuild()`. A fingerprint test fails when `_REBUILD_TABLES`/`_REBUILD_SEARCH_KINDS`/predicates/DDL/`_backfill_*` parser source change without a `REBUILD_DERIVE_VERSION` bump.
- [ ] A failed rebuild is not retried until its cooldown expires (state in the lock sidecar, not `meta`); the "rebuild pending" notice explains the stale-derived-tables consequence.
- [ ] Above the size threshold the hook spawns no `--rebuild` and surfaces a pending notice.
- [ ] `test_hook_session_start.py::TestSessionStartRebuild` updated to the new gate; remote stores still never rebuild from a hook.
- [ ] Docs (`HISTORY_SESSION_GUIDE.md`, `CLI.md`, `API.md`, `ARCHITECTURE.md` `last_rebuild_version` wording) updated in end-user shape.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-30_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 64/100 → MODERATE

### Concerns
- Scope is really 3678a (gate) plus 3678b (lock protocol); readiness reflects 3678a. 3678b is explicitly gated on an unrun spike, so do not start it from this score.
- `rebuild_needed()` does not exist yet (the hook currently inlines the `SCHEMA_VERSION` comparison at `session_start.py:203-214`), and `doctor.py` has no rebuild surface. Both are new code, not swaps.
- The "hook worker usually carries a single transcript" premise behind the bounded `LOCK_SH` wait is unverified.

### Outcome Risk Factors
- Moderate per-site complexity: the flock protocol (`LOCK_SH` ingest, `LOCK_EX` replay, re-check under the exclusive lock) spans `backfill_worker.py` and `lifecycle.py` with shared watermark state, and is unproven.
- No existing test harness for a concurrent two-worker replay; the 3678b tests must be built from scratch.
- The fingerprint test over `_backfill_*` source may be noisy (formatting-only edits), with an `ast.dump` fallback already noted.

## Related

- ENH-3666 (structural fix; now blocked by this issue), ENH-3679 (telemetry writer resilience), FEAT-3561 (its `SCHEMA_VERSION` bump is why the legacy rule is a floor).

## Status

**Open** | Created: 2026-09-30 | Priority: P2


## Session Log
- `/ll:verify-issues` - 2026-10-02T17:39:34 - `c4987968-ecb7-44fe-a16e-56254b7c993f.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-02T17:37:27 - `9416e528-98f1-4f80-9820-ac6e5fed4e1c.jsonl`
- `/ll:verify-issues` - 2026-10-02T17:32:28 - `b0f899a2-5d6e-4053-9fcb-6bd7647cde0c.jsonl`
- `/ll:reconcile-issue` - 2026-10-02T17:30:38 - `6ecc6d6a-67ab-4f16-bac7-1454c735549d.jsonl`
- `/ll:wire-issue` - 2026-10-02T17:27:57 - `f1065705-d813-48c2-b6b4-f468cf2be46f.jsonl`
- `/ll:refine-issue` - 2026-10-02T17:18:44 - `17172743-fe56-4b5b-955c-a50b6984c2e7.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:23 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
