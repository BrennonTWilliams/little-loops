---
id: FEAT-3681
type: FEAT
title: Extract reusable utility scorer from ll-loop next-loop
priority: P3
status: open
blocks:
- FEAT-3561
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T01:30:51Z'
---

# FEAT-3681: Extract reusable utility scorer from ll-loop next-loop

## Summary

Extract `ll-loop next-loop`'s deterministic scoring into a reusable `utility/` module and register a keyed `next` configuration surface. This is the behavior-preserving foundation for FEAT-3561's arena. It does not add `ll-next`, candidate generators, acceptance logging, or a history schema migration.

## Current Behavior

`ll-loop next-loop` calculates a weighted additive score from frequency, recency, and success rate with hardcoded weights `0.50`, `0.30`, and `0.20` in `cli/loop/next_loop.py`. The scorer and its response curves are not reusable by another action type.

## Expected Behavior

`ll-loop next-loop` emits byte-identical output for the same fixed project state and clock. Pure scoring functions expose a weighted sum and a separate weighted geometric aggregate with explicit gates for FEAT-3561. A `next` object in `ll-config.json` uses keyed weight/curve/gate objects so local overrides deep-merge one key without replacing siblings. The default next-loop weights reproduce today's constants exactly.

## Motivation

The arena needs auditable scoring, while existing loop recommendations must not shift merely because their implementation moved. Extracting and testing the scorer first gives the later multi-verb CLI a stable foundation.

## Proposed Solution

1. Move the next-loop response-curve and weighted-sum logic to `little_loops.utility` as pure, typed functions. Feed a fixed `as_of` time into recency rather than calling the clock within a golden test.
2. Expose a weighted geometric aggregate over **present, applicable non-gate axes**: normalize weights over those axes, floor an ordinary zero score at a documented positive epsilon so only explicit gates veto, and keep gate failures separate. A missing required gate fails closed; when no decision rule applies, decision-rule compliance is a positive pass, not missing data. Do not add an uncalibrated make-up term.
3. Add `next` keyed-object config parsing and JSON Schema validation. Pin the next-loop default weights to `0.50/0.30/0.20`. Invalid supplied config returns the next-loop CLI's config-error status without changing its successful output.

## Scope Boundaries

- **In scope:** pure utility module, next-loop adaptation, keyed config/schema, documentation and fixed-clock tests.
- **Out of scope:** `ll-next`, nine action generators, bucket pressure, `recommendation_events`, any `SCHEMA_VERSION` bump, acceptance matching, and backtesting (FEAT-3561).

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/next_loop.py`, new `scripts/little_loops/utility/` module, `scripts/little_loops/config/features.py`, `scripts/little_loops/config-schema.json`, and their focused tests.
- Config and CLI reference docs for the new `next` object. Existing `next-loop` behavior and CLI registry tests must remain green.

### Similar Patterns and Configuration

- Reuse `NextIssueConfig`'s validation approach, but do not copy its list-valued `sort_keys`: arrays replace on local-override merge, whereas keyed weight objects deep-merge.

## Program Design

### Signatures

- `weighted_sum(scores, weights) -> float` — retains next-loop's current output.
- `weighted_geometric(scores, weights, *, floor) -> float` — rejects invalid weights, excludes missing axes, and normalizes remaining weights. Gates are evaluated separately, so an ordinary score of zero cannot silently become a veto.
- The `next` schema uses objects keyed by axis/action name, with explicit bounds for weights and curves. The module is pure: no filesystem, database, clock, or network access.

### Call Path

Existing `cmd_next_loop` → `_score_loop` → new `utility.weighted_sum` → existing next-loop rendering. FEAT-3561 later calls `utility.weighted_geometric` after its explicit gate evaluation; neither utility function reads project state itself.

## Implementation Steps

1. Capture pre-extraction next-loop output over a fixed history fixture and fixed clock, then extract the pure scorer.
2. Add keyed config/schema with behavior-preserving defaults, and test local override merge behavior plus invalid config.
3. Add focused weighted-geometric, missing-axis, zero-score, and gate tests; update docs and run the local suite.

## Impact

- **Priority:** P3 — prerequisite for FEAT-3561 without changing current recommendations.
- **Effort:** Medium — scorer extraction, config/schema and tests.
- **Risk:** Medium — a default or time-source change could silently reorder existing output.
- **Breaking Change:** No.

## Acceptance Criteria

- [ ] A fixed-clock golden fixture proves `ll-loop next-loop` output byte-identical before and after extraction; default weights equal `0.50/0.30/0.20`.
- [ ] Both pure aggregators have tests for weights, missing axes, ordinary zero scores and explicit gates; no implicit geometric-zero veto or uncalibrated make-up term remains.
- [ ] `next` keyed objects validate through `config-schema.json`; one-key local overrides preserve sibling keys; invalid config has a deterministic CLI error.
- [ ] No `ll-next` entry point or history schema change is introduced; `python -m pytest scripts/tests/`, lint and type checks pass.

## Related

- FEAT-3561 (arena Phase 1; blocked by this issue). ENH-3678 must precede FEAT-3561's future history schema bump but is not a prerequisite for this pure extraction.

## Use Case

A user runs `ll-loop next-loop` after the extraction and gets the same recommendation and explanation. A later `ll-next` implementation imports the pure scorer without copying the loop-specific code.

## Related Key Documentation

- `docs/reference/CLI.md` (`ll-loop next-loop`) and `docs/reference/CONFIGURATION.md` (`next` config).

## Status

**Open** | Created: 2026-09-30 | Priority: P3
