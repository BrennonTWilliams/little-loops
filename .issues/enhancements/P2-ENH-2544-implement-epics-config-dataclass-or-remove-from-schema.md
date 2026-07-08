---
id: ENH-2544
title: 'Resolve `epics.*` schema-only limbo: implement EpicsConfig or remove from schema'
type: ENH
priority: P2
status: open
discovered_date: 2026-07-08
captured_at: '2026-07-08T09:20:00+00:00'
discovered_by: audit
decision_needed: true
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

Option A is preferred if EPIC scoping config is genuinely a user-tunable; Option B is preferred if the thresholds are policy, not configuration.

## Resolution

Recommend Option A unless design review confirms the keys are not user-tunable. Once decided, file a follow-up to implement and remove the Schema-only blockquote from `CONFIGURATION.md`.

## Out of scope

- Changing the `scope-epic` skill algorithm itself (only its config-binding change).
- Adding new `epics.*` keys beyond what schema already declares.

## Verification

- Whichever path is taken: `python -m pytest scripts/tests/` green; `ll-init --plan` generates the right config shape; `{{config.epics.scope.min_children}}` resolves to an integer (Option A) or the config-validation rejects the unknown key (Option B).

Captured by `/ll:audit-docs docs/reference/` Phase 2 review (2026-07-08).
