---
id: ENH-3660
type: ENH
title: Prove OpenCode cache and reasoning usage contract
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
- ENH-3671
---

# ENH-3660: Prove OpenCode cache and reasoning usage contract

## Evidence gap

ENH-3648 captured OpenCode 1.1.53 live `step_finish` and matching stored
`step-finish` parts, including a resume. The observed cache read/write fields
are all zero. `tokens.input` inclusivity, `tokens.reasoning` inclusion in
`tokens.output`, omitted-field semantics, and part identity across retries or
compaction remain unknown. The typed map marks observed output/cache fields
available while normalized disjoint input stays unknown.

## Required proof

Capture a sanitized, versioned cache-hit and cache-write-capable run with
matching live and stored parts, a tool call, resume, and any retry/compaction
behavior that occurs. Establish whether input includes cache reads/writes,
whether reasoning is included in output, what absent fields mean, and whether
`(sessionID, part.id)` is stable and unique across live/stored/replay. Update
`scripts/tests/fixtures/opencode/README.md` and the six-host telemetry map
only for proved metric/channel semantics. Hand the contract to ENH-3671;
ENH-3534 owns only shared replay/refresh. Keep the epic's OpenCode ledger
incomplete until stored ingestion, trigger and reader are verified.

## Acceptance Criteria

- [ ] Save a sanitized, versioned native capture with a tool call, resume, and matching live/stored parts; document which cache-hit/write and retry/compaction cases were actually observed.
- [ ] Record a verdict for each input, output, cache-read, cache-creation, and reasoning metric on each relevant channel: `supported`, `unsupported` with affirmative producer evidence, or `unknown` with the missing proof. State inclusivity, omitted-field behavior, grain/reset rules, and the namespace and stability of `(sessionID, part.id)`.
- [ ] Give ENH-3671 a replay-ready source fixture and dedup contract. The delivery issue proves parser → stored observation → trigger → reader; this evidence issue does not count as ingestion completion.
- [ ] If a nonzero cache or identity case cannot be exercised, record the access/model blocker and leave the affected semantics `unknown`. Keep this issue open or mark it `blocked`; do not infer `unsupported` from zero-only samples.
