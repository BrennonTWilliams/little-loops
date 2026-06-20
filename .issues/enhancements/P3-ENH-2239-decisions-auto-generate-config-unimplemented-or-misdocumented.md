---
id: ENH-2239
title: "decisions.auto_generate config: unimplemented filter or misdocumented field"
type: ENH
priority: P3
status: open
labels: [decisions, config, docs]
---

## Problem

`decisions.auto_generate` is described in `docs/guides/DECISIONS_LOG_GUIDE.md` as:

> "Issue type prefixes to auto-generate entries from when `ll-issues decisions generate` runs (e.g., `["FEAT", "ENH"]` skips BUG entries)"

However, `generate_from_completed()` in `scripts/little_loops/decisions.py:382` never reads `config.decisions.auto_generate`. It iterates **all** completed issues without any prefix filter. The JSON Schema (`config-schema.json`) describes the field as "Entry IDs to auto-generate on init" — a different purpose than the guide states.

## Impact

Users who configure `decisions.auto_generate: ["FEAT", "ENH"]` expecting BUG issues to be skipped during `ll-issues decisions generate` will find the setting has no effect.

## Proposed Solution

**Option A**: Implement the filter in `generate_from_completed()` to honor `config.decisions.auto_generate` as issue-type prefixes (making the guide description accurate). Update the schema description to match.

**Option B**: The field is genuinely for a different purpose (init-time stubs). Remove the filtering description from the guide and update the config table to match the schema description.

Needs investigation to determine intended design before implementing.

## References

- `scripts/little_loops/decisions.py:382` — `generate_from_completed()` (no `auto_generate` reference)
- `scripts/little_loops/config/features.py:419` — `DecisionsConfig.auto_generate` field
- `config-schema.json` — schema says "Entry IDs to auto-generate on init"
- `docs/guides/DECISIONS_LOG_GUIDE.md` (Configuration section) — says "Issue type prefixes"
