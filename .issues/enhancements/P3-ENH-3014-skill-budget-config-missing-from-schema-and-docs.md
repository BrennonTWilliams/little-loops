---
id: ENH-3014
title: skill_budget.threshold_tokens missing from config-schema.json and CONFIGURATION.md
type: ENH
status: open
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
program_design_not_applicable: true
testable: true
labels:
- config-schema
- docs
---

# ENH-3014: `skill_budget.threshold_tokens` missing from `config-schema.json` and `CONFIGURATION.md`

## Summary

`skill_budget.threshold_tokens` is a real, working config override — read
directly from raw config and used by `ll-verify-skill-budget`/`ll-doctor` — but
it is completely absent from both `config-schema.json` (the schema/IDE-hint
source of truth) and `docs/reference/CONFIGURATION.md` (the human-facing
reference). This is schema drift in the reverse direction from most of this
epic's other findings: code reads a key the schema doesn't know about.

## Current Behavior

```python
threshold = (
    BRConfig(base_dir)
    ._raw_config.get("skill_budget", {})
    .get("threshold_tokens", _DEFAULT_BUDGET_TOKENS)
)
```
in `scripts/little_loops/cli/docs.py:171-175`, used by `validate_skill_budget`
(`cli/docs.py:111-179`), wired into `ll-doctor` at `cli/doctor.py:536-555`.

`grep -n "skill_budget" scripts/little_loops/config-schema.json` returns
nothing. `docs/reference/CONFIGURATION.md` has no `skill_budget` section
either. Because top-level `additionalProperties: false` is the schema's stated
intent, a user who follows the schema literally would have no idea
`skill_budget.threshold_tokens` is a legitimate override — and if schema
validation is ever turned on at load time (see EPIC-3008's shared context),
this key would start being rejected.

## Scope Boundaries

In scope: adding a `skill_budget` object (with `threshold_tokens`) to
`config-schema.json` and a matching section in `CONFIGURATION.md`. Out of
scope: migrating `cli/docs.py`'s `._raw_config.get(...)` read to a typed
`BRConfig` accessor (optional follow-up, not required for the doc/schema fix).

**File-contention note:** ENH-3013 edits the same two files — it removes 8 dead
properties from the `issues` object in `config-schema.json` and may touch
`scripts/tests/test_config_schema.py`, while this issue adds a new top-level
schema object plus a new parity assert to that same test module. Different
regions, so no `depends_on` is declared, but do not run these two as concurrent
epic branches under `parallel.epic_branches` — land one, then the other.
(Separately, this issue and ENH-3015 both edit `docs/reference/CONFIGURATION.md`
in different sections.)

## Expected Behavior

`skill_budget` (with `threshold_tokens`, default matching
`_DEFAULT_BUDGET_TOKENS` in `cli/docs.py`) should be declared in
`config-schema.json` alongside the other top-level sections, and documented in
`docs/reference/CONFIGURATION.md`.

## Precedence chain (must be documented, not just the key)

`threshold_tokens` is not the only input — there is a three-level chain, and the
CONFIGURATION.md section is wrong if it documents only the middle level:

1. **`--threshold` CLI flag** (`cli/docs.py:145`, help text: *"Token budget
   threshold (default: {\_DEFAULT\_BUDGET\_TOKENS}; overrides ll-config.json)"*) — highest precedence.
2. **`skill_budget.threshold_tokens`** in `.ll/ll-config.json` (`cli/docs.py:171-175`).
3. **`_DEFAULT_BUDGET_TOKENS`** built-in default (`cli/docs.py:121`).

## Suggested Fix Direction

Add a `skill_budget` object to `config-schema.json` with `threshold_tokens`
(integer, default = current `_DEFAULT_BUDGET_TOKENS` value read from
`cli/docs.py` at implementation time — do not hardcode a guessed number).
Add a matching `### \`skill_budget\`` section to `CONFIGURATION.md` describing
its purpose (skill file token-budget enforcement), its consumer
(`ll-verify-skill-budget`/`ll-doctor`, wired at `cli/doctor.py:536-555`), and
the flag > config > default precedence chain above. Optionally migrate
`cli/docs.py` to read via `BRConfig`'s typed accessors instead of
`._raw_config.get(...)` for consistency, if that's a small change — otherwise
leave the read path as-is and just fix the schema/docs gap.

## Acceptance Criteria

- [ ] `grep -n "skill_budget" scripts/little_loops/config-schema.json` returns a
      declared object with a `threshold_tokens` integer property.
- [ ] The schema `default` equals the live `_DEFAULT_BUDGET_TOKENS` value
      (assert this equality in `test_config_schema.py` so the two can't drift).
- [ ] `CONFIGURATION.md` gains a `### \`skill_budget\`` section documenting the
      full flag > config > default precedence, not just the config key.
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Impact

- **Priority**: P3 — real feature, currently undocumented and un-schematized;
  would silently break under future schema enforcement.
- **Effort**: Small.
- **Risk**: Low.
- **Breaking Change**: No.
