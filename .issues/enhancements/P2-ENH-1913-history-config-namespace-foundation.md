---
id: ENH-1913
title: history.* config namespace foundation (schema + HistoryConfig + BRConfig.history)
type: ENH
priority: P2
status: open
discovered_date: 2026-06-03
captured_at: "2026-06-03T21:38:03Z"
discovered_by: capture-issue
parent: EPIC-1707
relates_to: [EPIC-1707, ENH-1905, ENH-1907, ENH-1909, ENH-1911, ENH-1914, ENH-1915]
blocks: [ENH-1905, ENH-1907]
labels:
  - history-db
  - configurability
  - foundation
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
| `history.velocity_window` | int | TBD | ENH-1905 |
| `history.effort_fields` | list[str] | TBD | ENH-1905 |
| `history.max_age_days` | int | TBD | ENH-1905 |
| `history.session_digest.*` | object | — | ENH-1907 |
| `history.planning_skills` | list[str] | TBD | ENH-1909 |
| `history.evolution.feedback_min_recurrence` | int | TBD | ENH-1911 |
| `history.evolution.bypass_min_count` | int | TBD | ENH-1911 |
| `history.go_no_go.correction_penalty` | float | -0.2 | ENH-1914 (E) |
| `history.capture_issue.dup_overlap_threshold` | float | 0.7 | ENH-1914 (E) |

## Implementation Steps

1. `config-schema.json`: add the top-level `history` object with
   `additionalProperties: false` and the **complete** property set above
   (flat scalars/lists + nested `session_digest`, `evolution`, `go_no_go`,
   `capture_issue` objects).
2. `scripts/little_loops/config/features.py`: add `HistoryConfig` with a lenient
   `from_dict`. Flat scalar/list keys mirror `AnalyticsCaptureConfig`
   (`features.py:426`); the **nested** blocks mirror `EventsConfig`
   (`features.py:625`), where each nested block is its own dataclass with its own
   lenient `from_dict`.
3. `scripts/little_loops/config/core.py`: add a `BRConfig.history` property
   (mirror the existing `analytics_capture` / `events` property pattern,
   `core.py:313`).
4. Document the two-layer contract ("strict schema, lenient runtime, never
   raise, defaults-on-absent") once, here.

## Integration Map

### Files to Modify
- `config-schema.json` — add `history` top-level object with all sub-keys and `additionalProperties: false`
- `scripts/little_loops/config/features.py` — add `HistoryConfig` dataclass (mirror `AnalyticsCaptureConfig` pattern ~line 426; nested sub-objects mirror `EventsConfig` pattern ~line 625)
- `scripts/little_loops/config/core.py` — add `BRConfig.history` property (mirror `analytics_capture`/`events` property pattern ~line 313)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/config/core.py` — imports `HistoryConfig` from `features.py`
- Future consumers: ENH-1905, ENH-1907, ENH-1909, ENH-1911, ENH-1914 will import `BRConfig.history`

### Similar Patterns
- `AnalyticsCaptureConfig` in `features.py` — flat scalar/list key pattern to mirror
- `EventsConfig` in `features.py` — nested sub-object pattern to mirror (each nested block = own dataclass with own lenient `from_dict`)
- `BRConfig.analytics_capture` / `BRConfig.events` in `core.py` — property pattern to mirror

### Tests
- `scripts/tests/` — add `HistoryConfig.from_dict` tests: unknown key ignored, absent block all-defaults, nested block parsing
- Add test for `BRConfig.history` property returns `HistoryConfig` instance

### Documentation
- N/A — internal config addition; `/ll:configure` coverage handled by ENH-1916

### Configuration
- `config-schema.json` — primary target; users gain `history.*` keys in `.ll/ll-config.json` after this issue

## Acceptance Criteria

- Unknown key under `history` → strict schema rejects (tooling), but
  `HistoryConfig.from_dict` ignores-and-defaults (never raises).
- Absent `history` block → all defaults; consuming CLI runs normally.
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
- `/ll:verify-issues` - 2026-06-03T22:42:44 - `25083174-f806-4589-a206-0f8b53978497.jsonl`
- `/ll:format-issue` - 2026-06-03T21:44:40 - `a83ec0b5-ae28-4c26-924d-679cbaa34a5a.jsonl`
- `/ll:capture-issue` - 2026-06-03T21:38:03Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b03d2da2-37d4-4901-b030-76fe8b08f787.jsonl`

---

## Status

**Open** | Created: 2026-06-03 | Priority: P2
