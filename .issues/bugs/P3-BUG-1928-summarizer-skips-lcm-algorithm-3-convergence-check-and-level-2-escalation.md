---
id: BUG-1928
title: Summarizer skips LCM Algorithm 3 convergence check and level-2 escalation
type: BUG
priority: P3
status: open
captured_at: "2026-06-04T04:15:05Z"
discovered_date: "2026-06-04"
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- FEAT-1712
labels:
- bug
- history
- session-store
- context-management
- captured
---

# BUG-1928: Summarizer skips LCM Algorithm 3 convergence check and level-2 escalation

## Summary

FEAT-1712 claims to inherit "LCM Algorithm 3, level-3 convergence guarantee," but `_summarize_block()` does not implement the guarantee. Algorithm 3 escalates on **compaction failure** — `if Tokens(S) < Tokens(X)` is false, i.e. the summary is not smaller than its input — stepping through level 1 (preserve-details) → level 2 (aggressive/bullet-points at T/2) → level 3 (deterministic truncate). Our implementation does one LLM call and only truncates on **subprocess error / empty stdout**. It never compares output vs. input size, so a verbose LLM summary that is *longer* than the block is accepted and stored — defeating compaction and violating the very convergence property the fallback was cited to provide. Level 2 is absent entirely.

## Root Cause

`scripts/little_loops/session_store.py` — `_summarize_block()` (~lines 1028-1053):

```python
if proc.returncode == 0 and proc.stdout.strip():
    return proc.stdout.strip()   # accepted with no Tokens(S) < Tokens(X) check
except Exception:
    pass
# fallback fires only on LLM *error*, not on non-reduction
max_chars = budget * 4
return block_text[:max_chars]
```

The fallback trigger is "LLM unavailable," not "summary failed to reduce token count" — a different condition than Algorithm 3 specifies. There is also no level-2 (aggressive/bullet-point at T/2) stage between the normal summary and truncation.

Secondary divergence: the paper truncates to 512 tokens at level 3; we truncate to `budget * 4` chars (≈ the full budget, 16K chars at the 4096 default).

## Expected Behavior

`_summarize_block()` enforces convergence per LCM Algorithm 3:
1. Level 1: normal LLM summary (preserve details), target = budget.
2. If `est(summary) >= est(input)`: level 2 — aggressive/bullet-point LLM summary at target = budget/2.
3. If still not reduced (or LLM unavailable at any step): level 3 — deterministic truncation (guaranteed to converge).
4. Accept the first level whose output is strictly smaller than the input.

## Current Behavior

One LLM call; output accepted unconditionally on exit 0 with non-empty stdout. Truncation only on subprocess failure. No size check, no level 2.

## Implementation Steps

1. Add an `est()`-based size check after the level-1 LLM call; if not reduced, escalate.
2. Add a level-2 aggressive summarization prompt (bullet points, half the target budget).
3. Keep the deterministic truncation as level 3; reconcile the truncation target with the paper's intent (decide between the 512-token paper constant and the current `budget*4` chars and document the choice).
4. Add a `_summarize_block` unit test that feeds a non-reducing "summary" (monkeypatch the host call to echo a string longer than the input) and asserts escalation to a reduced output.

## API/Interface

Internal only (`_summarize_block`); no public surface change. Update the FEAT-1712 docstring/comment that asserts the convergence guarantee so the claim matches the code.

## Acceptance Criteria

- When the LLM returns a summary not smaller than its input, `_summarize_block()` escalates and ultimately returns output strictly smaller than the input (never stores a non-reducing summary).
- A test exercises the non-reduction path (not just the subprocess-error path).
- `summary_nodes.tokens` for a leaf is always `< est(block input)`.

## Impact

- **Who benefits**: anyone relying on compaction to actually reduce context; today a verbose model could inflate rather than compress.
- **Severity**: P3 — opt-in feature (`history.compaction.enabled=false` by default), but it is a correctness/fidelity bug: the cited convergence guarantee is not enforced.

## Status

---

open

## Session Log
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
