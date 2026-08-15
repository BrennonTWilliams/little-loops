---
id: 3183
title: Local agent-quality report over history.db
type: FEAT
priority: P0
status: open
discovered_date: '2026-08-15'
labels:
- path-a
- observability
- history-db
---

## Summary

Ship a local, screenshot-worthy agent-quality report built from `.ll/history.db`: fix-rate, correction rate, retry inflation, and cost per issue, each **trended over time** rather than reported as a point-in-time total.

## Motivation

`history.db` already stores tool calls, tokens, corrections, and lifecycle transitions per project. Nothing turns that into an answer to the only question a user actually asks: *are my agents any good, and is that changing?*

A point-in-time total cannot answer it. "You spent 40k tokens on this issue" is trivia; "your fix-rate has dropped 30% since the last model update" is actionable, and it is the shape of analysis that people currently hand-build one session-corpus at a time because no tool produces it.

## Boundary (non-duplication)

**FEAT-2315** (`ll-logs summary`, under EPIC-2369) produces a per-project *work digest* — what happened. This issue produces a *quality trend* — whether it is getting worse. The two must share metric definitions where they overlap and must not ship two competing report commands; prefer extending the existing surface over adding a parallel one.

## Acceptance Criteria

- One command emits the report from any project's `history.db` with no network access and no LLM call.
- At least four metrics, each with a time series and an explicit window definition.
- Empty or sparse databases degrade to a clear "insufficient data" state, not a crash and not a misleading zero.
- Metric definitions are documented in one place and reusable by downstream regression detection.
- The output is legible to someone who did not run the loops it describes.
