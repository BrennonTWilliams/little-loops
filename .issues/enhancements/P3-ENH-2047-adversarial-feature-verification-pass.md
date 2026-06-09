---
id: ENH-2047
title: Adversarial feature-verification pass (try-to-break, distinct from confirmatory verify)
type: ENH
priority: P3
status: open
captured_at: "2026-06-09T00:00:00Z"
discovered_date: "2026-06-09"
discovered_by: capture-issue
relates_to: [ENH-216, FEAT-808]
labels: [verification, testing, adversarial, harness, eval]
---

# ENH-2047: Adversarial feature-verification pass

## Summary

Add a verification mode that deliberately tries to *break* an implemented feature
— boundary values, malformed/hostile inputs, failure modes — rather than
confirming it works. This is squid's adversarial-QA framing: failing to attempt a
few genuine break-paths is itself a FAIL, not a pass.

Today every feature-level verification path in little-loops is **confirmatory** or
**user-perspective**; the only adversarial framing that exists is for issue
*prioritization*, not for stress-testing a built feature.

## Current Behavior

| Path | Framing | Adversarial? |
|---|---|---|
| `run-tests` | Executes configured `test_cmd` | No — execution only |
| eval harness `execute` state (`create-eval-from-issues`) | "Use it as a real user would" | No — quality-of-experience |
| `verify-issue-loop` | "Does criterion N *hold*?" per acceptance criterion | No — confirmatory |
| `verify-issues` | Issue accuracy / regression vs. code | No — consistency check |
| `go-no-go` | Adversarial debate on *whether to build* | Adversarial, but prioritization |

Existing fuzz/adversarial issues are narrower: ENH-216 (fuzz critical *parsers*)
and the parallel-state fuzz suite (FEAT-1200/1214/1219/1222) target specific
modules, not "attack this implemented feature/criterion." Nothing generates
boundary/hostile/failure-mode probes against a feature and treats "no break-paths
attempted" as failure.

## Expected Behavior

A new adversarial verification pass that, for a given feature or acceptance
criterion, generates and exercises deliberate break-paths:

- Boundary / extreme values (empty, max, off-by-one, unicode, very large).
- Malformed / hostile inputs (wrong types, injection-shaped strings, partial
  state, concurrent/duplicate invocation).
- Known failure modes (missing config, absent files, interrupted runs).
- **Verdict rule (squid-derived): attempting fewer than N genuine break-paths is
  itself a FAIL**, even if everything attempted passed.

### Hard constraint

This MUST be a *distinct* pass — a sibling to `verify-issue-loop` or a new mode —
and MUST NOT alter the eval harness `execute` state. The `execute` state's
"as a real user would" framing is load-bearing and protected by a standing
correction (eval `execute` = exercise as a user, not break-it, not implement).
Polluting it with adversarial framing would regress that design.

Placement options for refinement to decide:
- A sibling skill that emits an adversarial verification loop YAML (mirrors
  `verify-issue-loop`'s structure: one state per probe class, `llm_structured`
  evaluator, fail-fast), OR
- An `--adversarial` mode on `verify-issue-loop` that adds a break-path state
  per criterion alongside the existing "does it hold" state.

Recommendation: lean toward a sibling skill so the confirmatory and adversarial
loops stay independently runnable and composable.

## Acceptance Criteria

- [ ] A verification path exists that, given a feature/issue, produces deliberate
      break-path probes across at least boundary, malformed/hostile, and
      failure-mode categories.
- [ ] The pass FAILs when fewer than a configured minimum number of distinct
      break-paths are genuinely attempted (not just when a probe finds a bug).
- [ ] The eval harness `execute` state is unchanged (verified by test/diff).
- [ ] Output integrates with existing FSM verification tooling (runnable via
      `ll-loop`, fail-fast routing consistent with `verify-issue-loop`).
- [ ] Tests cover: a feature that survives all probes (pass), a feature with a
      reproducible break (fail-with-finding), and the "too few break-paths
      attempted" self-FAIL.

## Out of Scope

- Replacing or modifying `run-tests` (stays execution-only).
- Parser-level fuzzing already tracked by ENH-216 and the parallel fuzz suite.
- Adversarial *prioritization* (owned by `go-no-go` / FEAT-808).

## Labels

verification, testing, adversarial, harness, eval

## Status

open

## Session Log
- `/ll:verify-issues` - 2026-06-09T18:30:00 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`

- Captured - 2026-06-09 - from squid-plugin evaluation; adversarial-QA framing
  applied to feature verification, kept distinct from eval `execute`.
