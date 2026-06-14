---
id: ENH-2113
title: "Wire loops.run_defaults into ll-init project templates"
type: ENH
status: open
priority: P3
captured_at: "2026-06-13T18:07:59Z"
discovered_date: "2026-06-13"
discovered_by: capture-issue
---

# ENH-2113: Wire loops.run_defaults into ll-init project templates

## Summary

ENH-2109 added `loops.run_defaults` support to the config parser and `ll-loop run` CLI, but `ll-init` has no awareness of it. New projects get a generated `ll-config.json` that omits the section entirely, making the feature invisible until a user discovers it via docs or source.

## Current Behavior

`ll-init` generates `ll-config.json` via `scripts/little_loops/init/writers.py`. The generated config includes a `loops:` block (via `LoopsConfig` defaults) but the `run_defaults` sub-key is never written. Users have to hand-edit `ll-config.json` to opt in.

## Expected Behavior

New projects initialized with `ll-init` should have `loops.run_defaults` present in the generated config — either as a commented-out stub showing available keys, or as an explicit block with the default values (`clear: false`, `show_diagrams: null`, `mode: null`). Users should be able to discover and customize the feature without reading source.

## Motivation

`loops.run_defaults` was shipped in ENH-2109 but has zero discovery surface. The init path is the primary onboarding touchpoint for new projects; omitting the section means the feature effectively doesn't exist for most users. A commented-out stub costs nothing and acts as inline documentation.

## Proposed Solution

In `scripts/little_loops/init/writers.py` (or wherever the `ll-config.json` skeleton is assembled), add a `run_defaults` sub-block under `loops:`. Options:

1. **Explicit defaults** — write the block with all three fields at their default values (`clear: false`, `show_diagrams: null`, `mode: null`). Simplest, always present, but adds noise to minimal configs.
2. **Commented stub** — emit `# loops.run_defaults: { clear: false, show_diagrams: null, mode: null }` as a JSON comment alternative (not valid JSON; only works if the config format allows comments, e.g. YAML or JSONC).
3. **Schema-driven** — generate the block dynamically from `config-schema.json`'s `loops.run_defaults` object definition. Most robust but most complex.

Option 1 is simplest and consistent with how other optional config sections are handled.

Also check project-type templates in `templates/` (e.g. `python-generic.json`, `generic.json`) to see if they include a `loops:` stanza that also needs updating.

## Integration Map

### Files to Modify
- `scripts/little_loops/init/writers.py` — wherever the `ll-config.json` skeleton is written
- `templates/python-generic.json`, `templates/generic.json`, etc. — if they contain a `loops:` stanza

### Dependent Files (Callers/Importers)
- `scripts/little_loops/init/core.py` — calls writers; no change likely needed
- `scripts/little_loops/cli/init.py` — entry point; no change needed

### Similar Patterns
- `scripts/little_loops/config/features.py:LoopsConfig.from_dict()` — already handles `run_defaults` absence gracefully; no change needed
- Other `LoopsConfig` fields (`loops_dir`, `queue_wait_timeout_seconds`, `glyphs`) to understand how they appear in generated configs

### Tests
- `scripts/tests/test_init_writers.py` (if it exists) — add assertion that generated config includes `loops.run_defaults`
- `scripts/tests/test_loop_cli_defaults.py` — existing tests for the config parsing layer; no change needed

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — already documents `loops.run_defaults`; may want to note it appears in generated configs

### Configuration
- `config-schema.json` — already has `loops.run_defaults` schema; no change needed

## Implementation Steps

1. Identify where `ll-init` assembles the `ll-config.json` skeleton in `writers.py`
2. Add `run_defaults` sub-block under `loops:` with explicit defaults
3. Check `templates/*.json` for any `loops:` stanzas and update those too
4. Add/update tests verifying the generated config includes `loops.run_defaults`
5. Verify `ll-init --dry-run` output reflects the new section

## Impact

- **Priority**: P3 - Feature is usable but undiscoverable; low urgency
- **Effort**: Small - Single file edit plus tests; no new logic
- **Risk**: Low - Init writer change; no runtime behavior change
- **Breaking Change**: No

## Success Metrics

- Generated `ll-config.json` (from `ll-init`) contains a `loops.run_defaults` block with all three default keys (`clear`, `show_diagrams`, `mode`)
- `ll-init --dry-run` output reflects the new section
- Tests in `scripts/tests/test_init_writers.py` assert the generated config includes `loops.run_defaults`
- No regression in existing `ll-loop run` behavior when `run_defaults` is present at defaults

## Scope Boundaries

- Does not change `LoopRunDefaults` defaults or validation logic
- Does not change how `ll-loop run` reads the config
- Does not add a TUI prompt for `run_defaults` during `ll-init` interactive mode (that's a separate concern)

## Related Key Documentation

- `docs/guides/LOOPS_GUIDE.md` — documents `loops.run_defaults` config keys; may want to note these appear in generated configs after this fix
- ENH-2109 — the issue that introduced `loops.run_defaults` to the config parser and `ll-loop run` CLI

## Labels

`enhancement`, `ll-init`, `loops`, `captured`

## Verification Notes

2026-06-13: Verified. `scripts/little_loops/init/writers.py` exists but has zero references to `run_defaults` or `LoopsConfig` — gap confirmed. Implementation steps are accurate. Ready to implement.

## Session Log
- `/ll:verify-issues` - 2026-06-14T00:12:44 - `dcbaf608-eff5-4e7b-8a64-4d13a266c421.jsonl`
- `/ll:format-issue` - 2026-06-13T18:12:01 - `c9085d04-ffdf-4c69-980f-055827eceb22.jsonl`

- `/ll:capture-issue` - 2026-06-13T18:07:59Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/68161d6f-aa46-4b19-8309-5c8794319dc2.jsonl`

---

## Status

**Open** | Created: 2026-06-13 | Priority: P3
