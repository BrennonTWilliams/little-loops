> **Status: Won't Do** — superseded by multi-loop parallel approach (simpler, no inter-loop coordination needed)

---
discovered_date: "2026-04-21"
discovered_by: issue-size-review
parent_issue: FEAT-1204
size: Very Large
confidence_score: 80
outcome_confidence: 93
score_complexity: 25
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1212: test_items_hash_mismatch_warning_is_prominent (resume-warning test)

## Summary

Add `test_items_hash_mismatch_warning_is_prominent` to `scripts/tests/test_parallel_runner.py`, verifying that an `items_hash` mismatch on resume surfaces at WARNING level in stdlib logging and echoes to stdout via the custom `Logger` class.

## Parent Issue

Decomposed from FEAT-1204: TestParallelRunnerSingletonSafety + items_hash Resume-Warning Test

## Use Case

**Who**: Developer completing FEAT-1075/FEAT-1174 (`ParallelRunner` + items_hash resume warning)

**Context**: `items_hash` has zero codebase presence today — this test validates behavior introduced by FEAT-1075/FEAT-1174, not existing behavior. `PersistentExecutor.resume()` at `persistence.py:504-558` currently emits no WARNING-level logs. The test ensures the resume-warning feature is wired correctly through both the stdlib logging path and the custom `Logger` → stdout path.

**Goal**: Add `test_items_hash_mismatch_warning_is_prominent` (standalone function or within `TestParallelRunnerSingletonSafety`) to `scripts/tests/test_parallel_runner.py`.

**Outcome**: `python -m pytest scripts/tests/test_parallel_runner.py -k test_items_hash_mismatch_warning_is_prominent -x` passes green.

## Proposed Solution

### Add to existing file: scripts/tests/test_parallel_runner.py

#### test_items_hash_mismatch_warning_is_prominent

Suspend a parallel state mid-run, mutate the `items` source on disk, resume. Assert:

1. Mismatch log line appears at `WARNING` level (not `DEBUG`), checked via `caplog.at_level(logging.WARNING, logger="little_loops.fsm.persistence")`
2. Log message contains both pre-suspend and post-resume hash values
3. Log message names the resume action (`"full re-run of parallel state <state>"`)
4. Warning appears in the summary printed by `ll-loop resume` at exit (captured via `capsys`)

### Implementation Notes

**Two logging systems in play — pick the right fixture for each assertion:**

- `persistence.py:43` uses **stdlib logging** (`logger = logging.getLogger(__name__)` with no `basicConfig` / handlers registered anywhere in `scripts/little_loops/`). This is where the `items_hash` WARNING record originates. → assert via `caplog.records` with `logger="little_loops.fsm.persistence"`.
- `lifecycle.py:19,282` uses the **custom `Logger` class** from `little_loops/logger.py:17-113`. `Logger.info()` (76-79), `Logger.success()` (86-89), `Logger.warning()` (91-94) call `print(..., flush=True)` to **stdout** (only `.error()` at `logger.py:96-99` goes to stderr). It is NOT loguru and NOT stdlib logging. → assert the resume-summary echo via `capsys.readouterr().out` (stdout, not stderr).
- Consequence for FEAT-1174 re-echo: for the WARNING to appear in `ll-loop resume` stdout, `lifecycle.py` (or a callback from `persistence.py.resume()`) must explicitly call the CLI `Logger.warning(...)` — stdlib `logger.warning(...)` alone will go to the stdlib "last resort" stderr handler and will NOT land in `capsys.readouterr().out`. If FEAT-1174 hasn't wired this echo, the `capsys` assertion will fail — flag as a FEAT-1174 gap rather than relaxing the test.

- **`capsys` + `caplog` in same test**: No existing test combines both fixtures. This test would be the first. Do not set `propagate=False` on the caplog logger or it will suppress the stdlib log record before caplog can capture it.
- For caplog: use **Form 2** (`caplog.at_level(logging.WARNING, logger="little_loops.fsm.persistence")` + `caplog.records` predicate) — gives level-specific scoping and structured record access. Reference: `scripts/tests/test_issue_parser.py:674-699`.
- `lifecycle.py:271` already has `logger.warning(f"Nothing to resume for: {loop_name}")` — concrete precedent for the `Logger.warning()` → stdout path that the FEAT-1174 echo should follow.

### Codebase Research Findings

- `persistence.py:504-558` `resume()` emits only `loop_resume` event via `append_event` at line 555; no WARNING logs today — items_hash check added by FEAT-1174.
- `logger.py` `Logger` class spans lines 17-113; `.info` (76-79), `.success` (86-89), `.warning` (91-94) call `print(..., flush=True)` → stdout; `.error` (96-99) → stderr.
- `lifecycle.py:282-285` `logger.success("Resumed and completed: ...")` ✓ — WARNING must surface here via `Logger.warning()`.

## Integration Map

### Files to Modify
- `scripts/tests/test_parallel_runner.py` — Add test function; file created by FEAT-1202, extended by FEAT-1203 and FEAT-1211

### Dependent Files (under test / needed first)
- `scripts/little_loops/fsm/parallel_runner.py` — Implementation under test (FEAT-1075); does NOT exist yet
- `scripts/little_loops/fsm/persistence.py:504-558` — `PersistentExecutor.resume()`; items_hash check integration point (new behavior via FEAT-1075/FEAT-1174)
- `scripts/little_loops/cli/loop/lifecycle.py:282-285` — `logger.success(...)` exit summary; WARNING must surface here via `Logger.warning()` → stdout
- `scripts/little_loops/logger.py:91-94` — `Logger.warning` → `print(..., flush=True)` to stdout
- FEAT-1174 must be complete (items_hash WARNING + stdout echo wired)
- FEAT-1202 and FEAT-1211 must be complete

### Test Infrastructure

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/conftest.py` — provides `temp_project_dir` fixture (tmp_path-backed dir with `.ll/` subfolder) and `tmp_path` (pytest built-in); use these for state-file setup in the test. No other conftest fixtures are directly relevant — `ParallelRunner` setup will need class-level fixtures defined inline (follow `class TestPersistentExecutor` in `scripts/tests/test_fsm_persistence.py:554-580` (class at 554; `simple_fsm` fixture 557-575; `tmp_loops_dir` fixture 577-580)).

### Similar Patterns (copy from)
- `scripts/tests/test_issue_parser.py:674-699` — caplog Form 2 (`logging.WARNING` + `caplog.records` predicate)
- `scripts/tests/test_ll_loop_state.py:328-408` — `test_resume_continues_running_loop` — ONLY existing test asserting `lifecycle.py:282-285` stdout via real `Logger` + `capsys.readouterr().out`; primary pattern reference
- `scripts/tests/test_logger.py:253-278,286-311` — `TestLoggerSuccess` (253-278) and `TestLoggerWarning` (286-311) `capsys`-based assertions against `Logger.success()` / `Logger.warning()`

### Tests to Run After Completion
```bash
pytest scripts/tests/test_parallel_runner.py -k test_items_hash_mismatch_warning_is_prominent
```

## Dependencies

- **FEAT-1075** must be complete (`ParallelRunner` implementation)
- **FEAT-1174** must be complete (`items_hash` resume-warning feature with `Logger.warning()` stdout echo)
- **FEAT-1202** must be complete (creates `test_parallel_runner.py`)
- **FEAT-1211** must be complete (adds `TestParallelRunnerSingletonSafety`; may be in same class)

## Acceptance Criteria

- `test_items_hash_mismatch_warning_is_prominent` passes green
- Asserts WARNING level (not DEBUG) via `caplog.records` with `logger="little_loops.fsm.persistence"`
- Asserts both pre-suspend and post-resume hash values appear in log message
- Asserts resume action name in log message
- Asserts WARNING echoed to stdout (`capsys.readouterr().out`) via `Logger.warning()`
- If FEAT-1174 omits the stdout echo, test fails and flags the gap back to FEAT-1174

## Labels

`fsm`, `parallel`, `tests`, `integration`

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-04-21_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 93/100 → HIGH CONFIDENCE

### Concerns
- All 4 dependencies are unresolved: `parallel_runner.py` does not exist, `items_hash` has zero codebase presence, `test_parallel_runner.py` does not yet exist, and `TestParallelRunnerSingletonSafety` class (FEAT-1211) is absent. This test cannot be written to pass until FEAT-1075, FEAT-1174, FEAT-1202, and FEAT-1211 are all complete.
- FEAT-1174 stdout-echo gap: `persistence.py.resume()` currently emits no WARNING-level logs and `lifecycle.py` has no `Logger.warning()` call for items_hash. If FEAT-1174 omits this echo, assertion #4 (`capsys` stdout check) will fail on delivery.

## Session Log
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5e495daf-e8c8-43ef-8911-8b0f5ec74795.jsonl`
- `/ll:refine-issue` - 2026-04-21T05:48:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6631d765-0e68-4ae1-aace-6660a853172c.jsonl`
- `/ll:confidence-check` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ee07b9c-f8db-4390-b679-840b3b16f223.jsonl`
- `/ll:wire-issue` - 2026-04-21T05:44:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/23c62886-3b1f-4c0e-ac39-b325ca81e731.jsonl`
- `/ll:refine-issue` - 2026-04-21T05:38:37 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9e9b8fde-f907-4393-a9bf-d155310a2741.jsonl`
- `/ll:issue-size-review` - 2026-04-21T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0dfd96a3-66df-4e02-b30b-139bf75f812f.jsonl`
