---
id: ENH-2082
title: Add shallow-iteration failure mode detector to loop audit
type: ENH
priority: P3
status: open
captured_at: "2026-06-10T18:12:09Z"
discovered_date: "2026-06-10"
discovered_by: capture-issue
parent: EPIC-2087
---

# ENH-2082: Add shallow-iteration failure mode detector to loop audit

## Motivation

A common failure pattern in loop runs is high tool-call counts without accumulating reusable structure — the loop iterates shallowly without building stable primitives, burning token budget without progress. This is a more specific diagnostic than the existing 'feature-stubbing' taxonomy and has a concrete detectable signal.

## Proposed Solution

Add a heuristic to `ll:audit-loop-run` that flags runs where the tool-call count exceeds a threshold (e.g., >30) but no new helper files were created or modified outside the primary artifact path. Report this as a `shallow-iteration` warning in the audit output. Cross-reference with `diff_stall` evaluator verdicts as a corroborating signal. Document the pattern in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` under the failure mode taxonomy alongside feature-stubbing.

## Implementation Steps

1. Add `shallow-iteration` detection heuristic to `ll:audit-loop-run`
2. Implement threshold check: tool-call count > 30 with no helper file creates/modifies outside primary artifact path
3. Cross-reference with `diff_stall` evaluator verdicts to emit corroborated warnings
4. Report `shallow-iteration` warning in audit output with remediation suggestion
5. Document pattern in `docs/guides/HARNESS_OPTIMIZATION_GUIDE.md` under failure mode taxonomy

## Acceptance Criteria

- [ ] `ll:audit-loop-run` emits `shallow-iteration` warning when tool-call count exceeds threshold without auxiliary file changes
- [ ] Warning cross-references `diff_stall` verdict when present
- [ ] `HARNESS_OPTIMIZATION_GUIDE.md` documents `shallow-iteration` alongside `feature-stubbing`
- [ ] Threshold is configurable or clearly documented

## Status

open
