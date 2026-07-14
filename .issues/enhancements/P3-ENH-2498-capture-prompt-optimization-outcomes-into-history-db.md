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

### Documentation

- `docs/ARCHITECTURE.md` — schema-versions table needs a v19 `prompt_opt_events` row.
- `docs/reference/API.md` — `session_store` (`record_prompt_opt_event`, `_backfill_prompt_opt`)
  and `history_reader` (`recent_prompt_opt_events`, `prompt_opt_offer_rate`) entries.
- `docs/reference/CLI.md` — `ll-session recent --kind prompt_opt`.

### Configuration

- `config-schema.json` — `prompt_optimization.*` at lines 581–614
  (`enabled`, `mode`, `confirm`, `bypass_prefix`, `clarity_threshold`); read-only for
  this issue (behavior unchanged). No schema change unless a per-feature
  `analytics.capture.prompt_opt` gate is added (out of scope — the top-level
  `analytics.enabled` gate is the lighter precedent the siblings follow).

## Proposed Solution

### Split the capture: offer (live) vs. outcome (backfill)

The hook only emits an *instruction*; it never sees the result. So model two
concerns honestly, mirroring how ENH-2495 treats advisory hooks:

1. **Offer row — live, at hook fire.** Cheap, authoritative, always available.
2. **Outcome enrichment — backfill from JSONL.** The optimized prompt and whether
   the user/model accepted it live in the transcript; a `_backfill_prompt_opt`
   pass (invoked by `ll-session backfill`) fills `optimized_len`,
   `optimized_text`, and an `accepted` heuristic. Never blocks the live path.

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
- `/ll:audit-issue-conflicts` - 2026-07-14T00:23:48 - `bf6876a0-2fb4-4626-99a4-da1569d51511.jsonl`
- `/ll:refine-issue` - 2026-07-07T01:29:53 - `396f134c-5bb3-4cf3-988f-e98b42e96ee1.jsonl`
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
