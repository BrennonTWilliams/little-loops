---
id: ENH-2239
title: 'decisions.auto_generate config: unimplemented filter or misdocumented field'
type: ENH
priority: P3
status: done
labels:
- decisions
- config
- docs
testable: false
completed_at: 2026-06-20 04:18:42+00:00
---

## Summary

The `decisions.auto_generate` config field is documented as an issue-type prefix filter (skip BUG entries during `ll-issues decisions generate`) but the implementation ignores it entirely. The JSON Schema also describes the field differently than the guide, creating a three-way inconsistency between guide, schema, and code.

## Current Behavior

`decisions.auto_generate` is described in `docs/guides/DECISIONS_LOG_GUIDE.md` as:

> "Issue type prefixes to auto-generate entries from when `ll-issues decisions generate` runs (e.g., `["FEAT", "ENH"]` skips BUG entries)"

However, `generate_from_completed()` in `scripts/little_loops/decisions.py:382` never reads `config.decisions.auto_generate`. It iterates **all** completed issues without any prefix filter. The JSON Schema (`config-schema.json`) describes the field as "Entry IDs to auto-generate on init" — a different purpose than the guide states.

## Expected Behavior

The `decisions.auto_generate` field should have consistent, documented behavior across code, schema, and guide. Either:

- **(Option A)** The field filters by issue-type prefix in `generate_from_completed()`, matching the guide description — guide and schema updated to agree.
- **(Option B)** The field serves a different purpose (init-time stubs) — filtering description removed from the guide, config table updated to match the schema.

After resolution, configuring `decisions.auto_generate` produces the documented effect with no ambiguity.

## Motivation

Users who read the guide and configure `decisions.auto_generate: ["FEAT", "ENH"]` expecting BUG issues to be skipped will find the setting silently does nothing. The three-way inconsistency (guide ≠ schema ≠ implementation) makes it impossible to determine the field's intended purpose without source archaeology.

## Proposed Solution

**Option A**: Implement the filter in `generate_from_completed()` to honor `config.decisions.auto_generate` as issue-type prefixes (making the guide description accurate). Update the schema description to match.

**Option B**: The field is genuinely for a different purpose (init-time stubs). Remove the filtering description from the guide and update the config table to match the schema description.

Needs investigation to determine intended design before implementing.

## Scope Boundaries

- **In scope**: Resolving the discrepancy between the `decisions.auto_generate` documentation, JSON Schema description, and implementation (pick one option and align all three)
- **Out of scope**: Redesigning the broader decisions log system; adding new `auto_generate` behaviors beyond what is currently described in either the guide or schema

## Integration Map

### Files to Modify
- `scripts/little_loops/decisions.py` — `generate_from_completed()` (Option A: add prefix filter)
- `docs/guides/DECISIONS_LOG_GUIDE.md` — Configuration section (both options)
- `config-schema.json` — `decisions.auto_generate` field description (both options)
- `scripts/little_loops/config/features.py` — `DecisionsConfig.auto_generate` field docstring (Option A: add usage note)

### Dependent Files (Callers/Importers)
- N/A — `auto_generate` is currently unreferenced in `generate_from_completed()`; callers of that function do not pass the field

### Similar Patterns
- TBD — check how other `DecisionsConfig` fields are consumed in `decisions.py` for consistency

### Tests
- TBD — identify existing test coverage for `generate_from_completed()` in `scripts/tests/`

### Documentation
- `docs/guides/DECISIONS_LOG_GUIDE.md` — Configuration section must be updated regardless of option chosen

### Configuration
- `config-schema.json` — `decisions.auto_generate` description must be updated to match chosen behavior

## Implementation Steps

1. Investigate `DecisionsConfig.auto_generate` intended design (git log, original PR, comments in `features.py`)
2. Choose Option A or Option B based on original intent
3. If Option A: add prefix-filter logic in `generate_from_completed()`; update `config-schema.json` description to "Issue type prefixes to skip during generate"
4. If Option B: remove filtering description from `DECISIONS_LOG_GUIDE.md`; update config table to reflect "Entry IDs to auto-generate on init"
5. Verify guide, schema, and code are all consistent after changes
6. Add or update test coverage for the resolved behavior

## Impact

- **Priority**: P3 — Low; setting has no effect so no data loss, but silently misleading to users who configure it
- **Effort**: Small — investigation + targeted fix in one file (code or docs), plus schema update
- **Risk**: Low — no breaking change in either direction; Option A adds new filtering behavior users must opt into via config
- **Breaking Change**: No

## References

- `scripts/little_loops/decisions.py:382` — `generate_from_completed()` (no `auto_generate` reference)
- `scripts/little_loops/config/features.py:419` — `DecisionsConfig.auto_generate` field
- `config-schema.json` — schema says "Entry IDs to auto-generate on init"
- `docs/guides/DECISIONS_LOG_GUIDE.md` (Configuration section) — says "Issue type prefixes"


## Session Log
- `/ll:ready-issue` - 2026-06-20T04:11:51 - `dde47d98-d5ef-4b37-99fc-398674473e68.jsonl`
- `/ll:format-issue` - 2026-06-20T03:52:16 - `944d4086-6e38-4faf-af3e-429f91e88def.jsonl`
