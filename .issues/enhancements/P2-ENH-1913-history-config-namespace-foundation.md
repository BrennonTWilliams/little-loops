---
id: ENH-1913
title: history.* config namespace foundation (schema + HistoryConfig + BRConfig.history)
type: ENH
priority: P2
status: done
discovered_date: 2026-06-03
captured_at: '2026-06-03T21:38:03Z'
completed_at: '2026-06-04T00:05:41Z'
discovered_by: capture-issue
parent: EPIC-1707
relates_to:
- EPIC-1707
- ENH-1905
- ENH-1907
- ENH-1909
- ENH-1911
- ENH-1914
- ENH-1915
blocks:
- ENH-1905
- ENH-1907
labels:
- history-db
- configurability
- foundation
confidence_score: 98
outcome_confidence: 88
score_complexity: 19
score_test_coverage: 21
score_ambiguity: 24
score_change_surface: 24
---

# ENH-1913: history.* config namespace foundation

## Summary

Establish the single, consistent foundation for **read/consume** configurability
of `.ll/history.db`: a top-level `history` object in `config-schema.json`, a
`HistoryConfig` dataclass with a lenient `from_dict`, and a `BRConfig.history`
property. This issue is the **sole owner of the `history` namespace schema** — it
declares the *complete* sub-key set for every planned consumer so that consumers
(ENH-1905/1907/1909/1911 and the (E)/(F) follow-ups) wire **runtime + CLI only**
and never touch `config-schema.json`. Blocks the rest of the consistency work.

## Current Behavior

No top-level `history` key exists in `config-schema.json`, no `HistoryConfig` dataclass exists in `scripts/little_loops/config/features.py`, and no `BRConfig.history` property exists in `scripts/little_loops/config/core.py`. History.db consumers must either hardcode thresholds (as in ENH-1888) or invent ad-hoc key placement, leading to namespace drift (e.g., ENH-1911 placed a history-read threshold under `analysis.evolution.*` rather than `history.*`).

## Expected Behavior

A single `history` object in `config-schema.json` (with `additionalProperties: false`) owns the complete sub-key set for all planned history.db consumers. A `HistoryConfig` dataclass with a lenient `from_dict` is available in `scripts/little_loops/config/features.py`. A `BRConfig.history` property in `scripts/little_loops/config/core.py` exposes the config. After this issue, consumers (ENH-1905/1907/1909/1911/1914) wire runtime + CLI only — no further schema edits needed.

## Motivation

An audit of every open + recently-done history.db issue surfaced namespace drift:
read tunables live under `history.*` (ENH-1905/1907/1909) but ENH-1911 put an
equivalent history-read threshold under `analysis.evolution.*` (a third
namespace), and done consumers (ENH-1888) bake in hardcoded thresholds with no
config exposure. There is currently **no** top-level `history` key in
`config-schema.json`, **no** `HistoryConfig` dataclass, and **no**
`BRConfig.history` property — so there is no shared foundation for any consumer to
build on. Without a single owner of the namespace, every consumer would re-edit
the schema and collide on the parent object.

## Ratified design decisions

- **Read-mechanism rule (self-gating only)**: config is read in **Python via
  `BRConfig`**, never in markdown. Every config-gated history behavior lives in a
  Python CLI that self-gates — the skill calls the CLI unconditionally; the CLI
  reads `config.history`, applies the gate, and no-ops (exit 0, empty output)
  when disabled. **No generic `ll-config get` CLI is built** (explicitly out of
  scope).
- **Namespace split**: `history.*` = read/consume side; `analytics.*` =
  capture/write side. ENH-1911's `analysis.evolution.*` moves to
  `history.evolution.*` (handled in that issue).
- **Two-layer config contract (strict schema / lenient runtime)**:
  - *Schema layer* (`config-schema.json`): `history` uses
    `additionalProperties: false`, consistent with every sibling object. A
    misspelled key is a *tooling* error surfaced via `/ll:configure` / schema
    checks — not a runtime crash.
  - *Runtime layer* (`HistoryConfig.from_dict`): lenient, mirroring
    `AnalyticsCaptureConfig` — reads known keys via `data.get(key, default)`,
    ignores unknown keys, falls back to defaults when `history` is absent, and
    **never raises**.

## Scope Boundaries

- No generic `ll-config get` CLI tool — config is read only in Python via `BRConfig`, never in markdown.
- No namespace migration of ENH-1911's `analysis.evolution.*` keys — that is handled within ENH-1911.
- No runtime behavior changes for existing consumers — this issue delivers schema + dataclass + property only.
- No `history.go_no_go.*` or `history.capture_issue.*` runtime wiring (delivered by ENH-1914).
- No `history.session_digest.*` runtime wiring (delivered by ENH-1907).
- No `/ll:configure` coverage check for the `history` namespace (delivered by ENH-1916).

## API/Interface

Declare the **full** property set up front (so consumers never edit the schema):

| Key | Type | Default | Consumer |
|-----|------|---------|----------|
| `history.velocity_window` | int | `10` | ENH-1905 |
| `history.effort_fields` | list[str] | `["session_count", "cycle_time_days"]` | ENH-1905 |
| `history.max_age_days` | int \| null | `null` | ENH-1905 |
| `history.session_digest.enabled` | bool | `false` | ENH-1907 |
| `history.session_digest.days` | int | `7` | ENH-1907 |
| `history.session_digest.char_cap` | int | `1200` | ENH-1907 |
| `history.session_digest.sections` | list[str] | all v1 providers (ordered) | ENH-1907 |
| `history.planning_skills` | list[str] | `["create-sprint", "scope-epic", "manage-issue", "review-epic"]` | ENH-1909 |
| `history.evolution.feedback_min_recurrence` | int | `2` | ENH-1911 |
| `history.evolution.bypass_min_count` | int | `2` | ENH-1911 |
| `history.go_no_go.correction_penalty` | float | `-0.2` | ENH-1914 |
| `history.capture_issue.dup_overlap_threshold` | float | `0.7` | ENH-1914 |

## Implementation Steps

1. `config-schema.json`: add the top-level `history` object with
   `additionalProperties: false` and the **complete** property set above.
   Model after the `analytics` block (lines 1365–1405) for flat keys and the
   `events` block (lines 1224–1304) for nested sub-objects. Each nested sub-object
   (`session_digest`, `evolution`, `go_no_go`, `capture_issue`) needs its own
   `"type": "object"`, `"properties"`, and `"additionalProperties": false`.
2. `scripts/little_loops/config/features.py`: add four leaf sub-config dataclasses
   (`SessionDigestConfig`, `EvolutionConfig`, `GoNoGoConfig`, `CaptureIssueConfig`)
   then a `HistoryConfig` parent that assembles them. Mirror leaf configs after
   `SocketEventsConfig` (line 561); mirror the parent after `EventsConfig` (line 625).
   Each sub-config's `from_dict` uses `data.get(key, default)` for every field
   (mirror `AnalyticsCaptureConfig.from_dict` at line 440). `HistoryConfig.from_dict`
   delegates: `SessionDigestConfig.from_dict(data.get("session_digest", {}))` etc.
3. `scripts/little_loops/config/core.py`: three sub-tasks:
   a. Wire `self._history = HistoryConfig.from_dict(self._raw_config.get("history", {}))` in
      `_parse_config` (mirror `_events` at line 216, not the double-`.get()` used for `_analytics_capture`).
   b. Add `BRConfig.history` property returning `self._history` typed as `HistoryConfig`
      (mirror `BRConfig.events` at line 298).
   c. Add a `history` serialization block in `to_dict` after the `events` block
      (lines 619–634), inlining all sub-object fields (mirror the `events` block shape).
4. `scripts/little_loops/config/__init__.py`: add `HistoryConfig` and each nested
   sub-config class to the `from little_loops.config.features import (...)` block
   and to `__all__` (mirror `AnalyticsCaptureConfig` at line 41, `EventsConfig` at
   line 46, and the socket/otel/webhook sub-classes at lines 54–59).
5. Tests (`scripts/tests/test_config.py`): add `TestHistoryConfig` (unit tests for
   `from_dict({})`, per-key override, nested sub-object defaults, unknown key ignored)
   and `TestBRConfigHistoryIntegration` (property exists, defaults-on-absent, loads
   from config, round-trips via `to_dict`). Model after `TestAnalyticsCaptureConfig`
   (line 1178), `TestEventsConfig` (line 1555), `TestBRConfigEventsIntegration`
   (line 1698), and `TestBRConfigAnalyticsCaptureIntegration` (line 2551).
   Add a schema presence test in `scripts/tests/test_config_schema.py` (model after
   `test_analytics_in_schema` line 253 / `test_events_in_schema` line 347).

## Integration Map

### Files to Modify
- `config-schema.json` — add `history` top-level object with all sub-keys and `additionalProperties: false` (model `analytics` block lines 1365–1405 for flat keys; `events` block lines 1224–1304 for nested sub-objects)
- `scripts/little_loops/config/features.py` — add four leaf sub-config dataclasses (`SessionDigestConfig`, `EvolutionConfig`, `GoNoGoConfig`, `CaptureIssueConfig`) then `HistoryConfig` parent (mirror leaf configs after `SocketEventsConfig` line 561; mirror parent after `EventsConfig` line 625; `from_dict` pattern after `AnalyticsCaptureConfig.from_dict` line 440)
- `scripts/little_loops/config/core.py` — (a) wire `_history` in `_parse_config` (mirror `_events` at line 216); (b) add `BRConfig.history` property (mirror `events` at line 298); (c) add `history` serialization block in `to_dict` after `events` block (lines 619–634)
- `scripts/little_loops/config/__init__.py` — add `HistoryConfig` and all nested sub-config classes to imports and `__all__` (mirror `AnalyticsCaptureConfig` line 41, `EventsConfig` line 46, sub-classes lines 54–59)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py` — imports `HistoryConfig` from `features.py`
- `scripts/little_loops/config/__init__.py` — re-exports `HistoryConfig` and nested sub-config classes via `__all__`
- Future consumers: ENH-1905, ENH-1907, ENH-1909, ENH-1911, ENH-1914 will import `BRConfig.history`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/history_reader.py` — exports `STALE_DAYS_DEFAULT = 30` (hardcoded); ENH-1905/ENH-1907 will replace this with `config.history.max_age_days` — not in ENH-1913 scope but the threshold this config key is designed to replace [Agent 1 finding]
- `scripts/little_loops/cli/history_context.py` — imports and uses `STALE_DAYS_DEFAULT` from `history_reader`; future consumer wiring point for the same threshold replacement [Agent 1 finding]

### Similar Patterns
- `AnalyticsCaptureConfig` in `features.py:426` — flat scalar/list `from_dict` pattern to mirror; `from_dict` at line 440 uses `data.get(key, default)` for every field, ignores unknowns, never raises
- `EventsConfig` in `features.py:625` — nested sub-object pattern to mirror; leaf sub-configs (`SocketEventsConfig` line 561, `SqliteEventsConfig` line 611, etc.) each have standalone `from_dict`; parent delegates via `SubClass.from_dict(data.get("key", {}))`
- `BRConfig.events` in `core.py:298` / `BRConfig.analytics_capture` in `core.py:312` — property pattern to mirror; `_parse_config` wiring at line 216 (`_events`) and lines 223–225 (`_analytics_capture`)
- `BRConfig.to_dict` `analytics` block at `core.py:610` and `events` block at `core.py:619` — serialization block pattern to mirror for the new `history` block

### Tests
- `scripts/tests/test_config.py` — add tests modeled after:
  - `TestAnalyticsCaptureConfig` (line 1178): flat `from_dict` — empty dict, per-key override, unaffected defaults
  - `TestEventsConfig` (line 1555): nested sub-object unit tests for each sub-config default
  - `TestBRConfigEventsIntegration` (line 1698): property exists, returns correct type, loads from file, `to_dict` round-trip
  - `TestBRConfigAnalyticsCaptureIntegration` (line 2551): nested-namespace BRConfig integration pattern
- `scripts/tests/test_config_schema.py` — add schema presence test (model after `test_analytics_in_schema` line 253 / `test_events_in_schema` line 347): assert `history` in `data["properties"]`, `additionalProperties: false`, each leaf key's `type` and `default`
- `scripts/tests/conftest.py` — fixtures `temp_project_dir` (line 56) and `sample_config` (line 66) require no changes; tests augment `sample_config["history"]` then write to disk via `config_path.write_text(json.dumps(sample_config))`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config.py` import block (lines 11-48) — **must be updated** to add `HistoryConfig`, `SessionDigestConfig`, `EvolutionConfig`, `GoNoGoConfig`, `CaptureIssueConfig` to the named imports when adding step 5's test classes; no `__all__` snapshot tests exist so this is purely additive and safe [Agent 3 finding]

### Documentation
- N/A — internal config addition; `/ll:configure` coverage handled by ENH-1916

### Configuration
- `config-schema.json` — primary target; users gain `history.*` keys in `.ll/ll-config.json` after this issue

## Acceptance Criteria

- Unknown key under `history` → strict schema rejects (tooling), but
  `HistoryConfig.from_dict` ignores-and-defaults (never raises).
- Absent `history` block → all defaults; consuming CLI runs normally.
- `BRConfig(project_dir).history` returns a `HistoryConfig` instance with correct defaults when no `history` key is in `ll-config.json`.
- `BRConfig(project_dir).to_dict()["history"]` serializes all sub-keys and round-trips cleanly through `HistoryConfig.from_dict`.
- `HistoryConfig` and all nested sub-config classes are importable from `little_loops.config`.
- Exactly one issue's diff touches `config-schema.json`'s `history` object (this
  one); consumers add runtime + CLI only.
- `python -m pytest scripts/tests/` green.

## Impact

- **Priority**: P2 — Hard blocker for ENH-1905, ENH-1907, ENH-1909, ENH-1911, ENH-1914, ENH-1916; without this foundation each consumer would re-edit `config-schema.json` and collide on the shared parent object.
- **Effort**: Small — Three-file change mirroring well-established patterns (`AnalyticsCaptureConfig`, `EventsConfig`, `BRConfig.analytics_capture`); no new patterns required.
- **Risk**: Low — Purely additive (new schema key, new dataclass, new property); no existing behavior is modified; test surface is straightforward.
- **Breaking Change**: No

## Dependencies

- **Blocks**: ENH-1905, ENH-1907, ENH-1909, ENH-1911, ENH-1914 (E), and the
  `/ll:configure` coverage check in ENH-1916 (G).

## Session Log
- `/ll:ready-issue` - 2026-06-03T23:53:06 - `12728b4b-a976-4d52-9b90-cd6b72b5c0f9.jsonl`
- `/ll:confidence-check` - 2026-06-03T23:58:00Z - `286334a1-4aad-4f22-a746-3c852dea89fd.jsonl`
- `/ll:wire-issue` - 2026-06-03T23:45:58 - `4b26a3c9-8297-4ab3-88d3-d5a86b8bc511.jsonl`
- `/ll:refine-issue` - 2026-06-03T23:41:03 - `c471fc82-5a38-4413-8d07-76f8f9c17090.jsonl`
- `/ll:verify-issues` - 2026-06-03T22:42:44 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:format-issue` - 2026-06-03T21:44:40 - `a83ec0b5-ae28-4c26-924d-679cbaa34a5a.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

**Open** | Created: 2026-06-03 | Priority: P2
