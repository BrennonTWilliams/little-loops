---
id: ENH-2762
type: enhancement
priority: P4
status: done
captured_at: '2026-07-24T19:36:28Z'
completed_at: '2026-07-25T06:38:29Z'
discovered_date: 2026-07-24
discovered_by: capture-issue
parent: EPIC-2765
confidence_score: 100
outcome_confidence: 88
score_complexity: 21
score_test_coverage: 22
score_ambiguity: 22
score_change_surface: 23
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
- `scripts/little_loops/cli/doctor.py` — `main_doctor` (line 115, guard at
  161-163), `_print_report` (line 83, JSON branch 89-99),
  `_print_capture_section` (line 26), `_print_issues_section` (line 48)

### Dependent Files (Callers/Importers)
- Any automation parsing `ll-doctor --json` (additive keys, so backward compatible)

### Similar Patterns
- Other `--json`-capable ll CLIs (`ll-issues show --json`, `ll-session`) for key-naming convention

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` (line 131) + `cmd_show()` (line 818) — the exact pure-dict-helper split this issue's Proposed Solution asks for: one dict-returning function, consumed by both `print_json(fields)` and the text renderer.
- `scripts/little_loops/cli/output.py:print_json()` (lines 213-215) — shared `json.dumps(data, indent=2)` helper already used by `show.py`. `doctor.py`'s `_print_report` currently inlines `json.dumps(...)` directly (line 98) instead of calling this helper — switch to `print_json()` for consistency while making this change.

### Tests
- `scripts/tests/test_cli_doctor.py` — assert JSON parity with the text sections

### Documentation
- `docs/reference/HOST_COMPATIBILITY.md:308-312`
- `docs/reference/CLI.md:264-265`
- `docs/codex/README.md:42` — states ll-doctor "also reports" capture state

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` (~line 8711-8741, `CapabilityReport` section) — currently documents `ll-doctor --json` as a 1:1 serialization of the `CapabilityReport` dataclass (`host`, `binary`, `version`, `capabilities`). Once `analytics_capture`/`issues` keys are added from `cfg` (not from `CapabilityReport`), this description becomes stale and should note the JSON payload is a superset of the dataclass.
- `docs/ARCHITECTURE.md:875` — same `CapabilityReport` table entry ("holds `host`, `binary`, `version`, and `capabilities`"), same staleness once JSON output includes config-derived sections.

### Configuration
- Reads `analytics.capture` and `issues` from `.ll/ll-config.json`; no new keys.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Exact current structure** (confirmed by direct read of `doctor.py`):
  - `_print_capture_section(capture: object)` (lines 26-45) mixes `getattr`
    reads and `print()` in the same statements — there is no intermediate
    dict today. It reads 5 of `AnalyticsCaptureConfig`'s 7 fields: `skills`,
    `cli_commands`, `corrections`, `file_events`, `correction_patterns`.
    `capture.usage_events` and `capture.hooks` (both present on
    `AnalyticsCaptureConfig`, `scripts/little_loops/config/features.py:622-623`)
    are **not** currently read or printed by this function at all — the
    Proposed Solution's `analytics_capture` JSON shape should decide whether
    to also surface these two previously-unsurfaced fields or stay scoped to
    the 5 already in text output (Scope Boundaries says "emitting the
    *existing* ... state", which argues for staying at 5).
  - `_print_issues_section(issues_cfg: object)` (lines 48-57) similarly reads
    only `auto_commit` and `auto_commit_prefix` off `IssuesConfig` — a
    narrow, auto-commit-scoped view, not the full `IssuesConfig` (which also
    has `base_dir`, `categories`, `priorities`, `duplicate_detection`,
    `next_issue`, etc. — `features.py:191-243`). This matches the issue's
    proposed `{"issues": {"auto_commit": bool, "auto_commit_prefix": str}}`
    shape exactly.
  - `_print_report`'s JSON branch (lines 89-99) is the only existing
    `json.dumps` call site in the file and builds its `data` dict inline
    (not via a separate pure-function helper) — `{host, binary, version,
    capabilities}`. There is **no `"hooks"` key** in current JSON output;
    `test_cli_doctor.py:275` explicitly asserts `"hooks" not in data` per a
    resolved sibling issue (BUG-2760, `CapabilityReport.hooks` was never
    populated and the dead field was removed). The issue summary's mention
    of "hooks" among CapabilityReport fields is stale — don't reintroduce it.
  - Config resolution: `cfg.analytics_capture` and `cfg.issues` are accessed
    as strongly-typed dataclass properties on `BRConfig`
    (`scripts/little_loops/config/core.py:255`, `:265-268`), not via a
    generic dot-path resolver — no `ll-config get`-style indirection to
    worry about.

- **Reusable pattern for the pure-dict-helper refactor**: `ll-issues show`
  already does exactly this split —
  `scripts/little_loops/cli/issues/show.py:_parse_card_fields()` (line 131)
  is a pure function returning a flat dict; `cmd_show()` (line 818) branches
  on `args.json` to call `print_json(fields)` (shared helper,
  `scripts/little_loops/cli/output.py:213-215`, `json.dumps(data, indent=2)`)
  or pass the same dict to a text renderer (`_render_card()`, line 593). Use
  this shape: extract `_capture_section_data(capture) -> dict` and
  `_issues_section_data(issues_cfg) -> dict` from the current print
  functions, have both `_print_capture_section`/`_print_issues_section` and
  the new JSON path consume them.

- **Existing test scaffolding to extend, not duplicate**: `test_cli_doctor.py`
  already has `test_json_output_flag()` (line 247-275, the pattern to copy —
  captures stdout via a `_capture_print()` helper at line 37-40, then
  `json.loads()`s it) plus `test_analytics_capture_section_all_enabled()`
  (line 334-359) and `test_issues_auto_commit_section_enabled()` (line
  387-414), which are currently **text-mode-only** and mock
  `BRConfig`/`mock_config.analytics_capture.*`/`mock_config.issues.*`. The
  natural parity test is a new
  `test_json_output_includes_analytics_capture_and_issues_sections` that
  reuses that same `mock_config` fixture shape but asserts
  `data["analytics_capture"]`/`data["issues"]` keys after `json.loads()`,
  mirroring `test_json_output_flag`'s structure.

- **Sibling/parent issue context** (same EPIC-2765): `EPIC-2765` sequences
  ENH-2762 to land early to establish text/JSON parity before later doctor
  work. `BUG-2760` (done) already removed the stray never-populated `hooks`
  JSON key — this issue's fix should not resurrect it. `FEAT-2763` (open)
  depends on this issue landing first.

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

## Resolution

Extracted `_capture_section_data()` / `_issues_section_data()` pure-dict helpers
in `scripts/little_loops/cli/doctor.py` from `_print_capture_section` /
`_print_issues_section`, and wired them into `_print_report`'s JSON branch
under `analytics_capture`/`issues` keys (also switched the JSON branch to the
shared `print_json()` helper). Fixed `test_cli_doctor.py`'s bare
`patch("little_loops.config.BRConfig")` JSON-mode tests (their `MagicMock`
attributes broke `json.dumps` once real section data was added) and added
`test_json_output_includes_analytics_capture_and_issues_sections` as the
text/JSON parity test. Updated `HOST_COMPATIBILITY.md`, `CLI.md`, `API.md`,
and `ARCHITECTURE.md` to describe the JSON payload as a superset of
`CapabilityReport`.

## Session Log
- `/ll:manage-issue` - 2026-07-25T06:38:00Z - `3f3f87aa-97aa-4889-96fb-0a8861ac8aa1.jsonl`
- `/ll:confidence-check` - 2026-07-25T00:00:00Z - `e8e18f2e-b0c3-47b1-a87d-02e78ead3883.jsonl`
- `/ll:wire-issue` - 2026-07-25T06:29:47 - `3ff07c02-1c11-4ec5-8132-d486f96c3a23.jsonl`
- `/ll:refine-issue` - 2026-07-25T06:25:19 - `50ef7031-b157-4db4-9458-e09c986da5de.jsonl`
- `/ll:capture-issue` - 2026-07-24T19:36:28Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00041c0b-3526-41ec-b743-a686380c429a.jsonl`

---

## Status

**Open** | Created: 2026-07-24 | Priority: P4
