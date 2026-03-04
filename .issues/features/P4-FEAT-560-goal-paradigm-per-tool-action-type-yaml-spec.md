---
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: ~
outcome_confidence: ~
---

# FEAT-560: Add per-tool `action_type` support to `goal` paradigm YAML spec

## Summary

The `goal` paradigm's `tools:` list accepts only plain strings. Add support for object-style tool entries so users can explicitly declare `action_type` per tool, giving them direct control without relying on auto-detection (ENH-562) or converting to `fsm` paradigm.

## Current Behavior

`tools:` in a `goal` paradigm loop only accepts plain strings:
```yaml
tools:
  - "ll-issues refine-status"
  - |
    Run `ll-issues refine-status`...
```

The second entry (multiline) is silently run as a bash command, causing the loop to fail and cycle forever.

## Expected Behavior

`tools:` accepts both plain strings (backward-compatible) and object entries with an explicit `action_type`:
```yaml
paradigm: goal
goal: "All issues refined"
tools:
  - "ll-issues refine-status"        # backward-compat: string → shell
  - tool: |                           # new: object with explicit type
      Run `ll-issues refine-status`...
    action_type: prompt
```

## Motivation

ENH-562 provides auto-detection of multiline → prompt, but some users will want to explicitly declare `action_type` for clarity, documentation, or to force a specific dispatch mode. Explicit beats implicit. This feature also makes the `goal` paradigm's expressiveness closer to the `fsm` paradigm without requiring users to write a full FSM.

## Acceptance Criteria

- [ ] `tools:` list items may be plain strings (existing) or objects `{tool: str, action_type: str}`
- [ ] Object-style entries are validated: `tool` is required, `action_type` must be one of `shell`, `prompt`, `slash_command`
- [ ] Backward compatibility: all existing plain-string `tools:` entries continue to work unchanged
- [ ] `fsm-loop-schema.json` updated to allow both string and object formats in the `tools` array
- [ ] `skills/create-loop/paradigms.md` documents the new object syntax with examples
- [ ] `scripts/tests/test_fsm_compilers.py` — new tests for object-style tool parsing

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/compilers.py:164-175` — update `compile_goal` validation and tool extraction to handle both string and dict tool entries:
  ```python
  def _parse_tool_entry(entry: str | dict) -> tuple[str, str | None]:
      """Parse a tools[] entry into (action, action_type)."""
      if isinstance(entry, str):
          return entry, None
      return entry["tool"], entry.get("action_type")
  ```
- `scripts/little_loops/fsm/fsm-loop-schema.json` — update `tools` array items to accept `oneOf: [string, {type: object, required: [tool], properties: {tool: string, action_type: string}}]`
- `skills/create-loop/paradigms.md` — document new object syntax in the `goal` paradigm section

### Dependent Files (Reference Only)

- `scripts/tests/test_fsm_compilers.py` — add tests for object-style tool entries

## Implementation Steps

1. **Add `_parse_tool_entry()` helper** in `compilers.py`:
   ```python
   def _parse_tool_entry(entry: str | dict) -> tuple[str, str | None]:
       if isinstance(entry, str):
           return entry, None
       if not isinstance(entry, dict) or "tool" not in entry:
           raise ValueError(f"Invalid tool entry: {entry!r}")
       return entry["tool"], entry.get("action_type")
   ```

2. **Update `compile_goal`** to use the helper for both check and fix tools:
   ```python
   check_action, check_type = _parse_tool_entry(tools[0])
   fix_action, fix_type = _parse_tool_entry(tools[1])
   # If no explicit type, fall back to auto-detection (ENH-562)
   if fix_type is None:
       fix_type = _infer_action_type(fix_action)
   ```

3. **Update schema** in `fsm-loop-schema.json` — change `tools` items from `{type: string}` to:
   ```json
   "items": {
     "oneOf": [
       {"type": "string"},
       {
         "type": "object",
         "required": ["tool"],
         "properties": {
           "tool": {"type": "string"},
           "action_type": {"type": "string", "enum": ["shell", "prompt", "slash_command"]}
         },
         "additionalProperties": false
       }
     ]
   }
   ```

4. **Update docs** in `skills/create-loop/paradigms.md` — add object-style example to `goal` paradigm section.

5. **Add tests** for object-style entries, mixed entries, and invalid entries.

## Impact

- **Priority**: P4 - Low; ENH-562 covers the most common case (multiline auto-detect); this is an ergonomic addition
- **Effort**: Small-Medium — schema change + parser update + docs + tests
- **Risk**: Low — purely additive; no existing behavior changes
- **Breaking Change**: No

## Labels

`feature`, `fsm`, `goal-paradigm`, `schema`, `ergonomics`

## Scope Boundaries

- Allowing object entries for `check` tool (first tool) is **in scope** — same `_parse_tool_entry()` applies
- Adding validation beyond `action_type` enum check is **out of scope**
- Changing FSM paradigm YAML spec is **out of scope** — FSM already supports `action_type` per state

## Related Key Documentation

- `scripts/little_loops/fsm/compilers.py` — primary implementation target
- `scripts/little_loops/fsm/fsm-loop-schema.json` — schema to update
- `skills/create-loop/paradigms.md` — docs to update
- `.loops/tests-until-passing.yaml` — working reference for `action_type: prompt`
- `ENH-562` — auto-detection complement; both are additive

## Status

Open

---

## Session Log
- `capture-issue` - 2026-03-04 - identified while debugging `.loops/issue-refinement.yaml`; Option C counterpart to ENH-562 Option B
