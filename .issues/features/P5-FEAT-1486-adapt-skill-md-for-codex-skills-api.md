---
id: FEAT-1486
type: FEAT
priority: P5
status: done
captured_at: '2026-05-15T23:00:00Z'
discovered_date: 2026-05-15
discovered_by: manage-issue
parent: EPIC-1463
decision_needed: false
confidence_score: 98
outcome_confidence: 67
score_complexity: 13
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
missing_artifacts: false
completed_at: 2026-05-15T00:00:00Z
---

# FEAT-1486: Adapt ll Skills for Codex Skills API

## Summary

The Codex CLI Skills API (`~/.codex/skills/<name>/SKILL.md`) is confirmed stable
(researched in FEAT-1483). ll's existing `skills/*/SKILL.md` frontmatter is
incompatible: the required `name:` field is absent, and the recommended
`metadata.short-description:` and `agents/openai.yaml` UI metadata are missing.
This issue implements the adaptation needed to make ll skills installable and
discoverable from a Codex CLI session.

## Current Behavior

ll skills live at `skills/*/SKILL.md`. Claude Code discovers them via the plugin
SDK. Codex users have no in-session access to ll skills — they must call
`ll-action` or `ll-auto` from a terminal.

## Expected Behavior

After this issue:
- Each `skills/*/SKILL.md` has the required `name:` frontmatter field.
- Each `skills/*/SKILL.md` has `metadata.short-description:` for the Codex TUI chip.
- Each skill directory has an `agents/openai.yaml` with `display_name` and
  `short_description`.
- ll skills can be installed into a Codex session via
  `codex plugin marketplace add BrennonTWilliams/little-loops --sparse skills`
  (or the built-in `skill-installer`).

## Motivation

This feature would:
- Unblock Codex host-compatibility for skill discovery — currently shows ✗ in
  `docs/reference/HOST_COMPATIBILITY.md`; this ships a ✓
- Enable Codex CLI users to invoke ll skills in-session (currently they must fall
  back to terminal `ll-action` or `ll-auto` calls)
- Surface ll skills in the Codex TUI chip panel via `metadata.short-description`,
  making them discoverable without knowing the exact skill name
- Keep the change additive and reversible — Claude Code ignores unrecognized
  frontmatter fields

## Use Case

**Who**: An ll user whose primary host is Codex CLI

**Context**: They open a Codex session on a project and want to run `/ll:capture-issue`
or `/ll:format-issue` directly from the Codex TUI without switching to a terminal

**Goal**: Invoke ll skills with slash-command discovery in the Codex skill picker

**Outcome**: All ll skills appear in the Codex chip panel with short descriptions;
`codex plugin marketplace add BrennonTWilliams/little-loops --sparse skills`
installs and exposes them end-to-end

## Acceptance Criteria

- [ ] All `skills/*/SKILL.md` files have `name:` frontmatter matching their
      directory slug (e.g., `skills/manage-issue/SKILL.md` → `name: manage-issue`)
- [ ] All `skills/*/SKILL.md` files have `metadata:\n  short-description:` (≤80 chars)
- [ ] Each `skills/*/` directory has `agents/openai.yaml` with `display_name`
      and `short_description`
- [ ] `docs/reference/HOST_COMPATIBILITY.md` Codex "Skill discovery" cell updated
      from `✗` to `✓` (or `(partial)` if only a subset of skills is adapted)
- [ ] `thoughts/research/codex-command-discovery.md` gating recommendation updated
      to reflect implementation status

## Research Notes

See `thoughts/research/codex-command-discovery.md` for the full Codex Skills API
spec (SKILL.md frontmatter format, `agents/openai.yaml` format, installation
methods, and compatibility gap analysis).

## Integration Map

### Files to Modify

- `skills/*/SKILL.md` — add `name:` and `metadata.short-description:` to frontmatter
- `docs/reference/HOST_COMPATIBILITY.md` — flip Codex "Skill discovery" cell from ✗ to ✓

### Files to Create

- `skills/*/agents/openai.yaml` — one per skill directory

### Dependent Files (Callers/Importers)

- `scripts/little_loops/host_runner.py` — `resolve_host()` picks the active host;
  no change needed but verify skill invocation path is unaffected
- `.claude-plugin/plugin.json` — plugin manifest lists skills; no change needed
  (Claude Code discovery is unaffected by added frontmatter fields)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/action.py` — imports `_find_plugin_root` from `skill_expander`; unaffected by this change but shares the function being reused
- `scripts/little_loops/issue_manager.py` — imports `expand_skill` from `skill_expander`; `expand_skill()` calls `strip_frontmatter()` so new frontmatter fields are stripped before prompt delivery — no change needed
- `scripts/little_loops/frontmatter.py` — `update_frontmatter()` is called with nested `{"metadata": {"short-description": desc}}` in the new script; current type annotation `dict[str, str | int]` must widen to `dict[str, Any]` to avoid mypy failure (callers passing flat str/int are unaffected)

### Similar Patterns

- `skills/scrape-docs/SKILL.md` — existing skill with frontmatter to use as a
  reference baseline when adding `name:` and `metadata.short-description:`
- `thoughts/research/codex-command-discovery.md` — documents the canonical
  frontmatter format and `agents/openai.yaml` schema to follow

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/cli/migrate.py:_set_fields()` — insert-or-replace pattern for flat frontmatter fields; handles "field absent → insert before closing `---`" and "field present → replace in-place"; identical copy in `migrate_relationships.py`
- `scripts/little_loops/frontmatter.py:update_frontmatter()` — YAML-roundtrip update required for nested `metadata.short-description:` field; flat `_set_fields()` does not handle nested keys
- `scripts/little_loops/skill_expander.py:_find_plugin_root()` — resolves the skills directory; reuse to locate `skills/*/SKILL.md` in any new script
- `scripts/little_loops/cli/generate_skill_descriptions.py:_process_skills()` — canonical `for skill_md in sorted(skills_dir.glob("*/SKILL.md")):` enumeration loop with `skill_name = skill_md.parent.name`
- `scripts/little_loops/cli/generate_skill_descriptions.py:_parse_frontmatter()` — flat frontmatter reader; detects absent fields via `fm.get("name")`, `fm.get("metadata")`
- `scripts/little_loops/cli_args.py:add_dry_run_arg()` — shared `--dry-run` argument; import for any new migration CLI
- `scripts/little_loops/cli/__init__.py` + `scripts/pyproject.toml` — three-file registration pattern: new module → re-export from `cli/__init__.py` → `[project.scripts]` entry in pyproject.toml

### Tests

- No automated tests for SKILL.md frontmatter validation; verify by running
  `codex` locally and confirming skill appears in the chip panel
- Manual smoke test: `codex plugin marketplace add ... --sparse skills` then
  invoke one adapted skill

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_adapt_skills_for_codex.py` — new test file needed; follow `test_generate_skill_descriptions.py` pattern (`_make_skill()` helper, `_find_plugin_root` mock via `patch(... return_value=tmp_path)`); cover: `name:` insert when absent/no-op when present; `metadata.short-description:` nested YAML write; `agents/openai.yaml` creation; dry-run leaves files unchanged; `main_adapt_skills_for_codex()` returns 0 on success
- `scripts/tests/test_frontmatter.py` — `TestUpdateFrontmatter` has no test for nested dict value (`{"metadata": {"short-description": "..."}}`) — add one; also covers the type-signature widening
- `scripts/tests/test_create_extension_wiring.py` — add `TestFeat1486LlAdaptSkillsWiring` class asserting `"ll-adapt-skills-for-codex"` presence in `commands/help.md`, `.claude/CLAUDE.md`, `docs/reference/CLI.md`, and `skills/configure/areas.md` (follows `TestEnh1395LlGenerateSkillDescriptionsWiring` pattern)
- Integration guard (new test file or appended): glob real `skills/*/SKILL.md` after adaptation and assert each has `name:` == dir name and `metadata.short-description:` ≤ 80 chars

### Documentation

- `docs/reference/HOST_COMPATIBILITY.md` — update Codex "Skill discovery" cell
- `thoughts/research/codex-command-discovery.md` — update gating recommendation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `### ll-adapt-skills-for-codex` section (per established pattern for every new `ll-*` CLI tool)
- `commands/help.md` — add one-line entry in the CLI TOOLS block
- `.claude/CLAUDE.md` "CLI Tools" section — add one-line entry for `ll-adapt-skills-for-codex`
- `skills/configure/areas.md` — increment "Authorize all 20" → "Authorize all 21" and append `ll-adapt-skills-for-codex` to the permission list (line ~823)
- `README.md` — increment "22 typed CLI tools" → 23 and "23 CLI tools" → 24 (lines 46 and 164)
- `CONTRIBUTING.md` "New Skill Checklist" frontmatter template — add `name:` (and optionally `metadata.short-description:`) to the canonical SKILL.md template example so new skills are Codex-compatible from creation
- `docs/claude-code/skills.md` "Frontmatter Reference" table — add `metadata.short-description` row with a note that it is Codex-specific (≤80 chars)
- `docs/reference/API.md` — add module entry for `little_loops.cli.adapt_skills_for_codex` documenting `main_adapt_skills_for_codex()` (follows `little_loops.cli.generate_skill_descriptions` section pattern) [Agent 2 finding]
- `docs/ARCHITECTURE.md` — add note that `skills/*/agents/` is a recognized artifact directory (one `agents/openai.yaml` per skill), introduced by this issue [Agent 2 finding]

### Cross-Tool Interactions

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/generate_skill_descriptions.py:_write_description_to_frontmatter()` — updates `description:` in SKILL.md but NOT `metadata.short-description:`. A subsequent `ll-generate-skill-descriptions --apply` run after `ll-adapt-skills-for-codex --apply` will cause divergence between the two fields. **Decision**: document as a known maintenance concern in `docs/claude-code/skills.md` (or extend `ll-adapt-skills-for-codex` to re-seed `metadata.short-description:` from `description:` when already present, making it safe to re-run). `scripts/little_loops/cli/docs.py:check_skill_budget()` reads only `description:` — budget verification is unaffected.

### Configuration

- N/A — no ll-config.json or settings changes required

## Implementation Steps

1. Audit all `skills/*/SKILL.md` files to collect those missing `name:` and
   `metadata.short-description:` frontmatter (script or glob + grep)
2. Add `name: <dir-slug>` and `metadata:\n  short-description: <≤80-char text>`
   to each `skills/*/SKILL.md` frontmatter
3. Create `skills/*/agents/openai.yaml` for each skill directory with
   `display_name` and `short_description` fields per the Codex Skills API spec
4. Update `docs/reference/HOST_COMPATIBILITY.md` Codex "Skill discovery" cell
   from ✗ to ✓ (or `(partial)` if only a subset is adapted)
5. Update `thoughts/research/codex-command-discovery.md` gating recommendation
6. Verify end-to-end: install via `codex plugin marketplace add ... --sparse skills`
   and confirm at least one ll skill appears and runs in Codex TUI

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 (Audit)**: Use `scripts/little_loops/skill_expander.py:_find_plugin_root()` to locate the skills dir, then `glob("*/SKILL.md")` to enumerate all 30 files. **Do NOT use `_parse_frontmatter()` from `generate_skill_descriptions.py` for gap detection** — it is a flat line-splitting parser; nested YAML like `metadata:\n  short-description:` flattens to `fm["metadata"] = ""`, making the idempotency check return a false "absent". Use `yaml.safe_load(frontmatter_text)` directly and check `fm.get("name")` and `isinstance(fm.get("metadata"), dict)`.
- **Step 2 (`name:` field)**: Reuse `_set_fields()` from `scripts/little_loops/cli/migrate.py` for the flat `name:` insert. Value is always `skill_md.parent.name` (the directory slug, e.g. `"capture-issue"`).
- **Step 2 (`metadata.short-description:`)**: The nested YAML structure requires `scripts/little_loops/frontmatter.py:update_frontmatter()` — flat `_set_fields()` does not handle nested keys. Call with `{"metadata": {"short-description": desc}}`.
- **Step 2 (short-description text)**: The existing `description:` field in each SKILL.md is contextually accurate; use it as the `metadata.short-description:` value (truncate to 80 chars if needed). **Note**: many skills use `description: |` (YAML literal block scalar), so `yaml.safe_load` returns multiline text with trailing newlines — strip whitespace and take only the first line (`.splitlines()[0].strip()`) before truncating to 80 chars.
- **Step 3 (`agents/openai.yaml`)**: No prior examples exist in the codebase. **Confirmed format** from `thoughts/research/codex-command-discovery.md` — fields are nested under an `interface:` block (NOT flat at the root):
  ```yaml
  interface:
    display_name: "Capture Issue"
    short_description: "Use when asked to capture or create an issue from conversation or natural language."
  ```
  `display_name` = title-cased slug (e.g., `"Capture Issue"`), `short_description` = same value as `metadata.short-description:`. `icon_small` and `icon_large` are optional per spec.
- **Script structure**: If wrapping in a CLI, follow the three-file pattern — new module at `scripts/little_loops/cli/adapt_skills_for_codex.py` with `main_adapt_skills_for_codex()`, re-exported from `scripts/little_loops/cli/__init__.py`, registered in `scripts/pyproject.toml` as `ll-adapt-skills-for-codex`. Use `add_dry_run_arg()` from `cli_args.py`.
- **Tests**: Model after `scripts/tests/test_generate_skill_descriptions.py:_make_skill()` helper to create temp skill dirs; mock `_find_plugin_root()` to redirect to `tmp_path`. **Important**: patch at `"little_loops.cli.adapt_skills_for_codex._find_plugin_root"` (the delegation wrapper in the new module), NOT at `"little_loops.skill_expander._find_plugin_root"` — patch where it is looked up, not where it is defined (same pattern used in `test_generate_skill_descriptions.py:TestMainGenerateSkillDescriptions`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Widen `update_frontmatter()` type annotation in `scripts/little_loops/frontmatter.py` from `dict[str, str | int]` to `dict[str, Any]` — required before calling it with the nested `{"metadata": {"short-description": desc}}` value; existing callers (all flat str/int) are unaffected
8. Register `ll-adapt-skills-for-codex` in `scripts/pyproject.toml` under `[project.scripts]` and add import + `__all__` + docstring entry in `scripts/little_loops/cli/__init__.py` (three-file registration pattern)
9. Update CLI documentation: `docs/reference/CLI.md` (new section), `commands/help.md` (one-line entry), `.claude/CLAUDE.md` (one-line entry), `skills/configure/areas.md` (increment count + append name), `README.md` (increment CLI tool counts at lines 46 and 164)
10. Update `CONTRIBUTING.md` New Skill Checklist frontmatter template to include `name:` so new skills are Codex-compatible from creation
11. Write `scripts/tests/test_adapt_skills_for_codex.py` (unit tests following `test_generate_skill_descriptions.py` pattern)
12. Add nested-dict test to `scripts/tests/test_frontmatter.py:TestUpdateFrontmatter` covering `{"metadata": {"short-description": "..."}}` round-trip
13. Add `TestFeat1486LlAdaptSkillsWiring` to `scripts/tests/test_create_extension_wiring.py` asserting CLI tool is registered in all five wiring locations
14. Document `description:` ↔ `metadata.short-description:` divergence risk in `docs/claude-code/skills.md` — note that running `ll-generate-skill-descriptions --apply` after adaptation will update `description:` but not `metadata.short-description:`; recommend re-running `ll-adapt-skills-for-codex --apply` to re-sync

## API/Interface

N/A — No public Python API changes. Changes are additive YAML frontmatter
fields in `SKILL.md` files and new `agents/openai.yaml` config files.

## Impact

- **Priority**: P5 — Codex host support is exploratory; Claude Code remains
  primary host; no user is blocked by absence
- **Effort**: Medium — ~30 skill directories each need frontmatter + yaml;
  scriptable bulk edits, but requires per-skill short-description authoring
- **Risk**: Low — additive frontmatter; Claude Code ignores unknown fields;
  no existing skill invocation paths changed
- **Breaking Change**: No

## Labels

codex, skills, host-compat

## Status

**Open** | Created: 2026-05-15 | Priority: P5


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-15_

**Readiness Score**: 98/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- Wide change surface across ~60 skill files: 30 SKILL.md + 30 new `agents/openai.yaml` is a mechanical enumerable sweep, but volume creates execution risk if the adaptation script contains an edge case. The planned integration guard test (`glob real skills/*/SKILL.md` + assert `name:` and `metadata.short-description:`) should be written before marking the issue complete — currently it does not exist.
- New CLI module and tests are co-deliverables: `adapt_skills_for_codex.py` and `test_adapt_skills_for_codex.py` are both planned deliverables; until the tests are written there is no automated validation of the adaptation logic. Write tests before running the script against the real skills dir to avoid hard-to-reverse bulk edits.

## Resolution

**Implemented**: 2026-05-16

All acceptance criteria satisfied:

- **28 `skills/*/SKILL.md` files** updated with `name:` (directory slug) and
  `metadata.short-description:` (first line of description, ≤80 chars) via
  `ll-adapt-skills-for-codex --apply`. 2 skills skipped (no description field).
- **28 `skills/*/agents/openai.yaml`** files created with `interface.display_name`
  and `interface.short_description` per Codex Skills API spec.
- `docs/reference/HOST_COMPATIBILITY.md` — Codex "Skill discovery" cell flipped ✗ → ✓.
- `thoughts/research/codex-command-discovery.md` — gating recommendation updated to
  reflect FEAT-1486 completion.

**New artifacts**:
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — new CLI tool
- `scripts/tests/test_adapt_skills_for_codex.py` — 32 tests (unit + integration guard)
- `scripts/tests/test_adapt_skills_for_codex.py::TestRealSkillsIntegrationGuard` — verifies
  all `skills/*/SKILL.md` have correct `name:` and `metadata.short-description:` fields

**Type annotation fix**: `frontmatter.py:update_frontmatter()` widened from
`dict[str, str | int]` to `dict[str, Any]` to accept nested dicts.

**Documentation**: CLI.md, help.md, CLAUDE.md, areas.md, README.md, CONTRIBUTING.md,
`docs/claude-code/skills.md` all updated.

## Session Log
- `/ll:wire-issue` - 2026-05-16T04:45:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/510b7dce-4e29-440d-9ada-e3da78700741.jsonl`
- `/ll:refine-issue` - 2026-05-16T04:11:21 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e2adda96-b8f4-4c4c-8c1d-f78f1ca1d727.jsonl`
- `/ll:confidence-check` - 2026-05-15T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d6cfbcca-43bc-445d-b90f-328332d02daf.jsonl`
- `/ll:wire-issue` - 2026-05-16T03:54:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/986a2315-fa44-4bc3-83b9-3e72df663cac.jsonl`
- `/ll:refine-issue` - 2026-05-16T03:49:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/69a28b96-46bc-4615-b15f-bafca259f985.jsonl`
- `/ll:format-issue` - 2026-05-16T03:44:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/895ed89a-4cbd-4a2a-a74e-26e9cb8dd7c3.jsonl`
