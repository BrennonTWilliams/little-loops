---
id: 3398
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

## Motivation

The local agent-quality report already turns `history.db` into a longitudinal metric series, but a series is only actionable if something reads it. Silent quality regression — agents that got quietly worse after a model, host, or toolkit change, with nobody noticing for weeks — is the failure mode the series exists to catch, and detecting it by eye does not scale past one project.

Attribution is what makes an alert actionable. A detected drop with no candidate cause is noise: the operator cannot tell whether to roll back a model, pin a host, or investigate their own harness. Naming the change boundary the shift coincides with turns a plotted line into a decision.

## Design notes

Detection must be statistical over recorded values only — no LLM in the detection path. The evidence chain this feeds is meant to be checkable by someone who does not trust the agent, and an LLM grading its own quality series is exactly the bias the deterministic verification-evidence work already rejects.

Baseline windows and change-point detection over the existing metric series are the mechanism; the attribution join is against the model/host/version stamps carried on runs.

## Dependencies

Depends on the local agent-quality report over `history.db` for metric definitions and windowing.

Requires that runs carry model/host/version stamps. If `history.db` does not already record them, adding that capture is in scope for this issue.

## Acceptance Criteria

- Detection is deterministic and LLM-free — statistical over recorded values only.
- A fixture corpus with an injected quality drop is detected; a corpus with no drop produces no alert (false-positive check is part of the test, not an afterthought).
- Each detection names the candidate change (model/host/version boundary) it coincides with, or explicitly reports "no attributable change".
- Sensitivity is configurable, with a documented default and its false-positive tradeoff.
