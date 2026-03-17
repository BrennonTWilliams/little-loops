---
id: ENH-793
type: ENH
priority: P3
title: "Fix stall detection and live LLM judge in rl-coding-agent"
status: completed
completed_date: 2026-03-17
---

## Summary

Fixed two known limitations in `loops/rl-coding-agent.yaml`:

1. **Stall detection was broken** — the `score` state's convergence evaluator had no `previous:` field, so `previous` was always `None` and the "stall" route never fired.
2. **LLM-as-judge was a constant** — the reward formula hardcoded `+ 0.2` instead of calling Claude to score code quality.

## Changes Made

**File**: `loops/rl-coding-agent.yaml`

### Fix 1: Stall Detection

Added a `persist_reward` state between `improve` and `act`. It captures only the clean numeric reward. The next iteration's `score` evaluator reads this via `previous: "${captured.prev_reward.output}"`.

FSM flow after fix:
```
act → refine → observe → score ──target──→ done
                              └──progress─→ improve → persist_reward → act
                              └──stall────→ act  (skips persist_reward, keeps old prev_reward)
```

On stall, routing goes directly to `act`, skipping `persist_reward`, so the baseline stays stable for continued comparison.

### Fix 2: Live LLM Judge

Replaced the `+ 0.2` constant in `observe` with a `claude -p` subprocess call:
- Determines target files from `context.target_files` or `git diff --name-only HEAD`
- Asks Claude to rate code quality as a decimal 0.0–1.0
- Clamps result to [0.0, 1.0] with a 0.5 fallback on parse failure
- Reward formula: `TEST_SCORE * 0.5 + LINT_SCORE * 0.3 + LLM_SCORE * 0.2`

### Also Updated

- `description` field: "LLM-as-judge weight" → "live LLM-as-judge score"
- Removed stale limitation comments from `score` and `observe`

## Verification

- All 3610 existing tests pass (`python -m pytest scripts/tests/`)
- No schema changes; only loop YAML edits
