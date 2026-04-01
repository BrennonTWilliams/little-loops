---
discovered_date: 2026-03-31
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 78
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Additional files to modify (not listed above):**
- `scripts/little_loops/config/features.py:189–200` — `LoopsConfig` dataclass; add a `glyphs: LoopsGlyphsConfig` field with `default_factory=LoopsGlyphsConfig` following the same structure as `CliColorsEdgeLabelsConfig` in `cli.py:76–116`
- `scripts/little_loops/cli/loop/info.py:683–689` — second call site for `_render_fsm_diagram`; currently called without glyph config (no config is loaded here at all); must be updated alongside `run.py`
- `scripts/little_loops/config/__init__.py:62–66` — exports config classes; add `LoopsGlyphsConfig` to the export list

**Correction on `config/cli.py`:** This file is a **pattern reference** (`CliColorsEdgeLabelsConfig` at `cli.py:76–116`), not a file that currently loads `loops` config. The `loops` config is in `features.py`, not `cli.py`.

**Schema constraint:** `config-schema.json:652` has `"additionalProperties": false` on the parent `loops` object. Adding `glyphs` requires explicitly adding it to the `properties` block — adding glyphs as an unknown property will fail schema validation until the parent is updated.

**Architecture note:** `layout.py` has **no config system imports** (confirmed at lines 10–19 — only `re`, `deque`, `wcwidth`, and internal `fsm`/`output` imports). The established pattern for this codebase (used by `edge_label_colors`) is:
1. Add a `badges: dict[str, str] | None = None` parameter to `_render_fsm_diagram` (mirroring `edge_label_colors` at `layout.py:1429–1448`)
2. Thread it into `_get_state_badge()` at `layout.py:118–130`
3. Load and pass from call sites: `run.py:154–166` (live run) and `info.py:683–689` (`ll-loop show`)
- This keeps `layout.py` config-free and matches the `_colorize_diagram_labels` / `edge_label_colors` precedent at `layout.py:77–94`

**Test patterns to follow:**
- `test_config.py:1264–1295` (`TestCliColorsEdgeLabelsConfig`) — leaf dataclass defaults, partial override, and `to_dict()` tests
- `test_config.py:1324–1374` (`TestBRConfigCli`) — end-to-end BRConfig + JSON file loading test
- `test_ll_loop_display.py:1277–1331` — custom `edge_label_colors` override tests; glyph override tests should follow the same `_render_fsm_diagram(..., badges=custom_badges)` call pattern

## Implementation Steps

1. Audit `layout.py` to confirm all glyph constants and where `_get_state_badge()` reads them.
2. Add `loops.glyphs` to `config-schema.json` mirroring the `cli.colors` pattern (object with per-key string defaults).
3. Update `layout.py`: load ll-config at call time (or module init) and build a merged glyph dict; replace constant references in `_get_state_badge()`.
4. Add unit tests covering default pass-through and single-key override.
5. Smoke-test `ll-loop show` with a custom glyph entry in `.ll/ll-config.json`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete file:line references:_

1. **Confirm glyph constants** — already confirmed: `layout.py:101–109` (three constants); sole consumer is `_get_state_badge()` at `layout.py:118–130` which is called at `layout.py:518` and `layout.py:1499`.

2. **Update `config-schema.json`** — add `glyphs` under `loops.properties` at line ~642; also remove/update `"additionalProperties": false` on the parent `loops` object (currently at line 652) to allow the new key.

3. **Add `LoopsGlyphsConfig` dataclass to `features.py:189–200`** — model after `CliColorsEdgeLabelsConfig` at `cli.py:76–116`: one `str` field per glyph with unicode defaults, a `from_dict()` with `.get(key, default)` per field, and a `to_dict()` that returns `dict[str, str]` for use in layout. Add a `glyphs: LoopsGlyphsConfig` field to `LoopsConfig` with `default_factory=LoopsGlyphsConfig`.

4. **Update `layout.py`** — add `badges: dict[str, str] | None = None` parameter to `_render_fsm_diagram()` at line 1429 (mirror `edge_label_colors` parameter); thread it into `_get_state_badge()` at line 118; inside `_get_state_badge`, build the merged dict as `effective = {**_ACTION_TYPE_BADGES, **(badges or {})}` and use `effective` instead of the module constants.

5. **Wire config at call sites:**
   - `run.py:154–166` — already loads `BRConfig`; add `badges=BRConfig(Path.cwd()).loops.glyphs.to_dict()` alongside `edge_label_colors`
   - `info.py:683–689` — currently has no config loading; add `BRConfig(Path.cwd()).loops.glyphs.to_dict()` and pass as `badges=`

6. **Add tests:**
   - `test_config.py` — add `TestLoopsGlyphsConfig` following `TestCliColorsEdgeLabelsConfig` at lines 1264–1295 (defaults, partial override, `to_dict()`)
   - `test_ll_loop_display.py` — add `test_custom_glyph_override_applied` following the pattern at lines 1277–1331: call `_render_fsm_diagram(fsm, badges={"prompt": "P"})` and assert the custom string appears in output

7. **Export** — add `LoopsGlyphsConfig` to `config/__init__.py` export list (alongside `LoopsConfig`, currently around lines 62–66).

**Correction to Step 5 (call-site threading):**
`run.py` does NOT call `_render_fsm_diagram` directly. The actual call chain is:
- `run.py:165` → `run_foreground(executor, fsm, args, ..., edge_label_colors=edge_label_colors)`
- `_helpers.py:351–356` → `_render_fsm_diagram(fsm, ..., edge_label_colors=edge_label_colors)`

Wiring `badges` at this call site requires three steps:
1. Load `badges` in `run.py` alongside `edge_label_colors` in the same `BRConfig` block at lines 155–166
2. Add `badges: dict[str, str] | None = None` to `run_foreground`'s signature in `_helpers.py`
3. Pass `badges` through to `_render_fsm_diagram` at `_helpers.py:351–356`

**Correction to Step 7 (export line):**
`LoopsConfig` is at line 55 of `config/__init__.py` `__all__` (import from `features` is at line 38). Lines 62–66 contain the `CliColors*` exports. Add `LoopsGlyphsConfig` to the import at line 38 and to `__all__` adjacent to `LoopsConfig` at line 55.

**Unrelated hardcoded glyph (out of scope, for awareness):**
`_helpers.py:387` defines `prompt_badge = "\u2726"` — an independent inline glyph used in the `action_start` event display path (not inside `_render_fsm_diagram`). Out of scope for this enhancement.

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
- `/ll:confidence-check` - 2026-03-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c14e750-271b-434b-8be3-344981d3eff2.jsonl`
- `/ll:refine-issue` - 2026-04-01T03:52:49 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c14e750-271b-434b-8be3-344981d3eff2.jsonl`
- `/ll:confidence-check` - 2026-03-31T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c14e750-271b-434b-8be3-344981d3eff2.jsonl`
- `/ll:refine-issue` - 2026-04-01T03:34:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3c14e750-271b-434b-8be3-344981d3eff2.jsonl`
- `/ll:format-issue` - 2026-04-01T03:21:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3838f86a-9688-4708-8f33-4d8d699d79ac.jsonl`
- `/ll:capture-issue` - 2026-03-31T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6df5ee0a-f20f-4ab8-a215-3c707d7115cd.jsonl`

---

**Open** | Created: 2026-03-31 | Priority: P4
