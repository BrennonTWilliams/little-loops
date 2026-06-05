---
id: ENH-1923
title: "Dead-skill detection: never-invoked skills from log corpus"
type: ENH
priority: P4
status: open
captured_at: "2026-06-04T02:27:34Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1918
relates_to: [EPIC-1918, ENH-1921]
labels: [captured, ll-logs, find-dead-code]
---

# ENH-1923: Dead-skill detection — never-invoked skills from log corpus

## Summary

Cross-reference the ll skill/command catalog against the log corpus to flag
skills that are **never invoked** in any real session — discoverability or value
candidates for `/ll:find-dead-code`.

## Current Behavior

`find-dead-code` analyzes code references but has no usage signal: a skill can be
fully wired and referenced yet never actually invoked by any user. Such skills
are invisible to current dead-code analysis.

## Expected Behavior

A check (e.g. `ll-logs stats --never-invoked`, or a `find-dead-code` input) lists
catalog skills/commands with zero invocations across the corpus within
`--window-days`, separating "never invoked" from "rarely invoked".

## Motivation

A skill nobody triggers is either undiscoverable or low-value. Usage-grounded
dead-skill detection complements reference-based dead-code analysis.

## Proposed Solution

Enumerate the catalog (`skills/*/SKILL.md`, `commands/*.md`); subtract the set of
skills observed in `ll-logs stats` (ENH-1921). Report the difference, tiered by
invocation count.

## Integration Map

### Files to Modify
- `scripts/little_loops/logs.py` (or `ll_logs` subcommand module) — add `--never-invoked` / `stats` output with catalog cross-reference

### Dependent Files (Callers/Importers)
- ENH-1921 (`ll-logs stats`) — invocation-count source; this feature consumes its output
- `skills/find-dead-code/SKILL.md` — consume the never-invoked list as an additional input signal

### Similar Patterns
- `ll-find-dead-code` skill — existing reference-based dead-code detection to stay consistent with output format

### Tests
- `scripts/tests/` — new test with catalog fixture + corpus fixture; assert correct never-invoked/rarely-invoked split

### Documentation
- `docs/reference/API.md` — document new `ll-logs` subcommand/flag

### Configuration
- N/A

## Implementation Steps

1. Build the catalog set from skills/ and commands/.
2. Build the observed-invocation set from ENH-1921 output.
3. Report difference, tiered (never vs. rarely); `--json`.
4. Tests with a catalog + corpus fixture.

## Success Metrics

- Output correctly distinguishes a known never-invoked skill from a used one in fixtures.

## Scope Boundaries

- Out: deciding to delete a skill — this only flags candidates for human/find-dead-code review.

## Impact

- **Priority**: P4 — useful complement to existing dead-code analysis but no active user pain; low urgency
- **Effort**: Small — enumerate catalog files + diff against stats output; no new infrastructure
- **Risk**: Low — additive read-only feature; no changes to existing skill or log behavior
- **Breaking Change**: No

Adds a usage dimension to dead-code review; surfaces discoverability gaps.

## Related Key Documentation

- `docs/reference/API.md` (ll-logs); `skills/find-dead-code/`

## Labels

captured, ll-logs, find-dead-code

## Status

open

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map has wrong path for the logs module: `scripts/little_loops/logs.py` → should be `scripts/little_loops/cli/logs.py`. Also, the skill directory referenced is `skills/find-dead-code/` but actual dir is `skills/ll-find-dead-code/`.

- `/ll:verify-issues` - 2026-06-05 - Feature not implemented. No `--never-invoked` flag in cli/logs.py. Issue body references incorrect paths: `scripts/little_loops/logs.py` → should be `scripts/little_loops/cli/logs.py`; `skills/find-dead-code/` → should be `skills/ll-find-dead-code/`. Correct these paths in the Implementation Plan before starting.

## Session Log
- `/ll:verify-issues` - 2026-06-05T22:34:32 - `1a4d9590-60c8-47b0-9997-b0f543664183.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:22:06 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:format-issue` - 2026-06-04T03:10:33 - `6828653f-c5aa-47bf-a167-82e4553412d0.jsonl`
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
