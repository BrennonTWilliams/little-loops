---
id: ENH-1915
title: User-extensible correction detection phrases via analytics.capture.correction_patterns
type: ENH
priority: P4
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T21:38:03Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [EPIC-1707, ENH-1831, ENH-1887]
labels:
  - history-db
  - configurability
---

# ENH-1915: User-extensible correction detection phrases

## Summary

Correction detection (ENH-1831/1887, done) uses a fixed built-in regex/phrase
set. Expose a user-extensible list, `analytics.capture.correction_patterns`
(list[str]), that is **appended to** the built-ins so projects can teach the
detector their own correction phrasings without forking code.

## Current Behavior

The correction detector uses a fixed built-in regex/phrase set. Projects with
domain-specific correction language ("not quite", "actually use X instead",
etc.) have those corrections silently missed — no mechanism exists to extend
the phrase set without forking code.

## Expected Behavior

Users add `analytics.capture.correction_patterns: ["not quite", "actually use X
instead"]` to `.ll/ll-config.json`. Configured patterns are appended to the
built-ins; built-ins always remain active. Absent config → zero behavior change.
Malformed config (non-list or non-string items) → degrades gracefully to
built-ins only, never raises.

## Motivation

The `user_corrections` corpus is the EPIC's core signal, but the detector only
recognizes built-in phrasings. Teams with domain-specific correction language
("not quite", "actually use X instead", etc.) silently lose those corrections.
Making the phrase set extensible improves capture recall — a write-side quality
lever, so it belongs in the `analytics.*` (capture/write) namespace per the
ratified split.

## API/Interface

- `analytics.capture.correction_patterns` — list[str], default `[]`, appended to
  the built-in patterns (built-ins always remain active).

## Implementation Steps

1. `config-schema.json`: add `correction_patterns` to
   `analytics.capture.properties` (note: `analytics.capture` is
   `additionalProperties: false`, current keys `cli_commands`, `corrections`,
   `file_events`, `skills` — so a schema edit **is** required here; this issue
   does not touch the `history` object, hence it does not depend on ENH-1913).
2. `AnalyticsCaptureConfig.from_dict`: read `correction_patterns` leniently
   (default `[]`).
3. In the correction-detection path, compile built-ins + configured patterns into
   the active matcher.

## Acceptance Criteria

- Absent config → built-in behavior unchanged.
- Configured patterns are additive (never replace built-ins); malformed config
  degrades to built-ins, never raises.

## Scope Boundaries

- **In scope**: `correction_patterns` key under `analytics.capture` in
  `config-schema.json`; `AnalyticsCaptureConfig.from_dict` reading the key
  leniently (default `[]`); compiling built-ins + configured patterns into the
  active matcher.
- **Out of scope**: Replacing or disabling built-in patterns; changes to the
  `history` namespace (ENH-1913); file-event tool→path map (ENH-1832,
  intentionally not filed); any UI/GUI for managing patterns.

## Integration Map

### Files to Modify
- `config-schema.json` — add `correction_patterns` to `analytics.capture.properties` (`additionalProperties: false` block)
- `scripts/little_loops/analytics/capture_config.py` (or wherever `AnalyticsCaptureConfig` is defined) — add `correction_patterns: list[str]` field, read leniently from dict (default `[]`)
- Correction-detection path — compile built-ins + configured patterns into active matcher (find via `grep -r "correction_pattern\|built.in" scripts/`)

### Dependent Files (Callers/Importers)
- TBD — `grep -r "AnalyticsCaptureConfig" scripts/` to find call sites that construct or pass the config object

### Similar Patterns
- `analytics.capture.cli_commands`, `analytics.capture.skills` — existing boolean gates in same config block; follow the same lenient `from_dict` pattern

### Tests
- Add test: configured patterns are additive (both built-in and custom fire)
- Add test: malformed config (non-list, non-string items) degrades to built-ins only without raising

### Documentation
- N/A — internal config key; no user-facing docs need updating

### Configuration
- `config-schema.json` (`analytics.capture.correction_patterns`)

## Notes

- Write-side namespace (`analytics.*`), so does **not** depend on ENH-1913 — but
  it is **not** schema-free (it edits `analytics.capture`).
- ENH-1832's file-event tool→path map is a lower-value optional, intentionally
  not filed.

## Dependencies

- Follow-up to ENH-1831 / ENH-1887 (both done).

## Impact

- **Priority**: P4 — Incremental quality-of-life improvement; correction recall gap exists but no blocking impact on existing workflows
- **Effort**: Small — 3 targeted edits: schema addition, config class update, matcher compilation
- **Risk**: Low — Additive config with graceful fallback; built-ins remain active regardless of user config
- **Breaking Change**: No

## Session Log
- `/ll:format-issue` - 2026-06-03T21:44:21 - `39a37568-d7a7-42c9-8508-05b4e238e1ce.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

open
