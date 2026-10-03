---
id: ENH-3678
type: ENH
title: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T00:31:00Z'
reconcile_attempted: true
blocks:
- FEAT-3561
- ENH-3698
- ENH-3699
relates_to:
- EPIC-3693
- ENH-3698
- ENH-3699
confidence_score: 95
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3678: Gate the auto-spawned history rebuild on a derive version instead of SCHEMA_VERSION

> **Split 2026-10-02 (Opus review of EPIC-3693's children).** This issue is now **the gate only** (3678a). The size threshold, "rebuild pending" notice and `ll-doctor` check moved to **ENH-3698** (3678b); the single-flight flock, failed-rebuild cooldown and `ll-session rebuild` contention report moved to **ENH-3699** (3678c, deferred, spike-gated). It was detached from EPIC-3693: it is a local-store fix, and under `parallel.epic_branches` a P2 child inside a P4 remote-work epic would sit on the epic branch and keep FEAT-3561 blocked. **Re-run `/ll:confidence-check`**: the earlier scores (90/64) described the pre-split scope and were cleared.

## Summary

Stop the SessionStart hook from spawning a full `backfill_worker --rebuild` on every `SCHEMA_VERSION` bump. Gate the auto-rebuild on a dedicated `REBUILD_DERIVE_VERSION` that changes only when parser or `_REBUILD_TABLES` derivation semantics change, expose the decision as `rebuild_needed(db) -> RebuildState`, and pin the bump rule with a checked-in fingerprint test. **FEAT-3561 is the unblock target** (its `SCHEMA_VERSION` bump to 59 must not trigger a multi-GB rebuild).

**Ordering caveat:** until ENH-3698 (size gate) lands, a `REBUILD_DERIVE_VERSION` bump still triggers a full multi-GB rebuild on every store. Do not bump the constant before ENH-3698 lands; this is stated in a comment on the constant.

## Current Behavior

`hooks/session_start.py` (`handle`, ~`:189-214`) adds `--rebuild` whenever `meta.last_rebuild_version < SCHEMA_VERSION` (currently 58; the only reader of `last_rebuild_version` outside tests, so the swap is a one-site change). About 20 bumps since June, several of which (e.g. the `harness_events` and harness-column bumps) change no `_REBUILD_TABLES` derivation, each force a full wipe-and-replay of a multi-GB store. A ~9.6 GB store held the write lock for minutes and dropped concurrent `ll-*` telemetry rows. `rebuild_needed()` does not exist; the hook inlines the comparison and `read`s `last_rebuild_version` coercing missing/NULL to 0.

## Expected Behavior

- **Constant.** `REBUILD_DERIVE_VERSION: str` in `session_store/lifecycle.py`, a module-level string tag compared with `!=` (equality, never ordered), like `_USAGE_DERIVE_VERSION` (`lifecycle.py:~1037`). A comment block directly above it opens with "Bump when ..." and states the effect of a mismatch (every store rebuilds once), and adds **"do not bump before ENH-3698 (size gate) lands"**. Bump it whenever any non-usage `rebuild()` output or selection changes: parser/replay semantics, `_REBUILD_TABLES` or search-index derivation, corrections, summaries, or prompt-opt enrichment. Usage-only derivation changes bump `_USAGE_DERIVE_VERSION` (incremental path), never this constant.
- **Meta key.** `rebuild_derive_version`, **unseeded** (not created at schema creation and not in the `usage_derive_` namespace). `rebuild()` stamps it with an inline `INSERT ... ON CONFLICT(key) DO UPDATE` **inside the same transaction** as the derived rows and the existing `last_rebuild_version` upsert (`lifecycle.py:~1554`), so a rolled-back rebuild leaves it unwritten. `last_rebuild_version == SCHEMA_VERSION` keeps being stamped (the legacy floor depends on it). The SessionStart hook and `ensure_db`/migrations never stamp it. NULL and absent are treated identically.
- **Frozen-legacy floor rule (migration, no hook write).** `rebuild_needed()` treats "no `rebuild_derive_version` **and** `last_rebuild_version >= _LEGACY_REBUILD_FLOOR`" (a literal, 58) as the **frozen legacy derive version** (its own string literal `_FROZEN_LEGACY_DERIVE_VERSION`, initially equal in value to `REBUILD_DERIVE_VERSION` but **never written as an alias** `= REBUILD_DERIVE_VERSION`: an alias would move with every bump and silently defeat the "a future bump makes an unmarked legacy store stale" criterion), never the current constant. A floor rather than `== 58`: a `SCHEMA_VERSION` bump that lands first (FEAT-3561's `recommendation_events`, queued) leaves stores rebuilt at 59+ unmarked, and an equality rule would force a multi-GB rebuild on each. A store first opened after a future derive bump must rebuild (frozen value != new constant). Missing or `< floor` `last_rebuild_version` rebuilds once.
- **`rebuild_needed(db: Path | str) -> RebuildState`.** `RebuildState` is a frozen dataclass `RebuildState(status: Literal["current", "stale", "unknown"], reason: str)`. The status vocabulary matches the `usage_source_freshness` precedent (`fresh`/`stale`/`unknown`); `reason` is one of a closed set of codes: `derive_match`, `legacy_floor` (both `current`), `derive_mismatch`, `legacy_below_floor`, `no_stamp`, `db_missing` (all `stale`), `read_error`, `remote` (both `unknown`). Tests assert the reason codes as well as the status. (Decided 2026-10-02 review: a bare `Literal` cannot carry the reason, and a str enum would need a second field anyway.) `unknown` means a read failure (any exception opening or reading the store); the **hook does not spawn on `unknown`** (fail safe). A missing DB or a fresh DB with no stamp is `stale`. **Busy timeout (2026-10-02 Opus review):** `connect_readonly` calls `sqlite3.connect` with sqlite's default `timeout=5.0`, equal to the hook's whole 5 s budget (`hooks/hooks.json`), so a contended open could get the hook killed before `Popen` runs and even the incremental backfill would not spawn. Add a `timeout: float = 5.0` keyword to `Backend.connect_readonly` (the chokepoint gate forbids a raw `sqlite3.connect`); `rebuild_needed` passes ~0.5 s and a lock timeout maps to `unknown`/`read_error`. The hook logs the reason code whenever it declines to spawn on `unknown`, and ENH-3698's doctor check reports `unknown`. It opens the store with `Backend.connect_readonly` (`session_store/backend.py:~276`, never creates/migrates, `PRAGMA query_only`), **not** `connect()` and **not** `history_reader._base._connect_readonly` (which passes `ensure=True` and migrates); the hook already calls `ensure_db` earlier in `handle`, so no second migration-capable open is added inside the 5 s hook budget. A remote store raises `HistoryUnsupported` (mapped to `unknown`); the hook's remote guard (`raise RuntimeError("remote store: never rebuild from a hook")`, ~`:202`) stays **ahead** of any read-only open. ENH-3698 later combines `stale` with the size check to decide "pending"; "pending" is **not** a state of `rebuild_needed`.
- **Hook swap.** `handle` replaces the inline `SCHEMA_VERSION` comparison with `rebuild_needed()`; it adds `--rebuild` only on `stale`. Keep `LL_NON_INTERACTIVE` suppression and the remote guard unchanged.
- **Bump-rule guard (fingerprint test).** A checked-in snapshot test, modeled on `test_session_store_schema.py::TestSchemaManifest::test_schema_manifest_matches_checked_in_file` (the docstring carries the regeneration command), pins a fingerprint of: `_REBUILD_TABLES`, `_REBUILD_SEARCH_KINDS`, `_REBUILD_TABLE_PREDICATES`; the DDL of the **non-usage** rebuild tables (`usage_events` DDL and its entries in the constants are **excluded**: nearly every recent `ALTER TABLE` targets `usage_events`, which is in `_REBUILD_TABLES`, so hashing it would force a `REBUILD_DERIVE_VERSION` bump, and a multi-GB rebuild, for usage-only migrations that `_USAGE_DERIVE_VERSION` already governs); and the source of **every module-level function in `writers.py`/`lifecycle.py` reachable from `rebuild()`**.
  - **Function set = a walk from `rebuild`, not a hand-written `_backfill_*` list** (2026-10-02 Opus review). Start at `rebuild` itself, walk each body's AST for calls to module-level functions defined in `writers.py`/`lifecycle.py`, add them, and repeat to a fixed point. The walk includes `rebuild()`'s own body (cursor ordering, call order), `_backfill_sessions`, `_backfill_tool_events`, `_backfill_messages`, `_backfill_assistant_messages`, `_backfill_skill_events`, `_backfill_prompt_opt`, `_compact_sessions`, the summary helpers (`_summarize_block`/`_call_llm_for_summary`, so a summary-prompt edit trips the test, which matches the bump rule's "summaries"; say so in the failure message) and `mine_corrections_from_messages` (`writers.py`).
  - **Excluded subtrees:** `_backfill_usage_events` and `_set_usage_derive_checkpoint` (governed by `_USAGE_DERIVE_VERSION`; hashing them would force a rebuild bump for a usage-only change). Helpers reachable only from them are excluded; a helper shared with a non-usage path is included. **`backfill()`-only functions are out of the set** (`_backfill_raw_events`, `_backfill_commit_events`, `_backfill_subagent_runs`, `_backfill_snapshots`, `_backfill_issues_and_snapshots`, `_backfill_loops`, `_backfill_learning_test_events`): `rebuild()` never calls them and they write tables a rebuild does not touch, so hashing them would force a multi-GB derive bump for changes a rebuild cannot apply, the harm this issue exists to prevent.
  - **Snapshot contents:** the digest **and the resolved function-name set**, so a new helper entering the walk shows up as a diff; the test docstring lists the set. Residual gap, stated in the docstring: `sessions.py` `iter_events` dispatch and the host normalizers (`qwen.py`, `gemini.py`, `omp.py`, `CodexNormalizer`) are not covered.
  - **Normalization must be interpreter-independent.** `ast.dump` is not (verified 2026-10-02: one two-line function hashes differently on 3.11.14, 3.12.10 and 3.13.12; CI runs 3.11 on push only while the dev `python` is 3.12, so a locally generated snapshot would pass here and break `main` on both CI legs after the merge). `ast.unparse` also varies across patch releases and `tokenize` differs between 3.11 and 3.12+ (PEP 701 f-strings). Recipe, measured stable on 3.10.17 through 3.13.12: per function, take the source slice from `lineno`/`end_lineno`, delete the docstring line ranges (located via the AST), blank COMMENT tokens by position, remove all whitespace, and hash. **Rule: the AST is used for discovery (callees, docstring ranges) only, never as the hashed representation.** Comment-only, docstring-only and whitespace-only edits do not trip the test; a ruff reflow that adds or removes a trailing comma or parenthesis does (accepted false positive). Verify the snapshot on both 3.11 and 3.12 before landing.
  - **Failure message** uses the two-assert convention of `TestAllowlistVersionLockstep` (`test_feat3304_artifact_dashboard.py:~704`): "version changed, snapshot stale" vs "content changed, `REBUILD_DERIVE_VERSION` not bumped", each naming the identifiers to edit and the regeneration command. Honest limit: regenerating the snapshot by reflex defeats it; it is a discipline aid, not a hard guarantee.
- **Ordering lockstep (enforces the ENH-3698 dependency).** Until ENH-3698 lands, a test asserts `REBUILD_DERIVE_VERSION == _FROZEN_LEGACY_DERIVE_VERSION` with the message "do not bump REBUILD_DERIVE_VERSION before ENH-3698 (size gate) lands; ENH-3698 deletes this test". **ENH-3698's Implementation Steps must include deleting it** (follow-up on that issue). Combined with the fingerprint test, a derivation change made before ENH-3698 forces a deliberate "regenerate the snapshot without a bump" decision rather than an accidental bump.

## Motivation

Every `SCHEMA_VERSION` bump is a full multi-GB wipe-and-replay today, even when no derivation changed, which stalls telemetry writers and every concurrent `ll-*` command. FEAT-3561 is queued to bump `SCHEMA_VERSION` to 59 and is blocked until this gate exists.

## Scope Boundaries

- **In scope**: `REBUILD_DERIVE_VERSION` + `rebuild_derive_version` meta key, `rebuild_needed()`/`RebuildState`, the SessionStart gate swap, the fingerprint test, the package re-export, stale trigger-wording docs/docstrings.
- **Out of scope**: the size threshold, pending notice and doctor check (ENH-3698); the single-flight lock, cooldown and contention report (ENH-3699); a worker-side stamp re-check under `BEGIN IMMEDIATE` (during a multi-minute WAL rebuild concurrent sessions still read `stale` and may each spawn a redundant `--rebuild`; pre-existing behavior, deferred to ENH-3699 alongside the single-flight lock, 2026-10-02 review); restructuring `rebuild()` (ENH-3666); telemetry-writer resilience (ENH-3679); remote stores (never rebuild from a hook). `usage_stop.py` (`--usage-trigger`, already rejects `--rebuild`) and `usage_refresh.py` are untouched.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store/lifecycle.py` — `REBUILD_DERIVE_VERSION`, `_LEGACY_REBUILD_FLOOR`, frozen legacy literal, `RebuildState`, `rebuild_needed()`; `rebuild()` stamps `rebuild_derive_version` in its transaction (no migration, no `SCHEMA_VERSION` bump); update the `rebuild()` docstring ("Updates the `last_rebuild_version` meta key to `SCHEMA_VERSION`") and the `also_rebuild` docstrings of `backfill` (~`:1626`) and `backfill_incremental` (~`:1708`), which state the old trigger.
- `scripts/little_loops/session_store/backend.py` — add `timeout: float = 5.0` to `Backend.connect_readonly` (protocol at ~`:224`, `SqliteBackend` at ~`:276`, **and the module-level `connect_readonly()` wrapper at ~`:358`**, which `rebuild_needed` would call and which needs a pass-through), passed to `sqlite3.connect(..., timeout=...)`.
- `scripts/little_loops/session_store/libsql.py` — `LibsqlBackend.connect_readonly` (~`:273`) must accept and ignore the `timeout` keyword so it satisfies the updated `Backend` protocol (remote stores never reach `rebuild_needed`'s read-only open; the hook's remote guard comes first).
- `scripts/little_loops/session_store/__init__.py` — import `REBUILD_DERIVE_VERSION`, `RebuildState` and `rebuild_needed` from `lifecycle` (import block ~`:96`) **and** add them to `__all__`; `TestPackageReexportSurface::test_all_and_required_private_names_resolve` fails if only one is done. `_REBUILD_TABLE_PREDICATES` is not re-exported, so the fingerprint test imports it from `lifecycle` directly.
- `scripts/little_loops/hooks/session_start.py` (`handle`, ~`:189-214`) — swap the comparison; update the ENH-2581 comment (`:189-190`, "pass --rebuild only when SCHEMA_VERSION has advanced").
- `scripts/little_loops/cli/backfill_worker.py` — module docstring (`:11`, "SCHEMA_VERSION has changed since the last rebuild"); no logic change.
- Docs stating the old trigger: `docs/ARCHITECTURE.md` (~`:695` v19 schema-table row, ~`:772`), `docs/reference/API.md` (`rebuild()` prose ~`:10158`, one-line descriptions ~`:5104`/`:9959`, and a `rebuild_needed()`/`REBUILD_DERIVE_VERSION` entry), `docs/guides/HISTORY_SESSION_GUIDE.md` ("rebuild is safe and repeatable" callout ~`:190-204`). End-user shape (`test_docs_audience_gate.py`): no `scripts/tests/` or `scripts/little_loops/` paths.

### Other `SCHEMA_VERSION` comparisons (must stay untouched)

`issue_history/workspace_quality.py` (`schema_skew`), `cli/artifact/dashboard.py` (source-version warning), `cli/session.py:_main_migrate`, `cli/doctor.py:_schema_drift_data` are not rebuild gating. `hooks/__init__.py:_USAGE` needs no change (no new hook intent). Not coupled: `skills/`, `commands/`, `agents/`, `loops/`, `hooks/hooks.json`, host adapters under `hooks/adapters/**` (all route through `session_start.handle`), `config-schema.json`.

### Tests

Existing tests to update or keep green:

- `test_hook_session_start.py::TestSessionStartRebuild::test_rebuild_flag_added_on_fresh_db` / `test_rebuild_flag_omitted_when_already_current` (`:389`, `:398`; `rebuild(...)` at `:404`) — move to the derive-version gate (a fresh DB has no `rebuild_derive_version`). Uses a real DB and a `_FakePopen` argv recorder. `test_remote_hooks.py:76` (remote stores never get `--rebuild`, via a stub lacking `last_rebuild_version`) and `test_remote_hooks.py::TestBackfillWorker::test_a_rebuild_is_refused_with_a_message_and_no_traceback` must keep passing.
- `test_session_store_lifecycle.py::TestRebuild::test_rebuild_updates_last_rebuild_version` (`~:1890`, `int(value) == SCHEMA_VERSION`) — keep; add the sibling `rebuild_derive_version` assertion beside it.
- `test_session_store_schema.py`: `test_meta_seeds_present` (`:900`, filtered query, would tolerate seeding, but keep the key unseeded) and `test_structurally_matching_over_stamp_is_clamped` (`:2382`, asserts `last_rebuild_version` NULL/absent after clamp; breaks if migrations start stamping the new key).
- `test_history_store_chokepoint_gate.py::test_no_raw_sqlite_connect_outside_chokepoint_and_allowlist` — `rebuild_needed` and the hook must open via `connect_readonly`, no raw `sqlite3.connect(`.
- `test_remote_operation_matrix.py::TestRejectedOperations` — `rebuild()` / `backfill_incremental(also_rebuild=True)` still raise `HistoryUnsupported(operation="rebuild")` with no new request; `rebuild(tmp_path / "scratch.db")` under libsql still succeeds.
- `test_enh_3166_qwen_normalizer.py::TestBackfillWorkerHost::test_flags_are_position_insensitive`, `test_session_store_usage_refresh.py` (asserts no `usage_derive_%` meta keys after refresh — keep the new key out of that namespace), `test_backfill_worker_usage_trigger.py::test_cli_requires_explicit_supported_trigger`.
- Every test calling `rebuild(db)` now also stamps the new key; none assert its absence — no change expected.

New tests (version-gate tests monkeypatch the constant on `lifecycle` and use a real DB, as in `test_session_store_incremental_usage.py::test_normalizer_version_change_replays_historical_rows`):

- `rebuild_needed` in `test_session_store_lifecycle.py` near `TestRebuild`: unmarked at 57/58/59/60 (set via `meta`, not `SCHEMA_VERSION`; 58-60 read as the frozen legacy value without a write, 57/missing rebuild); NULL vs absent key; equal; behind; future bump via `monkeypatch.setattr(lifecycle, "REBUILD_DERIVE_VERSION", ...)` (an unmarked legacy store then reads `stale`); DB absent -> `stale`; read failure -> `unknown`; remote -> `unknown`; byte-identical-before/after read-only check modeled on `test_session_store_backend.py::TestConnectReadonlyStrict::test_existing_store_is_byte_identical_before_and_after`.
- Failed-rebuild stamp absence, modeled on `TestBackfillUsageEvents::test_rebuild_failure_rolls_back_usage_delete`: `rebuild_derive_version` absent after rollback.
- Hook: `unknown` does not spawn; `stale` spawns; reuse `TestSessionStartRebuild._setup`.
- Fingerprint snapshot test (see Expected Behavior), snapshot file checked in beside `schema_manifest.json`; it stores the digest plus the resolved function-name set. Add a test that the normalizer is stable under comment/docstring/whitespace edits and changes on a code edit, run on the 3.11 and 3.12 interpreters available locally.
- Ordering lockstep test (`REBUILD_DERIVE_VERSION == _FROZEN_LEGACY_DERIVE_VERSION`; deleted by ENH-3698).
- `connect_readonly(timeout=...)`: a locked store (held write lock) maps to `unknown`/`read_error` within the short timeout; the default stays 5.0 for other callers.
- `SCHEMA_VERSION == 58` is hard-coded in ~34 assertions (`test_session_store_schema.py` ×28, `test_session_store_writers.py` ×5, `test_assistant_messages.py` ×1); FEAT-3561's bump to 59 touches them independent of this issue and is out of scope here.

## Program Design

### Types

- `REBUILD_DERIVE_VERSION: str` in `little_loops.session_store.lifecycle`; `rebuild_derive_version` `meta` key (inline upsert, string value, unseeded).
- `RebuildState` — frozen dataclass `{status: Literal["current", "stale", "unknown"], reason: str}` with the closed reason-code set in Expected Behavior; never a bare bool.

### Signatures

- `rebuild_needed(db: Path | str) -> RebuildState` — opens the store via `connect_readonly`; `stale` when the (implicit frozen-legacy-resolved) stamped version `!=` `REBUILD_DERIVE_VERSION`, or the DB/stamp is missing; `unknown` on any read failure or remote store. Identifiers compared for equality, not ordered.

### Call Path

- `handle` (`little_loops.hooks.session_start`) → remote guard → `rebuild_needed` → on `stale` only, detached `little_loops.cli.backfill_worker --rebuild` → `rebuild()` stamps `last_rebuild_version` and `rebuild_derive_version` in one transaction.

## Implementation Steps

1. Add `REBUILD_DERIVE_VERSION` (with the "Bump when ... do not bump before ENH-3698 lands" comment), `_LEGACY_REBUILD_FLOOR`, the frozen legacy literal, `RebuildState` and `rebuild_needed()`; stamp the key in `rebuild()`'s transaction. Add the `timeout` keyword to `Backend.connect_readonly`.
2. Export from `session_store/__init__.py` (import and `__all__` together).
3. Swap the hook comparison; keep the remote guard first; update the stale comment/docstrings.
4. Update `TestSessionStartRebuild`; add the `rebuild_needed`, stamp-absence, hook `unknown`/`stale` and migration tests.
5. Write the fingerprint snapshot test (walk from `rebuild`, interpreter-independent normalization, digest + function-name set) and the ordering lockstep test; check in the snapshot with its regeneration command and verify it on both 3.11 and 3.12.
6. Update docs; run `python -m pytest scripts/tests/`, `ruff check scripts/`, `python -m mypy scripts/little_loops/` (scope `ruff format` to changed files).

## Impact

- **Priority**: P2 - stops multi-GB full rebuilds (and their write-lock stalls) on schema bumps that change no derivation; unblocks FEAT-3561
- **Effort**: Medium - a version constant, one meta key, a read-only state function, a hook swap, a new snapshot-test kind, and docs in several files
- **Risk**: Medium - a wrong legacy-baseline rule could skip a needed rebuild; a derive bump before ENH-3698 still rebuilds every store
- **Breaking Change**: No

## Acceptance Criteria

- [ ] An unmarked store at `last_rebuild_version >= 58` (tested at 58, 59 and 60) is read as the frozen legacy derive version with no write; `57`/missing rebuilds once. When the current derive version is subsequently bumped, that same unmarked legacy store reads `stale` rather than current.
- [ ] A `SCHEMA_VERSION` bump that does not change derivation does not trigger a rebuild; a `REBUILD_DERIVE_VERSION` bump does.
- [ ] `rebuild_needed()` returns a `RebuildState(status, reason)` dataclass with the closed reason-code set; a read failure or remote store returns `unknown` and the hook spawns nothing; a missing DB/stamp is `stale`; it opens via `connect_readonly` and leaves the store byte-identical.
- [ ] The SessionStart hook writes no meta stamp; `rebuild_derive_version` is written only by a successful `rebuild()`, in its transaction (absent after a rolled-back rebuild); the key is unseeded and outside `usage_derive_*`.
- [ ] The fingerprint snapshot test fails (two distinct messages) when `_REBUILD_TABLES`/`_REBUILD_SEARCH_KINDS`/predicates/non-usage DDL or any function reachable from `rebuild()` (excluding the `_backfill_usage_events`/`_set_usage_derive_checkpoint` subtrees) changes without a `REBUILD_DERIVE_VERSION` bump or snapshot regeneration; `backfill()`-only functions do not trip it; the snapshot carries the resolved function-name set; the residual `sessions.py`/host-normalizer gap is documented.
- [ ] The snapshot digest is identical on Python 3.11 and 3.12 (no `ast.dump`/`ast.unparse`/`tokenize` in the hashed representation).
- [ ] A lockstep test fails if `REBUILD_DERIVE_VERSION` is bumped before ENH-3698 lands; `_FROZEN_LEGACY_DERIVE_VERSION` is a separate literal, not an alias.
- [ ] `connect_readonly` accepts a `timeout` keyword; `rebuild_needed` uses ~0.5 s and maps a lock timeout to `unknown`.
- [ ] `REBUILD_DERIVE_VERSION` carries a "Bump when ... (do not bump before ENH-3698 lands)" comment; `session_store/__init__.py` exports the new names in both import and `__all__`.
- [ ] `TestSessionStartRebuild` updated to the new gate; remote stores still never rebuild from a hook.
- [ ] Docs (`HISTORY_SESSION_GUIDE.md`, `API.md`, `ARCHITECTURE.md` `last_rebuild_version` wording) and the stale docstrings/comments updated in end-user shape.

## Related

- ENH-3698 (size gate + pending notice + doctor check; must land before any derive bump), ENH-3699 (single-flight lock + cooldown; deferred, spike-gated; blocks ENH-3666), ENH-3666 (structural fix; now `blocked_by` ENH-3699), ENH-3679 (telemetry writer resilience), FEAT-3561 (unblock target; its `SCHEMA_VERSION` bump is why the legacy rule is a floor), EPIC-3693 (detached 2026-10-02).

## Status

**Open** | Created: 2026-09-30 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-10-03T03:33:25 - `559f97f2-0fed-4e17-be64-5c3d7a03740e.jsonl`
- `/ll:advise` (Opus, ENH-3678/FEAT-3667 pre-implementation review; edits applied) - 2026-10-02
- `/ll:advise` (Opus, EPIC-3693 pre-implementation review) + split into ENH-3678/3698/3699 - 2026-10-02
- `/ll:verify-issues` - 2026-10-02T17:39:34 - `c4987968-ecb7-44fe-a16e-56254b7c993f.jsonl`
- `/ll:refine-issue:gap-analysis` - 2026-10-02T17:37:27 - `9416e528-98f1-4f80-9820-ac6e5fed4e1c.jsonl`
- `/ll:verify-issues` - 2026-10-02T17:32:28 - `b0f899a2-5d6e-4053-9fcb-6bd7647cde0c.jsonl`
- `/ll:reconcile-issue` - 2026-10-02T17:30:38 - `6ecc6d6a-67ab-4f16-bac7-1454c735549d.jsonl`
- `/ll:wire-issue` - 2026-10-02T17:27:57 - `f1065705-d813-48c2-b6b4-f468cf2be46f.jsonl`
- `/ll:refine-issue` - 2026-10-02T17:18:44 - `17172743-fe56-4b5b-955c-a50b6984c2e7.jsonl`
- `/ll:confidence-check` - 2026-09-30T05:10:23 - `defb8cbc-fb4d-4d9b-9b95-eac7264d3124.jsonl`
