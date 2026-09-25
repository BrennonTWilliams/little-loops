---
id: BUG-3541
title: MODEL_ALIASES maps opus and fable to superseded model IDs
type: BUG
priority: P2
status: done
parent: EPIC-3563
epic: EPIC-3563
discovered_date: '2026-09-23'
completed_at: '2026-09-25T01:35:43Z'
labels:
- multi-host
- models
relates_to:
- BUG-3564
confidence_score: 95
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
---

# MODEL_ALIASES maps opus and fable to superseded model IDs

## Summary

`host_runner.MODEL_ALIASES` (`scripts/little_loops/host_runner.py:97-102`)
resolves `opus → claude-opus-5` and `fable → claude-fable-5`. The current
lineup is Opus 5.5 (`claude-opus-5-5`) and Fable 5.1 (`claude-fable-5-1`).
The CLI path is unaffected (the host binary resolves aliases itself), but every
SDK/batch request (`orchestration.request_path: sdk|batch`) that uses `opus` or
`fable` is sent to the older model. ENH-3527 derives its `anthropic-api`
`reasoning` hint target from this table, so the staleness would carry into
hints too.

## Current Behavior

- `resolve_model_alias("opus")` → `claude-opus-5`; `resolve_model_alias("fable")`
  → `claude-fable-5`. `sonnet → claude-sonnet-5` and `haiku → claude-haiku-4-5`
  are current.
- `advisor.py:56-58` ranks `claude-fable-5-1` but has no `claude-opus-5-5`
  entry, so ranking a resolved `claude-opus-5-5` would fall to the unknown-model
  default.
- `pricing.py` has no entry for `claude-opus-5-5` or `claude-fable-5-1`, so
  `estimate_cost_usd` returns `None` for either (null `cost_usd` rows).
- `pricing.py` also has no entry for the undated `claude-haiku-4-5`, which is
  what `haiku` resolves to. It only keys `claude-haiku-4-5-20251001`, and
  `MODEL_PRICING.get()` is an exact lookup. Every SDK/batch `haiku` request is
  therefore unpriced today. This also means a guard test over all alias targets
  would fail on `haiku` before this fix.

## Steps to Reproduce

1. `python -c "from little_loops.host_runner import resolve_model_alias as r; print(r('opus'), r('fable'))"`
2. Observe `claude-opus-5 claude-fable-5`; expected `claude-opus-5-5 claude-fable-5-1`.
3. `python -c "from little_loops.pricing import estimate_cost_usd as e; print(e('claude-haiku-4-5', 1, 1))"` prints `None` (the `haiku` alias target is unpriced).

## Impact

- **Priority**: P2 — only SDK/batch request paths are affected (the CLI path resolves aliases itself), but ENH-3527 is `blocked_by` this bug, so it is raised to P2.
- **Effort**: Small — table entries plus tests.
- **Risk**: Low. It changes which model `opus` / `fable` hit on SDK/batch paths, but explicitly named old IDs still pass through unchanged.

## Expected Behavior

Aliases resolve to the current model IDs; the advisor rank table and pricing
table recognize both the new and the superseded IDs (history rows keep old IDs).

## Scope

1. Update `MODEL_ALIASES` `opus`/`fable` targets.
2. Add `claude-opus-5-5` to `advisor.py` rank table (same rank as `claude-opus-5`).
3. Add `pricing.py` entries using the live pricing-page rates. Do **not** copy
   the predecessors' rates; the cache-read multipliers differ.
   - `claude-opus-5-5`: input 4.0, output 20.0, cache_read 0.20, cache_creation 5.0.
   - `claude-fable-5-1`: input 10.0, output 50.0, cache_read 0.25 (0.025x input,
     not Fable 5's 0.1x), cache_creation 12.50.
   - `claude-haiku-4-5`: point it at the **same dict object** as
     `claude-haiku-4-5-20251001`, for example a module-level `_HAIKU_4_5`
     referenced by both keys. The two IDs cannot then drift, and BUG-3564's
     rate correction fixes both.
   - Keep the `claude-opus-5` / `claude-fable-5` entries for historical rows.
4. Update `scripts/tests/test_host_runner_dispatch.py:383-387` (`opus`/`fable`
   expectations) and `test_advisor.py`.
5. Extend `test_dispatch_sends_resolved_model_to_sdk` and
   `test_batch_submission_sends_resolved_model_to_sdk`
   (`test_host_runner_dispatch.py`, which cover `sonnet` only today) to
   parametrize over `opus` and `fable`. Assert the new IDs reach
   `messages.create` and `messages.batches.create`.
6. Add `claude-opus-5` and `claude-fable-5` to
   `test_non_aliases_pass_through_unchanged`, so an explicit old ID still
   reaches the API unchanged.
7. Add a guard test asserting every `MODEL_ALIASES` target has an advisor rank
   and a `MODEL_PRICING` entry, so the three tables cannot drift again.

## Integration Map

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Tables that must agree, all exact-key lookups** (a missing row fails silently — `None` or passthrough): `MODEL_ALIASES` (`host_runner.py:97-102`), `MODEL_RANKS["claude-code"]` (`advisor.py:52-59`), `MODEL_PRICING` (`pricing.py:21-91`). `MODEL_CONTEXT_WINDOW` (`context_window.py:19-33`) is a fourth table with no 5.x entries at all (`claude-sonnet-5`, `claude-opus-5`, `claude-fable-5` all fall to the 200k floor); it is outside this issue's Scope but shares the drift shape.
- **Only two non-test callers of `resolve_model_alias`**: `build_anthropic_request()` in `host_runner.py` (batch reuses this builder, so SDK and batch are both covered) and `rank_model()` in `advisor.py`. `MODEL_ALIASES` is referenced nowhere outside `host_runner.py`.
- **Correction to Current Behavior**: `rank_model` returns `None` for an unranked ID — there is no "unknown-model default" rank.
- **Correction to Scope 4**: the line 383-387 range in `test_host_runner_dispatch.py` also contains the `haiku` (384) and `Sonnet` (386) rows; only 383 (`opus`), 385 (`fable`) and 387 (`" opus "`) change.
- **Tests that break as a direct consequence of the alias change and must be updated together**: `test_advisor.py:58` (`rank_model(.., "opus") == rank_model(.., "claude-opus-5")` becomes `None` vs `3`); `test_advisor.py:30-38` asserts an exact five-ID set, so any new rank row edits it; `test_pricing.py:20-32` `LIVE_RATES` is a second hand-typed copy of the rates and `test_every_model_pinned` (`:94-95`) asserts `set(MODEL_PRICING) == set(LIVE_RATES)`, so every new pricing key must be added to `LIVE_RATES` in the same change (which also pulls it into `test_rates_match_live_table` and `test_batch_halves_each_rate`).
- **Stale references adjacent to the change**: the `advisor.py:49` comment cites `host_runner.py:79-84` (now the `__all__` list; `resolve_model_alias` is at `:105-114`); `advisor.py:88` docstring and `docs/reference/API.md:12228,12236` name `claude-opus-5` as the current opus.
- **Unaffected by new IDs**: `cache_marking_oracle.py` matches by family substring (`"opus"`), so `claude-opus-5-5` behaves like `claude-opus-5`; `claude-fable-*` and haiku use the same default minimum before and after.
- **Pricing details relevant to the haiku shared-dict scope item**: `INTRO_PRICING` is keyed by model ID separately and is currently empty (`{}`), so a shared rate dict cannot diverge on intro pricing today; nothing mutates `MODEL_PRICING` entries.

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/host_runner.py` — `build_anthropic_request()` (~`:2950`) calls `resolve_model_alias(model)`; SDK and batch both inherit the new targets [Agent 1 finding]
- `scripts/tests/test_host_runner_dispatch.py` — `test_non_aliases_pass_through_unchanged` (`:399-404`) and the `DEFAULT_LLM_MODEL` resolution test (`:438`) also exercise the table; confirm `DEFAULT_LLM_MODEL` does not resolve through `opus`/`fable` [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `### MODEL_PRICING` (`:12366`) prose says it "covers the current Claude 5.x / 4.x model registry"; add `claude-opus-5-5`, `claude-fable-5-1`, `claude-haiku-4-5` and note the shared haiku dict [Agent 2 finding]
- `docs/observability/tier0-traces.md:231` — cites `pricing.py:15-80` for `MODEL_PRICING`; line range goes stale as rows are added [Agent 2 finding]
- `docs/observability/realized-savings-verification.md:43-44` — lists which models ENH-2745 added to `MODEL_PRICING` (history; no edit needed, informational) [Agent 2 finding]

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_pricing.py` — `LIVE_RATES` (`:20-32`) needs `claude-opus-5-5`, `claude-fable-5-1`, `claude-haiku-4-5` rows; `test_every_model_pinned` (`:94-95`) fails otherwise. Note `:67` `assert "claude-fable-5" in MODEL_PRICING` is a presence check and stays valid [Agent 3 finding]
- `scripts/tests/test_advisor.py:42` (`ranks["claude-haiku-4-5"] < ranks["claude-opus-5"]`) — stays valid; add an equivalent assertion for `claude-opus-5-5` [Agent 3 finding]
- `scripts/tests/test_session_store_writers.py`, `test_session_store_queries.py`, `test_history_reader_events.py`, `test_issue_history_agent_quality.py` — use `claude-opus-5` as a literal `advisor_model`/`model` fixture value; unaffected (no alias resolution), confirms old IDs must stay accepted [Agent 3 finding]

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/context_window.py:19-33` — `MODEL_CONTEXT_WINDOW` has `claude-haiku-4-5` but no 5.x rows; out of scope, no change required [Agent 2 finding]

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_pricing.py` — add the three new keys to `LIVE_RATES` in the same change as the `pricing.py` edit
- Update `scripts/tests/test_advisor.py:30-38,58` — extend the exact rank-ID set and fix the `opus` equality assertion
- Update `docs/reference/API.md:12228,12236,12366` — refresh current-model names and the `MODEL_PRICING` coverage sentence
- Update `scripts/little_loops/advisor.py:49,88` — fix stale `host_runner.py:79-84` cite and the `claude-opus-5` docstring example

## Program Design

### Types

- `MODEL_ALIASES: dict[str, str]`
- `MODEL_PRICING: dict[str, dict[str, float]]`
- `MODEL_RANKS: dict[str, dict[str, int]]`

### Signatures

- `resolve_model_alias(model: str) -> str` — unchanged; reads the updated table.
- `rank_model(host: str, model: str) -> int | None` — unchanged; gains a `claude-opus-5-5` row.
- `estimate_cost_usd(model: str, input_tokens: int | None, output_tokens: int | None, cache_read_tokens: int | None = 0, cache_creation_tokens: int | None = 0, is_batch: bool = False, as_of: date | None = None) -> float | None` — unchanged; gains the three new keys.
- `test_every_alias_target_is_ranked_and_priced() -> None` — new guard test.

### Call Path

`resolve_model_alias` -> `rank_model` and `estimate_cost_usd`; the guard test iterates `MODEL_ALIASES` and asserts both resolve for every target.

## Acceptance Criteria

- [ ] `resolve_model_alias("opus") == "claude-opus-5-5"` and
      `resolve_model_alias("fable") == "claude-fable-5-1"`.
- [ ] `rank_model("claude-code", "opus") == rank_model("claude-code", "claude-opus-5-5")`.
- [ ] Explicit price assertions:
      `estimate_cost_usd("claude-opus-5-5", 1_000_000, 1_000_000, 1_000_000, 1_000_000) == 4.0 + 20.0 + 0.20 + 5.0`,
      and `estimate_cost_usd("claude-fable-5-1", 0, 0, 1_000_000, 0) == 0.25`.
- [ ] `MODEL_PRICING["claude-haiku-4-5"] is MODEL_PRICING["claude-haiku-4-5-20251001"]`.
- [ ] Every `MODEL_ALIASES` target has a rank and a price (guard test, passing for all four aliases).
- [ ] SDK and batch dispatch send `claude-opus-5-5` / `claude-fable-5-1` for the `opus` / `fable` aliases.
- [ ] Superseded IDs remain ranked, priced and passed through unchanged when named explicitly.

## Related

- ENH-3527 — `anthropic-api` hint targets derive from `MODEL_ALIASES`; ENH-3527 is `blocked_by` this bug so its SDK hint tests assert current IDs. Raised P3 → P2 to match (avoids a P3 blocking a P2).
- BUG-3564 corrects stale rates on existing `MODEL_PRICING` rows (Sonnet 5,
  Opus 4.5-4.7, Haiku 4.5). This issue only adds keys. Either can land first.
- Pricing source: platform.claude.com/docs/en/about-claude/pricing (checked 2026-09-24).

## Resolution

Fixed: `opus`/`fable` alias targets updated; rank, pricing (incl. shared `_HAIKU_4_5` dict), tests, guard test and API docs added.

## Status

**Done** | Created: 2026-09-23 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-25T01:35:43 - `78c573a3-d8de-4658-8e06-ee4d39711fd8.jsonl`
- `/ll:ready-issue` - 2026-09-25T01:29:52 - `559586e1-5e99-4e04-8b13-db7e1060b910.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:17:35 - `f2929467-388f-4f26-bd46-bd63a1730405.jsonl`
- `/ll:wire-issue` - 2026-09-25T01:11:17 - `283a56a1-35bd-43bb-b2f7-64d9f104c2c4.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:06:50 - `42a934e3-5df9-4ac6-9296-d0ced0bc2261.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:19 - `4b76ee9e-e590-41ab-940d-a6df6f1554bd.jsonl`

## Conventions in Force

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Model tables are hand-edited and keyed on the concrete ID; superseded IDs are retained when new ones are added (`pricing.py` keeps `claude-opus-4-5`..`4-8` beside `claude-opus-5`; `advisor.py:57-58` keeps `claude-fable-5` and `claude-fable-5-1` at the same rank). Each module's tests hold a second hand-typed copy of the expected keys, and equality against that copy is the drift signal (`LIVE_RATES`, the literal rank set, the `(alias, expected)` parametrize list).
- **No cross-table guard exists today**, and no test references `MODEL_ALIASES` directly; the Scope 7 guard test is genuinely new coupling.
- **Contested point**: `MODEL_PRICING` uses only independent inline dict literals (`pricing.py:23-90`, even where values are identical) and no test asserts dict identity. The issue's shared-dict `is` requirement for the two haiku keys would be the first such use; the identical-rates outcome can also be enforced by value equality.
- The SDK/batch dispatch tests are `sonnet`-only (`test_host_runner_dispatch.py:406-432`) while the alias-map test is already parametrized over all four aliases.
