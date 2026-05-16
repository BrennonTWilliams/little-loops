---
captured_at: '2026-05-10T14:25:47Z'
completed_at: '2026-05-16T08:46:10Z'
discovered_date: '2026-05-10'
discovered_by: capture-issue
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
status: done
---

# BUG-1414: ll-loop run --worktree flag silently dropped with --background

## Problem

When `ll-loop run` is invoked with both `--worktree` and `--background`, the `--worktree` flag is silently lost. The loop runs in the background without an isolated git worktree — no error, no warning. The user gets background execution but no worktree isolation, which may corrupt shared state.

## Root Cause

`run_background()` in `scripts/little_loops/cli/loop/_helpers.py` re-execs the process with a reconstructed argv, but has no line to forward `--worktree`. The worktree block in `cmd_run()` (`run.py`, lines 289–331) is only reachable after the background branch exits early (lines 198–199 check `args.background` first), so the re-spawned child never reaches the worktree setup.

**Anchor:** `run_background` in `scripts/little_loops/cli/loop/_helpers.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Argv reconstruction block**: `scripts/little_loops/cli/loop/_helpers.py:269-322` inside `run_background()`. Forwarding lines for flags live at lines 283–313. The block forwards: `--max-iterations`, `--no-llm`, `--llm-model`, `--verbose`, `--show-diagrams`, `--quiet`, `--queue`, `--context` (repeatable), `--program-md`, `--delay`, `--handoff-threshold`, `--context-limit`. **Missing from this list: `--worktree` AND `--builtin`** (both `action="store_true"` flags on the `run` subparser).
- **Established boolean-flag forwarding pattern** (mirror this when forwarding `--worktree`):
  ```python
  if getattr(args, "verbose", False):
      cmd.append("--verbose")
  ```
- **Argparse definitions**: `--background` at `scripts/little_loops/cli/loop/__init__.py:118-120`, `--worktree` at lines 166–173, `--foreground-internal` (internal injected flag that replaces `--background` in the child) at lines 121–125. No `add_mutually_exclusive_group()` is currently declared on the `run` subparser.
- **`cmd_run()` branch order** (`scripts/little_loops/cli/loop/run.py:88-362`): dry-run → context-var check → background dispatch at lines 197–199 (`return run_background(...)` — hard exit, worktree block unreachable) → PID file → scope lock → worktree block at lines 288–331 → executor.
- **Worktree branch mechanics** (lines 288–331): calls `setup_worktree()` from `scripts/little_loops/worktree_utils.py`, registers `cleanup_worktree()` via `atexit`, sets `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`, then `os.chdir(_worktree_path)`. Nothing in this sequence requires a live terminal — it works fine inside a detached `Popen` child. Forwarding `--worktree` is structurally safe.
- **Direct precedents for this exact bug-class** (single-line fix to `run_background()` argv forwarding):
  - `P4-BUG-621-run-background-drops-verbose-flag.md` — fixed by adding `if getattr(args, "verbose", False): cmd.append("--verbose")`.
  - `P2-BUG-1308-ll-loop-background-mode-drops-positional-input-arg.md` — fixed by appending the positional input value before `--foreground-internal`.

## Expected Behavior

`ll-loop run my-loop --worktree --background` should either:
1. Create an isolated worktree and run the loop inside it in the background (preferred), or
2. Raise an explicit error: `--worktree and --background cannot be combined`

## Steps to Reproduce

```bash
ll-loop run my-loop --worktree --background
# Observe: runs in background, no worktree created, no error
```

## Impact

Silent data hazard: users who combine these flags for isolation + non-blocking execution get neither the isolation nor an error. The background child writes to the main working tree.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()`, lines 283–313: add a `--worktree` forwarding block following the established boolean-flag pattern (and, while in scope, the missing `--builtin` flag has the same defect — flag it for follow-up but resist scope creep here).
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`, lines 197–199 (background branch): if Option B is chosen, add a pre-dispatch validation that rejects `--worktree + --background` via `raise SystemExit("--worktree and --background cannot be combined")` (matches the pattern at `run.py:149,159`).

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/loop/lifecycle.py:13-18` — `cmd_resume` also calls `run_background()` when resuming in background mode; any fix must respect resume semantics (resume may want to inherit worktree from the originating run's `.running/<instance_id>` state — confirm or document).

### Similar Patterns

- `scripts/little_loops/cli/loop/_helpers.py:292-293` — boolean flag forwarding pattern to mirror:
  ```python
  if getattr(args, "verbose", False):
      cmd.append("--verbose")
  ```
- `scripts/little_loops/cli/loop/run.py:149,159` — `raise SystemExit("...")` pattern for in-handler validation errors (use this for Option B, not `argparse.ArgumentTypeError`).
- `scripts/little_loops/cli/history.py:97` & `scripts/little_loops/cli/logs.py:329` — `add_mutually_exclusive_group()` pattern (declarative argparse-level rejection) if Option B is preferred and the rejection should happen at parse time.
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()` / `cleanup_worktree()` (shared util the worktree branch delegates to; no changes needed).

### Tests

- `scripts/tests/test_cli_loop_background.py` — `TestRunBackground` class: add a test following the per-flag pattern (e.g., `test_forwards_worktree` / `test_worktree_not_forwarded_when_false`). The class already covers `--verbose`, `--quiet`, `--queue`, etc.; the per-flag test idiom is at lines 272 and 296.
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWorktree._make_args()` at line 562: extend the fixture so `background=True` is testable alongside `worktree=True`, then add an end-to-end test covering the combined flag case.
- For Option B: add a CLI-level test that asserts `SystemExit` (or non-zero exit) when both flags are passed — model on `test_issue_history_cli.py::test_main_history_analyze_compare_and_since_mutually_exclusive` (line 456).

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_lifecycle.py` — `TestCmdResumeBackground` (lines 591–638): verify resume path still passes after any changes to `run_background()` — the resume `args` namespace has no `worktree` attribute; `getattr(args, "worktree", False)` safely returns `False`, so no resume-side changes are needed. [Agent 2 finding]

### Configuration

- None — this is a pure CLI argv-forwarding / validation fix.

### Documentation

- `docs/reference/CLI.md` — `--worktree` description (line 323) and `--background` description (lines 314, 389): if Option B is chosen, document the incompatibility. If Option A is chosen, add a one-line note that the combination is supported.
- `docs/guides/LOOPS_GUIDE.md` — references both flags; check whether the worktree section needs a "works with --background" mention.

_Wiring pass added by `/ll:wire-issue`:_
- `docs/generalized-fsm-loop.md` — "Run Flags" table (line 1490): `--background` appears as an example but `--worktree` is entirely absent. Under Option B, add a note that `--background` and `--worktree` are mutually exclusive. Under Option A, add a one-line note that the combination is supported. [Agent 2 finding]

## Implementation Steps

This bug has **two distinct implementation options**. Pick one with `/ll:decide-issue`.

### Option A — Forward `--worktree` through to the background child (preferred)

Restores the user's stated intent: isolated worktree + non-blocking execution.

1. In `scripts/little_loops/cli/loop/_helpers.py`, inside `run_background()`'s argv-reconstruction block (between lines 283 and 313), add:
   ```python
   if getattr(args, "worktree", False):
       cmd.append("--worktree")
   ```
   Place it adjacent to the other boolean-flag forwards (e.g., right after the `--queue` block at line 297) to match style.
2. The child re-execs into `cmd_run()` with `--foreground-internal` and `--worktree`, hits the worktree branch at `run.py:288-331`, and runs inside the worktree. `atexit`-registered `cleanup_worktree()` will run when the child exits.
3. Verify the `os.chdir()` at `run.py:331` does not break PID-file resolution at `run.py:201-220` (PID file path is computed before chdir — confirm by tracing variable capture; if it's captured pre-chdir, no change needed).
4. Add `test_forwards_worktree` and `test_worktree_not_forwarded_when_false` to `TestRunBackground` in `scripts/tests/test_cli_loop_background.py` (mirror the `--verbose` tests at lines 272/296).
5. Run `python -m pytest scripts/tests/test_cli_loop_background.py scripts/tests/test_cli_loop_worktree.py -v`.

### Option B — Reject the combination explicitly

> **Selected:** Option B — Reject the combination explicitly — lower implementation risk (exact `raise SystemExit` pattern at `run.py:149,159`); combined-flag support can be revisited with dedicated e2e tests.

Simpler; avoids any background+worktree interaction questions (e.g., PID file under worktree path, cleanup races).

1. In `scripts/little_loops/cli/loop/run.py`, near the top of `cmd_run()` (before the background dispatch at line 197), add:
   ```python
   if getattr(args, "background", False) and getattr(args, "worktree", False):
       raise SystemExit("--worktree and --background cannot be combined")
   ```
2. Use `raise SystemExit(...)` (not `argparse.ArgumentTypeError`) to match the existing in-handler validation pattern at `run.py:149,159`.
3. Alternatively, declare the conflict at parse time in `scripts/little_loops/cli/loop/__init__.py` near the `run` subparser (lines 118 & 167) — but argparse `add_mutually_exclusive_group()` is awkward when the flags are added separately; the in-handler form is cleaner here.
4. Add a CLI test asserting `SystemExit` for the combination (model on `test_main_history_analyze_compare_and_since_mutually_exclusive` at `scripts/tests/test_issue_history_cli.py:456`).
5. Update `docs/reference/CLI.md` to document the incompatibility.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- **Option A only**: Use `getattr(args, "worktree", False)` (not `args.worktree`) in the new forwarding line in `run_background()`. All 18 existing `TestRunBackground` tests in `test_cli_loop_background.py` (lines 132–541) build minimal `argparse.Namespace` objects without a `worktree` key — accessing `args.worktree` directly would raise `AttributeError` in every existing test. The `getattr` pattern already used for `--verbose`, `--quiet`, etc. avoids this breakage without touching existing tests. [Agent 3 finding]
- **Both options**: Run `scripts/tests/test_cli_loop_lifecycle.py::TestCmdResumeBackground` after changes to confirm the resume path is unaffected (expected: all pass with no changes needed, since `getattr(args, "worktree", False)` returns `False` for the resume namespace). [Agent 1/2 finding]
- **Option B only**: Update `docs/generalized-fsm-loop.md` flag table (line 1490) to note that `--background` and `--worktree` are mutually exclusive. [Agent 2 finding]

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-16.

**Selected**: Option B — Reject the combination explicitly

**Reasoning**: Option B maps directly onto two existing guards in `cmd_run()` at `run.py:149` and `run.py:159` — same function, same `raise SystemExit(str)` form, same `getattr(args, ...)` accessor pattern — earning negligible implementation risk (3/3). Option A is structurally sound but earns a lower risk score (2/3) because no existing test covers the combined `foreground_internal=True + worktree=True` child-execution path end-to-end. Though Option A was marked "preferred" in the issue, combined-flag support can be revisited once dedicated end-to-end test infrastructure exists.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option B | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: Five existing `getattr(args, "flag", False): cmd.append("--flag")` precedents in `_helpers.py:283–313`; two prior bugs (BUG-621, BUG-1308) fixed by the same pattern; PID file capture verified safe pre-chdir. Gap: no e2e test for combined background+worktree child path.
- **Option B**: `raise SystemExit(str)` used at `run.py:149,159` in the exact same function; `pytest.raises(SystemExit)` test pattern at `test_cli_loop_lifecycle.py:870–874`; no unknowns.

## Related

- `scripts/little_loops/cli/loop/_helpers.py` — `run_background()` (lines 247-327)
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`, lines 197–199 (background branch) and 288–331 (worktree branch)
- `scripts/little_loops/cli/loop/__init__.py` — argparse defs at lines 118–120 (`--background`), 166–173 (`--worktree`), 121–125 (`--foreground-internal`)
- `scripts/little_loops/cli/loop/lifecycle.py` — also calls `run_background()` (resume path)
- `scripts/little_loops/worktree_utils.py` — `setup_worktree()`, `cleanup_worktree()`
- `scripts/tests/test_cli_loop_background.py` — `TestRunBackground` (per-flag forwarding tests)
- `scripts/tests/test_cli_loop_worktree.py` — `TestCmdRunWorktree` (worktree tests, `_make_args()` fixture at line 562)
- Precedents: completed `BUG-621` (verbose flag drop), `BUG-1308` (positional input drop) — both single-line fixes to the same forwarding block.

---

## Status

Done

## Resolution

Implemented Option B — `cmd_run()` now rejects `--worktree + --background` explicitly.

- `scripts/little_loops/cli/loop/run.py`: Added a guard immediately before the background dispatch that raises `SystemExit("--worktree and --background cannot be combined")` when both flags are present. Uses the same `raise SystemExit(str)` form as the in-handler validations at `run.py:149,159`.
- `scripts/tests/test_cli_loop_worktree.py::TestCmdRunWorktree::test_worktree_and_background_rejected`: New test asserting `SystemExit` with the expected message.
- `docs/reference/CLI.md`: Documented the incompatibility on the `--worktree` row.
- `docs/generalized-fsm-loop.md`: Added `--worktree` to the Run Flags table and noted mutual exclusivity on both rows.

Tests: 140 passed across `test_cli_loop_background.py`, `test_cli_loop_worktree.py`, and `test_cli_loop_lifecycle.py`. Lint: `ruff check` clean on changed files.

## Session Log
- `/ll:manage-issue` - 2026-05-16T08:46:10Z - resolved BUG-1414 via Option B (reject combination)
- `/ll:ready-issue` - 2026-05-16T08:43:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/483764c9-968a-44ac-a956-3d21ad4ead9d.jsonl`
- `/ll:confidence-check` - 2026-05-16T11:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2aefac76-cd75-4383-bbd3-8354fcb522d7.jsonl`
- `/ll:decide-issue` - 2026-05-16T08:40:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/65b4feb8-201a-4cef-bda2-c36551a00016.jsonl`
- `/ll:confidence-check` - 2026-05-16T09:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6116d8f-9414-4607-9c5b-1253f33e88a0.jsonl`
- `/ll:wire-issue` - 2026-05-16T08:32:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ff8003a8-80d8-4987-90ea-fde3f3f9f722.jsonl`
- `/ll:refine-issue` - 2026-05-16T08:26:19 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/db8d2309-72fd-4aa7-a317-fc82ee72c48f.jsonl`
- `/ll:capture-issue` - 2026-05-10T14:25:47Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7b252132-81fd-48fa-abf4-43fc7a785312.jsonl`
