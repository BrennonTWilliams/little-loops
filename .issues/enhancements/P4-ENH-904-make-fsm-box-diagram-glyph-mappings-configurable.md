---
discovered_date: 2026-03-31
discovered_by: capture-issue
---

# ENH-904: Make FSM Box Diagram Glyph Mappings Configurable

## Summary

The unicode glyph/badge characters used in FSM box diagrams are hardcoded in `scripts/little_loops/cli/loop/layout.py`. Users cannot override them without modifying source code. This enhancement exposes the glyph mappings as a configurable option in `ll-config.json` (with schema support) or via a dedicated `.ll/` config file.

## Current Behavior

Glyph mappings are defined as module-level constants in `layout.py`:

```python
_ACTION_TYPE_BADGES: dict[str, str] = {
    "prompt": "\u2726",       # ✦
    "slash_command": "/\u2501\u25ba",  # /━►
    "shell": "\u276f_",       # ❯_
    "mcp_tool": "\u26a1",     # ⚡
}
_SUB_LOOP_BADGE = "\u21b3\u27f3"  # ↳⟳
_ROUTE_BADGE = "\u2443"           # ⑃
```

There is no way to override these without editing the source file.

## Expected Behavior

Users can override any glyph by adding a `loops.glyphs` key (or similar) to `.ll/ll-config.json`. The config schema (`config-schema.json`) is updated to document and validate the new key. Unspecified glyphs fall back to the hardcoded defaults, so partial overrides work.

Example config:

```json
{
  "loops": {
    "glyphs": {
      "prompt": "✦",
      "slash_command": "/━►",
      "shell": "❯_",
      "mcp_tool": "⚡",
      "sub_loop": "↳⟳",
      "route": "⑃"
    }
  }
}
```

## Motivation

Some terminal fonts don't render the chosen glyphs cleanly (e.g., wcwidth mismatches cause layout corruption). Power users and CI environments may also want plain ASCII badges. Making glyphs configurable avoids source edits and makes the display layer consistent with the rest of the ll-config.json customization surface.

## Success Metrics

- Glyph override: 0 user-configurable glyph keys → 6 configurable keys (`prompt`, `slash_command`, `shell`, `mcp_tool`, `sub_loop`, `route`) via `loops.glyphs` in `ll-config.json`
- Partial override: setting any subset of keys applies only those overrides; unspecified keys fall back to built-in defaults unchanged
- ASCII compatibility: FSM diagram renders without layout corruption when all glyphs are replaced with single-character ASCII strings (wcwidth mismatch artifacts eliminated)
- Test coverage: `scripts/tests/test_ll_loop_display.py` has at least one parameterized test verifying a custom glyph override round-trips correctly

## Proposed Solution

1. Add `loops.glyphs` object to `config-schema.json` under the existing `loops` property, with per-glyph string fields and the current unicode values as defaults.
2. In `layout.py`, load the config at module/function level and merge user-supplied glyphs over the hardcoded defaults. Since `layout.py` already imports config utilities (or can), this is a small delta.
3. Ensure `_get_state_badge()` reads from the merged dict rather than the module constants directly.
4. Add tests asserting that a custom glyph config is respected.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — replace constant references with config-driven lookup
- `config-schema.json` — add `loops.glyphs` properties with defaults

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py` — imports from `layout.py`; verify no badge constants are re-exported
- `scripts/little_loops/config/cli.py` — may already load `loops` config; check if merge logic lives here

### Similar Patterns
- `cli.colors` in `config-schema.json` (lines 819–875) — existing pattern for user-overridable visual constants with ANSI SGR defaults; follow the same `additionalProperties: false` + per-key default structure

### Tests
- `scripts/tests/test_ll_loop_display.py` — add parameterized tests for custom glyph override
- `scripts/tests/test_ll_loop_commands.py` — verify diagram output reflects config glyphs

### Documentation
- `config-schema.json` descriptions are the primary docs; no separate doc file needed
- `docs/` or README may mention FSM diagram customization — check and update if present

### Configuration
- `config-schema.json` — primary change
- `.ll/ll-config.json` (user-level) — consumers add overrides here

## Implementation Steps

1. Audit `layout.py` to confirm all glyph constants and where `_get_state_badge()` reads them.
2. Add `loops.glyphs` to `config-schema.json` mirroring the `cli.colors` pattern (object with per-key string defaults).
3. Update `layout.py`: load ll-config at call time (or module init) and build a merged glyph dict; replace constant references in `_get_state_badge()`.
4. Add unit tests covering default pass-through and single-key override.
5. Smoke-test `ll-loop show` with a custom glyph entry in `.ll/ll-config.json`.

## Scope Boundaries

- Only the FSM box diagram badge glyphs (action-type badges, sub-loop badge, route badge) are in scope.
- Edge label text (e.g., "yes", "no") and ANSI colors (`cli.colors.fsm_edge_labels`) are out of scope.
- No new config file format — use existing `ll-config.json` only (the "or separate file" option is deferred).

## API/Interface

New `config-schema.json` fragment under `loops`:

```json
"glyphs": {
  "type": "object",
  "description": "Override unicode badge glyphs shown in FSM box diagrams. Omitted keys use built-in defaults.",
  "properties": {
    "prompt":        { "type": "string", "default": "\u2726",           "description": "Badge for prompt states (default: ✦)" },
    "slash_command": { "type": "string", "default": "/\u2501\u25ba",    "description": "Badge for slash_command states (default: /━►)" },
    "shell":         { "type": "string", "default": "\u276f_",          "description": "Badge for shell states (default: ❯_)" },
    "mcp_tool":      { "type": "string", "default": "\u26a1",           "description": "Badge for mcp_tool states (default: ⚡)" },
    "sub_loop":      { "type": "string", "default": "\u21b3\u27f3",     "description": "Badge for sub-loop states (default: ↳⟳)" },
    "route":         { "type": "string", "default": "\u2443",           "description": "Badge for route states (default: ⑃)" }
  },
  "additionalProperties": false
}
```

## Impact

- **Priority**: P4 — Nice-to-have; workaround is editing source
- **Effort**: Small — config schema addition + ~10-line change in `layout.py` + tests
- **Risk**: Low — purely additive; defaults preserve existing behavior
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `fsm-diagram`, `configuration`, `captured`

## Session Log
- `/ll:format-issue` - 2026-04-01T03:21:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3838f86a-9688-4708-8f33-4d8d699d79ac.jsonl`
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6df5ee0a-f20f-4ab8-a215-3c707d7115cd.jsonl`

---

**Open** | Created: 2026-03-31 | Priority: P4
