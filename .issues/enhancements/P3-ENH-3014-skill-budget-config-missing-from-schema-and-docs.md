---
id: ENH-3014
title: skill_budget.threshold_tokens missing from config-schema.json and CONFIGURATION.md
type: ENH
status: open
priority: P3
discovered_date: 2026-08-02
discovered_by: multi-agent-audit
parent: EPIC-3008
depends_on:
- ENH-3013
- BUG-3012
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
`config-schema.json`, emitting it from `BRConfig.to_dict()` (see "Interaction
with BUG-3012's parity guard" below), and a matching section in
`CONFIGURATION.md`. Out of scope: migrating `cli/docs.py`'s
`._raw_config.get(...)` read to a typed `BRConfig` accessor (optional
follow-up, not required for the doc/schema fix).

**Sequencing: `depends_on: [ENH-3013]`** (declared in frontmatter, not just
prose). ENH-3013 edits the same two files — it removes 8 dead properties from
the `issues` object in `config-schema.json` and may touch
`scripts/tests/test_config_schema.py`, while this issue adds a new top-level
schema object plus a new parity assert to that same test module. This is the
tightest file overlap in EPIC-3008 after the CLI.md pair, and prose alone is not
enforced by anything: `parallel.epic_branches` reads `depends_on`, not Scope
Boundaries text. Land ENH-3013 first.

(Separately, this issue and ENH-3015 both edit `docs/reference/CONFIGURATION.md`
in different sections — safe to run concurrently.)

## Interaction with BUG-3012's parity guard — this is a hard break, not a style note

**`depends_on: [BUG-3012]` is also declared, and this issue must emit
`skill_budget` from `to_dict()`.** BUG-3012 adds a schema-driven parity test
that reads `config-schema.json`'s top-level `properties`, subtracts the
`{"$schema", "install_source"}` exclusion set, subtracts the keys `to_dict()`
emits, and asserts the difference is empty.

This issue adds a **new top-level** schema property. Adding it without a
matching `to_dict()` entry makes that guard fail with
`{'skill_budget'}` — so whichever of the two issues lands second turns the suite
red. Verified against current code: the schema-vs-`to_dict()` diff today is
exactly BUG-3012's 11 sections plus the two excluded meta keys, and the reverse
diff is empty.

Two resolutions were available; **emit it** was chosen over **exclude it**:

- Adding `skill_budget` to the guard's exclusion set would suppress the failure
  but leave `ll-config get skill_budget.threshold_tokens` unreachable — the
  exact reachability defect BUG-3012 exists to fix. It would also grow an
  exclusion list that is supposed to hold only non-config meta keys.
- Emitting it costs one raw-passthrough entry (`self._raw_config.get(
  "skill_budget", {})`, matching BUG-3012's Shape constraint 4 for
  never-modelled sections) and makes the key resolvable through both documented
  surfaces.

Do **not** introduce a typed `SkillBudgetConfig` dataclass here — same reasoning
as BUG-3012's Shape constraint 4. Consequence to accept: a project with no
`skill_budget` block emits `{}`, so `ll-config get skill_budget.threshold_tokens`
returns nothing rather than the built-in default. That matches every other
never-modelled section and does not affect `ll-doctor`, which reads
`_raw_config` directly and applies `_DEFAULT_BUDGET_TOKENS` itself
(`cli/docs.py:171-177`).

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
- [ ] `BRConfig.to_dict()` emits a top-level `skill_budget` key (raw
      passthrough), so BUG-3012's schema-driven parity guard stays green with
      the new schema property present.
- [ ] `ll-config get skill_budget.threshold_tokens` returns the configured value
      on a fixture project that sets it.
- [ ] No `SkillBudgetConfig` dataclass is introduced; a project without a
      `skill_budget` block emits `{}` and the lookup returns nothing (asserted
      explicitly, per BUG-3012's Shape constraint 4).
- [ ] `ll-doctor`'s skill-budget check is unaffected — it still falls back to
      `_DEFAULT_BUDGET_TOKENS` when the key is unset (`cli/docs.py:171-177`).
- [ ] `python -m pytest scripts/tests/` exits 0.

## Status

**Open** | Created: 2026-08-02 | Priority: P3

## Impact

- **Priority**: P3 — real feature, currently undocumented and un-schematized;
  would silently break under future schema enforcement.
- **Effort**: Small.
- **Risk**: Low.
- **Breaking Change**: No.
