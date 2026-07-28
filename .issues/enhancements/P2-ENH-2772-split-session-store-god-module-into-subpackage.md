---
id: ENH-2772
status: done
priority: P2
discovered_commit: fb5673902939bbf5a17bc7afe61317982d40bfd2
discovered_branch: main
discovered_date: 2026-07-24 22:31:26+00:00
discovered_by: audit-architecture
focus_area: large-files
labels:
- enhancement
- architecture
- refactoring
- auto-generated
parent: EPIC-2789
confidence_score: 94
outcome_confidence: 52
score_complexity: 8
score_test_coverage: 22
score_ambiguity: 16
score_change_surface: 6
size: Very Large
completed_at: '2026-07-28T09:59:24Z'
---

# ENH-2772: Split session_store.py god module into a subpackage

## Summary

Architectural issue found by `/ll:audit-architecture`. `session_store.py` is the
largest file in the codebase and its most heavily depended-on module at the same
time — a god module whose blast radius covers most of the package.

## Location

- **File**: `scripts/little_loops/session_store.py`
- **Line(s)**: 1-5154 (entire file)
- **Module**: `little_loops.session_store`

## Finding

### Current State

- 5,154 lines, 89 top-level defs/classes in a single module.
- Fan-in of **70 modules** import from it — the second-highest in the package
  (after `little_loops.config` at 78).
- It carries at least four separable concerns already named by the CLI surface
  (`ll-session` subcommands): SQL migrations (`_MIGRATIONS`), the
  `_KIND_TABLE` kind registry, the query/read API (search, recent, expand,
  describe), and the retention lifecycle (compact, prune, recompress, backfill).
- A circular dependency with `little_loops.compaction` is broken via deferred
  imports at `session_store.py:4119` and `:4136` — a symptom of concerns that
  belong in separate modules.

### Impact

- **Development velocity**: any change to session storage touches a 5k-line file
  with 70 dependents; reviews and merges routinely conflict here (it is the
  most-edited source file over the last 7 days).
- **Maintainability**: migrations, schema registry, queries, and retention are
  interleaved; finding the right seam requires reading most of the file.
- **Risk**: high — wide blast radius means a regression here breaks history,
  analytics, compaction, and several CLIs at once.

## Proposed Solution

Convert to a `session_store/` subpackage with the module split along the
existing seams, keeping `little_loops.session_store` as the public import path
(re-export via `__init__.py` so none of the 70 importers change).

### Suggested Approach

1. Create `session_store/` package; move `_MIGRATIONS` + `_KIND_TABLE` into
   `schema.py` (this is also what `ll-verify-kinds` inspects — update its
   import).
2. Move the read/query API (search/FTS, recent, expand, describe, grep) into
   `queries.py`; move backfill/compact/prune/recompress into `lifecycle.py`.
3. Keep the connection/db-path resolution (`LL_HISTORY_DB` → config → default)
   in `__init__.py` or `db.py`; re-export the existing public names from
   `__init__.py` and confirm `python -m pytest scripts/tests/` passes with no
   importer changes.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation:_

4. Re-export `sqlite3` itself as a `session_store` package attribute (not
   just the wrapped functions) so `scripts/tests/conftest.py:615-655`'s
   suite-wide `_guard_real_history_db` autouse fixture keeps patching
   `session_store.sqlite3.connect` without breaking every test.
5. Confirm the following private names resolve through the new package's
   `__init__.py` in addition to `_MIGRATIONS`/`_KIND_TABLE`/`_KINDLESS_TABLES`:
   `_split_sql_statements`, `SCHEMA_VERSION`, `_call_llm_for_summary`,
   `_estimate_tokens`, `compact_session_with_reasoning`, `_summarize_block`,
   `_derive_transition`, `_pack_payload`, `_unpack_payload`.
6. Split `scripts/tests/test_session_store.py` (~75 test classes, grouped by
   feature/schema-version, not by module) into
   `test_session_store_schema.py`/`test_session_store_queries.py`/
   `test_session_store_lifecycle.py`/`test_session_store_db.py` via manual
   per-class triage — no mechanical move exists.
7. Update `skills/compact-session/SKILL.md:68` and
   `skills/improve-claude-md/SKILL.md:206,293,308` if the qualified
   private-name path or flat import path changes; verify the latter's
   executable snippets still run post-split.
8. Run `python -m pytest scripts/tests/` (full suite, not a subset) and
   `ll-verify-package-data` after the split to catch both the conftest
   fixture risk and any wheel-manifest drift from the new package layout.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Current concern boundaries** (file is `scripts/little_loops/session_store.py`,
5,154 lines, `__all__` declared at lines 74-117):

- **Schema/migrations**: `SCHEMA_VERSION` (line 231), `VALID_KINDS` (233),
  `_KIND_TABLE` (258), `_KINDLESS_TABLES` (290), `_LOOP_EVENT_TYPES` (304),
  `_MIGRATIONS` (379, ~813-line SQL list), `_configure_connection` (1247),
  `_split_sql_statements` (1266), `_current_version` (1279),
  `_apply_migrations` (1296), `ensure_db` (1335), `connect` (1376).
- **DB-path resolution**: `DEFAULT_DB_PATH` (121), `_is_default_shaped` (124),
  `_config_db_path` (141), `_resolve_db_path` (168, the `LL_HISTORY_DB` →
  config → default precedence chain), `resolve_history_db` (193, public
  wrapper). Natural home is `__init__.py` or `db.py` since `ensure_db`/
  `connect` depend on it.
- **Query/read API**: `fts_phrase` (3016), `search` (3028), `recent` (3056),
  `export_history` (5409, with `_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES`
  globals at 5366/5388) — this slice is thin; the bulk of the file
  (~lines 1388-4000) is `record_*_event`/`*_event_context` writer functions
  plus paired `_backfill_*` helpers that don't map cleanly onto any of the
  four named concerns and will need their own home (a writer-API module) if
  the split goes further than the four groups this issue names.
- **Retention lifecycle**: `_backfill_sessions` (4680) through
  `backfill_incremental` (5045), `compact` (5096), `prune` (5186),
  `record_retirement`/`list_retirements` (5310/5337). Session-compaction
  (LCM/FEAT-2598) lives in the same region: `_maybe_soft_threshold_summary`
  (4412), `_compact_session_conn*` (4213/4306), `compact_session` (4646).
- **Circular-dependency deferred imports**: the issue text cites lines
  4119/4136; in the current file state the actual deferred imports are at
  **line 4436** (`from little_loops.compaction.instant import
  SOFT_THRESHOLD_TOKENS, evict_sink_and_window`) and **line 4453**
  (`from little_loops.compaction.instant import summarize_6_section`), both
  inside `_maybe_soft_threshold_summary` — line numbers have drifted since
  the issue was filed. A `TYPE_CHECKING`-only import at 71-72
  (`from little_loops.config.features import CompactionConfig`) is the third
  leg of the same cycle-avoidance.
- **Module-level state to preserve on split**: `_KIND_TABLE` is read by
  `search`, `recent`, and every `record_*` writer, so whichever submodule
  owns it becomes an import dependency for nearly all the others. The one
  genuine runtime shared state is a per-instance `threading.Lock()` inside
  `SQLiteTransport` (line 3100) — splits safely with the class since it's
  not module-level.
- **`ll-verify-kinds` update needed** (`scripts/little_loops/cli/verify_kinds.py`):
  lines 22-23 (`from little_loops import session_store` /
  `from little_loops.session_store import DEFAULT_DB_PATH, cli_event_context`)
  and lines 33/40/41 access `session_store._MIGRATIONS` /
  `session_store._KIND_TABLE` / `session_store._KINDLESS_TABLES` as
  *attribute access on the module object*, not `from...import` of the name —
  so either re-export these underscore-prefixed names through
  `session_store/__init__.py` (keeps `verify_kinds.py` unchanged, following
  the `issue_history/__init__.py` precedent below) or update those three
  lines to import from the new `schema.py` submodule directly, per the
  original suggested approach.
- **Second call site for the same private names**: `scripts/little_loops/queue_store.py`
  defines its own separate `_MIGRATIONS`/`_KIND_TABLE` (not importing
  session_store's) — worth a quick check during implementation but not a
  session_store dependent.

**Existing subpackage precedent in this codebase** (no split has used exactly
`schema.py`/`queries.py`/`lifecycle.py`/`db.py` before — this issue's naming
is novel, not an established convention):

- `scripts/little_loops/fsm/__init__.py:1-250` — module docstring enumerates
  every public export grouped by concern (lines 7-74), followed by
  `from little_loops.fsm.<submodule> import (...)` blocks (76-168), then a
  single alphabetized `__all__` (170-250) that is what keeps
  `from little_loops.fsm import FSMLoop`-style imports working. Submodules
  are concern-named (`schema.py`, `validation.py`, `persistence.py`, etc.),
  not generic — `fsm/schema.py` is FSM-loop dataclass schema, not SQL schema,
  so it's not literally reusable but is the closest naming analogue for a
  `session_store/schema.py` (SQL migrations) module.
- `scripts/little_loops/issue_history/__init__.py:1-207` — same re-export
  shape, and notably re-exports **private** helpers "for test access" (e.g.
  `_detect_processing_agent`, lines 120-128/203-207) — the exact pattern
  needed to keep `session_store._MIGRATIONS`-style attribute access working
  if that route is chosen over updating `verify_kinds.py`.
- `scripts/little_loops/config/` — split by concern (`core.py`, `cli.py`,
  `automation.py`, `orchestration.py`, `features.py`), thinner `__init__.py`
  without the full docstring manifest.
- **Test convention**: both `fsm/` (16 submodules) and `issue_history/`
  (13 submodules) keep tests as **flat files with a module-name prefix**
  (`test_fsm_schema.py`, `test_issue_history_parsing.py`, etc.) — no
  `scripts/tests/fsm/` or `scripts/tests/issue_history/` mirror directory
  exists. The existing `scripts/tests/test_session_store.py` would predictably
  split into `test_session_store_schema.py`, `test_session_store_queries.py`,
  `test_session_store_lifecycle.py` following this convention, not a new
  `scripts/tests/session_store/` directory.

## Integration Map

### Files to Modify

- `scripts/little_loops/session_store.py` — split into a `session_store/`
  package (see Codebase Research Findings above for exact seam line ranges)
- `scripts/little_loops/cli/verify_kinds.py:22-23,33,40-41` — imports
  `session_store._MIGRATIONS`/`_KIND_TABLE`/`_KINDLESS_TABLES` via attribute
  access on the module object; needs either an `__init__.py` re-export of
  those private names or a direct import from the new `schema.py`

### Dependent Files (Callers/Importers)

122 files match a `from little_loops.session_store import ...` /
`import little_loops.session_store` grep. Heaviest consumers, by area:

- CLI entry points: `cli/session.py`, `cli/compact_session.py`,
  `cli/ctx_stats.py`, `cli/history.py`, `cli/history_context.py`,
  `cli/logs.py`, `cli/action.py`, `cli/harness.py`, `cli/auto.py`,
  `cli/parallel.py`, `cli/sprint/run.py`, `cli/loop/__init__.py`,
  `cli/loop/run.py`, `cli/queue.py`, `cli/doctor.py`,
  `cli/verify_cli_allowlist.py`, `cli/verify_triggers.py`,
  `cli/verify_design_tokens.py`, `cli/verify_des_audit.py`,
  `cli/verify_host_map.py`, `cli/verify_decisions.py`, `cli/docs.py`,
  `cli/schemas.py`, `cli/adapt.py`, `cli/learning_tests.py`,
  `cli/create_extension.py`, `cli/issues/set_status.py`, `cli/deps.py`,
  `cli/code.py`, `cli/config.py`, `cli/sync.py`, `init/cli.py`,
  `cli/backfill_worker.py`
- Core/package-level: `little_loops/__init__.py` (re-exports
  `SQLiteTransport`, `record_issue_snapshot`, `record_session_lifecycle_event`),
  `transport.py`
- FSM/automation: `fsm/executor.py`, `fsm/continuity.py`
- Hooks: `hooks/__init__.py` (calls `hook_event_context`),
  `hooks/user_prompt_submit.py`, `hooks/session_start.py`,
  `hooks/subagent_start.py`, `hooks/subagent_stop.py`,
  `hooks/post_tool_use.py`, `hooks/post_commit.py`, `hooks/pre_compact.py`,
  `hooks/sweep_stale_refs.py`
- Compaction (reverse edge of the circular import): `compaction/instant.py`,
  `compaction/result.py`
- Issue/parallel management: `issue_manager.py`, `history_reader.py`,
  `issue_history/analysis.py`, `parallel/worker_pool.py`,
  `parallel/orchestrator.py`, `parallel/merge_coordinator.py`,
  `user_messages.py`, `pytest_history_plugin.py`

A resulting `session_store/__init__.py` must re-export the full `__all__`
list (lines 74-117 of the current file: `DEFAULT_DB_PATH`, `SCHEMA_VERSION`,
`VALID_KINDS`, `ensure_db`, `connect`, `SQLiteTransport`, `backfill*`,
`rebuild`, `compact`, `search`, `recent`, `record_*` writers,
`resolve_history_db`, etc.) since most call sites do
`from little_loops.session_store import <name>` rather than importing
submodules directly.

_Wiring pass added by `/ll:wire-issue`:_

- Additional leaf CLI consumers not previously enumerated (public-API only,
  low structural risk, but confirm they still import cleanly post-split):
  `cli/issues/__init__.py`, `cli/sprint/__init__.py`, `cli/migrate.py`,
  `cli/artifact.py`, `cli/adapt_skills_for_codex.py`,
  `cli/adapt_agents_for_codex.py`, `cli/verify_package_data.py`,
  `cli/messages.py`, `cli/migrate_status.py`, `cli/migrate_relationships.py`,
  `cli/gitignore.py`, `cli/generate_skill_descriptions.py`.
- **Private names confirmed required in the re-export surface** (beyond
  `_MIGRATIONS`/`_KIND_TABLE`/`_KINDLESS_TABLES` already named above):
  `_split_sql_statements`, `SCHEMA_VERSION` (imported directly by
  `scripts/tests/test_enh_2511_mcp_telemetry.py:18` and
  `scripts/tests/test_enh_2497_agent_type.py:17`), plus `_call_llm_for_summary`,
  `_estimate_tokens`, `compact_session_with_reasoning`, `_summarize_block`
  (the latter referenced by qualified path in `skills/compact-session/SKILL.md:68`).
- `queue_store.py` **confirmed** to define its own independent `_MIGRATIONS`/
  schema-apply pattern rather than importing session_store's — not a
  dependent, no action needed (per the issue's existing note).
- **Highest-risk breakage point**: `scripts/tests/conftest.py:615-655`, the
  session-scoped `autouse=True` fixture `_guard_real_history_db`, does
  `mp.setattr(session_store.sqlite3, "connect", guarded_connect)` — this
  relies on `session_store` exposing a module-level `sqlite3` attribute
  (today true via `session_store.py`'s top-level `import sqlite3`). If the
  split moves the sqlite3 import into `db.py` without `session_store/__init__.py`
  also exposing the *same* `sqlite3` module object as an attribute, this
  fixture raises `AttributeError` at setup for the **entire test suite**, not
  a single test. Must preserve `session_store.sqlite3` resolving to the real
  `sqlite3` module post-split.
- Other `monkeypatch.setattr(session_store, "<name>", ...)` call sites
  requiring `<name>` to remain a live, patchable package-level attribute (not
  a value copied at import time): `scripts/tests/test_hook_post_tool_use.py:195,409`
  (`connect`, `write_file_event`), `scripts/tests/test_enh_2505_subagent_runs.py:270,275`
  (`record_subagent_run_start`), `scripts/tests/test_fsm_executor.py:2629,2715-2716,2749,2776-2777`
  (`record_loop_run_summary`, `record_usage_event`), `scripts/tests/test_cli_learning_tests.py:377,526`
  (`record_learning_test_event`), `scripts/tests/test_cli_loop_worktree.py:869,900`
  (`record_session_lifecycle_event`).
- `skills/improve-claude-md/SKILL.md` contains **executable** code snippets
  (not just prose) doing `from little_loops.session_store import
  resolve_history_db` (line 206) and `from little_loops.session_store import
  record_retirement` (lines 293, 308) — a functional dependency on the flat
  import path, not documentation-only.
- `.claude/CLAUDE.md:246` names `session_store._MIGRATIONS`/`_KIND_TABLE` in
  prose describing `ll-verify-kinds` — must keep resolving post-split.
- Run `ll-verify-package-data` against the new `session_store/` package
  files once created (lints `__file__`-escape patterns + in-wheel manifest
  coverage; no `__file__`-based path resolution exists in the current module,
  so this is a verification step, not an expected fix).

### Similar Patterns

- `scripts/little_loops/fsm/__init__.py:1-250` — re-export shape to follow
  (docstring manifest + per-submodule import blocks + alphabetized `__all__`)
- `scripts/little_loops/issue_history/__init__.py:1-207` — same shape, plus
  the "re-export private names for test/attribute access" pattern
  (`_detect_processing_agent` etc., lines 120-128/203-207) directly
  applicable to `_MIGRATIONS`/`_KIND_TABLE`/`_KINDLESS_TABLES`

### Tests

- `scripts/tests/test_session_store.py` — primary suite; per the flat
  test-naming convention in `fsm/`/`issue_history/`, expect this to become
  `test_session_store_schema.py` / `test_session_store_queries.py` /
  `test_session_store_lifecycle.py`, not a mirrored `tests/session_store/` dir
- `scripts/tests/test_verify_kinds.py` — exercises the `_MIGRATIONS`/
  `_KIND_TABLE` attribute-access path that must keep working post-split
- Also touching session_store: `test_ll_session.py`, `test_compaction.py`,
  `test_hook_session_start.py`, `test_session_log.py`,
  `test_cli_doctor_full.py`, `test_cli_doctor.py`, `test_cli_ctx_stats.py`,
  `test_history_reader.py`, `test_history_context_cli.py`,
  `test_pytest_history_plugin.py`,
  `tests/spike/fsm_continuity_compaction/test_continuity_pipeline.py`

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/tests/test_session_store.py` is confirmed a **flat file** (~6,900
  lines, ~75 `class Test*` groups organized by feature/schema-version, e.g.
  `TestEnsureDb`, `TestSchemaV2`...`TestSchemaV35ReviewEvents`), not
  pre-structured by module boundary — splitting it into
  `test_session_store_schema.py`/`_queries.py`/`_lifecycle.py`/`_db.py` (or
  similar) requires manual per-class triage, not a mechanical move. It also
  imports private names directly (`test_session_store.py:16-40`:
  `_KIND_TABLE`, `_derive_transition`, `_estimate_tokens`, `_pack_payload`,
  `_summarize_block`, `_unpack_payload`, `SCHEMA_VERSION`, `VALID_KINDS`)
  that must remain resolvable off the top-level package.
- Confirmed test-split naming convention from `fsm/`/`issue_history/`
  precedent: `test_<package>_<concern>.py`, flat under `scripts/tests/`, no
  new `conftest.py` needed beyond the existing shared root fixture file.
- `scripts/tests/test_enh_2511_mcp_telemetry.py:18` and
  `scripts/tests/test_enh_2497_agent_type.py:17` — module-level imports of
  `_MIGRATIONS`, `SCHEMA_VERSION`, `_split_sql_statements` not previously
  listed; break if these aren't re-exported.
- `scripts/tests/conftest.py:615-655` (`_guard_real_history_db`, session-scoped
  `autouse=True`) — patches `session_store.sqlite3.connect`; suite-wide
  breakage risk if `session_store.sqlite3` doesn't resolve post-split (see
  Integration Map note above). Highest-priority test to verify against after
  the split lands.
- No existing test asserts on `session_store.py`'s line count as an
  anti-god-module regression guard — if one is desired, it is net-new (no
  precedent in `fsm/`/`issue_history/` splits either).

### Documentation

- `docs/ARCHITECTURE.md` — documents session_store schema versions,
  migrations, EventBus integration, circular-dependency context
- `docs/reference/API.md` — module API reference entries for session_store
- `docs/reference/CLI.md` — references `ll-verify-kinds`, `ll-session`,
  `ll-compact-session`, `ll-history-context`, `ll-ctx-stats`

_Wiring pass added by `/ll:wire-issue`:_

- `.claude/CLAUDE.md:246` — CLI Tools entry for `ll-verify-kinds` names
  `session_store._MIGRATIONS`/`_KIND_TABLE` in prose
- `skills/compact-session/SKILL.md:68` — references `session_store._summarize_block`
  by qualified path (private helper, LCM three-level escalation description)
- `skills/improve-claude-md/SKILL.md:206,293,308` — **executable** code
  snippets (`from little_loops.session_store import resolve_history_db` /
  `record_retirement`), a functional dependency on the flat import path
  continuing to work, not documentation prose only

## Impact Assessment

- **Severity**: High
- **Effort**: Large
- **Risk**: Medium
- **Breaking Change**: No (public import path preserved via re-exports)

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-28_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 52/100 → LOW

### Outcome Risk Factors
- broad enumeration across ~122 dependent files spanning CLI, hooks, FSM,
  compaction, and issue/parallel management — high breadth even though most
  sites are simple import-preserving re-exports
- deep per-site complexity: this is an architectural restructure (interleaved
  schema/query/lifecycle concerns, a circular-dependency workaround, and
  module-level shared state in `_KIND_TABLE`) rather than a mechanical move
- splitting `scripts/tests/test_session_store.py` (~6,900 lines, 79 test
  classes) requires manual per-class triage — no mechanical move exists, and
  it is itself a large sub-task with its own correctness risk
- highest-risk breakage point is `scripts/tests/conftest.py`'s
  `_guard_real_history_db` autouse fixture, which patches
  `session_store.sqlite3.connect` — missing this in the re-export surface
  fails setup for the entire test suite, not a single test

## Session Log
- `/ll:issue-size-review` - 2026-07-28T00:00:00 - `b1c96f1a-23da-4c31-89fd-9b68894245c4.jsonl`
- `/ll:confidence-check` - 2026-07-28T09:55:22 - `373be456-f23f-4bcc-8e50-304f12ee4d58.jsonl`
- `/ll:wire-issue` - 2026-07-28T09:53:09 - `dbc1f548-56af-4f11-a0a0-9d0dff4f5f3a.jsonl`
- `/ll:refine-issue` - 2026-07-28T09:46:40 - `d630f0fa-8c7d-42c3-9d2f-afbccd5a219e.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-07-28
- **Reason**: Issue too large for single session

### Decomposed Into
- ENH-2890: Split session_store.py production code into a subpackage
- ENH-2891: Split test_session_store.py into per-module test files

---

## Status

**Done** | Created: 2026-07-24 | Priority: P2

---

## Resolution

- **Status**: Decomposed
- **Closed**: 2026-07-28
- **Decomposed into**: ENH-2890, ENH-2891

Work for ENH-2772 is now carried by its child issues; this parent was closed by rn-decompose.
