---
id: 3463
title: Unit-test an eval's grading logic deterministically before it is allowed to
  grade a live-model run
type: ENH
priority: P3
status: open
discovered_date: '2026-09-13'
labels: []
blocked_by:
- '3462'
parent: EPIC-3475
epic: EPIC-3475
---

## Summary

`ll-harness` grading code decides pass/fail for every stochastic subject it evaluates, but nothing currently requires that the grading logic itself be tested. A scorer with an inverted comparison, an off-by-one threshold, or a regex that never matches will report confident verdicts on real runs, and because the subject is stochastic the wrong verdicts look like ordinary model variance rather than a bug in the harness.

Require that any grading or scoring function used by a live-model probe have deterministic unit tests over fixed synthetic inputs — zero API calls — covering at minimum a clear pass, a clear fail, and the boundary the threshold sits on. The tests exercise the grader as a pure function of (output, criteria) so they run in CI at no cost and fail loudly when scoring logic changes.

## Design

The pattern is proven in a cross-host ruleset project whose eval strategy separates three tiers — deterministic unit tests, a live-model behavior gate, and an agentic benchmark — and whose load-bearing property is that **the graders of the live-model tier are themselves unit-tested** ("RED/GREEN, no API key"): the deterministic tier verifies the live-eval tier's grading logic before that logic is trusted to grade a real model. That is the exact discipline to import: a grader is not allowed to grade until its own logic passes its own deterministic tests.

Distinct from the adjacent verdict work: n-run redundancy (ENH-3415, shipped) governs how many runs a verdict needs before it counts; score-splitting work governs what gets scored; information-isolation work governs flow between builder and validator roles. None of the three tests the grader's own code.

## Acceptance

A grader with a deliberately inverted comparison is caught by its unit tests before any live run is dispatched.


## Session Log
- `/ll:audit-issue-conflicts` - 2026-09-13T21:28:47 - `23df08cc-836b-4f77-a1e2-bfb5aedb0f55.jsonl`
