---
id: ENH-1254
priority: P3

discovered_date: "2026-04-22"
discovered_by: issue-size-review
size: Small
decision_needed: false
confidence_score: 100
outcome_confidence: 93
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 25
completed_at: 2026-04-22T20:27:41Z
parent: ENH-1248
status: done
---

# ENH-1254: worktree-health.yaml Grep Fix + cmd_run(worktree=True) Integration Test

## Summary

Two always-applicable fixes that require no design decision: (1) replace the broken grep in `worktree-health.yaml:14` so the built-in loop reports real orphan counts instead of always 0, and (2) add an integration test for the `cmd_run(worktree=True)` code path in `run.py:201-243` which currently has 0% coverage.

## Parent Issue

Decomposed from ENH-1248: ll-loop Worktree Orphan Scan Coverage + worktree-health.yaml Fix

## Current Behavior

- `worktree-health.yaml:14` greps for `ll-worktree` which matches no actual worktree name → always reports 0 orphaned worktrees.
- `run.py:201-243` (the `worktree=True` branch of `cmd_run`) has no integration test.

## Expected Behavior

1. `worktree-health.yaml` reports the actual count of non-main worktrees using `git worktree list --porcelain`.
2. `cmd_run(worktree=True)` has at least one integration test asserting atexit registration and worktree name format.

## Proposed Solution

### worktree-health.yaml

Replace the broken grep action at line 14 with:

```yaml
action: |
  ORPHANED=$(git worktree list --porcelain 2>/dev/null | grep "^worktree " | tail -n +2 | wc -l | tr -d ' ' || echo 0)
  echo "$ORPHANED"
```

The `tail -n +2` skip is essential — `git worktree list --porcelain` lists the main repo as the first `worktree` entry; skipping it avoids counting the main checkout as an orphan.

### cmd_run(worktree=True) integration test

In `scripts/tests/test_cli_loop_worktree.py`, add a test class modeled on `test_cli_loop_lifecycle.py:715-764`:

- Construct `args` with `args.worktree = True`, `args.dry_run = True`, and all required `Namespace` fields
- Patch `atexit.register` via `patch("little_loops.cli.loop.run.atexit.register", side_effect=registered.append)`
- Assert exactly one atexit handler was registered (`_cleanup_worktree_on_exit`)
- Assert the worktree path name matches `r"^\d{8}-\d{6}-"` (timestamp prefix pattern)

## Files to Modify

- `scripts/little_loops/loops/worktree-health.yaml:14` — replace broken grep
- `scripts/tests/test_cli_loop_worktree.py` — add `cmd_run(worktree=True)` test class
- `scripts/tests/test_builtin_loops.py` — add assertion that `worktree-health.yaml` action contains `git worktree list --porcelain` and does NOT contain `ll-worktree`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/worktree-health.yaml:14` — replace `grep -c "^worktree.*ll-worktree"` action with porcelain count
- `scripts/tests/test_cli_loop_worktree.py` — add new test class (file exists, 480 lines, 4 classes currently)
- `scripts/tests/test_builtin_loops.py` — add assertion class for `worktree-health.yaml` content

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:199-243` — worktree setup block under test; imports `setup_worktree` from `worktree_utils` at runtime
- `scripts/little_loops/worktree_utils.py` — `setup_worktree` and `cleanup_worktree` (both mocked in the integration test)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/__init__.py:368` — dispatches `cmd_run(args.loop, args, loops_dir, logger)` for the `run`/`r` subcommand; only production call site
- `scripts/tests/test_cli_loop_lifecycle.py:721,740,754,809,828,846` — calls `cmd_run()` with `dry_run=True`, `worktree` not set; these won't break from this issue

### Test Patterns to Follow
- `scripts/tests/test_cli_loop_lifecycle.py:680-764` — `TestCmdRunHandoffThreshold`: `_make_args(**kwargs)` + `_make_loop(tmp_path)` helpers
- `scripts/tests/test_cli_loop_lifecycle.py:548-561` — atexit capture via `side_effect=registered.append`
- `scripts/tests/test_builtin_loops.py:261-303` — `TestBuiltinLoopScratchIsolation`: `yaml.safe_load` + `_collect_action_text()` pattern

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py:29` (`TestBuiltinLoopFiles.test_all_parse_as_yaml`) — re-validates all YAML files after the grep fix; must remain passing (new action must be valid YAML)
- `scripts/tests/test_builtin_loops.py:36` (`TestBuiltinLoopFiles.test_all_validate_as_valid_fsm`) — re-validates all YAML files as valid FSM; must remain passing
- `scripts/tests/test_builtin_loops.py:59` (`TestBuiltinLoopFiles.test_expected_loops_exist`) — membership check only; unaffected by content change
- New: `scripts/tests/test_builtin_loops.py` — add `TestWorktreeHealthLoop` class using `_collect_action_text()` helper (see pattern at line 261); assert `git worktree list --porcelain` present and `ll-worktree` absent
- New: `scripts/tests/test_cli_loop_worktree.py:481+` — add `TestCmdRunWorktree` class; `cmd_run` must be imported **inside each test method body** (lazy import, following convention at `test_cli_loop_lifecycle.py:721`), not at module level

### Configuration
- `BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"` (test_builtin_loops.py:15)

## Similar Patterns

- `scripts/tests/test_cli_loop_lifecycle.py:715-764` — canonical `cmd_run()` test pattern
- `scripts/tests/test_cli_loop_lifecycle.py:548-561` — `atexit.register` mock pattern
- `scripts/tests/test_builtin_loops.py:261` — built-in loop content-inspection pattern

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**CRITICAL: `dry_run=True` does NOT reach the worktree block.**
`run.py:103-105` exits early (`if args.dry_run: return 0`) **before** the worktree block at line 201. The integration test must use `dry_run=False`.

**Required patches** (all needed to prevent real filesystem/git side effects):
```python
registered: list = []
with (
    patch("little_loops.cli.loop.run.setup_worktree", return_value=None),
    patch("little_loops.cli.loop.run.BRConfig") as mock_cfg,
    patch("little_loops.cli.loop.run.os.chdir"),
    patch("little_loops.cli.loop.run.atexit.register", side_effect=registered.append),
):
    mock_cfg.return_value.get_worktree_base.return_value = tmp_path / ".worktrees"
    mock_cfg.return_value.parallel.worktree_copy_files = []
    mock_cfg.return_value.cli.colors.fsm_edge_labels.to_dict.return_value = {}
    mock_cfg.return_value.cli.colors.fsm_active_state = None
    mock_cfg.return_value.loops.glyphs.to_dict.return_value = {}
    mock_cfg.return_value.commands.rate_limits.circuit_breaker_enabled = False
    mock_cfg.return_value.extensions = []
```

**Namespace fields** (from `test_cli_loop_lifecycle.py:683-704`; add `worktree=True, dry_run=False`):
```python
args = argparse.Namespace(
    input=None, context=[], max_iterations=None, delay=None,
    no_llm=False, llm_model=None, dry_run=False, background=False,
    foreground_internal=False, quiet=False, verbose=False,
    show_diagrams=False, clear=False, queue=False, handoff_threshold=None,
    worktree=True,
)
```

**atexit count correction:** `cmd_run` registers at least 2 handlers when `worktree=True, dry_run=False`: `_cleanup_pid` (line 145) and `_cleanup_worktree_on_exit` (line 240). Assert `len(registered) >= 2`, not `== 1`.

**`_make_loop` helper** (from `test_cli_loop_lifecycle.py:706-712`):
```python
loops_dir = tmp_path / ".loops"
loops_dir.mkdir()
(loops_dir / "test-loop.yaml").write_text(
    "name: test-loop\ninitial: done\nstates:\n  done:\n    terminal: true\n"
)
```

**Worktree path pattern:** `run.py:211-214` constructs `_branch_name = f"{_timestamp}-{_safe_name}"`. Assert `os.chdir` mock was called with a path whose name matches `r"^\d{8}-\d{6}-test-loop$"`.

**Exact current YAML action at line 14:**
```
ORPHANED=$(git worktree list --porcelain 2>/dev/null | grep -c "^worktree.*ll-worktree" || echo 0)
```

## Acceptance Criteria

- `worktree-health.yaml` grep produces non-zero count when worktrees exist
- `test_cli_loop_worktree.py` has a passing `cmd_run(worktree=True)` test
- `test_builtin_loops.py` asserts `ll-worktree` pattern is absent from `worktree-health.yaml`
- Regression: `python -m pytest scripts/tests/test_cli_loop_worktree.py scripts/tests/test_builtin_loops.py -v`

## Labels

`loop`, `worktree`, `reliability`, `cleanup`, `test`

## Resolution

Fixed `worktree-health.yaml:14` by replacing the broken `grep -c "^worktree.*ll-worktree"` with `git worktree list --porcelain | tail -n +2 | wc -l` to correctly count non-main worktrees. Added `TestCmdRunWorktree` integration test class to `test_cli_loop_worktree.py` covering the `worktree=True` code path in `run.py:201-243`. Added `TestWorktreeHealthLoop` to `test_builtin_loops.py` asserting the fixed grep pattern is present and the broken one is absent.

All 279 tests in `test_cli_loop_worktree.py` and `test_builtin_loops.py` pass.

## Session Log
- `/ll:manage-issue enh fix ENH-1254` - 2026-04-22T20:27:41Z
- `/ll:ready-issue` - 2026-04-22T20:22:14 - `21fe4b82-7e78-43be-96c8-169403280da0.jsonl`
- `/ll:wire-issue` - 2026-04-22T16:59:03 - `3f322d82-007d-436b-91a4-e8fd47be4ac7.jsonl`
- `/ll:refine-issue` - 2026-04-22T16:53:23 - `46ebe1e5-629b-43e5-ab61-64f4014d103c.jsonl`
- `/ll:issue-size-review` - 2026-04-22T17:00:00 - `79aadd9e-32c2-44ea-be52-e9ec9bcff212.jsonl`
- `/ll:confidence-check` - 2026-04-22T17:20:00 - `7f5ba111-1be8-4bc7-b6d6-c29345a8285a.jsonl`

---

**Open** | Created: 2026-04-22 | Priority: P3
