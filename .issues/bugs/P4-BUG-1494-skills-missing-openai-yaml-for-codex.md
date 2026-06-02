---
id: BUG-1494
type: BUG
priority: P4
status: done
captured_at: '2026-05-16T13:04:12Z'
completed_at: '2026-05-16T14:00:38Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by:
- ENH-1497
relates_to:
- FEAT-1486
labels:
- captured
- codex
- skills-api
- parity
decision_needed: false
confidence_score: 98
outcome_confidence: 90
score_complexity: 22
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1494: Two skills missing `agents/openai.yaml` for Codex

## Summary

`skills/verify-issue-loop/` and `skills/init/` do not have an `agents/openai.yaml` sibling alongside their `SKILL.md`. Per the Codex Skills API contract documented in `ll-adapt-skills-for-codex`, both files are required for the skill to be discoverable from Codex. 28 of 30 skill directories have the yaml; these two are stragglers.

## Steps to Reproduce

1. `ls skills/verify-issue-loop/` — note absence of `agents/openai.yaml`
2. `ls skills/init/` — note absence of `agents/openai.yaml`
3. Compare against any other skill directory (e.g. `ls skills/commit/agents/openai.yaml`) which has the file
4. Run `ll-adapt-skills-for-codex` then check `~/.codex/skills/` — observe that `verify-issue-loop` and `init` are not installed

## Current Behavior

```
$ ls skills/verify-issue-loop/
SKILL.md
$ ls skills/init/
SKILL.md  (plus other content, but no agents/openai.yaml)
```

After running `ll-adapt-skills-for-codex`, these two skills are absent from `~/.codex/skills/`. A Codex user invoking `/ll:verify-issue-loop` or `/ll:init` finds nothing.

## Expected Behavior

Both `skills/verify-issue-loop/agents/openai.yaml` and `skills/init/agents/openai.yaml` exist with frontmatter matching the conventions used by the other 28 skills. After re-running the adapter, both skills install under `~/.codex/skills/` and are invokable from Codex.

## Root Cause

When the Codex Skills API support was added (FEAT-1486), the adapter was expected to be the source of truth for emitting `agents/openai.yaml`. For most skills, the adapter was run and the files committed. These two appear to have been missed — most likely because `ll-adapt-skills-for-codex` was authored after they existed and the back-fill run skipped them (either due to a `disable-model-invocation: true` flag or an oversight).

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Neither SKILL.md has `disable-model-invocation: true`**: Both `skills/verify-issue-loop/SKILL.md` and `skills/init/SKILL.md` frontmatter were verified — the flag is absent from both.
- **The adapter does not check this flag at all**: `_process_skills()` in `scripts/little_loops/cli/adapt_skills_for_codex.py` only skips a skill if its `description:` field is missing or unreadable — `disable-model-invocation: true` has no effect on skip logic.
- **Both yaml files now exist and are committed**: `skills/verify-issue-loop/agents/openai.yaml` and `skills/init/agents/openai.yaml` are present on disk with no pending git changes. The yaml-creation portion of the bug is resolved; the outstanding work is step 4 (regression test).
- **Skip condition in `_process_skills()`**: A skill is only skipped when `not skill_changed AND yaml_exists` — i.e., SKILL.md frontmatter was already complete AND the yaml file already existed. These two skills were likely re-processed after the yaml was initially missing, producing the files now on disk.

## Integration Map

### Files to Modify / Create
- `skills/verify-issue-loop/agents/openai.yaml` — create if missing
- `skills/init/agents/openai.yaml` — create if missing
- `skills/manage-issue/agents/openai.yaml` — also missing yaml; no `disable-model-invocation: true` flag, so the adapter should generate it; must be created or the regression test will fail for it [Agent 1 finding]
- `CONTRIBUTING.md` — "New Skill Checklist" section (if it exists) needs a step to run `ll-adapt-skills-for-codex --apply` when adding a new skill; once `test_all_real_skills_have_openai_yaml` runs in CI, any skill added without the adapter will break CI with no checklist warning [Agent 2 finding]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — exports `main_adapt_skills_for_codex` in `__all__`; no change needed, awareness only [Agent 1 finding]
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1486LlAdaptSkillsWiring` asserts that `ll-adapt-skills-for-codex` is wired in four doc files (`commands/help.md`, `.claude/CLAUDE.md`, `docs/reference/CLI.md`, `skills/configure/areas.md`); no change needed [Agent 2 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — full documentation section for `ll-adapt-skills-for-codex` with flags and examples; no change needed [Agent 1 finding]
- `docs/reference/HOST_COMPATIBILITY.md` — claims "all ll skills are now adapted" in footnote `[^cmds]`; currently inaccurate while `manage-issue` and `update-docs` lack yaml; the test enforces this claim so no text change needed, but awareness of the claim is important [Agent 2 finding]

### Tests
- `scripts/tests/test_adapt_skills_for_codex.py` — add a third test to `TestRealSkillsIntegrationGuard` (line 324) asserting that every `skills/*/` directory has a corresponding `agents/openai.yaml`; model after `test_all_real_skills_have_name_field()` (line 327) which already walks `skills/*/SKILL.md` and asserts per-file presence
- **Critical scope constraint** (wiring pass finding): `update-docs` has `disable-model-invocation: true` and no yaml — this is intentionally deferred to ENH-1497; the new test MUST skip skills with `disable-model-invocation: true` in frontmatter, or it will immediately fail for `update-docs`; `manage-issue` has no such flag and must have a yaml file created [Agent 3 finding]

## Implementation Steps

1. ~~Inspect both SKILL.md files for `disable-model-invocation: true`~~ — **Done**: neither flag is present; both are true bugs, not design
2. ~~Run `ll-adapt-skills-for-codex` and verify the two yaml files are generated~~ — **Done**: both yaml files exist and are committed
3. ~~Commit the new yaml files~~ — **Done**: no pending git changes
4. Add a regression test to `TestRealSkillsIntegrationGuard` in `scripts/tests/test_adapt_skills_for_codex.py:324`:
   - Method name: `test_all_real_skills_have_openai_yaml`
   - Walk `skills/*/SKILL.md` (same glob as the two existing tests in the class)
   - **Skip skills with `disable-model-invocation: true`** in frontmatter — these are intentionally deferred (ENH-1497); parse frontmatter the same way the existing tests do (yaml.safe_load)
   - For remaining skills, assert `(skill_md.parent / "agents" / "openai.yaml").exists()`
   - Error message: `"skills/{skill_name}/agents/openai.yaml missing. Run: ll-adapt-skills-for-codex --apply"`
   - Run `python -m pytest scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard -v` to verify

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Create `skills/manage-issue/agents/openai.yaml` — this skill has no `disable-model-invocation: true` flag and no yaml file; run `ll-adapt-skills-for-codex --apply` (it will process `manage-issue` since its `description:` field is present) or create the file manually following the three-line convention: `interface:\n  display_name: "Manage Issue"\n  short_description: "<truncated from description field>"`
6. Update `CONTRIBUTING.md` — locate the "New Skill Checklist" section (or nearest equivalent) and add a step to run `ll-adapt-skills-for-codex --apply` after creating a new skill directory; without this, the new CI regression test will fail silently for contributors who don't know to run the adapter

## Impact

- **Priority**: P4 — Two specific skills affected; low blast radius
- **Effort**: Small — re-run the adapter and commit
- **Risk**: Low — Additive
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `.claude/CLAUDE.md` | Documents `ll-adapt-skills-for-codex` and the `disable-model-invocation` skip rule |

## Labels

`bug`, `captured`, `codex`, `skills-api`, `parity`

## Status

**Open** | Created: 2026-05-16 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-05-16T13:56:59 - `9a034326-2e9c-44f4-a1ac-61fd8aee5499.jsonl`
- `/ll:confidence-check` - 2026-05-16T14:00:00Z - `89f7ed97-14f8-4a61-8652-43859d871142.jsonl`
- `/ll:wire-issue` - 2026-05-16T13:53:40 - `29317053-5a72-4c29-a7e3-bb6fe4da5a4b.jsonl`
- `/ll:refine-issue` - 2026-05-16T13:48:16 - `4f7fab7d-3e70-455e-8ef5-3174de20e6fb.jsonl`
- `/ll:format-issue` - 2026-05-16T13:17:07 - `70806095-0635-45d5-8e45-68976e09735c.jsonl`
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
