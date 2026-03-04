---
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: ~
outcome_confidence: ~
---

# ENH-563: `compile_goal` silently runs multiline tool text via bash instead of Claude prompt

## Summary

When a tool in the `goal` paradigm `tools:` list is multi-line text (contains `\n`), it is almost certainly intended as a Claude CLI prompt, not a shell command. `compile_goal` should auto-detect this and set `action_type="prompt"` on the fix state. Currently it silently produces broken FSMs: the fix state runs the multiline text via `bash -c`, which fails immediately, and since `fix` has `next="evaluate"` (unconditional), the error is swallowed and the loop cycles forever with nothing actually fixed.

## Current Behavior

`compile_goal` in `compilers.py:174-175` assigns `fix_tool = tools[1]`. Since the multiline text doesn't start with `/`, `executor.py:519` (`is_slash_command = action.startswith("/")`) treats it as a shell command and runs it via `bash -c`. Bash fails immediately. The `fix` state has `next="evaluate"` (unconditional), so the error is silently swallowed and the loop cycles forever.

## Expected Behavior

When a tool string in the `tools:` list contains a newline character, `compile_goal` infers `action_type="prompt"` for the fix state. A single-line tool string that starts with `/` continues to be treated as a slash command (or `None` for shell). No user-visible YAML changes required.

## Motivation

The `goal` paradigm is supposed to offer a simpler alternative to writing a full FSM. But if a user writes a multiline fix prompt (the natural way to describe a complex remediation), the loop silently does nothing — the bug is invisible until the user notices the loop iterating forever with ~0s fix runs. Auto-detection of multiline → prompt eliminates this footgun at zero cost to the user.

## Acceptance Criteria

- [ ] `compile_goal` detects multiline fix tools and sets `action_type="prompt"` on the fix `StateConfig`
- [ ] Single-line tools (starting with `/` or plain shell commands) are unaffected
- [ ] A warning is logged when multiline auto-detection fires (to aid debugging)
- [ ] `scripts/tests/test_fsm_compilers.py` — new tests assert:
  - Multiline fix tool produces `StateConfig(action_type="prompt")`
  - Single-line `/ll:cmd` fix tool produces `StateConfig(action_type=None)` (existing behavior)
  - Single-line `ll-issues refine-status` fix tool produces `StateConfig(action_type=None)`

## Proposed Solution

Add `_infer_action_type()` helper above `compile_goal` in `compilers.py`:

```python
def _infer_action_type(tool: str) -> str | None:
    """Infer action_type from tool string. Multiline text → 'prompt'."""
    if "\n" in tool:
        return "prompt"
    return None
```

Wire into `compile_goal` when building the fix `StateConfig`:

```python
fix_action_type = _infer_action_type(fix_tool)
if fix_action_type == "prompt":
    logger.warning("compile_goal: multiline fix tool detected, using action_type='prompt'")
"fix": StateConfig(action=fix_tool, action_type=fix_action_type, next="evaluate"),
```

> **Note**: `compilers.py` currently has no logging — add `import logging` and `logger = logging.getLogger(__name__)` at the top of the module. Follow the pattern in `validation.py:16-26`.

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/compilers.py:174-195` — add `_infer_action_type()` helper and pass result into `StateConfig` for the fix state:
  ```python
  def _infer_action_type(tool: str) -> str | None:
      if "\n" in tool:
          return "prompt"
      return None

  fix_action_type = _infer_action_type(fix_tool)
  "fix": StateConfig(
      action=fix_tool,
      action_type=fix_action_type,
      next="evaluate",
  )
  ```

### Dependent Files (Reference Only)

- `scripts/little_loops/fsm/executor.py:515-525` — `_run_action()` / `is_slash_command` dispatch — no change needed; `action_type="prompt"` is already handled
- `scripts/little_loops/fsm/executor.py:576-592` — `_evaluate()` default evaluator selection — **side effect**: setting `action_type="prompt"` here will also cause the fix state to use LLM evaluation (via `evaluate_llm_structured`) instead of exit-code evaluation; this is the correct and desired behavior
- `scripts/little_loops/fsm/schema.py:191` — `action_type: Literal["prompt", "slash_command", "shell"] | None = None` — reference for valid values
- `scripts/little_loops/fsm/validation.py:16-26` — logger pattern to follow: `import logging; logger = logging.getLogger(__name__)`
- `scripts/tests/test_fsm_compilers.py` — add new test cases; assertion style: `fsm.states["fix"].action_type == "prompt"` using inline spec dicts, no fixtures

### Similar Patterns

- `executor.py` `is_slash_command = action.startswith("/")` — same dispatch-by-inspection pattern; `_infer_action_type` extends this to compile time

### Tests

- `scripts/tests/test_fsm_compilers.py` — add multiline, slash-cmd, and shell-cmd test cases

### Documentation

- N/A — no user-facing docs change; behavior is transparent to YAML authors

### Configuration

- N/A — no config changes

## Implementation Steps

1. Add `import logging` and `logger = logging.getLogger(__name__)` at the top of `compilers.py` (currently has no logger; follow `validation.py:16-26` pattern)
2. Add `_infer_action_type()` helper in `compilers.py` above `compile_goal` (around line 134)
3. Wire result into fix `StateConfig` with `logger.warning(...)` in `compile_goal` (around lines 173-195)
4. Add test cases in `scripts/tests/test_fsm_compilers.py` inside `TestGoalCompiler`:
   - Multiline fix tool → `fsm.states["fix"].action_type == "prompt"`
   - Single-line `/ll:cmd` fix tool → `fsm.states["fix"].action_type is None`
   - Single-line shell command fix tool → `fsm.states["fix"].action_type is None`

## Impact

- **Priority**: P3 - Medium; silent failure makes goal-paradigm loops with multiline prompts completely broken
- **Effort**: Small — ~10 lines of logic + tests
- **Risk**: Low — additive change; only affects goal paradigm compilation
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `goal-paradigm`, `bug-prevention`

## Scope Boundaries

- Inferring `action_type` for the **check** tool (first tool) is **out of scope** — check tools should always be shell commands
- Supporting object-style tool entries in YAML is **out of scope** — see FEAT-560
- Changing executor dispatch logic is **out of scope**

## Success Metrics

- All new tests in `test_fsm_compilers.py` pass (multiline → prompt, single-line unaffected)
- Goal-paradigm loop with multiline fix tool no longer cycles silently — fix state dispatches via Claude prompt, not `bash -c`

## Related Key Documentation

- `scripts/little_loops/fsm/compilers.py` — primary implementation target
- `scripts/little_loops/fsm/executor.py` — downstream dispatcher (reference only)
- `scripts/tests/test_fsm_compilers.py` — test patterns to follow
- `.loops/tests-until-passing.yaml` — working reference: uses `action_type: prompt` explicitly

## Blocked By

- BUG-530

## Status

Open

---

## Verification Notes

**Verdict: VALID** — verified 2026-03-04

- `compilers.py:175` `fix_tool = tools[1] if len(tools) > 1 else tools[0]` — confirmed; issue omits conditional fallback and slightly mislabels as line 174, but core claim is accurate
- `executor.py:519` `is_slash_command = action.startswith("/")` — verified exactly
- Fix state `StateConfig(action=fix_tool, next="evaluate")` — confirmed; no `action_type` set, errors silently swallowed
- `_infer_action_type` helper does not exist — confirmed, fix not yet implemented
- No multiline/prompt `action_type` tests for `compile_goal` in `test_fsm_compilers.py` — confirmed

## Session Log
- `capture-issue` - 2026-03-04 - root cause discovered while debugging `.loops/issue-refinement.yaml` infinite loop
- `/ll:format-issue` - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6f4dee21-8bf7-4b06-a184-dbae77b0cc48.jsonl`
- `/ll:verify-issues` - 2026-03-04 - VALID; all core claims confirmed against codebase
- `/ll:refine-issue` - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/037c8035-cf2b-4bea-8dab-6337898b38c5.jsonl`
- `/ll:map-dependencies` - 2026-03-04 - validated existing `Blocked By: BUG-530`; added missing backlink `Blocks: ENH-563` to BUG-530
