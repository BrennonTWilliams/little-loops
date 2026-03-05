---
id: ENH-584
priority: P3
status: completed
discovered_date: 2026-03-04
resolved_date: 2026-03-04
discovered_by: capture-issue
confidence_score: 95
outcome_confidence: 71
---

# ENH-584: Make CLI Color Output Configurable

## Summary

Add a `cli.color` boolean setting to `.claude/ll-config.json` (default: `true`) that controls whether ANSI color codes are emitted in CLI terminal output across all `ll-*` tools. Also add a `cli.colors` sub-object that lets users override individual ANSI color codes for log levels (`logger.py`) and issue display categories (`cli/output.py` priority and type dicts). Also replace all existing red color usage in CLI output with orange.

## Current Behavior

All `ll-*` CLI tools (`ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`) emit ANSI color codes without a config-driven toggle. The `cli/output.py` layer already checks `NO_COLOR` env var and TTY detection (`_USE_COLOR: bool = sys.stdout.isatty() and os.environ.get("NO_COLOR", "") == ""`), but `logger.py` does not — it defaults `use_color=True` unconditionally. There is no first-class `ll-config.json` key to suppress colors or override individual color codes. All colors are hardcoded: `Logger` defines CYAN/GREEN/YELLOW/RED/MAGENTA/GRAY constants; `cli/output.py` has `PRIORITY_COLOR` and `TYPE_COLOR` dicts with fixed ANSI codes.

## Expected Behavior

When `cli.color: false` is set in `ll-config.json`, or when the `NO_COLOR` environment variable is set, all `ll-*` CLI tools suppress ANSI escape sequences and emit plain text. When `cli.color` is omitted (defaults to `true`) and `NO_COLOR` is unset, color output is unchanged. `logger.py` should also respect `NO_COLOR`. When `cli.colors` sub-keys are present, their values override the default ANSI codes for the corresponding log level or issue category — unspecified keys retain their defaults.

## Motivation

ENH-582 improved CLI output polish using stdlib utilities (`rich`, `shutil.get_terminal_size`, etc.), but color output is always on. Users in CI environments, terminals without color support, or who prefer plain output have no way to disable colors without environment workarounds like `NO_COLOR`. A first-class config toggle gives users direct control.

## Proposed Solution

- `ll-config.json` gains a new `cli` section:
  ```json
  {
    "cli": {
      "color": true,
      "colors": {
        "logger": {
          "info": "36",
          "success": "32",
          "warning": "33",
          "error": "38;5;208"
        },
        "priority": {
          "P0": "38;5;208;1",
          "P1": "38;5;208",
          "P2": "33",
          "P3": "0",
          "P4": "2",
          "P5": "2"
        },
        "type": {
          "BUG": "38;5;208",
          "FEAT": "32",
          "ENH": "34"
        }
      }
    }
  }
  ```
- `cli.color` defaults to `true` (no behavior change for existing users); `false` suppresses all ANSI output.
- `cli.colors` is optional; any omitted sub-key retains its default value. Values are raw ANSI SGR parameter strings (e.g. `"32"`, `"38;5;208"`, `"1;34"`).
- Should respect the existing `NO_COLOR` env var convention as an additional override (takes priority over `cli.color: true`).

## Implementation Steps

1. Add `cli.color` and `cli.colors` to `config-schema.json` — boolean with default `true`, and a nested object with `logger`, `priority`, and `type` sub-objects containing ANSI SGR string values.
2. Add `CliColorsConfig` and `CliConfig` dataclasses to `little_loops/config.py`; expose via `BRConfig.cli`.
3. Pass `cli.color` into `cli/output.py` (`_USE_COLOR` computation) and `logger.py` (`use_color` default) — disable color when `False`.
4. Ensure `NO_COLOR` env var also disables color (industry convention, overrides config).
5. Replace red (`\033[31m` / `"31"` / `"31;1"`) with orange using ANSI 256-color code `38;5;208` (e.g. `"\033[38;5;208m"` in `logger.py`, `"38;5;208"` / `"38;5;208;1"` in `cli/output.py` dicts). Note: `\033[33m` is already used for YELLOW, so standard 16-color has no pure orange — 256-color is required.
6. Merge `cli.colors.logger` values into `Logger` color constants at instantiation; merge `cli.colors.priority` and `cli.colors.type` into `PRIORITY_COLOR` / `TYPE_COLOR` dicts at module load (or pass via config object).
7. Update `docs/reference/API.md` and `config-schema.json` descriptions.

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | CLI tool structure and shared config loading |
| `docs/reference/API.md` | Config schema reference |
| `.claude/CLAUDE.md` | Dev conventions and test commands |

## Acceptance Criteria

- [ ] `config-schema.json` documents `cli.color` (boolean, default `true`) and `cli.colors` (nested object with `logger`, `priority`, `type` sub-objects)
- [ ] Setting `cli.color: false` suppresses all ANSI codes in `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop` output
- [ ] `NO_COLOR=1` env var disables color regardless of config value
- [ ] Existing behavior unchanged when `cli.color` and `cli.colors` are omitted (defaults preserved)
- [ ] Setting a `cli.colors` sub-key overrides only that color; unspecified keys keep their defaults
- [ ] Tests cover color-enabled, color-disabled, and custom-color code paths

## Scope Boundaries

- **In scope**: `cli.color` boolean config key; `cli.colors` sub-object for overriding individual ANSI codes (logger levels, priority labels, type labels); respecting `NO_COLOR` env var as an override
- **Out of scope**: Per-tool color configuration (all tools share the same setting); output verbosity controls; 24-bit (truecolor) ANSI support; colors for output elements beyond `logger.py` log levels and `cli/output.py` priority/type dicts

## Impact

- **Priority**: P3 — Quality-of-life improvement for CI users and terminals without color support; does not block core functionality
- **Effort**: Small-Medium — Adds `cli.color` toggle and `cli.colors` override map; threads both through `Logger` and `cli/output.py`; no new dependencies
- **Risk**: Low — Default is `true` (no behavior change for existing users); change is additive and isolated to output rendering
- **Breaking Change**: No

## API/Interface

New `ll-config.json` config keys (all optional; shown with defaults):

```json
{
  "cli": {
    "color": true,
    "colors": {
      "logger": {
        "info": "36",
        "success": "32",
        "warning": "33",
        "error": "38;5;208"
      },
      "priority": {
        "P0": "38;5;208;1",
        "P1": "38;5;208",
        "P2": "33",
        "P3": "0",
        "P4": "2",
        "P5": "2"
      },
      "type": {
        "BUG": "38;5;208",
        "FEAT": "32",
        "ENH": "34"
      }
    }
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
    },
    "colors": {
      "type": "object",
      "description": "Override individual ANSI SGR color codes. Values are raw SGR parameter strings (e.g. \"32\", \"38;5;208\").",
      "properties": {
        "logger": {
          "type": "object",
          "description": "Colors for Logger log-level output.",
          "properties": {
            "info":    { "type": "string", "default": "36" },
            "success": { "type": "string", "default": "32" },
            "warning": { "type": "string", "default": "33" },
            "error":   { "type": "string", "default": "38;5;208" }
          }
        },
        "priority": {
          "type": "object",
          "description": "Colors for issue priority labels (P0–P5).",
          "properties": {
            "P0": { "type": "string", "default": "38;5;208;1" },
            "P1": { "type": "string", "default": "38;5;208" },
            "P2": { "type": "string", "default": "33" },
            "P3": { "type": "string", "default": "0" },
            "P4": { "type": "string", "default": "2" },
            "P5": { "type": "string", "default": "2" }
          }
        },
        "type": {
          "type": "object",
          "description": "Colors for issue type labels (BUG, FEAT, ENH).",
          "properties": {
            "BUG":  { "type": "string", "default": "38;5;208" },
            "FEAT": { "type": "string", "default": "32" },
            "ENH":  { "type": "string", "default": "34" }
          }
        }
      }
    }
  }
}
```

## Integration Map

### Files to Modify
- `config-schema.json` — add `cli.color` and `cli.colors` (with `logger`, `priority`, `type` sub-objects)
- `scripts/little_loops/config.py` — add `CliColorsLoggerConfig`, `CliColorsPriorityConfig`, `CliColorsTypeConfig`, `CliColorsConfig`, and `CliConfig` dataclasses; expose via `BRConfig.cli`
- `scripts/little_loops/cli/output.py` — fold `cli.color` into `_USE_COLOR`; merge `cli.colors.priority` and `cli.colors.type` into `PRIORITY_COLOR` / `TYPE_COLOR` dicts
- `scripts/little_loops/logger.py` — add `NO_COLOR` env var check; accept `CliColorsConfig` to override color constants at init

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/issues/list_cmd.py` — imports `colorize` from `cli/output.py`
- `scripts/little_loops/parallel/orchestrator.py` — instantiates `Logger(verbose=verbose)`
- `scripts/little_loops/issue_manager.py` — instantiates `Logger(verbose=verbose)`
- `scripts/little_loops/cli/sync.py` — instantiates `Logger`
- `scripts/little_loops/cli/messages.py` — instantiates `Logger`
- `scripts/little_loops/cli/parallel.py` — instantiates `Logger`
- `scripts/little_loops/cli/sprint/run.py`, `show.py`, `create.py`, `edit.py`, `manage.py` — all instantiate `Logger`
- `scripts/little_loops/cli/loop/__init__.py` — instantiates `Logger`

### Similar Patterns
- `BRConfig` section configs follow the `@dataclass` + `from_dict` pattern (see `CommandsConfig`, `ScanConfig`, `SprintsConfig`)
- Config-driven feature flags: `context_monitor.enabled`, `scratch_pad.enabled`, `commands.confidence_gate.enabled`

### Tests
- `scripts/tests/test_cli_output.py` — existing tests for `colorize`, `_USE_COLOR`; add config-driven color toggle and custom color override tests
- `scripts/tests/test_logger.py` — add `NO_COLOR` env var suppression test and custom color override test
- `scripts/tests/test_config.py` — add `CliConfig` and `CliColorsConfig` parsing tests (full, partial, empty)

### Documentation
- `docs/reference/API.md` — document `cli.color` config option

### Configuration
- `config-schema.json` — primary change location

## Labels

`enhancement`, `cli`, `config`, `captured`

## Resolution

All acceptance criteria met:
- `config-schema.json` documents `cli.color` (boolean, default `true`) and `cli.colors` (nested object with `logger`, `priority`, `type` sub-objects)
- `CliConfig`, `CliColorsConfig`, and sub-configs added to `little_loops/config.py` with `BRConfig.cli` property
- `logger.py` now checks `NO_COLOR` env var by default and accepts `CliColorsConfig` for color overrides; `RED`/`ORANGE` constants changed to 256-color orange (`38;5;208`)
- `cli/output.py` `PRIORITY_COLOR`/`TYPE_COLOR` dicts updated to use orange (replacing red); `configure_output(config)` function added
- `configure_output` called in all 4 entry points: `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-loop`
- Tests added to `test_config.py`, `test_logger.py`, `test_cli_output.py`; 3273 tests pass
- `docs/reference/API.md` updated with `CliConfig` reference and `cli.color` documentation

### Files Modified
- `config-schema.json` — added `cli` section
- `scripts/little_loops/config.py` — added 5 new dataclasses + `BRConfig.cli` property
- `scripts/little_loops/logger.py` — NO_COLOR check, orange constant, CliColorsConfig support
- `scripts/little_loops/cli/output.py` — orange defaults, `configure_output()` function
- `scripts/little_loops/cli/auto.py` — `configure_output(config.cli)` call
- `scripts/little_loops/cli/parallel.py` — `configure_output(config.cli)` call
- `scripts/little_loops/cli/sprint/__init__.py` — `configure_output(config.cli)` call
- `scripts/little_loops/cli/loop/__init__.py` — `configure_output(config.cli)` call
- `scripts/tests/test_config.py` — CliConfig/CliColorsConfig tests
- `scripts/tests/test_logger.py` — NO_COLOR and custom colors tests
- `scripts/tests/test_cli_output.py` — configure_output and orange defaults tests
- `docs/reference/API.md` — CliConfig reference and Logger constructor update

## Session Log
- `/ll:capture-issue` - 2026-03-04T21:57:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d1b61e9b-5498-4fe4-9f8c-9e3d2dd5ded4.jsonl`
- `/ll:format-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6096add-5d47-4995-a7f1-581d0e6a5ee7.jsonl`
- `/ll:ready-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/176b337e-9885-4dcb-8bf0-7199f3e2df7f.jsonl`
- `/ll:confidence-check` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0aa7e0bf-0aca-4b24-9aba-9165144f189e.jsonl`
- `/ll:manage-issue` - 2026-03-04T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current-session.jsonl`

---

**Open** | Created: 2026-03-04 | Priority: P3
