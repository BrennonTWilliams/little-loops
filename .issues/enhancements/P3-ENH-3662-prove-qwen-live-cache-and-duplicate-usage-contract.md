---
id: ENH-3662
type: ENH
title: Prove Qwen live cache and duplicate usage contract
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels:
- observability
- multi-host
- producer-evidence
relates_to:
- ENH-3648
- ENH-3534
- ENH-3544
blocks:
- ENH-3673
---

# ENH-3662: Prove Qwen live cache and duplicate usage contract

## Evidence gap

ENH-3648 captured a real Qwen Code 0.24.6 on-disk UI/assistant usage pair.
The live probe failed after the configured OAuth free tier was discontinued.
The pair reports zero cached content and no cache-write field; input
inclusivity, thought-token inclusion, response identity across the two
representations, and resume/compaction behavior remain unknown.

## Required proof

With working authentication, capture a sanitized versioned live invocation
and matching transcript with tool use, cache hit/write if available, and
resume. Establish whether `promptTokenCount` includes cached input, whether
`thoughtsTokenCount` is included in `candidatesTokenCount`, what missing fields
mean, and how `response_id`/`prompt_id` joins the assistant `uuid` without
double-counting. Update `scripts/tests/fixtures/qwen/README.md` and the typed
map for proved entries, then hand a replay contract to ENH-3673; ENH-3534
owns only shared replay/refresh. Keep Qwen incomplete in EPIC-3562 until
stored ingestion, trigger and reader are proven.

## Acceptance Criteria

- [ ] Capture a sanitized, versioned Qwen live/transcript pair with tool use and resume under working authentication. Preserve enough of the native assistant record, including `message.parts`, to make the transcript usable in `iter_events` parser tests; the current reduced usage pair yields no event.
- [ ] Record per-metric/channel `supported`, evidence-backed `unsupported`, or `unknown` verdicts for input, output, cache read/write, and thought tokens. Prove or leave explicit the inclusivity, omission, grain/reset, and UI/assistant request-join semantics.
- [ ] Give ENH-3673 the complete-enough native fixture and duplicate-pair rule. ENH-3673 proves that the parser preserves `usageMetadata` and that one response produces one stored observation and a fresh selected read.
- [ ] If authentication or nonzero cache behavior remains unavailable, record the exact blocker and keep those semantics `unknown`; keep this evidence issue open or `blocked` rather than claiming unsupported telemetry.
