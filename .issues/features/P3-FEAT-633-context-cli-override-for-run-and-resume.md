---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# FEAT-633: No `--context KEY=VALUE` CLI override for runtime FSM context variables in `run`/`resume`

## Summary

The FSM schema supports a `context:` block for user-defined shared variables interpolated via `${context.key}` throughout actions and evaluators. These values are read from the YAML file at load time and cannot be overridden at runtime without editing the YAML. The `run` and `resume` subcommands have no `--context` or `--set` option.

## Location

- **File**: `scripts/little_loops/cli/loop/__init__.py`
- **Line(s)**: 94–117 (at scan commit: 12a6af0)
- **Anchor**: `in function main_loop()`, run_parser setup
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/cli/loop/__init__.py#L94-L117)

- **File**: `scripts/little_loops/cli/loop/lifecycle.py`
- **Line(s)**: 145–213 (at scan commit: 12a6af0)
- **Anchor**: `in function cmd_resume()`

## Current Behavior

```yaml
# loop.yaml
context:
  issue_id: "007"  # cannot be changed from CLI
```

To run the same loop with a different `issue_id`, the user must copy the YAML file and edit the `context` block. There is no way to inject context at runtime.

## Expected Behavior

```bash
ll-loop run myloop --context issue_id=042
ll-loop resume myloop --context issue_id=042
```

The `--context` flag overrides specific keys in `fsm.context` after loading. Multiple flags override multiple keys.

## Use Case

A developer has a `manage-issue` loop parametrized by `${context.issue_id}`. They want to run it against issues 001, 002, and 003 in sequence. With `--context`, they run:
```bash
ll-loop run manage-issue --context issue_id=001
ll-loop run manage-issue --context issue_id=002
ll-loop run manage-issue --context issue_id=003
```
Without it, they must maintain three separate YAML files or manually edit the file between runs.

## Acceptance Criteria

- `--context KEY=VALUE` is accepted by both `run` and `resume` subcommands
- Multiple `--context` flags are supported (one per key-value pair)
- Context overrides apply after loading/compiling the FSM, before execution starts
- Invalid format (missing `=`) emits a clear error
- Context keys not in the YAML's `context` block are accepted (additive)

## API/Interface

```
ll-loop run <loop> [--context KEY=VALUE ...]
ll-loop resume <loop> [--context KEY=VALUE ...]
```

```python
# run_parser addition:
run_parser.add_argument(
    "--context",
    action="append",
    metavar="KEY=VALUE",
    help="Override a context variable (can be repeated)",
)
```

## Proposed Solution

1. Add `--context KEY=VALUE` as `action="append"` to both `run` and `resume` parsers
2. After loading the FSM, merge CLI context overrides into `fsm.context`:
   ```python
   for kv in getattr(args, "context", None) or []:
       key, _, value = kv.partition("=")
       fsm.context[key.strip()] = value.strip()
   ```
3. For `resume`, load the existing FSM from the loop file and apply overrides before passing to `PersistentExecutor.resume()`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--context` to run_parser and resume_parser
- `scripts/little_loops/cli/loop/_helpers.py` — `run_foreground()` / `run_background()` to merge context overrides
- `scripts/little_loops/cli/loop/lifecycle.py` — `cmd_resume()` to apply context overrides

### Tests
- `scripts/tests/` — add tests for `--context` override in run and resume paths

### Documentation
- Docs/help text for `ll-loop run` and `ll-loop resume`

### Configuration
- N/A

## Implementation Steps

1. Add `--context` to `run` and `resume` subparsers
2. Apply overrides to `fsm.context` after loop load in `run_foreground`, `run_background`, and `cmd_resume`
3. Forward `--context` flags in `run_background` re-exec command
4. Add tests

## Impact

- **Priority**: P3 — High practical value; enables parametric loop reuse without YAML duplication
- **Effort**: Medium — Parser changes + context merge in 3 code paths + background forwarding
- **Risk**: Low — Additive; no changes to FSM execution logic itself
- **Breaking Change**: No

## Labels

`feature`, `cli`, `loop`, `fsm`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P3
