---
id: ENH-3719
type: ENH
title: Unpriced-model footer and cost-table docs correction for ll-loop usage report
priority: P3
status: open
testable: true
discovered_by: ll-issues-create
discovered_date: '2026-10-04'
captured_at: '2026-10-04T01:15:41Z'
parent: EPIC-3562
blocked_by:
- BUG-3696
---

# ENH-3719: Unpriced-model footer and cost-table docs correction for ll-loop usage report

## Summary

The `ll-loop run` usage table shows `est_cost` as `n/a` for any model ID absent from `MODEL_PRICING` with no explanation. Add a footer naming unpriced model IDs (including IDs on rows that also have incomplete tokens), and correct the stale cost-table documentation. Split out of BUG-3696 (2026-10-04 Opus review) so the one-line Sonnet 5.5 price could land and unblock BUG-3701 without waiting on this matrix. The estimate uses published API list prices regardless of subscription/API billing; it is not the user's billed amount.

**Scope:** human-readable diagnostics and docs only. No pricing changes (BUG-3696 owns the Sonnet 5.5 rate), no family-prefix fallback (ENH-3703), no stable-JSON change, no cost-ceiling change, no history backfill, no change to model/token normalization or cost aggregation.

## Current Behavior

1. `CostReport.from_usage_jsonl` (`scripts/little_loops/fsm/cost_graph.py`) sets a state's cost to `None` if any row is unpriced. It also skips the estimator entirely for a row with a null token component or a positive `*_missing` count. The existing `has_unknown_model` flag therefore covers both an absent price and an incomplete observation; it cannot say why a row is unpriced.
2. `PerStateCost.table_row()` renders `n/a`, and `_compute_totals` leaves the run's total cost null. Known-cost subtotals are not presented as complete totals.
3. `estimate_cost_usd` returns `None` only for a model absent from `MODEL_PRICING` or any null token component. `INTRO_PRICING` is empty and `as_of` only affects it, so neither adds a third unpriced reason.
4. A row's `model` is `usage_events[-1].model` (`fsm/executor.py:2761`), so a mixed-model action is priced and named by its last model only. The persisted row is written as `event.get("model", "unknown")` (`fsm/persistence.py:~1104`); a JSON-null model therefore reaches `from_usage_jsonl` as `None`, and `str(None)` is `"None"`.
5. Stale docs: CLI/observability text still describes `~$` fallback, `0.0` unknown costs, a printed `TOTAL` row and thousands separators, and mis-defines the `input` and `cache` columns.

## Expected Behavior

- A report built from `usage.jsonl` lists each ID absent from `MODEL_PRICING` once in a sorted footer, even when the same row also has incomplete tokens.
- A known model with incomplete tokens remains unpriced and does not create a footer entry. The footer explains missing prices, not every possible reason for `n/a`.
- Reports containing only priced models retain their existing table output byte-for-byte. The stable JSON is unchanged and cannot carry the footer through `read_json`.
- Missing model identifiers have a separate footer diagnostic, with no advice to report a placeholder as a model.

## Scope Boundaries

Out of scope (each owned elsewhere or deliberately excluded):

- The Sonnet 5.5 rate and any other `MODEL_PRICING` change (BUG-3696)
- Family-prefix or approximate pricing (ENH-3703)
- Changes to the stable JSON schema, `_compute_totals` aggregation, `executor._check_cost_ceiling` or history backfill of stored null `cost_usd`
- Changing event model attribution (`executor.py:2761` last-event model) or model/token normalization
- Alias/rank selection tables (BUG-3701) and context windows (BUG-3704)

## Motivation

New host-reported model IDs silently erase state/run cost visibility and leave gaps in history cost coverage. Alias/rank/price coverage (BUG-3696) catches drift in tables the repo controls; this footer diagnoses models that arrive from the host outside those tables.

## Proposed Solution

1. Add `CostReport.unpriced_models: list[str] = field(default_factory=list)`, populated as sorted, de-duplicated values from the existing `str(row.get("model", "unknown"))` lookup. Check exact membership independently of the token-completeness branch. Do not infer missing prices from `cost is None` or `has_unknown_model`.
2. **Read the same table the estimator reads.** Look up `MODEL_PRICING` as a module attribute at call time (`from little_loops import pricing`, then `pricing.MODEL_PRICING`), not through a `from ... import MODEL_PRICING` binding, so a test that patches the table affects the estimator and the footer identically. Tests use `patch.dict` or patch the module attribute; they must never leave the two readers disagreeing.
3. **Sentinel set.** The missing-model sentinels, after `str()` and `.strip()`, are `{"unknown", "None", ""}` (whitespace-only strings collapse into `""`). `"None"` is a real production case from a JSON-null model, not a hypothetical. A sentinel is never reported as a model; a concrete ID is reported verbatim, with no prefix/suffix normalization.
4. Render the footer in `table()` when the list is non-empty and the report has states. For concrete IDs append `no pricing for model(s): <comma-separated IDs> — affected state costs shown as n/a; report an ID if it should be priced`. Sentinels produce one `missing model ID — affected state costs shown as n/a` line without report/upgrade advice. Mixed concrete IDs and sentinels produce both lines, concrete first. A missing rate makes the affected state and run total unavailable rather than subtracting a contribution. The footer is end-user-facing; do not tell users to edit a Python module or promise that upgrading supplies a deliberately unsupported model's price. Do not serialize the list; `read_json` defaults it to empty.
5. **Mixed-model rows (known limitation).** Because a row's model is the last usage event's model (`executor.py:2761`), a mixed-model action is priced and named by its last model only, and the footer cannot name earlier ones. Document it in the CLI reference; do not change event attribution here.
6. Correct the stale docs: `~$` fallback, `0.0` unknown costs, a printed `TOTAL` row, thousands separators. Fix the column definitions: `input` is the aggregate `input_tokens` field without cache tokens; `cache` combines `cache_read_tokens` and `cache_creation_tokens`. State that costs are exact-ID estimates, that state/run costs become null if any contributor is unpriced, and that stored null history costs are not back-filled. Distinguish the broad `has_unknown_model` flag (any unpriceable contribution) from this missing-price diagnostic; incomplete tokens alone still produce `n/a` without the footer. Record the exact-match limitation: dated, `anthropic.`-prefixed or `[1m]` model IDs stay unpriced and the footer now names them.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/cost_graph.py` — import the pricing module, collect diagnostic IDs in `from_usage_jsonl`, add the report field and table footer; keep `to_dict`, `read_json` parsing and `_compute_totals` semantics
- `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_usage_reporter.py`, `scripts/tests/test_cli_cost_table.py` — diagnostics and output compatibility
- `docs/reference/CLI.md` — per-state summary (~L1005–1057): correct examples, input/cache column definitions, state-vs-total JSON flags, footer, mixed-model and no-backfill limitations
- `docs/reference/API.md` — `## little_loops.pricing` (~L12630) description of exact-ID cost semantics; keep the heading pinned by `test_wiring_reference_docs.py`
- `docs/observability/realized-savings-verification.md:39` — replace stale `cost_usd: 0.0` with null
- `docs/observability/tier0-traces.md:147` — document the footer alongside existing table output

### Dependent Files

- `cli/loop/summary.py:_print_usage_summary` — production table caller; no change
- `cli/loop/runner.py` — summary exceptions are swallowed, so direct reporter regression coverage is required
- `fsm/executor.py:_check_cost_ceiling` — unchanged; an unpriced cost still follows `cost_ceiling_unknown`
- `issue_history/agent_quality.py` — null-cost coverage semantics remain accurate
- `fsm/__init__.py` — existing `CostReport` export; no new symbol

### Tests

Four tests, deliberately not an exhaustive byte-pinning matrix (over-specified wording tests make the footer brittle for little added protection):

1. **Parametrized classification matrix** (`test_fsm_cost_graph.py`): model {known, unknown concrete, each sentinel `unknown`/`None`/`""`/whitespace} × tokens {complete, explicit null component, positive `*_missing`}. Unknown+incomplete names the ID; known+incomplete does not. Include multiple unpriced IDs across states, repeated IDs, mixed priced/unpriced contributors (one sorted footer; affected state and run costs null; complete known-only states keep numeric costs), and dated, `anthropic.`-prefixed and `[1m]` Sonnet 5.5 IDs staying unpriced and appearing verbatim. Legacy absent-token keys keep their zero defaults. Patch the table with `patch.dict` in at least one case to prove footer and estimator read the same table.
2. **Exact bytes** (`test_cli_cost_table.py`): one footer-present table (concrete-only, sentinel-only and mixed two-line block, including trailing newline), one complete all-priced table byte-identical to the legacy output, and a no-states report with no footer. `fixture_jsonl` in `test_fsm_cost_graph.py` and `test_cli_cost_table.py` uses unpriced Sonnet 4.5, so its table deliberately gains the footer; do not relabel it as priced. Preserve the reporter's existing silence for missing/empty files.
3. **Unknown-model JSON round-trip**: `loaded.to_dict() == report.to_dict()`, null costs preserved, no `unpriced_models` key, loaded list empty, loaded table has no footer. Do not assert dataclass equality. The existing `test_enh3538_token_observations.py` incomplete-known-model round-trip stays valid but cannot alone prove unknown-model metadata loss.
4. **Reporter** (`test_usage_reporter.py`): `_print_usage_summary` with an unknown-model fixture and a `cost_output_json` destination together: stdout contains the footer while the written JSON keeps its locked keys and null costs with no diagnostic list. A second case uses the observed run's exact-ID Sonnet 5.5 projection (first row: 14 input, 5748 output, 433686 cache-read, 70335 cache-creation → $0.3200827, rendered `$0.3201`) and asserts the price renders with no footer and no `n/a`. Requires BUG-3696's rate.

Keep the locked per-state/top-level JSON key tests.

## Program Design

### Types

- `CostReport.unpriced_models: list[str]` — diagnostic-only, default empty; sorted, de-duplicated existing lookup values absent from `pricing.MODEL_PRICING`, including the reserved missing-ID sentinels; absent from stable JSON

### Signatures

- `CostReport.from_usage_jsonl(path)` — adds independent model-price membership tracking before the incomplete-token pricing shortcut
- `CostReport.table()` — optional concrete-ID and missing-ID footer lines, otherwise identical output; no footer without states
- `estimate_cost_usd(...) -> float | None` — unchanged

### Call Path

`cli/loop/summary.py:_print_usage_summary` -> `CostReport.from_usage_jsonl` -> membership in `pricing.MODEL_PRICING` for diagnostics and `estimate_cost_usd` for complete observations -> `CostReport.table` for the footer. `CostReport.write_json` -> `to_dict` retains the locked JSON; `CostReport.read_json` constructs a report with the diagnostic list's empty default.

## Implementation Steps

1. Land BUG-3696 first so Sonnet 5.5 has an exact price.
2. Add independent unpriced-ID collection (module-attribute table lookup, pinned sentinel set) and the conditional footer; implement test 1 (matrix) and test 2 (exact bytes).
3. Add test 3 (JSON round-trip) and test 4 (reporter stdout/JSON plus observed-run projection).
4. Correct the listed reference/observability docs and examples; record the mixed-model, exact-match and no-backfill limitations.
5. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 — diagnoses silent `n/a` cost for any host-reported model outside the pricing table
- **Effort**: Medium — footer, four tests and a four-doc sweep (much of it pre-existing doc drift)
- **Risk**: Low — diagnostics only; no fallback, aggregation or JSON change
- **Breaking Change**: No (tables with unpriced models gain a footer line)

## Acceptance Criteria

- [ ] Unknown model IDs are sorted and de-duplicated in the footer with complete or incomplete tokens; incomplete known models do not appear there
- [ ] Sentinel set `{unknown, None, "", whitespace-only}` produces one missing-ID line without report advice; mixed concrete IDs and sentinels produce the two-line block; concrete IDs and exact-match variants (dated, `anthropic.`-prefixed, `[1m]`) appear verbatim
- [ ] The footer's membership check and `estimate_cost_usd` read the same `MODEL_PRICING` object (proved by a patched-table test)
- [ ] Exact footer bytes are tested; empty reports have no footer; all-priced tables are byte-identical to legacy output
- [ ] Mixed known/unknown contributors preserve null state/run cost semantics
- [ ] Stable JSON keys are unchanged; an unknown-model report round-trips with null costs and intentionally loses its footer metadata
- [ ] `_print_usage_summary` prints the unknown-ID footer and writes locked JSON with null costs in the same invocation; the observed Sonnet 5.5 projection renders `$0.3201` with no footer
- [ ] Footer wording is end-user-facing (no instruction to edit `little_loops.pricing`)
- [ ] CLI/API/observability docs match actual `n/a`/null behavior and the input/cache column definitions, distinguish per-state flags from `totals.has_unknown_model` and the missing-price diagnostic, describe the footer, and state the mixed-model (last-event model), exact-match and no-backfill limitations
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3696 — adds the Sonnet 5.5 price and alias/rank/price coverage; hard dependency (test 4's priced projection needs the rate)
- BUG-3701 — alias/rank correction; independent of this footer
- ENH-3703 — family-prefix approximate pricing (separate follow-up)
- BUG-3704 — effective context windows, independent scope

## Related Key Documentation

| Document | Relevance |
| --- | --- |
| `docs/reference/CLI.md` | Per-state usage table and JSON flags |
| `docs/reference/API.md` | Pricing API and stable cost semantics |
| `docs/ARCHITECTURE.md` | History usage ingestion and null cost coverage |

## Status

**Open** | Created: 2026-10-04 | Priority: P3

## Session Log

- Split from BUG-3696 - 2026-10-04 - `/ll:advise` with Opus (confidence 0.78): footer, sentinel matrix, JSON-loss/reporter tests and the doc sweep moved here so pricing could land alone; test matrix trimmed to four; added same-table lookup, pinned sentinel set (incl. real `"None"` from JSON-null model) and last-event-model limitation.
