---
id: ENH-3546
type: ENH
title: Establish Claude usage producer contract and measured provenance
priority: P2
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T17:40:15Z'
labels:
- observability
relates_to:
- ENH-3528
- BUG-3531
confidence_score: 90
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# ENH-3546: Establish Claude usage producer contract and measured provenance

## Summary

Decide and implement which Claude usage observations can be persisted as `provenance='measured'`. Today every Claude row is `unknown` (BUG-3531 Decision 1: "Claude rows stay `unknown` (ENH-3528 owns any Claude promotion)"), but ENH-3528 does not take on that promotion. Without it, most `ll-ctx-stats` figures will be labelled `unknown`, which makes ENH-3528's labelling low-value.

## Current Behavior

- Claude live `result.usage` (headless CLI) and transcript assistant `message.usage` currently use unknown provenance. Legacy NULL provenance is also interpreted as unknown.
- No producer-contract evidence is recorded for either Claude path, in the way BUG-3531 Decision 6 records it for Codex.

## Expected Behavior

For each Claude acquisition path (live `result`, transcript `message.usage`):

1. Establish the producer contract from captured fixtures, with the Claude Code version recorded: whether `input_tokens` is uncached, whether `cache_creation_input_tokens`/`cache_read_input_tokens` are always emitted, what an omitted field means, and what scope the figure covers (per request vs. per invocation).
2. Set `measured` only for new observations that satisfy that contract with valid known components; all others stay `unknown`.
3. Legacy rows are not promoted.

This establishes provenance only. Live/transcript overlap (ENH-3528 coverage) is unchanged.

### Eligibility and rebuild invariants

Before promotion, record a per-acquisition-path validity predicate backed by versioned producer fixtures. All required components must be nonnegative non-boolean integers with verified disjoint semantics; missing, null, string, float, negative and boolean values must not be silently coerced to zero. Define empty/absent/wrong-type usage-container handling and whether an explicit all-zero block is a measurement separately for each producer path.

A Claude-shaped event is not host evidence. Live eligibility must be evaluated with the resolved runner's verified host; transcript eligibility requires verified source attribution and evidence for the acquisition contract. Other hosts normalized into assistant/message shapes cannot acquire Claude measured provenance. Keep the generic parser conservative until host/path qualification is available; record where that qualification is applied rather than promoting solely in an event-type branch.

Legacy observations remain unknown after rebuild, not only after migration. Rebuild deletes and reconstructs derived transcript usage, so an insertion timestamp is not evidence of a newly qualified source. Define a durable capture/contract eligibility discriminator that replay preserves, or an equivalent rule retaining legacy uncertainty; `host_basis='handle'` alone proves host attribution, not producer-version eligibility. Missing evidence stays unknown. Any new persisted discriminator requires an append-only migration and manifest update.

## Scope Boundaries

- **In scope**: producer-contract evidence and `measured` eligibility for Claude live `result.usage` and transcript `message.usage`.
- **Out of scope**: live/transcript overlap reconciliation; legacy row promotion; other hosts (ENH-3534).

## Program Design

### Types

- `TokenUsage.provenance` is measured only after host/path and component qualification. Record any additive eligibility discriminator needed to preserve legacy uncertainty across replay; no unconditional host-wide promotion.

### Signatures

- `usage_from_event(event: dict[str, Any], *, default_model: str) -> TokenUsage | None` — preserve the public parser contract; validate components here, and qualify measured provenance at the verified-host/path boundary. If an additive host-aware argument/helper is needed, define it explicitly with conservative defaults.
- `record_usage_event` — unchanged; persists the provenance it is given.

### Call Path

- Claude `result` event → `usage_from_event` → `FSMExecutor._finish` → `record_usage_event`
- transcript `assistant` record + persisted eligibility/attribution evidence → `_backfill_usage_events` → transcript `usage_events` insert

## Integration Map

- `scripts/little_loops/subprocess_utils.py` (parser and verified runner stamping), `session_store/writers.py` (`_backfill_usage_events`), `session_store/lifecycle.py` (replay input); `session_store/schema.py` and `session_store/schema_manifest.json` if a durable eligibility discriminator is added.
- Tests: `test_subprocess_utils.py`, `test_session_store_writers.py`, `test_session_store_lifecycle.py`, migration/manifest tests as needed; versioned producer fixtures under `scripts/tests/fixtures/`.

## Impact

- **Priority**: P2 — without it ENH-3528's labels are mostly `unknown`.
- **Effort**: Small to medium (mostly evidence capture).
- **Risk**: Low to medium — must not certify fields whose semantics are unverified.

## Acceptance Criteria

- [ ] A non-Claude producer with a Claude-shaped usage block remains unknown under the Claude contract; absent/unverified host/path evidence cannot be promoted.
- [ ] Legacy transcript observations remain unknown after migration, rebuild and repeated replay, even when their component values look complete; newly qualified observations remain measured through replay.
- [ ] The per-path predicate covers malformed components/containers and explicit zero; no invalid component is coerced into measured zero, and a captured CLI version does not certify unversioned legacy input.

- [ ] Fixtures plus a README record the contract for both Claude paths.
- [ ] Contract-satisfying new rows persist as `measured`; malformed, partial or unverified rows stay `unknown`; legacy rows are unchanged (tests).
- [ ] Live and transcript paths set provenance explicitly only at a verified host/path eligibility boundary; component validation and related docstrings are updated.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- Integration Map corrected by the epic review: transcript backfill is in `writers.py`; lifecycle owns replay input.
- The component-validation floor is specified; per-path producer evidence, zero/container rules and durable legacy eligibility remain readiness gates. The earlier confidence score predates these requirements.

## Status

**Open** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:confidence-check` - 2026-09-25T01:02:57 - `1524097a-5772-41c1-ba3b-6e5742f08a6c.jsonl`
