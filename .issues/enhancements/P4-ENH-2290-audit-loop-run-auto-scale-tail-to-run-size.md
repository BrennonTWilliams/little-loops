---
id: ENH-2290
title: audit-loop-run should auto-scale --tail to run size instead of defaulting to 200
priority: P4
type: ENH
status: open
captured_at: '2026-06-25T13:53:17Z'
discovered_date: '2026-06-25'
discovered_by: audit-loop-run
labels:
- audit-loop-run
- skills
- diagnostics
---

# ENH-2290: audit-loop-run should auto-scale --tail to run size instead of defaulting to 200

## Summary

When `/ll:audit-loop-run` runs without an explicit `--tail` argument, it silently truncates the event stream to 200 events, causing incomplete fault-signal analysis on large runs. The skill should auto-scale the event window to cover the full run size and emit a notice when truncation occurs.

## Current Behavior

`/ll:audit-loop-run` loads the event history with a hardcoded default of `--tail 200`
(Step 2: `ll-loop history <loop> [<run>] --json --tail 200`). For runs with more than
200 events this silently truncates the event stream without warning. Phase 1
fault-signal analysis and the Step 5.5 `TOOL_CALL_COUNT` operate on the truncated
partial window and report results as if they cover the full run.

## Expected Behavior

1. With no explicit `--tail`, auditing a run with more than 200 events loads
   the full event stream (or an explicitly-stated, sufficient window).
2. When the loaded window is smaller than the run's total event count, the
   audit output includes a one-line truncation notice with the loaded vs total
   counts.
3. An explicit user-supplied `--tail` still takes precedence over the
   auto-scaled default.

## Motivation

For long runs, silent truncation means the audit verdict is based on incomplete data.
Concrete example: auditing run `2026-06-25T065113-rn-implement` (89 iterations, 795
total events, 8 issues processed) with the default tail surfaced only the last ~2
issues' events. The audit's own `action_complete` count (36) was a subset of the full
run, and fault-signal coverage was incomplete. A second pass with `--tail 1000` was
required to reach ground truth.

## Proposed Solution

In Step 2, before loading history, query the run's total event/iteration count
and scale the tail accordingly rather than hard-defaulting to 200:

- Read the run's iteration/event total (e.g. from the `loop_complete` event's
  `iterations`, or `ll-loop status`/`history` metadata).
- If the user did not pass an explicit `--tail`, set the effective tail to
  cover the whole run (e.g. `max(200, total_events)` or an "all events"
  sentinel), capped at a sane ceiling.
- When truncation does occur (explicit small `--tail` on a larger run), emit a
  one-line notice in the audit output, e.g.
  `ℹ️ Loaded last N of M events — fault analysis covers a partial window.`
  so the verdict is not read as full coverage (consistent with the skill's
  existing "No silent caps" principle for loops).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **"All events" sentinel**: `--tail 0` already works — `cmd_history()` in `info.py` does `events[-tail:]` and Python `list[-0:]` returns the full list. This is a documented, tested behavior (`TestHistoryTail.test_history_tail_zero_shows_all` in `test_ll_loop_commands.py:1506`). Using `--tail 0` as the auto-scaled default is simpler than computing `max(200, total_events)`.
- **Total event count source**: `wc -l .loops/.history/<run_id>-<loop_name>/events.jsonl` gives the raw JSONL line count (= total event count). Do NOT use `loop_complete.iterations` or `LoopState.iteration` — those are FSM iteration counts, which are ~9× smaller than raw event counts (89 iterations vs. 795 events in the motivating run).
- **`ll-loop status` is not useful here**: `cmd_status()` in `lifecycle.py` reads `.running/` (live state), not `.history/` (archived). For completed runs, `ll-loop status` returns no data.
- **Skill is pure-markdown**: No Python code changes. The only edit is the `<tail_arg_or_200>` prose in `skills/audit-loop-run/SKILL.md` Step 2 (~line 95).

## Scope Boundaries

- Changes are limited to the `audit-loop-run` skill's Step 2 event-load logic
- No changes to `ll-loop history` command interface or behavior
- No changes to loop runner, FSM execution, or other `ll-loop` subcommands
- No new CLI flags or configuration settings; the existing `--tail` argument is unchanged

## Integration Map

### Files to Modify
- `skills/audit-loop-run/SKILL.md` — two change sites: (a) Step 2 (~line 95): replace `<tail_arg_or_200>` prose with auto-scaling logic + truncation-notice block; (b) frontmatter `arguments[tail].description` (~line 10): update from "Limit history events analyzed to the N most recent (default 200)" to reflect auto-scaling semantics [Wiring pass]

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/info.py` — `cmd_history()` (~line 574): applies `events[-tail:]` after loading the full JSONL; no changes needed here — `--tail 0` already works (Python `list[-0:]` = full list, documented and tested)
- `scripts/little_loops/fsm/persistence.py` — `get_archived_events()` (~line 1013): loads `events.jsonl` into memory line-by-line; archive path is `.loops/.history/<run_id>-<loop_name>/events.jsonl`
- `scripts/little_loops/loops/outer-loop-eval.yaml` — invokes `/ll:audit-loop-run ${context.input} --auto` in `generate_report` (~line 93) and `refine_analysis` (~line 117) states with no hardcoded `--tail`; passively benefits from auto-scaling (was silently truncating at 200); no changes needed [Wiring pass — Agent 1 finding]

### Similar Patterns
- `skills/debug-loop-run/SKILL.md` — Step 2 (~lines 94, 100): identical `<tail_arg_or_200>` pattern and same 200-default bug; out of scope for this issue but a natural follow-up

### Tests
- `scripts/tests/test_audit_loop_run_skill.py` — `test_skill_has_tail_argument()` (~line 66): verify `--tail` is still declared after the change; no assertion on `"200"` so survives unchanged
- `scripts/tests/test_ll_loop_commands.py` — `TestHistoryTail.test_history_tail_zero_shows_all()` (~line 1506): documents and proves `--tail 0` = all events (the "all events" sentinel this fix should use)
- `scripts/tests/test_outer_loop_eval.py` — `test_generate_report_has_llm_structured_evaluator()` (~line 123) and `test_refine_analysis_loops_to_generate_report()` (~line 133): verify outer-loop-eval states invoke audit-loop-run; not affected by prose change [Wiring pass — Agent 1 finding]

_Wiring pass added by `/ll:wire-issue`:_

New tests to write in `scripts/tests/test_audit_loop_run_skill.py` (follow pattern of `test_skill_has_tail_argument()` — read SKILL.md as text, assert on string presence):
- `test_skill_step2_uses_tail_zero_not_200()` — assert `"--tail 0"` (or `"tail_arg_or_0"`) appears in Step 2 section; assert `"--tail 200"` does NOT appear as the default call
- `test_skill_step2_derives_event_count_via_wc()` — assert `"wc -l"` and `"events.jsonl"` appear in Step 2 section (the total-event-count derivation)
- `test_skill_has_truncation_notice()` — assert truncation-notice prose (e.g. `"partial window"` or `"Loaded last"`) appears in Step 2 or adjacent step
- `test_skill_tail_description_no_longer_says_default_200()` — assert frontmatter `arguments[tail].description` does not contain `"default 200"` after the update

### Configuration
- Archive path pattern (no config change): `.loops/.history/<LATEST_RUN_ID>-<loop_name>/events.jsonl` — resolvable from LATEST_RUN_ID already extracted in Step 1

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — section `/ll:audit-loop-run`, `tail` argument entry: currently reads `Limit history events analyzed to the N most recent (default 200)` — must be updated to reflect auto-scaling semantics (e.g., "default: all events; use N to limit to N most recent") [Agent 2 finding]

## Implementation Steps

1. In the `audit-loop-run` skill's Step 2, query the run's total event count before calling `ll-loop history` (e.g. via `ll-loop status` or parsing the `loop_complete` event)
2. Derive the effective `--tail` value: if the user did not supply `--tail`, use `max(200, total_events)` or an "all events" sentinel
3. If the loaded window is smaller than the total event count, emit a one-line truncation notice in the audit output
4. Verify by re-auditing `2026-06-25T065113-rn-implement` (795 events) and confirming all events are loaded without a second pass

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — no separate event-count query needed:** The LATEST_RUN_ID resolved in Step 1 gives direct access to the archive path `.loops/.history/<LATEST_RUN_ID>-<loop_name>/events.jsonl`. Use:
```bash
wc -l .loops/.history/<LATEST_RUN_ID>-<loop_name>/events.jsonl | awk '{print $1}'
```
to get the true raw event count before calling `ll-loop history`. Do NOT use `loop_complete.iterations` or `state.json`'s `iteration` field — those are FSM pass counts (89 for the motivating run vs. 795 raw events, a ~9× difference).

**Step 2 — the "all events" sentinel is `--tail 0`:** `cmd_history()` in `info.py` slices with `events[-tail:]`; Python `list[-0:]` returns the full list. This behavior is documented and has an explicit test at `TestHistoryTail.test_history_tail_zero_shows_all()`. So when the user did not supply `--tail`, the skill can simply use `--tail 0` rather than computing `max(200, total_events)`. The total event count (`wc -l` result) is still needed in Step 3 to generate the truncation notice.

**Step 3 — truncation notice applies to user-supplied explicit `--tail` only:** When the user passes `--tail N` explicitly and `N < total_count`, emit the notice. When using the auto-scaled default (`--tail 0`), no truncation occurs and no notice is needed.

**Concrete Step 2 prose for the skill** (replacing `<tail_arg_or_200>`):
```
# If --tail was supplied by the user, use it directly; otherwise use 0 (all events)
EFFECTIVE_TAIL=<tail_arg_or_0>
TOTAL_EVENTS=$(wc -l .loops/.history/<LATEST_RUN_ID>-<loop_name>/events.jsonl | awk '{print $1}')
ll-loop history <loop_name> [<LATEST_RUN_ID>] --json --tail ${EFFECTIVE_TAIL}
# If EFFECTIVE_TAIL > 0 and EFFECTIVE_TAIL < TOTAL_EVENTS, emit truncation notice
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Update `skills/audit-loop-run/SKILL.md` frontmatter `arguments[tail].description` — change "default 200" to reflect auto-scaling semantics (e.g., "default: all events; use N to limit to N most recent")
6. Update `docs/reference/COMMANDS.md` `/ll:audit-loop-run` section — same `tail` argument description needs updating from "default 200"
7. Add 4 new tests to `scripts/tests/test_audit_loop_run_skill.py` — `test_skill_step2_uses_tail_zero_not_200`, `test_skill_step2_derives_event_count_via_wc`, `test_skill_has_truncation_notice`, `test_skill_tail_description_no_longer_says_default_200`

## Impact

- **Priority**: P4 — Diagnostic-quality improvement to the audit skill; the
  workaround (pass a larger `--tail`) is trivial once the user knows to.
- **Effort**: Small — change the default-tail derivation in the skill's Step 2
  and add a truncation-notice line.
- **Risk**: Low — skill-doc change; no code or loop changes.
- **Breaking Change**: No

## Status

**Open** | Created: 2026-06-25 | Priority: P4

## Session Log
- `/ll:wire-issue` - 2026-06-25T14:25:22 - `e65f1034-5dff-4e4e-8a88-69da0e6d888c.jsonl`
- `/ll:refine-issue` - 2026-06-25T14:17:21 - `ef18e2b4-2e0b-447e-a13e-de18997666b3.jsonl`
- `/ll:format-issue` - 2026-06-25T14:05:47 - `fb5dcf44-bdaf-4d95-85d4-261312bfa8ee.jsonl`
- `/ll:capture-issue` - 2026-06-25T13:53:17Z - `fe374318-c8a2-454a-82dd-24bd83653458.jsonl`
