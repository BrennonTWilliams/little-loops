---
id: ENH-2889
title: Rework docs-sync.yaml to respect action-severity model
type: ENH
parent: ENH-2875
priority: P2
status: open
discovered_date: 2026-07-28
labels:
- verification
- ll-doctor
depends_on:
- ENH-2886
---

# ENH-2889: Rework docs-sync.yaml to respect action-severity model

## Parent Issue
Decomposed from ENH-2875: Give drift findings an action-severity and a throttle, and forbid opportunistic repair

## Summary

`scripts/little_loops/loops/docs-sync.yaml` is the codebase's current instance of "opportunistic repair" — the pattern this issue's parent forbids. Its `route_results` state regex-matches the raw combined text output of `ll-verify-docs`/`ll-check-links`, and its `fix_docs` state dispatches a free-form LLM prompt that repairs everything unconditionally, with zero severity discrimination. Once ENH-2886 lands the `auto`/`mention`/`route` action-severity model, this loop must be reworked to restrict itself to `auto`-severity findings only.

## Current Behavior

`scripts/little_loops/loops/docs-sync.yaml`'s `route_results` state regex-matches the *raw combined text output* of `ll-verify-docs`/`ll-check-links` for `"FAIL|ERROR|BROKEN|MISMATCH"` (`output_contains`), and its `fix_docs` state then dispatches a free-form LLM prompt ("Fix all documentation discrepancies... Update counts... Fix broken internal links...") with zero severity discrimination — repairing everything unconditionally, including what is now `mention`/`route`-severity findings (per ENH-2886).

`scripts/little_loops/loops/lib/cli.yaml` — `ll_check_links` fragment (line 70) is the shared action `docs-sync.yaml` invokes for `ll-check-links`; also has a raw-output string dependency that action-severity output changes may break.

## Expected Behavior

`docs-sync.yaml` is reworked to restrict itself to `auto`-severity findings (or gated through `--fix`, per ENH-2886) — it must never repair a `mention`/`route`-severity finding, satisfying the parent issue's hard rule: "Never repair drift as a side effect of a design task. A staleness finding is reported, not acted on, unless the user asks."

## Scope Boundaries

In scope: `docs-sync.yaml`'s `route_results`/`fix_docs` states and `loops/lib/cli.yaml`'s `ll_check_links` fragment's output-parsing dependency on action-severity. Out of scope: the action-severity field itself (ENH-2886, a prerequisite), `ll-doctor --full` aggregation (ENH-2887), the session-start hook (ENH-2888).

## Acceptance Criteria

- `docs-sync.yaml`'s repair path applies only to `auto`-severity findings; `mention`/`route`-severity findings are reported, not repaired, by this loop.
- `loops/lib/cli.yaml`'s `ll_check_links` fragment is updated for any output-shape change from ENH-2886.

## Tests

- `ll-loop validate loops/docs-sync` passes after the rework.

## Documentation

- `scripts/little_loops/loops/README.md` — update the loop catalog listing, which describes `docs-sync.yaml`'s current unconditional-fix behavior.

## Session Log
- `/ll:issue-size-review` - 2026-07-28T08:00:00 - `f26799df-de87-40c6-90ea-225f55ba976e.jsonl`

## Status

open
