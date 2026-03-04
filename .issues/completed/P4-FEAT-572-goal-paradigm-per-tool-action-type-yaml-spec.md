---
discovered_date: 2026-03-04
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 93
---

# FEAT-572: Add per-tool `action_type` support to `goal` paradigm YAML spec

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

ENH-563 provides auto-detection of multiline → prompt, but some users will want to explicitly declare `action_type` for clarity, documentation, or to force a specific dispatch mode. Explicit beats implicit. This feature also makes the `goal` paradigm's expressiveness closer to the `fsm` paradigm without requiring users to write a full FSM.

## Use Case

**Who**: A developer writing a `goal` paradigm loop YAML who needs precise control over tool dispatch mode.

**Context**: When authoring a loop where a tool entry contains a multiline prompt (or slash command) that auto-detection might misclassify, or when they want the loop configuration to be self-documenting about dispatch intent.

**Goal**: Declare `action_type: prompt` (or `shell` / `slash_command`) directly inline on a tool entry—without relying on ENH-563 auto-detection heuristics or converting the entire loop to FSM paradigm.

**Outcome**: The loop executor respects the declared `action_type` and dispatches the tool entry correctly, with no silent fallback or misclassification.

## Acceptance Criteria

- [x] `tools:` list items may be plain strings (existing) or objects `{tool: str, action_type: str}`
- [x] Object-style entries are validated: `tool` is required, `action_type` must be one of `shell`, `prompt`, `slash_command`
- [x] Backward compatibility: all existing plain-string `tools:` entries continue to work unchanged
- [x] `fsm-loop-schema.json` **NOT required** — this schema validates compiled FSM output (with `name`, `initial`, `states`), not pre-compilation paradigm YAML; the `tools:` key does not exist in the compiled output
- [x] `skills/create-loop/paradigms.md` documents the new object syntax with examples
- [x] `scripts/tests/test_fsm_compilers.py` — new tests for object-style tool parsing

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/compilers.py:163-195` — update `compile_goal` to handle both string and dict tool entries:
  - Validation block: `163-170` (add type-check for invalid dict entries)
  - Tool extraction: `172-175` (`check_tool = tools[0]`, `fix_tool = tools[1]`) — replace with `_parse_tool_entry()` calls
  - `StateConfig` creation: `182-195` — pass extracted `action_type` to each `StateConfig`
  ```python
  def _parse_tool_entry(entry: str | dict) -> tuple[str, str | None]:
      """Parse a tools[] entry into (action, action_type)."""
      if isinstance(entry, str):
          return entry, None
      return entry["tool"], entry.get("action_type")
  ```
- `skills/create-loop/paradigms.md` — document new object syntax in the `goal` paradigm section
- **`scripts/little_loops/fsm/fsm-loop-schema.json` — NO CHANGE NEEDED**: This schema validates compiled FSM output format (states with `name`, `initial`, `states` keys). The `tools:` array is a pre-compilation paradigm YAML key consumed by `compile_goal`; it is never present in the compiled `FSMLoop` output that the schema validates.

### Dependent Files (Reference Only)

- `scripts/tests/test_fsm_compilers.py` — add tests for object-style tool entries
- `scripts/tests/test_fsm_compiler_properties.py` — also covers `compile_goal`; consider adding property-based tests for mixed entry types here

### Similar Patterns

- `scripts/little_loops/fsm/compilers.py` — existing `compile_goal` handles plain-string tools; new logic mirrors the FSM paradigm's per-state `action_type` field
- `.loops/tests-until-passing.yaml` — working reference for `action_type: prompt` in an FSM loop

### Tests

- `scripts/tests/test_fsm_compilers.py` — add tests: object-style tool entry, mixed string/object entries, missing `tool` key raises `ValueError`, invalid `action_type` raises error

### Documentation

- `skills/create-loop/paradigms.md` — add object-syntax example to `goal` paradigm section
- `scripts/little_loops/fsm/fsm-loop-schema.json` — inline schema comments updated

### Configuration

- N/A — no config file changes required

## API/Interface

New internal helper in `scripts/little_loops/fsm/compilers.py`:

```python
def _parse_tool_entry(entry: str | dict) -> tuple[str, str | None]:
    """Parse a tools[] entry into (action, action_type).

    Args:
        entry: Either a plain string or a dict with 'tool' and optional 'action_type' keys.

    Returns:
        Tuple of (action_string, action_type_or_None).

    Raises:
        ValueError: If entry is a dict missing the required 'tool' key.
    """
    if isinstance(entry, str):
        return entry, None
    if not isinstance(entry, dict) or "tool" not in entry:
        raise ValueError(f"Invalid tool entry: {entry!r}")
    return entry["tool"], entry.get("action_type")
```

No schema file changes — `fsm-loop-schema.json` validates compiled FSM output, not paradigm YAML (which has no `tools` property after compilation). No public CLI API changes.

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

2. **Update `compile_goal`** (`compilers.py:172-195`) to use the helper for both check and fix tools:
   ```python
   check_action, check_type = _parse_tool_entry(tools[0])
   fix_action, fix_type = _parse_tool_entry(tools[1] if len(tools) > 1 else tools[0])
   # Pass action_type directly to StateConfig (None = executor uses / heuristic)
   # Note: _infer_action_type (ENH-563) is NOT a prerequisite — None falls back to
   # executor heuristic (action.startswith("/")) which already handles most cases.
   ```
   Then pass `action_type=check_type` / `action_type=fix_type` to each `StateConfig`.

3. **No schema change needed** — `fsm-loop-schema.json` validates compiled FSM output; paradigm YAML is not JSON Schema validated. Skip this step.

4. **Update docs** in `skills/create-loop/paradigms.md` — add object-style example to `goal` paradigm section.

5. **Add tests** in `scripts/tests/test_fsm_compilers.py` for object-style entries, mixed entries, and invalid entries.

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
- `scripts/little_loops/fsm/fsm-loop-schema.json` — **no change needed** (validates compiled output, not paradigm YAML)
- `skills/create-loop/paradigms.md` — docs to update
- `.loops/tests-until-passing.yaml` — working reference for `action_type: "prompt"` in FSM paradigm
- `.loops/issue-refinement.yaml` — working reference for `action_type: shell` + `action_type: prompt`
- `ENH-563` — auto-detection complement (`_infer_action_type` planned there); both are additive and independent
- `scripts/little_loops/fsm/schema.py:191-192` — `StateConfig.action_type` field (already exists; `compile_goal` just never sets it)

## Resolution

Implemented 2026-03-04. Added `_parse_tool_entry()` helper to `compilers.py` that parses both string and object-style tool entries. Updated `compile_goal` to use the helper, passing `action_type` to each `StateConfig`. Added 19 new tests across `TestParseToolEntry` and `TestGoalWithObjectTools`. Updated `skills/create-loop/paradigms.md` with object-syntax docs and examples.

## Status

Completed

---

## Session Log
- `capture-issue` - 2026-03-04 - identified while debugging `.loops/issue-refinement.yaml`; Option C counterpart to ENH-562 Option B
- `/ll:format-issue` - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c8508667-855e-42a5-8045-689c560ff2ef.jsonl`
- `/ll:refine-issue` - 2026-03-04 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38770f19-a4ab-4c64-9367-0a96f408e368.jsonl`
- `/ll:confidence-check` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/91190f25-5aa6-4463-8959-6135885f4143.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d75ec1be-6c57-4483-9251-119ffd45e2a9.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`
