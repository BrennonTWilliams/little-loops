---
id: ENH-2762
type: enhancement
priority: P4
status: open
captured_at: "2026-07-24T19:36:28Z"
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
---

# ENH-2762: ll-doctor --json omits Analytics Capture and Issues sections

## Summary

`ll-doctor --json` emits only the `CapabilityReport` fields (host, binary,
version, capabilities, hooks). The "Analytics Capture" and "Issues" config-state
sections are printed exclusively on the human-readable path — `main_doctor`
guards both `_print_capture_section` and `_print_issues_section` behind
`if not args.json`. Machine consumers get a strictly smaller report than humans.

## Current Behavior

- Text mode prints capabilities + `analytics.capture` state + `issues.auto_commit` state.
- JSON mode prints capabilities only.
- Any automation wanting the config state must either parse the human table or
  re-resolve config itself.

## Expected Behavior

`--json` is a superset-equivalent of the text output: the same sections, in
machine-readable form, under stable keys (e.g. `analytics_capture` and `issues`
alongside `capabilities`).

## Motivation

`--json` exists for automation, and `docs/reference/HOST_COMPATIBILITY.md`
describes it as the "machine-readable CapabilityReport." Today it silently
drops half the diagnostic surface, so anything scripting a preflight check has
to shell out again or scrape text. Fixing it is a small change that makes the
flag honest.

## Scope Boundaries

**In scope**: emitting the existing capture and issues config state under
`--json`, plus schema-shape documentation.

**Out of scope**: adding *new* config sections to the report (see the broader
scope expansion tracked separately), and changing the text output format.

## API/Interface

```python
# Current --json payload
{"host": ..., "binary": ..., "version": ..., "capabilities": [...], "hooks": [...]}

# Proposed
{..., "analytics_capture": {"skills": [...], "cli_commands": [...],
                            "corrections": bool, "file_events": bool,
                            "correction_patterns": [...]},
      "issues": {"auto_commit": bool, "auto_commit_prefix": str}}
```

## Proposed Solution

Extract the field-gathering out of `_print_capture_section` /
`_print_issues_section` into small pure functions returning plain dicts, have
both the text and JSON paths consume them, and drop the `if not args.json`
guard. This keeps the two outputs from drifting again, which is the actual root
cause — they are currently two independent code paths with no shared source.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/doctor.py` — `main_doctor`, `_print_report`,
  `_print_capture_section`, `_print_issues_section`

### Dependent Files (Callers/Importers)
- Any automation parsing `ll-doctor --json` (additive keys, so backward compatible)

### Similar Patterns
- Other `--json`-capable ll CLIs (`ll-issues show --json`, `ll-session`) for key-naming convention

### Tests
- `scripts/tests/test_cli_doctor.py` — assert JSON parity with the text sections

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:308-312`
- `docs/reference/CLI.md:264-265`
- `docs/codex/README.md:42` — states ll-doctor "also reports" capture state

### Configuration
- Reads `analytics.capture` and `issues` from `.ll/ll-config.json`; no new keys.

## Implementation Steps

1. Factor the section data-gathering into dict-returning helpers.
2. Point both output paths at the helpers; remove the `not args.json` guard.
3. Add a parity test so a future section can't be added to text only.
4. Document the JSON shape.

## Impact

- **Priority**: P4 - Small ergonomic gap; nothing is wrong, just incomplete.
- **Effort**: Small - One module, additive keys.
- **Risk**: Low - Purely additive to the JSON payload.
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/reference/HOST_COMPATIBILITY.md` | Describes `--json` as the machine-readable report |
| `docs/reference/CONFIGURATION.md:531` | `analytics.capture` gating that ll-doctor reports |

## Session Log
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P4
