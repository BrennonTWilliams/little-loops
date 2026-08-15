---
id: BUG-3192
type: BUG
title: 'config-schema.json diverges from code: learning_tests.enabled default flips
  behavior by install path, sync.github.pull_limit unschema''d, socket.max_clients stale'
priority: P3
status: open
testable: true
discovered_by: doc-audit-triage
discovered_date: '2026-08-15'
captured_at: '2026-08-15T17:51:50Z'
supersedes: []
---

# BUG-3192: config-schema.json diverges from code in three places

## Summary

Split out of BUG-3191 (`/ll:audit-docs` readme-scope sweep, 2026-08-15). Three findings
originally filed there were framed as documentation nits under "Risk: None — doc-only
change". They are not doc issues: in each case `scripts/little_loops/config-schema.json`
disagrees with the Python source, and in one case that disagreement changes runtime
behavior depending on how a project was initialized.

BUG-3191 retains only the genuinely doc-only findings. This issue owns the schema fixes.

## Current Behavior

### 1. `learning_tests.enabled` — behavioral divergence, not cosmetic (primary)

- `config-schema.json` declares `"default": true`.
- `LearningTestsConfig.enabled` (`scripts/little_loops/config/features.py:498`) defaults
  to `False`.

These are not two views of one value — both are live, on different paths:

- `ll-init` writes the key explicitly, sourced from the schema:
  `scripts/little_loops/init/core.py:190` calls
  `schema_default("learning_tests.enabled")` → writes `true` into the new
  `.ll/ll-config.json`.
- A project whose config omits the key (hand-written config, older config predating the
  key, partial config) falls through to the dataclass → `False`.

Net effect: the Learning Test Registry is **on** for `ll-init`-generated projects and
**off** for projects without the key, with no signal to the user that the two differ.
`docs/reference/CONFIGURATION.md:897,909-921` documents the default as `false`, which is
correct against the dataclass and wrong against `ll-init`.

### 2. `sync.github.pull_limit` — real, documented, and unschema'd

- Read by code: `scripts/little_loops/sync.py:557,565,577-580` (bounds the `gh issue
  list` fetch and warns on truncation, naming the key in the warning text).
- Documented: `docs/reference/CONFIGURATION.md:720`.
- Absent from `config-schema.json`'s `sync.github.properties`, which declares
  `additionalProperties: false`. Present keys: `repo`, `label_mapping`,
  `priority_labels`, `sync_completed`, `state_file`, `pull_template`.

Blast radius is narrower than it first appears: little-loops does **not** runtime-validate
`ll-config.json` against this schema. The schema is consumed as the `$schema` pointer for
editor validation and by `schema_default()`/`schema_enum()` lookups in
`little_loops/init/core.py`. So the symptom is a spurious editor warning on a legitimate
key, not a hard config rejection. Still wrong, and it makes the key look unsupported to
anyone reading the schema as the source of truth.

### 3. `events.socket.max_clients` — stale schema default

- `config-schema.json` declares `"default": 8`.
- Code default is `32`; `docs/reference/CONFIGURATION.md:1466` documents `32` and is
  correct. The schema is the stale artifact here.

## Expected Behavior

- One default per config key, agreed between `config-schema.json` and the corresponding
  dataclass, so that `ll-init`-generated and key-omitting projects behave identically.
- `sync.github.pull_limit` declared in the schema with its code default, so
  `additionalProperties: false` stops rejecting a supported key.
- `events.socket.max_clients` schema default corrected to `32`.

## Implementation Notes

The `learning_tests.enabled` fix requires a product decision, not just an edit — pick the
intended default and make both sides agree:

- **Schema wins (`true`)**: change `LearningTestsConfig.enabled` to `True`. Silently
  enables LT surfaces (discoverability hook, gate-loop hints) for existing projects that
  omit the key — a behavior change on upgrade for those projects.
- **Dataclass wins (`false`)**: change the schema default to `false`. `ll-init` then
  writes `false`, making LT opt-in. Matches what CONFIGURATION.md already documents.

Recommend **dataclass wins**: it is the documented behavior, it is opt-in rather than
opt-out for a feature that adds hook surface, and it changes nothing for existing
projects. Under this option CONFIGURATION.md needs no edit.

Whichever is chosen, add a regression test asserting schema default == dataclass default
for this key. Consider generalizing it to a parametrized test over every dotted path where
both a schema `default` and a dataclass field exist — this class of drift has now produced
two of the three findings in this issue, and a general test would have caught both.

## Acceptance Criteria

- [ ] `schema_default("learning_tests.enabled")` and `LearningTestsConfig.enabled` return
      the same value.
- [ ] `sync.github.pull_limit` is declared in `config-schema.json` with a `type`,
      `default` matching code, and a `description`.
- [ ] `events.socket.max_clients` schema default is `32`.
- [ ] A test in `scripts/tests/test_config_schema.py` fails if a schema default and its
      dataclass counterpart diverge (at minimum for `learning_tests.enabled`; ideally
      parametrized across all such pairs).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Impact

- **Priority**: P3 — the `learning_tests` divergence is a genuine behavior split across
  install paths, but the affected feature is non-destructive and the other two findings
  are low-severity schema hygiene.
- **Effort**: Small — three schema/dataclass edits plus one regression test.
- **Risk**: Low — a schema-only change is inert at runtime; the `learning_tests` half
  touches a real default and should land with the recommended (no-op for existing
  projects) option unless deliberately chosen otherwise.
- **Breaking Change**: No, under the recommended option.

## Status

**Open** | Created: 2026-08-15 | Priority: P3
