---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 96
outcome_confidence: 79
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

## Motivation

Users who maintain parametric FSM loops — loops parameterized by `${context.key}` variables — currently must duplicate YAML files or manually edit the `context:` block between runs. This creates maintenance overhead and breaks automation pipelines that need to drive a single loop template across multiple inputs (e.g., processing a list of issue IDs). Adding `--context KEY=VALUE` as a CLI override enables parametric loop reuse without YAML duplication, unlocking use in scripts and CI/CD workflows where context values are determined at runtime.

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
- `scripts/little_loops/cli/loop/__init__.py` — add `--context` to run_parser (lines 97-117) and resume_parser (lines 150-162)
- `scripts/little_loops/cli/loop/run.py` — apply `fsm.context` overrides after the existing override block at lines 54-60
- `scripts/little_loops/cli/loop/_helpers.py` — forward `--context` flags in `run_background()` subprocess re-exec at lines 243-257
- `scripts/little_loops/cli/loop/lifecycle.py` — apply `fsm.context` overrides in `cmd_resume()` after YAML load at lines 176-183

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py` — dispatches to `cmd_run` (line 235) and `cmd_resume` (line 247)
- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor.resume()` (line 377) receives the FSM after context is merged; `PersistentExecutor.__init__` at line 254 stores `self.fsm = fsm`
- `scripts/little_loops/fsm/executor.py:753-769` — `_build_context()` wires `fsm.context` into `InterpolationContext`
- `scripts/little_loops/fsm/interpolation.py:55,78-79` — resolves `${context.key}` via `InterpolationContext.context` dict

### Similar Patterns

#### `action="append"` precedent
`scripts/little_loops/cli/docs.py:159-164`:
```python
parser.add_argument(
    "--ignore",
    action="append",
    default=[],
    help="Ignore URL patterns (can be used multiple times)",
)
```
Use `default=[]` (not omitted) so `args.context` is always a list, never `None`.

#### Existing runtime FSM override block (model for context override)
`scripts/little_loops/cli/loop/run.py:54-60`:
```python
if args.max_iterations:
    fsm.max_iterations = args.max_iterations
if args.no_llm:
    fsm.llm.enabled = False
if args.llm_model:
    fsm.llm.model = args.llm_model
```
Context override goes here (or immediately after). `fsm.context` is `dict[str, Any]` (`schema.py:365`).

#### Background subprocess forwarding pattern
`scripts/little_loops/cli/loop/_helpers.py:243-257`:
```python
if getattr(args, "verbose", False):
    cmd.append("--verbose")
if getattr(args, "queue", False):
    cmd.append("--queue")
```
For an append-style list flag, extend the same block with:
```python
for kv in getattr(args, "context", None) or []:
    cmd.extend(["--context", kv])
```

### Tests
- `scripts/tests/test_cli_loop_background.py:163-200` — background forwarding tests (pattern to follow for `--context` forwarding tests)
- `scripts/tests/test_ll_loop_parsing.py:26-79` — run subparser arg tests (pattern for `--context` parser test)
- `scripts/tests/test_cli_loop_lifecycle.py` — resume path tests (add override application test)

### Documentation
- Help text for `ll-loop run` and `ll-loop resume` (added via `add_argument` help string)

### Configuration
- N/A

## Implementation Steps

1. **Add `--context` arg to both subparsers** (`__init__.py:97-117` for run, `__init__.py:150-162` for resume):
   ```python
   run_parser.add_argument(
       "--context", action="append", default=[],
       metavar="KEY=VALUE",
       help="Override a context variable (can be repeated)",
   )
   ```
   Apply same declaration to `resume_parser`.

2. **Apply context overrides in `run` path** (`run.py:54-60`, after existing override block):
   ```python
   for kv in args.context or []:
       key, _, value = kv.partition("=")
       if not key or "=" not in kv:
           raise SystemExit(f"Invalid --context format: {kv!r} (expected KEY=VALUE)")
       fsm.context[key.strip()] = value.strip()
   ```

3. **Apply context overrides in `resume` path** (`lifecycle.py:176-183`, after `load_loop()` call):
   Same `for kv in getattr(args, "context", []) or []:` block as step 2.

4. **Forward `--context` in background re-exec** (`_helpers.py:243-257`, at end of forwarding block):
   ```python
   for kv in getattr(args, "context", None) or []:
       cmd.extend(["--context", kv])
   ```

5. **Add tests**:
   - Parser test in `test_ll_loop_parsing.py` — verify `--context a=1 --context b=2` → `["a=1", "b=2"]`
   - Forwarding test in `test_cli_loop_background.py` — follow pattern at lines 163-200
   - Override application test in `test_cli_loop_lifecycle.py` — verify `fsm.context` is mutated before executor runs
   - Error test — verify invalid format (no `=`) raises `SystemExit` with clear message

## Impact

- **Priority**: P3 — High practical value; enables parametric loop reuse without YAML duplication
- **Effort**: Medium — Parser changes + context merge in 3 code paths + background forwarding
- **Risk**: Low — Additive; no changes to FSM execution logic itself
- **Breaking Change**: No

## Labels

`feature`, `cli`, `loop`, `fsm`, `captured`

## Verification Notes

- **Verdict**: VALID — issue accurately describes current codebase state
- `scripts/little_loops/cli/loop/__init__.py` exists; run_parser at lines 92–117 has no `--context` flag
- `scripts/little_loops/cli/loop/lifecycle.py` exists; `cmd_resume()` at lines 144–213 confirmed
- `scripts/little_loops/cli/loop/_helpers.py` exists (referenced in Integration Map)
- FSM `context:` field confirmed in `scripts/little_loops/fsm/schema.py:365`
- `${context.key}` interpolation confirmed in `scripts/little_loops/fsm/interpolation.py:79`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/02f72ff7-2858-498c-8a4b-ecf11e41a43e.jsonl`
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a0da8f20-18ff-4701-aed1-d0b40ec52360.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

## Resolution

**Status**: Completed | Resolved: 2026-03-07

### Changes Made

- `scripts/little_loops/cli/loop/__init__.py` — Added `--context KEY=VALUE` (`action="append"`, `default=[]`) to both `run_parser` and `resume_parser`
- `scripts/little_loops/cli/loop/run.py` — Apply context overrides after existing override block; validates `KEY=VALUE` format with clear `SystemExit` message
- `scripts/little_loops/cli/loop/lifecycle.py` — Apply context overrides in `cmd_resume()` after `load_loop()` call
- `scripts/little_loops/cli/loop/_helpers.py` — Forward `--context` flags in `run_background()` subprocess re-exec

### Tests Added

- `scripts/tests/test_ll_loop_parsing.py` — Three parser tests: single flag, multiple flags, empty default
- `scripts/tests/test_cli_loop_background.py` — Two forwarding tests: context flags forwarded, empty context not forwarded
- `scripts/tests/test_cli_loop_lifecycle.py` — Two resume tests: overrides applied to `fsm.context`, invalid format raises `SystemExit`

### Acceptance Criteria Verification

- [x] `--context KEY=VALUE` accepted by both `run` and `resume`
- [x] Multiple `--context` flags supported (accumulate via `action="append"`)
- [x] Overrides applied after FSM load, before execution
- [x] Invalid format (missing `=`) emits clear `SystemExit` error
- [x] Context keys not in YAML accepted (additive via `fsm.context[key] = value`)

## Status

**Completed** | Created: 2026-03-07 | Resolved: 2026-03-07 | Priority: P3
