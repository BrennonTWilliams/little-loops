---
id: ENH-2544
title: 'Resolve `epics.*` schema-only limbo: implement EpicsConfig or remove from schema'
type: ENH
priority: P2
status: open
discovered_date: 2026-07-08
captured_at: '2026-07-08T09:20:00+00:00'
discovered_by: audit
decision_needed: false
labels:
  - enhancement
  - schema
  - configuration
  - documentation
  - follow-up-from-docs-audit-2026-07-08
confidence_score: 75
outcome_confidence: 70
score_complexity: 7
score_test_coverage: 5
score_ambiguity: 8
score_change_surface: 7
---

# ENH-2544: Resolve `epics.*` schema-only limbo: implement `EpicsConfig` or remove from schema

## Summary

The Phase 1 docs audit marked `epics.*` settings in `config-schema.json` as **"Schema-only / not yet wired"** in `docs/reference/CONFIGURATION.md` — accepted by validation but never emitted in `BRConfig.to_dict()` because no `EpicsConfig` dataclass exists. This is a **schema-only limbo**: users can set `epics.scope.min_children` in their config, schema validation passes, but template substitution like `{{config.epics.scope.min_children}}` (used by `skills/scope-epic/SKILL.md`) produces nothing. The audit correctly deferred the decision rather than picking one path. This issue tracks the decision and implementation.

## Current Behavior

- `config-schema.json` declares `properties.epics.properties.scope.properties.{min_children,max_children}` and `properties.epics.properties.cascade.properties.default_status`.
- `scripts/little_loops/config/` does not define an `EpicsConfig` dataclass, so `BRConfig.to_dict()` emits no `"epics"` key.
- `skills/scope-epic/SKILL.md` references `{{config.epics.scope.min_children}}` which silently substitutes to empty string at runtime.
- `docs/reference/CONFIGURATION.md` documents the schema with a **Schema-only / not yet wired** blockquote noting the runtime gap.

## Expected Behavior (Decision Needed)

One of two resolutions:

**Option A — Wire the dataclass.** Add `EpicsConfig` to `scripts/little_loops/config/`, register it on `BRConfig`, update `to_dict()` to emit the `epics` key, and have `skills/scope-epic/SKILL.md` resolve the values correctly. Effort: medium (3 files, ~5–8 tests). The doc blockquote gets removed.

**Option B — Remove the schema keys.** Delete `properties.epics` from `config-schema.json` entirely. Drop the doc rows. If `scope-epic` legitimately needs the threshold, hard-code a default in the skill body (`min_children: 3`). Effort: low (2 files, 1 default). The schema shrinks back to declared-only.

> **Selected:** Option B — Remove the schema keys — aligns with BUG-1461 precedent and FEAT-2339/FEAT-2447's deliberate 2026-06-30 decision (ARCHITECTURE-096) to NOT use `epics.*` as a config namespace.

Option A is preferred if EPIC scoping config is genuinely a user-tunable; Option B is preferred if the thresholds are policy, not configuration.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-08.

**Selected**: Option B — Remove the schema keys

**Reasoning**: The "schema-only / not yet wired" blockquote in `docs/reference/CONFIGURATION.md:780-782` is an intentional design marker, not an oversight. FEAT-2339/FEAT-2447 (Decision ARCHITECTURE-096, 2026-06-30) explicitly chose `parallel.epic_branches.*` over `epics.*` as a config namespace, leaving the `epics.*` schema subtree as an abandoned alternative. The `--cascade` flag is already implemented and does NOT consume `epics.cascade.default_status` (hardcoded in argparse at `cli/issues/__init__.py:740`), and the only `{{config.epics.*}}` consumer is `skills/scope-epic/SKILL.md` lines 37, 38, 104, 105 — all of which already display "default: 3"/"default: 8" inline. Option B mirrors the BUG-1461 precedent (12/12 score for identical "remove unwired schema keys" shape).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A — Wire the dataclass | 2/3 | 2/3 | 3/3 | 1/3 | 8/12 |
| Option B — Remove the schema keys | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |

**Key evidence**:
- **Option A**: Direct precedent exists via FEAT-2447's `parallel.epic_branches.*` (3-level nested dataclass composition mirrors `EventsConfig` in `features.py:778-801`); `from_dict`/`to_dict`/`@property` registration is well-trodden; test patterns (`TestBRConfig.test_to_dict_*_schema_aligned_keys`, `TestEventsConfig.test_*_sub_config_round_trips_through_to_dict`) are direct templates. **Against**: contradicts FEAT-2339/FEAT-2447's deliberate 2026-06-30 decision to NOT use `epics.*` as a namespace; would re-litigate Decision ARCHITECTURE-096; no template currently emits `epics.*` (compare to `parallel.epic_branches` stamped in all 9 project-type templates).
- **Option B**: Exact precedent is BUG-1461 (`P3-BUG-1461-...md:111-128`, scored 12/12 for identical "remove unwired schema keys + remove stub references" pattern across 6 files); aligns with FEAT-2339/FEAT-2447's deliberate namespace decision; `--cascade` argparse default already hardcodes the same `"deferred"` value the schema advertised; only one skill (`scope-epic`) consumes the 4 substitution sites, all of which already display the inline default. Test-side: `test_config_schema.py:595-619` (`test_epics_scope_in_schema`) is removed alongside the schema block, mirroring BUG-1461's text-only footprint.

## Resolution

**Option B selected** (2026-07-08 by `/ll:decide-issue`). The follow-up implementation task is to remove the `properties.epics` block from `config-schema.json` (lines 1331-1369), drop the `### epics` / `#### epics.scope` / `#### epics.cascade` rows from `docs/reference/CONFIGURATION.md` (lines 780-795), replace the four `{{config.epics.*}}` substitutions in `skills/scope-epic/SKILL.md` (lines 37, 38, 104, 105) with the hardcoded integers `3` and `8`, and delete the `test_epics_scope_in_schema` test (`scripts/tests/test_config_schema.py:595-619`). Mirrors the BUG-1461 removal precedent.

## Out of scope

- Changing the `scope-epic` skill algorithm itself (only its config-binding change).
- Adding new `epics.*` keys beyond what schema already declares.

## Verification

- Whichever path is taken: `python -m pytest scripts/tests/` green; `ll-init --plan` generates the right config shape; `{{config.epics.scope.min_children}}` resolves to an integer (Option A) or the config-validation rejects the unknown key (Option B).

## Codebase Research Findings

_Added by `/ll:refine-issue` — based on direct reading of `scripts/little_loops/config/core.py`, `scripts/little_loops/config/features.py`, `scripts/little_loops/config/__init__.py`, `config-schema.json`, `docs/reference/CONFIGURATION.md`, and `skills/scope-epic/SKILL.md`:_

### State of the `epics.*` schema (ground truth)

- **`config-schema.json:1331-1369`** declares an `epics` object with two nested sub-objects:
  - `epics.scope.{min_children: integer ≥ 1 (default 3), max_children: integer ≥ 1 (default 8)}`
  - `epics.cascade.default_status: enum in ["deferred", "cancelled", "done"] (default "deferred")`
- **`additionalProperties: false`** is set on both `scope` and `cascade`, so unknown nested keys are rejected — but a user typing `epics.foo: 1` would be accepted against the schema (only the leaf is strict).
- **No `EpicsConfig` dataclass exists anywhere in `scripts/little_loops/config/`.** Search across the config module (grep for `class.*Epics` / `EpicsConfig`) returns zero hits. The only `epics` reference in `config/` is `REQUIRED_CATEGORIES["epics"]` at `features.py:83` — that is the **issue-category** named "epics" (prefix `EPIC`, dir `epics`, action `coordinate`), a completely separate concept from the `epics.*` runtime config subtree this issue is about.

### `BRConfig.to_dict()` data flow (`scripts/little_loops/config/core.py:544-...`)

- `to_dict()` returns a flat shape with **only** the following top-level keys (verified across the visible range): `project`, `issues`, `automation`, `parallel` (with nested `base`/`p0_sequential`/etc.). No `epics` key is emitted.
- This is the **sole source** of template substitution. When `skills/scope-epic/SKILL.md` writes `{{config.epics.scope.min_children}}`, interpolation resolves `config → BRConfig.to_dict()`; missing `epics` key → empty string substitution.

### Template substitution call sites

Only one skill references `config.epics.*` today: `skills/scope-epic/SKILL.md` at lines **37** (`{{config.epics.scope.min_children}}`), **38** (`{{config.epics.scope.max_children}}`), **104** (`MIN_CHILDREN = {{config.epics.scope.min_children}}`), and **105** (`MAX_CHILDREN = {{config.epics.scope.max_children}}`). All four are documentation/inline-display only — no code reads the value. The skill *also* hardcodes the default `(default: 3)` / `(default 3)` next to the empty substitution, which is the user-visible fallback today.

### `cascade.default_status` consumers

The `cascade.default_status` key currently has **no in-repo consumer code path** at all (grep for `cascade.default_status` / `epics.cascade` / `.cascade.` returns only the schema and the docs row). It exists schema-side as a future contract for `--cascade` flag handling; nothing currently defaults to it.

### Related open work (decide before implementing)

`FEAT-2339` (`features/P3-FEAT-2339-per-epic-integration-branch-strategy.md`) references `config/features.py` or `a new config/epics.py` and wiring through to `BRConfig`. If Option A is chosen, **coordinate with FEAT-2339** — both workstreams likely need to share an `EpicsConfig` dataclass so per-EPIC integration-strategy config can sit under `epics.*` alongside `scope`/`cascade`. Doing them as one PR is cheaper than two divergent designs.

### Option A implementation sketch (if chosen)

1. Create `scripts/little_loops/config/epics.py` with:
   ```python
   @dataclass
   class EpicsScopeConfig:
       min_children: int = 3
       max_children: int = 8

   @dataclass
   class EpicsCascadeConfig:
       default_status: str = "deferred"  # one of "deferred"|"cancelled"|"done"

   @dataclass
   class EpicsConfig:
       scope: EpicsScopeConfig = field(default_factory=EpicsScopeConfig)
       cascade: EpicsCascadeConfig = field(default_factory=EpicsCascadeConfig)
   ```
2. Register it in `BRConfig.__init__` (mirroring the pattern used by `self._parallel` etc.), load defaults from `DEFAULT_*` constants or `dict.get` deep-merging from a `DictConfig` adapter.
3. Add `"epics": {...}` to `BRConfig.to_dict()`.
4. `from_dict()` (or a config loader) needs to parse `config-schema.json`'s `epics` block with validation matching the `min/max ≥ 1` and `enum` constraints.
5. Update `tests/` to assert the new emitted key. The skill body needs no change — substitution resolves to the integer once emitted.
6. Remove the `> Schema-only / not yet wired` blockquote from `docs/reference/CONFIGURATION.md:782` and mark these rows as "wired in `BRConfig.to_dict()`".
7. Bump the schema-doc import (`docs/scripts` regenerate if any) — verify no docs-reference automation builds a rendered table from the markdown that would have to be refreshed.

### Option B implementation sketch (if chosen)

1. Remove the entire `epics` block from `config-schema.json:1331-1369`.
2. Remove the `### epics` and `#### epics.scope` / `#### epics.cascade` rows from `docs/reference/CONFIGURATION.md:780-795`.
3. In `skills/scope-epic/SKILL.md`, replace `{{config.epics.scope.min_children}}` with the hardcoded integer `3` and `{{config.epics.scope.max_children}}` with `8` (lines 37, 38, 104, 105).
4. Run `python -m pytest scripts/tests/` — no behavioral change since substitution was empty-string-→-hardcoded-text today.
5. **Out-of-scope concern:** if `FEAT-2339` later wants to wire its own `epics.*` keys, it will need to re-introduce the schema subtree. If that project tracks separately, Option B today and Option A in FEAT-2339 leaves a churn footprint — worth a design-review note even if Option B is chosen now.

### Recommended path

Prefer **Option A** unless `FEAT-2339` is closed/deferred without epics-config needs. Reason: `epics.cascade.default_status` is a real schema contract with future `--cascade` semantics, so removing it requires removing the contract too — and there's a known open workstream that will likely need `EpicsConfig` anyway. The 5–8 tests referenced in the issue body are reasonable; the larger cost is the `from_dict`/schema-validation plumbing for nested objects (mirroring `ParallelConfig.base`), not the dataclass itself.

Captured by `/ll:audit-docs docs/reference/` Phase 2 review (2026-07-08).


## Session Log
- `/ll:decide-issue` - 2026-07-08T14:48:41 - `af39a52e-94bf-4b16-9eb5-7c29f57a1a47.jsonl`
- `/ll:decide-issue` - 2026-07-08T14:48:16 - `af39a52e-94bf-4b16-9eb5-7c29f57a1a47.jsonl`
- `/ll:refine-issue` - 2026-07-08T14:39:47 - `ea1dab68-2ebe-4bc4-99ae-67df8309e565.jsonl`
