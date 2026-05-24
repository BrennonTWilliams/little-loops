---
id: ENH-1660
type: ENH
priority: P3
status: open
discovered_date: 2026-05-23
discovered_by: conversation
confidence_score: 70
outcome_confidence: 65
---

# ENH-1660: ll-action should expose per-skill input schema for agent callers

## Summary

`ll-action list --json` currently returns only `{name, description}` per skill (scripts/little_loops/cli/action.py:169). Agents calling `ll-action invoke <skill>` from non-Claude-Code hosts (Codex, Cursor, aider, scripts, CI) must guess what arguments the skill expects, then parse prose in `skills/<name>/SKILL.md` to figure it out. This is the same drift problem the HarnessAPI paper (docs/research/HarnessAPI-A-Skill-First-Framework.md) identifies for HTTP↔MCP: typed schemas at the boundary stop hallucinated invocations.

## Problem

Concretely, an external agent that wants to call `ll-action invoke refine-issue` has no programmatic way to know whether it takes an issue ID, a file path, both, or flags. Today's options:

1. Shell out to `cat skills/refine-issue/SKILL.md` and have the model read prose — fragile, no validation.
2. Try-and-fail loops on `ll-action invoke` — wasteful, especially for skills with side effects.
3. Hardcode argument shapes in each consuming host — exactly the dual-stack drift HarnessAPI calls out.

`/ll:help` solves this for *humans in Claude Code* but not for programmatic callers.

## Proposal

Two complementary additions, smallest viable first:

**Option A (smaller):** Extend `list --json` output to include an `args_hint` string per skill, sourced from a new optional `args:` frontmatter field in `skills/<name>/SKILL.md`. Skills that don't add the field get `null`. No schema validation, just a documented hint string the calling agent can pass to its model.

**Option B (richer):** Add `ll-action schema <skill>` subcommand that returns a structured JSON Schema describing positional args, flags, and expected types. Requires defining a schema-frontmatter convention for skills (e.g. `args_schema:` block with `type`, `required`, `description` per parameter).

Recommend starting with A — it's an additive change to existing frontmatter and `_load_skills()`, no new subcommand, no schema dialect to commit to. B can layer on later if real usage shows the hint string isn't enough.

## Acceptance Criteria

- [ ] `skills/<name>/SKILL.md` accepts an optional `args:` frontmatter field (string)
- [ ] `_load_skills()` in scripts/little_loops/cli/action.py reads and returns it
- [ ] `ll-action list --json` includes `args` per skill (null when absent)
- [ ] At least 5 commonly-invoked skills (`refine-issue`, `capture-issue`, `confidence-check`, `ready-issue`, `format-issue`) have the field populated
- [ ] docs/reference/API.md documents the new field
- [ ] No regression in existing `list` consumers (added field, not changed shape)

## Related

- ENH-1660 came from discussion of docs/research/HarnessAPI-A-Skill-First-Framework.md
- See [[ENH-1661]] for the companion discoverability issue (agents finding `ll-action` in the first place)
