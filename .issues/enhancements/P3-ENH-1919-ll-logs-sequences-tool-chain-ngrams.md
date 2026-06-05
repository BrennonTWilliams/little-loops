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

`ll-logs sequences [--project DIR|--all] [--min-len N] [--min-count M] [--top N] [--window-days D] [--json]`
walks the extracted `logs/**/*.jsonl` (or raw `~/.claude/projects/`) and emits
ranked n-grams of ll invocations: the chain, occurrence count, and per-edge
transition frequency. Default `--min-len 2`. `--top N` limits output to the
top N chains by frequency.

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

### Files to Modify
- `scripts/little_loops/cli/logs.py` — add `sequences` subcommand to `main_logs()`, reusing project enumeration from `extract`/`discover`

### Dependent Files (Callers/Importers)
- `skills/loop-suggester/` — consume `sequences --json` output as history-independent sequence source alongside `ll-messages`
- FEAT-1309 implementation — re-point `--passive-scan` mining logic at this primitive instead of inlining

### Similar Patterns
- `discover` and `extract` subcommands in `cli/logs.py` — reuse their project enumeration and JSONL-walking patterns
- `ll-messages` CLI — parallel extraction primitive; follow same `--json` output convention

### Tests
- `scripts/tests/` — add fixture corpus tests for `sequences` subcommand; cover n-gram counting, `--min-len`/`--min-count`/`--window-days` filtering, and JSON schema

### Documentation
- `docs/reference/API.md#little_loopscli` — document `sequences` subcommand signature and JSON schema

### Configuration
- N/A

## Implementation Steps

1. Define the per-session ll-invocation event-stream extractor (shared helper).
2. Add `sequences` subcommand + arg parsing in `cli/logs.py`.
3. n-gram counting with `--min-len`/`--min-count`/`--window-days`.
4. Text + JSON output; wire `cli_event_context` tracking like other subcommands.
5. Tests in `scripts/tests/` over a fixture corpus.

## API/Interface

`ll-logs sequences` — new subcommand; JSON schema: `[{chain: [str], count: int, edges: [{from, to, freq}]}]`. Supports `--top N` to limit output to top N chains by frequency.

## Scope Boundaries

- **In scope**: extracting ll skill/command/`ll-*` Bash invocations from JSONL logs into ordered per-session event streams; n-gram counting with CLI filters; text and `--json` output
- **Out of scope**: consuming or integrating the output into `loop-suggester` or FEAT-1309 (that's their respective issues); visualization or analysis of n-grams beyond ranked list output; real-time log monitoring; non-ll tool chains

## Impact

- **Priority**: P3 — enabling primitive for loop-suggester and FEAT-1309; not urgent but reduces duplicated mining logic
- **Effort**: Small — new subcommand reusing existing `discover`/`extract` project enumeration; no new parsing infrastructure needed
- **Risk**: Low — additive subcommand; does not modify existing `ll-logs` subcommands or shared state
- **Breaking Change**: No

## Related Key Documentation

- `docs/reference/API.md#little_loopscli` (ll-logs)

## Labels

captured, ll-logs, loop-suggester

## Status

**Open** | Created: 2026-06-04 | Priority: P3


## Verification Notes

**Verdict**: VALID — 2026-06-05T21:00:23

- Issue describes a planned feature/enhancement that has not yet been implemented
- Referenced files and directories verified to exist (where applicable)
- No claims about current code behavior are contradicted by the codebase
- Dependency references are valid (no broken refs, missing backlinks, or cycles)

## Session Log
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T05:19:16 - `cd123288-5c07-482f-b424-1eebfea29b6e.jsonl`
- `/ll:format-issue` - 2026-06-04T03:07:47 - `f957d413-8388-4582-b04a-6c037cc6e22e.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
