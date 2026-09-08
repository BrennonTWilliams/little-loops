---
id: FEAT-3398
title: Quality-regression detection with model/host/version attribution
type: FEAT
priority: P0
status: open
discovered_date: '2026-09-07'
labels:
- path-a
- observability
- regression-detection
---

## Summary

Detect quality regressions in the agent-quality metric series produced by the local quality report over `history.db` — baseline windows plus change-point detection — and attribute each detected shift to the model, host, and little-loops version in effect, so the report can say *"fix-rate dropped 30% since the model update"* rather than just plotting a line.

## Current Behavior

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) already turns `history.db` into a `QualityAnalysis` — a time series of `QualityWindow`s (fix rate, correction rate, cost per issue, tokens per issue, retry inflation) bucketed by `(period, orchestrator)`. Nothing reads that series for a shift: an operator has to eyeball the report output by hand to notice a regression, and nothing on a `QualityWindow` names the model, host, or little-loops version in effect for that window, so even a spotted drop has no candidate cause to attribute it to.

## Expected Behavior

A new detection pass over `QualityAnalysis.windows` flags statistically significant drops against a rolling baseline and, for each flagged window, names the model/host/version boundary its start coincides with (or reports "no attributable change" when none exists). Detection is deterministic and LLM-free. A fixture corpus with an injected drop is flagged; a fixture corpus with none is not.

## Use Case

**Who**: A maintainer running `ll-*` quality reports across their own agent-heavy projects.

**Context**: After bumping the model or host version, or after a little-loops upgrade, the maintainer wants to know within one report run whether agent quality moved — not weeks later after noticing a vague sense that "things feel worse".

**Goal**: See "fix-rate dropped 30% since the 2026-09-01 model update" surfaced automatically in the report, with a named cause to investigate (roll back the model, pin the host, or look at the harness itself).

**Outcome**: The report attaches a regression alert to the affected window, with the coinciding change boundary named, instead of a silent line the maintainer must interpret unaided.

## Motivation

The local agent-quality report already turns `history.db` into a longitudinal metric series, but a series is only actionable if something reads it. Silent quality regression — agents that got quietly worse after a model, host, or toolkit change, with nobody noticing for weeks — is the failure mode the series exists to catch, and detecting it by eye does not scale past one project.

Attribution is what makes an alert actionable. A detected drop with no candidate cause is noise: the operator cannot tell whether to roll back a model, pin a host, or investigate their own harness. Naming the change boundary the shift coincides with turns a plotted line into a decision.

## Design notes

Detection must be statistical over recorded values only — no LLM in the detection path. The evidence chain this feeds is meant to be checkable by someone who does not trust the agent, and an LLM grading its own quality series is exactly the bias the deterministic verification-evidence work already rejects.

Baseline windows and change-point detection over the existing metric series are the mechanism; the attribution join is against the model/host/version stamps carried on runs.

## Dependencies

Depends on the local agent-quality report over `history.db` for metric definitions and windowing.

Requires that runs carry model/host/version stamps. If `history.db` does not already record them, adding that capture is in scope for this issue.

## Program Design

### Types

- `RunAttribution`: `model: str`, `host: str`, `ll_version: str`, `effective_from: str` (period key)
- `RegressionEvent`: `metric: str`, `window: QualityWindow`, `baseline_period: str`, `magnitude: float`, `attribution: RunAttribution | None`

### Signatures

- `detect_quality_regressions(analysis: QualityAnalysis, *, sensitivity: float = DEFAULT_SENSITIVITY) -> list[RegressionEvent]`
- `attribute_change(window: QualityWindow, attributions: list[RunAttribution]) -> RunAttribution | None`

### Call Path

`analyze_agent_quality()` (`little_loops/issue_history/agent_quality.py`) -> `QualityAnalysis` -> `detect_quality_regressions()` -> `format_agent_quality_markdown()` (extended to render `RegressionEvent`s alongside the existing window table)

## Impact

- **Priority**: P0 - Silent quality regressions are the failure mode the whole metric series exists to catch; without detection the series is observed by nobody.
- **Effort**: Large - requires both a new statistical detection module and, per Dependencies, adding model/host/version stamp capture to `history.db` if not already present.
- **Risk**: Low - read-only analysis over existing `history.db` data; no changes to the write path or existing report output beyond additive alerts.
- **Breaking Change**: No

## Acceptance Criteria

- Detection is deterministic and LLM-free — statistical over recorded values only.
- A fixture corpus with an injected quality drop is detected; a corpus with no drop produces no alert (false-positive check is part of the test, not an afterthought).
- Each detection names the candidate change (model/host/version boundary) it coincides with, or explicitly reports "no attributable change".
- Sensitivity is configurable, with a documented default and its false-positive tradeoff.

## Status

**Open** | Created: 2026-09-07 | Priority: P0


## Session Log
- `/ll:format-issue` - 2026-09-08T00:08:41 - `fd8050c6-8bbf-4735-ba8f-b83f5f588867.jsonl`
