---
id: ENH-1660
type: ENH
priority: P3
status: done
completed_at: 2026-05-26T03:51:27Z
discovered_date: 2026-05-23
discovered_by: conversation
confidence_score: 100
outcome_confidence: 82
decision_needed: false
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# ENH-1660: ll-action should expose per-skill input schema for agent callers

## Summary

`ll-action list --json` currently returns only `{name, description}` per skill (scripts/little_loops/cli/action.py:169). Agents calling `ll-action invoke <skill>` from non-Claude-Code hosts (Codex, Cursor, aider, scripts, CI) must guess what arguments the skill expects, then parse prose in `skills/<name>/SKILL.md` to figure it out. This is the same drift problem the HarnessAPI paper (docs/research/HarnessAPI-A-Skill-First-Framework.md) identifies for HTTP↔MCP: typed schemas at the boundary stop hallucinated invocations.

## Current Behavior

Concretely, an external agent that wants to call `ll-action invoke refine-issue` has no programmatic way to know whether it takes an issue ID, a file path, both, or flags. Today's options:

1. Shell out to `cat skills/refine-issue/SKILL.md` and have the model read prose — fragile, no validation.
2. Try-and-fail loops on `ll-action invoke` — wasteful, especially for skills with side effects.
3. Hardcode argument shapes in each consuming host — exactly the dual-stack drift HarnessAPI calls out.

`/ll:help` solves this for *humans in Claude Code* but not for programmatic callers.

## Expected Behavior

`ll-action list --json` returns an `args` field per skill (e.g. `"args": "ISSUE_ID [--auto] [--dry-run]"`), sourced from an optional `args:` frontmatter field in `skills/<name>/SKILL.md`. Skills without the field return `"args": null`. An external agent can pass the hint string to its model instead of shelling out to read SKILL.md prose — no try-and-fail loops, no hardcoded argument shapes.

## Motivation

External agents and CI scripts calling `ll-action invoke <skill>` currently have no programmatic discovery path for accepted arguments. This forces hallucination-prone workarounds (prose parsing, try-and-fail loops, per-host hardcoding) — exactly the dual-stack drift problem documented in `docs/research/HarnessAPI-A-Skill-First-Framework.md`. Adding an `args` hint to `list --json` is a minimal additive change (one new frontmatter field + one output key) that unblocks non-Claude-Code hosts without committing to a full JSON Schema dialect.

## Proposed Solution

Two complementary additions, smallest viable first:

**Option A (smaller, recommended):** Extend `list --json` output to include an `args` string per skill, sourced from a new optional `args:` frontmatter field in `skills/<name>/SKILL.md`. Skills that don't add the field get `null`. No schema validation, just a documented hint string the calling agent can pass to its model.

> **Selected:** Option A — extend `list --json` with an `args` hint string (additive, matches existing frontmatter patterns; 19 existing `argument-hint:` skills get immediate value via aliasing)

**Option B (richer):** Add `ll-action schema <skill>` subcommand that returns a structured JSON Schema describing positional args, flags, and expected types. Requires defining a schema-frontmatter convention for skills (e.g. `args_schema:` block with `type`, `required`, `description` per parameter).

Implement A first — additive change to existing frontmatter reading in `_load_skills()` (`scripts/little_loops/cli/action.py`), no new subcommand, no schema dialect. B can layer on later if real usage shows the hint string isn't enough.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-25.

**Selected**: Option A — `args:` hint string in `list --json`

**Reasoning**: Option A is the clear winner: it extends the existing `parse_skill_frontmatter()` / `_load_skills()` pattern already used for `description:` with a single new key read, requires no new subcommand or schema dialect, and delivers immediate value to 19 skills that already have `argument-hint:` (via aliasing). Option B would require defining a new schema-frontmatter convention and a new `ll-action schema` subcommand — high complexity for a problem that a hint string already solves for the target use case (passing the hint to an agent model).

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B | 1/3 | 1/3 | 2/3 | 2/3 | 6/12 |

**Key evidence**:
- Option A: `_load_skills()` already reads `description:` from SKILL.md frontmatter via `parse_skill_frontmatter()`; adding `args:` follows the identical pattern. 19 skills already have `argument-hint:` — aliasing delivers immediate value without a migration pass.
- Option B: No existing `schema` subcommand infrastructure; would require a new schema-frontmatter convention (`args_schema:` block), a new CLI subcommand, and schema dialect definition — well beyond the stated minimum viable change.

**Sub-decision within Option A**: Read both `argument-hint:` and `args:` with `args:` taking precedence (aliasing approach), delivering immediate value to 19 existing skills without requiring a backfill migration pass.

## API/Interface

**New `args:` frontmatter field in `skills/<name>/SKILL.md`:**

```yaml
args: "ISSUE_ID [--auto] [--dry-run]"
```

**`ll-action list --json` output change (Option A):**

```json
// Before
{"name": "refine-issue", "description": "Enrich issue with codebase research"}

// After
{"name": "refine-issue", "description": "Enrich issue with codebase research", "args": "ISSUE_ID [--auto] [--dry-run]"}

// Skills without args: field
{"name": "old-skill", "description": "...", "args": null}
```

## Scope Boundaries

- **In scope**: Option A only — `args:` hint string in `list --json`; populating the field for 5 priority skills (`refine-issue`, `capture-issue`, `confidence-check`, `ready-issue`, `format-issue`)
- **Out of scope**: Option B (`ll-action schema` subcommand with full JSON Schema); schema validation at invocation time; auto-generating hints from SKILL.md prose; changes to `ll-action invoke` argument parsing behavior

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/action.py` — extend `_load_skills()` (~line 169) to read `args:` from frontmatter; update `list --json` serialization
- `skills/ll-refine-issue/SKILL.md` — add `args: "ISSUE_ID [--auto] [--dry-run]"` _(path corrected by `/ll:wire-issue`: `skills/refine-issue/` does not exist)_
- `skills/capture-issue/SKILL.md` — add `args:` field
- `skills/confidence-check/SKILL.md` — add `args:` field
- `skills/ll-ready-issue/SKILL.md` — add `args:` field _(path corrected by `/ll:wire-issue`: `skills/ready-issue/` does not exist)_
- `skills/format-issue/SKILL.md` — add `args:` field
- `docs/reference/API.md` — document new `args` field in ll-action list section

### Dependent Files (Callers/Importers)
- `scripts/tests/test_action.py` — `TestLoadSkills.test_skill_dict_has_name_and_description` and `TestCmdList.test_returns_skill_list` assert the exact `{"name": str, "description": str}` 2-key dict shape; both will need fixture and assertion updates when `"args"` is added
- No production callers of `ll-action list --json` found in scripts/, skills/, commands/, or hooks/ — additive `"args"` key is safe for all existing consumers

### Similar Patterns
- `_load_skills()` already reads `description:` from SKILL.md frontmatter — follow the same pattern for `args:`
- `_read_skill_description()` (`action.py:31`) calls `parse_skill_frontmatter()` then does `fm.get("description", "")` — `args` can be read the same way but returning `fm.get("args") or None` (not `""`, to distinguish absent from empty)
- Optional `None`-valued field serialization: `show.py:_parse_card_fields()` uses `str(x) if x is not None else None` — follow the same pattern for `args`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`argument-hint:` already exists in ~19 skills** (`skills/debug-loop-run/SKILL.md`, `skills/verify-issue-loop/SKILL.md`, `skills/cleanup-loops/SKILL.md`, `skills/configure/SKILL.md`, etc.). This field serves a similar purpose to the proposed `args:`. The implementation must decide: (a) use `args:` as an independent new field (19 skills gain no value without backfill), or (b) treat `args:` as a rename/alias for `argument-hint:` reading both keys with `args` taking precedence. Option (b) delivers value to the 19 skills that already have the hint without requiring a second migration pass.
- **`parse_skill_frontmatter()` already returns all scalar frontmatter fields** (`frontmatter.py:99`) — no changes to the parser needed; `action.py` just needs to read the additional key from the returned dict.
- **Efficient refactor path**: instead of adding a second helper function, refactor `_load_skills()` to call `parse_skill_frontmatter()` directly once per file (reads both `description` and `args` in a single parse) rather than calling `_read_skill_description()`.
- **Return type change needed**: `_load_skills()` is annotated `list[dict[str, str]]`; adding `args: str | None` requires `list[dict[str, str | None]]`.

### Tests
- `scripts/tests/test_action.py:TestCmdList.test_returns_skill_list` — asserts `[{"name": "my-skill", "description": "My skill"}]`; fixture SKILL.md and assertion both need `"args": null`
- `scripts/tests/test_action.py:TestLoadSkills.test_skill_dict_has_name_and_description` — asserts exact 2-key dict shape; needs `"args": null` added
- `scripts/tests/test_action.py:TestReadSkillDescription` — 6 tests; not affected (tests only `_read_skill_description()`)
- New test needed: skill with `args: "ISSUE_ID [--auto]"` in fixture → assert `cmd_list` output includes `"args": "ISSUE_ID [--auto]"`
- New test needed (if `argument-hint:` aliasing implemented): skill with `argument-hint: "[issue-id]"` and no `args:` → assert `_load_skills()` returns `"args": "[issue-id]"`; skill with both fields → assert explicit `args:` wins over `argument-hint:` [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue`:_

### Documentation
- `docs/reference/API.md` — ll-action list subcommand reference
- `docs/reference/CLI.md` — `#### list` section under `### ll-action` currently shows a 2-key JSON example (`{name, description}`); must be updated to show the new `"args"` key (null when absent) [Agent 2 finding]
- `docs/claude-code/skills.md` — `### Frontmatter reference` table lists all recognized SKILL.md frontmatter fields but does not include `args:`; needs a new row documenting this user-authored field [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue`:_

### Configuration
- N/A

## Implementation Steps

1. **Decide `argument-hint:` relationship** (see Codebase Research Findings): either read both `argument-hint` and `args` (with `args` winning) to get immediate value from 19 existing skills, or introduce `args:` as a fully independent field
2. Refactor `_load_skills()` (`action.py:43`) to call `parse_skill_frontmatter()` directly (instead of `_read_skill_description()`) and read both `description` and `args`/`argument-hint` in one parse; return `{"name": ..., "description": ..., "args": str | None}` — update type annotation to `list[dict[str, str | None]]`
3. Update `list --json` serialization (`cmd_list()` at `action.py:169`) — `print_json(skills)` already serializes the full dict, so this is automatic once step 2 is done
4. Update `scripts/tests/test_action.py:TestLoadSkills.test_skill_dict_has_name_and_description` and `TestCmdList.test_returns_skill_list` to expect `"args": null` in the base fixture; add a new test for a skill with `args:` populated
5. Add `args:` field to the 5 priority skills: `skills/refine-issue/SKILL.md`, `skills/capture-issue/SKILL.md`, `skills/confidence-check/SKILL.md`, `skills/ready-issue/SKILL.md`, `skills/format-issue/SKILL.md`
6. Update `docs/reference/API.md` ll-action list section to document the new `args` field
7. Run `python -m pytest scripts/tests/test_action.py -v` to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Fix file paths for 2 priority skills — use `skills/ll-refine-issue/SKILL.md` and `skills/ll-ready-issue/SKILL.md` (the non-prefixed paths `skills/refine-issue/` and `skills/ready-issue/` do not exist)
9. Update `docs/reference/CLI.md` `#### list` section — replace the 2-key JSON example with one showing the `"args"` field (null when absent)
10. Update `docs/claude-code/skills.md` `### Frontmatter reference` table — add row for `args:` describing it as an optional string used by `ll-action list --json` for programmatic callers
11. If `argument-hint:` aliasing is implemented in step 1, add the two aliasing tests to `scripts/tests/test_action.py` (fallback behavior and precedence of explicit `args:` over `argument-hint:`)

## Acceptance Criteria

- [x] `skills/<name>/SKILL.md` accepts an optional `args:` frontmatter field (string)
- [x] `_load_skills()` in scripts/little_loops/cli/action.py reads and returns it
- [x] `ll-action list --json` includes `args` per skill (null when absent)
- [x] At least 5 commonly-invoked skills (`refine-issue`, `capture-issue`, `confidence-check`, `ready-issue`, `format-issue`) have the field populated
- [x] docs/reference/API.md documents the new field
- [x] No regression in existing `list` consumers (added field, not changed shape)

## Impact

- **Priority**: P3 — Quality-of-life improvement for non-Claude-Code callers; not blocking current workflows
- **Effort**: Small — Additive change to existing frontmatter reading and `list --json` serialization; no new subcommands or schema dialect required
- **Risk**: Low — Adds a new output key; existing consumers unaffected (no keys removed or renamed)
- **Breaking Change**: No

## Labels

`enhancement`, `ll-action`, `agent-api`, `discoverability`

## Related

- Originated from discussion of `docs/research/HarnessAPI-A-Skill-First-Framework.md`
- See [[ENH-1661]] for the companion discoverability issue (agents finding `ll-action` in the first place)

## Status

**Done** | Created: 2026-05-23 | Completed: 2026-05-26 | Priority: P3

## Resolution

Implemented Option A: `_load_skills()` in `action.py` refactored to call `parse_skill_frontmatter()` directly, reading `args:` (with `argument-hint:` as fallback). `ll-action list --json` now emits `{"name", "description", "args"}` per skill. Five priority skills populated with `args:` fields. Tests updated with 4 new aliasing/precedence tests. Docs updated in CLI.md, API.md, and skills.md.

## Session Log
- `/ll:manage-issue` - 2026-05-26T03:51:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
- `/ll:ready-issue` - 2026-05-26T03:48:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fbab99cf-3bec-4073-9828-ca111f51daac.jsonl`
- `/ll:confidence-check` - 2026-05-25T12:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/825670bc-74a6-4b2d-b39c-2eeecf7b59b8.jsonl`
- `/ll:decide-issue` - 2026-05-26T03:44:27 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/862c9e92-a486-4454-9a73-4928af017504.jsonl`
- `/ll:wire-issue` - 2026-05-26T03:40:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d20f5560-2c92-4d4b-b42a-601e81b5c9d3.jsonl`
- `/ll:refine-issue` - 2026-05-26T03:34:17 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1080a152-438d-4546-858f-084e48968314.jsonl`
- `/ll:format-issue` - 2026-05-26T02:41:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e516063e-2929-474d-a82c-786360571ff5.jsonl`
- `/ll:confidence-check` - 2026-05-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/009a9eb7-1bb9-4e0f-8397-05b8ef3c2aeb.jsonl`
