---
id: ENH-2890
status: done
priority: P2
parent: EPIC-2789
labels:
- enhancement
- architecture
- refactoring
relates_to:
- ENH-2772
confidence_score: 96
outcome_confidence: 84
completed_at: '2026-07-28T10:44:50Z'
score_complexity: 18
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 22
---

# ENH-2890: Split session_store.py production code into a subpackage

## Summary

Convert `scripts/little_loops/session_store.py` (5,154 lines) into a
`session_store/` subpackage split along its existing seams — schema/migrations,
query/read API, retention lifecycle, and DB-path resolution — while keeping
`little_loops.session_store` as the public import path so none of the 70+
importers change. This is the production-code half of ENH-2772's decomposition;
splitting the ~6,900-line test file is tracked separately as ENH-2891.

## Current Behavior

`scripts/little_loops/session_store.py` is a single 5,470-line flat module
mixing schema/migrations, DB-path resolution, the query/read API, retention
lifecycle (including LCM session compaction), and the bulk of the
`record_*_event`/`*_event_context` writer functions in one file. 100+ files
import from it directly by name, and several call sites (tests, hooks,
`verify_kinds.py`) reach into private module-level names via attribute
access (`session_store._MIGRATIONS`, `session_store.sqlite3.connect`, etc.).

## Expected Behavior

`scripts/little_loops/session_store.py` no longer exists as a flat module;
`scripts/little_loops/session_store/` is a package with `schema.py`, `db.py`,
`queries.py`, `lifecycle.py`, and a writer-API module, while
`little_loops.session_store` remains the public import path. Every name in
the original file's `__all__`, the private names enumerated in step 6, and
the `sqlite3` module attribute are re-exported from `session_store/__init__.py`
so none of the 100+ importers change their import statements.

## Impact

At 5,470 lines, `session_store.py` is the largest module in the codebase and
the primary blocker to `ENH-2772`'s subpackage decomposition (`session_store.py`
tracked separately for its test file in ENH-2891). Its size makes it hard to
navigate, review, and modify safely — any change risks touching unrelated
schema, query, lifecycle, or writer concerns in the same diff. Splitting it
along existing seams reduces review surface and blast radius for future
changes without altering any public behavior.

## Scope Boundaries

In scope: splitting `session_store.py` production code into
`schema.py`/`db.py`/`queries.py`/`lifecycle.py`/a writer-API module, with a
transparent `__init__.py` re-export layer. Out of scope: splitting
`scripts/tests/test_session_store.py` (tracked separately as ENH-2891) and
any behavioral changes to the session store's public API.

## Parent Issue

Decomposed from ENH-2772: Split session_store.py god module into a subpackage.

## Proposed Solution

1. Create `session_store/` package; move `_MIGRATIONS`, `_KIND_TABLE`,
   `_KINDLESS_TABLES`, `_LOOP_EVENT_TYPES`, `SCHEMA_VERSION`, `VALID_KINDS`,
   `_configure_connection`, `_split_sql_statements`, `_current_version`,
   `_apply_migrations`, `ensure_db`, `connect` into `schema.py`.
2. Move DB-path resolution (`DEFAULT_DB_PATH`, `_is_default_shaped`,
   `_config_db_path`, `_resolve_db_path`, `resolve_history_db`) into `db.py`
   (or `__init__.py` — `ensure_db`/`connect` depend on it).
3. Move the query/read API (`fts_phrase`, `search`, `recent`, `export_history`
   + its `_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES` globals) into
   `queries.py`.
4. Move retention lifecycle (`_backfill_sessions` through
   `backfill_incremental`, `compact`, `prune`, `record_retirement`/
   `list_retirements`, plus LCM session-compaction:
   `_maybe_soft_threshold_summary`, `_compact_session_conn*`,
   `compact_session`, `compact_session_with_reasoning`, `_call_llm_for_summary`,
   `_estimate_tokens`, `_summarize_block`) into `lifecycle.py`. Preserve the
   deferred imports from `little_loops.compaction.instant` used to break the
   circular dependency (currently `_maybe_soft_threshold_summary`'s
   `SOFT_THRESHOLD_TOKENS`/`evict_sink_and_window`/`summarize_6_section`
   imports, plus the `TYPE_CHECKING`-only `CompactionConfig` import).
5. The bulk of the file (`record_*_event`/`*_event_context` writer functions
   and paired `_backfill_*` helpers, ~lines 1388-4000) doesn't map cleanly
   onto the four named concerns — give it its own writer-API module
   (e.g. `writers.py`) rather than forcing it into `queries.py` or
   `lifecycle.py`.
6. `session_store/__init__.py` re-exports the full existing `__all__` list
   (lines 74-117 of the current file) plus these private names required by
   external call sites: `_MIGRATIONS`, `_KIND_TABLE`, `_KINDLESS_TABLES`,
   `_split_sql_statements`, `SCHEMA_VERSION`, `_call_llm_for_summary`,
   `_estimate_tokens`, `compact_session_with_reasoning`, `_summarize_block`,
   `_derive_transition`, `_pack_payload`, `_unpack_payload`. Follow the
   `issue_history/__init__.py` precedent (re-exports private helpers "for
   test access").
7. **Re-export `sqlite3` itself as a `session_store` package attribute** (not
   just wrapped functions) — `scripts/tests/conftest.py:615-655`'s
   `_guard_real_history_db` autouse fixture does
   `monkeypatch.setattr(session_store.sqlite3, "connect", guarded_connect)`.
   Missing this breaks setup for the **entire test suite**, not one test.
   This is the single highest-risk breakage point in this issue.
8. Update `scripts/little_loops/cli/verify_kinds.py:22-23,33,40-41`, which
   accesses `session_store._MIGRATIONS`/`_KIND_TABLE`/`_KINDLESS_TABLES` via
   attribute access on the module object — the `__init__.py` re-export in
   step 6 keeps this file unchanged.
9. Update docs/skills that reference qualified private-name paths or the flat
   import path: `.claude/CLAUDE.md:246` (prose reference to
   `session_store._MIGRATIONS`/`_KIND_TABLE`), `skills/compact-session/SKILL.md:68`
   (`session_store._summarize_block`), `skills/improve-claude-md/SKILL.md:206,293,308`
   (executable snippets importing `resolve_history_db`/`record_retirement` —
   verify these still run post-split).
10. Run `python -m pytest scripts/tests/` (full suite — `test_session_store.py`
    stays as-is at this stage, unsplit, and must keep passing unchanged against
    the new package) and `ll-verify-package-data` (wheel-manifest/`__file__`-escape
    lint) to confirm the split is transparent to every consumer.

## Acceptance Criteria

- `scripts/little_loops/session_store.py` no longer exists as a flat module;
  `scripts/little_loops/session_store/` is a package with `schema.py`,
  `db.py`, `queries.py`, `lifecycle.py`, and a writer-API module.
- `session_store/__init__.py` re-exports every name in the original file's
  `__all__`, plus the private names enumerated in step 6, plus the `sqlite3`
  module attribute (step 7).
- `python -m pytest scripts/tests/` passes with **zero import changes** to any
  of the 122 dependent files, and `test_session_store.py` (still unsplit at
  this stage) passes unchanged.
- `ll-verify-kinds` and `ll-verify-package-data` both exit 0.
- No importer outside `session_store/` itself changes its import statements.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Line-count drift**: the file is currently **5,470 lines**, not the 5,154
  cited above — all line numbers below are measured against the current file.
- **`_pack_payload`/`_unpack_payload` module homes are unaddressed.** They live
  at `session_store.py:214`/`219` (zlib compression helpers for raw-event
  payloads) and are named in step 6 as required `__init__.py` re-exports, but
  no step assigns them to a target module. They're used by
  `_backfill_raw_events` — put them in `writers.py`.
- **`queries.py`'s four names are not contiguous in the source.**
  `fts_phrase`(3016)/`search`(3028)/`recent`(3056) sit in the middle of the
  writer/backfill block (between `_backfill_subagent_runs` and
  `SQLiteTransport`), while `export_history`(5409) +
  `_EXPORT_TABLE_MAP`(5366)/`_EXPORT_DEFAULT_TABLES`(5388) live ~2,300 lines
  away at the very end of the file. Extraction is a name-based pull, not a
  contiguous slice.
- **`SQLiteTransport` (class, `session_store.py:3100-3341`, ~240 lines) has no
  assigned module.** It falls inside the 1388-4000 band step 5 assigns to
  `writers.py` and writes `loop_events`/`issue_events`, making it a natural fit
  there, but step 5's text ("record_*_event/*_event_context writer functions
  and paired _backfill_* helpers") never names it explicitly — call this out
  when implementing so it isn't left behind in the flat module by mistake.
- **Pre-existing `__all__` mismatch**: `__all__` (lines 74-117) lists
  `backfill_snapshots`, but the only module-level symbol with that shape is
  `_backfill_snapshots` (private, line 3341) — no public `backfill_snapshots`
  exists today. This is a pre-existing bug in the current file, not introduced
  by the split, but the `__init__.py` re-export in step 6 will surface it as
  an `ImportError` unless resolved (either export the private name under the
  public alias, or fix `__all__`).
- **Confirmed one-directional cross-module dependencies** (no cycles): `schema.py → db.py`
  (`ensure_db`/`connect` call `_resolve_db_path`, session_store.py:1349),
  `queries.py → schema.py` (`export_history` calls `connect()`, :5447),
  `lifecycle.py → schema.py` (`_maybe_soft_threshold_summary`'s inner `_run()`
  calls `connect(db)`, :4458).
- **`issue_history/__init__.py` precedent, exact mechanics** (referenced in
  step 6): it does NOT use `from .module import *`. It uses fully-qualified
  explicit imports per submodule (`from little_loops.issue_history.<mod>
  import (...)`), mixing public and private names in the same import
  statement, followed by one trailing `__all__` list with a
  `# Private functions re-exported for test access` comment marking the
  underscore-prefixed entries. `session_store/__init__.py` should follow this
  same shape.
- **Importer scope confirmed**: 100+ files import `session_store` — 40+ CLI
  modules (all importing at minimum `DEFAULT_DB_PATH`/`cli_event_context`),
  9 hook modules, the parallel/FSM/compaction layers, and 30+ test files.
  `scripts/tests/conftest.py:615-651`'s `_guard_real_history_db` fixture
  (patches `session_store.sqlite3.connect`) is the single highest-risk
  breakage point, as step 7 already notes.

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation, in addition to steps 1-10 above:_

11. Assign `SkillEventCompletion`, `HookEventCompletion`, `normalize_issue_id`,
    `mine_corrections_from_messages`, `is_correction` to `writers.py` (all
    currently unassigned `__all__` entries — see Integration Map).
12. Add `from little_loops.session_store.schema import VALID_KINDS,
    _KIND_TABLE` to `queries.py`; add `import subprocess` at the
    `session_store/__init__.py` package level (not only in a submodule) so
    `patch("little_loops.session_store.subprocess.run")` continues to
    resolve.
13. Update `scripts/little_loops/__init__.py`'s own re-export of
    `SQLiteTransport`/`record_issue_snapshot`/`record_session_lifecycle_event`
    if its import path changes (verify — should be transparent since it goes
    through `little_loops.session_store`, not a submodule directly).
14. Verify the `compaction/instant.py` ↔ `session_store` import direction
    before finalizing `lifecycle.py`'s deferred-import shape — confirm
    whether `compaction/instant.py` genuinely imports
    `_call_llm_for_summary` back from `session_store` (would be a new cycle
    to design around) or whether that reference is comment-only.
15. Add one new test to `test_session_store.py` (not a new file) that
    iterates `session_store.__all__` plus the step-6 private-name list plus
    `sqlite3` and asserts each resolves via `hasattr`/`getattr` — no existing
    test covers re-export completeness end-to-end.
16. Update stale line-number references in `docs/reference/EVENT-SCHEMA.md:1046-1050`
    and `docs/development/USER_GUIDE_AUDIT_REPORT.md:293` to point at their
    new submodule locations.

## Integration Map

_Wiring pass added by `/ll:wire-issue`:_

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/session_start.py` — imports `_MIGRATIONS`,
  `SCHEMA_VERSION`, `_split_sql_statements` directly by name (not attribute
  access) — must resolve from `session_store/schema.py` via the `__init__.py`
  re-export.
- `scripts/little_loops/__init__.py` — imports `SQLiteTransport`,
  `record_issue_snapshot`, `record_session_lifecycle_event` from
  `session_store` for top-level package re-export; unaddressed by the issue's
  step 6 list (which only covers `session_store/__init__.py`, not the parent
  package `__init__.py` that re-exports from it).
- `scripts/little_loops/compaction/result.py` — imports
  `compact_session_with_reasoning`, `connect` (both landing in
  `lifecycle.py`/`schema.py` respectively).
- `scripts/little_loops/compaction/instant.py` — appears to reference
  `session_store._call_llm_for_summary`. **Needs verification before
  implementation**: `session_store.py`'s `_maybe_soft_threshold_summary`
  already does a *deferred* import *from* `compaction.instant`
  (`SOFT_THRESHOLD_TOKENS`/`evict_sink_and_window`/`summarize_6_section`) to
  avoid a cycle. If `compaction/instant.py` also imports back from
  `session_store`, that's a real bidirectional dependency — confirm which
  direction is real (doc comment vs. actual import) before assuming the
  planned `lifecycle.py → compaction.instant` deferred-import shape is
  sufficient.
- `scripts/little_loops/queue_store.py` — references
  `session_store._configure_connection`, `_split_sql_statements`,
  `_apply_migrations` (docs/reference/API.md:9012 and ARCHITECTURE.md:836
  independently confirm this is a "modeled on, not shared" pattern — verify
  whether these are live imports or comment-only references).
- `scripts/little_loops/cache_marking_oracle.py` and
  `scripts/little_loops/fsm/schema.py` — both reference
  `session_store._estimate_tokens`.
- `scripts/little_loops/observability/schema.py` — references
  `_LOOP_EVENT_TYPES`.
- `scripts/little_loops/learning_tests/extractor.py` — references
  `session_store._call_llm_for_summary`.
- `scripts/little_loops/parallel/orchestrator.py`, `worker_pool.py`,
  `merge_coordinator.py` — import `resolve_history_db`/session_store
  functions.
- `scripts/little_loops/fsm/executor.py`, `fsm/continuity.py` — import
  `resolve_history_db`/session_store functions.
- `scripts/little_loops/history_reader.py`, `pytest_history_plugin.py`,
  `user_messages.py`, `workflow_sequence/io.py` — import session_store
  functions (public API, lower risk).
- Additional private-name test imports beyond `test_session_store.py`:
  `scripts/tests/test_enh_2497_agent_type.py`,
  `scripts/tests/test_enh_2511_mcp_telemetry.py` (both import `_MIGRATIONS`,
  `SCHEMA_VERSION`, `_split_sql_statements` directly),
  `scripts/tests/test_des_schema.py:20` (imports `_LOOP_EVENT_TYPES`),
  `scripts/tests/test_compaction.py:268,300,328` (imports
  `_maybe_soft_threshold_summary` directly).
- `scripts/tests/conftest.py:632` — has a module-level `from little_loops
  import session_store` in addition to the already-known `:651`
  `session_store.sqlite3.connect` attribute patch.

### Missing `__init__.py` re-exports (undermines step 6)

- Two dataclasses are in `__all__` (lines 105, 113) but not assigned to any
  target module by the plan: `SkillEventCompletion` (`session_store.py:1686`,
  yielded by `skill_event_context`) and `HookEventCompletion` (yielded by
  `hook_event_context`) — both belong in `writers.py` alongside their
  context-manager functions.
- Three more `__all__` names have no assigned module:
  `normalize_issue_id` (`session_store.py:1201`),
  `mine_corrections_from_messages` (`session_store.py:3983`),
  `is_correction` (`session_store.py:343`) — the latter two are candidates
  for `writers.py` (co-located with `record_correction`).
- `queries.py` needs an explicit `from
  little_loops.session_store.schema import VALID_KINDS, _KIND_TABLE` —
  `search`/`recent`'s kind-dispatch logic depends on both, per
  `docs/reference/API.md:7780/7821/7860/7901`.
- `__init__.py` must `import subprocess` at the package level (not only
  inside a submodule) — `scripts/tests/test_fsm_continuity.py:82`,
  `test_compaction.py` (6 sites), `test_session_store.py` (14 sites), and the
  `spike/fsm_continuity_compaction/` driver all do
  `patch("little_loops.session_store.subprocess.run")`, which only resolves
  if `subprocess` is an attribute of the `session_store` package itself.

### Tests

- Existing regression sentinels to rely on (no changes needed, but call out
  as the concrete gate for the re-export requirement): `test_verify_kinds.py`
  (`TestAllMigrationTables`/`TestRun`) exercises
  `session_store._MIGRATIONS` at the real package level with no mocking —
  the sharpest existing check that step 6/7's re-export is complete.
  `test_verify_package_data.py`'s `TestFileDepth`/`TestLintFile` is the
  regression gate if any new submodule (`schema.py`, `db.py`, etc.) computes
  a path via `Path(__file__)` — moving from depth-0 (flat file) to depth-1
  (package) shifts the escape-count threshold by one level.
- No existing test walks `session_store.__all__` and asserts every name
  resolves via `hasattr`/`getattr` — this is a genuine coverage gap for the
  re-export-completeness requirement (steps 6/7). Recommend adding one new
  test (not a new file — can live in `test_session_store.py` per the
  "stays unsplit" constraint) that iterates `session_store.__all__` plus the
  step-6 private-name list plus `sqlite3` and asserts each resolves.
- Monkeypatch fragility to verify post-split, not fix pre-split: tests using
  `monkeypatch.setattr(session_store, "connect", boom)` /
  `"record_subagent_run_start"` (`test_hook_post_tool_use.py:197`,
  `test_hook_user_prompt_submit.py:148,307,567`,
  `test_enh_2505_subagent_runs.py:275`, `test_session_store.py:5611,6785`)
  only intercept calls if the hook/caller modules invoke
  `session_store.connect(...)` (qualified) rather than a bare name imported
  at call-site-module load time — split doesn't change this, but it's worth
  a smoke check since these are exactly the highest-traffic hook call sites.

### Documentation

- `docs/reference/EVENT-SCHEMA.md:1046-1050` — cites `SQLiteTransport`
  source location, `self._conn`/`send()` internals, and `_LOOP_EVENT_TYPES`
  by `session_store.py:<line>` — all stale post-split (moves to
  `writers.py`/`schema.py`); note the current line-range cited
  (1311-1430) is already stale against the file's actual position
  (`SQLiteTransport` is at `session_store.py:3100`), independent of this
  issue.
- `docs/development/USER_GUIDE_AUDIT_REPORT.md:293` — cites
  `session_store.py:89` for schema version, becomes `schema.py:<line>`.
- `docs/reference/CLI.md:3124` — references dotted path
  `session_store._MIGRATIONS` in `ll-verify-kinds` docs; remains valid only
  if `_MIGRATIONS` is re-exported at the package root (already required by
  step 6, but this doc line is the concrete consumer proving it).
- `docs/reference/API.md:9012`, `docs/ARCHITECTURE.md:836` — both describe
  `queue_store.py` as modeled on `session_store.py`'s
  `_configure_connection`/`_apply_migrations`/`ensure_db`/`connect` shape;
  low staleness risk (prose, not line-numbered) but names four functions
  moving to `schema.py` — worth a pass to confirm the prose still reads
  correctly post-split.

## Notes

Test-file reorganization (`scripts/tests/test_session_store.py` →
`test_session_store_schema.py`/`_queries.py`/`_lifecycle.py`/`_db.py`) is
**out of scope for this issue** — see ENH-2891. Keeping the flat test file
unsplit here gives this issue a clean, independently-verifiable regression
check (existing tests must keep passing untouched against the new package
before any test-file surgery begins).

## Resolution

Split `scripts/little_loops/session_store.py` (flat module) into
`scripts/little_loops/session_store/` package: `schema.py` (1059 lines),
`db.py` (95), `queries.py` (193), `lifecycle.py` (1382), `writers.py` (2696),
`__init__.py` (239, re-export layer). `little_loops.session_store` remains
the public import path; every `__all__` name, the step-6 private names, and
`sqlite3`/`subprocess` package attributes are re-exported per the
`issue_history/__init__.py` precedent (explicit per-submodule imports, no
`import *`).

Two deviations from the original plan, both required for correctness:
- `__init__.py`'s re-export list was expanded beyond the old `__all__` —
  several public functions (`record_review_event`,
  `record_context_pressure_event`, `record_subagent_run_start/stop`,
  `canonicalize_issue_id`, `record_loop_run_summary`, `record_usage_event`,
  `update_loop_run_diagnostics`) were importable pre-split despite not being
  listed in `__all__`.
- Submodules route internal `connect`/`ensure_db` calls through
  `_pkg.connect(...)` (lazy package-attribute lookup) instead of binding
  local names, because existing tests `monkeypatch.setattr(session_store,
  "connect", ...)` at the package level and expect every internal call site
  to observe the patch.

Verification: `python -m pytest scripts/tests/` → 16825 passed, 42 skipped,
7 failed (same 7 pre-existing failures unrelated to session_store — skill
line-limits, loop-validation gates, prose-dep drift on EPIC-2861 — confirmed
unchanged before/after this change). `test_session_store.py` alone: 402
passed (401 original + 1 new re-export-completeness test). `ll-verify-kinds`
and `ll-verify-package-data` both exit 0. `ruff check` clean.

## Session Log
- `/ll:ready-issue` - 2026-07-28T10:11:08 - `13c64ab5-6b77-4cd2-bf18-235b27e59f46.jsonl`
- `/ll:wire-issue` - 2026-07-28T10:08:39 - `216da898-27cb-4b3a-8912-89badfb6f2d6.jsonl`
- `/ll:refine-issue` - 2026-07-28T10:03:42 - `224b2103-cd24-42bd-ac0e-eaeec79de85c.jsonl`
- `/ll:issue-size-review` - 2026-07-28T00:00:00 - `b1c96f1a-23da-4c31-89fd-9b68894245c4.jsonl`

---

## Status

**Open** | Created: 2026-07-28 | Priority: P2
