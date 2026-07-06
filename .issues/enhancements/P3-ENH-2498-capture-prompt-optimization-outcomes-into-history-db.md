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

## Session Log
- `/ll:capture-issue` - 2026-07-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`
