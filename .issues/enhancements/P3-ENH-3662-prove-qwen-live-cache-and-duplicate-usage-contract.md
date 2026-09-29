---
id: ENH-3662
type: ENH
title: Prove Qwen live cache and duplicate usage contract
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels: [observability, multi-host, producer-evidence]
relates_to: [ENH-3648, ENH-3534, ENH-3544]
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
map for proved entries, then hand a replay contract to ENH-3534. Keep Qwen
incomplete in EPIC-3562 until stored ingestion, trigger and reader are proven.
