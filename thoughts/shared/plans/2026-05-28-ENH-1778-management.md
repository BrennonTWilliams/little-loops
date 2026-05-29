# ENH-1778: Add --no-lock flag to ll-loop run

**Status**: in_progress
**Confidence**: 100/100 (gate threshold: 85)

## Summary

Add `--no-lock` CLI flag to `ll-loop run` that skips `LockManager.acquire()` and pre-flight `find_conflict()` checks. Opt-in flag for demo/recording workflows where concurrent loop execution is safe.

## Changes

### 1. `scripts/little_loops/cli/loop/__init__.py` (+3 lines)

Add `--no-lock` argument to `run` subparser near `--queue` (L197-198):

```python
run_parser.add_argument("--no-lock", action="store_true", help="Skip scope lock (for demos/recordings)")
```

### 2. `scripts/little_loops/cli/loop/_helpers.py` (+3 lines)

- **Pre-flight check gate** (L942): Add `and not getattr(args, "no_lock", False)` to the conflict conditional
- **Flag forwarding** (after L994, `--queue` forwarding): Forward `--no-lock` to child re-exec command

### 3. `scripts/little_loops/cli/loop/run.py` (+5 lines)

- **Skip acquire** (L271): Gate `lock_manager.acquire()` with `if not getattr(args, "no_lock", False)`
  - When `--no-lock`, skip the entire acquire/conflict/queue block and proceed directly
- **Skip release** (L404): Gate `lock_manager.release()` with same conditional in `finally` block

### 4. Tests

- `test_cli_loop_background.py`: 3 tests (bypass, no-lock-file, forwarding)
- `test_ll_loop_parsing.py`: 2 tests (flag parsing)
- `test_cli_loop_queue.py`: 1 test (cmd_run skip acquire/release)

## Verification

```bash
python -m pytest scripts/tests/test_cli_loop_background.py scripts/tests/test_cli_loop_queue.py scripts/tests/test_ll_loop_parsing.py -v
```
