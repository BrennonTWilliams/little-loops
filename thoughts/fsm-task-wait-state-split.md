# FSM State Model: Task States vs Wait States

FEAT-1794 (`action_type: human_approval`) exposes a crack in the current FSM model
that will widen as the harness grows more ambitious. Every state today follows the
same shape:

```
action → capture → evaluate → route
```

`action_type` selects *what runs* (shell, prompt, mcp_tool), but the pipeline is
identical. `human_approval` breaks this because the human IS the evaluator — the
verdict arrives pre-formed from outside the process. There's no action to run and
nothing to evaluate. We're jamming a different state machine primitive into a slot
designed for something else.

This isn't the last time this will happen. Future candidates: `wait_for_ci` (block
until a GitHub check completes), `wait_for_deploy` (block until a health check
passes), `human_delegate` (assign a subtask to another person and wait for their
result). All of these share the same shape: **emit a request, suspend, resume on
external signal**.

## Two fundamental state categories

### Task states (what we have today)

```
execute → capture → evaluate → route
```

These *do* something: run a shell command, call an LLM, invoke an MCP tool. They
produce output, which gets evaluated, which produces a verdict, which routes.

### Wait states (new)

```
emit event → suspend → resume on external signal → route by signal type
```

These *request* something from outside the process and block until the answer
arrives. No action, no evaluator — the signal itself carries the routing key.

## YAML shape

A wait state replaces `action_type` with `type: wait` and a `wait_for` signal type:

```yaml
check_human:
  type: wait
  wait_for: human_approval
  prompt: >
    The execute step modified 240 lines. Threshold is 50.
    Approve to continue?
  channels: [terminal, push]
  timeout: 1800
  routes:
    approve: advance
    reject: execute
    edit: re_execute
    timeout: advance
```

`timeout` is just another signal in the routes map — no separate `on_timeout` field.

And `wait_for_ci` is the same shape with a different signal:

```yaml
wait_for_checks:
  type: wait
  wait_for: github_check
  check_run_id: ${captured.pr.create.check_run_id}
  timeout: 600
  routes:
    success: deploy
    failure: notify_author
    timeout: notify_author
```

Task states keep the current shape but gain an explicit `type: task` discriminator:

```yaml
execute:
  type: task
  action_type: prompt
  action: "/ll:manage-issue ${context.issue_id}"
  evaluate: llm_structured
  on_yes: verify
  on_no: execute
```

## Runtime model: suspend-to-journal

The executor shouldn't poll. The current `_interruptible_sleep()` pattern
(`executor.py:1463`) ties up a thread doing `time.sleep(0.1)` in a loop — it works
for short waits but is wrong for a 30-minute human approval window.

The right model is to treat a wait state as a serialization point:

1. On entering a wait state, the executor writes its full state (current state
   name, captured variables, iteration count, elapsed time) to the persistence
   journal
2. It emits the request event to the event bus — transports deliver it to the
   operator via configured channels
3. The executor process **exits** (or the loop run suspends at a well-known
   checkpoint)
4. When the operator responds — via a CLI helper (`ll respond <loop-id> approve`),
   an IM adapter, or a socket message — a response event is written to the journal
5. A watcher process (or the next cron tick, or a socket listener) sees the
   response, reloads the FSM state from the journal, and resumes execution from
   the wait state, routing by the signal type

This is how Temporal, AWS Step Functions, and Camunda work. The "blocking" is an
illusion — the workflow code looks synchronous but the runtime persists and resumes.

For v1, a simpler in-process wait (using the existing `_interruptible_sleep()`
pattern) is acceptable as long as the state shape and routing model don't preclude
upgrading to suspend-to-journal later.

## Channel abstraction

Prompt delivery and response collection should be symmetric:

```python
class Channel(Protocol):
    """A channel delivers wait-state requests and collects responses."""

    def deliver(self, request: WaitRequest) -> None:
        """Send the request to the operator via this channel."""
        ...

    def collect(self, request_id: str, timeout: int) -> WaitResponse | None:
        """Block until a response arrives or timeout expires."""
        ...
```

- `TerminalChannel` — renders the prompt to stderr, reads from stdin
- `PushNotificationChannel` — sends a push, polls a lightweight HTTP endpoint
- `SlackChannel` — posts a message with buttons, listens for a reaction via RTM API

The executor doesn't care which channel is used — it calls `deliver()` then
`collect()`. Channels are discovered and wired through the existing extension
system (`extension.py`), same as contributed actions and evaluators.

## Schema split

The `StateConfig` dataclass (`schema.py:309`) currently uses `action_type: str | None`
to discriminate everything. The split replaces this with `type: Literal["task", "wait"]`:

```python
@dataclass
class StateConfig:
    name: str
    type: Literal["task", "wait"] = "task"  # default = task for backwards compat

    # Task state fields (only valid when type == "task")
    action_type: Literal["prompt", "slash_command", "shell", "mcp_tool"] | None = None
    action: str | None = None
    evaluate: str | None = None
    evaluate_config: EvaluateConfig | None = None

    # Wait state fields (only valid when type == "wait")
    wait_for: str | None = None          # signal type: human_approval, github_check, etc.
    prompt: str | None = None            # rendered to operator
    channels: list[str] | None = None    # which channels to deliver through

    # Routing (shared — wait states route by signal, task states route by verdict)
    on_yes: str | None = None
    on_no: str | None = None
    on_error: str | None = None
    # ...
```

`extra_routes` (`schema.py:389`) already catches unrecognized `on_*` keys — wait
state signal routing can use this same mechanism. A `wait_for: human_approval` with
`routes: {approve: advance, reject: execute}` stores `approve` and `reject` in
`extra_routes` and the executor resolves them by signal name at runtime.

## Executor changes

The executor dispatch in `_execute_state()` (`executor.py:772`) becomes:

```python
def _execute_state(self, state: StateConfig) -> str | None:
    if state.loop is not None:
        return self._execute_sub_loop(state, ctx)
    if state.type == "learning" and state.learning is not None:
        return self._execute_learning_state(state, ctx)
    if state.type == "wait":
        return self._execute_wait_state(state, ctx)
    # Task state — existing action → evaluate → route pipeline
    ...
```

`_execute_wait_state()`:

1. Interpolates the prompt with captured context
2. Builds a `WaitRequest` (state name, prompt, timeout, channels)
3. Emits `wait_request` event via `self._emit()`
4. Calls `channel.collect(request_id, timeout)` — blocks in-process for v1, or
   suspends to journal in v2
5. On response: captures the response data, routes by signal name via
   `state.extra_routes.get(signal, state.on_no)`
6. On timeout: routes via `state.extra_routes.get("timeout", state.on_no)`

## Why this matters beyond FEAT-1794

The current `action_type` enum is accumulating values: `prompt`, `slash_command`,
`shell`, `mcp_tool`, `human_approval`, and eventually `wait_for_ci`,
`wait_for_deploy`, `human_delegate`. Each one adds a branch in `_action_mode()`,
`_run_action()`, and `_evaluate()`. The enum is really two enums mashed together:
**how something runs** (shell, prompt, mcp) and **what kind of state this is**
(task, wait).

Splitting them means:

- **Task states** grow by adding new action runners — pluggable via
  `ActionProviderExtension`, no executor core changes
- **Wait states** grow by adding new signal types and channels — pluggable via the
  same extension model
- **Neither growth path** requires touching the executor core dispatch

## Migration path

1. **FEAT-1794 v1**: Implement `human_approval` as a hardcoded dispatch branch
   (`action_type: human_approval`) following the `mcp_tool` pattern. Ship the
   feature. Don't block on the type-split refactor.
2. **Follow-up refactor**: Introduce `type: "wait"` as an alternative to
   `action_type`. Keep `action_type` working for task states. `type` and
   `action_type` are mutually exclusive; validator enforces this.
3. **Deprecation window**: `action_type: human_approval` continues to work but
   emits a deprecation warning suggesting `type: wait` + `wait_for: human_approval`.
4. **Cleanup**: Remove the hardcoded `human_approval` branch from `_action_mode()`
   and `_run_action()`. The only wait-state dispatch is the `type == "wait"` branch
   in `_execute_state()`.
