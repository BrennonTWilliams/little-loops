---
id: ENH-3546
type: ENH
title: Establish Claude usage producer contract and measured provenance
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- observability
relates_to:
- ENH-3528
- BUG-3531
---

# ENH-3546: Establish Claude usage producer contract and measured provenance

## Summary

Decide and implement which Claude usage observations can be persisted as `provenance='measured'`. Today every Claude row is `unknown` (BUG-3531 Decision 1: "Claude rows stay `unknown` (ENH-3528 owns any Claude promotion)"), but ENH-3528 does not take on that promotion. Without it, most `ll-ctx-stats` figures will be labelled `unknown`, which makes ENH-3528's labelling low-value.

## Current Behavior

- Claude live `result.usage` (headless CLI) and transcript assistant `message.usage` are written with `provenance` NULL (`unknown`), via ENH-3538's unknown-default writer.
- No producer-contract evidence is recorded for either Claude path, in the way BUG-3531 Decision 6 records it for Codex.

## Expected Behavior

For each Claude acquisition path (live `result`, transcript `message.usage`):

1. Establish the producer contract from captured fixtures, with the Claude Code version recorded: whether `input_tokens` is uncached, whether `cache_creation_input_tokens`/`cache_read_input_tokens` are always emitted, what an omitted field means, and what scope the figure covers (per request vs. per invocation).
2. Set `measured` only for new observations that satisfy that contract with valid known components; all others stay `unknown`.
3. Legacy rows are not promoted.

This establishes provenance only. Live/transcript overlap (ENH-3528 coverage) is unchanged.

## Scope Boundaries

- **In scope**: producer-contract evidence and `measured` eligibility for Claude live `result.usage` and transcript `message.usage`.
- **Out of scope**: live/transcript overlap reconciliation; legacy row promotion; other hosts (ENH-3534).

## Program Design

### Types

- No new types; `TokenUsage.provenance` is set to `"measured"` on contract-satisfying Claude observations.

### Signatures

- `usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None` — unchanged; the Claude `result` branch sets provenance.
- `record_usage_event` — unchanged; persists the provenance it is given.

### Call Path

- Claude `result` event → `usage_from_event` → `FSMExecutor._finish` → `record_usage_event`
- transcript `assistant` record → `_backfill_usage_events` → `record_usage_event`

## Integration Map

- `scripts/little_loops/subprocess_utils.py` (`usage_from_event`), `session_store/writers.py`, transcript usage backfill in `session_store/lifecycle.py`.
- Tests: `test_subprocess_utils.py`, `test_session_store_writers.py`; fixtures under `scripts/tests/fixtures/`.

## Impact

- **Priority**: P2 — without it ENH-3528's labels are mostly `unknown`.
- **Effort**: Small to medium (mostly evidence capture).
- **Risk**: Low to medium — must not certify fields whose semantics are unverified.

## Acceptance Criteria

- [ ] Fixtures plus a README record the contract for both Claude paths.
- [ ] Contract-satisfying new rows persist as `measured`; malformed, partial or unverified rows stay `unknown`; legacy rows are unchanged (tests).
- [ ] `usage_from_event`'s Claude `result` branch and the transcript usage path set provenance explicitly; related docstrings are updated.

## Status

**Open** | Created: 2026-09-24 | Priority: P2
