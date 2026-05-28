# BUG-1771 Implementation Plan

**Issue**: P3-BUG-1771-background-loop-scope-conflict-fails-silently
**Created**: 2026-05-28
**Status**: in_progress

## Summary

When a background loop (`-b` flag) can't start due to a scope conflict with another running loop, the parent process prints "started in background" and returns 0 before the child discovers the conflict. The child dies silently, leaving no `.state.json` — so `ll-loop status`/`monitor` see nothing.

**Fix**: Move the scope-conflict check to before the child spawn in `run_background()`.

## Phase 1: Code Changes

### 1.1 Add imports to `_helpers.py`

- Add `LockManager` import from `little_loops.fsm.concurrency` (line ~23, alongside existing `_process_alive` import from same module)

### 1.2 Add pre-flight check in `run_background()` (`_helpers.py` line ~928)

After `running_dir.mkdir(parents=True, exist_ok=True)` (line 928) and before `instance_id = _make_instance_id(loop_name)` (line 930), add:

```python
# Pre-flight scope conflict check — detect conflicts before spawning child
# so the user gets immediate feedback instead of a silent child failure.
logger = Logger.get(__name__)
try:
    fsm = load_loop(loop_name, loops_dir, logger)
except (FileNotFoundError, ValueError) as e:
    print(f"Error loading loop '{loop_name}': {e}", file=sys.stderr)
    return 1

lock_manager = LockManager(loops_dir)
scope = fsm.scope or ["."]
conflict = lock_manager.find_conflict(scope)
if conflict and not getattr(args, "queue", False):
    print(f"Scope conflict with running loop: {conflict.loop_name}", file=sys.stderr)
    print(f"  Conflicting scope: {conflict.scope}", file=sys.stderr)
    print("  Use --queue to wait for it to finish", file=sys.stderr)
    return 1
```

Key decisions:
- Uses `print(..., file=sys.stderr)` not `logger.error()` because `run_background()` has no logger (consistent with existing `print()` calls in the function)
- Matches the exact error message format from `cmd_run()` lines 316-319 for consistency
- `load_loop()` already exists at line 816 in the same file
- `Logger` already imported at line 24
- On `load_loop` failure, prints error and returns 1 (same early-exit pattern)

## Phase 2: Tests

### 2.1 File: `scripts/tests/test_cli_loop_background.py` → `TestRunBackground`

**Test 1**: `test_scope_conflict_returns_1` — pre-acquire lock, call `run_background()`, assert exit 1, assert stderr message

```python
def test_scope_conflict_returns_1(self, tmp_path, capsys):
    """Returns 1 and prints conflict message when scope is locked."""
    import argparse
    from little_loops.fsm.concurrency import LockManager

    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "my-loop.yaml").write_text("states:\n  - id: start\n    type: terminal\n")

    # Pre-acquire conflicting lock
    lm = LockManager(loops_dir)
    lm.acquire("blocker", ["."])

    args = argparse.Namespace(
        max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=False
    )

    with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 42
        from little_loops.cli.loop._helpers import run_background

        result = run_background("my-loop", args, loops_dir)

    assert result == 1
    mock_popen.assert_not_called()
    captured = capsys.readouterr()
    assert "Scope conflict" in captured.err
    assert "blocker" in captured.err
```

**Test 2**: `test_queue_bypasses_preflight_check` — pre-acquire lock, call with `queue=True`, assert spawn proceeds

```python
def test_queue_bypasses_preflight_check(self, tmp_path):
    """--queue bypasses pre-flight scope check and spawns child."""
    import argparse
    from little_loops.fsm.concurrency import LockManager

    loops_dir = tmp_path / ".loops"
    loops_dir.mkdir()
    (loops_dir / "my-loop.yaml").write_text("states:\n  - id: start\n    type: terminal\n")

    # Pre-acquire conflicting lock
    lm = LockManager(loops_dir)
    lm.acquire("blocker", ["."])

    args = argparse.Namespace(
        max_iterations=None, no_llm=False, llm_model=None, quiet=False, queue=True
    )

    with patch("little_loops.cli.loop._helpers.subprocess.Popen") as mock_popen:
        mock_popen.return_value.pid = 42
        from little_loops.cli.loop._helpers import run_background

        result = run_background("my-loop", args, loops_dir)

    assert result == 0
    mock_popen.assert_called_once()
```

### 2.2 Test validation rules

- Mock `subprocess.Popen` to avoid actual process spawn
- Use `tmp_path` fixture for isolated filesystem
- Create minimal loop YAML for `load_loop()` to succeed
- Use `LockManager.acquire()` to pre-create conflicting lock
- Use `capsys` fixture to capture stderr

## Phase 3: Integration Impact

- **`cmd_run()` (`run.py`)**: Unchanged — scope check lines 262-324 remain for foreground mode and `--queue` wait loop
- **`cmd_resume()` (`lifecycle.py`)**: Unchanged — passes through `run_background()` which now has the check
- **`LockManager.find_conflict()`**: Read-only call, no state change
- **No breaking changes**: Same error messages, same behavior for `--queue` flag

## Verification

```bash
python -m pytest scripts/tests/test_cli_loop_background.py scripts/tests/test_concurrency.py -v
ruff check scripts/little_loops/cli/loop/_helpers.py
```

## Success Criteria

- [x] Scope conflict detected before child spawn
- [x] Error message printed to stderr with conflict details
- [x] Return code 1 on conflict (not 0)
- [x] `--queue` flag bypasses pre-flight check
- [x] No `.pid` or `.log` file created for failed attempt
- [x] `load_loop` errors handled gracefully (FileNotFoundError, ValueError → stderr + return 1)
- [x] Existing tests continue to pass
