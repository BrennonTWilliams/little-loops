---
id: ENH-1704
priority: P4
type: ENH
status: done
parent: ENH-1670
depends_on:
- ENH-1703
confidence_score: 100
outcome_confidence: 82
score_complexity: 22
score_test_coverage: 10
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-05-27 21:32:20+00:00
---

# ENH-1704: Foreground log capture — documentation

## Summary

Document the always-on foreground log capture introduced in ENH-1703. Foreground runs now always write to `.loops/.running/<loop-name>-<YYYYMMDDTHHMMSS>.log`; users should know where to find it and what it contains.

No config schema changes — the opt-in `capture_foreground_logs` key was dropped when the design shifted to always-on.

The implementation (`_TeeWriter` in `scripts/little_loops/cli/loop/_helpers.py`) writes both stdout and stderr to the log file with ANSI escape sequences stripped, while preserving color output to the terminal.

## Current Behavior

Three locations in `docs/` contain stale text explicitly stating that foreground runs never create a log file:

- `docs/reference/CLI.md` (line 460): `` `log_file` is `null` for foreground runs (they never write a `.log` file) `` — inside the `--json` flag description for `ll-loop status`
- `docs/reference/CLI.md` (line 464): `Log: (foreground run — output went to terminal) — no .pid file; run mode never produced a log` — the second label in the three-label `Log:` table
- `docs/guides/LOOPS_GUIDE.md` (line 1734): code comment `# Stream live output for a background run (log_file is null for foreground runs)` — inside a bash block in the monitoring section
- `docs/guides/LOOPS_GUIDE.md` (line 1741): paragraph starting with `Foreground runs send output directly to the terminal and never create a .log file — log_file is null in --json output for these runs.`

## Expected Behavior

All four stale locations updated to reflect ENH-1703 behavior: foreground runs always tee output to `.loops/.running/<instance-id>.log` (ANSI-stripped). `log_file` is now non-null for foreground runs (null only for `--foreground-internal` children or pre-ENH-1703 state files). A new Tips bullet added in `docs/guides/LOOPS_GUIDE.md` documents the always-on behavior.

## Parent Issue

Decomposed from ENH-1670: Automatic log capture parity for foreground runs

## Proposed Solution

1. **`docs/reference/CLI.md`** — Add a note under `ll-loop run` and `ll-loop resume` that foreground runs always tee stdout/stderr to `{instance_id}.log` in the running directory, with ANSI codes stripped.

2. **`docs/guides/LOOPS_GUIDE.md`** — In the monitoring/debugging section, explain that foreground run output is preserved in `{instance_id}.log` for post-hoc inspection (`tail -f`, `grep`).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Three stale locations found** (not just adding new content — existing text explicitly states the opposite of the new behavior):

**Location 1 — `docs/reference/CLI.md:460`** (`ll-loop status --json` description):
```
log_file is null for foreground runs (they never write a .log file)
```
→ Change to: `log_file` is now a path for both foreground and background runs. `null` only occurs for background-spawned child processes (`--foreground-internal`) or pre-ENH-1703 state files.

**Location 2 — `docs/reference/CLI.md:464`** (`Log:` label table, second bullet):
```
Log: (foreground run — output went to terminal) — no .pid file; run mode never produced a log
```
→ Clarify this is now the legacy fallback case only (for pre-ENH-1703 instances or `instance_id=None`). Foreground runs after ENH-1703 produce a `.log` file and display `Log: <path>` instead.

**Location 3 — `docs/guides/LOOPS_GUIDE.md:1734,1741`** ("Monitoring progress" section):
- Code comment on line 1734: `# Stream live output for a background run (log_file is null for foreground runs)` → remove the parenthetical; the command now works for both
- Paragraph on line 1741: `Foreground runs send output directly to the terminal and never create a .log file — log_file is null in --json output for these runs.` → Replace with accurate description

**Exact log path format** (from `_helpers.py:run_foreground`):
```
.loops/.running/<loop-name>-<YYYYMMDDTHHMMSS>.log
```
Example: `.loops/.running/my-scan-20260527T142301.log`

**What the log contains**: Both stdout and stderr, ANSI escape sequences stripped, written throughout the entire run (not buffered). Both streams share the same log file handle via `_TeeWriter`.

**Tips bullet** — add to `docs/guides/LOOPS_GUIDE.md:2666` (after the archival bullet):
> **Foreground runs always write a log file** to `.loops/.running/<instance-id>.log` (same path as background runs). Output is ANSI-stripped plain text; use `tail -f` or `grep` for post-hoc inspection. `ll-loop status <loop>` shows the path in the `Log:` line.

## Acceptance Criteria

- `docs/reference/CLI.md:460` `--json` description no longer says `log_file is null for foreground runs`
- `docs/reference/CLI.md:464` second `Log:` label clarified as legacy/fallback only
- `docs/guides/LOOPS_GUIDE.md:1734` comment and line 1741 paragraph updated — no longer claim foreground runs never create a log file
- `docs/guides/LOOPS_GUIDE.md` Tips section has a bullet describing always-on foreground log capture

## Integration Map

### Files to Modify
- `docs/reference/CLI.md` — stale text at lines 460 (`--json` description) and 464 (second `Log:` label bullet)
- `docs/guides/LOOPS_GUIDE.md` — stale text at lines 1734 (code comment) and 1741 (narrative paragraph); new Tips bullet at line 2666

### Implementation (read-only reference)
- `scripts/little_loops/cli/loop/_helpers.py` — `_TeeWriter` class and `run_foreground()` (tee installation, log path resolution)
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()` passes `instance_id` and `running_dir` to `run_foreground()`
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` passes `instance_id` and `running_dir`; `_format_log_label()` renders the `Log:` status line

### Tests (behavioral contract, do not modify)
- `scripts/tests/test_ll_loop_display.py` — `TestRunForegroundCapture` (5 tests documenting log file behavior)
- `scripts/tests/test_cli_loop_lifecycle.py:1103` — `test_status_foreground_run_no_pid_no_log` (legacy-fallback label regression guard)

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_enh1704_doc_wiring.py` — new test file needed; assert stale phrases are absent from `docs/reference/CLI.md` and `docs/guides/LOOPS_GUIDE.md`, and assert accurate replacement phrases are present. Follow the established doc-wiring pattern in `scripts/tests/test_enh1428_doc_wiring.py`. [Agent 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `CHANGELOG.md` — ENH-1703 feature (always-on foreground log capture via `_TeeWriter`) has no CHANGELOG entry; this doc pass is the natural place to add it under the current release section. [Agent 2 finding]

## Implementation Steps

1. **Update `docs/reference/CLI.md` line 460** — In the `ll-loop status --json` flag description, replace `log_file is null for foreground runs (they never write a .log file)` with accurate wording: `log_file` is a path for foreground and background runs alike; `null` only for background-spawned children (`--foreground-internal`) or pre-ENH-1703 state files.
2. **Update `docs/reference/CLI.md` lines 463–464** — In the three-label `Log:` table, update the second bullet to clarify it is the legacy fallback (pre-ENH-1703 or `instance_id=None` runs), not the normal foreground case. Foreground runs now hit the first branch (`Log: <path>`).
3. **Update `docs/guides/LOOPS_GUIDE.md:1734`** — Remove `(log_file is null for foreground runs)` from the `tail -f` comment; the command now applies to all run modes.
4. **Update `docs/guides/LOOPS_GUIDE.md:1741`** — Replace the paragraph sentence claiming foreground runs never create a log file with accurate text: both foreground and background runs write to `.loops/.running/<instance-id>.log`; the log is ANSI-stripped plain text.
5. **Add Tips bullet in `docs/guides/LOOPS_GUIDE.md:2666`** — After the archival bullet, add: "**Foreground runs always write a log file** to `.loops/.running/<instance-id>.log`…" (see Proposed Solution for exact wording).
6. **Verify**: `grep -n "never write" docs/reference/CLI.md docs/guides/LOOPS_GUIDE.md` should return zero matches.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. **Create `scripts/tests/test_enh1704_doc_wiring.py`** — doc-wiring regression test (follow `test_enh1428_doc_wiring.py` pattern):
   - Assert `"log_file is null for foreground runs"` is absent from `docs/reference/CLI.md`
   - Assert `"never create a .log file"` is absent from `docs/guides/LOOPS_GUIDE.md`
   - Assert `"log_file is null for foreground runs"` is absent from `docs/guides/LOOPS_GUIDE.md`
   - Assert a positive replacement phrase (e.g., `"foreground and background runs"`) is present in each doc
8. **Add CHANGELOG entry for ENH-1703** — Under the current release section, add a bullet for always-on foreground log capture via `_TeeWriter`.

## Scope Boundaries

- No changes to implementation code (`_helpers.py`, `run.py`, `lifecycle.py`)
- No config schema additions — the `capture_foreground_logs` opt-in key was dropped; no replacement key needed
- No changes to `CONFIGURATION.md` — nothing to configure
- Existing tests (`TestRunForegroundCapture`, `test_status_foreground_run_no_pid_no_log`) are read-only reference; do not modify them

## Impact

- **Priority**: P4 (low) — documentation accuracy fix; ENH-1703 shipped but docs lag
- **Effort**: Small — four targeted text replacements across two docs, one new test file, one CHANGELOG bullet
- **Risk**: Low — documentation-only changes; regression guard provided by new `test_enh1704_doc_wiring.py`
- **Breaking Change**: No

## Labels

`documentation`, `enhancement`, `loops`

## Status

**Open** | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-05-27T21:30:19 - `d76ad14b-9daf-42a1-a0e1-3f7d7a571e2a.jsonl`
- `/ll:wire-issue` - 2026-05-27T21:23:53 - `bb0eb7e3-a579-42e8-8503-8ab1e51fb567.jsonl`
- `/ll:refine-issue` - 2026-05-27T21:19:01 - `6dd079ac-525a-42b9-a559-9e8370efa495.jsonl`
- `/ll:issue-size-review` - 2026-05-25T00:00:00Z - `49c875d1-35f0-42f5-a121-41c0c7663183.jsonl`
- Design revised to always-on (dropped config schema and CONFIGURATION.md changes) - 2026-05-26
- `/ll:confidence-check` - 2026-05-27T00:00:00Z - `0274acbe-25d8-4b5b-ac18-6570e5bbdc88.jsonl`
- `/ll:ready-issue` - 2026-05-27T00:00:00 - `d76ad14b-9daf-42a1-a0e1-3f7d7a571e2a.jsonl`
