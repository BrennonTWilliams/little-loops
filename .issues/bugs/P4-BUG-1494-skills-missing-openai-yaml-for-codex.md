---
id: BUG-1494
type: BUG
priority: P4
status: open
captured_at: "2026-05-16T13:04:12Z"
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by: [ENH-1497]
relates_to: [FEAT-1486]
labels: [captured, codex, skills-api, parity]
---

# BUG-1494: Two skills missing `agents/openai.yaml` for Codex

## Summary

`skills/verify-issue-loop/` and `skills/init/` do not have an `agents/openai.yaml` sibling alongside their `SKILL.md`. Per the Codex Skills API contract documented in `ll-adapt-skills-for-codex`, both files are required for the skill to be discoverable from Codex. 28 of 30 skill directories have the yaml; these two are stragglers.

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

Verify by:
1. Reading the frontmatter of `skills/verify-issue-loop/SKILL.md` and `skills/init/SKILL.md` for `disable-model-invocation: true` — if present, this is by design (see ENH-1497 for the broader question of whether to expose those skills)
2. If neither has the flag, this is a true bug — re-run `ll-adapt-skills-for-codex` and commit the missing yaml files

## Integration Map

### Files to Modify / Create
- `skills/verify-issue-loop/agents/openai.yaml` — create if missing
- `skills/init/agents/openai.yaml` — create if missing

### Tests
- `scripts/tests/test_adapt_skills_for_codex.py` — add an assertion that every `skills/*/SKILL.md` without `disable-model-invocation: true` has a corresponding `agents/openai.yaml`

## Implementation Steps

1. Inspect both SKILL.md files for `disable-model-invocation: true` — if present, close this bug and triage under ENH-1497
2. If not present, run `ll-adapt-skills-for-codex` and verify the two yaml files are generated
3. Commit the new yaml files
4. Add a regression test asserting parity between SKILL.md files and `agents/openai.yaml` files (skipping disable-model-invocation skills)

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
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
