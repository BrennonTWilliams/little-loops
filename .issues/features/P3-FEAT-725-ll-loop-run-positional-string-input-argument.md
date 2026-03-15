---
discovered_date: 2026-03-13
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 82
---

# FEAT-725: ll-loop run positional string input argument

## Summary

Add support for passing a positional string input to `ll-loop run` so that loops with an `init` state can receive a runtime value without requiring `--context key=value` syntax.

Target UX:
```
ll-loop run single-issue-refinement-loop "FEAT-719"
ll-loop run single-issue-refinement-loop FEAT-719
```

## Current Behavior

- `ll-loop run <loop-name>` accepts only the loop name as a positional argument.
- Runtime values must be passed via `--context input=FEAT-719`, which is verbose and requires the user to know the context key name.
- Loop YAML authors have no convention for declaring an "expected input" to document or validate that the loop requires a runtime string.

## Expected Behavior

- `ll-loop run <loop-name> [input]` accepts an optional second positional argument.
- When provided, the input is injected into `fsm.context["input"]` (or a configurable key declared in the loop YAML) before execution begins.
- Loops can declare an `input` key in their top-level `context:` with a placeholder/default (e.g., `null` or empty string) to signal that they accept runtime input.
- The `init` state (or any state) can reference `{{context.input}}` in its action/prompt to consume the value.

### Example loop YAML

```yaml
name: single-issue-refinement-loop
initial: init
context:
  input: null   # populated at runtime via positional arg
states:
  init:
    action: "/ll:refine-issue {{context.input}}"
    on_success: done
    on_failure: done
  done:
    terminal: true
```

### Example invocation

```bash
ll-loop run single-issue-refinement-loop FEAT-719
# equivalent to:
ll-loop run single-issue-refinement-loop --context input=FEAT-719
```

## Use Cases

### Structured IDs and file paths

**Who**: A developer using `ll-loop` to run parameterized loops (e.g., single-issue refinement, file processors).

**Context**: They have a loop YAML that accepts a runtime input (e.g., an issue ID or file path) and want to invoke it from the command line without knowing or typing the internal `--context input=...` key syntax.

**Goal**: Pass a runtime value to the loop as a simple positional argument.

**Outcome**: `ll-loop run single-issue-refinement-loop FEAT-719` runs the loop with `context["input"] = "FEAT-719"`, identical to the verbose `--context input=FEAT-719` form.

### Natural language prompts

**Who**: A developer using `ll-loop` to run prompt-driven loops (e.g., research, summarization, Q&A).

**Context**: They have a loop YAML whose `init` state passes `{{context.input}}` directly into a Claude prompt. The "input" is a free-form instruction or question, not a structured ID.

**Goal**: Inline a natural language string as the loop's driving prompt without needing `--context`.

**Outcome**: `ll-loop run research-loop "What are the best practices for Python error handling?"` runs the loop with `context["input"]` set to the full question string, making prompt-driven loops feel like natural CLI tools.

Example loop YAML for this pattern:
```yaml
name: research-loop
initial: init
context:
  input: null   # natural language question, populated at runtime
states:
  init:
    action: "Research and summarize: {{context.input}}"
    on_success: done
    on_failure: done
  done:
    terminal: true
```

## Motivation

Single-item loops (refine one issue, process one file, run one check) are a natural pattern but are awkward to invoke today — users must know the internal context key name and use the verbose `--context` flag. A positional input arg makes `ll-loop` feel like a natural CLI tool and unlocks reusable parameterized loop templates.

## Implementation Steps

1. **CLI argument**: In `scripts/little_loops/cli/loop/__init__.py:94`, add `run_parser.add_argument("input", nargs="?", default=None, help="Optional input string injected as context['input']")` after the existing `loop` positional.
2. **Injection in `cmd_run`**: In `scripts/little_loops/cli/loop/run.py`, insert positional injection **before** the `for kv in getattr(args, "context", ...)` loop at line 50 — e.g., `if getattr(args, "input", None): fsm.context["input"] = args.input`. This ensures `--context input=X` can still override.
3. **Schema update**: In `scripts/little_loops/fsm/fsm-loop-schema.json`, add `"input_key": {"type": "string", "description": "Context key populated by the positional input arg (default: 'input')"}` to the top-level `properties` object (the schema uses `"additionalProperties": false`, so the field must be explicitly declared).
4. **`FSMLoop` dataclass**: Optionally add `input_key: str = "input"` to `scripts/little_loops/fsm/schema.py:FSMLoop` (line ~389) so `cmd_run` can use `fsm.input_key` instead of hardcoding `"input"`.
5. **Dry-run display**: In `scripts/little_loops/cli/loop/_helpers.py:print_execution_plan` (line 148), add a `context` section after `Max iterations` that prints `fsm.context` when non-empty — shows the resolved `input` value.
6. **Test helper sync**: In `scripts/tests/test_ll_loop_parsing.py:_create_run_parser` (line 26), add `parser.add_argument("input", nargs="?", default=None)` to keep it synchronized with the production parser.
7. **Validation**: If `fsm.context.get(fsm.input_key) is None` after all injections (positional + `--context`), emit a warning via `logger.warning(...)` (not an error).

## API/Interface

```
ll-loop run <loop-name> [input] [options]
```

- `input` — optional positional string injected as `fsm.context["input"]` (or `fsm.context[fsm.input_key]` if `input_key` is declared)
- No breaking changes; existing invocations without positional input are unaffected

## Acceptance Criteria

- [ ] `ll-loop run my-loop "FEAT-719"` injects `FEAT-719` into `context["input"]` and runs successfully
- [ ] `ll-loop run my-loop` (no input) still works; `context["input"]` defaults to `null`/empty
- [ ] `--context input=X` still works and overrides the positional value
- [ ] `--dry-run` shows the resolved input value in the execution plan
- [ ] Tests cover: positional input injection, `--context` override wins, no-input default

## Impact

- **Priority**: P3 - Quality-of-life improvement; single-item loops work but require verbose syntax
- **Effort**: Small - Adds one positional arg to the `run` subparser and one injection line in `cmd_run`; schema update is additive
- **Risk**: Low - Fully backward compatible; no-input invocations are unaffected
- **Breaking Change**: No

## Labels

`cli`, `ll-loop`, `feature`

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add optional positional `input` to `run` subparser
- `scripts/little_loops/cli/loop/run.py` — inject `args.input` into `fsm.context["input"]` in `cmd_run`
- `scripts/little_loops/fsm/fsm-loop-schema.json` — add optional `input_key` string field

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/__init__.py:288` — dispatches to `cmd_run(args.loop, args, loops_dir, logger)`; `args.loop` becomes the first arg, new `args.input` will follow
- `scripts/little_loops/fsm/schema.py:389` — `FSMLoop.context: dict[str, Any]` — positional input is injected here; no `input_key` field exists on `FSMLoop` yet
- `scripts/little_loops/cli/loop/_helpers.py:148` — `print_execution_plan(fsm)` prints dry-run plan; currently prints `context` only implicitly via state actions; needs a `context` section showing resolved `input` value

### Similar Patterns
- `run.py:50-54` — existing `--context` parsing loop (`for kv in getattr(args, "context", ...) or []`); positional injection should happen **before** this block so `--context input=X` can still override
- `test_ll_loop_parsing.py:26-37` — `_create_run_parser()` mirrors the real run subparser; this helper must also get `input` added so parsing tests stay synchronized with production code

### Tests
- `scripts/tests/test_ll_loop_parsing.py` — primary test target; `_create_run_parser()` (line 26) and `TestLoopArgumentParsing` class (line 17) are where `input` parsing tests belong (see `test_context_single_flag` at line 179 for style guide)
- `scripts/tests/test_ll_loop_commands.py` — integration-level `cmd_run` tests (currently no context tests); add tests covering: positional injection, `--context` override wins, no-input default behavior

### Documentation
- `docs/` — update ll-loop CLI reference if positional arg docs exist

### Configuration
- `scripts/little_loops/fsm/fsm-loop-schema.json` — additive `input_key` field

## Related Key Documentation

- `scripts/little_loops/cli/loop/__init__.py` — run subparser argument definitions
- `scripts/little_loops/cli/loop/run.py` — `cmd_run` context injection logic
- `scripts/little_loops/fsm/fsm-loop-schema.json` — schema for `input_key`

---

## Status

**Active** — not yet started

## Verification Notes

- **Date**: 2026-03-14 (re-verified 2026-03-14)
- **Verdict**: VALID
- `scripts/little_loops/cli/loop/__init__.py:94` registers only `"loop"` as a positional argument for the `run` subparser — no second positional `input` argument exists. `run.py` has no `args.input` injection logic. `fsm-loop-schema.json` has no `input_key` field. Feature not yet implemented.

## Session Log
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7a1f56-687d-4b69-9d22-6ec472aa9b1f.jsonl`
- `/ll:refine-issue` - 2026-03-15T03:26:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/bf30ff97-a5f9-4719-b28c-ab6580383ecd.jsonl`
- `/ll:verify-issues` - 2026-03-15T03:23:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c6cacfa2-fc65-45e7-9629-01c3fe3df856.jsonl`
- `/ll:verify-issues` - 2026-03-15T00:11:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/623195d5-5e50-40d6-b2b9-5b105ad77689.jsonl`
- `/ll:capture-issue` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/582c29ac-d327-46f4-8794-3433874ce5c2.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/34ee1913-aa14-4e60-9d80-efda0df3efc0.jsonl`
- `/ll:format-issue` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:verify-issues` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
