---
captured_at: '2026-05-23T22:10:27Z'
completed_at: '2026-05-24T19:15:38Z'
discovered_date: '2026-05-23'
discovered_by: capture-issue
status: done
confidence_score: 100
outcome_confidence: 100
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
milestone: refined-ready
---

# ENH-1646: Add remaining-count progress log to prompt-across-issues advance state

## Summary

The built-in `prompt-across-issues` loop (`scripts/little_loops/loops/prompt-across-issues.yaml`) currently logs only `Completed <issue-id>` after each iteration. For long-running invocations (e.g. processing 50+ issues), the operator has no quick signal of how many items remain without inspecting `.loops/tmp/prompt-across-issues-pending.txt` out-of-band. Add a one-line remaining-count to the `advance` state so iteration logs convey progress at a glance.

This is proposal #2 from an external audit of a run of this loop. Proposal is prompt-agnostic, additive, and low-risk (single shell command in an existing action).

## Current Behavior

`advance` state at `scripts/little_loops/loops/prompt-across-issues.yaml:84-94` removes the head line and echoes only completion:

```yaml
advance:
  action: |
    tail -n +2 .loops/tmp/prompt-across-issues-pending.txt > .loops/tmp/prompt-across-issues-pending.tmp
    mv .loops/tmp/prompt-across-issues-pending.tmp .loops/tmp/prompt-across-issues-pending.txt
    echo "Completed ${captured.current_item.output}"
  action_type: shell
  next: discover
```

Operator must `wc -l .loops/tmp/prompt-across-issues-pending.txt` in a separate shell to gauge progress.

## Expected Behavior

`advance` echoes one additional line with the remaining count, e.g.:

```
Completed P3-BUG-817
Progress: 6 items remaining
```

When the list is empty (last iteration), the line should still print `Progress: 0 items remaining` so the final iteration's log is unambiguous.

## Motivation

- **Operator UX**: Long-running loops over the issue backlog can take hours; a per-iteration progress line lets the operator estimate ETA from log timestamps without correlating against an external file.
- **Audit trail**: Logged remaining counts make post-hoc analysis of partial runs (e.g. SIGKILL mid-loop) easier — the last logged count tells you exactly where the loop was when interrupted.
- **Zero behavioral change**: This is pure observability; the FSM transitions are untouched.

## Proposed Solution

Insert a `wc -l` against the updated pending file between the `mv` and the existing `echo` in the `advance` action body:

```yaml
advance:
  action: |
    tail -n +2 .loops/tmp/prompt-across-issues-pending.txt > .loops/tmp/prompt-across-issues-pending.tmp
    mv .loops/tmp/prompt-across-issues-pending.tmp .loops/tmp/prompt-across-issues-pending.txt
    REMAINING=$(wc -l < .loops/tmp/prompt-across-issues-pending.txt | tr -d ' ')
    echo "Completed ${captured.current_item.output}"
    echo "Progress: $REMAINING items remaining"
  action_type: shell
  next: discover
```

Notes:
- `wc -l` runs after the file has been truncated, so the count reflects what's left *after* this iteration.
- `tr -d ' '` strips macOS `wc` left-padding, matching the existing convention used in the `init` state (line 38).
- `$REMAINING` is single-`$` since it's used within the same action body (matches the existing `ISSUE_ID`/`PROMPT` convention in `prepare_prompt` documented at lines 62-63).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prompt-across-issues.yaml` — `advance` state action body only

### Dependent Files (Callers/Importers)
- N/A — loop YAML is consumed by `ll-loop run`; no code imports this file

### Similar Patterns
- N/A — no other loop currently emits per-iteration progress counts; this is a new convention worth establishing for other multi-item loops (e.g. `harness-multi-item`) but out of scope here

### Tests
- N/A — no existing test exercises the `advance` echo output; manual verification via `ll-loop run prompt-across-issues "<noop-prompt> {issue_id}"` is sufficient

#### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/tests/test_builtin_loops.py:TestPromptAcrossIssuesLoop` (lines 958–1045) — structural test class for this loop that asserts on state presence and action body content; add an assertion that `advance` action body includes `REMAINING` variable and `"remaining"` echo
- Reference pattern for shell-script assertions: `scripts/tests/test_loops_recursive_refine.py:TestDequeueProgressLine` — extracts the shell snippet verbatim into a raw string constant, runs it with `subprocess.run(["bash", "-c", script], cwd=tmp_path)`, and asserts on `result.stdout`/`result.stderr`; use as template if a full execution test is warranted

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_fragments.py` — loads and validates all built-in loop YAMLs (including `prompt-across-issues.yaml`) via `load_and_validate()`; this implicit safety net will catch any YAML syntax error in the new lines without requiring test changes
- **Optional shell-execution test** (pattern from `TestDequeueProgressLine`): if a runtime-level test is warranted, create a module-level `_ADVANCE_SCRIPT` raw-string constant (verbatim copy of the `advance` action body with `${captured.current_item.output}` replaced by a literal value), set up `.loops/tmp/prompt-across-issues-pending.txt` with N lines via `tmp_path`, run with `subprocess.run(["bash", "-c", _ADVANCE_SCRIPT], cwd=tmp_path)`, and assert `"N" in result.stdout` and the pending file has one fewer line
- **Interpolation safety note**: `$REMAINING` uses no curly braces, so the FSM interpolation engine (`VARIABLE_PATTERN = re.compile(r"\$\{([^}]+)\}")`) does not match it — no `$$` prefix required (contrast with `$${COUNT}` at `init` line 39 which uses braces)

### Documentation
- N/A — the in-YAML `description` block already documents loop usage; remaining-count is self-explanatory in logs

### Configuration
- N/A

## Implementation Steps

1. Edit `scripts/little_loops/loops/prompt-across-issues.yaml` `advance` action to add the `REMAINING=...` line and the second `echo`.
2. Validate the YAML still parses: `ll-loop validate prompt-across-issues`.
3. Add a structural assertion to `scripts/tests/test_builtin_loops.py:TestPromptAcrossIssuesLoop` confirming that the `advance` action body contains `REMAINING` and `remaining` (the progress echo); follow the existing assertion style in that class.
4. Run `python -m pytest scripts/tests/test_builtin_loops.py -k TestPromptAcrossIssuesLoop -v` to confirm the new assertion passes.
5. Manual smoke-test: run the loop with a trivial prompt (e.g. `"echo touched {issue_id}"`) against a small subset and confirm logs show the new progress line.

## Impact

- **Priority**: P4 — Operator UX improvement; no functional or safety implication.
- **Effort**: Small — Two added lines in one YAML state.
- **Risk**: Low — Additive shell echo; no transition or capture changes; cross-platform-safe (`wc -l` + `tr` already used at line 38).
- **Breaking Change**: No.

## Scope Boundaries

- Out of scope: mutation verification (audit proposal #1 — wrong abstraction for a generic dispatcher; see [[feedback_eval_harness_purpose]] for why prompt-specific signals belong in the prompt, not the loop).
- Out of scope: SIGKILL retry / checkpointing (audit proposal #3 — infrastructure-level, see related issue if filed separately).
- Out of scope: commit standardization in `advance` (audit proposal #4 — bakes in `format-issue` assumptions and violates the loop's prompt-agnostic contract).
- Out of scope: porting this progress-line convention to other loops; that should be a separate enhancement after this lands.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `loops`, `observability`, `captured`

## Resolution

Added `REMAINING=$(wc -l < .loops/tmp/prompt-across-issues-pending.txt | tr -d ' ')` and `echo "Progress: $REMAINING items remaining"` to the `advance` state action body. Added `test_advance_emits_progress_count` assertion to `TestPromptAcrossIssuesLoop`. YAML validates; 14 tests pass.

## Session Log
- `/ll:ready-issue` - 2026-05-24T19:14:36 - `8839a46d-00c0-4f31-b8c8-188151579b21.jsonl`
- `/ll:ready-issue` - 2026-05-24T17:52:18 - `43b7fa3e-acf7-4526-95d7-b6317ea8e31d.jsonl`
- `/ll:wire-issue` - 2026-05-24T15:13:56 - `847e0ce1-8815-443b-b5e6-c534c63a9949.jsonl`
- `/ll:refine-issue` - 2026-05-24T15:09:19 - `f05cec5c-4ab5-4f6b-84dc-9ddd8140f4b1.jsonl`
- `/ll:format-issue` - 2026-05-23T22:12:46 - `bc1fd6ed-dcdc-4bc4-b6c1-4c76f8056fd9.jsonl`

- `/ll:confidence-check` - 2026-05-24T00:00:00Z - `f2e7bf37-f8f2-40f5-a049-b975a301f9c6.jsonl`
- `/ll:capture-issue` - 2026-05-23T22:10:27Z - `220a4517-38ba-4722-a76b-94bd2d986f30.jsonl`

---

**Open** | Created: 2026-05-23 | Priority: P4
