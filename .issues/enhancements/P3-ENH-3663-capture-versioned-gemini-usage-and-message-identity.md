---
id: ENH-3663
type: ENH
title: Capture versioned Gemini usage and message identity
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels: [observability, multi-host, producer-evidence]
relates_to: [ENH-3648, ENH-3534, ENH-3544]
---

# ENH-3663: Capture versioned Gemini usage and message identity

## Evidence gap

ENH-3648 found a historical real Gemini `tokens` pair with repeated message
`id` and changed `toolCallCount`, but the producing CLI version is unknown.
The installed Gemini 0.46.0 live probe lacked Vertex configuration. The
historical pair cannot certify current-version metric availability or the
identity of independent usage observations.

## Required proof

With working Vertex/model configuration, capture sanitized live and on-disk
0.46.0-or-newer records with tool use and resume. Verify whether repeated
message IDs rewrite one usage record or represent distinct requests; record
cache inclusivity/write semantics, omissions, reasoning/output inclusion,
grain and resets. Add versioned fixtures and findings to
`scripts/tests/fixtures/gemini/README.md`; update the typed map only for
proved entries and hand the contract to ENH-3534. Keep Gemini incomplete in
EPIC-3562 until ingestion, trigger and reader are verified.
