---
discovered_date: 2026-04-12
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 70
---

# BUG-1054: Logger color state not wired to configure_output — ANSI leaks to piped output

## Summary

`ll-auto`, `ll-parallel`, and `ll-sprint` call `configure_output(config.cli)` at startup to establish the correct color state in `output.py` (`_USE_COLOR`). However, the `Logger` class used for all timestamped progress output computes its own independent `use_color` value and never syncs with what `configure_output()` decided. This creates two observable bugs: Logger emits ANSI escape codes to piped/non-TTY output (where `colorize()` correctly suppresses them), and Logger ignores `config.cli.color = false` so users cannot disable Logger colors via config. A related code quality issue in `orchestrator.py` manually replicates `Logger.debug()` logic with a raw `print()`, and the sprint signal handler uses bare `print()` instead of the Logger instance.

## Motivation

This bug causes two user-visible failures:
- `ll-auto 2>&1 | cat` and any piped usage emits raw ANSI escape codes, making output unparseable in CI log processors, grep pipelines, and terminal multiplexers
- `config.cli.color = false` silently fails to suppress Logger output — users who explicitly opt out of color still see it, which is a broken contract

Secondary: a 6-line manual `print()` block in `orchestrator.py` duplicates `Logger.debug()` logic, meaning any future change to Logger formatting must be applied in two places.

## Context

Identified from implementation plan `~/.claude/plans/sharded-mapping-sky.md` authored during a debugging session on CLI output styling.

**Direct mode**: Plan analysis — two confirmed bugs and two cleanup items across `output.py`, `logger.py`, `issue_manager.py`, `orchestrator.py`, and `sprint/run.py`.

## Root Cause

**File**: `scripts/little_loops/logger.py:54`
**Function**: `Logger.__init__` default parameter for `use_color`

```python
# Current — Logger computes color state independently
use_color = os.environ.get("NO_COLOR", "") == ""
```

`Logger.__init__` defaults `use_color` by checking only `NO_COLOR`. It does not:
- Check `sys.stdout.isatty()` (so ANSI codes reach piped output)
- Consult `_USE_COLOR` from `output.py` (so `config.cli.color = false` is ignored)

Four Logger construction sites use the default, so none inherit the finalized color state from `configure_output()`: `issue_manager.py:782`, `orchestrator.py:83`, `sprint/run.py:93`, and `cli/parallel.py:155` (immediately after `configure_output()` at `parallel.py:153`).

Secondary: `orchestrator.py:670–676` manually replicates `Logger.debug()` with a 6-line `print()` block instead of calling `self.logger.debug(status)`. The sprint signal handler (`sprint/run.py:38,41`) uses bare `print()` and cannot be wired to Logger because the handler is registered before `logger` is constructed.

## Expected Behavior

- `ll-auto 2>&1 | cat` produces zero ANSI escape codes in output
- Setting `config.cli.color = false` suppresses all color in Logger output as it does in `colorize()`
- `orchestrator.py` uses `self.logger.debug(status)` instead of a manual print block
- Sprint signal handler uses the Logger instance when available, falling back to `print()` only before Logger is created

## Current Behavior

- `ll-auto --dry-run 2>&1 | cat | grep -P '\033\['` matches — ANSI codes leak to piped output
- `config.cli.color = false` suppresses `colorize()` output but not Logger output
- `orchestrator.py:670–676` contains a 6-line manual color check duplicating `Logger.debug()`
- Sprint signal handler always uses `print()` regardless of whether Logger is available

## Steps to Reproduce

```bash
# Reproduce ANSI leak to piped output
ll-auto --dry-run 2>&1 | cat | grep -P '\033\[' && echo "FAIL: ANSI leaked" || echo "PASS: no ANSI"
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/output.py` — add `use_color_enabled()` accessor after `configure_output()` (after line 87, before `def colorize`)
- `scripts/little_loops/logger.py:53-54` — fix default `use_color` in `Logger.__init__` to check `isatty()`
- `scripts/little_loops/issue_manager.py:782` — wire Logger; add import `from little_loops.cli.output import use_color_enabled`
- `scripts/little_loops/parallel/orchestrator.py:83,670–676` — wire Logger; replace 6-line manual print block with `self.logger.debug(status)`
- `scripts/little_loops/cli/sprint/run.py:93,38,41` — wire Logger; fix signal handler pattern
- `scripts/little_loops/cli/parallel.py:155` — wire Logger (4th site, constructed immediately after `configure_output()` at line 153; missed in original issue)

### Dependent Files (Callers/Importers)

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/parallel.py:153-155` — calls `configure_output(config.cli)` then `Logger(verbose=args.verbose or not args.quiet)` — **must be wired**
- `scripts/little_loops/cli/loop/__init__.py:364` — `Logger(verbose=...)` after `configure_output()` — out of scope (ll-loop not named in issue, but same pattern applies)
- `scripts/little_loops/cli/sprint/create.py:14`, `show.py:156`, `manage.py:57,72`, `edit.py:18` — bare `Logger()` calls in sprint subcommands — `configure_output()` fires in `sprint/__init__.py:218` before these, but these are interactive commands not automation tools
- `scripts/little_loops/parallel/orchestrator.py:671` — external code reads `self.logger.use_color` directly (the manual print block at lines 670-676)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/_helpers.py:349` — `Logger()` construction with no `use_color`; auto-fixed when Step 2 adds `isatty()` to default (informational, no explicit wiring needed)
- `scripts/little_loops/cli/gitignore.py:44` — `Logger(verbose=not args.quiet)` with no `use_color`; auto-fixed by Step 2 (informational)
- `scripts/little_loops/cli/messages.py:133` — `Logger(verbose=...)` with no `use_color`; auto-fixed by Step 2 (informational)
- `scripts/little_loops/cli/sync.py:116` — `Logger(verbose=...)` with no `use_color`; auto-fixed by Step 2 (informational)
- `scripts/little_loops/cli/sprint/__init__.py:18,38` — re-exports `_sprint_signal_handler` from `sprint/run.py`; no wiring change needed, but confirms the signal handler is surface-visible outside the module
- `scripts/little_loops/cli/auto.py:69` — calls `configure_output(config.cli)` but constructs no Logger of its own; no wiring needed

### Similar Patterns

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/output.py:90-94` (`colorize`) — reads `_USE_COLOR` module-level flag directly; model for what `use_color_enabled()` will expose
- `scripts/tests/test_cli_output.py:185-215` — `configure_output()` tests use `patch("sys.stdout")` + `mock_stdout.isatty.return_value = True/False`; follow this pattern for new Logger isatty tests
- `scripts/tests/test_logger.py:671-703` — `NO_COLOR` env var tests using `patch.dict("os.environ", {"NO_COLOR": "1"})`; new isatty test should follow same fixture structure

### Tests
- `scripts/tests/test_logger.py` — has `test_default_use_color_true` (line ~62) but **no test for isatty=False → use_color=False**; new test needed after Step 2 fix
- `scripts/tests/test_cli_output.py` — has full `configure_output()` coverage; new test for `use_color_enabled()` accessor needed after Step 1
- `scripts/tests/test_orchestrator.py` — should verify debug() is used instead of manual print block

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_logger.py:61-66` — **WILL BREAK** after Step 2: `test_default_use_color_true` creates `Logger()` without mocking `sys.stdout.isatty()` — after the fix adds `isatty()` to the default, this test will assert `use_color is True` but get `False` in non-TTY pytest environments. Fix: add `patch("sys.stdout.isatty", return_value=True)` inside the test's `with` block
- `scripts/tests/test_logger.py:25-27,144-151` — **WILL BREAK** after Step 2: module-level fixture `logger = Logger()` is used by `test_format_with_color_includes_ansi` which asserts `"\033[" in captured.out`. After fix, `Logger()` in non-TTY context will have `use_color=False`, emitting no ANSI codes. Fix: add `isatty=True` mock to the fixture or the specific test
- `scripts/tests/test_logger.py:674-703` — **MAY BREAK** after Step 2: all 4 `TestLoggerNoColorEnv` tests create `Logger()` within `patch.dict(os.environ, {"NO_COLOR": "1"})` but do not mock `isatty()`. The `use_color=False` assertion will continue to pass (since `NO_COLOR` forces it False), but `isatty()` behavior is now mixed in. Best practice: add `patch("sys.stdout.isatty", return_value=True)` to isolate the `NO_COLOR` check as the deciding factor
- `scripts/tests/test_sprint.py:585-617` — tests `_sprint_signal_handler` directly (lines 588–617). After Step 5 adds the `_sprint_logger` module-level pattern, add a test that sets a mock on `sprint_run._sprint_logger` and asserts the signal handler routes output through it instead of bare `print()`
- `scripts/tests/test_issue_manager.py:727-801` — tests `AutoManager` Logger construction (`test_auto_manager_verbose_false_creates_quiet_logger` at line 727, `test_auto_manager_verbose_true_creates_verbose_logger` at line 765). These test `.verbose` only — they survive Step 3's wiring change. No update required, but consider adding `test_auto_manager_logger_use_color_wired_to_use_color_enabled` to verify the wiring

### Documentation
- `docs/reference/OUTPUT_STYLING.md` — references `Logger`, `configure_output`, `_USE_COLOR`, `use_color`; may need a note about `use_color_enabled()` accessor
- `docs/reference/API.md` — Logger and output module API contracts; update if `use_color_enabled()` is considered public API

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:2206` — currently documents `Logger.use_color` default as "Defaults to `True` unless the `NO_COLOR` environment variable is set." After Step 2, the correct wording is: "Defaults to `True` unless the `NO_COLOR` environment variable is set **or stdout is not a TTY**." Update this line when implementing Step 2
- `docs/reference/CONFIGURATION.md:527` — describes `config.cli.color` and `configure_output` behavior but does not mention that Logger construction sites also respect this flag via `use_color_enabled()`. No text is wrong today, but after Step 3 the claim is complete — add a note that Logger instances consult `use_color_enabled()` which reads the finalized color state

### Configuration
- N/A — `config.cli.color` is the affected config key (already in `config-schema.json`)

## Implementation Steps

### 1. Add `use_color_enabled()` to `output.py`

Insert after `configure_output` (after line 87, before `def colorize`):

```python
def use_color_enabled() -> bool:
    """Return the current module-level color state set by configure_output()."""
    return _USE_COLOR
```

### 2. Fix Logger's standalone default in `logger.py:54`

`sys` is already imported (line 9):

```python
# before
use_color = os.environ.get("NO_COLOR", "") == ""

# after
use_color = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""
```

### 3. Wire Logger construction sites to `use_color_enabled()`

All four execute after `configure_output()` has been called:

- **`issue_manager.py:782`** — add top-level `from little_loops.cli.output import use_color_enabled`; change `Logger(verbose=verbose)` → `Logger(verbose=verbose, use_color=use_color_enabled())`
- **`orchestrator.py:83`** — same import after line 24 (`from little_loops.logger import Logger`); change `Logger(verbose=verbose)` → `Logger(verbose=verbose, use_color=use_color_enabled())`
- **`sprint/run.py:93`** — same import after line 16; change `Logger(verbose=not args.quiet)` → `Logger(verbose=not args.quiet, use_color=use_color_enabled())`
- **`cli/parallel.py:155`** — same import after line 10 (`from little_loops.cli.output import configure_output`); change `Logger(verbose=args.verbose or not args.quiet)` → `Logger(verbose=args.verbose or not args.quiet, use_color=use_color_enabled())`

### 4. Replace manual `print()` block in `orchestrator.py:670–676`

The block in `_maybe_report_status()` (called every 5 seconds for progress reporting) is:

```python
if self.logger.use_color:
    color = self.logger.GRAY
    ts = self.logger._timestamp()
    print(f"{color}[{ts}]{self.logger.RESET} {status}", flush=True)
else:
    self.logger.info(status)
```

Replace the entire if/else with:

```python
self.logger.debug(status)
```

`Logger.debug()` at `logger.py:81-84` already uses `self.GRAY` via `_format()` which respects `self.use_color`, making the manual block redundant.

### 5. Fix sprint signal handler to use Logger when available

Add module-level `_sprint_logger: Logger | None = None` after line 26. Update `_sprint_signal_handler` (lines 38, 41) to use `_sprint_logger` when set, `print()` otherwise. After Logger construction at line 93: `global _sprint_logger; _sprint_logger = logger`. Clear at end of `_cmd_sprint_run` for test isolation: `_sprint_logger = None`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Fix `test_logger.py:61-66` (`test_default_use_color_true`) — add `patch("sys.stdout.isatty", return_value=True)` inside the test's `with` block so Step 2's `isatty()` check doesn't flip the assertion in non-TTY environments
7. Fix `test_logger.py:25-27,144-151` — the default `Logger()` fixture gets `use_color=False` in non-TTY pytest; either add `isatty=True` mock to the fixture or restrict the ANSI-presence assertion to a separate test with explicit `use_color=True`
8. Fix `test_logger.py:674-703` (`TestLoggerNoColorEnv`) — add `patch("sys.stdout.isatty", return_value=True)` to all 4 tests so the `NO_COLOR` env var remains the deciding factor, not `isatty()` leaking from the test environment
9. Update `test_sprint.py` — after adding `_sprint_logger` in Step 5, add a test that sets a mock on `sprint_run._sprint_logger` and asserts the first-signal handler routes output through it
10. Update `docs/reference/API.md:2206` — change `use_color` default description to mention `sys.stdout.isatty()` check alongside `NO_COLOR`
11. Update `docs/reference/CONFIGURATION.md:527` — add note that Logger instances also respect `config.cli.color` via `use_color_enabled()` after the fix

## Verification

```bash
# Full test suite
python -m pytest scripts/tests/ -v --tb=short

# ANSI leak regression
ll-auto --dry-run 2>&1 | cat | grep -P '\033\[' && echo "FAIL: ANSI leaked" || echo "PASS: no ANSI in piped output"

# Type check (add cli/parallel.py to the list)
python -m mypy scripts/little_loops/cli/output.py scripts/little_loops/logger.py scripts/little_loops/issue_manager.py scripts/little_loops/parallel/orchestrator.py scripts/little_loops/cli/sprint/run.py scripts/little_loops/cli/parallel.py
```

### New Tests Required

After Step 1, add to `test_cli_output.py` (follow `TestConfigureOutput` fixture pattern at line ~164):
```python
def test_use_color_enabled_reflects_configure_output_state():
    with patch.object(output_mod, "_USE_COLOR", False):
        assert output_mod.use_color_enabled() is False
    with patch.object(output_mod, "_USE_COLOR", True):
        assert output_mod.use_color_enabled() is True
```

After Step 2, add to `test_logger.py` (follow `TestLoggerInit` pattern; use `patch("sys.stdout")` as in `test_cli_output.py:191`):
```python
def test_default_use_color_false_when_not_a_tty():
    with patch("little_loops.logger.sys.stdout") as mock_stdout:
        mock_stdout.isatty.return_value = False
        log = Logger()
    assert log.use_color is False
```

## Impact

- **Priority**: P3 — ANSI leak to piped output breaks CI/toolchain usage; workaround exists (`NO_COLOR` env var)
- **Effort**: Small — 5 targeted one-to-five line changes; all file/function locations already identified
- **Risk**: Low — internal wiring only, no public API changes, no behavioral change for interactive TTY users
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/reference/API.md | Logger and output module API contracts |
| guidelines | .claude/CLAUDE.md | CLI tools and code style conventions |

## Labels

`bug`, `cli`, `output`, `logger`, `captured`

---

## Session Log
- `/ll:ready-issue` - 2026-04-12T17:21:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67b04cb6-511c-4978-bece-b16986e95e5c.jsonl`
- `/ll:confidence-check` - 2026-04-12T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ce35a85-17be-4d5a-963c-e2170d684583.jsonl`
- `/ll:wire-issue` - 2026-04-12T16:15:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/388c35ae-4c5c-4460-87fb-eccb1507565e.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:09:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc0ab9f5-bd9c-4c21-a2d2-8a159bb1ea23.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:07:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b4c3cfa-ad15-4d14-8823-28150e20d575.jsonl`
- `/ll:format-issue` - 2026-04-12T16:05:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f356deba-9948-4a09-8c17-cbf0b9c64582.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96afaf36-7dd4-49ed-8232-94d176c382a2.jsonl`

---

## Resolution

**Fixed** | Resolved: 2026-04-12 | Priority: P3

### Changes Made

1. **`scripts/little_loops/cli/output.py`** — added `use_color_enabled()` accessor after `configure_output()` to expose `_USE_COLOR` state
2. **`scripts/little_loops/logger.py:54`** — fixed default `use_color` to check `sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""`; updated docstring
3. **`scripts/little_loops/issue_manager.py`** — lazy import of `use_color_enabled`; wired Logger construction
4. **`scripts/little_loops/parallel/orchestrator.py`** — lazy import of `use_color_enabled`; wired Logger construction; replaced 6-line manual `print()` block with `self.logger.debug(status)`
5. **`scripts/little_loops/cli/sprint/run.py`** — added `use_color_enabled` import; wired Logger construction; added module-level `_sprint_logger`; updated signal handler to route through Logger when set; clear at end for test isolation
6. **`scripts/little_loops/cli/parallel.py`** — extended `output` import; wired Logger construction
7. **Tests** — fixed 2 breaking tests in `test_logger.py` (isatty mock); fixed 4 NO_COLOR tests for isolation; added `test_default_use_color_false_when_not_a_tty`; added `test_use_color_enabled_reflects_configure_output_state` in `test_cli_output.py`; added 2 sprint signal handler tests in `test_sprint.py`
8. **Docs** — updated `docs/reference/API.md` Logger `use_color` description; updated `docs/reference/CONFIGURATION.md` `cli.color` description

### Lazy Imports Note

`issue_manager.py` and `orchestrator.py` use lazy imports (`from little_loops.cli.output import use_color_enabled` inside `__init__`) to avoid a circular import cycle: `config.core` → `parallel.__init__` → `orchestrator` → `cli.__init__` → `cli.auto` → `config`. The import is safe at call time since all modules are fully initialized by then.

## Session Log
- `/ll:manage-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`
- `/ll:ready-issue` - 2026-04-12T17:21:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/67b04cb6-511c-4978-bece-b16986e95e5c.jsonl`
- `/ll:confidence-check` - 2026-04-12T17:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ce35a85-17be-4d5a-963c-e2170d684583.jsonl`
- `/ll:wire-issue` - 2026-04-12T16:15:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/388c35ae-4c5c-4460-87fb-eccb1507565e.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:09:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fc0ab9f5-bd9c-4c21-a2d2-8a159bb1ea23.jsonl`
- `/ll:refine-issue` - 2026-04-12T16:07:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3b4c3cfa-ad15-4d14-8823-28150e20d575.jsonl`
- `/ll:format-issue` - 2026-04-12T16:05:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f356deba-9948-4a09-8c17-cbf0b9c64582.jsonl`
- `/ll:capture-issue` - 2026-04-12T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96afaf36-7dd4-49ed-8232-94d176c382a2.jsonl`

---

## Status

**Completed** | Created: 2026-04-12 | Resolved: 2026-04-12 | Priority: P3
