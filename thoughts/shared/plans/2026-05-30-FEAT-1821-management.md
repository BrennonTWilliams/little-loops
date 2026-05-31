# Implementation Plan: FEAT-1821 — A/B Baseline CLI Flag Wiring and Parallel Execution

**Created**: 2026-05-30
**Status**: ready

## Summary

Add `--baseline`, `--baseline-skill`, and `--items` flags to `ll-loop run`, implement parallel execution (harness arm + ungated baseline arm) via `ThreadPoolExecutor`, wire `on_usage` callback for per-arm token capture, and update all wiring touchpoints (run_background forwarding, PersistentExecutor, StateFeedRenderer, ActionRunner Protocol).

## Files to Modify

| File | Change |
|------|--------|
| `cli/loop/__init__.py` | Add `--baseline`, `--baseline-skill`, `--items` flags to run subparser |
| `cli/loop/run.py` | Consume flags in `cmd_run()`, gate `--baseline` + `--worktree` |
| `cli/loop/_helpers.py` | Forward flags in `run_background()`, handle `baseline_complete` in `StateFeedRenderer` |
| `cli/loop/lifecycle.py` | Block `--baseline` with `cmd_resume()` |
| `fsm/executor.py` | Spawn parallel arms in `_execute_state()`, pass `on_usage` through `_run_action()` |
| `fsm/runners.py` | Add `on_usage` to `ActionRunner` Protocol, `DefaultActionRunner.run()`, `SimulationActionRunner.run()` |
| `fsm/persistence.py` | Add `baseline_complete` to save-trigger list |
| `fsm/types.py` | (read-only: `UsageCallback` already exists in `subprocess_utils.py:33`) |

## Test Files to Modify/Create

| File | Change |
|------|--------|
| `tests/test_ll_loop_parsing.py` | Add flag parsing tests |
| `tests/test_cli_loop_background.py` | Add flag forwarding tests |
| `tests/test_fsm_executor.py` | Add `on_usage` parameter to ~18 mock runners; add pass-through test |
| `tests/test_fsm_persistence.py` | Add `on_usage` to ~6 mock runners; add `baseline_complete` save-trigger test |
| `tests/test_learning_state.py` | Add `on_usage=None` to `_MockRunner.run()` |
| `tests/test_state_feed_renderer.py` | Add `baseline_complete` display test |

---

## Phase 0: Write Tests (Red) — TDD Mode

### Step 0.1: CLI Flag Parsing Tests (`test_ll_loop_parsing.py`)

Add to existing `TestLoopArgumentParsing` class:

```python
def test_baseline_flag_parsed(self) -> None:
    """--baseline is parsed as True when provided."""
    args = parse_run_args(["run", "my-loop", "--baseline"])
    assert args.baseline is True

def test_baseline_default_false(self) -> None:
    """--baseline defaults to False."""
    args = parse_run_args(["run", "my-loop"])
    assert args.baseline is False

def test_baseline_skill_flag(self) -> None:
    """--baseline-skill accepts a string value."""
    args = parse_run_args(["run", "my-loop", "--baseline", "--baseline-skill", "my-skill"])
    assert args.baseline_skill == "my-skill"

def test_baseline_skill_default_none(self) -> None:
    """--baseline-skill defaults to None."""
    args = parse_run_args(["run", "my-loop"])
    assert args.baseline_skill is None

def test_items_flag(self) -> None:
    """--items accepts an integer."""
    args = parse_run_args(["run", "my-loop", "--baseline", "--items", "5"])
    assert args.items == 5

def test_items_default_none(self) -> None:
    """--items defaults to None."""
    args = parse_run_args(["run", "my-loop"])
    assert args.items is None
```

### Step 0.2: Flag Forwarding Tests (`test_cli_loop_background.py`)

```python
def test_forwards_baseline(self) -> None:
    """--baseline is forwarded to child process."""

def test_forwards_baseline_skill(self) -> None:
    """--baseline-skill VALUE is forwarded."""

def test_forwards_items(self) -> None:
    """--items N is forwarded."""

def test_baseline_not_forwarded_when_false(self) -> None:
    """--baseline is NOT forwarded when not set."""
```

### Step 0.3: Mock Runner Signature Updates (multiple test files)

Add `on_usage=None` parameter to `.run()` signatures in:
- `test_fsm_executor.py`: `MockActionRunner.run()` (line 43) + ~12 inline runners
- `test_fsm_persistence.py`: `MockActionRunner.run()` (line 610) + ~5 inline runners
- `test_learning_state.py`: `_MockRunner.run()` (line 31)

### Step 0.4: baseline_complete Tests

- `test_fsm_persistence.py`: verify `_save_state()` called for `baseline_complete` events
- `test_state_feed_renderer.py`: verify per-arm timing/tokens displayed for `baseline_complete`

---

## Phase 1: Wire CLI Flags

### Step 1.1: Add flags to run subparser (`cli/loop/__init__.py`)

After the `--worktree` flag block (line 230), add:

```python
run_parser.add_argument(
    "--baseline", action="store_true", help="Run with ungated baseline arm for comparison"
)
run_parser.add_argument(
    "--baseline-skill", type=str, default=None, metavar="SKILL",
    help="Override the auto-extracted baseline skill"
)
run_parser.add_argument(
    "--items", type=int, default=None, metavar="N",
    help="Limit sample size for baseline comparison"
)
```

### Step 1.2: Consume flags in `cmd_run()` (`cli/loop/run.py`)

After `--context` parsing (line 151), add:

```python
# Baseline mode
baseline_enabled = getattr(args, "baseline", False)
baseline_skill = getattr(args, "baseline_skill", None)
baseline_items = getattr(args, "items", None)
```

Gate: `--baseline` + `--worktree` is incompatible (both create separate execution contexts):

```python
if baseline_enabled and getattr(args, "worktree", False):
    raise SystemExit("--baseline and --worktree cannot be combined")
```

Gate: `--baseline` + `--background` is incompatible (background spawns a child, baseline needs in-process arm spawning):

Actually, re-reading: `--baseline` should work with background — the flags get forwarded. The baseline arms spawn inside the FSM executor running in the child process. So no gate needed.

Store baseline config on FSM context for the executor to consume:

```python
if baseline_enabled:
    fsm.context["_baseline"] = {
        "enabled": True,
        "skill": baseline_skill,
        "items": baseline_items,
    }
```

### Step 1.3: Gate `--baseline` incompatibility with resume (`cli/loop/lifecycle.py`)

At `cmd_resume()` (around line 443), add:

```python
if getattr(args, "baseline", False):
    logger.error("--baseline is not supported with resume. Start a fresh run with 'll-loop run'.")
    return 1
```

---

## Phase 2: Wire `on_usage` Callback

### Step 2.1: Update `ActionRunner` Protocol (`fsm/runners.py:28-53`)

Add `on_usage` parameter:

```python
def run(
    self,
    action: str,
    timeout: int,
    is_slash_command: bool,
    on_output_line: Callable[[str], None] | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
    on_usage: "UsageCallback | None" = None,  # NEW
) -> ActionResult:
```

Import `UsageCallback` from `little_loops.subprocess_utils` (or use string annotation + `from __future__ import annotations` which is already present).

### Step 2.2: Update `DefaultActionRunner.run()` (`fsm/runners.py:62`)

Add `on_usage: UsageCallback | None = None` parameter and forward to `run_claude_command()`:

```python
def run(
    self,
    action: str,
    timeout: int,
    is_slash_command: bool,
    on_output_line: Callable[[str], None] | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
    on_usage: UsageCallback | None = None,
) -> ActionResult:
```

In the slash-command branch, pass `on_usage=on_usage` to `run_claude_command()` call at line 102.

### Step 2.3: Update `SimulationActionRunner.run()` (`fsm/runners.py:191`)

Add `on_usage=None` parameter (unused, like `agent`/`tools`):

```python
def run(
    self,
    action: str,
    timeout: int,
    is_slash_command: bool,
    on_output_line: Callable[[str], None] | None = None,
    agent: str | None = None,
    tools: list[str] | None = None,
    on_usage: UsageCallback | None = None,
) -> ActionResult:
```

Add `del on_usage` alongside existing `del timeout, on_output_line, agent, tools`.

### Step 2.4: Forward `on_usage` in `FSMExecutor._run_action()` (`fsm/executor.py`)

In the `else` branch (line 1014-1022), add an `on_usage` callback that captures tokens and pass it to `self.action_runner.run()`.

In the `contributed` branch (line 1003-1013), also pass `on_usage` to contributed runners.

### Step 2.5: Forward `on_usage` in contributed action dispatch (`executor.py:1007`)

Pass `on_usage=None` (contributed runners may ignore it, same as `agent`/`tools`).

---

## Phase 3: Parallel Arm Execution

### Step 3.1: Implement parallel spawning in `FSMExecutor` (`fsm/executor.py`)

In `_execute_state()` or a new `_execute_with_baseline()` method:

```python
def _execute_with_baseline(
    self, state: StateConfig, action_template: str, ctx: InterpolationContext
) -> str | None:
    """Execute harness arm + baseline arm in parallel."""
    from concurrent.futures import ThreadPoolExecutor
    
    harness_tokens: list[tuple[int, int]] = []
    baseline_tokens: list[tuple[int, int]] = []
    harness_start = _now_ms()
    baseline_start = _now_ms()
    
    def _on_harness_usage(input_tokens: int, output_tokens: int) -> None:
        harness_tokens.append((input_tokens, output_tokens))
    
    def _on_baseline_usage(input_tokens: int, output_tokens: int) -> None:
        baseline_tokens.append((input_tokens, output_tokens))
    
    action = interpolate(action_template, ctx)
    
    # Extract baseline skill: use --baseline-skill override, or extract from action
    baseline_ctx = ctx.copy()
    baseline_skill_action = self._baseline_skill or _extract_skill_from_action(action)
    
    with ThreadPoolExecutor(max_workers=2) as pool:
        harness_future = pool.submit(
            self._run_harness_arm, state, action, ctx, _on_harness_usage
        )
        baseline_future = pool.submit(
            self._run_baseline_arm, baseline_skill_action, state, baseline_ctx, _on_baseline_usage
        )
        harness_result = harness_future.result()
        baseline_result = baseline_future.result()
    
    harness_duration = _now_ms() - harness_start
    baseline_duration = _now_ms() - baseline_start
    
    # Emit baseline_complete event
    self._emit("baseline_complete", {
        "harness_duration_ms": harness_duration,
        "baseline_duration_ms": baseline_duration,
        "harness_tokens": sum(t[0] + t[1] for t in harness_tokens),
        "baseline_tokens": sum(t[0] + t[1] for t in baseline_tokens),
    })
    
    return harness_result  # harness drives routing
```

### Step 3.2: Implement `_run_harness_arm()`

Wraps existing `_run_action()` + eval chain logic. Returns the next state name.

### Step 3.3: Implement `_run_baseline_arm()`

Single-shot invocation via `resolve_host().build_streaming()` with no eval gates. Returns `ActionResult` for data collection only.

Uses the selector-based streaming pattern from `subprocess_utils.py:277-386` (direct `Popen` with selectors, no `run_claude_command()` wrapper needed since we need the raw output for comparison, not the managed lifecycle).

Actually, it's simpler to use `self.action_runner.run()` with a baseline skill command — the `DefaultActionRunner` already handles subprocess execution. The key difference is: no eval-chain routing after the action completes.

Wait, re-reading the issue more carefully:

> **Baseline arm**: Single-shot skill invocation — call `resolve_host().build_streaming()` (`host_runner.py:233`) with the bare slash command (extracted from `execute.action`), no eval gates, no retries.

So the baseline arm should use the host CLI directly (not through `DefaultActionRunner`). But for simplicity and code reuse, using `DefaultActionRunner.run()` with the baseline skill as the action is cleaner. The "no eval gates, no retries" part is handled by returning the baseline result for data collection only — the harness arm drives the FSM routing.

Let me use `DefaultActionRunner.run()` for both arms but:
- Harness arm: drives FSM routing (the normal path)
- Baseline arm: collects timing/tokens only, result discarded for routing

This is simpler and reuses existing infrastructure. The baseline arm just calls a different slash command.

---

## Phase 4: Wiring Touchpoints

### Step 4.1: Flag forwarding in `run_background()` (`cli/loop/_helpers.py`)

After the existing flag-forwarding block (line 1055), add:

```python
if getattr(args, "baseline", False):
    cmd.append("--baseline")
baseline_skill = getattr(args, "baseline_skill", None)
if baseline_skill is not None:
    cmd.extend(["--baseline-skill", baseline_skill])
items = getattr(args, "items", None)
if items is not None:
    cmd.extend(["--items", str(items)])
```

### Step 4.2: `PersistentExecutor` event handling (`fsm/persistence.py`)

Add `"baseline_complete"` to the save-trigger list at line 616:

```python
if event_type in ("state_enter", "loop_complete", "baseline_complete"):
    self._save_state()
```

### Step 4.3: `StateFeedRenderer` progress display (`cli/loop/_helpers.py`)

Add a `baseline_complete` branch in `handle_event()`:

```python
elif event_type == "baseline_complete":
    h_ms = event.get("harness_duration_ms", 0)
    b_ms = event.get("baseline_duration_ms", 0)
    h_tok = event.get("harness_tokens", 0)
    b_tok = event.get("baseline_tokens", 0)
    status = (
        f"  {indent}baseline: {b_ms/1000:.1f}s, {b_tok} tokens  |  "
        f"harness: {h_ms/1000:.1f}s, {h_tok} tokens"
    )
    print(status)
```

---

## Phase 5: Test Fixes

### Step 5.1: Update mock runners in test files

All mock `.run()` methods need `on_usage=None` added:
- `test_fsm_executor.py`: grep for `def run(self, action` and add parameter
- `test_fsm_persistence.py`: same
- `test_learning_state.py`: same

### Step 5.2: Run all tests to verify no regressions

```bash
python -m pytest scripts/tests/test_fsm_executor.py scripts/tests/test_fsm_persistence.py scripts/tests/test_learning_state.py scripts/tests/test_ll_loop_parsing.py scripts/tests/test_cli_loop_background.py scripts/tests/test_state_feed_renderer.py -v
```

---

## Implementation Order

1. Tests first (TDD Red phase): add flag parsing tests, baseline_complete tests
2. Wire CLI flags (`__init__.py`, `run.py`, `lifecycle.py`, `_helpers.py`)
3. Update `ActionRunner` Protocol + `DefaultActionRunner` + `SimulationActionRunner` (`runners.py`)
4. Forward `on_usage` in `FSMExecutor._run_action()` (`executor.py`)
5. Implement parallel arm execution in `FSMExecutor` (`executor.py`)
6. Wire `PersistentExecutor` + `StateFeedRenderer` (`persistence.py`, `_helpers.py`)
7. Update all mock runners in tests (signature changes)
8. Run full test suite, fix any regressions
9. Verify acceptance criteria
