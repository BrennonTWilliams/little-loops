---
id: ENH-584
priority: P3
status: active
discovered_date: 2026-03-04
discovered_by: capture-issue
---

# ENH-584: Make CLI Color Output Configurable

## Summary

Add a `cli.color` boolean setting to `.claude/ll-config.json` (default: `true`) that controls whether ANSI color codes are emitted in CLI terminal output across all `ll-*` tools.

## Current Behavior

All `ll-*` CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`) emit ANSI color codes unconditionally. There is no configuration option to disable colors — users in CI environments or terminals without color support must rely on external workarounds (e.g., piping through a strip-ansi filter or setting `NO_COLOR` as an undocumented convention that may or may not be respected).

## Motivation

ENH-582 improved CLI output polish using stdlib utilities (`rich`, `shutil.get_terminal_size`, etc.), but color output is always on. Users in CI environments, terminals without color support, or who prefer plain output have no way to disable colors without environment workarounds like `NO_COLOR`. A first-class config toggle gives users direct control.

## Proposed Solution

- `ll-config.json` gains a new `cli` section:
  ```json
  {
    "cli": {
      "color": true
    }
  }
  ```
- Default is `true` (no behavior change for existing users).
- When set to `false`, all CLI tools suppress ANSI escape sequences in output.
- Should respect the existing `NO_COLOR` env var convention as an additional override.

## Implementation Steps

1. Add `cli.color` to `config-schema.json` as a boolean with default `true`.
2. Read the setting in the shared config-loading path (e.g., `little_loops/config.py` or equivalent).
3. Pass the flag into the output/display layer introduced by ENH-582 — disable color when `False`.
4. Ensure `NO_COLOR` env var also disables color (industry convention).
5. Update `docs/reference/API.md` and `config-schema.json` descriptions.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI tool structure and shared config loading |
| `docs/reference/API.md` | Config schema reference |
| `.claude/CLAUDE.md` | Dev conventions and test commands |

## Acceptance Criteria

- [ ] `config-schema.json` documents `cli.color` with type `boolean`, default `true`
- [ ] Setting `cli.color: false` suppresses all ANSI codes in `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop` output
- [ ] `NO_COLOR=1` env var disables color regardless of config value
- [ ] Existing behavior unchanged when `cli.color` is omitted (defaults to `true`)
- [ ] Tests cover color-enabled and color-disabled code paths

## Scope Boundaries

- **In scope**: `cli.color` boolean config key in `ll-config.json`; respecting `NO_COLOR` env var as an override
- **Out of scope**: Per-tool color configuration (all tools share the same setting); custom color theming; output verbosity controls; color level distinctions (256-color vs 24-bit ANSI)

## Impact

- **Priority**: P3 — Quality-of-life improvement for CI users and terminals without color support; does not block core functionality
- **Effort**: Small — Adds one config key; threads a flag through the display layer introduced by ENH-582; no new dependencies
- **Risk**: Low — Default is `true` (no behavior change for existing users); change is additive and isolated to output rendering
- **Breaking Change**: No

## API/Interface

New `ll-config.json` config key:

```json
{
  "cli": {
    "color": true
  }
}
```

`config-schema.json` addition:

```json
"cli": {
  "type": "object",
  "properties": {
    "color": {
      "type": "boolean",
      "default": true,
      "description": "Emit ANSI color codes in CLI output. Set to false for CI or plain-text environments."
    }
  }
}
```

## Integration Map

### Files to Modify
- `config-schema.json` — add `cli.color` key with type, default, and description
- `scripts/little_loops/config.py` (or equivalent config-loading module) — read and expose `cli.color`
- Output/display layer introduced by ENH-582 — accept and apply `color` flag when initializing `rich.console.Console` or equivalent

### Dependent Files (Callers/Importers)
- TBD — use grep to find display/output helpers: `grep -r "rich\|Console\|get_terminal_size" scripts/`

### Similar Patterns
- TBD — check for other config-driven feature flags: `grep -r "config\." scripts/little_loops/`

### Tests
- TBD — identify or create test files covering color-enabled and color-disabled output paths

### Documentation
- `docs/reference/API.md` — document `cli.color` config option

### Configuration
- `config-schema.json` — primary change location

## Labels

`enhancement`, `cli`, `config`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-04T21:57:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1b61e9b-5498-4fe4-9f8c-9e3d2dd5ded4.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6096add-5d47-4995-a7f1-581d0e6a5ee7.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P3
