---
id: BUG-1934
title: Implement three-level LCM Algorithm 3 escalation in _summarize_block()
type: BUG
priority: P3
status: done
completed_at: 2026-06-04 08:01:03+00:00
parent: BUG-1928
relates_to:
- EPIC-1707
- FEAT-1712
labels:
- bug
- history
- session-store
- context-management
size: Large
decision_needed: false
confidence_score: 100
outcome_confidence: 80
score_complexity: 20
score_test_coverage: 15
score_ambiguity: 22
score_change_surface: 23
---

# BUG-1934: Implement three-level LCM Algorithm 3 escalation in _summarize_block()

## Summary

`_summarize_block()` in `session_store.py` does a single LLM call and accepts the output unconditionally on exit 0 — it never checks whether the summary is actually smaller than the input. FEAT-1712 claims to inherit "LCM Algorithm 3, level-3 convergence guarantee," but the code skips the size-check gating and level-2 escalation entirely. This child implements the three-level escalation chain and adds tests to cover the previously-untested LLM summary path.

## Current Behavior

`_summarize_block()` in `session_store.py` does a single LLM call via `subprocess.run()` and accepts the output unconditionally on `returncode == 0` — it never checks whether the summary is actually smaller than the input. It has only two paths: LLM success (returns raw `proc.stdout.strip()` — the entire JSON envelope, not the prose `result` field) or deterministic truncation (falls back to `block_text[:budget * 4]` characters). There is no intermediate "retry with aggressive prompt" path (level 2). Additionally:

- `CompactionConfig.model` and `CompactionConfig.timeout` are declared but never wired through to `_summarize_block()`; the timeout is hardcoded at 60s and no model is passed to `build_blocking_json()`.
- The bare `except Exception: pass` silently swallows `TimeoutExpired`, `FileNotFoundError`, and all other exception types with no diagnostic logging.
- `build_blocking_json()` returns a JSON envelope (`{"type":"result","result":"..."}`), but line 1050 stores the raw JSON string — so `summary_nodes.content` contains JSON boilerplate and the token estimate counts wrapper characters.
- Both call sites are equally affected: leaf blocks (line 1109) and condensed nodes (line 1133).

## Expected Behavior

`_summarize_block()` should implement three-level LCM Algorithm 3 escalation:

1. **Level 1**: Normal LLM summary — parse JSON envelope, extract `result` prose, accept only if `_estimate_tokens(result) < _estimate_tokens(input)`.
2. **Level 2**: Aggressive bullet-point LLM summary at `budget // 2` — if level 1 output is not smaller than input, retry with a tighter prompt.
3. **Level 3**: Deterministic truncation — guaranteed to produce output ≤ input by construction, using a bounded character cap (e.g., `min(budget * 4, 2048)`).

Escalations should be logged at `WARNING` level so operators can detect systemic LLM summarization failures. The `model` and `timeout` fields from `CompactionConfig` should be wired through to the LLM call.

## Steps to Reproduce

1. Enable compaction with `history.compaction.enabled: true` in config and a sufficiently large `budget_tokens` (e.g., 4096).
2. Run `ll-session backfill` on a session with short message content (a few hundred tokens total).
3. The LLM summary of already-compact text will be similar in length to (or longer than) the input, but `_summarize_block()` accepts it unconditionally.
4. Observe: `summary_nodes.tokens` for the leaf is equal to or greater than the token estimate of the input block — compaction produced no actual size reduction.
5. Expected: Level 1 escalates to level 2 (aggressive prompt), and if that also fails to reduce size, level 3 truncation is applied, guaranteeing a strictly smaller output.

## Root Cause

- **File**: `scripts/little_loops/session_store.py`
- **Anchor**: `_summarize_block()` at line 1030
- **Cause**: The function accepts LLM output unconditionally on `returncode == 0` (line 1049) without checking whether the summary is actually smaller than the input. It has only two paths: LLM success (line 1050) or deterministic truncation (line 1055). There is no intermediate "retry with aggressive prompt" path (level 2), and the truncation fallback at line 1054 uses `budget * 4` characters — which can be as large as the full budget — not a guaranteed-small constant. Additionally:
  - `CompactionConfig.model` (config/features.py:730) and `CompactionConfig.timeout` (config/features.py:731) are declared but never wired through to `_summarize_block()`; the timeout is hardcoded at 60s (line 1047) and no model is passed to `build_blocking_json()` (line 1042).
  - The bare `except Exception: pass` at line 1051 silently swallows `TimeoutExpired`, `FileNotFoundError`, and all other exception types with no diagnostic logging.
  - `build_blocking_json()` at `host_runner.py:283` adds `--output-format json`, so the CLI returns a JSON envelope (`{"type":"result","result":"..."}`), not raw prose. Line 1050 returns `proc.stdout.strip()` — the entire JSON string — meaning `summary_nodes.content` stores JSON boilerplate and the token estimate `len(content) // 4` counts wrapper characters.
  - Both call sites are equally affected: leaf blocks (line 1109) and condensed nodes (line 1133). The condensed path is higher risk because it summarizes already-summarized text.

## Parent Issue

Decomposed from BUG-1928: Summarizer skips LCM Algorithm 3 convergence check and level-2 escalation

## Scope

This child covers the code change, unit tests, and integration test verification. Documentation updates (docstrings, migration comments, config-schema descriptions) are in BUG-1935.

### Covers Parent Steps

Steps 1–6, 11–15, 17 from BUG-1928 Implementation Steps, plus the `_estimate_tokens` test coverage from step 13.

## Proposed Solution

In `scripts/little_loops/session_store.py`, restructure `_summarize_block()` (~line 1028) into three levels matching LCM Algorithm 3:

```python
def _summarize_block(block_text: str, budget: int) -> str:
    """Summarize block_text to fit within budget tokens, with convergence guarantee.

    LCM Algorithm 3 escalation:
      Level 1: normal LLM summary (preserve details), target = budget.
      Level 2: if est(summary) >= est(input) → aggressive/bullet-point LLM summary at target = budget/2.
      Level 3: if still not reduced (or LLM unavailable) → deterministic truncation (guaranteed to converge).
    """
    est_input = _estimate_tokens(block_text)

    # Level 1: normal summary
    summary = _call_llm_summarize(block_text, target_tokens=budget, style="preserve-details")
    if summary and _estimate_tokens(summary) < est_input:
        return summary

    # Level 2: aggressive bullet-point summary at half budget
    summary = _call_llm_summarize(block_text, target_tokens=budget // 2, style="aggressive-bullet")
    if summary and _estimate_tokens(summary) < est_input:
        return summary

    # Level 3: deterministic truncation (guaranteed reduction)
    return block_text[:budget * 4]  # or align with paper's 512-token constant
```

Key changes:
- Promote `_est(s) = len(s) // 4` from local closure in `_compact_session_conn()` (line 1077) to module-level `_estimate_tokens(text: str) -> int`
- Replace `if proc.returncode == 0` gate with `_estimate_tokens(summary) < _estimate_tokens(input)` size checks
- Add level-2 LLM call with aggressive/bullet-point prompt at `budget // 2`, modeled after existing prompt pattern (lines 1033-1035)
- Keep truncation as level 3; reconcile truncation target (paper: 512 tokens vs. current: `budget * 4` chars) and document the choice
- Add logging when escalation occurs (level 1→2, level 2→3) so operators can detect systemic LLM summarization failures
- Replace bare `except Exception: pass` with proper error handling following the `evaluate_llm_structured()` pattern at `fsm/evaluators.py:832-880`

### Token estimation

Promote `_est` to `_estimate_tokens()` at module scope so both `_compact_session_conn()` and `_summarize_block()` can use it.

### Prompt construction

The current prompt (lines 1033-1035) requests "2-3 paragraphs" of "concise" prose but doesn't mention a token budget. The level-2 prompt must explicitly request bullet points and mention the halved budget.

### Error visibility

Replace bare `except Exception: pass` at line 1049 with proper logging when escalation occurs.

### Condensed node coverage

`_summarize_block()` is called twice per session — for leaf blocks (line 1109) and for the condensed node (line 1131). Both paths need the convergence fix.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **JSON envelope storage**: `build_blocking_json()` at `host_runner.py:283` hardcodes `--output-format json`, so the claude CLI returns a JSON envelope (`{"type":"result","result":"..."}`) not raw prose. The current code at line 1050 returns `proc.stdout.strip()` — the entire JSON string. This means `summary_nodes.content` stores JSON boilerplate alongside the summary text, and `tokens = _est(content)` counts JSON wrapper characters. The three-level implementation should parse the envelope and extract only the `result` field for storage and size comparison. Follow the envelope parsing pattern at `fsm/evaluators.py:844-880` (`is_error` detection, `result` extraction).
- **Config wiring gap**: `_compact_sessions()` at line 1170 only passes `budget=compact_cfg.budget_tokens` to `_compact_session_conn()`. Neither `model` (config/features.py:730) nor `timeout` (config/features.py:731) from `CompactionConfig` are forwarded. The implementation should thread both through `_compact_session_conn()` → `_summarize_block()` → `build_blocking_json(model=model)` and `subprocess.run(timeout=timeout)`.
- **Truncation target reconciliation**: Current `budget * 4` (line 1054) at default 4096 tokens = 16,384 characters — enough to hold the full block text in most cases, providing no size reduction. The LCM paper's level-3 constant is 512 tokens (~2,048 chars at 4 chars/token). Options: (a) adopt `min(budget * 4, 2048)` for guaranteed reduction, (b) use `budget // 2 * 4` to halve, (c) keep current formula but document the choice. Truncation is a convergence guarantee, not a quality mechanism — a smaller fixed cap is defensible.
- **Two call sites, same bug**: Both leaf (line 1109) and condensed (line 1133) call paths are equally affected — neither gets a size check. The condensed path is arguably higher risk because it summarizes already-summarized text, where an LLM may produce output similar in length to its input.
- **Existing tests never mock subprocess**: All 7 `TestCompactSession` tests exercise the truncation fallback only (LLM call fails in test environment because `claude` binary is not on PATH). The new `TestSummarizeBlock` class will be the first to mock `subprocess.run` in this test file. Use `_make_completed()` from `test_cli_harness.py:39-42` or the `MagicMock` fixture pattern from `test_fsm_evaluators.py:678-686`.
- **`resolve_host` import inside try block**: `from little_loops.host_runner import resolve_host` at line 1040 is inside the try/except. If the import fails (e.g., package not installed), it's silently swallowed by the bare `except Exception: pass`. The new error handling should move this import to module level or handle `ImportError` explicitly. Current practice in `fsm/evaluators.py` is to import at module level (line 22).
- **Logging when escalation occurs**: The codebase uses `logging.getLogger(__name__)` pattern (e.g., `session_store.py` line ~30). Add `logger.warning()` calls when escalating level 1→2 and level 2→3 so operators can detect systemic LLM summarization failures.

## Implementation Steps

1. **Promote `_est` to module-level**: Extract `_est(s) = len(s) // 4` from `_compact_session_conn()` closure (lines 1079-1080) into `_estimate_tokens(text: str) -> int` at module scope (insert near `_summarize_block()` at line ~1029). Update the three call sites in `_compact_session_conn()` — block accumulation at line 1089 (`tok = _est(content)`), leaf token storage at line 1114 (`_est(summary)`), and condensed token storage at line 1138 (`_est(condensed_text)`) — to use `_estimate_tokens()` instead. This makes token estimation available to `_summarize_block()` for size-comparison gating.

2. **Add level-1 size check and JSON envelope parsing**: Before the LLM call, compute `est_input = _estimate_tokens(block_text)`. After `subprocess.run()` succeeds (`returncode == 0` and stdout non-empty), parse the JSON envelope from `proc.stdout` (follow `evaluate_llm_structured()` at `fsm/evaluators.py:844-880` for envelope parsing, `is_error` detection, and `result` extraction). Extract the `result` field (the actual summary prose), compute `est_output = _estimate_tokens(result)`, and return `result` only if `est_output < est_input`. If not, escalate to level 2. This also fixes the current bug where JSON boilerplate is stored in `summary_nodes.content` alongside the prose.

3. **Add level-2 aggressive summarization**: Construct an aggressive/bullet-point prompt (replacing "2-3 paragraphs" at lines 1035-1038 with bullet-list instructions and an explicit token budget mention: e.g., "Summarize as a bullet list within ~{target} tokens"). Target `budget // 2` tokens. Call `build_blocking_json(prompt=level2_prompt, model=model)` again (wiring through the `model` config field from `CompactionConfig`). Parse JSON envelope, extract `result`, compute `est_output = _estimate_tokens(result)`. If `est_output < est_input`, return `result`. Log `logger.warning("_summarize_block: escalated to level 2 (aggressive bullet-point)")`. If still not smaller, escalate to level 3.

4. **Keep level-3 truncation, reconcile target**: Current `budget * 4` chars (line 1054) at default 4096 tokens = 16,384 chars vs. paper's 512-token constant (~2,048 chars at 4 chars/token). Options: (a) adopt `min(budget * 4, 2048)` for guaranteed reduction, (b) use `budget // 2 * 4` to halve, (c) keep current formula but document the choice. Truncation is a convergence guarantee (always produces output ≤ input by construction), not a quality mechanism — a smaller fixed cap is defensible. Log `logger.warning("_summarize_block: escalated to level 3 (deterministic truncation)")` when reaching this path so operators can detect systemic LLM summarization failures.

5. **Replace bare `except Exception: pass` (line 1051)**: Follow `evaluate_llm_structured()` pattern at `fsm/evaluators.py:785-824` — distinguish each failure mode:
   - `subprocess.TimeoutExpired` (cf. line 792): log warning, fall through to level 3 truncation
   - `FileNotFoundError` (cf. line 797): log error with host CLI path hint, fall through to truncation
   - Non-zero `returncode` (cf. line 807): log error with `proc.stderr`, fall through to truncation
   - Empty stdout on exit 0 (cf. line 817): log error with stderr preview, fall through to truncation
   - Move `from little_loops.host_runner import resolve_host` (line 1040) to module-level import (follows `fsm/evaluators.py` line 22 convention); if the import must stay lazy, handle `ImportError` explicitly rather than letting the bare `except Exception` swallow it.

6. **Add `TestSummarizeBlock` test class** in `test_session_store.py`: Mock `subprocess.run` (using `_make_completed()` pattern from `test_cli_harness.py:39-42`) to return a verbose "summary" longer than input. Assert `_summarize_block()` escalates to level 2, then level 3, and returned output is strictly smaller than input by token count.

7. **Add `_estimate_tokens` unit tests**: Cover empty string → 0, ASCII text → `len(s)//4`, multi-byte Unicode, very long string, consistency with previous local-closure behavior.

8. **Verify existing compaction tests**: Run `python -m pytest scripts/tests/test_session_store.py::TestCompactSession -v` and confirm all 7 existing tests still pass.

9. **Verify summary DAG tests**: Run `python -m pytest scripts/tests/test_history_reader.py::TestSummaryDagRetrieval -v` (10 tests) and `python -m pytest scripts/tests/test_ll_session.py::TestGrepExpandDescribe -v`.

10. **Verify indirect backfill consumers**: Run `test_issue_history_cli.py`, `test_workflow_sequence_analyzer.py`, `test_issue_history_parsing.py`.

11. **Smoke test `ll-session backfill`**: Run `ll-session backfill <db>` to confirm end-to-end.

12. **Smoke test DAG readers**: Run `ll-session grep`, `ll-session expand`, `ll-session describe` against a compacted DB.

## Integration Map

### Files to Modify
- `scripts/little_loops/session_store.py` — `_summarize_block()` (line 1030, primary), `_estimate_tokens()` (new, promote from `_est` closure at line 1079), `_compact_session_conn()` (line 1058, update `_est` call sites at lines 1089, 1114, 1138), `_compact_sessions()` (line 1151, wire `model` and `timeout` through to `_summarize_block()`), `compact_session()` (line 1174, same wiring gap)
- `scripts/tests/test_session_store.py` — Add `TestSummarizeBlock` class (following `TestCompactSession` pattern at line 1621) and `_estimate_tokens` unit tests

### Callers / Dependents
- `_compact_session_conn()` at `session_store.py:1109` — calls `_summarize_block(contents, budget)` for leaf blocks
- `_compact_session_conn()` at `session_store.py:1133` — calls `_summarize_block(leaf_summaries, budget)` for condensed node (when `len(all_leaves) >= 2`)
- `_compact_sessions()` at `session_store.py:1170` — wires `CompactionConfig.budget_tokens` but not `model` or `timeout`
- `compact_session()` at `session_store.py:1174` — public API, same wiring gap
- `backfill()` at `session_store.py:1240` — top-level caller that invokes `_compact_sessions()`
- Both call sites are equally affected: neither gets a size check. The condensed path (line 1133) is higher risk because it summarizes already-summarized text.

_Wiring pass added by `/ll:wire-issue`:_
- `cli/session.py::backfill` subcommand (line 292-330) — imports `backfill()` and accesses `counts["summaries"]` from the return dict to construct a CLI success message. Structurally compatible (key name unchanged), but listed as a consumer for awareness during implementation and verification.

### Similar Patterns
- `evaluate_llm_structured()` at `fsm/evaluators.py:741-886` — canonical error handling to follow: distinguishes `TimeoutExpired` (line 792), `FileNotFoundError` (line 797), non-zero returncode (line 807), empty stdout (line 817), and JSON parse failures (line 881)
- `cmd_prompt()` at `cli/harness.py:330-349` — simpler three-level subprocess error pattern
- `_make_completed()` at `test_cli_harness.py:39-42` — mock helper for `subprocess.CompletedProcess` to use in new tests
- `mock_cli` fixture at `test_fsm_evaluators.py:678-686` — MagicMock pattern for `subprocess.run` as alternative mocking approach

### Tests
- `scripts/tests/test_session_store.py::TestCompactSession` (line 1621) — 7 existing tests; all exercise the truncation fallback only (LLM unavailable in test env, `subprocess.run` raises `FileNotFoundError`); no tests mock subprocess for non-reduction behavior
- `scripts/tests/test_history_reader.py::TestSummaryDagRetrieval` — 10 DAG retrieval tests for verification
- `scripts/tests/test_ll_session.py::TestGrepExpandDescribe` — DAG reader command tests
- `scripts/tests/test_fsm_evaluators.py::TestLLMStructuredEvaluator` (line ~660) — subprocess mocking patterns to model after
- `scripts/tests/test_issue_history_cli.py` — indirect backfill consumer
- `scripts/tests/test_workflow_sequence_analyzer.py` — indirect backfill consumer
- `scripts/tests/test_issue_history_parsing.py` — indirect backfill consumer

_Wiring pass added by `/ll:wire-issue` — test impact analysis:_
- **No existing tests should break.** All 7 `TestCompactSession` tests exercise the truncation fallback only (`subprocess.run` raises `FileNotFoundError` → caught → falls through to truncation). The three-level escalation adds paths *above* truncation (level 1 LLM success, level 2 aggressive retry), which existing tests never enter. Tests assert on structural DB outcomes (node count, `kind`, `parent_id`), not on `content` or `tokens` values.
- **Truncation target change risk:** If level-3 truncation changes from `budget * 4` to `min(budget * 4, 2048)`, the `tokens` column values for default-budget (4096) sessions change from ~4096 to ~512. No test asserts on specific token values, so this is safe — but it highlights that no test currently validates the `tokens` field. Consider adding a `tokens` assertion in the new `TestSummarizeBlock` tests.
- **No E2E/integration test files exist** (`test_e2e*.py`, `test_integration*.py`). The closest integration coverage is `test_backfill_with_compaction_enabled` (line 1765) and the DAG reader helper methods in `test_history_reader.py` and `test_ll_session.py`.
- `scripts/tests/test_config.py` lines 2770-2785 — validates `CompactionConfig` defaults and overrides (no change needed, config fields already exist)
- `scripts/tests/test_config_schema.py` lines 304-317 — validates compaction schema properties exist (no change needed, schema unchanged)

### Registration / Exports

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/config/__init__.py` line 44 — re-exports `CompactionConfig` in public API. No change needed (already correct), but listed for awareness during wiring verification.

### Documentation

_Wiring pass added by `/ll:wire-issue` — doc updates are BUG-1935 scope; listed here for awareness:_
- `docs/ARCHITECTURE.md` lines 558, 562, 633-634 — describes compaction, summary DAG, and `compact_session()`
- `docs/reference/API.md` line 3505 — API documentation for `backfill()`
- `docs/reference/CLI.md` lines 1752, 1780-1781 — documents `ll-session backfill` subcommand
- `CONTRIBUTING.md` line 246 — lists `session_store.py` as a key file (no update needed)

### Configuration
- `scripts/little_loops/config/features.py::CompactionConfig` (line 720) — `model` (line 730) and `timeout` (line 731) declared but unused by `_summarize_block()`; `_compact_sessions()` only passes `budget` (line 1170)
- `config-schema.json` line ~1519 — references `len(content) // 4` token estimate; docstring updates handled by sibling BUG-1935

## Acceptance Criteria

- When LLM returns a summary not smaller than its input, `_summarize_block()` escalates and ultimately returns output strictly smaller than input
- `TestSummarizeBlock` exercises the non-reduction path (not just the subprocess-error path)
- `summary_nodes.tokens` for a leaf is always `< est(block input)`
- All existing compaction and summary DAG tests continue to pass

## Impact

**Who benefits**: Anyone relying on compaction to actually reduce context. **Severity**: P3 — opt-in feature, but correctness/fidelity bug.

## Session Log
- `/ll:ready-issue` - 2026-06-04T07:20:04 - `d6f36357-a790-4340-9deb-b9afe500affa.jsonl`
- `/ll:wire-issue` - 2026-06-04T07:13:04 - `2a1b9fbd-c1f2-446d-b24c-7f8d353c4f74.jsonl`
- `/ll:refine-issue` - 2026-06-04T07:04:45 - `24d8e8b5-d82b-4d71-9812-0248a40d8b40.jsonl`

- `/ll:issue-size-review` - 2026-06-04T08:56:00Z - `f4ca78cf-649f-4e81-a544-c9b72f755584.jsonl`
- `/ll:confidence-check` - 2026-06-04T02:16:00Z - `90fc1dc8-a70c-488e-8e90-3f1e00ee560f.jsonl`
- `/ll:manage-issue` - 2026-06-04T08:01:03Z - `26ec5488-fbf3-422e-ba34-b6544f9c5de4`

## Resolution

**Status**: done
**Completed**: 2026-06-04T08:01:03Z

### Changes Made

**`scripts/little_loops/session_store.py`**:
- Promoted `_est` local closure to module-level `_estimate_tokens(text: str) -> int`
- Restructured `_summarize_block()` with three-level LCM Algorithm 3 escalation:
  - Level 1: Normal LLM summary with token budget — accepted only if output < input
  - Level 2: Aggressive bullet-point LLM summary at `budget // 2`
  - Level 3: Deterministic truncation (`min(budget * 4, 2048)` chars), guaranteed convergence
- Added short-circuit guard for very small inputs (est < 25 tokens)
- Extracted `_call_llm_for_summary()` helper with proper JSON envelope parsing and error handling
- Replaced bare `except Exception: pass` with structured error handling (TimeoutExpired, FileNotFoundError, non-zero returncode, empty stdout)
- Wired `model` and `timeout` from `CompactionConfig` through the full call chain:
  `_compact_sessions()` → `_compact_session_conn()` → `_summarize_block()` → `build_blocking_json()` / `subprocess.run()`
- Moved `resolve_host` import to module level (follows `fsm/evaluators.py` convention)
- Added `logger.warning()` calls on escalation (level 1→2, level 2→3)

**`scripts/tests/test_session_store.py`**:
- Added `TestEstimateTokens` (5 tests) — covers empty string, ASCII, Unicode, long strings
- Added `TestSummarizeBlock` (11 tests) — covers all three escalation levels, JSON envelope parsing, model/timeout wiring, logging, multi-message joining, truncation cap
- Updated `test_backfill_with_compaction_enabled` to mock `subprocess.run` for speed
- All 7 existing `TestCompactSession` tests continue to pass

### Verification
- All 146 `test_session_store.py` tests pass
- All 13 `TestSummaryDagRetrieval` DAG tests pass
- All 12 `TestGrepExpandDescribe` tests pass
- All 221 indirect consumer tests pass
- `ruff check` passes on both files
- `mypy` passes with no issues
