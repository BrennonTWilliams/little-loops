# Wire-Issue: Graph-Accelerated Discovery (Phase 3.6)

Loaded by `/ll:wire-issue` Phase 3.6. Added by ENH-2578 (EPIC-2575).

**Read [`docs/guides/GRAPH_DISCOVERY_GUIDE.md`](../../docs/guides/GRAPH_DISCOVERY_GUIDE.md) first** —
it is the canonical `ll-code` contract, the three safety rules, and the staleness
policy shared with `/ll:refine-issue` Step 3.05. This file adds only what is
specific to wire-issue.

## Overview

Seed Phase 4 candidates (callers, importers, impacted files) from the `ll-code`
query surface **before** the exhaustive agent tracing, then spend the remaining
budget *confirming* those candidates with one targeted Grep each — instead of
discovering them from scratch. The written output (Integration Map) is
format-identical to today; only *how* candidates are found changes. `--auto` and
`--dry-run` behavior are unchanged.

`ll-code` seeds are **hints, not verdicts.** Every candidate is confirmed at its
`path:line` before it enters the Integration Map, and negative results are never
trusted alone.

## Wire-issue specifics

- **Targets** come from the issue's Implementation Steps / Files to Modify.
- **Confirm-before-use** is *confirm-before-map* here: a hit enters the Integration
  Map only after its `path:line` Grep confirms it, and it is then recorded like any
  Agent 1 finding.
- **Seed slots**: feed confirmed candidates into Phase 4 Agent 1's
  "Already-known callers:" and "Key symbols to trace:" slots so the agents confirm
  and extend rather than rediscover.
- **Staleness**: widen confirmation to the full exploratory flow for anything
  wiring-critical.
