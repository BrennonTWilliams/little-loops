---
id: ENH-737
type: ENH
priority: P5
status: completed
discovered_date: 2026-03-13
discovered_by: manual
confidence_score: 100
outcome_confidence: 100
---

# ENH-737: Simplify `fix-quality` state in `fix-quality-and-tests` loop

## Summary

The `fix-quality` state in `loops/fix-quality-and-tests.yaml` contained a redundant two-step skill sequence: it called `/ll:check-code all` to inspect errors, then immediately called `/ll:check-code fix` to auto-fix lint/format — but `check-code all` already includes the auto-fix behavior. The duplicate `fix` step was removed, reducing the action to a single call with manual type-error follow-up.

## Problem

The `fix-quality` action read:

```yaml
action: |
  Run `/ll:check-code all` to see current lint, format, and type errors.

  Step 1 — Auto-fix lint and format:
  Run `/ll:check-code fix` to auto-fix lint and format violations.

  Step 2 — Fix remaining type errors manually:
  If type errors remain, investigate each one ...
```

`/ll:check-code all` (confirmed in `commands/check-code.md` line 45) already auto-fixes lint and format violations. The explicit `check-code fix` step in Step 1 duplicated that behavior, causing Claude to run the same auto-fix twice per iteration.

## Solution

Collapsed the two-step sequence into a single call:

```yaml
action: |
  Run `/ll:check-code all` to check and auto-fix lint and format violations.

  If type errors remain after the above, investigate each one: read the error
  and the affected file, apply a targeted fix. Do NOT suppress with
  `# type: ignore` unless genuinely unavoidable and documented why.
```

## Investigation Notes

The session also reviewed whether natural language wrappers in `action_type: prompt` states should be replaced with bare skill calls (e.g. `/ll:check-code lint,format,types`). Investigation of all 18 loop YAML files confirmed:

- Natural language wrappers are the established convention — no bare calls exist anywhere.
- They are correct: the `llm_structured` evaluator reads Claude's stdout, and "report results" phrasing guides Claude to surface structured output. Bare calls leave this implicit.
- Multi-step states like `fix-quality` and `fix-tests` embed behavioral guardrails that cannot be expressed as a single skill invocation.

`check-quality` and `fix-tests` states were confirmed correct as-is and left unchanged.

## Files Changed

- `loops/fix-quality-and-tests.yaml` — `fix-quality` state `action` field (lines 25–34 → 25–30)
