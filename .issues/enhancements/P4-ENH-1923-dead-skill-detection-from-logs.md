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

- ENH-1921 (`ll-logs stats`): invocation-count source.
- `find-dead-code` (`skills/find-dead-code/`): consume the never-invoked list.

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

Adds a usage dimension to dead-code review; surfaces discoverability gaps.

## Related Key Documentation

- `docs/reference/API.md` (ll-logs); `skills/find-dead-code/`

## Labels

captured, ll-logs, find-dead-code

## Status

open

## Session Log
- `/ll:capture-issue` - 2026-06-04T02:27:34Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a8bc5f2d-5c58-451d-9bc9-c722459e42b9.jsonl`
