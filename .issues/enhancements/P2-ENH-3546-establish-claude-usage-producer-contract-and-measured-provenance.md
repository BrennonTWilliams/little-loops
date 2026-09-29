---
id: ENH-3546
type: ENH
title: Establish Claude usage producer contract and measured provenance
priority: P2
status: done
parent: EPIC-3562
epic: EPIC-3562
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
completed_at: '2026-09-29T08:22:43Z'
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

1. Establish the producer contract from captured fixtures, with the Claude Code version recorded: whether `input_tokens` is uncached, whether `cache_creation_input_tokens`/`cache_read_input_tokens` are always emitted, what an omitted field means, what scope the figure covers (per request vs. per invocation), and whether repeated assistant records are snapshots or distinct usage observations.
2. Set `measured` only for new observations that satisfy that contract with valid known components; all others stay `unknown`.
3. Legacy rows are not promoted.

This establishes provenance only. Live/transcript overlap (ENH-3528 coverage) is unchanged.

### Eligibility and rebuild invariants

Before promotion, record a per-acquisition-path validity predicate backed by versioned producer fixtures. All required components must be nonnegative non-boolean integers with verified disjoint semantics; missing, null, string, float, negative and boolean values must not be silently coerced to zero. Define empty/absent/wrong-type usage-container handling and whether an explicit all-zero block is a measurement separately for each producer path.

A Claude-shaped event is not host evidence. Live eligibility must be evaluated with the resolved runner's verified host; transcript eligibility requires verified source attribution and evidence for the acquisition contract. Other hosts normalized into assistant/message shapes cannot acquire Claude measured provenance. Keep the generic parser conservative until host/path qualification is available; record where that qualification is applied rather than promoting solely in an event-type branch.

Legacy observations remain unknown after rebuild, not only after migration. Rebuild deletes and reconstructs derived transcript usage, so an insertion timestamp is not evidence of a newly qualified source. Define a durable capture/contract eligibility discriminator that replay preserves, or an equivalent rule retaining legacy uncertainty; `host_basis='handle'` alone proves host attribution, not producer-version eligibility. Missing evidence stays unknown. Any new persisted discriminator requires an append-only migration and manifest update.

**Where the discriminator lives (2026-09-28):** `rebuild()` deletes and regenerates transcript `usage_events` from `raw_events`, so a discriminator stored only on `usage_events` is lost on rebuild. Store it on **`raw_events`** at ingest time and copy it to `usage_events` on replay — the same pattern BUG-3542 used for `host_basis` (v55 added it to both tables). The migration is ordered in the epic's § Schema coordination with ENH-3532 (which also adds a `raw_events` column).

**Evidence capture is step one.** No `scripts/tests/fixtures/claude/` directory exists. Capture a headless `claude -p --output-format stream-json` run (live `result` path) and the matching on-disk transcript (`message.usage` path), with the Claude Code version recorded, before any code change. Include at least one cache-hit turn so `cache_read_input_tokens` is non-zero.

Capture and document assistant `uuid` and `message.id` behavior across repeated transcript entries, including whether usage fields change before a final entry. The current `ll-ctx-stats` direct reader deduplicates by `uuid`, while `_backfill_usage_events` writes each qualifying raw line; neither rule is certified as the producer's observation identity. Provide the evidence to ENH-3651 for full/incremental derivation and ENH-3656 for numeric-parity or deliberate-correction tests. Do not choose a key from equal token values alone or add a redundant raw UUID column: the stored raw payload already carries these fields.

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

## Captured Producer Evidence (2026-09-29)

The sanitized `scripts/tests/fixtures/claude/` captures come from Claude Code
2.1.284. The paired headless `result.usage` and on-disk transcript have two
requests with nonzero cache reads. The live result's four token components
equal the sums of the requests' final transcript components (18 uncached
input, 11223 cache creation, 38429 cache read, 165 output). The transcript
records each carry `version: 2.1.284`, giving ingest a producer-version
signal that does not depend on a current machine-wide CLI version.

One request appears twice under the same `message.id` and different outer
`uuid`s in the paired capture. A second real 2.1.284 transcript sample has
five records for one `message.id`: four report output 4, then the final one
reports output 481. Thus the last valid snapshot of a verified message ID is
the final request observation; outer UUIDs are record IDs, not request IDs.
ENH-3651 owns applying this identity rule in full and incremental derivation.

The fixtures do not establish a contract for omitted components or an all-zero
usage block, so these remain unknown. The measured predicate requires all four
components to be nonnegative non-boolean integers, a verified Claude Code
host/path, and the captured version. Anthropic's API usage documentation
defines the three input fields as disjoint components; see the fixture README.
Legacy raw rows retain unknown eligibility across rebuild even if their
stored payload contains a qualifying version and values.

## Acceptance Criteria

- [x] A non-Claude producer with a Claude-shaped usage block remains unknown under the Claude contract; absent/unverified host/path evidence cannot be promoted.
- [x] Legacy transcript observations remain unknown after migration, rebuild and repeated replay, even when their component values look complete; newly qualified observations remain measured through replay.
- [x] The per-path predicate covers malformed components/containers and explicit zero; no invalid component is coerced into measured zero, and a captured CLI version does not certify unversioned legacy input.

- [x] Fixtures plus a README record the contract for both Claude paths, including repeated assistant record identity (`uuid` versus `message.id`), changed usage on a repeated ID and the final-usage boundary; unsupported cases are explicitly unknown.
- [x] Contract-satisfying new rows persist as `measured`; malformed, partial or unverified rows stay `unknown`; legacy rows are unchanged (tests).
- [x] Live and transcript paths set provenance explicitly only at a verified host/path eligibility boundary; component validation and related docstrings are updated.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-24_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- Integration Map corrected by the epic review: transcript backfill is in `writers.py`; lifecycle owns replay input.
- The component-validation floor is specified; per-path producer evidence, zero/container rules and durable legacy eligibility remain readiness gates. The earlier confidence score predates these requirements.

## Status

**Done** | Created: 2026-09-24 | Priority: P2


## Session Log
- `/ll:manage-issue` - 2026-09-29T08:22:43 - `688ef729-26a9-43d5-8442-56084d826e08.jsonl`
- `/ll:confidence-check` - 2026-09-25T01:02:57 - `1524097a-5772-41c1-ba3b-6e5742f08a6c.jsonl`


## Resolution

- **Action**: Implement
- **Completed**: 2026-09-29
- **Status**: Done

### Changes Made

- Claude 2.1.284 live and transcript captures establish measured eligibility; legacy and unverified usage stays unknown through replay.

### Verification Results

- Full local suite: 27,525 passed, 301 skipped.
- Ruff lint and format, host-map verifier and private-reference verifier: passed. The configured mypy command is blocked by this environment's untyped `ruamel` dependency; a run with the project config and Python 3.12 target reports existing `no-any-return` and `unused-ignore` errors across the package.
