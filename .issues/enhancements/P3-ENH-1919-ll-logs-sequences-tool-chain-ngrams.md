---
id: ENH-1919
title: "ll-logs sequences: tool-chain n-gram extraction primitive"
type: ENH
priority: P3
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918, FEAT-1309]
labels: [captured, ll-logs, loop-suggester]
---

# ENH-1919: ll-logs sequences — tool-chain n-gram extraction primitive

## Summary

Add an `ll-logs sequences` subcommand that mines **tool-level** n-grams (ordered
chains of ll skill/command/tool invocations) from the extracted log corpus, with
occurrence counts and transition frequencies. This is the reusable extraction
primitive that `loop-suggester` and FEAT-1309's passive-scan UX can consume.

## Current Behavior

`loop-suggester` and `analyze-workflows` source candidate workflows from
`ll-messages` (user *text*). The actual sequence of skill/command invocations —
e.g. `refine-issue → wire-issue → ready-issue` — is visible in the JSONL tool-use
records but is never extracted as structured sequence data.

## Expected Behavior

`ll-logs sequences [--project DIR|--all] [--min-len N] [--min-count M] [--window-days D] [--json]`
walks the extracted `logs/**/*.jsonl` (or raw `~/.claude/projects/`) and emits
ranked n-grams of ll invocations: the chain, occurrence count, and per-edge
transition frequency. Default `--min-len 2`, surfacing the chains most worth
turning into loops.

## Motivation

n-grams over *real tool chains* give `loop-suggester` ground truth about what
users actually do, not what they say. It also factors the n-gram logic out of
FEAT-1309 (which currently inlines mining into a `--passive-scan` flag) into a
single reusable primitive.

## Proposed Solution

Add `sequences` to `cli/logs.py` (`main_logs()`), reusing the project
enumeration that `extract` already shares with `discover`. Parse tool-use records
for ll skill/command/`ll-*` Bash invocations into an ordered per-session event
stream, then count n-grams within `--window-days`. Emit text + `--json`.

## Integration Map

- `loop-suggester` (`skills/loop-suggester/`): consume `--json` output as a
  history-independent sequence source alongside `ll-messages`.
- FEAT-1309: re-point `--passive-scan` at this primitive instead of inlining.

## Implementation Steps

1. Define the per-session ll-invocation event-stream extractor (shared helper).
2. Add `sequences` subcommand + arg parsing in `cli/logs.py`.
3. n-gram counting with `--min-len`/`--min-count`/`--window-days`.
4. Text + JSON output; wire `cli_event_context` tracking like other subcommands.
5. Tests in `scripts/tests/` over a fixture corpus.

## API/Interface

`ll-logs sequences` — new subcommand; JSON schema: `[{chain: [str], count: int, edges: [{from, to, freq}]}]`.

## Impact

Enables data-driven loop suggestion; de-duplicates mining logic with FEAT-1309.

## Related Key Documentation

- `docs/reference/API.md#little_loopscli` (ll-logs)

## Labels

captured, ll-logs, loop-suggester

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
