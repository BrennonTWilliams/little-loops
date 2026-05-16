---
discovered_date: 2026-03-05
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 86
---

# BUG-599: issue-refinement loop stuck in infinite cycle due to fmt/priority bugs

## Summary

Five bugs in `loops/issue-refinement.yaml` and `ll-loop run -v` cause the issue-refinement loop to run indefinitely and process issues in the wrong order. The critical bug is a mismatch between what the evaluate state considers a failure (`fmt=✗`) and what the fix state will act on (only `fmt=—`), creating an unbreakable cycle. Observed by running `ll-loop run issue-refinement -v` in an external project and confirmed via `ll-loop history`.

## Current Behavior

1. **`fmt=✗` vs `fmt=—` mismatch — infinite loop (critical)**: The evaluate prompt fails any issue where `fmt` shows `✗`. But the fix prompt's Step A only triggers `/ll:format-issue` if the column shows `—` (em-dash). When format-issue was previously attempted and produced `✗` (run but failed/incomplete), the fix never re-runs it. Evaluate perpetually fails and routes back to fix, which does nothing to resolve `fmt`, which causes evaluate to fail again — forever.

2. **No escape path for issues that hit an inherent confidence ceiling (high)**: The fix prompt stops after 5 refinements regardless of score. But evaluate still fails if `confidence < 70`. FEAT-2078 hit 63/100 with an "inherent ceiling" (file renames touching 11+ importers), was accepted by the fix step as done, but evaluate continues to fail it. Loop cycles on that issue indefinitely with no exit.

3. **Issue selection by "highest ID" skips high-priority bugs (medium)**: The fix prompt selects "the highest Issue ID that still needs refinement work." A P4 FEAT (FEAT-2078, ID 2078) was worked on for 14 minutes while a P0 BUG (BUG-2169, ID 2169 — a higher numeric ID) went untouched. ID-based selection is the wrong ordering heuristic.

4. **Evaluate `on_error: fix` on LLM timeout wastes a fix slot (medium)**: In the observed run, iteration 1's LLM evaluation timed out (`LLM evaluation timeout`), causing `on_error: fix` to fire and spawn a 14-minute Claude session unnecessarily. History shows each LLM evaluate step takes ~24 seconds and is vulnerable to inference latency spikes. A timeout should retry evaluation, not trigger a full fix.

5. **`ll-loop run -v` duplicates shell action output (low)**: In verbose run mode, shell command output is printed twice per iteration. Confirmed by comparing `run -v` output (table appears twice) with `history` output (table appears once). The shell command runs correctly once; the duplication is in the verbose display layer.

## Expected Behavior

1. Fix prompt handles `fmt=✗` identically to `fmt=—`: re-runs `/ll:format-issue` to clear either state.
2. Fix has a ceiling-acceptance path: after 5 refinements with `readiness>=85`, the issue is treated as done for loop purposes even if `confidence < 70`, and the loop moves on.
3. Issue selection processes by priority (P0 → P5), using ID as tiebreaker — not by highest ID alone.
4. `on_error: evaluate` (retry) instead of `on_error: fix` in the evaluate state.
5. Verbose mode prints each shell action's output exactly once.

## Steps to Reproduce

1. Have a project with active issues where some have `fmt=✗` in `ll-issues refine-status` (format previously attempted but incomplete).
2. Run `ll-loop run issue-refinement`.
3. Observe: evaluate fails on `fmt=✗`; fix never re-runs format-issue (Step A only checks for `—`); loop cycles evaluate → fix → evaluate → fix indefinitely without progress.

## Root Cause

- **Bug 1**: `loops/issue-refinement.yaml` fix prompt Step A: condition `"column shows — or absent"` does not cover the `✗` state for `fmt` or `verify`.
- **Bug 2**: `loops/issue-refinement.yaml` fix prompt Step C: no logic to flag an issue as "ceiling reached" and exempt it from future evaluate failures.
- **Bug 3**: `loops/issue-refinement.yaml` fix prompt: `"Find the highest Issue ID"` uses numeric ID as a proxy for priority — wrong heuristic.
- **Bug 4**: `loops/issue-refinement.yaml` evaluate state: `on_error: fix` should be `on_error: evaluate` to retry on timeout rather than spawning a fix session.
- **Bug 5**: `scripts/little_loops/cli/loop/info.py` (verbose run display) — shell output rendered twice per iteration in verbose mode.

## Motivation

The `issue-refinement` loop is a key component of automated issue prep workflows used by `ll-auto`, `ll-parallel`, and `ll-sprint`. When the loop infinite-cycles due to the `fmt=✗` mismatch, those automation pipelines stall entirely — no issues get refined, and the loop must be killed manually. Projects relying on automated refinement before a sprint lose the ability to prepare issues hands-free, negating the primary value of the loop system.

## Proposed Solution

**Bug 1** — Update Step A in the fix prompt to cover both `—` and `✗`:
```
- format incomplete (column shows — or ✗): /ll:format-issue [ISSUE_ID] --auto
- verify incomplete (column shows — or ✗): /ll:verify-issues [ISSUE_ID] --auto
```

**Bug 2** — Add a ceiling-acceptance rule to Step C: after 5 refinements, if `readiness >= 85`, treat the issue as refined-to-ceiling and move on. The evaluate prompt should also be updated to accept `readiness >= 85` as passing when `refine >= 5` (inherent ceiling case).

**Bug 3** — Change fix prompt selection criterion from "highest Issue ID" to "highest-priority issue needing work (lowest P number first, then highest ID as tiebreaker)."

**Bug 4** — Change `on_error: fix` → `on_error: evaluate` in the evaluate state.

**Bug 5** — Investigate `scripts/little_loops/cli/loop/info.py` for double-render of action output in verbose run mode and add a regression test.

## Integration Map

### Files to Modify
- `loops/issue-refinement.yaml` — Bugs 1, 2, 3, 4 (fix prompt and evaluate routing)
- `scripts/little_loops/cli/loop/_helpers.py` — Bug 5 (`display_progress` closure: `action_output` branch at line 258, `output_preview` branch at lines 284–290)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_ll_loop_display.py` — Tests for display behavior; add regression test for Bug 5
- `scripts/little_loops/fsm/executor.py` — emits `action_output` per line (line 549) and `action_complete` with `output_preview` (lines 559–567); no changes needed but explains the dual-emission root cause
- `scripts/little_loops/cli/loop/info.py` — reference only: `_format_history_event` at line 88 correctly gates `action_output` on verbose (`if event_type == "action_output" and not verbose: return None`); the live run fix in `_helpers.py` should mirror this pattern

### Similar Patterns
- `loops/fix-quality-and-tests.yaml` — both `check-quality` (line 22) and `check-tests` (line 51) also use `on_error: fix-*`; same routing-to-fix-on-error pattern; audit candidate for Bug 4 equivalent

### Tests
- `scripts/tests/test_ll_loop_display.py` — Add test asserting verbose mode emits each shell action output exactly once; use `MockExecutor` (lines 27–44) + `_make_args(verbose=True)` (line 861) + `capsys.readouterr()` pattern from `TestDisplayProgressEvents` (lines 858–924)

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Fix `loops/issue-refinement.yaml` evaluate state: change `on_error: fix` → `on_error: evaluate`
2. Fix `loops/issue-refinement.yaml` fix prompt Step A: add `✗` to column-check conditions for `fmt` and `verify`
3. Fix `loops/issue-refinement.yaml` fix prompt: change issue selection from "highest ID" to "highest priority then highest ID"
4. Fix `loops/issue-refinement.yaml` fix prompt Step C: add ceiling-acceptance logic (after 5 refinements with readiness>=85, skip to next issue)
5. Fix `scripts/little_loops/cli/loop/_helpers.py`: in `display_progress` closure, gate the `action_output` branch (line 258) on `verbose` (mirror `info.py:88` history pattern); then suppress `output_preview` printing in `action_complete` (lines 284–290) when `verbose=True` since lines were already streamed — net effect: non-verbose shows tail summary only; verbose shows streaming lines only
6. Add regression test to `scripts/tests/test_ll_loop_display.py` using `MockExecutor` + `_make_args(verbose=True)` + `capsys`: send `action_output` + `action_complete` events for a shell state and assert output lines appear exactly once

## Impact

- **Priority**: P2 — The loop is non-functional due to infinite cycling on the `fmt=✗` mismatch; blocks automated issue refinement workflows entirely
- **Effort**: Small — Bugs 1–4 are YAML config text changes; Bug 5 requires code investigation in one file
- **Risk**: Low — YAML changes are isolated to the loop config; display fix is additive
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|---|---|
| `docs/ARCHITECTURE.md` | FSM loop architecture and state routing |
| `.claude/CLAUDE.md` | CLI tools reference (`ll-loop`, `ll-issues`) |

## Labels

`bug`, `loops`, `fsm`, `issue-refinement`, `captured`

## Verification Notes

- **2026-03-05** — VALID. All 5 bugs confirmed in current codebase:
  - Bug 1: `loops/issue-refinement.yaml` evaluate state has `on_error: fix` (line 33); fix prompt Step A only checks `—` (not `✗`) for `fmt`/`verify` ✓
  - Bug 2: No ceiling-acceptance path in fix Step C ✓
  - Bug 3: Fix prompt selects "highest Issue ID" — priority-unaware ✓
  - Bug 4: `on_error: fix` confirmed in evaluate state (should be `on_error: evaluate`) ✓
  - Bug 5: `scripts/little_loops/cli/loop/info.py` exists; verbose display code at `cmd_run` path present; duplication not yet fixed ✓

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis (2026-03-05):_

### Precise Bug Locations

| Bug | File | Line(s) | Current Value | Required Change |
|-----|------|---------|---------------|-----------------|
| 1 (fmt=✗ mismatch) | `loops/issue-refinement.yaml` | 51–52 | `"— or absent"` | Add `or ✗` for `fmt` and `verify` conditions in Step A |
| 2 (no ceiling path) | `loops/issue-refinement.yaml` | 58 | Soft "max 5" in prompt only | Add hard ceiling-acceptance rule to Step C prompt |
| 3 (wrong selection) | `loops/issue-refinement.yaml` | 44 | `"Find the highest Issue ID"` | Change to priority-first (lowest P number, then highest ID) |
| 4 (on_error routing) | `loops/issue-refinement.yaml` | 33 | `on_error: fix` | `on_error: evaluate` |
| 5 (double output) | `scripts/little_loops/cli/loop/_helpers.py` | 258–262, 284–290 | No verbose guard on `action_output`; `output_preview` also prints for shell | Gate `action_output` on verbose; suppress `output_preview` in verbose |

### Bug 1 — `fmt`/`verify` Column Values Are Never `—`

`refine_status.py:282–283` shows `fmt` and `verify` (norm) emit **only** `✓` (`\u2713`) or `✗` (`\u2717`) — never `—` (`\u2014`). The em-dash is reserved for unscored numeric fields (`ready`, `confidence`) and unknown columns. Therefore, Step A's `"— or absent"` condition for `fmt`/`verify` can never trigger for a previously-attempted-but-failed format run that produced `✗`.

The evaluate prompt at lines 12–25 says `"Return 'success' ONLY if all boolean columns show ✓"` and `"Return 'failure' if any issue has — in fmt/verify"`. Because `✓` is required for success, `✗` will correctly fail the evaluate verdict — but since the explicit failure condition only mentions `—`, the evaluate prompt could be clarified to also mention `✗` to prevent LLM ambiguity.

### Bug 5 — Dual Emission Architecture

The double-print comes from two independent paths in `_helpers.py` `display_progress` closure:
- **Path 1** (`_helpers.py:258–262`): `action_output` event handler — fires once per output line as the shell command streams; no `verbose` guard
- **Path 2** (`_helpers.py:284–290`): `action_complete` `output_preview` block — fires after shell completes, prints tail (8 lines non-verbose, 20 lines verbose); guarded by `not is_prompt` only

Both paths are driven by `executor.py`: `_on_line` callback emits `action_output` at line 549; `output_preview = result.output[-2000:]` is sent in `action_complete` at lines 559–567.

The correct fix mirrors `info.py:88` (history display): gate `action_output` on `verbose`, and suppress `output_preview` when `verbose=True`. This produces exactly-once output in both modes:
- **Non-verbose**: `output_preview` tail shown after completion (up to 8 lines)
- **Verbose**: streaming lines shown via `action_output`; `output_preview` suppressed

### Regression Test Pattern (Bug 5)

Model the new test after `TestDisplayProgressEvents` in `test_ll_loop_display.py:858–924`:
```python
def test_verbose_shell_output_printed_once(self, capsys):
    """In verbose mode, shell action output appears exactly once."""
    events = [
        {"event": "action_output", "line": "  fmt  | verify"},
        {"event": "action_output", "line": "   ✓   |   ✓  "},
        {"event": "action_complete", "exit_code": 0, "duration_ms": 100,
         "output_preview": "  fmt  | verify\n   ✓   |   ✓  ", "is_prompt": False},
    ]
    executor = MockExecutor(events)
    run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
    out = capsys.readouterr().out
    # Count occurrences of a distinctive line
    assert out.count("fmt") == 1
```

## Session Log

- `/ll:capture-issue` - 2026-03-05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5ab8beb-daac-4b0a-bbba-56295f1d683b.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/605b9148-691d-487e-9661-b1d6c6c35f7b.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:refine-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc2e2b2-799c-46fe-a53f-709ef6712993.jsonl`
- `/ll:ready-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e23a3407-5485-4fd8-b07d-89ff0ab68583.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5d13788-6974-4244-a10b-8a4718c5ecd1.jsonl`

---

## Resolution

**Fixed** on 2026-03-05.

- **Bug 1**: Updated `loops/issue-refinement.yaml` fix prompt Step A to treat `—`, `✗`, and absent as incomplete for `fmt`, `verify`, and `map` columns
- **Bug 2**: Added ceiling-acceptance rule to Step C: after 5 refinements with `readiness>=85`, issue treated as refined-to-ceiling and loop moves on
- **Bug 3**: Changed fix prompt issue selection from "highest Issue ID" to "highest-priority issue (lowest P number first, then highest ID as tiebreaker)"
- **Bug 4**: Changed `on_error: fix` → `on_error: evaluate` in the evaluate state; also clarified failure condition to mention both `—` and `✗`
- **Bug 5**: Gated `action_output` event handler on `verbose=True`; suppressed `output_preview` in verbose mode — net effect: exactly-once output in both modes; added two regression tests to `test_ll_loop_display.py`

## Session Log

- `/ll:capture-issue` - 2026-03-05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5ab8beb-daac-4b0a-bbba-56295f1d683b.jsonl`
- `/ll:format-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/605b9148-691d-487e-9661-b1d6c6c35f7b.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:refine-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dc2e2b2-799c-46fe-a53f-709ef6712993.jsonl`
- `/ll:ready-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e23a3407-5485-4fd8-b07d-89ff0ab68583.jsonl`
- `/ll:confidence-check` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5d13788-6974-4244-a10b-8a4718c5ecd1.jsonl`
- `/ll:manage-issue` - 2026-03-05T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4d5ce6a1-7c0e-4bf1-8804-4441c82e69cd.jsonl`

---

## Status

**Completed** | Created: 2026-03-05 | Closed: 2026-03-05 | Priority: P2
