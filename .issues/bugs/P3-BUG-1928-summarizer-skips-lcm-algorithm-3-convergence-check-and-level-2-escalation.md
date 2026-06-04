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

## Steps to Reproduce

1. Enable history compaction: set `history.compaction.enabled=true` in `.ll/ll-config.json`.
2. Create a session with a large message block that triggers summarization (block size > `compaction.target_tokens`).
3. Ensure the LLM host returns a verbose summary that is not smaller than the input block (e.g., through a model that expands rather than compresses, or by monkeypatching `_summarize_block`'s host call in tests).
4. Observe that `_summarize_block()` accepts the non-reducing summary and stores it — `summary_nodes.tokens >= est(block input)`, violating the LCM Algorithm 3 convergence guarantee cited in FEAT-1712.
5. Expected: the method should detect the non-reduction, escalate to level 2 (aggressive/bullet-point summary at T/2), and if still not reduced, fall back to deterministic truncation (level 3).

## Expected Behavior

`_summarize_block()` enforces convergence per LCM Algorithm 3:
1. Level 1: normal LLM summary (preserve details), target = budget.
2. If `est(summary) >= est(input)`: level 2 — aggressive/bullet-point LLM summary at target = budget/2.
3. If still not reduced (or LLM unavailable at any step): level 3 — deterministic truncation (guaranteed to converge).
4. Accept the first level whose output is strictly smaller than the input.

## Current Behavior

One LLM call; output accepted unconditionally on exit 0 with non-empty stdout. Truncation only on subprocess failure. No size check, no level 2.

## Proposed Solution

In `scripts/little_loops/session_store.py`, `_summarize_block()` (~line 1028), restructure the summarization path into three levels matching LCM Algorithm 3:

```python
def _summarize_block(block_text: str, budget: int) -> str:
    """Summarize block_text to fit within budget tokens, with convergence guarantee.

    LCM Algorithm 3 escalation:
      Level 1: normal LLM summary (preserve details), target = budget.
      Level 2: if est(summary) >= est(input) → aggressive/bullet-point LLM summary at target = budget/2.
      Level 3: if still not reduced (or LLM unavailable) → deterministic truncation (guaranteed to converge).
    """
    est_input = estimate_tokens(block_text)

    # Level 1: normal summary
    summary = _call_llm_summarize(block_text, target_tokens=budget, style="preserve-details")
    if summary and estimate_tokens(summary) < est_input:
        return summary

    # Level 2: aggressive bullet-point summary at half budget
    summary = _call_llm_summarize(block_text, target_tokens=budget // 2, style="aggressive-bullet")
    if summary and estimate_tokens(summary) < est_input:
        return summary

    # Level 3: deterministic truncation (guaranteed reduction)
    return block_text[:budget * 4]  # or align with paper's 512-token constant
```

Key changes:
- Replace the single `if proc.returncode == 0` gate with `est(summary) < est(input)` size checks.
- Add a level-2 LLM call with an aggressive/bullet-point prompt at half the target budget.
- Keep the existing truncation fallback as level 3; reconcile the truncation target (paper: 512 tokens vs. current: `budget * 4` chars) and document the choice.
- Update the FEAT-1712 docstring/comment claiming the convergence guarantee so the claim matches the code.

## Implementation Steps

1. Add an `est()`-based size check after the level-1 LLM call; if not reduced, escalate.
2. Add a level-2 aggressive summarization prompt (bullet points, half the target budget).
3. Keep the deterministic truncation as level 3; reconcile the truncation target with the paper's intent (decide between the 512-token paper constant and the current `budget*4` chars and document the choice).
4. Add a `_summarize_block` unit test that feeds a non-reducing "summary" (monkeypatch the host call to echo a string longer than the input) and asserts escalation to a reduced output.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_summarize_block()` (primary change site)
- `scripts/little_loops/session_store.py` — FEAT-1712 docstring/comment claiming convergence guarantee

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py` — `_summarize_block()` is called internally; verify callers within the module
- TBD — grep for `_summarize_block` to find external callers

### Similar Patterns
- TBD — search for other compaction/summarization paths that may have the same missing-convergence-check pattern

### Tests
- `scripts/tests/test_session_store.py` — add unit test for non-reducing summary escalation
- Verify existing summarization tests still pass after the three-level restructure

### Documentation
- Update FEAT-1712 docstring/comment in `session_store.py` to accurately reflect the enforced convergence guarantee

### Configuration
- N/A — no config changes; `history.compaction.enabled` already exists and gates this code path

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
- `/ll:format-issue` - 2026-06-04T04:25:50 - `ebd660b4-d823-4604-938b-3e6221250f5e.jsonl`
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
