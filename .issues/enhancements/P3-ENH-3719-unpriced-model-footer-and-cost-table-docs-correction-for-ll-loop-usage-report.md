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
relates_to:
- BUG-3696
- BUG-3724
---

# ENH-3719: Unpriced-model footer and cost-table docs correction for ll-loop usage report

## Summary

**Baseline landed 2026-10-06 (PR #43); the contribution-aware residual below remains open.** Complete the `ll-loop run` footer so it names authoritative contribution models rather than a row's last-event summary, use the estimator's current pricing table, and correct the remaining CLI paragraph/docstring drift. The aggregate-model footer, JSON behavior and general docs sweep already landed. Split out of BUG-3696 (2026-10-04 Opus review) so the one-line Sonnet 5.5 price could land independently. The estimate uses published API list prices regardless of subscription/API billing; it is not the user's billed amount.

**Scope:** human-readable diagnostics and docs only. No pricing changes (BUG-3696 owns the Sonnet 5.5 rate), no family-prefix fallback (ENH-3703), no stable-JSON change, no cost-ceiling change, no history backfill, no change to model/token normalization or cost aggregation.

## Landed Baseline (PR #43, merge `3defb2a97`, commit `75cbb57eb`, 2026-10-06)

A change merged outside this issue's workflow implemented the **aggregate-model** footer. The issue stayed `open` because it does not meet this issue's contribution-aware contract. What is on `main`:

- `CostReport.unpriced_models` (sorted, de-duplicated concrete IDs) and `unpriced_missing_sentinels` (bool), diagnostic-only and absent from `to_dict()`; `read_json` defaults them empty.
- `table()` footer (only when the report has states): `Note: <ids> not priced; cost shown is n/a.` then, when any sentinel row exists, `Note: usage rows with no price identifier (unknown, None, "") contribute to n/a.`; concrete line first. The sentinel check is `model.strip().lower() in {"unknown", "none", "", " "}`, so it is case-insensitive (accepted deviation; `Unknown`/`NONE` are treated as missing).
- Tests: `test_fsm_cost_graph.py` (classification matrix, JSON round-trip, exact-ID variants, patched-table case), `test_cli_cost_table.py` (exact footer bytes: all-priced, concrete-only, sentinel-only, mixed, no-states) and `test_usage_reporter.py` (stdout footer with locked JSON; observed Sonnet 5.5 projection).
- Docs: `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/observability/realized-savings-verification.md`, `docs/observability/tier0-traces.md`.

**Residual gaps (this issue's remaining scope), verified on `main` 2026-10-07:**

1. **Aggregate-only diagnostics (functional).** `from_usage_jsonl` tests only the row's flat `model` (the *last* event's model on new rows) against the table, before the `USAGE_CONTRIBUTIONS_KEY` branch. For a BUG-3724 row, an earlier unpriced contribution behind a priced last model is never named, and an unpriced aggregate whose contributions are all priced produces a false `not priced; cost shown is n/a` note on a state that did price. No landed test uses `usage_contributions`.
2. **Documented behavior that does not exist.** `docs/reference/CLI.md` (Last-event-model limitation paragraph) says rows carrying `usage_contributions` "enumerate every unpriced model, so a known last model cannot hide an earlier unpriced or missing-ID one" — false until gap 1 is fixed. The same file also contains the `Mixed-model actions (BUG-3724)` paragraph twice, verbatim (merge artifact), and describes the footer only for the aggregate case.
3. **Table binding.** `cost_graph.py` imports `MODEL_PRICING` by name, so the footer and the estimator (`pricing.MODEL_PRICING`) are separate bindings; the landed patched-table test patches both module attributes by hand to compensate. Real-world severity is low; it matters for test fidelity and for the issue's "same table object" criterion.
4. **Stale docstring.** The `CostReport` docstring still says "Once BUG-3724 lands" (it has landed).

**Decision (2026-10-07):** keep the landed footer wording (`Note: … not priced; cost shown is n/a.`). Changing it would invalidate the byte-pinned tests for marginal benefit; the earlier "report an ID if it should be priced" advice is dropped from the contract. An Opus consult suggested rewording `cost shown is n/a` to avoid reading as the run total; not adopted for the same reason. The merge commit message's shell-mangled `$0.0421` → `/bin/bash.0421` is cosmetic and not amended.

## Current Behavior

1. `CostReport.from_usage_jsonl` (`scripts/little_loops/fsm/cost_graph.py`) sets a state's cost to `None` if any effective contribution is unpriced. The legacy absent-contribution-key branch skips pricing for a null token component or positive `*_missing` count; new rows price their authoritative contributions, each with its own completeness check. The existing `has_unknown_model` flag covers missing prices, incomplete observations and invalid attribution; it cannot identify the missing-price model IDs by itself.
2. `PerStateCost.table_row()` renders `n/a`, and `_compute_totals` leaves the run's total cost null. Known-cost subtotals are not presented as complete totals.
3. `estimate_cost_usd` returns `None` only for a model absent from `MODEL_PRICING` or any null token component. `INTRO_PRICING` is empty and `as_of` only affects it, so neither adds a third unpriced reason.
4. BUG-3724 is done: new action rows carry authoritative `usage_contributions` by model/batch/pricing date; the flat model/token summary is audit-only when that key exists. An absent key retains legacy aggregate pricing. A present empty/non-list envelope or invalid model attribution fails closed and never falls back to the parent last-model summary. Legacy JSON-null models still become the `"None"` sentinel after `str()`. The footer must follow these actual contribution/legacy branches.
5. PR #43 corrected the fallback, null-cost, table-row and column-definition docs. Remaining drift is the duplicated CLI mixed-model paragraph, its premature contribution-footer claim, and the `CostReport` docstring's future-tense BUG-3724 handoff; no second general docs sweep is required.

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
- Changing completed contribution attribution/accounting or model/token normalization
- Alias/rank selection tables (BUG-3701) and context windows (BUG-3704)

## Motivation

New host-reported model IDs silently erase state/run cost visibility and leave gaps in history cost coverage. Alias/rank/price coverage (BUG-3696) catches drift in tables the repo controls; this footer diagnoses models that arrive from the host outside those tables.

## Proposed Solution

1. **(Field and legacy-row collection landed in PR #43; residual = the contribution branch.)** `CostReport.unpriced_models: list[str]` exists and is populated from the aggregate `str(row.get("model", "unknown"))`. BUG-3724 has landed: move the collection after the `USAGE_CONTRIBUTIONS_KEY` branch decision so it inspects every authoritative contribution model when the key is present, and the aggregate model only for the legacy absent-key branch. Never use the parent model as a fallback for a present invalid contribution envelope. Check exact membership independently of the token-completeness branch. Do not infer missing prices from `cost is None` or `has_unknown_model`.
2. **Read the same table the estimator reads. (Residual — landed code binds `MODEL_PRICING` by name.)** Look up `MODEL_PRICING` as a module attribute at call time (`from little_loops import pricing`, then `pricing.MODEL_PRICING`), not through a `from ... import MODEL_PRICING` binding, so a test that patches the table affects the estimator and the footer identically. Tests use `patch.dict` or patch the module attribute; they must never leave the two readers disagreeing.
3. **Sentinel set.** Preserve the landed case-insensitive `_is_missing_model_sentinel`: after string conversion where the legacy branch already uses it, `.strip().lower()` matches `{"unknown", "none", ""}` (whitespace-only strings collapse into `""`). JSON-null legacy models become `"None"`; contribution objects with missing/non-string model identities set the missing-ID diagnostic without stringifying arbitrary values into concrete IDs. A sentinel is never included in `unpriced_models`; a concrete ID is reported verbatim, with no prefix/suffix normalization.
4. Render the footer in `table()` when the list is non-empty and the report has states. **(Landed with the PR #43 wording; the original `no pricing for model(s): … report an ID if it should be priced` text is superseded — see the 2026-10-07 decision above.)** Concrete IDs: `Note: <ids> not priced; cost shown is n/a.` Sentinels: one `Note: usage rows with no price identifier (unknown, None, "") contribute to n/a.` line without report/upgrade advice. Mixed concrete IDs and sentinels produce both lines, concrete first. A missing rate makes the affected state and run total unavailable rather than subtracting a contribution. The footer is end-user-facing; do not tell users to edit a Python module or promise that upgrading supplies a deliberately unsupported model's price. Do not serialize the list; `read_json` defaults it to empty.
5. **Contribution-aware diagnostics (completed BUG-3724 handoff).** Reuse the accounting branch/validated model extraction in `from_usage_jsonl`; a small local helper may avoid duplicated branch rules, with no persisted schema change. Enumerate each concrete authoritative contribution ID even when its tokens are incomplete, so a known last model cannot hide an earlier unpriced model. Missing/non-string/blank model identities get the missing-ID diagnostic. A present empty/non-list envelope or non-mapping item does not invent a concrete missing-price ID and cannot use the parent model. Preserve any existing invalid-attribution reason independently of model-price diagnostics; concrete IDs on readable contribution objects may still explain a real missing table entry without repairing the malformed attribution. Test a priced parent with an earlier unpriced contribution, an unpriced parent with all-priced contributions, incomplete contributions, and malformed/empty envelopes. Legacy rows cannot recover earlier model identities and remain exact-ID legacy estimates; document that limitation only for the absent-key path. No new fallback or attribution repair is part of this footer.

6. Remove the duplicated `Mixed-model actions (BUG-3724)` CLI paragraph, align its footer description with the completed contribution branch and fix the stale `CostReport` docstring. Preserve the already-landed exact-ID, null-cost, no-backfill and input/cache column guidance; known incomplete tokens still produce `n/a` without a missing-price footer.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/cost_graph.py` — **residual:** switch to call-time `pricing.MODEL_PRICING`, move diagnostic collection behind the contribution-vs-legacy branch in `from_usage_jsonl`, and fix the stale "Once BUG-3724 lands" docstring (field, footer and `to_dict`/`read_json` behavior landed in PR #43); keep `to_dict`, `read_json` parsing and `_compute_totals` semantics
- `scripts/tests/test_fsm_cost_graph.py`, `scripts/tests/test_usage_reporter.py`, `scripts/tests/test_cli_cost_table.py` — **residual:** contribution-aware cases (none of the landed tests exercises a contribution-bearing row); replace the hand-patched dual-binding table test with a single `pricing.MODEL_PRICING` patch
- `docs/reference/CLI.md` — per-state summary (~L1005–1057): footer/columns/flags landed in PR #43; **residual:** remove the verbatim-duplicated `Mixed-model actions (BUG-3724)` paragraph (appears twice), and keep the "Last-event-model limitation" paragraph's contribution claim only after the code makes it true

### Dependent Files

- `cli/loop/summary.py:_print_usage_summary` — production table caller; no change
- `cli/loop/runner.py` — summary exceptions are swallowed, so direct reporter regression coverage is required
- `fsm/executor.py:_check_cost_ceiling` — unchanged; an unpriced cost still follows `cost_ceiling_unknown`
- `issue_history/agent_quality.py` — null-cost coverage semantics remain accurate
- `fsm/__init__.py` — existing `CostReport` export; no new symbol
- `docs/reference/API.md`, `docs/observability/realized-savings-verification.md`, `docs/observability/tier0-traces.md` — PR #43's exact-ID/null-cost/footer guidance is already present; preserve it without a second sweep

### Tests

**Residual test set (2026-10-07):** add contribution-aware cases to `test_fsm_cost_graph.py` (and one stdout-footer case in `test_usage_reporter.py`): (a) `usage_contributions` [unpriced, priced] with a priced parent names the earlier unpriced ID; (b) an unpriced parent with all-priced contributions yields no note and numeric state cost; (c) missing/non-string/blank/case-insensitive sentinel contribution identities set only the missing-ID line; (d) empty/non-list envelopes and non-mapping items invent no ID and cannot use the parent model; (e) incomplete contributions still name their concrete unpriced model, while known incomplete models do not. Include a malformed sibling beside a readable unpriced contribution: name that concrete ID while retaining unavailable invalid-attribution cost. Patch only `pricing.MODEL_PRICING` once and assert footer and estimator agree.

Preserve the existing aggregate classification/exact-ID, table-byte, JSON round-trip/locked-key, empty-file and reporter/projection tests from PR #43. Their current 51-test baseline passes; do not recreate or re-pin those controls.

## Program Design

### Types

- `CostReport.unpriced_models: list[str]` — diagnostic-only, default empty; sorted, de-duplicated concrete effective pricing IDs absent from `pricing.MODEL_PRICING`, excluding missing-ID sentinels; read legacy aggregate IDs only when the contribution key is absent; otherwise inspect authoritative contribution identities; absent from stable JSON
- `CostReport.unpriced_missing_sentinels: bool` — existing independent missing-identifier flag, default false and absent from stable JSON; never put placeholders or stringified non-string contribution models in `unpriced_models`

### Signatures

- `CostReport.from_usage_jsonl(path)` — adds independent model-price membership tracking before the incomplete-token pricing shortcut
- `CostReport.table()` — optional concrete-ID and missing-ID footer lines, otherwise identical output; no footer without states
- `estimate_cost_usd(...) -> float | None` — unchanged

### Call Path

`cli/loop/summary.py:_print_usage_summary` -> `CostReport.from_usage_jsonl` -> membership in `pricing.MODEL_PRICING` for diagnostics and `estimate_cost_usd` for complete observations -> `CostReport.table` for the footer. `CostReport.write_json` -> `to_dict` retains the locked JSON; `CostReport.read_json` constructs a report with the diagnostic list's empty default.

## Implementation Steps

1. BUG-3696 has landed, so Sonnet 5.5 has an exact price. PR #43 landed the aggregate-model footer, JSON round-trip/reporter tests and doc sweep (see Landed Baseline).
2. Make diagnostics contribution-aware: collect after the contribution-vs-legacy branch decision, enumerate every authoritative contribution model, apply the sentinel rule to missing contribution identities, and look up `pricing.MODEL_PRICING` at call time.
3. Add the residual contribution-aware tests (a)–(e) and replace the dual-binding patch test.
4. Fix `docs/reference/CLI.md`: delete the duplicated `Mixed-model actions (BUG-3724)` paragraph and confirm the Last-event-model paragraph's contribution claim is now true; fix the stale `cost_graph.py` docstring.
5. Run `python -m pytest scripts/tests/`.

## Impact

- **Priority**: P3 — diagnoses silent `n/a` cost for any host-reported model outside the pricing table
- **Effort**: Small — contribution-aware diagnostics, one table-binding repair, focused regression cases and the remaining CLI/docstring corrections
- **Risk**: Low — diagnostics only; no fallback, aggregation or JSON change
- **Breaking Change**: No (tables with unpriced models gain a footer line)

## Acceptance Criteria

- [ ] Unknown model IDs are sorted and de-duplicated in the footer with complete or incomplete tokens; incomplete known models do not appear there (aggregate branch landed, PR #43; **contribution branch open**). BUG-3724 contributions are present: an earlier unpriced/missing-ID contribution followed by a known last model is diagnosed; malformed/empty envelopes cannot fall back to the parent model, and all-priced contributions ignore an unpriced parent summary
- [x] (PR #43; the landed check is case-insensitive, accepted) Sentinel set `{unknown, None, "", whitespace-only}` produces one missing-ID line without report advice; mixed concrete IDs and sentinels produce the two-line block; concrete IDs and exact-match variants (dated, `anthropic.`-prefixed, `[1m]`) appear verbatim
- [ ] The footer's membership check and `estimate_cost_usd` read the same `MODEL_PRICING` object (proved by a single patched-table test; landed code binds the name and its test patches both modules by hand — **open**)
- [x] (PR #43) Exact footer bytes are tested; empty reports have no footer; all-priced tables are byte-identical to legacy output
- [ ] Mixed known/unknown contributors preserve null state/run cost semantics (existing behavior; re-verify with `usage_contributions` rows)
- [x] (PR #43) Stable JSON keys are unchanged; an unknown-model report round-trips with null costs and intentionally loses its footer metadata
- [x] (PR #43) `_print_usage_summary` prints the unknown-ID footer and writes locked JSON with null costs in the same invocation; the observed Sonnet 5.5 projection renders `$0.3201` with no footer
- [x] (PR #43) Footer wording is end-user-facing (no instruction to edit `little_loops.pricing`)
- [ ] (landed in PR #43 except the contribution claim and the duplicated BUG-3724 paragraph — **open**) CLI/API/observability docs match actual `n/a`/null behavior and the input/cache column definitions, distinguish per-state flags from `totals.has_unknown_model` and the missing-price diagnostic, describe the footer, and state the completed contribution-aware mixed-model/batch/date accounting and the absent-key legacy limitation, exact-match and no-backfill limitations
- [ ] `python -m pytest scripts/tests/` exits 0

## Related

- BUG-3696 — adds the Sonnet 5.5 price and alias/rank/price coverage; landed; the existing priced reporter projection relies on the rate
- BUG-3701 — alias/rank correction; independent of this footer
- ENH-3703 — deferred family-prefix approximate pricing decision after this footer; retained under EPIC-3562
- BUG-3724 — completed model/batch/date contribution accounting; consume its authoritative contribution and fail-closed invalid-attribution contract
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

- Pre-implementation consumer review - 2026-10-07 - Reproduced both parent/contribution disagreement defects at `659639f17`: a priced parent hides an earlier unpriced ID; an unpriced parent over priced contributions emits a false footer despite numeric state cost. Reconciled the concrete-ID list/separate sentinel flag and preserved landed case-insensitive sentinels. Reduced directives to the residual contribution/table-binding/CLI/docstring work; existing cost/report suites: 51 passed. No implementation or new score claimed.

- Pre-implementation epic review - 2026-10-07 - Found PR #43 (`75cbb57eb`, merged 2026-10-06 outside the issue workflow) had landed the aggregate-model footer, tests and docs while this issue and EPIC-3562 still described it as untouched. Verified residual gaps on `main`: no contribution-aware enumeration (earlier unpriced contribution behind a priced last model is never named; unpriced aggregate over all-priced contributions emits a false note), name-bound `MODEL_PRICING`, stale docstring, CLI.md claims contribution enumeration that does not exist and carries the BUG-3724 paragraph twice. Rewrote scope to the residual; kept landed wording (Opus's reword suggestion not adopted: byte-pinned tests, marginal benefit). 51 landed cost tests pass. No implementation claimed.

- Pre-implementation epic review - 2026-10-05 - Reconciled with completed BUG-3724. Footer diagnostics now follow authoritative contributions versus the absent-key legacy branch, independently of incomplete tokens; malformed envelopes cannot fall back to the parent model or manufacture a missing-price ID. Added both-direction parent/contribution disagreement controls while preserving stable JSON/accounting scope.

- Pre-implementation epic review - 2026-10-04 - Added the functional BUG-3724 handoff after the Opus critique: the second lander makes diagnostics contribution-aware and tests an earlier unpriced model hidden by a known last model. Legacy identities remain unrecoverable; footer scope and stable JSON remain unchanged.

- Split from BUG-3696 - 2026-10-04 - `/ll:advise` with Opus (confidence 0.78): footer, sentinel matrix, JSON-loss/reporter tests and the doc sweep moved here so pricing could land alone; test matrix trimmed to four; added same-table lookup, pinned sentinel set (incl. real `"None"` from JSON-null model) and last-event-model limitation.
