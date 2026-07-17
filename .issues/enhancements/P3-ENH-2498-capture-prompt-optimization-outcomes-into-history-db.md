---
id: ENH-2498
title: Capture prompt-optimization outcomes into history.db
type: ENH
priority: P3
status: open
discovered_date: 2026-07-05
captured_at: "2026-07-05T00:00:00Z"
discovered_by: capture-issue
parent: EPIC-2457
labels:
  - enhancement
  - history-db
  - captured
---

# ENH-2498: Capture prompt-optimization outcomes into history.db

## Summary

The `UserPromptSubmit` hook (`scripts/little_loops/hooks/user_prompt_submit.py`)
rewrites vague user prompts when `prompt_optimization.enabled` is set: it renders
`optimize-prompt-hook.md` to stdout, instructing the model to expand the prompt
with codebase context (template-only in `quick` mode, or via the
`prompt-optimizer` agent in `thorough` mode). This is the one hook that *mutates
user intent* — yet nothing records that it fired, in what mode, or whether the
optimization was accepted. The hook already writes `record_correction` and
`record_skill_event` for the *same* prompt (lines 84 & 92), but the optimization
event itself is invisible, so there is no way to answer "how often is
optimization offered, and does it actually help?" This is the missing signal
class that would let the feature be evaluated on its own merits.

## Motivation

- **The feature is unmeasured.** `prompt_optimization` is a config-schema feature
  (`quick`/`thorough` modes, `confirm`, `bypass_prefix`) that changes what the
  model acts on. With no persisted record, offer-rate, mode mix, and any
  before→after signal can only be reconstructed by hand from raw JSONL.
- **Symmetry with the rest of EPIC-2457.** ENH-2460 gave skills a success signal;
  ENH-2461 gives real token counts; this gives the prompt-rewrite path its own
  observability row. It closes a producer that already sits inches from two
  existing DB writes in the same handler.
- **Cheap offer-side capture.** The hook knows everything needed for the *offer*
  row at fire time (mode, confirm, bypass reason, prompt length, session_id) —
  one more best-effort write next to the two already there.

## Current Behavior

- `user_prompt_submit.py::handle()` renders the optimization template to stdout
  and returns; it records a `correction` and/or `skill_event` for the prompt but
  **nothing** about the optimization offer.
- The accepted/optimized prompt text is produced by the model *in-conversation*,
  so it exists only in the transcript/JSONL, never in `.ll/history.db`.
- No `--kind prompt_opt` in `ll-session`; `ll-ctx-stats` does not surface it.

## Expected Behavior

- Every time the hook offers optimization (or explicitly bypasses it), a row lands
  in a `prompt_opt_events` table recording mode, whether it fired vs. was
  bypassed (and why), the raw prompt length, and `session_id`.
- The accepted/rejected outcome and before→after delta are reconstructed
  **best-effort** by a JSONL backfill pass (like the other `_backfill_*`
  producers), since the hook return cannot observe the model's response.
- `ll-session recent --kind prompt_opt` returns rows; `ll-session search --fts`
  matches the optimized-prompt text once backfilled.

## Integration Map

_Added by `/ll:refine-issue` — verified against the codebase (line numbers current as of research):_

### Files to Modify

- `scripts/little_loops/session_store.py` — the bulk of the change:
  - Append a **v19** entry to `_MIGRATIONS` (list at line 208; v18 `test_run_events`
    block at lines 521–544 is the closest DDL precedent) with the
    `prompt_opt_events` table + `idx_prompt_opt_events_session` /
    `idx_prompt_opt_events_mode` indexes. Use `CREATE TABLE/INDEX IF NOT EXISTS`.
  - Bump the `SCHEMA_VERSION` constant at line 102 (`18 → 19`); it must equal
    `len(_MIGRATIONS)`, so adding the migration entry and bumping the constant go
    together. `_apply_migrations()` (line 609, runs under `BEGIN IMMEDIATE`) applies
    it and stamps `meta(key='schema_version')`.
  - Add `"prompt_opt"` to `_VALID_KINDS` (frozenset, line 104) and
    `"prompt_opt": "prompt_opt_events"` to `_KIND_TABLE` (dict, line 119). `recent()`
    (line 1268) is generic over `_KIND_TABLE`, so no new dispatch branch is needed.
  - Add `record_prompt_opt_event()` — model on `record_commit_event` (line 1041) /
    `record_test_run_event` (line 1171): keyword-only args after `db_path`, `connect()`
    + `_now()` for the `ts` fallback, plain `INSERT`, then `_index(conn, kind="prompt_opt",
    ref=session_id or "", anchor=mode, content=...[:512], ts=ts)` so FTS matches.
  - Add `_backfill_prompt_opt(conn, jsonl_files) -> int` — model on `_backfill_skill_events`
    (line 1800). It **UPDATEs** the live offer row (matched by session_id+ts) with
    `optimized_len` / `optimized_text` / `accepted`, then `_index(...)` the optimized text.
  - Register `_backfill_prompt_opt` in **both** `backfill()` (line 2441) and
    `backfill_incremental()` (line 2497), adding a `"prompt_opt_events"` key to each
    count dict and a `_PROMPT_OPT_KEY = "last_backfill_ts_prompt_opt_events"` watermark
    (mirror the `_SKILL_KEY` / assistant-messages watermark self-healing at lines ~2549/2574).
  - Add `"record_prompt_opt_event"` to `__all__` (line 60) and update the module docstring
    (lines 1–38) and the `recent()` docstring `Kinds:` line to mention `prompt_opt`.
  - Optional: add `"prompt_opt_event": ("prompt_opt_events", "ts")` to `_EXPORT_TABLE_MAP`
    (line 2791) if `ll-session export` should include the table.
- `scripts/little_loops/hooks/user_prompt_submit.py` — `handle()` (line 61). Add
  best-effort `record_prompt_opt_event()` calls at each return point, wrapped in the
  same `with contextlib.suppress(Exception):` pattern and gated by the same
  `feature_enabled(config, "analytics.enabled")` check that already wraps
  `record_correction` (line 84) and `record_skill_event` (line 92). **The gate lives
  at the call site (line 78), not inside the recorder** — matching the two siblings.
- `scripts/little_loops/history_reader.py` — add a `PromptOptEvent` dataclass near
  `CommitEvent` (line ~124), `recent_prompt_opt_events(mode=None, since=None, limit=50)`
  (model on `recent_commit_events`, line 524), and `prompt_opt_offer_rate(since=None)`
  (model on `summarize_skills`, line 472). Both use `_connect_readonly` (line 235) +
  `_row_to_dataclass` (line 252) and return `[]` on `sqlite3.Error`.
- `scripts/little_loops/cli/session.py` — add `"prompt_opt"` to **both** argparse
  `choices=[...]` lists: `search` parser (lines ~92–103) **and** `recent` parser
  (lines ~115–126). Omitting either makes argparse reject the kind before the runtime
  `_VALID_KINDS` check is reached.

### Additional session_store.py / cli surfaces (Wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

- `scripts/little_loops/session_store.py:1-38` — module docstring. Add a one-line
  `record_prompt_opt_event(db,...):   write one row to ``prompt_opt_events`` +
  search_index (ENH-2498)` entry alongside the sibling writers
  (`record_commit_event`/`record_test_run_event`) [Agent 2 finding].
- `scripts/little_loops/session_store.py:61-93` — `__all__` exports. Add
  `"record_prompt_opt_event"` next to `"record_commit_event"` /
  `"record_test_run_event"` (note: those two are *not* currently in `__all__` — a
  pre-existing inconsistency; follow precedent and add only the new symbol unless
  backfilling siblings is in scope) [Agent 2 finding].
- `scripts/little_loops/session_store.py:244-255` — `_KINDLESS_TABLES`. **Do NOT**
  add `prompt_opt_events` here. `ll-verify-kinds` (ENH-2581) asserts every
  `CREATE TABLE` has a `_KIND_TABLE` entry **or** is explicitly kindless; adding
  it would silently disable the lint gate for this table [Agent 2 finding].
- `scripts/little_loops/session_store.py:1468-1472` — `recent()` docstring
  `Kinds:` line. Append `, prompt_opt` to the existing enumeration
  (`tool, file, issue, loop, correction, message, skill, cli, commit, test_run,
  usage`) [Agent 2 finding, issue §8a already calls out].
- `scripts/little_loops/session_store.py:2818-2835` — `_REBUILD_TABLES` /
  `_REBUILD_SEARCH_KINDS`. Add `"prompt_opt_events"` to `_REBUILD_TABLES`
  (alongside `"usage_events"` line 2833) and `"prompt_opt"` to
  `_REBUILD_SEARCH_KINDS` (alongside `"usage"` line 2835). Per ENH-2581 the
  rebuild wipe lists are now the canonical registration point for
  JSONL-derived cache tables [Agent 2 finding, issue research §3 calls this
  shape out].
- `scripts/little_loops/session_store.py:2856-2895` — `rebuild()` body. Add
  `"prompt_opt_events": 0` to the `counts` dict (lines 2857-2866) and add
  `counts["prompt_opt_events"] = _backfill_prompt_opt(conn, _raw_events_cursor())`
  to the dispatch (lines 2881-2888, next to the `usage_events` line 2886). Update
  the `rebuild()` docstring (lines 2844-2854) with a one-line mention [Agent 2
  finding].
- `scripts/little_loops/session_store.py:3304-3329` — `_EXPORT_TABLE_MAP` /
  `_EXPORT_DEFAULT_TABLES`. Optional: add `"prompt_opt_event":
  ("prompt_opt_events", "ts")` to `_EXPORT_TABLE_MAP` (next to `"usage_event"`
  line 3315) and `"prompt_opt_event"` to `_EXPORT_DEFAULT_TABLES` (next to
  `"usage_event"` line 3328). Issue marks this as optional; recommended for
  parity with `usage_event` [Agent 2 finding].
- `scripts/little_loops/history_reader.py:1-42` — module docstring. Add a
  `PromptOptEvent` dataclass entry (around line 21 next to `RunEvent`) and two
  function entries (`recent_prompt_opt_events`, `prompt_opt_offer_rate`) in the
  public API listing (around lines 28-29 next to `recent_commit_events` /
  `recent_test_runs`). `history_reader.py` has no `__all__` — docstring is the
  sole export surface [Agent 2 finding].
- `scripts/little_loops/cli/session.py:9-10` — module docstring `recent` kind
  listing. The choices at lines 103/115 are auto-derived from
  `list(VALID_KINDS)` (so no argparse edit), but the docstring is a static
  string and must be updated to include `prompt_opt`. Same precedent: ENH-2461
  added `usage` to both the docstring and `_VALID_KINDS` [Agent 2 finding].

### Bypass-reason enum — full branch inventory

The issue's example enum (`prefix | slash | short | disabled`) is a subset. `handle()`
actually has these return points (line numbers current as of research); the
`bypass_reason` column should cover all of them:

| Return line | `offered` | `bypass_reason` | Notes |
|-------------|-----------|-----------------|-------|
| 73 | — | (none) | Empty prompt (`.strip() == ""`) — returns **before** the analytics-capture block; no row can be written here (nothing to optimize). |
| 97 | 0 | `no_config` | `config is None` (`_NO_CONFIG_MSG`). Analytics gate not yet evaluated at this point. |
| 103 | 0 | `disabled` | `prompt_optimization.enabled` is `False`. |
| 111 | 0 | `prefix` | `bypass_prefix` matched (default `*`). |
| 113 | 0 | `slash` | `/`-prefixed. |
| 115 | 0 | `hash` | `#`-prefixed. |
| 117 | 0 | `question` | `?`-prefixed. |
| 119 | 0 | `short` | `len < _MIN_PROMPT_LENGTH` (10). |
| 123 | 0 | `no_template` | Prompt template file missing. |
| 128 | 0 | `template_error` | `OSError` reading template. |
| 135 | 1 | `NULL` | Optimization offered (template rendered). Capture `mode`. |

`mode` / `confirm` / `bypass_prefix` are only known from line 105 onward, so the two
earliest branches (73, 97) have no `mode`. Decide whether to skip the offer row at 73/97
or write it with `mode=NULL` — document the choice in the AC.

### Similar Patterns

- Live-record + backfill split: **ENH-2495** (session lifecycle) is the direct precedent.
- Table + producer + kind + reader + CLI: **ENH-2458** (`commit_events`, schema v17) and
  **ENH-2459** (`test_run_events`, schema v18) are near-identical shapes to copy.

### Tests

- `scripts/tests/test_session_store.py` — `TestRecordPromptOptEvent` (roundtrip +
  FTS-searchable, model on `TestRecordCommitEvent` at line 3416), `TestPromptOptSchema`
  (table/index exist + upgrade path, using `_bootstrap_schema_at` at line 3075),
  bypass-reason matrix, analytics-gating (model on `test_record_correction_gate_disabled`
  at line 1483), graceful degradation (pass a directory as `db_path` to force
  `OperationalError`), and `TestBackfillPromptOpt` (JSONL fixture, model on
  `TestBackfillSkillEvents` at line 1556).
- `scripts/tests/test_ll_session.py` — `--kind prompt_opt` accepted by **both** `recent`
  and `search` (model on `test_recent_subcommand_commit_accepted` at line 78).
- `scripts/tests/test_history_reader.py` — `recent_prompt_opt_events` + `prompt_opt_offer_rate`
  (model on `test_recent_commit_events_filters` at line 1421; add to the missing-DB
  graceful-degradation test).
- `scripts/tests/test_hook_user_prompt_submit.py` — offered/bypass wiring per branch.

### Additional tests to extend (Wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

The following existing tests do not currently cover `prompt_opt_events` directly
but will break or silently regress if the migration lands without coordinated
updates. They are NOT new test files — they are extensions to existing ones.

- `scripts/tests/test_session_store.py:1372,1817,1932,1984,2080,3658,3699` —
  `TestSchemaV5/V9/V10/V11/V12/V13/V14::test_schema_version_is_*` — each
  asserts `assert SCHEMA_VERSION == 20` and the mated line asserts
  `int(row[0]) == 20`. Bump all literals to `21` after the migration lands [Agent
  3 finding, paired meta-row assertions at lines 1818, 1933, 1985, 2081, 3659,
  3700 must be bumped in lockstep].
- `scripts/tests/test_assistant_messages.py:88` —
  `test_schema_version_is_12::test_schema_version` — also asserts
  `assert SCHEMA_VERSION == 20`. Bump to `21` [Agent 3 finding].
- `scripts/tests/test_session_store.py:3409` —
  `TestValidKindsCentralization::test_every_valid_kind_has_a_kind_table_entry` —
  asserts `set(VALID_KINDS) == set(_KIND_TABLE.keys())`. Fails until
  `"prompt_opt"` is added to both, **and** `"prompt_opt": "prompt_opt_events"`
  to `_KIND_TABLE`. Will fail loudly otherwise [Agent 3 finding].
- `scripts/tests/test_verify_kinds.py:11,19` —
  `test_finds_known_tables` / `test_clean_state_returns_zero` — must extend
  assertions to include `prompt_opt_events`. The verifier auto-discovers tables
  from `_MIGRATIONS`, so the only test-side change is the assertion list
  [Agent 3 finding].
- `scripts/tests/test_history_reader.py:1530-1545` —
  `test_readers_return_empty_on_missing_db` — extend the import block
  (lines 1531-1537) and the assertion block (lines 1541-1544) to include
  `recent_prompt_opt_events` and `prompt_opt_offer_rate` [Agent 3 finding,
  issue §Tests partial].
- `scripts/tests/test_hooks_integration.py:1215,1275` — existing
  `prompt_optimization: enabled=False/True` fixtures. Extend to assert the
  resulting `prompt_opt_events` row count matches the bypass matrix [Agent 1
  finding].
- `scripts/tests/test_hook_user_prompt_submit.py:328,364,394,409` — the
  existing render/short/disabled/bypass tests should each be extended to
  assert the corresponding `bypass_reason` (or `offered=True` for the render
  path at line 328) row exists in `prompt_opt_events`. Pattern: mirror the
  existing `correction`-row assertions [Agent 3 finding].

### Documentation

- `docs/ARCHITECTURE.md` — schema-versions table needs a v19 `prompt_opt_events` row.
- `docs/reference/API.md` — `session_store` (`record_prompt_opt_event`, `_backfill_prompt_opt`)
  and `history_reader` (`recent_prompt_opt_events`, `prompt_opt_offer_rate`) entries.
- `docs/reference/CLI.md` — `ll-session recent --kind prompt_opt`.

### Additional doc surfaces (Wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

- `docs/ARCHITECTURE.md:659-678` — schema-versions table. Add a v21 row
  (or whatever next-available slot — read live `SCHEMA_VERSION` before
  editing) for `prompt_opt_events`, listing the columns `(ts, session_id,
  mode, offered, bypass_reason, raw_len, optimized_len, optimized_text,
  accepted)`, the live-write path (`user_prompt_submit.py::handle()`),
  the backfill pass (`_backfill_prompt_opt` via `rebuild()`), and the
  CLI/reader surfaces. Issue already names `docs/ARCHITECTURE.md` but not
  this specific line range [Agent 2 finding].
- `docs/reference/API.md:7280-7294` — `little_loops.session_store` Python
  import block. Add `record_prompt_opt_event` next to `record_commit_event`
  / `record_test_run_event`. Issue already names `docs/reference/API.md`
  but not this specific block [Agent 2 finding].
- `docs/reference/API.md:6836-6850` — `little_loops.history_reader`
  Python import block. Add `recent_prompt_opt_events`,
  `prompt_opt_offer_rate`, and a `PromptOptEvent` dataclass reference
  next to `CommitEvent` / `RunEvent` (lines 6847-6848) [Agent 2 finding].
- `docs/reference/CLI.md:2427,2435` — `--kind {…}` brace-listings. The
  table at line 2427 lists `tool,file,issue,loop,correction,message,skill,
  cli,commit,test_run`; the one at 2435 lists the same plus `snapshot`.
  Both omit `usage` (ENH-2461 left them stale). Update both to include
  `prompt_opt` (or run a sweep to add `usage` and `prompt_opt`
  together). The line 2435 description already says these are "sourced
  from `VALID_KINDS`, the single source of truth" — so the brace-lists
  are documentation-only and lag the runtime [Agent 2 finding].
- `docs/guides/HISTORY_SESSION_GUIDE.md:85-99` — `*.db` tables table.
  Add a `prompt_opt_events` row between `usage_events` (line 97) and
  the `summary_nodes` / `summary_spans` rows (line 98). Describe columns
  `(ts, session_id, mode, offered, bypass_reason, raw_len,
  optimized_len, optimized_text, accepted)` and the ENH-2498 source
  [Agent 2 finding].
- `docs/guides/HISTORY_SESSION_GUIDE.md:170` — search `--kind` examples
  comment. Currently lists `tool, file, issue, loop, correction, message,
  skill, cli, commit, test_run, usage`. Add `prompt_opt` (and `usage`
  while at it) [Agent 2 finding].

### Configuration

- `config-schema.json` — `prompt_optimization.*` at lines 581–614
  (`enabled`, `mode`, `confirm`, `bypass_prefix`, `clarity_threshold`); read-only for
  this issue (behavior unchanged). No schema change unless a per-feature
  `analytics.capture.prompt_opt` gate is added (out of scope — the top-level
  `analytics.enabled` gate is the lighter precedent the siblings follow).

### Intentionally skipped config / schema surfaces (Wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

The following per-feature `analytics.capture.*` surfaces exist and could host
a dedicated `prompt_opt` / `prompt_optimization` gate, but adding them would
expand `AnalyticsCaptureConfig` + `config-schema.json` + init admission
list. Per the issue's "Configuration" section, the lighter precedent is the
top-level `analytics.enabled` gate. Flagged here for completeness — do not
edit unless the implementation deliberately expands scope:

- `scripts/little_loops/config/features.py:528-558` — `AnalyticsCaptureConfig`
  dataclass. Mirror the `config=` stub pattern used by
  `record_test_run_event()` if a per-feature gate is desired [Agent 2 finding].
- `scripts/little_loops/init/core.py:17` — `_ANALYTICS_CAPTURE_KEYS` admission
  list (currently `("skills", "cli_commands", "corrections", "file_events",
  "usage_events")`) [Agent 2 finding].
- `scripts/little_loops/cli/doctor.py:25-44` — `_print_capture_section`
  runtime consumer of the per-feature capture field names [Agent 2 finding].
- `scripts/little_loops/config-schema.json:1608-1680` — `analytics.capture.*`
  schema mirror [Agent 2 finding].
- `docs/reference/CONFIGURATION.md:519` — `analytics.capture.usage_events`
  row precedent [Agent 2 finding].
- `docs/guides/BUILTIN_HOOKS_GUIDE.md:433-434` — config-by-hook table
  [Agent 2 finding].

### Codebase Research Findings

_Added by `/ll:refine-issue` — current-code reconciliation from the 2026-07-16 research pass:_

- **Schema slot and migration anchors have moved.** `scripts/little_loops/session_store.py:207`
  currently reports `SCHEMA_VERSION = 20`; v19 is `raw_events` and v20 is `usage_events`,
  so this issue's migration must be the next live slot (v21 unless another migration lands
  first). The preceding line-number references for `_MIGRATIONS`, `_VALID_KINDS`,
  `_KIND_TABLE`, `recent()`, `record_commit_event()`, `record_test_run_event()`,
  `_backfill_skill_events()`, `backfill()`, `backfill_incremental()`, and
  `_EXPORT_TABLE_MAP` are historical and must be re-anchored before implementation.
- **ENH-2581 changed the backfill contract.** `session_store.py:2824-2898` wipes and
  re-materializes JSONL-derived tables from `raw_events` via `_iter_events()`; the current
  `backfill()` at `session_store.py:2924-2980` ingests raw lines only, and
  `backfill_incremental()` at `session_store.py:2983-3031` uses the single
  `last_raw_event_ts` watermark. Register the new producer in `_REBUILD_TABLES`,
  `_REBUILD_SEARCH_KINDS`, and `rebuild()`; do **not** add the removed per-table
  `_PROMPT_OPT_KEY` watermark or assume `backfill()` directly materializes cache rows.
- **The CLI choices are data-driven.** Both `ll-session` argparse `--kind` choices at
  `scripts/little_loops/cli/session.py:99-118` use `list(VALID_KINDS)`. Adding
  `"prompt_opt"` to `session_store.VALID_KINDS` and `_KIND_TABLE` is the runtime/CLI
  registration point; only the CLI documentation and any stale module docstrings need
  separate edits.
- **The analytics capture contract is currently top-level only.**
  `AnalyticsCaptureConfig` has no `prompt_opt_events` field, so the existing codebase
  supports `analytics.enabled` for this producer but not a dedicated
  `analytics.capture.prompt_opt` switch. The current AC wording about both gates should
  be implemented as the top-level gate unless the implementation deliberately expands
  `config/features.py` and `config-schema.json` as additional scope.
- **The earliest branches cannot be captured with a resolved mode.**
  `user_prompt_submit.handle()` at `:72-97` returns for an empty prompt or missing config
  before `mode` is read and before the existing analytics block can run. Preserve the
  explicit decision in the implementation: skip those rows, or write a best-effort row
  with `mode=NULL`; do not claim unconditional per-prompt coverage when analytics is
  disabled or config is absent. The remaining bypass inventory is `disabled`, `prefix`,
  `slash`, `hash`, `question`, `short`, `no_template`, and `template_error`, followed by
  the offered return at `:130-135`.
- **Outcome reconstruction has an evidence limitation.**
  `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md:45-65` emits an
  `ORIGINAL:`/`ENHANCED:` diff only for `confirm=true`, while `confirm=false` emits only
  a short `[ll:autoprompt] Enhanced with:` note. The hook's rendered stdout is injected
  as `additionalContext`; the ordinary JSONL user event still contains the original
  prompt. Therefore `_backfill_prompt_opt()` can populate `optimized_text` and
  `accepted` only when a transcript fixture contains a parseable enhancement and a
  deterministic correlation to the live offer. Otherwise those columns must remain NULL;
  the acceptance criterion should not imply that every historical offer has a recoverable
  before→after text delta.
- **Backfill row matching needs an explicit invariant.** The live offer row is not
  identified by a transcript field, so the implementation must define a bounded
  `session_id`/timestamp correlation (and idempotent update behavior) before writing
  `optimized_*` fields. The fixture should exercise both a parseable `ENHANCED:` response
  and an unparseable/auto-apply response to prove that best-effort enrichment does not
  fabricate acceptance.

## Proposed Solution

### Split the capture: offer (live) vs. outcome (backfill)

The hook only emits an *instruction*; it never sees the result. So model two
concerns honestly, mirroring how ENH-2495 treats advisory hooks:

1. **Offer row — live, at hook fire.** Cheap, authoritative, always available.
2. **Outcome enrichment — backfill from JSONL.** The optimized prompt and whether
   the user/model accepted it live in the transcript; a `_backfill_prompt_opt`
   pass (invoked by `ll-session backfill`) fills `optimized_len`,
   `optimized_text`, and an `accepted` heuristic. Never blocks the live path.

### Codebase Research Findings

_Added by `/ll:refine-issue` — implementation constraints from the current backfill and hook paths:_

- Keep the live writer best-effort and call it inside the existing
  `feature_enabled(config, "analytics.enabled")` block with
  `contextlib.suppress(Exception)`, matching `record_correction()` and
  `record_skill_event()` in `user_prompt_submit.py:78-94`. The recorder itself should
  follow the keyword-only writer/FTS pattern used by `record_test_run_event()`;
  `recent()` already dispatches generically from `_KIND_TABLE`.
- The `_backfill_prompt_opt()` implementation must accept the shared
  `list[Path] | sqlite3.Cursor` source shape used by `_iter_events()`. It should be
  invoked during `rebuild()` after raw-event ingestion, and its table/search kind must
  be included in the rebuild wipe lists so repeated rebuilds do not leave stale rows or
  duplicate FTS entries. A separate prompt-specific watermark would conflict with the
  current single-`last_raw_event_ts` design.
- `optimized_text` should be indexed only after a parseable transcript match; the live
  offer index can contain a short mode/bypass summary. Backfill updates must be
  idempotent, bounded to the matched offer row, and leave `accepted=NULL` when the
  transcript does not provide enough evidence. This is more precise than treating all
  assistant responses as accepted optimizations.
- The prompt template has two materially different signals: `confirm=true` includes the
  full `ENHANCED:` candidate, while `confirm=false` includes only a summary. Tests and
  docs should state which signal the heuristic consumes and should include a fixture for
  each path rather than asserting universal recovery of the optimized prompt.

### Schema migration

```sql
CREATE TABLE IF NOT EXISTS prompt_opt_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    session_id TEXT,
    mode TEXT,                   -- "quick" | "thorough"
    offered INTEGER,             -- 1 fired, 0 bypassed
    bypass_reason TEXT,          -- NULL | "prefix" | "slash" | "short" | "disabled" | ...
    raw_len INTEGER,             -- len(user_prompt)
    optimized_len INTEGER,       -- backfilled
    optimized_text TEXT,         -- backfilled (FTS-indexed)
    accepted INTEGER             -- backfilled heuristic; NULL until enriched
);
CREATE INDEX IF NOT EXISTS idx_prompt_opt_events_session ON prompt_opt_events(session_id);
CREATE INDEX IF NOT EXISTS idx_prompt_opt_events_mode ON prompt_opt_events(mode);
```

Bump `SCHEMA_VERSION`. Add `"prompt_opt"` to `_VALID_KINDS` and
`"prompt_opt": "prompt_opt_events"` to `_KIND_TABLE`.

### Producer wiring

- Add `record_prompt_opt_event(db_path, *, ts, session_id, mode, offered,
  bypass_reason=None, raw_len=None)` to `session_store.py`. Best-effort guarded.
- Call it from `user_prompt_submit.py::handle()` at each return point — one row
  per prompt, capturing whether it fired and, on bypass, the reason (the handler
  already branches on prefix/slash/short/disabled). Gate on
  `analytics.enabled` like the sibling `record_correction`/`record_skill_event`
  calls so it respects the existing capture switch.
- Add `_backfill_prompt_opt(db_path, session_jsonl)` to the backfill worker to
  enrich `optimized_*`/`accepted` from the transcript; FTS-index `optimized_text`.

### Read API

- `history_reader.recent_prompt_opt_events(mode=None, since=None, limit=50)`.
- `history_reader.prompt_opt_offer_rate(since=None)` (offered / total).

### CLI surface

- `ll-session recent --kind prompt_opt`.
- Optional: surface offer-rate / mode-mix in `ll-ctx-stats`.

## Acceptance Criteria

- Schema migration lands; `prompt_opt_events` exists; `SCHEMA_VERSION` bumped.
- A prompt that triggers optimization writes one `offered=1` row with the mode;
  a bypassed prompt (e.g. `*`-prefixed or `/`-slash) writes `offered=0` with the
  correct `bypass_reason`.
- Writes are best-effort: DB absent/locked never changes hook stdout/exit — the
  optimization template still renders.
- Capture respects `analytics.enabled` and `analytics.capture` gating (no rows
  when analytics is disabled).
- `_backfill_prompt_opt` populates `optimized_len`/`optimized_text` for at least
  one accepted optimization from a fixture JSONL; `accepted` heuristic documented.
- `ll-session recent --kind prompt_opt` returns rows; FTS matches optimized text.
- Tests cover: offered (quick), offered (thorough), each bypass reason, analytics
  disabled (no write), graceful degradation, backfill enrichment.

## Implementation Steps

1. Schema migration for `prompt_opt_events`; bump `SCHEMA_VERSION`.
2. Add `"prompt_opt"` to `_VALID_KINDS` and `_KIND_TABLE`.
3. Implement `record_prompt_opt_event()` in `session_store.py`; export.
4. Wire the per-return-point calls into `user_prompt_submit.py::handle()`
   (offered + bypass_reason), gated on `analytics.enabled`.
5. Add `_backfill_prompt_opt()` to the backfill worker; FTS-index optimized text.
6. `history_reader.recent_prompt_opt_events()` + `prompt_opt_offer_rate()`.
7. CLI: `ll-session recent --kind prompt_opt`.
8. Tests: `TestRecordPromptOptEvent`, `TestPromptOptSchema`, bypass-reason matrix,
   analytics-gating, backfill enrichment, graceful degradation.
9. Docs: `docs/ARCHITECTURE.md` schema row, `docs/reference/API.md`,
   `docs/reference/CLI.md`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete sequencing corrections:_

1. Before writing the migration, re-read `session_store.py:207` and append after the
   live migration list; the next slot is currently v21, not the historical v19 cited
   above. Register the table in `_KIND_TABLE` and keep it out of `_KINDLESS_TABLES` so
   the `ll-verify-kinds` invariant remains satisfied.
2. Implement the live producer and hook wiring before the backfill parser, then add
   `_backfill_prompt_opt()` to `rebuild()`'s raw-event replay path, `_REBUILD_TABLES`,
   and `_REBUILD_SEARCH_KINDS`. Do not wire it as a direct cache-table write in
   `backfill()` or introduce a per-table watermark.
3. Define and test the transcript correlation/acceptance contract before asserting
   `optimized_text` or `accepted`: `ENHANCED:` is available only in the confirm-diff
   path, while auto-apply produces a summary without the full replacement prompt.
4. Add a CLI parser test for both `recent --kind prompt_opt` and `search --kind prompt_opt`,
   but do not add a second argparse choices list—the choices already derive from
   `VALID_KINDS`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in
the implementation alongside the existing 1–9 steps above._

10. **SCHEMA_VERSION literal bump.** Update the seven `TestSchemaV*` tests in
    `scripts/tests/test_session_store.py` (lines 1372, 1817-1818, 1932-1933,
    1984-1985, 2080-2081, 3658-3659, 3699-3700) and the
    `test_schema_version` assertion in `scripts/tests/test_assistant_messages.py:88`
    from `20` to `21`. [Agent 3 finding — without this, the meta-row
    assertions break once `SCHEMA_VERSION` advances.]
11. **Schema registration invariants.**
    - Add `"prompt_opt"` to `_VALID_KINDS` (line 209) and
      `"prompt_opt": "prompt_opt_events"` to `_KIND_TABLE` (line 215). The
      `TestValidKindsCentralization` test (line 3409) will fail loudly if
      these two are not landed together.
    - Add `"prompt_opt_events"` to `_REBUILD_TABLES` (line 2824) and
      `"prompt_opt"` to `_REBUILD_SEARCH_KINDS` (line 2835). Update
      `rebuild()` `counts` dict and dispatch (lines 2856-2895).
    - Verify `_KINDLESS_TABLES` (line 244) does **NOT** contain
      `prompt_opt_events` — `ll-verify-kinds` enforces that every
      `CREATE TABLE` is either registered in `_KIND_TABLE` or explicitly
      kindless, and adding it here would silently disable the lint gate.
12. **Docstring + `__all__` updates.**
    - `scripts/little_loops/session_store.py:1-38` — module docstring.
    - `scripts/little_loops/session_store.py:61-93` — `__all__` (add
      `"record_prompt_opt_event"`).
    - `scripts/little_loops/session_store.py:1468-1472` — `recent()`
      docstring `Kinds:` line.
    - `scripts/little_loops/history_reader.py:1-42` — module docstring
      (add `PromptOptEvent` dataclass entry + two function entries).
    - `scripts/little_loops/cli/session.py:9-10` — module docstring
      listing.
13. **Optional export registration.** Add `"prompt_opt_event":
    ("prompt_opt_events", "ts")` to `_EXPORT_TABLE_MAP` (line 3304) and
    `"prompt_opt_event"` to `_EXPORT_DEFAULT_TABLES` (line 3329) for parity
    with `usage_event`. Issue marks as optional; recommended.
14. **History guide doc.** Add a `prompt_opt_events` row to the `*.db`
    tables table in `docs/guides/HISTORY_SESSION_GUIDE.md:85-99`, and
    update the `--kind` examples comment at line 170 to include
    `prompt_opt` (and `usage` while at it).
15. **API reference import blocks.** Extend `docs/reference/API.md:7280-7294`
    (session_store) and `:6836-6850` (history_reader) Python import blocks.
16. **CLI reference `--kind` brace-lists.** Update the `--kind {…}`
    brace-listings at `docs/reference/CLI.md:2427` and `:2435`.
17. **Architecture schema-versions table.** Add a v21 row to
    `docs/ARCHITECTURE.md:659-678` for `prompt_opt_events`.
18. **Missing-DB graceful degradation.** Extend
    `scripts/tests/test_history_reader.py:1530-1545`
    (`test_readers_return_empty_on_missing_db`) to import and assert
    `recent_prompt_opt_events` and `prompt_opt_offer_rate`.
19. **`ll-verify-kinds` test extension.** Update
    `scripts/tests/test_verify_kinds.py:11,19`
    (`test_finds_known_tables`, `test_clean_state_returns_zero`) to include
    `prompt_opt_events` in the known-tables assertion.
20. **Hook integration test extensions.** Extend the existing
    `scripts/tests/test_hooks_integration.py:1215,1275` fixtures to assert
    `prompt_opt_events` row counts per bypass branch.
21. **Hook handler test extensions.** Extend the render / short / disabled
    / bypass tests in `scripts/tests/test_hook_user_prompt_submit.py`
    (lines 328, 364, 394, 409) to assert the corresponding `bypass_reason`
    or `offered=True` row.

### Verified-safe surfaces (Wiring pass)

_Wiring pass added by `/ll:wire-issue`:_

The following surfaces were verified to NOT need changes despite a
hypothesis that they might:

- `scripts/little_loops/hooks/__init__.py:50-54` — `_USAGE` banner. ENH-2498
  adds a *table*, not a new hook *intent*. No edit needed.
- `scripts/little_loops/observability/schema.py` /
  `scripts/little_loops/cli/verify_des_audit.py` — DES variant registry.
  Confirmed no DES variant is required for `record_prompt_opt_event` or
  `_backfill_prompt_opt`; the F5 adoption gate walks `event_bus.emit(...)`
  sites only and these are direct DB writers, mirroring the
  `record_correction`/`record_skill_event`/`record_commit_event`/
  `record_test_run_event` precedent which all lack DES variants.
- `CHANGELOG.md` — defer per project convention `feedback_changelog_no_unreleased.md`;
  the entry lands during release prep, not at implementation time.

## Sources

- `scripts/little_loops/hooks/user_prompt_submit.py` — the producer (renders
  optimization template; already calls `record_correction`/`record_skill_event`
  at lines 84 & 92 for the same prompt)
- `scripts/little_loops/hooks/prompts/optimize-prompt-hook.md` — the template
- `config-schema.json` — `prompt_optimization.*` (`mode`, `confirm`,
  `bypass_prefix`, `enabled`)
- EPIC-2457 review (2026-07-05) — new sibling beyond the original 15 children
- ENH-2495 — precedent for advisory-hook capture (live sentinel + backfill split)

## Scope Boundaries

**In scope:** a `prompt_opt_events` table + migration; a live offer-row write from
`user_prompt_submit.py`; a best-effort `_backfill_prompt_opt` enrichment pass;
read API + `ll-session recent --kind prompt_opt`; tests and docs.

**Out of scope:** changing prompt-optimization *behavior* (modes, confirm,
bypass rules stay as-is — this only observes); reconstructing before→after for
historical sessions beyond what `ll-session backfill` already replays; any
capture when `analytics.enabled` is false; blocking or altering the hook's
stdout/exit on DB failure (graceful-degradation contract per EPIC-2457).

## Impact

- **Priority**: P3 — additive observability for an existing, config-gated feature;
  no coordinated release pressure.
- **Effort**: Small-Medium — one table + `record_*` (mirrors existing producers),
  per-return-point wiring in one handler, plus a backfill pass and its tests.
- **Risk**: Low — additive table, best-effort guarded writes, analytics-gated; no
  existing table or hook return path changes semantically.
- **Breaking Change**: No.

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/ARCHITECTURE.md` | Schema versions table |
| `docs/reference/API.md` | `session_store`, `history_reader` modules |
| `config-schema.json` | `prompt_optimization.*` feature surface |

## Status

**Open** | Created: 2026-07-05 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): This issue's Integration Map
assumes it is the sole claimant of the next schema-version slot ("bump
`SCHEMA_VERSION = 18` → `19`"). At least ten other active EPIC-2457 siblings
(ENH-2463, ENH-2464, ENH-2465, ENH-2492, ENH-2493, ENH-2494, ENH-2495,
ENH-2496, ENH-2497, ENH-2511) independently make the same "18→19" claim in
their own Integration Maps — they cannot all be v19. Verified against current
code (`scripts/little_loops/session_store.py`): `SCHEMA_VERSION` is now **20**
(v17=`commit_events`/ENH-2458 done, v18=`test_run_events`/ENH-2459 done,
v19=`raw_events`/ENH-2581 done, v20=`usage_events`/ENH-2461 done). At
implementation time, read the live `SCHEMA_VERSION` constant to determine the
actual next-available slot rather than trusting this issue's stale "19"
literal; each child lands its own migration at whatever version is open when
it is implemented (no coordinated release; per EPIC-2457's own "no shared
helper module is required" scope note).

## Session Log
- `/ll:wire-issue` - 2026-07-17T00:08:22 - `1a6a415c-07aa-41f7-87c2-f7aafafb29ad.jsonl`
- `/ll:refine-issue` - 2026-07-16T15:47:11 - `fd81b1d4-3269-4fb1-aa37-7a65417fe3e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:48 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T01:29:53 - `396f134c-5bb3-4cf3-988f-e98b42e96ee1.jsonl`
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
