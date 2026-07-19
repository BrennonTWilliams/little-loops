---
id: ENH-2495
title: Record session-lifecycle / handoff events into history.db
type: ENH
priority: P3
status: done
discovered_date: 2026-07-05
captured_at: '2026-07-05T00:00:00Z'
completed_at: '2026-07-19T23:25:47Z'
discovered_by: capture-issue
parent: EPIC-2457
labels:
- enhancement
- history-db
- hooks
- captured
confidence_score: 94
outcome_confidence: 74
score_complexity: 16
score_test_coverage: 22
score_ambiguity: 20
score_change_surface: 16
decision_needed: false
---

# ENH-2495: Record session-lifecycle / handoff events into history.db

## Summary

Of all registered hooks, **only the `post-tool-use.sh` and `user-prompt-check.sh`
paths write to history.db** (tool/skill events, and corrections + `/ll:` skill
dispatches via `user_prompt_submit.py`). The session-lifecycle hooks — `context-monitor.sh`
(threshold tracking, `context_monitor.auto_handoff_threshold: 50`),
`context-handoff-sentinel.sh` (Stop hook, writes the
`.ll/ll-context-handoff-needed` sentinel), the stale-ref sweep
(`scripts/little_loops/hooks/sweep_stale_refs.py`), and PreCompact handoff —
produce **sentinel/state files and advisory feedback only; nothing is persisted
as an event.** So the DB
can't answer "how often does this project hit the context-handoff threshold?" or
"how many stale cross-issue refs get swept per session?" Add a
`session_lifecycle_events` table capturing these transitions
(`handoff_needed`, `compaction`, `stale_ref_sweep`, `session_end`) so context
pressure and session churn become queryable and correlatable with issue/loop
activity.

## Motivation

- **Context pressure is a first-order workflow signal, entirely unrecorded.** The
  auto-handoff threshold crossing is exactly the moment work fragments across
  sessions — precisely what `issue_sessions` / ENH-2462 exist to reconstruct, yet
  the trigger itself is never logged.
- **Sweep findings evaporate.** `sweep_stale_refs.py` computes a findings count
  (stale cross-issue status refs) and emits it as advisory hook feedback; it's
  never persisted, so "is stale-ref churn getting better or worse?" is
  unanswerable.
- **Compaction events are implicit.** Compaction writes `summary_nodes`, but the
  compaction *event* (trigger, when) has no row, so summary provenance can't be
  tied to a moment.

## Current Behavior

- `context-monitor.sh` (PostToolUse) tracks usage into a state file; no DB write.
- `context-handoff-sentinel.sh` (Stop) writes `.ll/ll-context-handoff-needed`;
  no DB write.
- `sweep_stale_refs.py` (SessionStart/session-end path) emits an advisory count;
  no DB write.
- PreCompact hooks run `precompact.sh` / `precompact-handoff.sh`; no lifecycle row.
- There is no `--kind session_lifecycle` in `ll-session`.

## Expected Behavior

- A `session_lifecycle_events` table records rows keyed by session with an
  `event` discriminator (`handoff_needed`, `compaction`, `stale_ref_sweep`,
  `session_end`) plus an event-specific `detail` (JSON), e.g. sweep findings
  count, threshold percent at handoff, compaction token budget.
- The relevant hooks call a new `record_session_lifecycle_event()` (best-effort,
  never blocking the hook) at their existing fire points.
- `ll-session recent --kind session_lifecycle` returns rows.

## Integration Map

_Added by `/ll:refine-issue` — based on codebase analysis:_

### Files to Modify

| File | Anchor | Change |
|------|--------|--------|
| `scripts/little_loops/session_store.py` | `_MIGRATIONS` list (live range 348–856), `SCHEMA_VERSION` (line 216, currently 26 — re-verify before merge), `VALID_KINDS` (lines 218–234), `_KIND_TABLE` (lines 235–251), `__all__` (lines 68–102), top-of-module docstring (lines 1–38) | Append v27 migration after the v26 entry at lines 835–855; bump `SCHEMA_VERSION = 26 → 27`; add `"session_lifecycle"` to `VALID_KINDS` and `_KIND_TABLE`; export `record_session_lifecycle_event` |
| `scripts/little_loops/session_store.py` | after `record_test_run_event` (line 1171) | Add `record_session_lifecycle_event()` best-effort helper modeled on `record_test_run_event` + `record_commit_event` (ENH-2458) |
| `scripts/little_loops/history_reader.py` | top-level docstring (lines 1–42); near `recent_commit_events` (around line 124) | Add `LifecycleEvent` dataclass + `recent_lifecycle_events()` + `handoff_frequency()` |
| `scripts/little_loops/cli/session.py` | `search_parser` choices list (line 92); `recent_parser` choices list (line 113) | Add `"session_lifecycle"` to BOTH `choices=[...]` lists; no further code change (`recent()` is generic over `_KIND_TABLE`) |
| `scripts/little_loops/hooks/sweep_stale_refs.py` | `handle()` lines 174, 194, 201 | Call `record_session_lifecycle_event(..., event="stale_ref_sweep", detail={"findings": N})` before each `return LLHookResult(exit_code=0)` |
| `scripts/little_loops/hooks/pre_compact.py` | `handle()` after `atomic_write_json(state_file, state)` (around line 165), before `return LLHookResult(exit_code=2, ...)` at line 169 | Call `record_session_lifecycle_event(..., event="compaction", detail={"budget_tokens": ..., "compacted_at": ...})` |
| `scripts/little_loops/hooks/pre_compact_handoff.py` | `handle()` after `atomic_write(prompt_path, content)` (line 152 onward) | Optionally emit second `compaction` row (idempotency via shared `compacted_at` timestamp) |
| `scripts/little_loops/hooks/__init__.py` | `_USAGE` banner (lines 50–54); `_dispatch_table()` (lines 74–99) | Update `_USAGE` string to mention `session_lifecycle` if a new intent is added; otherwise no change |
| `hooks/scripts/context-handoff-sentinel.sh` | after sentinel write at lines 76–81 | Shell out to `python -c 'from little_loops.session_store import record_session_lifecycle_event; ...'` with `event="handoff_needed"` and `detail={"threshold_pct": USAGE_PERCENT, "sentinel_threshold": SENTINEL_THRESHOLD, "token_count": TOKEN_COUNT, "context_limit": CONTEXT_LIMIT}` |
| `hooks/scripts/context-monitor.sh` | after crossing-branch at lines 354–362 (PostToolUse threshold-cross) | Optional: emit `event="handoff_needed"` from PostToolUse when threshold first crosses (currently no Python path — would need shell-out helper) |
| `scripts/tests/test_session_store.py` | after `TestRecordTestRunEvent` (line 3549) | Add `TestRecordLifecycleEvent` (roundtrip, event discriminator, detail JSON, FTS) and `TestSchemaV27` (uses `_bootstrap_schema_at(db, 26)` from line ~3901) |
| `scripts/tests/test_ll_session.py` | after the `test_recent_subcommand_commit_accepted` pair (lines 78–95) | Add `test_recent_subcommand_session_lifecycle_accepted` for both `recent` and `search` parsers |
| `scripts/tests/test_history_reader.py` | after `TestRecentCommitEvents` | Add `TestRecentLifecycleEvents` + `TestHandoffFrequency` |
| `scripts/tests/test_sweep_stale_refs.py` | add to existing sweep tests | Add `test_writes_lifecycle_row` verifying `stale_ref_sweep` event lands in DB |
| `scripts/tests/test_pre_compact.py` | add to existing tests | Add `test_writes_compaction_lifecycle_row` |
| `docs/ARCHITECTURE.md` | schema versions table + hook-write-paths note | Document v27 + `session_lifecycle_events` row |
| `docs/reference/API.md` | `session_store` and `history_reader` sections | Document new public functions |
| `docs/reference/CLI.md` | `ll-session recent --kind` table | Add `session_lifecycle` to the kind list |

### Dependent Files (Callers/Importers)

- `scripts/little_loops/hooks/user_prompt_submit.py:83` — pattern for `with contextlib.suppress(Exception):` call-site wrapping (closest precedent for the new hook call sites)
- `scripts/little_loops/hooks/post_tool_use.py:158` — second precedent for call-site suppress wrap
- `scripts/little_loops/hooks/session_start.py:122` — `ensure_db(resolve_history_db(...))` bootstrap precedent
- `scripts/little_loops/cli/backfill_worker.py` — backfill substrate may need updating if `session_lifecycle` is added to `_EXPORT_TABLE_MAP` (lines ~2791–2802) for `export` support

### Similar Patterns

- `scripts/little_loops/session_store.py:record_test_run_event()` (line 1171) — closest structural twin: many optional scalar fields + one JSON-serialized column (`failing_names_json` ↔ `detail`)
- `scripts/little_loops/session_store.py:record_commit_event()` (line 1041) — newer shape with `INSERT OR IGNORE` idempotency + returns `bool`
- `scripts/little_loops/session_store.py:skill_event_context()` (lines 925–1000) — internal `try/except sqlite3.Error: logger.warning(...)` graceful-degradation precedent (the modern post-EPIC-1707 pattern, tighter than caller-side suppress)

### Tests

- `scripts/tests/test_session_store.py` — `TestRecordLifecycleEvent`, `TestSchemaV27` (mirroring `TestSchemaV20UsageEvents` at line 3228)
- `scripts/tests/test_ll_session.py` — `test_recent_subcommand_session_lifecycle_accepted`
- `scripts/tests/test_history_reader.py` — `TestRecentLifecycleEvents`, `TestHandoffFrequency`
- `scripts/tests/test_sweep_stale_refs.py` — `test_writes_lifecycle_row` (graceful-degradation: pass a directory as `db_path`)
- `scripts/tests/test_pre_compact.py` — `test_writes_compaction_lifecycle_row`

### Documentation

- `docs/ARCHITECTURE.md` — schema row for `session_lifecycle_events`
- `docs/reference/API.md` — `session_store.record_session_lifecycle_event()`, `history_reader.recent_lifecycle_events()`, `history_reader.handoff_frequency()`
- `docs/reference/CLI.md` — `ll-session recent --kind session_lifecycle`
- `docs/guides/HISTORY_SESSION_GUIDE.md` — user-facing walkthrough (if present)

### Configuration

- `LL_HISTORY_DB` env-var override (already honored by `resolve_history_db()` at line 94) — no new config needed for the recorder itself
- `context_monitor.auto_handoff_threshold` (default **80**, not 50 — see "Threshold correction" in Codebase Research Findings below)
- `context_monitor.sentinel_threshold` (default **50** — this is the sentinel threshold, the one that triggers `.ll/ll-context-handoff-needed`)

### Wiring Additions (added by `/ll:wire-issue`)

_Files and coupling surfaces identified by the wiring pass that are not on the Integration Map above. These must be touched alongside the primary implementation._

#### Additional Files to Modify

| File | Anchor | Change | Source |
|------|--------|--------|--------|
| `scripts/little_loops/__init__.py` | line 44 (`__all__` re-export block) | Re-export `record_session_lifecycle_event` for `from little_loops import *` parity with `record_issue_snapshot` | Agent 1 (caller tracer) |
| `scripts/tests/test_assistant_messages.py` | line 88 (`assert SCHEMA_VERSION == 26`) | Bump to 27 when v27 migration lands | Agent 1 + Agent 3 |
| `scripts/tests/test_hook_session_start.py` | lines 307, 332, 341 (`TestRebuildFlagOnlyWhenSchemaVersionAdvanced`, `TestFreshMigrationTriggersRebuild`) | Bump `SCHEMA_VERSION == 26` literals to 27 | Agent 1 + Agent 3 |
| `scripts/tests/test_session_store.py` | lines 1371–1372, 1817, 1932, 1984, 2080, 3658, 3699 | Multiple `assert SCHEMA_VERSION == 26` literals across `TestRecord*` classes — bump to 27 | Agent 3 (test gap finder) |
| `scripts/tests/test_hooks_integration.py` | `TestContextHandoffSentinel` (lines 2740–2905) | Add `test_writes_lifecycle_row_on_threshold_crossing` (asserts `session_lifecycle_events` row landed in DB after bash script runs) and `test_python_failure_does_not_flip_exit_code` (DB write failure → `returncode == 0` AND sentinel still written — verifies `\|\| true` semantics) | Agent 3 |
| `scripts/tests/test_sweep_stale_refs.py` | add to `TestSweepStaleRefsGracefulDegradation` (line 255) | Add `test_writes_lifecycle_row_silently_with_broken_db` — call `handle(_event(cwd=tmp_path))` after pointing `LL_HISTORY_DB` at the tmp directory; assert sweep primary job completes AND no `session_lifecycle_events` row is written (graceful drop) | Agent 3 |
| `scripts/tests/test_pre_compact.py` | add to existing precompact tests | Add `test_writes_compaction_lifecycle_row_silently_with_broken_db` — same shape as sweep; verify compaction primary job completes AND DB write fails silently | Agent 3 |
| `docs/guides/HISTORY_SESSION_GUIDE.md` | lines 51, 60–75 (schema versions table), 32–43 (task→command table), 80–100 ("What Gets Recorded" table), 170 (`--kind` enumeration) | Add v27 row; add `session_lifecycle_events` to "What Gets Recorded"; add `ll-session recent --kind session_lifecycle` row to task→command table; append `session_lifecycle` to brace-enumerated kind list | Agent 1 + Agent 2 |
| `docs/guides/BUILTIN_HOOKS_GUIDE.md` | line 59 ("PostToolUse records tool & file events"), line 94 (flow diagram), line 434 (`analytics.capture.file_events` config row) | Add `session_lifecycle` companion line to PostToolUse writers list; add `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel` producers to flow diagram; consider `analytics.capture.session_lifecycle_events` flag (precedent: `usage_events`) | Agent 1 |
| `docs/reference/CONFIGURATION.md` | lines 1162–1178 (`hooks.pre_compact.rubric.*` block) | Mention that compaction events from this hook flow into `session_lifecycle_events` (cross-reference ENH-2507 if present) | Agent 1 |
| `.claude/CLAUDE.md` | lines 141–142, 186, 196, 203, 218 (multiple `ll-session` prose references) | Add `session_lifecycle` to kind listings where `recent`/`search`/`compact` are documented; mirror the table updates in `HISTORY_SESSION_GUIDE.md` | Agent 1 |
| `docs/reference/API.md` | line 81 (history.db prose), lines 4102–4103 (`--kind` brace list — already drifted, no `snapshot`/`usage`/`orchestration_run`/`loop_run`/`learning_test`), line 7275 ("Current schema version: 19" — already stale by 7 versions), line 7279 (`SCHEMA_VERSION` import snippet), lines 6847–6848 (history_reader imports block), 7051–7077 (recent_commit_events/recent_test_runs sections), 7286–7287 + 7346–7389 (record_commit_event/record_test_run_event API reference sections) | Add `session_lifecycle` to prose enumeration (line 81); fix brace-list drift at 4102–4103; bump "Current schema version" to 27; add `LifecycleEvent`, `recent_lifecycle_events`, `handoff_frequency` to imports block; add API reference sections for the new functions | Agent 1 + Agent 2 |
| `docs/reference/CLI.md` | lines 2427 (`search --kind` choices list — ends at `test_run`), 2435 (`recent --kind` choices list — ends at `test_run`), 2501 (`export --tables` choices table), 2510–2512 (worked examples block) | Add `session_lifecycle` to `search` and `recent` `--kind` brace lists; add `session_lifecycle_event` to `export --tables` choices IF `_EXPORT_TABLE_MAP` extended; add `ll-session recent --kind session_lifecycle` example | Agent 1 + Agent 2 |
| `docs/ARCHITECTURE.md` | lines 670–678 (schema versions table ends at v20, already stale by 6 versions), lines 714–729 (mermaid sequence diagram `v1–v20`), lines 753–754 (Components table — only `post_tool_use` and `user_prompt_submit` listed as hook writers) | Add v27 row mirroring v17–v26 format (or file follow-on cleanup for the v21–v26 backlog); extend sequence diagram to show `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel` as DB writers; add Components table rows for the new producers | Agent 1 + Agent 2 |

#### Additional Dependent Files (Callers/Importers) — Awareness Only (no edit required)

- `scripts/little_loops/cli/verify_kinds.py:40` — iterates `_KIND_TABLE.values()` against `_MIGRATIONS` CREATE TABLEs; the ENH-2581 gate enforces that `session_lifecycle_events` is in `_KIND_TABLE` OR `_KINDLESS_TABLES`. No edit, but failure mode if forgotten: `ll-verify-kinds` exits 1.
- `scripts/little_loops/cli/session.py:228–230` — `export --tables` help text lists `session, issue_event, ...`; only edit if `_EXPORT_TABLE_MAP` is extended for parity with `commit_event`/`test_run_event`.
- `scripts/little_loops/hooks/types.py:44` — `LLHookEvent.session_id: str | None = None`; this is the data source for `session_id=event.session_id` on every new `record_session_lifecycle_event(...)` call (per the Integration Map's Stale Reference Audit item at line 262).
- `scripts/little_loops/cli/history.py:297,314`, `scripts/little_loops/cli/logs.py:1644`, `scripts/little_loops/cli/history_context.py:31,331`, `scripts/little_loops/loops/sft-corpus.yaml:67`, `scripts/tests/test_loops_sft_corpus.py:42,101` — transitive importers of `history_reader`; the new `recent_lifecycle_events`/`handoff_frequency` functions will be available to these automatically once added.
- `scripts/little_loops/pytest_history_plugin.py:126,130` — direct importer of `record_test_run_event` from `session_store`; serves as the import-shape precedent for `record_session_lifecycle_event` (no edit).
- `scripts/little_loops/__init__.py:44` — package-level `from little_loops.session_store import (..., record_issue_snapshot)` (overlaps with Files to Modify above).

#### Additional Codebase Research Findings

_Added by `/ll:wire-issue` — based on wiring research:_

- **`_EXPORT_DEFAULT_TABLES` ALSO needs the entry** — not just `_EXPORT_TABLE_MAP`. The Integration Map mentions `_EXPORT_TABLE_MAP` (per `cli/backfill_worker.py` coupling at line 104), but Agent 2 confirmed `_EXPORT_DEFAULT_TABLES` at `session_store.py:3318–3329` is a SEPARATE constant that gates which tables `ll-session export` writes without `--tables`. Without both entries, `ll-session export` silently skips `session_lifecycle_events` unless the user passes `--tables session_lifecycle_event` explicitly. ENH-2461 documented this two-map pattern at `.issues/enhancements/P3-ENH-2461-...md:378`.
- **Recorder should use `connect()` (not `ensure_db()` + raw INSERT)** — Agent 3 flagged that `record_skill_event` uses `connect()` which calls `ensure_db()` internally and swallows migration errors more aggressively. The new `record_session_lifecycle_event` should mirror `record_skill_event`'s shape (call `connect()`), NOT `cli_event_context`'s (call `ensure_db()` explicitly). This affects the graceful-degradation contract because `connect()`-based call sites never block the hook even on partial migration state.
- **`_EXPORT_TABLE_MAP` lives in `session_store.py:3304–3316`, NOT in `cli/backfill_worker.py`** — the Integration Map's "Dependent Files" note (`cli/backfill_worker.py` line 2791–2802) is incorrect. The actual map is in `session_store.py:3304`. `backfill_worker.py` is the consumer but doesn't define it.
- **Bash shell-out needs explicit `|| true` verification test** — the proposed bash shell-out pattern `python3 -c '...'` followed by `|| true` is necessary because the hook host (Claude Code `Stop` event) treats any non-zero exit as a stop-blocking error. The new test `test_python_failure_does_not_flip_exit_code` (Agent 3 finding) verifies this contract by triggering a DB write failure (e.g., `LL_HISTORY_DB=/some/dir/`) and asserting `returncode == 0` AND the sentinel file was still written.
- **`docs/reference/API.md:7275` is already drifted** — currently says "Current schema version: **19**" while live is 26. The implementer should bump to 27 (the next open slot per the v27 Implementation Steps refresh) AND fix the drift. Same for line 7279 (`SCHEMA_VERSION,        # 19` in the import snippet).
- **`docs/reference/API.md:4102–4103` brace-list is already drifted** — the `--kind {tool,file,issue,loop,correction,message,skill,cli,commit,test_run}` brace list omits `snapshot` and `usage` despite being valid kinds per `VALID_KINDS`. The new entry should NOT inherit this drift — update the brace list to the full `VALID_KINDS` (or link to it) so future additions don't require a doc re-touch.
- **`docs/reference/CLI.md:2427, 2435` brace lists are also drifted** — same observation as above; both lists end at `test_run`.
- **`test_assistant_messages.py:88` AND `test_hook_session_start.py:307,332,341` ALSO hardcode `SCHEMA_VERSION == 20`** — alongside `test_session_store.py`'s multiple literals. The implementer must grep for `SCHEMA_VERSION == ` across the whole `scripts/tests/` tree when bumping.
- **Codex/OpenCode adapters don't register `pre_compact_handoff`** — `hooks/adapters/codex/hooks.json:17–28` and `hooks/adapters/opencode/index.ts:64–72` only register `pre_compact`, not `pre_compact_handoff`. This is an intentional adapter gap (the handoff variant is Claude-Code-only), NOT a fix-required observation for ENH-2495. Codex/OpenCode users simply won't get `compaction` lifecycle events from the handoff path — the regular `pre_compact` path still emits them.
- **`ENH-2509` coordination anchor confirmed** — `ENH-2509:142` records the `/ll:decide-issue` decision for Option A (Co-implement): both issues land in a single PR sharing the `session_lifecycle_events` table. The shared schema (`(ts, session_id, event, detail JSON, head_sha, branch)` per ENH-2495 line 152–162) is canonical; `ENH-2509`'s `worktree_create`/`worktree_merge`/`worktree_delete` event discriminators are added as additional `event` TEXT values (no CHECK constraint). The shared recorder signature is `record_session_lifecycle_event(db_path, *, ts, session_id, event, detail=None, head_sha=None, branch=None)` — confirmed identical at `ENH-2509:241–246`.

### Wiring Additions — 2026-07-19 (second wire-issue pass)

_Added by `/ll:wire-issue` (second pass) — residual gaps surfaced by the 2026-07-19 tracer agents that were not yet covered above. The original Integration Map's "Wiring Additions" section is preserved; these entries are additive only._

#### Additional Files to Modify (second pass)

| File | Anchor | Change | Source |
|------|--------|--------|--------|
| `scripts/little_loops/config/features.py` | `AnalyticsCaptureConfig` dataclass (`:610`), fields list (`:618–623`), `from_dict()` (`:632–639`) | Add `session_lifecycle_events: bool = True` field between `usage_events` (`:622`) and `correction_patterns` (`:623`); extend `from_dict()` to populate it. Failure mode if forgotten: `ll-init` validation rejects generated config. | Agent 1 (caller tracer) |
| `scripts/little_loops/init/core.py` | `_ANALYTICS_CAPTURE_KEYS = ("skills", "cli_commands", "corrections", "file_events", "usage_events")` (`:17`); dict comprehension at `:140` | Append `"session_lifecycle_events"` to the tuple; this constant drives the comprehension that emits `analytics.capture.*` defaults into generated `ll-config.json`. | Agent 1 |
| `scripts/little_loops/config-schema.json` | `analytics.capture.usage_events` block (`:1743–1747`); parent block at `:1717` has `additionalProperties: false` | Add a `session_lifecycle_events` property mirroring the `usage_events` schema (`{"type": "boolean", "default": true, "description": "..."}`); without this entry, `ll-init` validation rejects the new `AnalyticsCaptureConfig.session_lifecycle_events` field. | Agent 1 |
| `scripts/little_loops/cli/session.py` | module docstring (`:9–10`) — `recent   most recent rows for an event kind (tool, file, issue, loop, correction, message, skill, cli, snapshot, commit, test_run, usage, orchestration_run)` | Replace literal enumeration with a reference to `VALID_KINDS` (the source of truth), or append `, session_lifecycle`. Currently drifts (missing `loop_run`, `learning_test`) — fixes both at once. | Agent 2 (side-effect tracer) |
| `scripts/little_loops/cli/session.py` | `export_parser.add_argument("--tables", ...)` help text (`:240–251`); specifically `:247–249` has the hardcoded `Choices: session, issue_event, issue_snapshot, skill_event, loop_event, correction, summary_node, message_event, commit_event, test_run_event, usage_event, orchestration_run` | Append `, session_lifecycle_event` to the literal list. This is NOT auto-derived from `_EXPORT_TABLE_MAP`; without this edit, `ll-session export --tables=session_lifecycle_event` rejects the value before reaching the runtime check. | Agent 1 + Agent 2 |
| `docs/reference/CLI.md` | line `:2560` (parallel hardcoded `--tables` Choices list in the CLI reference) | Same update as `cli/session.py:247–249` — the two lists have been drifting in parallel. | Agent 1 + Agent 2 |
| `docs/guides/HISTORY_SESSION_GUIDE.md` | line `:180` — prose sentence enumerating `--kind` values literally | Add `session_lifecycle` (and backfill `snapshot`, `loop_run`, `learning_test` which are already missing). | Agent 2 |
| `docs/ARCHITECTURE.md` | Components table at `:752–768` (only `post_tool_use` and `user_prompt_submit` listed as hook writers at `:762–763`) | Add three new rows for `sweep_stale_refs`, `pre_compact`, `context-handoff-sentinel` as DB writers. The mermaid sequence diagram update at `:714–729` is already in the existing Wiring Additions table; this is the Components-table companion. | Agent 2 |
| `docs/guides/HISTORY_SESSION_GUIDE.md` | schema versions table at `:54–83` (lines `:56–81` for the per-version rows) | Add v27 row mirroring v26 format. The integration map's existing entry at line 155 calls out `:51, :60–75`; the agent confirmed `:54–83` is the live range. Also fix "Current schema version: 26" prose at `:52` → 27. | Agent 2 |
| `scripts/tests/test_history_reader.py` | `test_readers_return_empty_on_missing_db` (`:1816–1831`); import list at `:1819–1822` | Add `recent_lifecycle_events` to the parallel missing-DB assertion. Pattern every new reader follows (precedent: `TestNewEventReaders` / `TestUsageEventReaders`). | Agent 1 |
| `scripts/tests/test_pre_compact_handoff.py` | new test method (no existing test for the negative-control invariant) | Add `test_does_not_emit_compaction_lifecycle_row(self, tmp_path, monkeypatch)`: run `pre_compact_handoff.handle(...)` and assert the `session_lifecycle_events` table has NO `compaction` row. This locks in Step 30's "do NOT emit from `pre_compact_handoff.handle()`" decision against future accidental double-counting. | Agent 3 (test gap finder) |
| `scripts/tests/test_history_reader.py` | within `TestRecentLifecycleEvents` (planned; mirror `test_recent_commit_events_filters` at `:1531–1550`) | Add `test_recent_lifecycle_events_filter_by_event`: seed two rows with different `event` discriminators, filter by `event="handoff_needed"`, assert only one row returned. | Agent 3 |
| `scripts/tests/test_history_reader.py` | within `TestHandoffFrequency` (planned; mirror `test_recent_usage_events_newest_first_and_filters` at `:1862–1893`) | Add `test_handoff_frequency_with_since_filter`: seed three rows (`handoff_needed`, `compaction`, `handoff_needed`), assert `handoff_frequency() == 2`, `handoff_frequency(since=t2) == 1`, `handoff_frequency(db=tmp_path/"nope"/"history.db") == 0`. | Agent 3 |
| `scripts/tests/test_hooks_integration.py` | **`TestContextMonitor`** class (NOT `TestContextHandoffSentinel` as the first-pass Wiring Additions table claimed) | Add `test_writes_lifecycle_row_on_threshold_crossing` here, not in `TestContextHandoffSentinel`. The 80% PostToolUse threshold-crossing transition lives in `TestContextMonitor`, mirroring `test_sentinel_written_above_threshold` (`:2747–2780`) but seeding 80%+ usage and asserting the `session_lifecycle_events` row. The first-pass row for `test_hooks_integration.py:TestContextHandoffSentinel` covers only `test_python_failure_does_not_flip_exit_code` (the bash shell-out contract test for the Stop path). | Agent 3 |
| `scripts/tests/test_hook_intents.py` | within `TestHooksMainModule` (`:259–~640`); pattern precedent at `:477–509` (host propagation) and `:541–563` (LL_HOOK_HOST default) | Add `test_main_hooks_session_id_propagates_from_payload`: stub `_dispatch_table` to capture the event, set `sys.stdin` to a payload with `session_id`, call `main_hooks()`, assert `captured[0].session_id == "abc123"`. Add `test_main_hooks_session_id_defaults_to_none`: same shape but no `session_id` in payload, assert `event.session_id is None`. The first-pass Wiring Additions row mentioned "Add a dispatcher test" but did not enumerate these two test names. | Agent 3 |
| `scripts/tests/test_session_store.py` | within `TestRecordSessionLifecycleEvent` (planned; conditional on `config=` parameter being included in the new recorder signature per ENH-2509 reconciliation) | Add `test_record_session_lifecycle_event_config_stub_accepted` mirroring `test_record_skill_event_config_stub_accepted` (`:1657–1664`). **Note**: the issue's Step 23 signature includes `config=` but ENH-2509's locked signature does NOT. If ENH-2509 reconciliation removes `config=`, this test is unnecessary; if kept, this test is required. | Agent 3 (conditional) |

#### Additional `SCHEMA_VERSION == 26` Bump Sites (second pass)

The first-pass Wiring Additions row for `test_session_store.py` listed 7 sites (lines `1371–1372, 1817, 1932, 1984, 2080, 3658, 3699`). Live grep confirms **11 sites, not 7** (line numbers have drifted +7 lines since authoring; **3 additional sites are missed**):

| File:Line | Class | Test |
|-----------|-------|------|
| `scripts/tests/test_session_store.py:1379` | `TestSchemaV7ToolsLog` | `test_schema_version_is_seven` (first-pass said :1371) |
| `scripts/tests/test_session_store.py:1824` | (per-line) | (first-pass said :1817) |
| `scripts/tests/test_session_store.py:1939` | (per-line) | (first-pass said :1932) |
| `scripts/tests/test_session_store.py:1991` | (per-line) | (first-pass said :1984) |
| `scripts/tests/test_session_store.py:2087` | (per-line) | (first-pass said :2080) |
| `scripts/tests/test_session_store.py:3668` | `TestSchemaV13.test_schema_version_is_thirteen` | (first-pass said :3658) |
| `scripts/tests/test_session_store.py:3709` | `TestSchemaV14.test_schema_version_is_fourteen` | (first-pass said :3699) |
| **`scripts/tests/test_session_store.py:4457`** | `TestOrchestrationRuns.test_v21_db_upgrades_gains_orchestration_runs` | **NOT in first-pass list — add** |
| **`scripts/tests/test_session_store.py:4603`** | `TestLoopRunSummary.test_v22_db_upgrades_gains_loop_runs` | **NOT in first-pass list — add** |
| **`scripts/tests/test_session_store.py:4824`** | `TestRecordLearningTestEvent.test_v25_db_upgrades_gains_learning_test_events` | **NOT in first-pass list — add** |

Implementer must `grep -nE "SCHEMA_VERSION == 26" scripts/tests/` at merge time to confirm the complete list. Source: Agent 3 (live grep).

#### Anchor Drift Fixes (second pass)

The first-pass Wiring Additions table cites line numbers that have drifted since authoring. Files are correctly named; only the anchors are stale. The integrator should re-verify each anchor at implementation time.

| File | First-pass anchor | Live anchor | Source |
|------|-------------------|-------------|--------|
| `scripts/tests/test_session_store.py` | `:1371–1372, 1817, 1932, 1984, 2080, 3658, 3699` (7 sites) | `:1379, 1824, 1939, 1991, 2087, 3668, 3709, 4457, 4603, 4824` (10 sites, +3 missed) | Agent 3 |
| `scripts/little_loops/cli/session.py` (search_parser) | `:92` | `:103` | Agent 1 |
| `scripts/little_loops/cli/session.py` (recent_parser) | `:113` | `:115` | Agent 1 |
| `scripts/little_loops/cli/session.py` (--tables help text) | `:228–230` | `:247–249` | Agent 1 |
| `scripts/little_loops/__init__.py` (record_issue_snapshot import) | `:44` | `:50` | Agent 2 |
| `scripts/little_loops/__init__.py` (record_issue_snapshot in `__all__`) | `:44` | `:108` | Agent 2 |
| `scripts/little_loops/hooks/types.py` (LLHookEvent.session_id) | `:44` | `:43` (line 44 is the surrounding docstring) | Agent 2 |
| `docs/guides/HISTORY_SESSION_GUIDE.md` (schema versions table) | `:51, :60–75` | `:54–83` (range widened) | Agent 2 |
| `docs/reference/CLI.md` (--tables choices list) | `:2501` | `:2560` | Agent 1 + Agent 2 |

#### Additional Dependent Files (Callers/Importers) — Awareness Only (no edit required)

- `scripts/little_loops/observability/schema.py` — DES variant registration; the issue explicitly excludes DES bus path (direct-call recorder pattern). No edit needed.
- `scripts/little_loops/cli/history.py:297,314`, `scripts/little_loops/cli/logs.py:1644`, `scripts/little_loops/cli/history_context.py:31,331`, `scripts/little_loops/loops/sft-corpus.yaml:67`, `scripts/tests/test_loops_sft_corpus.py:42,101` — transitive importers of `history_reader`; the new `recent_lifecycle_events`/`handoff_frequency` functions will be available to these automatically once added.
- `docs/development/TROUBLESHOOTING.md:580–591` — handoff troubleshooting cluster (no lifecycle-event query reference; possible follow-on entry for `ll-history-context --handoff-frequency` after the helper ships).
- `docs/development/TROUBLESHOOTING.md:1149–1196` — `pre_compact_handoff` test snippet (no `--kind` enumeration; awareness only).
- `docs/reference/HOST_COMPATIBILITY.md:30` + footnote `:58–68` — `session_end` intent footnote explains the SessionStart re-homing. If Step 31's new `session_end_record` intent lands, this footnote needs a follow-on note; otherwise unchanged.
- `.issues/epics/P3-EPIC-2457-post-epic-1707-history-db-coverage-expansion.md:93,165,292` — epic tracker references ENH-2495's `session_lifecycle_events` table; no edit required (issue-text references remain valid post-implementation).
- `CHANGELOG.md` — awareness only; per `feedback_changelog_no_unreleased.md`, new entries go to a concrete `## [X.Y.Z] - DATE` section during release prep, not `[Unreleased]`.

#### Additional Codebase Research Findings (second pass)

_Added by `/ll:wire-issue` (second pass) — based on the 2026-07-19 wiring research:_

- **`analytics.capture.session_lifecycle_events` is a true live-writer flag, not a forward-compat gate.** The precedent at `docs/reference/CONFIGURATION.md:527` describes `usage_events` as a "forward-compat gate" because `usage_events` is derived from `raw_events` rebuild (not a fire-time hook). Lifecycle events are written by fire-time hooks (`context-monitor.sh`, `sweep_stale_refs.py`, `pre_compact.py`, `context-handoff-sentinel.sh`), so the closer precedent is `corrections`/`file_events` (true live writers), not `usage_events`. The implementer should mirror the `corrections` schema description, not the `usage_events` one.
- **`test_writes_lifecycle_row_on_threshold_crossing` location correction.** The first-pass Wiring Additions row puts this test in `test_hooks_integration.py:TestContextHandoffSentinel`, but the 80% PostToolUse threshold-crossing transition lives in `TestContextMonitor` (the PostToolUse class), not `TestContextHandoffSentinel` (the Stop class). Move the test to `TestContextMonitor` to keep test class semantics aligned with the production code under test. `TestContextHandoffSentinel` retains only `test_python_failure_does_not_flip_exit_code` (the bash shell-out contract test for the Stop path).
- **`config=` parameter coordination conflict.** The issue's Step 23 signature includes `config: dict | None = None`; ENH-2509's locked shared signature does NOT include `config=`. Per the issue's Confidence Check Notes, this is a known unresolved decision. The integration test `test_record_session_lifecycle_event_config_stub_accepted` (Agent 3 Gap 8) is conditional on the reconciliation outcome — include only if `config=` survives reconciliation.
- **Three missing `SCHEMA_VERSION == 26` literals in `test_session_store.py`** are at `:4457` (`TestOrchestrationRuns.test_v21_db_upgrades_gains_orchestration_runs`), `:4603` (`TestLoopRunSummary.test_v22_db_upgrades_gains_loop_runs`), and `:4824` (`TestRecordLearningTestEvent.test_v25_db_upgrades_gains_learning_test_events`). These are upgrade tests for sibling EPIC-2457 history-DB migrations (v21, v22, v25) and assert `SCHEMA_VERSION == 26` at the head of the test to confirm the upgrade landed. All three must bump to 27 in the same commit; the first-pass Wiring Additions table missed them.
- **`docs/reference/HOST_COMPATIBILITY.md:30` footnote on `session_end`.** If Step 31's new `session_end_record` intent lands, this footnote (`:58–68`) needs a follow-on sentence: the existing `session_end` intent remains the SessionStart sweep; the new `session_end_record` intent fires on the true `SessionEnd` event for Claude Code. Codex/OpenCode skip the new intent (no equivalent end callback). The footnote edit is small but belongs in the same commit if Step 31 lands.
- **`scripts/little_loops/cli/session.py:9–10` module docstring** lists kinds literally (missing `loop_run`, `learning_test`, and post-ENH-2495 `session_lifecycle`). Replace with a reference to `VALID_KINDS` to prevent future drift, or append the missing values.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Threshold correction**: The Summary/Expected Behavior states `context_monitor.auto_handoff_threshold: 50` — that value is wrong. The actual default is **80** (see `context-monitor.sh:26`: `LL_HANDOFF_THRESHOLD:-ll_config_value context_monitor.auto_handoff_threshold 80`). The **50** in the issue is the `sentinel_threshold` (line 76 of `context-handoff-sentinel.sh`), which is intentionally lower so the resume turn has headroom. The implementer should pick the appropriate threshold based on which event source they're wiring (PostToolUse crossing → 80; Stop sentinel → 50) and include the relevant threshold in `detail`.
- **Three distinct best-effort patterns** exist in the codebase; the modern post-EPIC-1707 pattern is `try/except sqlite3.Error: logger.warning(...)` *inside* the recorder (see `skill_event_context` at lines 962–963). Older patterns put the suppression at the call site (`with contextlib.suppress(Exception):` in `user_prompt_submit.py:83`). Either works; the internal pattern is preferred because it guarantees the hook call site can't accidentally fail-open.
- **`_VALID_KINDS` is a `frozenset`** validated inside `recent()` at line 1278 (`if kind not in _VALID_KINDS: raise ValueError(...)`). Adding `"session_lifecycle"` to the set is the gate; the parallel `_KIND_TABLE` mapping is what `recent()` uses to compute `SELECT * FROM {table}` (line 1280).
- **Argparse `choices` lists are duplicated** — both `search_parser` and `recent_parser` in `scripts/little_loops/cli/session.py` carry a hard-coded list. Both must be updated; otherwise `ll-session recent --kind session_lifecycle` will reject the kind before reaching the runtime check.
- **Idempotency strategy**: Lifecycle events don't need natural uniqueness (two sweeps per session at the same UTC second is improbable), so plain `INSERT` is fine — but the `_apply_migrations` body MUST use `CREATE TABLE IF NOT EXISTS` so re-runs after a partial migration don't fail (per the v18 precedent at line 525).
- **`__all__` re-export** at `session_store.py:60-87` is the public-API contract. Adding `"record_session_lifecycle_event"` there is required for downstream imports; without it, `from little_loops.session_store import record_session_lifecycle_event` will fail in tests.
- **`_index()` FTS5 helper** at `session_store.py:705-718` is the only path to populate `search_index`; call it with `kind="session_lifecycle"`, `ref=session_id or ""`, `anchor=event`, `content=f"{event} {session_id or ''} {json.dumps(detail or {})}"[:512]` so `ll-session search --fts "<keyword>" --kind session_lifecycle` finds the rows.
- **Hook call sites are doubly safe**: `sweep_stale_refs.handle()` has an outer `except Exception: return LLHookResult(exit_code=0)` (line 202); `pre_compact.handle()` has the same pattern at lines 166–167. Even without the inner `contextlib.suppress`, a recorder exception would be swallowed by the outer catch. The inner wrap is still recommended for explicit intent.
- **`sweep_stale_refs` was re-homed to SessionStart** (per the file's docstring at lines 1–22, because the SessionEnd 1.5s ceiling isn't reliable for the sweep work). The handoff-sentinel remains on Stop. Don't confuse the two paths when wiring.

## Proposed Solution

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS session_lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    event TEXT NOT NULL,        -- handoff_needed | compaction | stale_ref_sweep | session_end
    detail TEXT,                -- JSON: {"threshold_pct":52} | {"findings":3} | ...
    head_sha TEXT,
    branch TEXT
);
CREATE INDEX IF NOT EXISTS idx_lifecycle_event ON session_lifecycle_events(event);
CREATE INDEX IF NOT EXISTS idx_lifecycle_session ON session_lifecycle_events(session_id);
```

Append the v27 migration to `_MIGRATIONS` in `session_store.py` (one beyond current v26 for `learning_test_events`, ENH-2466; re-verify the live `SCHEMA_VERSION` constant before merge). Bump `SCHEMA_VERSION = 26` → `SCHEMA_VERSION = 27`. Add `"session_lifecycle"` to `VALID_KINDS` (lines 218–234) and `"session_lifecycle": "session_lifecycle_events"` to `_KIND_TABLE` (lines 235–251).

### Producer wiring

- Add `record_session_lifecycle_event(db_path, *, ts, session_id, event,
  detail=None, head_sha=None, branch=None)` to `session_store.py`, best-effort
  guarded, FTS-indexing `event` (`kind="session_lifecycle"`).
- Wire via the host-agnostic Python hook handlers under
  `scripts/little_loops/hooks/` (not the bash adapters), consistent with how
  other hooks dispatch:
  - `context-handoff-sentinel` path → `event="handoff_needed"` with the threshold
    percent that tripped it, when it writes `.ll/ll-context-handoff-needed`.
  - `sweep_stale_refs.handle()` → `event="stale_ref_sweep"` with
    `detail={"findings": N}`.
  - PreCompact handler → `event="compaction"` with the token budget.
  - Session-end handler → `event="session_end"`.
- All writes best-effort per the EPIC-1707 contract — a hook must never fail
  because the DB is absent/locked.

### Read API

- `history_reader.recent_lifecycle_events(event=None, since=None, limit=50)`.
- `history_reader.handoff_frequency(since=None)` — count of `handoff_needed`.

### CLI surface

- `ll-session recent --kind session_lifecycle`.

## Acceptance Criteria

- Schema migration lands; `session_lifecycle_events` exists; `SCHEMA_VERSION`
  bumped.
- Crossing the auto-handoff threshold writes a `handoff_needed` row with the
  threshold percent in `detail`.
- A session-end stale-ref sweep writes a `stale_ref_sweep` row with the findings
  count.
- A compaction writes a `compaction` row.
- Every write is best-effort: with the DB absent/locked, each hook still
  completes its primary job (sentinel written, sweep advisory emitted) unchanged.
- `ll-session recent --kind session_lifecycle` returns rows.
- Tests cover: each event type, DB-absent graceful degradation, detail JSON
  round-trip.

## API/Interface

Three new public helpers and one new CLI `--kind` value:

```python
# scripts/little_loops/session_store.py
def record_session_lifecycle_event(
    db_path: Path | str,
    *,
    ts: str | None = None,        # ISO-8601 UTC; defaults to _now()
    session_id: str | None,       # event.session_id from LLHookEvent
    event: str,                   # handoff_needed | compaction | stale_ref_sweep | session_end | worktree_*
    detail: dict | None = None,   # JSON-serialized into TEXT column
    head_sha: str | None = None,
    branch: str | None = None,
) -> bool:                        # True if inserted, False on graceful-degrade
    ...

# scripts/little_loops/history_reader.py
@dataclass
class LifecycleEvent:
    id: int
    ts: str
    session_id: str | None
    event: str
    detail: dict | None
    head_sha: str | None
    branch: str | None

def recent_lifecycle_events(
    event: str | None = None,     # filter by event discriminator
    since: str | None = None,     # ISO-8601 lower bound
    limit: int = 50,
) -> list[LifecycleEvent]: ...

def handoff_frequency(since: str | None = None) -> int:
    """Count of `handoff_needed` events since the given ISO-8601 timestamp."""
    ...
```

CLI additions:

```
ll-session recent --kind session_lifecycle [--limit N] [--since TS]
ll-session search --fts "<keyword>" --kind session_lifecycle
```

The shared schema (`(ts, session_id, event, detail TEXT JSON, head_sha, branch)`)
is intentionally wide — `ENH-2509` reuses it with additional `worktree_create`
/ `worktree_merge` / `worktree_delete` event discriminators (per the
`/ll:decide-issue` Option A coordination at `ENH-2509:142`).

## Implementation Steps

_Stale v19/v20/v21-targeted implementation steps removed on 2026-07-19 — the live open schema-version slot is **v27**. See [Implementation Steps — 2026-07-19 (full-rewrite pass refresh)](#implementation-steps--2026-07-19-full-rewrite-pass-refresh) below for the authoritative steps._

### Codebase Research Findings

_Superseded by the 2026-07-19 full-rewrite pass below. The findings here are retained only because the
provenance trail is useful when comparing drift across passes; treat the
[Codebase Research Findings — 2026-07-19 (full-rewrite pass)](#codebase-research-findings--2026-07-19-full-rewrite-pass)
as authoritative._

- The **migration step alone** spans three coordinated edits to `session_store.py`: `_MIGRATIONS`, `SCHEMA_VERSION`, and the module docstring — implementers commonly miss the docstring update. _(Anchor drift: lines 1–38/102/119–130 are stale — see full-rewrite pass for current line numbers.)_
- The **CLI step** is purely additive to `VALID_KINDS`/`_KIND_TABLE` — no new dispatch branch in `main_session()` is needed because `recent()` already routes through `_KIND_TABLE`. _(The earlier note that "both `search_parser` and `recent_parser` choices lists are duplicated" is wrong — both call `choices=list(VALID_KINDS)` and inherit from one source.)_
- The **bash handoff-sentinel path** has no Python handler today. Two implementation choices: (a) shell out to `python3 -c '...'` (minimal diff, no new entry-point); (b) port `context-handoff-sentinel.sh` to Python and route through the dispatcher. The first matches the issue's "best-effort, never blocking" requirement without enlarging the hook surface. _(Step 28 of the v27 refresh locks this to the bash shell-out path.)_
- The **`session_end` row** is currently unspecified in the issue — consider whether the SessionEnd/SessionStart fallback in `sweep_stale_refs.handle()` should always emit a `session_end` row (even with zero findings) to make session-churn queryable. _(Step 31 of the v27 refresh resolves this as a separate sub-task requiring a new minimal handler — keep this deferred.)_
- **Idempotency**: lifecycle events don't need a UNIQUE key — two sweeps per session at the same UTC second are improbable — so plain `INSERT` (per `record_correction` / `record_skill_event`) is acceptable. _(Confirmed in Step 22 of the v27 refresh.)_


### Stale Reference Audit

_Audit superseded by the 2026-07-19 live reconciliation and full-rewrite pass below. The single surviving directive from this audit — "`session_id` is available on `LLHookEvent`" — is incorporated into Step 26 of the v27 Implementation Steps refresh (dispatcher fix); all other findings about `VALID_KINDS`/`_KIND_TABLE` line numbers and the `__all__` block have been re-anchored in the full-rewrite pass._

### Codebase Research Findings — 2026-07-19 Live Reconciliation

_Added by `/ll:refine-issue` — based on the current working tree. These findings
supersede stale schema-version, event-source, and session-ID assumptions above
without removing the earlier audit trail._

- **The live schema is v26, so the next open slot is v27 if nothing else lands
  first.** `scripts/little_loops/session_store.py:SCHEMA_VERSION` is `26`; the
  v26 migration creates `learning_test_events` for ENH-2466. The lifecycle
  migration must be appended after that entry, all `SCHEMA_VERSION == 26`
  assertions must move with it, and the upgrade test must bootstrap v26 rather
  than any previously documented v18/v20/v25 baseline. Continue to read the
  live constant at implementation time because sibling history work can claim
  v27 first.
- **No lifecycle foundation has landed yet.** The current tree still has no
  `session_lifecycle_events` table, `record_session_lifecycle_event()`,
  `LifecycleEvent`, `recent_lifecycle_events()`, or `handoff_frequency()`.
  ENH-2509's selected co-implementation therefore still requires this issue's
  shared schema/recorder/reader in the same change.
- **The hook dispatcher does not populate `LLHookEvent.session_id`.** Although
  `hooks/types.py:LLHookEvent` declares the field, `hooks/__init__.py:main_hooks()`
  currently constructs events with only `host`, `intent`, `payload`, and `cwd`.
  Update that constructor with `session_id=payload.get("session_id")`, and add a
  dispatcher test in `scripts/tests/test_hook_intents.py`; otherwise new Python
  producer calls that pass only `event.session_id` will persist `NULL` even when
  the host payload contains a session ID. Call sites should remain tolerant of
  hosts that genuinely omit it.
- **`context-monitor.sh` already owns the canonical crossing transition.** Its
  `main()` reads the PostToolUse payload, computes the final usage value, and
  sets `threshold_crossed_at` only on the first crossing of the configured
  `auto_handoff_threshold` (default 80%). Parse `.session_id` in the existing
  single `jq` extraction, set a local `crossed_now` flag while holding the
  state lock, persist the updated state, then perform the guarded recorder call
  after releasing the lock. This records one `handoff_needed` row per pressure
  episode; `check_compaction()` clears the crossing state, so a later
  post-compaction episode may correctly produce another row.
- **The 50% Stop sentinel is a fallback artifact, not a second handoff event.**
  `context-handoff-sentinel.sh` runs at every Claude Code Stop boundary, can
  overwrite the same sentinel repeatedly, does not consume stdin/session ID,
  and intentionally fires below the 80% auto-handoff threshold to leave room
  for a continuation turn. Keep it artifact-only in this issue; recording the
  same `handoff_needed` discriminator there would conflate two meanings and
  double-count a pressure episode. ENH-2507 remains the owner of continuous
  PostToolUse pressure samples and threshold telemetry; ENH-2495 owns the one
  discrete 80% lifecycle transition.
- **Only `pre_compact.handle()` owns the `compaction` row.** Claude Code invokes
  both `pre_compact` and `pre_compact_handoff` for one PreCompact occurrence.
  Record after `pre_compact.handle()` successfully writes
  `.ll/ll-precompact-state.json`, using that state's `compacted_at` as `ts` and
  detail such as `{"source": "host_precompact", "state_preserved": true}`.
  Do not emit from `pre_compact_handoff.handle()`; its prompt-freshness guard
  deduplicates a continuation artifact, not a database event. Also remove the
  stale proposed `budget_tokens` detail: this hook does not compute the LCM or
  retention-compaction budget.
- **`stale_ref_sweep` is a SessionStart observation.** The adapter named
  `session-end.sh` is deliberately registered under `SessionStart`, because the
  full issue scan is unsuitable for the real SessionEnd time budget. Refactor
  `sweep_stale_refs.handle()` to calculate one findings count (including zero)
  and emit one `stale_ref_sweep` row per invocation with detail such as
  `{"findings": N, "fix_mode": fix_mode, "trigger": "session_start"}`. It
  must never imply that the preceding session ended.
- **A real `session_end` needs a separate, minimal producer.** The only current
  Claude Code `SessionEnd` registration is `scratch-cleanup.sh`; Stop is not
  session termination, and Codex/OpenCode have no equivalent end callback.
  Add a small host-agnostic `record_session_end` intent/handler plus Claude Code
  adapter registration under the actual `SessionEnd` hook. Emit nothing for
  hosts without a true end signal rather than synthesizing rows from Stop,
  compaction, or the next SessionStart.
- **Kind and export registration remain separate.** Add `session_lifecycle` to
  the live `VALID_KINDS` tuple and `_KIND_TABLE`; both `search` and `recent`
  argparse choices already derive from that tuple, so there are no duplicated
  parser lists to edit. Separately add `session_lifecycle_event` to both
  `_EXPORT_TABLE_MAP` and `_EXPORT_DEFAULT_TABLES`, and call `_index()` from the
  recorder if `search --fts --kind session_lifecycle` remains part of the API.

#### Resolved Producer Contract

**Recommended**: use one authoritative producer per discriminator:

| Event | Canonical producer | Exactly-once boundary |
|-------|--------------------|-----------------------|
| `handoff_needed` | `context-monitor.sh` first 80% threshold transition | Once per pressure episode; compaction reset opens a new episode |
| `compaction` | `pre_compact.handle()` after state persistence | Once per host PreCompact occurrence |
| `stale_ref_sweep` | `sweep_stale_refs.handle()` at SessionStart | Once per completed sweep, including zero findings |
| `session_end` | New minimal handler registered on true Claude Code SessionEnd | Once per host termination callback; no synthetic cross-host fallback |
| `worktree_*` | ENH-2509's verified successful worktree operations | Once per successful create/merge/delete operation; no row for dry-run/failure |

This single-producer contract resolves the confidence-check's three open
questions without adding competing implementation options. Tests must prove
that the Stop sentinel and `pre_compact_handoff` create no duplicate lifecycle
rows, that `event.session_id` reaches Python handlers through `main_hooks()`,
and that a missing/locked database never changes each producer's primary
artifact or exit-code behavior.

### Codebase Research Findings — 2026-07-19 (full-rewrite pass)

_Added by `/ll:refine-issue --full-rewrite` on 2026-07-19 — supersedes
specific points in the prior "Codebase Research Findings" and "Implementation
Steps" sections where the codebase state, pattern reference, or anchor
drift has invalidated the earlier text. Existing content preserved per the
Preservation Rule; this section records the live state as of the
2026-07-19 evening snapshot._

#### Schema & Migration Anchor Refresh

- **Live `SCHEMA_VERSION = 26`** at `scripts/little_loops/session_store.py:216`.
  The next open slot is **v27** (not v19/v20/v21 as the prior "Coordination
  Note" and Implementation Steps imply). The v26 entry
  (`learning_test_events`, ENH-2466) sits at lines 835–855. Append the new
  migration after it with the trailing `,`; bump `SCHEMA_VERSION` on the
  same commit.
- **All `SCHEMA_VERSION == N` assertions must move with the bump.** Grep
  `scripts/tests/` for `SCHEMA_VERSION ==` — confirmed live sites to bump
  to 27: `scripts/tests/test_session_store.py` lines 1371–1372, 1817, 1932,
  1984, 2080, 3658, 3699; `scripts/tests/test_assistant_messages.py:88`;
  `scripts/tests/test_hook_session_start.py:307, 332, 341`.
- **Migration line range** is now `348–856` (not `208–545` as the original
  Integration Map cited). `_apply_migrations()` (lines 920–956) confirms
  every migration uses `CREATE TABLE IF NOT EXISTS` (v26 at line 843, v18
  at line 665) — so the new `session_lifecycle_events` migration should
  follow the same idempotent shape.

#### Pattern Anchor Refresh

- **`record_skill_event` (session_store.py:1095–1120) is the canonical
  modern pattern**, NOT `record_test_run_event`. The new recorder should
  model its body on `record_skill_event` (`connect(db_path)` + `try/finally
  conn.close()` + `ts = _now()` inside + `_index(...)` for FTS), and its
  return contract on `record_commit_event` (returns `bool`).
- **`record_test_run_event` (session_store.py:1474–1536) returns `None`**,
  NOT `bool` as the Integration Map's "Similar Patterns" note implied. This
  is drift from the original "closer to `record_test_run_event`" guidance;
  the issue's "INSERT or IGNORE on a natural UNIQUE" pattern is the
  `record_commit_event` shape (line 1344), not the test-run shape.
- **`record_learning_test_event` (session_store.py:1730–1805)** is the most
  recently added recorder and uses UPSERT keyed on a natural UNIQUE
  (`record_id`). Lifecycle events do NOT need this dedup (two sweeps per
  session at the same UTC second are improbable). Mention it only as the
  precedent if a future dedup constraint is added; today, plain `INSERT`
  per `record_correction` / `record_skill_event` is sufficient.
- **`_index()` lives at session_store.py:1012–1025.** Signature:
  `_index(conn, *, content, kind, ref, anchor, ts)`. Call shape for the
  new recorder: `_index(conn, content=f"{event} {session_id or ''} {json.dumps(detail or {})}"[:512], kind="session_lifecycle", ref=session_id or "", anchor=event, ts=ts)`.

#### Export Map Anchor Refresh

- **`_EXPORT_TABLE_MAP` lives at `session_store.py:3881–3896`**, NOT in
  `cli/backfill_worker.py` as the prior "Dependent Files" note claimed.
  The companion `_EXPORT_DEFAULT_TABLES` is at lines 3897–3909. Both are
  SEPARATE constants inside `session_store.py`. `backfill_worker.py` is a
  consumer but does not define them.
- The KEY in `_EXPORT_TABLE_MAP` is the *export* name (e.g.
  `"commit_event"`), distinct from the `VALID_KINDS` `"commit"` string.
  For lifecycle: add `"session_lifecycle_event": ("session_lifecycle_events", "ts")`.
- `_EXPORT_DEFAULT_TABLES` (lines 3897–3909) is a separate LIST — not a
  dict — that gates which tables `ll-session export` writes WITHOUT
  `--tables`. Without adding the entry here, `ll-session export` silently
  skips `session_lifecycle_events`. ENH-2461 documented the two-map
  pattern at `.issues/enhancements/P3-ENH-2461-...md:378`.

#### Dispatcher Fix — Explicit Step in Scope

- **`main_hooks()` (session_store.py hooks/__init__.py:102–143)** constructs
  `LLHookEvent(host, intent, payload, cwd)` at lines 132–137. It does NOT
  pass `session_id` even though `LLHookEvent.session_id: str | None = None`
  is defined at `hooks/types.py:44` and read in `from_dict` at `types.py:79`.
  Without this fix, every Python producer call passing
  `session_id=event.session_id` will persist `NULL`.
- The fix is one line: change the constructor at hooks/__init__.py:132–137
  to pass `session_id=payload.get("session_id")`. Call sites must remain
  tolerant of absent values (some hosts do not surface session_id).
- Add a dispatcher test in `scripts/tests/test_hook_intents.py` verifying
  session_id is populated when present in the host payload AND `None` when
  absent. The prior Live Reconciliation marked this in scope but did not
  enumerate it as a discrete Implementation Step — it is now Step 26 in
  the refresh below.

#### Sentinel Session-ID Plumbing Gap

- **`hooks/scripts/context-handoff-sentinel.sh` does NOT consume stdin or
  extract session_id** — Stop event in Claude Code does not surface
  session_id at the hook boundary. To link sentinel writes to a session,
  the state file (`.ll/ll-context-state.json`) would need to carry
  `session_id`, which `context-monitor.sh` would need to write on its next
  PostToolUse pass.
- Until that plumbing exists, the implementer should emit
  `event="handoff_needed"` from the sentinel path with `session_id=None`
  and accept the row-isolation consequence (sentinel rows are not
  correlatable to `issue_sessions`/ENH-2462 without the follow-on state
  format extension — defer that to a sub-issue).
- The sentinel's `|| true` envelope at `context-handoff-sentinel.sh:77–80`
  protects the hook exit code; the bash shell-out pattern `python3 -c '...'`
  followed by `|| true` is the minimal-diff path that satisfies the
  "never blocking" contract.

#### Producer Wiring — Live Code Anchors

- **`scripts/little_loops/hooks/sweep_stale_refs.py:handle()`** at line 141;
  return points at 174, 194, 201, 204. The findings count is at line 196
  (`[ll] {len(all_findings)} stale cross-issue reference(s) found:`).
  Insert the recorder call before line 201 (the findings-feedback return)
  with `event="stale_ref_sweep"`, `detail={"findings": N, "fix_mode": fix_mode, "trigger": "session_start"}`.
- **`scripts/little_loops/hooks/pre_compact.py:handle()`** at line 152;
  `compacted_at` set at line 130; `atomic_write_json(state_file, state)`
  at line 165; final return at line 169. Insert the recorder call AFTER
  line 165 succeeds, using `state["compacted_at"]` as `ts` and detail
  `{"source": "host_precompact", "state_preserved": true}`. **Do NOT**
  include `budget_tokens` in detail — this hook does not compute the LCM
  or retention-compaction budget (the prior Implementation Steps'
  `budget_tokens` proposal was incorrect).
- **`scripts/little_loops/hooks/pre_compact_handoff.py:handle()`** at
  line 152; prompt-freshness guard at lines 167–175. Do NOT emit a
  `compaction` row from this handler — its guard dedupes a continuation
  artifact, not a database event.
- **`hooks/scripts/context-monitor.sh:main()`** at line 213;
  `USAGE_PERCENT` computed at line 351; canonical 80% crossing transition
  at lines 354–410. The single `jq` extraction at line 45 is the natural
  extension point for `.session_id` (`jq -r '[(.tool_name // ""), (.transcript_path // ""), (.session_id // "")] | @tsv'`).
  Set the `crossed_now` flag under the state lock; perform the recorder
  call AFTER the lock is released.
- **`hooks/scripts/context-handoff-sentinel.sh`** Stop hook; sentinel
  write at lines 76–81; `SENTINEL_THRESHOLD` default 50 (line 32); `|| true`
  envelope protects the exit code. Emit `event="handoff_needed"` with
  `session_id=None` until state-file plumbing lands.

#### CLI Surface — Live Anchors

- **`search_parser` and `recent_parser`** in `scripts/little_loops/cli/session.py`
  both call `choices=list(VALID_KINDS)` (line 103 and line 115
  respectively). There is exactly ONE update point: the `VALID_KINDS`
  tuple at session_store.py:218–234. The prior Implementation Steps' note
  that "two duplicate choices lists" must be updated is **incorrect** —
  the auto-propagation means adding `"session_lifecycle"` to `VALID_KINDS`
  once is sufficient.
- **`recent()`** lives in `session_store.py:1908` and routes via
  `_KIND_TABLE[kind]`. The CLI call site is `cli/session.py:486`
  (`rows = recent(args.db, kind=args.kind, limit=args.limit)`).
- **`VALID_KINDS` is `tuple[str, ...]` at lines 218–234** (no leading
  underscore; the prior "Stale Reference Audit" reference to "frozenset"
  is incorrect — type is `tuple`).
- **`_KIND_TABLE` is `dict[str, str]` at lines 235–251**.
- **`__all__` block lives at session_store.py:68–102** (34 entries; last
  three are `"SkillEventCompletion"`, `"record_retirement"`,
  `"list_retirements"`, `"record_learning_test_event"`). Insert
  `"record_session_lifecycle_event"` after `"record_learning_test_event"`
  at line 101.
- **Package re-export precedent** for `from little_loops import *` is at
  `scripts/little_loops/__init__.py` lines 68–142. `record_issue_snapshot`
  at line 50 / 108 is the precedent for adding
  `record_session_lifecycle_event` to the top-level `__all__`.

#### Documentation Anchor Refresh

- **`docs/reference/API.md:7275`** is already drifted (says "Current
  schema version: **19**" while live is 26); bump to 27 in the same
  commit.
- **`docs/reference/API.md:7279`** has the import snippet
  `SCHEMA_VERSION, # 19` — bump to 27.
- **`docs/reference/API.md:4102–4103`** has a brace-list drift on
  `--kind {tool,file,issue,loop,correction,message,skill,cli,commit,test_run}`
  — missing `snapshot`, `usage`, `orchestration_run`, `loop_run`,
  `learning_test`. The implementer should update the brace list to
  match the live `VALID_KINDS` (or link to it) so future additions don't
  require a doc re-touch.
- **`docs/reference/CLI.md:2427` and `:2435`** have the same brace-list
  drift as above — update in the same commit.
- **`docs/ARCHITECTURE.md:670–678`** schema versions table ends at v20
  (already stale by 6 versions); add v21, v22, v23, v24, v25, v26 rows
  AND the new v27 row in the same commit (or file a follow-on cleanup
  issue for the v21–v26 backlog).
- **`docs/guides/HISTORY_SESSION_GUIDE.md`** schema versions table at
  lines 51, 60–75 — same v27 update needed.

#### Hook Dispatcher — Verified Live State

- The 8-intent dispatch table at `scripts/little_loops/hooks/__init__.py:74–99`:
  `pre_compact`, `pre_compact_handoff`, `session_start`, `session_end`,
  `user_prompt_submit`, `post_tool_use`, `pre_tool_use`, `edit_batch_nudge`.
- `session_end → sweep_stale_refs.handle` is the current mapping; this
  handler runs on SessionStart (per the `session-end.sh` script name
  registered under SessionStart in `hooks/hooks.json:16–26`), not
  SessionEnd. The 1.5s SessionEnd ceiling rationale is documented in
  `sweep_stale_refs.py:10–19`.
- The actual `SessionEnd` registration in `hooks/hooks.json:199–209` is
  `scratch-cleanup.sh` ONLY. Adding a real `session_end` producer (per
  the prior Live Reconciliation's recommendation) requires a new minimal
  Python handler + Claude Code adapter registration under the actual
  SessionEnd event — this is Step 31 in the Implementation Steps
  refresh below.

#### JSONL Logs & `raw_events` Do NOT Obviate Fire-Time Capture

_Added 2026-07-19 — empirical investigation of whether Claude Code session
logs / `raw_events` already carry these lifecycle events (they do not, in a
usable form)._

- **Hook executions DO appear in the Claude Code JSONL transcripts**, but only
  as `attachment` records. Each carries a nested `attachment` sub-object with
  `type: hook_success` (or a `blockingError` variant), `hookName` (e.g.
  `SessionStart:startup`), `hookEvent`, `toolUseID`, and the hook's raw
  `stdout` / `stderr` / `exitCode` / `command` / `durationMs`.
- **Only a subset of hook events is logged.** Across recent sessions the
  observed `hookEvent` values are `PreToolUse`, `PostToolUse`, `SessionStart`,
  `Stop`, `UserPromptSubmit` — **no `PreCompact` and no `SessionEnd`**. Note
  `Stop` ≠ `SessionEnd` (Stop fires at every turn boundary). So the two
  discriminators this issue most needs — `compaction` and a true `session_end`
  — are **absent from the JSONL entirely**, reinforcing that a new
  `session_end` producer (Step 31) and the `pre_compact.handle()` wiring
  (Step 30) are genuinely net-new, not transformable from logs.
- **`ll-session backfill` DOES ingest these lines** — `_backfill_raw_events()`
  (`session_store.py:3248`) loops every JSONL line with **no type filter** and
  `INSERT OR IGNORE`s one `raw_events` row each. The hook-bearing lines have a
  well-formed top-level `sessionId` + `timestamp`, so those columns populate
  correctly. Live `.ll/history.db` confirms ~135k `attachment` rows already
  present in `raw_events`.
- **But they are stored as opaque `attachment` blobs, not queryable hook
  events**, for three reasons:
  1. `event_type` is set to the top-level `record["type"]` = `"attachment"`
     (session_store.py:3285), so a hook execution is indistinguishable from any
     other attachment at the column level — all mixed into one bucket.
  2. The hook payload (`hookName`, `hookEvent`, `exitCode`, stdout) lives inside
     the nested `attachment` object within the zlib-compressed
     `raw_line`/`parsed_json` BLOB — not greppable without `_unpack_payload`.
  3. **No rebuild extractor, cache table, or `VALID_KINDS` entry consumes
     attachment/hook lines** — `grep` for `attachment`/`hook*` in the rebuild
     path returns zero hits, and no `%hook%`/`%attach%` table exists.
- **Implication for scope**: the raw hook-*execution* traces are durably
  captured in `raw_events` already (a future "query hook executions" feature
  would be a transform-from-`raw_events` job, orthogonal to this issue). But
  that does NOT shortcut ENH-2495: the semantic transitions (findings count,
  threshold %, compaction, session_end) are either absent from the logs or
  buried as unstructured stdout text. Fire-time structured capture into
  `session_lifecycle_events` remains the correct and necessary approach; the
  "no historical backfill — first-write-only" scope boundary stands, and the
  `raw_events` attachment rows are at best a fallback audit trail for the
  subset of hooks Claude Code chooses to log.

#### Decision-Point Note

- The fresh research did NOT surface any new binary alternatives. The
  Resolved Producer Contract from the prior Live Reconciliation
  (one authoritative producer per discriminator) is intact.
- `decision_needed` stays `false`. No `**Option A**`/`**Option B**`
  formatting was deposited that would require flipping it to `true`.

#### Live Reconciliation Addendum — 2026-07-19 (auto-refinement of decide-issue)

_Added by `/ll:refine-issue` (triggered as Phase 2.5 of `/ll:decide-issue ENH-2495 --auto`
because the decidability gate found 0 enumerable options in Proposed Solution)._
_Additive only — preserves the preceding Decision-Point Note verbatim._

- **Project config threshold drift.** `.ll/ll-config.json` has
  `context_monitor.auto_handoff_threshold: 50`, NOT the script default of 80
  quoted in earlier sections. `sentinel_threshold` is absent from the
  project config, so the script default of 50 applies. In this project's
  LIVE state, both thresholds resolve to 50%. The earlier "Threshold
  correction" reading is correct about the SCRIPT default (80%) but
  incomplete about the PROJECT override (50%). Step 27's directive to
  emit `USAGE_PERCENT` and `SENTINEL_THRESHOLD` from the resolved runtime
  values remains correct — the implementer emits what the script actually
  sees, not a hardcoded 80. The `detail={"threshold_pct": USAGE_PERCENT}`
  field captures whatever is in force at emission time.

- **Stop hook DOES surface `session_id` at the boundary.** Verified against
  https://code.claude.com/docs/en/hooks on 2026-07-19: `session_id` is
  listed as a default input field for ALL hook events, including Stop
  (verified under Claude Code v2.1.197+). This contradicts the prior
  "Sentinel Session-ID Plumbing Gap" section (lines 513–525 above), which
  asserted Stop does NOT surface session_id. The bash shell-out pattern in
  Step 28 could be extended to read `session_id` from the Stop payload's
  stdin and pass it to the recorder. The current `session_id=None`
  fallback is the conservative default until that extension lands; it is
  no longer gated on a state-file plumbing prerequisite.

- **Dispatcher session_id plumbing gap confirmed live.** `main_hooks()` at
  `scripts/little_loops/hooks/__init__.py` constructs `LLHookEvent(host,
  intent, payload, cwd)` without passing `session_id`. The
  `LLHookEvent.session_id: str | None = None` field exists at
  `hooks/types.py:43` (minor drift from the issue's claimed line 44 — line
  43 is the dataclass field annotation, line 44 is its surrounding
  docstring). Step 26's dispatcher fix remains in scope and is the
  critical-path dependency for Python producer call sites that pass
  `session_id=event.session_id`.

- **No new binary alternatives surfaced.** Three focused research agents
  (locator, analyzer, pattern-finder) returned on 2026-07-19. None
  proposed a competing Option A/B/C against the Resolved Producer
  Contract. Producer wiring has a single canonical approach, with the only
  live variants being threshold value (resolved at runtime via config,
  recorded in `detail`) and session_id plumbing (Step 26 dispatcher fix
  plus optional Step 28 stdin extension). The prior Decision-Point Note
  stands.

### Implementation Steps — 2026-07-19 (full-rewrite pass refresh)

_The following steps supersede the prior numbered list (steps 1–21) on
specific points where live anchors or pattern drift have invalidated the
earlier text. Each step cites the live anchor it replaces._

22. **Migration lands at v27**, not v19/v20. Append a new entry to
    `scripts/little_loops/session_store.py:_MIGRATIONS` AFTER the v26 entry
    at lines 835–855. Use `record_learning_test_event`'s migration shape as
    the closest precedent (`CREATE TABLE IF NOT EXISTS session_lifecycle_events (...)`
    + 2 indexes). Bump `SCHEMA_VERSION = 26 → 27` at line 216 in the same
    commit. Required SQL:

    ```sql
    CREATE TABLE IF NOT EXISTS session_lifecycle_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        session_id TEXT,
        event TEXT NOT NULL,    -- handoff_needed | compaction | stale_ref_sweep | session_end | worktree_*
        detail TEXT,            -- JSON: {"threshold_pct":80} | {"findings":3} | ...
        head_sha TEXT,
        branch TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_lifecycle_event ON session_lifecycle_events(event);
    CREATE INDEX IF NOT EXISTS idx_lifecycle_session ON session_lifecycle_events(session_id);
    ```

    No CHECK constraint on `event` — `ENH-2509`'s `worktree_*` values share
    the table. Per the prior Codebase Research Findings idempotency
    analysis, plain `INSERT` (no UNIQUE key) is acceptable; two sweeps per
    session at the same UTC second are improbable.

23. **`record_session_lifecycle_event()` signature follows `record_skill_event`
    + `record_commit_event`.** Place the function AFTER
    `record_learning_test_event` (session_store.py:1730–1805). Mirror
    `record_skill_event` (line 1095) for the body shape
    (`connect(db_path)` + `try/finally conn.close()` + `ts = _now()` inside),
    and `record_commit_event` (line 1344) for the `bool` return contract
    (True if inserted, False on graceful-degrade). Required signature:

    ```python
    def record_session_lifecycle_event(
        db_path: Path | str,
        *,
        session_id: str | None,
        event: str,
        detail: dict | None = None,
        head_sha: str | None = None,
        branch: str | None = None,
        ts: str | None = None,
    ) -> bool:
        ...
    ```

    **No `config` parameter (revised by `/ll:decide-issue` on 2026-07-19).**
    An earlier draft of this signature included `config: dict | None = None`,
    but `ENH-2509`'s locked shared signature (confirmed at `ENH-2509:255–256`)
    does not have it, and the two issues co-implement against one shared
    recorder per the Option A coordination (`ENH-2509:142`). Dropping `config`
    here reconciles the contract; this matches the API/Interface section
    above, which never carried the extra parameter.

    Use internal `try/except sqlite3.Error: logger.warning(...)` for
    graceful degradation (mirror `skill_event_context` lines 1230–1303);
    do NOT rely on caller-side `contextlib.suppress(Exception)` as the only
    safety net. Add to `__all__` after `record_learning_test_event` at
    line 101. Re-export at `scripts/little_loops/__init__.py` per the
    `record_issue_snapshot` precedent at line 50 / 108.

24. **One update point for `VALID_KINDS` propagation.** Add
    `"session_lifecycle"` to `session_store.py:VALID_KINDS` (lines 218–234)
    AND `"session_lifecycle": "session_lifecycle_events"` to `_KIND_TABLE`
    (lines 235–251). `search_parser` and `recent_parser` derive
    `choices=list(VALID_KINDS)` automatically at
    `cli/session.py:103, :115` — no CLI edit needed.

25. **Export registration requires BOTH `_EXPORT_TABLE_MAP` and
    `_EXPORT_DEFAULT_TABLES`** at `session_store.py:3881–3896` and
    `3897–3909` respectively (NOT in `cli/backfill_worker.py` as the prior
    "Dependent Files" note claimed). Add
    `"session_lifecycle_event": ("session_lifecycle_events", "ts")` to the
    map and `"session_lifecycle_event"` to the default list. Without BOTH,
    `ll-session export` silently skips `session_lifecycle_events` unless
    `--tables session_lifecycle_event` is passed explicitly.

26. **Dispatcher fix (explicit in scope).** Update
    `scripts/little_loops/hooks/__init__.py:main_hooks()` lines 132–137 to
    pass `session_id=payload.get("session_id")` when constructing the
    `LLHookEvent`. Add a dispatcher test in `scripts/tests/test_hook_intents.py`
    verifying session_id is populated when present in the host payload and
    `None` when absent (call sites must remain tolerant of absent values).
    Without this fix, every Python producer call passing
    `session_id=event.session_id` will persist `NULL`.

27. **Context-monitor shell extension.** Append `.session_id` to the single
    `jq` extraction at `hooks/scripts/context-monitor.sh:45`
    (`jq -r '[(.tool_name // ""), (.transcript_path // ""), (.session_id // "")] | @tsv'`).
    Set the `crossed_now` flag under the state lock; perform the recorder
    call AFTER the lock is released. Emit
    `event="handoff_needed"`, `detail={"threshold_pct": USAGE_PERCENT, "sentinel_threshold": SENTINEL_THRESHOLD, "token_count": TOKEN_COUNT, "context_limit": CONTEXT_LIMIT}`.

28. **Handoff-sentinel stays artifact-only (revised by `/ll:decide-issue` on
    2026-07-19).** This step previously directed
    `hooks/scripts/context-handoff-sentinel.sh` to also emit
    `event="handoff_needed"` after its sentinel write. That contradicted the
    Resolved Producer Contract (line 494–502) and the "50% Stop sentinel is a
    fallback artifact, not a second handoff event" finding (line 453–461):
    `context-monitor.sh`'s 80%-threshold crossing (Step 27) is the sole
    canonical producer for `handoff_needed`, one row per pressure episode.
    Recording the same discriminator again at the 50% Stop sentinel would
    double-count a single pressure episode (Stop fires on every turn boundary
    and can re-emit while the 80% state is already set). **Decision:**
    `context-handoff-sentinel.sh` makes NO `record_session_lifecycle_event`
    call in this issue — it continues to only write
    `.ll/ll-context-handoff-needed`. The new
    `test_python_failure_does_not_flip_exit_code` test (Step 32) still applies
    to the Step 27 `context-monitor.sh` shell-out, not to the sentinel script.

29. **Sweep producer.** Refactor
    `scripts/little_loops/hooks/sweep_stale_refs.py:handle()` (function at
    line 141) to calculate one findings count (including zero) and emit
    exactly ONE `stale_ref_sweep` row per invocation. Insert the recorder
    call before line 201 (the findings-feedback return). Detail:
    `{"findings": N, "fix_mode": fix_mode, "trigger": "session_start"}`.
    Pass `session_id=event.session_id` (None today, populated after
    Step 26 lands).

30. **Compaction producer.** Refactor
    `scripts/little_loops/hooks/pre_compact.py:handle()` (function at line
    152) to call the recorder AFTER `atomic_write_json(state_file, state)`
    at line 165 succeeds. Detail:
    `{"source": "host_precompact", "state_preserved": true}` (NOT
    `budget_tokens` — this hook does not compute the LCM or
    retention-compaction budget). Use `state["compacted_at"]` (set at
    pre_compact.py:130) as `ts`. Do NOT add a recorder call to
    `pre_compact_handoff.handle()` (its prompt-freshness guard at lines
    167–175 dedupes a continuation artifact, not a database event).

31. **`session_end` producer is OUT OF SCOPE for this issue (confirmed by
    `/ll:decide-issue` on 2026-07-19 — see Scope Boundaries).** File a
    follow-on sub-issue for it; do not implement in this PR. Retained below
    for the follow-on issue's reference: add a minimal
    Python intent handler (suggested name
    `scripts/little_loops/hooks/session_end_record.py`) that emits
    `event="session_end"`, `detail={"trigger": "host_sessionend"}`. Register
    it under the `session_end` intent in `hooks/__init__.py:_dispatch_table()`
    (lines 74–99) — but this conflicts with the existing
    `session_end → sweep_stale_refs.handle` mapping; use a NEW intent name
    (e.g. `session_end_record`) and register it separately. Add a Claude
    Code adapter script under `hooks/adapters/claude-code/session-end-record.sh`
    and register it on the actual `SessionEnd` event in `hooks/hooks.json`.
    Codex/OpenCode skip (no equivalent end callback exists). The handler
    must be idempotent: multiple SessionEnd registrations must not produce
    multiple rows per session.

32. **Test coverage adds** (in addition to the prior Implementation Steps
    coverage):
    - `TestSchemaV27` in `scripts/tests/test_session_store.py` mirroring
      `TestSchemaV20UsageEvents` at line 3228.
    - `test_v26_db_upgrades_gains_session_lifecycle_events` using
      `_bootstrap_schema_at(db, 26)` (helper at lines 3901–3921) +
      `ensure_db(db)`.
    - `TestRecordSessionLifecycleEvent.test_roundtrip` mirroring
      `TestRecordTestRunEvent.test_roundtrip` at lines 4372–4424.
    - `TestRecordSessionLifecycleEvent.test_graceful_when_store_unwritable`
      mirroring `test_hook_post_tool_use.py:184–209` —
      `monkeypatch.setattr(session_store, "connect", boom)` to force
      `OperationalError`; assert recorder returns `False` (NOT raises).
    - `TestRecentLifecycleEvents` + `TestHandoffFrequency` in
      `scripts/tests/test_history_reader.py`.
    - `test_writes_lifecycle_row` in
      `scripts/tests/test_sweep_stale_refs.py` (verify graceful drop on
      broken DB).
    - `test_writes_compaction_lifecycle_row` in
      `scripts/tests/test_pre_compact.py`.
    - `test_writes_lifecycle_row_on_threshold_crossing` +
      `test_python_failure_does_not_flip_exit_code` in
      `scripts/tests/test_hooks_integration.py:TestContextHandoffSentinel`.

33. **Documentation updates** (live anchors confirmed):
    - `docs/reference/API.md:7275` — bump "Current schema version: 19"
      (already drifted by 7 versions) → 27. Also bump `:7279` import
      snippet `SCHEMA_VERSION, # 19` → 27. Fix the brace-list drift at
      `:4102–4103` to enumerate the live `VALID_KINDS` (or link to it).
    - `docs/reference/CLI.md:2427, :2435` — same brace-list drift fix.
      Add `ll-session recent --kind session_lifecycle` example at
      `:2510–2512`.
    - `docs/ARCHITECTURE.md:670–678` schema versions table — add v27 row
      AND backfill v21–v26 rows (or file a follow-on cleanup issue for
      the backlog); extend the mermaid sequence diagram at `:714–729` to
      include `sweep_stale_refs`/`pre_compact`/`context-handoff-sentinel`
      as DB writers; add Components table rows at `:753–754` for the new
      producers.
    - `docs/guides/HISTORY_SESSION_GUIDE.md` lines 51, 60–75 (schema
      versions table), 32–43 (task→command table), 80–100 ("What Gets
      Recorded"), 170 (`--kind` enumeration).
    - `docs/guides/BUILTIN_HOOKS_GUIDE.md:59` (PostToolUse writers list),
      `:94` (flow diagram), `:434` (`analytics.capture.session_lifecycle_events`
      flag — precedent: `usage_events`).
    - `docs/reference/CONFIGURATION.md:1162–1178`
      (`hooks.pre_compact.rubric.*` block) — mention compaction events
      flow into `session_lifecycle_events`.
    - `.claude/CLAUDE.md` lines 141–142, 186, 196, 203, 218 — add
      `session_lifecycle` to kind listings where `recent`/`search`/`compact`
      are documented.

## Sources

- `thoughts/history-db-expand-wiring.md` — §2 (issue↔session linkage / lifecycle)
- EPIC-2457 review (2026-07-05) — item #4
- `hooks/hooks.json` — hook registrations (only `post-tool-use` and `user-prompt-check` write to DB; no lifecycle hook does)
- `hooks/scripts/context-handoff-sentinel.sh`, `hooks/scripts/context-monitor.sh`
- `scripts/little_loops/hooks/sweep_stale_refs.py` — sweep findings count
- `reference_loop_handoff_mechanics` (memory) — CONTEXT_HANDOFF marker semantics
- ENH-2462 — explicit `session_id` on issue_events (the linkage this complements)

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions; hook write-paths |
| `docs/reference/API.md` | `session_store`, hooks handlers |
| `docs/reference/CLI.md` | New `ll-session --kind` value |

## Impact

- **Priority**: P3 — observability enhancement with no user-facing behavior
  change; valuable but not blocking. Justified by the inability to answer
  "how often does context handoff trigger?" or "is stale-ref churn
  improving?" from the existing data.
- **Effort**: Medium — one schema migration + one new public helper +
  four hook call sites + CLI plumbing + tests + doc drift fixes across
  ~12 files. Reuses the established `record_test_run_event` /
  `record_commit_event` patterns, so per-file complexity is low.
- **Risk**: Low-Medium — additive (new table, no schema breaking changes
  to existing tables); recorder is best-effort with `try/except
  sqlite3.Error` graceful-degradation, so a bug cannot block hooks;
  coordination with `ENH-2509` (shared `session_lifecycle_events` table)
  is already locked-in via the `/ll:decide-issue` Option A decision.
- **Breaking Change**: No — purely additive. New table, new `VALID_KINDS`
  entry, new public helpers, new CLI `--kind` value. Existing schemas
  unchanged; existing hooks continue to write to their original tables.

## Resolution

Implemented per the Resolved Producer Contract and the 2026-07-19 full-rewrite
Implementation Steps (22–33):

- **Schema**: v27 migration adds `session_lifecycle_events`
  `(id, ts, session_id, event, detail, head_sha, branch)` + two indexes;
  `SCHEMA_VERSION` bumped 26→27; `"session_lifecycle"` added to `VALID_KINDS`/
  `_KIND_TABLE`; `record_session_lifecycle_event()` added to `session_store.py`
  (models `record_skill_event`'s body shape + `record_commit_event`'s `bool`
  return contract, per Step 23); `_EXPORT_TABLE_MAP`/`_EXPORT_DEFAULT_TABLES`
  gained `session_lifecycle_event` entries (Step 25).
- **Producers** (one authoritative producer per discriminator, per the
  Resolved Producer Contract): `context-monitor.sh`'s first 80%-threshold
  crossing per pressure episode → `handoff_needed` (bash shell-out with
  `|| true`, Step 27 — `context-handoff-sentinel.sh` stays artifact-only per
  Step 28); `pre_compact.handle()` after state persistence → `compaction`
  (Step 30 — `pre_compact_handoff.handle()` emits nothing, locked in by a
  negative-control test); `sweep_stale_refs.handle()` once per invocation
  including zero findings → `stale_ref_sweep` (Step 29).
- **Dispatcher fix** (Step 26): `main_hooks()` now passes
  `session_id=payload.get("session_id")` when constructing `LLHookEvent`.
- **Bug found and fixed during implementation**: the original single-jq-pass
  extraction in `context-monitor.sh` used `@tsv` + `IFS=$'\t' read`, which
  silently shifts fields when an interior field (`transcript_path`) is empty —
  bash treats tab as "IFS whitespace" and collapses consecutive delimiters
  even when IFS is set to tab alone. Switched to `\x1f` (unit separator) via
  `join("")`, which is not whitespace-collapsed.
- **Read API**: `history_reader.LifecycleEvent` (parses `detail` JSON into a
  `dict`, unlike sibling `*_json` columns which stay raw strings),
  `recent_lifecycle_events(event, since, limit)`, `handoff_frequency(since)`.
- **CLI**: `session_lifecycle` flows through `VALID_KINDS` automatically —
  no duplicated argparse choices lists to edit, confirming the full-rewrite
  pass's anchor correction over the earlier (incorrect) "two lists" note.
- **Out of scope, confirmed unchanged**: a true `session_end` producer
  (Step 31) remains deferred to a follow-on sub-issue — not implemented here.
- **Tests**: `TestSchemaV27`, `TestRecordSessionLifecycleEvent`,
  `TestRecentLifecycleEvents`, `TestHandoffFrequency`, per-producer
  graceful-degradation tests (`sweep_stale_refs`, `pre_compact`,
  `context-monitor.sh` subprocess-level), the `pre_compact_handoff`
  negative-control test, and the dispatcher `session_id` propagation tests.
  All 11 `SCHEMA_VERSION == 26` test-literal sites plus 8 additional
  `int(row[0]) == 26` / `int(version[0]) == 26` full-migration-check sites
  (not caught by the issue's original grep, which only searched for the
  `SCHEMA_VERSION ==` pattern) were bumped to 27. Full suite:
  15518 passed, 38 skipped.
- **Docs**: `docs/ARCHITECTURE.md`, `docs/reference/API.md`,
  `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`,
  `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/reference/CONFIGURATION.md`,
  `.claude/CLAUDE.md` updated. Deferred as follow-on cleanup (not required by
  Acceptance Criteria): backfilling the v21–v26 schema-version-table rows in
  `docs/ARCHITECTURE.md`/`HISTORY_SESSION_GUIDE.md` that had already drifted
  before this issue (those tables were current as of this pass, so no backlog
  existed); the optional `analytics.capture.session_lifecycle_events` config
  gate proposed in the second-pass Wiring Additions (not in Acceptance
  Criteria or core Scope Boundaries — lifecycle producers are unconditional
  best-effort writes, same as `corrections`/`file_events` today without a
  dedicated flag).

## Status

**Open** | Created: 2026-07-05 | Priority: P3

---

## Scope Boundaries

- **In scope**:
  - New `session_lifecycle_events` table + **v27** migration (verified open
    slot on 2026-07-19; live `SCHEMA_VERSION = 26` at
    `scripts/little_loops/session_store.py:216`; re-verify before merge).
  - `record_session_lifecycle_event()` recorder, `_VALID_KINDS` /
    `_KIND_TABLE` registration, `__all__` re-export.
  - Wiring four lifecycle event producers: `context-handoff-sentinel.sh`
    (bash shell-out, `|| true`), `sweep_stale_refs.handle()`,
    `pre_compact.handle()`, `pre_compact_handoff.handle()` (optional).
  - Read API: `history_reader.recent_lifecycle_events()` +
    `handoff_frequency()`.
  - CLI plumbing: `session_lifecycle` in `search`/`recent` `--kind`
    choices; `_EXPORT_TABLE_MAP` + `_EXPORT_DEFAULT_TABLES` entries.
  - Tests: `TestRecordLifecycleEvent`, `TestSchemaV??` (using live
    `SCHEMA_VERSION`), `TestRecentLifecycleEvents`, `TestHandoffFrequency`,
    per-hook graceful-degradation tests, CLI `--kind` acceptance.
  - Doc updates: `docs/ARCHITECTURE.md`, `docs/reference/API.md`,
    `docs/reference/CLI.md`, `docs/guides/HISTORY_SESSION_GUIDE.md`,
    `docs/guides/BUILTIN_HOOKS_GUIDE.md`, `docs/reference/CONFIGURATION.md`,
    `.claude/CLAUDE.md`.

- **Out of scope**:
  - A real `session_end` producer (Step 31): new intent name, new Python
    handler, new Claude Code `SessionEnd` adapter registration. **Deferred to
    a follow-on sub-issue (resolved by `/ll:decide-issue` on 2026-07-19)** —
    the Impact/Effort estimate and the In-Scope "four lifecycle event
    producers" list above already excluded it, and Acceptance Criteria never
    listed a `session_end` row as a pass condition (only Expected Behavior's
    illustrative event list mentioned it). Filing it separately also avoids
    the intent-name collision with the existing
    `session_end → sweep_stale_refs.handle` dispatch mapping inside this
    issue's blast radius.
  - Migrating existing post-hoc data into `session_lifecycle_events` (no
    historical backfill — first-write-only).
  - Changing the meaning of existing `VALID_KINDS` values (tool/file/issue/
    loop/correction/message/skill/cli/commit/test_run/snapshot/usage all
    remain semantically identical).
  - Adding CHECK constraints on `event` discriminator — kept open so
    `ENH-2509`'s `worktree_*` values can share the table.
  - Replacing bash `context-handoff-sentinel.sh` with a Python handler —
    bash shell-out with `|| true` is the minimal-diff path that satisfies
    the "never blocking" contract.
  - Codex/OpenCode `pre_compact_handoff` registration (intentional adapter
    gap; `pre_compact` path still emits compaction events on those hosts).

### Coordination Note (added by `/ll:audit-issue-conflicts`)

_Refreshed by `/ll:refine-issue` (full-rewrite pass) on 2026-07-19: live
`SCHEMA_VERSION = 26` at `scripts/little_loops/session_store.py:216`; the
next open slot is **v27**._

This issue's Integration Map originally assumed it was the sole claimant of
the next schema-version slot ("bump `SCHEMA_VERSION = 18` → `19`"). At least
ten other active EPIC-2457 siblings (ENH-2463, ENH-2464, ENH-2465, ENH-2492,
ENH-2493, ENH-2494, ENH-2496, ENH-2497, ENH-2498, ENH-2511) independently made
the same "18→19" claim in their own Integration Maps — they cannot all be v19.
Verified against current code (`scripts/little_loops/session_store.py`):
`SCHEMA_VERSION` is now **26** (v17=`commit_events`/ENH-2458 done,
v18=`test_run_events`/ENH-2459 done, v19=`raw_events`/ENH-2581 done,
v20=`usage_events`/ENH-2461 done, v21=FEAT-2478 OTel columns,
v22=`orchestration_runs`/ENH-2492 done, v23=`loop_runs`/ENH-2463 done,
v24=`tool_events.agent_type`/ENH-2497 done, v25=`tool_events` MCP
columns/ENH-2511 done, v26=`learning_test_events`/ENH-2466 done).
**ENH-2495 lands at v27.** At implementation time, read the live
`SCHEMA_VERSION` constant to confirm v27 is still the open slot — sibling
history work can claim v27 first; each child lands its own migration at
whatever version is open when it is implemented (no coordinated release; per
EPIC-2457's own "no shared helper module is required" scope note).

Note also that **ENH-2509** (worktree lifecycle events) is an intentional,
already-coordinated widening of this issue's `session_lifecycle_events` table
— not a conflict.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-19 (re-run; content unchanged since prior run — no edits landed since the 22:14:30 wire-issue pass). `decision_needed` flipped to `true` this run: the Outcome Risk Factors below contain the Phase 4.6 signal phrases "unresolved decision" and "resolve before implementing", which the prior run's notes already carried but did not act on._

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 63/100 → LOW

### Outcome Risk Factors
- Unresolved decision: the Resolved Producer Contract keeps the 50% Stop
  sentinel artifact-only, while refreshed Step 28 and Scope Boundaries still
  direct it to emit `handoff_needed`; resolve before implementing to prevent
  double-counting pressure episodes.
- Unresolved decision: ENH-2509's shared recorder signature (per its
  `/ll:decide-issue` Option A lock) does not include the `config` parameter
  proposed by this issue; reconcile the shared contract before merging the
  coordinated change.
- Unresolved decision: Step 31 introduces a new `session_end_record` intent
  to avoid colliding with the existing `session_end → sweep_stale_refs.handle`
  dispatch mapping, but the Section "Scope Boundaries" In-Scope list still
  enumerates only the four original hook call sites without the new
  producer; resolve whether `session_end` recording is in scope or deferred
  to a sub-issue before implementing.
- Moderate blast radius across roughly 30 production, test, and documentation
  files with mixed per-site edits (SQL migration, tuple/dict entries, bash
  shell-out, dispatcher fix, prose updates); stage foundation, producer
  wiring, and validation/docs as reviewable slices so each stage can be
  verified against the live schema version.
- Best-effort shell/Python boundaries can hide partial wiring: the bash
  shell-out pattern `python3 -c '...' || true` must be paired with the
  dedicated `test_python_failure_does_not_flip_exit_code` integration test
  to prove the DB-write failure path does not change the hook's primary
  exit code.

### Decision Rationale

Resolved by `/ll:decide-issue` on 2026-07-19. These were not competing
`### Option A`/`### Option B` alternatives — the decidability scan (Phases
2.5/3) found zero enumerable options in Proposed Solution or Codebase
Research Findings — so no scoring pass applied. Instead, all three
`/ll:confidence-check` "unresolved decision" risk factors were prose
contradictions between later research passes and earlier, now-superseded
implementation steps. Each is resolved in favor of the most recent,
best-evidenced pass:

1. **Handoff-sentinel double-emission** — Step 28 is rewritten so
   `context-handoff-sentinel.sh` stays artifact-only (no
   `record_session_lifecycle_event` call). The Resolved Producer Contract
   (single canonical producer per discriminator) and the explicit
   "50% Stop sentinel is a fallback artifact, not a second handoff event"
   finding both predate and outrank Step 28's stale instruction to also emit
   from the Stop path.
2. **`config` parameter mismatch** — dropped from Step 23's signature. This
   issue and `ENH-2509` share one recorder per the already-locked Option A
   co-implementation decision (`ENH-2509:142`); `ENH-2509`'s confirmed
   signature (`ENH-2509:255–256`) has no `config` param, and this issue's own
   API/Interface section never carried one either — Step 23 was the sole
   drifted copy.
3. **`session_end` scope ambiguity** — Step 31 (`session_end` producer) is
   moved to Out of Scope and deferred to a follow-on sub-issue. The
   Impact/Effort estimate and the In-Scope producer list already excluded it
   (both count exactly four hook call sites), and Acceptance Criteria never
   required a `session_end` row — only Expected Behavior's illustrative list
   mentioned it. Deferring also sidesteps the `session_end` intent-name
   collision with the existing `sweep_stale_refs` dispatch mapping without
   growing this issue's blast radius further.

## Session Log
- `/ll:manage-issue fix` - 2026-07-19T23:24:39Z - `b0f63cd3-69e9-4e57-ad7d-00b5f1b7b80c.jsonl`
- `/ll:ready-issue` - 2026-07-19T22:42:53 - `51b0ed9e-d527-4b05-9340-b38244f69150.jsonl`
- `/ll:confidence-check` - 2026-07-19T00:00:00Z - `926de526-7a59-4baf-abfe-5ac37cfae19f.jsonl`
- `/ll:decide-issue` - 2026-07-19T22:36:41 - `a4d44b24-82b1-4bf5-9f50-d3f765694441.jsonl`
- `/ll:confidence-check` - 2026-07-19T22:25:57+00:00 - `33b2994d-51c1-4020-ab32-9872d899c1b8.jsonl`
- `/ll:wire-issue` - 2026-07-19T22:14:30 - `1bc4af3f-adca-450d-8add-6215fd0d1baa.jsonl`
- `/ll:decide-issue` - 2026-07-19T21:39:15 - `2a7e7982-bd66-4387-8634-f83d50258c40.jsonl`
- `/ll:refine-issue` - 2026-07-19T21:38:24 - `2a7e7982-bd66-4387-8634-f83d50258c40.jsonl`
- `/ll:confidence-check` - 2026-07-19T22:30:00+00:00 - `08ceda0d-2689-4844-aff8-3a17f78ec11e.jsonl`
- `/ll:confidence-check` - 2026-07-19T21:15:47+00:00 - `b2e2dd56-ba34-41ae-8e5b-1a738c701859.jsonl`
- `/ll:refine-issue` - 2026-07-19T21:07:47 - `fb9deb39-7de4-47c9-8dae-623bc72a3cdf.jsonl`
- `/ll:decide-issue` - 2026-07-19T20:55:06 - `698b8bb2-130e-48d6-a2d7-5f7573b4c92e.jsonl`
- `/ll:refine-issue` - 2026-07-19T20:51:08 - `57ecf04b-c4c6-4c01-82f1-86902c32fa21.jsonl`
- `/ll:confidence-check` - 2026-07-19T20:59:05+00:00 - `24943062-dd24-4cde-a308-f80deae18969.jsonl`
- `/ll:confidence-check` - 2026-07-19T20:31:37+00:00 - `9e59a6e2-2a2d-4a6c-8a64-3c652a66068c.jsonl`
- `/ll:format-issue` - 2026-07-19T20:28:07 - `7545f370-99d5-4dbc-b5a4-2b810f64d7c9.jsonl`
- `/ll:wire-issue` - 2026-07-16T23:33:29 - `93c7c3d0-7fc2-409d-9882-227ad5f6e063.jsonl`
- `/ll:refine-issue` - 2026-07-16T15:15:18 - `165a14ee-791b-4c16-a333-4b3b4da4a314.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:48 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T00:57:52 - `f072a647-96ed-4b8d-bdc1-936243abf1c4.jsonl`
- audit - 2026-07-06 - Corrected "only post-tool-use writes to history.db": the `user-prompt-check.sh` → `user_prompt_submit.py` path also writes (corrections + skill events). Core claim stands — no session-*lifecycle* hook writes to the DB. Fixed sweep_stale_refs path.
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
