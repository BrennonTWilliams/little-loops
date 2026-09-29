---
id: ENH-3665
type: ENH
title: Prove Kimi usage component and replay identity
priority: P3
status: open
parent: EPIC-3562
epic: EPIC-3562
discovered_date: '2026-09-29'
labels: [observability, multi-host, producer-evidence]
relates_to: [ENH-3648, ENH-3534, ENH-3544]
---

# ENH-3665: Prove Kimi usage component and replay identity

## Evidence gap

ENH-3648 captured Kimi Code 0.30.0 stored `usage.record` fields, a nonzero
cache read, a resume, and matching `context.append_loop_event` copies. The
live stream sample had no usage. `inputOther` normalization,
`inputCacheCreation` behavior beyond zero, reasoning/output inclusion,
`usageScope: turn` grain, and a durable request key for dedup/replay remain
unknown. One no-usage live sample does not prove that channel unsupported.

## Required proof

Capture or establish producer-contract evidence for `inputOther` versus cached
input, nonzero cache creation if available, omission behavior, output versus
reasoning, and the mapping of `usage.record` to `llm.request.turnStep` across
resume, retries and compaction. Determine whether a stable native ID exists;
otherwise define a replay-safe source-position key. Verify whether additional
live event modes can expose usage. Update
`scripts/tests/fixtures/kimi-code/README.md` and the typed map for proved
entries, then hand the stored-record dedup rule to ENH-3534. Keep Kimi Code
incomplete in EPIC-3562 until ingestion, trigger and reader are verified.
