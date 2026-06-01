---
id: FEAT-1857
type: FEAT
priority: P3
status: done
captured_at: '2026-06-01T17:35:32Z'
completed_at: '2026-06-01T22:00:44Z'
discovered_date: '2026-06-01'
discovered_by: capture-issue
relates_to:
- FEAT-1810
- FEAT-1737
parent: EPIC-1864
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1857: `/ll:scope-epic` — theme-to-EPIC decomposition skill

## Summary

Add a `/ll:scope-epic` skill that takes a high-level theme/goal description and produces (1) an EPIC issue file scoped to the theme and (2) 3–8 child issue stubs pre-wired with `parent: EPIC-NNN`. This is the upstream creation step that `/ll:capture-issue --parent` assumes already happened.

## Current Behavior

To start an EPIC-shaped initiative today the user must:

1. Manually compose an EPIC issue (or call `/ll:capture-issue "epic: ..."`).
2. Manually identify child scope.
3. Repeatedly call `/ll:capture-issue --parent EPIC-NNN ...` for each child.

There is no skill that decomposes a theme into the EPIC + skeleton children in one pass. `/ll:capture-issue` creates *one* issue at a time and `--parent` requires the EPIC to already exist.

## Expected Behavior

```
$ /ll:scope-epic "Harness Codex CLI as a full claude-p replacement"

[skill proposes]
EPIC-XXXX: Harness Codex CLI as a full claude-p replacement
  ├── FEAT-XXXX: Codex auth & session management
  ├── FEAT-XXXX: Model selection & defaulting
  ├── FEAT-XXXX: Streaming output adapter
  ├── FEAT-XXXX: Tool-use bridge
  └── ENH-XXXX: MCP server compatibility

Proceed? [y/n]
```

On confirm: writes all 6 files with wiring (`parent:` on children, `relates_to:` + `## Children` on the EPIC). User then runs `/ll:refine-issue` on each child as needed.

## Motivation

Theme-to-EPIC decomposition is currently the highest-friction step in starting any multi-issue initiative. Users either skip the EPIC and end up with orphan issues, or write the EPIC and skip the children (so `/ll:scan-codebase` discovers them as orphans later, requiring `/ll:link-epics` to wire them back in).

Capturing the decomposition once at the start — when the theme is freshest in the user's head — produces better-scoped children than discovering them piecewise weeks later.

## Proposed Solution

Skill flow:

1. **Accept theme** — natural-language description, optional file path to a goals doc.
2. **Decompose (LLM)** — propose EPIC summary + 3–8 child issues, each with type (FEAT/ENH/BUG), priority, and one-line summary. Hint that children should be **independently shippable** (mirror `/ll:issue-size-review`'s principle).
3. **Present plan** — table view with type, priority, summary. User can edit interactively (add/remove/reorder/retype) before committing.
4. **Allocate IDs** — sequential via `ll-issues next-id`.
5. **Write EPIC first** — full template, `## Children` section with all proposed children, `relates_to:` frontmatter populated.
6. **Write each child** — minimal template (mirror `--quick`), `parent: EPIC-NNN` frontmatter set.
7. **Stage all files**.
8. **Print next-step hint**: `/ll:refine-issue` on any child whose scope needs deepening.

**Boundary vs. FEAT-1810 (`goal-cluster`)**: `goal-cluster` *executes* a list of related goals through loops; `scope-epic` *creates* the issue files that represent those goals. They are upstream/downstream of each other and may share the decomposition LLM prompt.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **No existing inline LLM→JSON precedent**: No current skill asks the model to emit a structured JSON decomposition list inline. The closest patterns are CLI tools emitting JSON (`ll-issues list --type EPIC --json`, `ll-issues fingerprint`) that skills then parse — but those are CLI-driven, not LLM-driven. The JSON schema for child proposals will be novel; document it explicitly in SKILL.md.
- **EPIC wiring is prose-level duplication, not a shared helper**: Both `capture-issue` Phase 4c and `link-epics` Step 6 (6a/6b/6c) implement the same 3-case `relates_to:` update and `## Children` append/create logic as LLM prompt instructions using `Edit`. There is no factored Python helper yet — FEAT-1857's Implementation Step 5 "factor Phase 4c into a shared helper" is an aspirational refactor, not a pre-existing function to call.
- **`assemble_issue_markdown()` is the right file-creation entry point**: `scripts/little_loops/issue_template.py:assemble_issue_markdown()` accepts `issue_type`, `variant`, `issue_id`, `title`, `frontmatter` dict, and `content` dict. Use `variant="full"` for the EPIC and `variant="minimal"` for stubs. Section defaults come from `templates/epic-sections.json` and `templates/feat-sections.json`.
- **`config-schema.json` has no `epics` key today**: The `epics.scope.*` config proposed in this issue will require creating a new top-level `epics` property in `config-schema.json`. Check neighboring objects (`issues`, `project`, `scan`) for the schema property-definition shape to replicate.
- **`## Children` bullet format is stable across 8+ live EPIC files**: `- **TYPE-NNN** — one-sentence title` (bold ID, em-dash, sentence). EPIC-1864 (the parent of this issue) is the canonical live example.

## Integration Map

### Files to Modify
- `skills/scope-epic/SKILL.md` (new) — main skill; phases mirror `skills/capture-issue/SKILL.md` structure
- `skills/scope-epic/templates.md` (new, optional) — EPIC and child stub templates (may inline in SKILL.md instead)
- `commands/help.md` — add `/ll:scope-epic` listing under Issue Discovery group
- `.claude/CLAUDE.md` — add `scope-epic`^ to Commands & Skills section under Issue Discovery
- `config-schema.json` — add `epics.scope.min_children` (default 3) and `epics.scope.max_children` (default 8) under `epics` object (object does not currently exist in schema)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — add `### /ll:scope-epic` section and `| scope-epic |` row in Quick Reference table (after `review-epic` row at ~line 936)
- `README.md` — bump skill count: "60 skills" → "61 skills" (~line 161)
- `CONTRIBUTING.md` — bump skill definition count: "32 skill definitions" → "33" (~line 123); add `scope-epic/` entry in skills tree (~line 147)
- `docs/ARCHITECTURE.md` — bump skill count: "32 skill definitions" → "33" (~line 114)
- `skills/scope-epic/agents/openai.yaml` (new) — Codex adaptation companion, auto-generated via `ll-adapt-skills-for-codex`

### Dependent Files (Callers/Importers)
- `skills/capture-issue/SKILL.md` — Phase 4c: Wire Parent EPIC: the canonical 3-case `relates_to:` update + `## Children` append/create logic; replicate this exactly
- `skills/link-epics/SKILL.md` — Step 6: Apply Assignments (6a/6b/6c/6d): same wiring operations applied retroactively; use as secondary implementation reference
- `skills/issue-size-review/SKILL.md` — Phase 4, step 2: independently-shippable definition (each child must produce its own PR with tests; no artifact-type splits)

### Similar Patterns
- `skills/capture-issue/SKILL.md` — Conversation Mode section: markdown table + `AskUserQuestion` multiSelect UI for presenting a list of proposals before writing files
- `skills/link-epics/SKILL.md` — Step 5: Proposal Flow > Interactive Mode: scored multiSelect table pattern; adapt for child-review step
- `skills/capture-issue/SKILL.md` — Phase 4: Execute Action: per-issue `ll-issues next-id` call made **immediately before each `Write`** — do NOT batch-allocate IDs upfront (see Duplicate-ID recovery callout in that section)
- `scripts/little_loops/cli/issues/next_id.py` — `cmd_next_id()` → `scripts/little_loops/issue_parser.py:get_next_issue_number()`: returns global max integer + 1 across all issue types/dirs, zero-padded to 3 digits (e.g., `"071"`)
- `scripts/little_loops/issue_template.py` — `assemble_issue_markdown()`: builds a well-formed issue file from type + variant + frontmatter dict + content overrides; use variant `"full"` for EPIC, `"minimal"` for children; `load_issue_sections()` loads per-type section definitions from `templates/`
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()`: in-place frontmatter field updates used by `capture-issue` Phase 4c for `parent:` and `relates_to:`
- `scripts/little_loops/file_utils.py` — `atomic_write()`: safe write-to-temp-then-rename pattern; use for each issue file
- `.issues/epics/P2-EPIC-1864-epic-lifecycle-and-visibility-tooling.md` — `## Children` section: canonical bullet format `- **TYPE-NNN** — one-sentence title` (live example with 8 children)

### Tests
- `scripts/tests/test_scope_epic_skill.py` (new) — model after `scripts/tests/test_issue_size_review_skill.py:TestIssueSizeReviewSkillWriteBack` (slice by heading, assert on content) and `scripts/tests/test_audit_loop_run_skill.py:TestAssessLoopSkill` (existence checks):
  - Skill file exists: `skills/scope-epic/SKILL.md`
  - Required phases present: ID allocation, interactive review, EPIC write, child write, EPIC wiring
  - `Edit` listed in `allowed_tools` frontmatter (required for in-place EPIC wiring)
  - `AskUserQuestion` present in interactive review phase
  - Both `relates_to:` and `## Children` wiring referenced in file-write phase
  - `ll-issues next-id` referenced for ID allocation (not batch increment)
- Existing `scripts/tests/test_issues_cli.py:TestIssuesCLINextId` and `scripts/tests/test_issue_parser.py:TestGetNextIssueNumber` already cover ID allocation — no new ID tests needed unless a `--count N` flag is added

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_config_schema.py` — add `test_epics_scope_in_schema` guard method asserting `epics` top-level key exists with `scope.min_children` (integer, default 3) and `scope.max_children` (integer, default 8) sub-properties; follows existing pattern e.g. `test_commands_review_epic_in_schema` (line 98)
- `scripts/tests/test_feat1857_doc_wiring.py` (new) — following `scripts/tests/test_feat1856_doc_wiring.py` pattern: assert `/ll:scope-epic` in help.md command reference + quick table, `scope-epic` in `.claude/CLAUDE.md` Commands & Skills, `scope-epic` in `docs/reference/COMMANDS.md` section + Quick Reference row, `skills/scope-epic/agents/openai.yaml` exists
- `scripts/tests/test_issue_template.py` (optional) — `test_full_variant_with_epic` asserting EPIC `variant="full"` includes `## Children` section from `templates/epic-sections.json` common_sections

### Documentation
- `docs/guides/EPIC_GUIDE.md` (new) — end-to-end EPIC workflow: scope → refine → review → ship
- `commands/help.md` — add to Issue Discovery group

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/COMMANDS.md` — add `### /ll:scope-epic` section describing arguments, phases, and exit behavior; add `| scope-epic |` to Quick Reference table (after `review-epic` row ~line 936)
- `README.md` — bump skill count: "60 skills" → "61 skills" (~line 161)
- `CONTRIBUTING.md` — bump "32 skill definitions" → "33" (~line 123); add `│   ├── scope-epic/` to skills tree (~line 147)
- `docs/ARCHITECTURE.md` — bump "32 skill definitions" / "32 composable skills" → "33" (~line 114)

### Configuration
- `config-schema.json` — `epics.scope.min_children` (integer, default 3): fewer proposals triggers "consider `/ll:capture-issue`" warning
- `config-schema.json` — `epics.scope.max_children` (integer, default 8): more proposals triggers "consider sub-EPIC decomposition" suggestion

## Implementation Steps

1. **Scaffold skill** — create `skills/scope-epic/SKILL.md`; structure phases to mirror `skills/capture-issue/SKILL.md`: flag parsing → theme extraction → LLM decomposition → interactive review → ID allocation + file writes → EPIC wiring → git staging. Add `Edit` and `Write` to `allowed_tools` frontmatter (required for in-place EPIC wiring via Phase 4c).
2. **Decomposition prompt** — ask the LLM to output a structured JSON array: `[{"type": "FEAT"|"ENH"|"BUG", "priority": "P2"|"P3", "summary": "...", "title": "..."}]`. No existing skill uses inline LLM→JSON; the closest structural reference is `skills/workflow-automation-proposer/SKILL.md`. Document the schema in SKILL.md. The child-sizing constraint comes from `skills/issue-size-review/SKILL.md` Phase 4 step 2: each child must be independently shippable (no artifact-type splits, no wiring-from-implementation splits).
3. **Interactive edit loop** — display a markdown table (columns: #, Type, Priority, Summary) then `AskUserQuestion` with `multiSelect: true` to select which children to keep. Adapt the UI pattern from `skills/capture-issue/SKILL.md` Conversation Mode (table + multiSelect) and `skills/link-epics/SKILL.md` Step 5: Proposal Flow > Interactive Mode (scored proposal table). Follow with a single-select confirm/edit/cancel question.
4. **ID allocation + file writes** — call `ll-issues next-id` once **immediately before writing each file** (not batched upfront — see Duplicate-ID recovery callout in `skills/capture-issue/SKILL.md` Phase 4). Use `scripts/little_loops/issue_template.py:assemble_issue_markdown()` with variant `"full"` and type `"EPIC"` for the EPIC file, variant `"minimal"` for each child. Use `scripts/little_loops/file_utils.py:atomic_write()` for each file write. Write EPIC first, then children in order.
5. **Wire EPIC ↔ children** — replicate Phase 4c from `skills/capture-issue/SKILL.md` for each child: (a) append child ID to EPIC `relates_to:` frontmatter using the 3-case logic (absent → insert; empty list → replace; populated → append) via `scripts/little_loops/frontmatter.py:update_frontmatter()`; (b) append `- **CHILD_ID** — [one-sentence summary]` bullet to EPIC `## Children` section (create section before `## Status` if absent) via `Edit`; (c) set `parent: EPIC-NNN` in each child's frontmatter. Reference `skills/link-epics/SKILL.md` Step 6 (6a/6b/6c) as a secondary guide.
6. **Git staging** — `git add` each written file (EPIC + all children) after all writes and wiring edits complete.
7. **Config schema** — add `epics.scope` object to `config-schema.json` with `min_children` (integer, default 3, minimum 1) and `max_children` (integer, default 8) properties. The `epics` key does not currently exist in the schema; check neighboring config objects (e.g., `issues`, `project`) for the correct property-definition shape to match.
8. **Tests** — create `scripts/tests/test_scope_epic_skill.py` following `scripts/tests/test_issue_size_review_skill.py:TestIssueSizeReviewSkillWriteBack` (read SKILL.md, slice by heading, assert content present) and `scripts/tests/test_audit_loop_run_skill.py:TestAssessLoopSkill` (file existence + key string checks). Assert: file exists, phases present, `Edit` in allowed_tools, `AskUserQuestion` in review phase, `relates_to:` and `## Children` both referenced, `ll-issues next-id` in ID step.
9. **Docs + help** — add `scope-epic`^ to `commands/help.md` Issue Discovery group; add entry to `.claude/CLAUDE.md` Commands & Skills > Issue Discovery section.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

10. **Doc reference wiring** — add `### /ll:scope-epic` section to `docs/reference/COMMANDS.md` with description, usage, flags, and trigger keywords; add `| scope-epic |` row to Quick Reference table after `review-epic` row (~line 936).
11. **Skill count bumps** — bump skill counts in `README.md` ("60 skills" → "61"), `CONTRIBUTING.md` ("32 skill definitions" → "33", plus add `│   ├── scope-epic/` to the skills tree at ~line 147), and `docs/ARCHITECTURE.md` ("32 composable skills" → "33"). These hardcoded counts are verified by `ll-verify-docs`; leaving them stale causes a CI mismatch.
12. **Config schema test** — add `test_epics_scope_in_schema` method to `scripts/tests/test_config_schema.py` asserting: `epics` exists in top-level properties, `scope` sub-object with `min_children` (integer, default 3) and `max_children` (integer, default 8). Follow pattern from `test_commands_review_epic_in_schema` (line 98).
13. **Doc wiring test** — create `scripts/tests/test_feat1857_doc_wiring.py` following `scripts/tests/test_feat1856_doc_wiring.py` pattern: assert `/ll:scope-epic` in help.md, `scope-epic` in CLAUDE.md, `scope-epic` in COMMANDS.md, `skills/scope-epic/agents/openai.yaml` exists (generated via `ll-adapt-skills-for-codex`).
14. **Codex adaptation** — run `ll-adapt-skills-for-codex --apply` after creating `skills/scope-epic/SKILL.md` to generate `skills/scope-epic/agents/openai.yaml`. The CI test `test_all_real_skills_have_openai_yaml` fails without this file.

## Impact

- **Priority**: P3 — Quality-of-life; not blocking but eliminates a multi-step manual flow.
- **Effort**: Medium — Reuses `capture-issue` writing + wiring; new LLM prompt + interactive UI.
- **Risk**: Low — Additive skill; no behavioral change to existing tools.
- **Breaking Change**: No

## Use Case

User opens little-loops with the goal "make our docs sweep automatic" and runs `/ll:scope-epic "Automatic docs sweep — detect drift, propose updates, verify links"`. Skill proposes EPIC-XXXX with 5 children (detection, proposal, verification, scheduling, reporting). User accepts. 6 issue files exist 30 seconds later, all wired. Today this would take 5+ manual `/ll:capture-issue` invocations and a separate EPIC creation step.

## Acceptance Criteria

- [ ] `/ll:scope-epic "<theme>"` proposes an EPIC + 3–8 children.
- [ ] User can edit/remove/retype proposed children before commit.
- [ ] On commit, EPIC file is written first with full `relates_to:` and `## Children` populated.
- [ ] Each child is written with `parent: EPIC-NNN` frontmatter.
- [ ] All files staged for git.
- [ ] Cancellation at the confirm step writes nothing.
- [ ] Theme that produces fewer than `min_children` proposals emits a warning ("this might be a single-issue task, consider `/ll:capture-issue`").
- [ ] Theme that produces more than `max_children` proposals suggests sub-EPIC decomposition.

## API/Interface

```bash
/ll:scope-epic "<theme description>"
/ll:scope-epic --from-doc thoughts/goals/feature-x.md
/ll:scope-epic "<theme>" --priority P2          # override default EPIC priority
```

No Python API.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`enhancement`, `epics`, `skill`, `decomposition`, `captured`

## Session Log
- `/ll:ready-issue` - 2026-06-01T21:46:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9a66023e-f692-4d62-bacb-ee50c29a40b2.jsonl`
- `/ll:wire-issue` - 2026-06-01T23:30:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/540b3294-cbb3-4d48-9bcb-553455ab6996.jsonl`
- `/ll:refine-issue` - 2026-06-01T21:22:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c0a7b6da-9f87-494e-bbbf-ba6d77bc6215.jsonl`
- `/ll:format-issue` - 2026-06-01T17:44:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/756a4b19-3f84-45ba-b4ff-aeb860ba5ecf.jsonl`
- `/ll:capture-issue` - 2026-06-01T17:35:32Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/277dd3c5-ffef-46cb-bcc6-124409ce1225.jsonl`
- `/ll:confidence-check` - 2026-06-01T23:31:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4c5c971e-9282-4dbf-a93b-36e183431aca.jsonl`

---

## Status

**Open** | Created: 2026-06-01 | Priority: P3
