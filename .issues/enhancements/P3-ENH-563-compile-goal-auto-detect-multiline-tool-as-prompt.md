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

- `scripts/little_loops/fsm/executor.py:519` — `is_slash_command = action.startswith("/")` — this is the downstream dispatcher; no change needed here
- `scripts/tests/test_fsm_compilers.py` — add new test cases

## Implementation Steps

1. **Add `_infer_action_type()` helper** in `compilers.py` above `compile_goal`:
   ```python
   def _infer_action_type(tool: str) -> str | None:
       """Infer action_type from tool string. Multiline text → 'prompt'."""
       if "\n" in tool:
           return "prompt"
       return None
   ```

2. **Wire into `compile_goal`** — capture result and pass to `StateConfig`:
   ```python
   fix_action_type = _infer_action_type(fix_tool)
   if fix_action_type == "prompt":
       logger.debug("compile_goal: multiline fix tool detected, using action_type='prompt'")
   # ...
   "fix": StateConfig(action=fix_tool, action_type=fix_action_type, next="evaluate"),
   ```

3. **Add tests** in `test_fsm_compilers.py`:
   - Test multiline fix tool → `StateConfig.action_type == "prompt"`
   - Test single-line `/ll:cmd` → `StateConfig.action_type is None`
   - Test single-line shell command → `StateConfig.action_type is None`

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

## Related Key Documentation

- `scripts/little_loops/fsm/compilers.py` — primary implementation target
- `scripts/little_loops/fsm/executor.py` — downstream dispatcher (reference only)
- `scripts/tests/test_fsm_compilers.py` — test patterns to follow
- `.loops/tests-until-passing.yaml` — working reference: uses `action_type: prompt` explicitly

## Status

Open

---

## Session Log
- `capture-issue` - 2026-03-04 - root cause discovered while debugging `.loops/issue-refinement.yaml` infinite loop
