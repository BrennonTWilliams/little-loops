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

### Additional Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Token estimator inaccessible**: the only token heuristic `_est(s) = len(s) // 4` is a local closure inside `_compact_session_conn()` at line 1077, not accessible to `_summarize_block()` at line 1028. Even if `_summarize_block()` wanted to compare sizes, it has no way to estimate tokens.
- **Config fields ignored**: `CompactionConfig.model` (line 730 of `config/features.py`) and `CompactionConfig.timeout` (line 731) are declared but never read by `_summarize_block()`. The host invocation at line 1040 calls `build_blocking_json(prompt=prompt)` without `model`, and the timeout is hardcoded to 60s (line 1045).
- **JSON envelope stored verbatim**: `build_blocking_json()` adds `--output-format json` to the host args. The raw stdout includes a JSON wrapper, not just prose. `proc.stdout.strip()` stores the entire stdout into `summary_nodes.content` — the envelope inflates the stored text and may skew `_est()` token counts.
- **Two call sites, same bug**: `_summarize_block()` is called twice per session — for leaf blocks (line 1107) and for the condensed node (line 1131). Both paths lack size checks and level-2 escalation.

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Token estimation**: The only token estimator in the codebase is the local closure `_est(s) = len(s) // 4` at `session_store.py:1077-1078`, defined inside `_compact_session_conn()`. It is inaccessible to `_summarize_block()` (line 1028). To implement the `est(summary) < est(input)` size check, either:
- Promote `_est` to a module-level `_estimate_tokens(text: str) -> int` function usable by both `_compact_session_conn()` and `_summarize_block()`, or
- Duplicate the `len(s) // 4` heuristic inside `_summarize_block()`.

**Host invocation details**: `_summarize_block()` calls `resolve_host().build_blocking_json(prompt=prompt)` at line 1040 without passing `model` or `timeout`. Both `CompactionConfig.model` (line 730 of `config/features.py`) and `CompactionConfig.timeout` (line 731) are declared but ignored. The timeout is hardcoded to 60s (line 1045). For the level-2 call, consider passing the config model and using the config timeout rather than hardcoding.

**Prompt construction**: The current prompt (lines 1033-1035) requests "2-3 paragraphs" of "concise" prose but does not mention a token budget. The `budget` parameter is unused in the prompt text. The level-2 prompt should explicitly request bullet points and mention the halved budget to guide the LLM toward compression.

**JSON envelope concern**: `build_blocking_json()` adds `--output-format json` to the host args. The raw stdout includes a JSON envelope, not just prose summary text. `proc.stdout.strip()` stores the entire stdout verbatim into `summary_nodes.content`. Consider stripping the JSON wrapper before storing (or before running size checks) — the envelope inflates the stored content and may skew token estimates.

**Condensed node double-escalation**: `_summarize_block()` is called twice per session — once per leaf block (line 1107) and once for the condensed node (line 1131). Both calls need the convergence fix. The condensed node's input is already-compact leaf summaries; escalation to level 2/3 is less likely but must still be enforced for correctness.

**Error visibility**: The bare `except Exception: pass` at line 1049 silently swallows all failures — no logging, no warning. Consider logging when escalation occurs (level 1→2, level 2→3) so operators can detect systemic LLM summarization failures.

**Related bugs**: BUG-1926 (summary DAG has no inter-level edges) and ENH-1927 (recursive cross-session condensation) touch adjacent code in `_compact_session_conn()`. Coordinate with those fixes to avoid merge conflicts in the `_compact_session_conn()` function body.

## Implementation Steps

1. **Promote `_est` to module-level** (`session_store.py`): extract `_est(s) = len(s) // 4` from the `_compact_session_conn()` closure (line 1077) into `_estimate_tokens(text: str) -> int` at module scope, so `_summarize_block()` can use it for size comparison.
2. **Add level-1 size check** (`_summarize_block()`, after line 1048): compute `est_input = _estimate_tokens(block_text)` before the LLM call, then `est_output = _estimate_tokens(summary)` after. Accept only if `est_output < est_input`. If not, escalate to level 2.
3. **Add level-2 aggressive summarization** (`_summarize_block()`): construct an aggressive/bullet-point prompt with explicit token budget guidance (`target_tokens = budget // 2`). Call `build_blocking_json(prompt=...)` again with the new prompt. If the result is smaller than input, accept it. Model the prompt construction after the existing pattern at lines 1033-1035.
4. **Keep level-3 truncation, reconcile target** (`_summarize_block()`, line 1052): the current `budget * 4` chars (16,384 at default) is ~4x the paper's 512-token constant. Decide: keep `budget * 4` (aligned with budget) or adopt paper's 512-token constant. Document the choice in a comment above the truncation line. Also update the misleading comment on line 1051.
5. **Add `TestSummarizeBlock` test class** (`test_session_store.py`): mock `subprocess.run` (following the pattern in `test_subprocess_mocks.py:38-68`) to return a verbose "summary" longer than input. Assert `_summarize_block()` escalates to level 2, then level 3, and the returned output is strictly smaller than input by token count.
6. **Verify existing compaction tests**: run `python -m pytest scripts/tests/test_session_store.py::TestCompactSession -v` and confirm all 7 existing tests still pass.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_summarize_block()` (primary change site)
- `scripts/little_loops/session_store.py` — FEAT-1712 docstring/comment claiming convergence guarantee

### Dependent Files (Callers/Importers)
- `scripts/little_loops/session_store.py:1107` — `_compact_session_conn()` calls `_summarize_block(contents, budget)` for each leaf block
- `scripts/little_loops/session_store.py:1131` — `_compact_session_conn()` calls `_summarize_block(leaf_summaries, budget)` for the session-level condensed node (when ≥2 leaves)
- `scripts/little_loops/session_store.py:1142` — `_compact_sessions()` iterates all sessions, gated by `CompactionConfig.enabled`
- `scripts/little_loops/session_store.py:1165` — `compact_session()` public entry point wraps `_compact_session_conn()`
- `scripts/little_loops/session_store.py:1262` — `backfill()` wires compaction as final step (single transaction commit)
- `scripts/little_loops/session_store.py:1269` — `backfill_incremental()` does **not** wire compaction (no `_compact_sessions()` call)
- No external callers exist — `_summarize_block()` is module-private, called only from `_compact_session_conn()`

### Similar Patterns
- `scripts/little_loops/fsm/evaluators.py:351-413` — `evaluate_convergence()` implements size-comparison logic (`current < previous` for `minimize` direction) that mirrors the needed `est(summary) < est(input)` check
- `scripts/little_loops/fsm/evaluators.py:416-508` — `evaluate_diff_stall()` implements counter-based multi-step escalation (track iterations, escalate when threshold reached) — a pattern for the level-1→level-2→level-3 chain
- `scripts/little_loops/session_store.py:1077-1078` — `_est(s) = len(s) // 4` is the only token estimator in the codebase; a local closure inside `_compact_session_conn()`, not accessible to `_summarize_block()`. Should be promoted to module-level or duplicated into `_summarize_block()`
- `scripts/little_loops/host_runner.py:274-300` — `ClaudeCodeRunner.build_blocking_json()` is the host invocation pattern; currently called without `model` parameter (config field is ignored)
- No other compaction/summarization paths with the same bug exist — `_summarize_block()` is the sole summarization primitive

### Tests
- `scripts/tests/test_session_store.py:1608-1779` — class `TestCompactSession`; existing compaction tests (7 tests: leaf creation, idempotency, spans, condensed nodes, empty session, backfill with/without compaction). All test the end-to-end DB path without mocking the LLM host call
- `scripts/tests/test_session_store.py` — add unit test for non-reducing summary escalation in class `TestSummarizeBlock` (new). Mock `subprocess.run` to return a verbose "summary" longer than input; assert the function escalates to level 2, then level 3, and returns output strictly smaller than input
- `scripts/tests/test_subprocess_mocks.py:38-68` — `mock_popen` fixture and `@patch("subprocess.run")` pattern to model the new test after
- `scripts/tests/test_subprocess_mocks.py:69-77` — `_patch_resolve_host` autouse fixture patches `resolve_host` to return `ClaudeCodeRunner()` — may be needed if the host binary isn't on PATH in CI
- Verify existing `TestCompactSession` tests (lines 1608-1779) still pass after the three-level restructure

### Documentation
- `scripts/little_loops/session_store.py:1051` — misleading comment: `# Deterministic truncation fallback (LCM Algorithm 3, level 3 convergence guarantee).` — implies three-level escalation exists when only level 3 is implemented. Update to describe the actual three-level chain after the fix.
- `scripts/little_loops/session_store.py:1024` — section comment: `# Compaction -- LCM-style summary DAG (FEAT-1712)` — may need update to reflect the enforced convergence guarantee
- `.issues/features/P3-FEAT-1712-...:170-171` — FEAT-1712 "Post-validation" section describes accepting "non-empty after `.strip()`" — does not describe size-check gating. The implementation will diverge from FEAT-1712's original spec by adding convergence enforcement; document this divergence in both the issue and the code comments.
- `docs/ARCHITECTURE.md:562` — documents v10 schema (summary_nodes, summary_spans) and LCM-style summary DAG — no update needed unless architecture docs describe the compaction algorithm in detail
- `docs/research/LCM-Lossless-Context-Management.md` — LCM paper reference describing Algorithm 3 escalation — no update needed

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
- `/ll:refine-issue` - 2026-06-04T04:37:49 - `433923b9-97cc-4e7b-8b6e-3c892d62246e.jsonl`
- `/ll:format-issue` - 2026-06-04T04:25:50 - `ebd660b4-d823-4604-938b-3e6221250f5e.jsonl`
- `/ll:capture-issue` - 2026-06-04T04:15:05Z - `92ad3505-8fca-44b2-aa0f-0ee9ce80d024.jsonl`
