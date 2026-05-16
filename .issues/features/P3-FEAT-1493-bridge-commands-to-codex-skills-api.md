---
id: FEAT-1493
type: FEAT
priority: P3
status: done
captured_at: '2026-05-16T13:04:12Z'
completed_at: '2026-05-16T14:44:12Z'
discovered_date: 2026-05-16
discovered_by: capture-issue
parent: EPIC-1463
blocked_by:
- ENH-1497
relates_to:
- FEAT-1486
- FEAT-1487
labels:
- captured
- codex
- host-compat
- skills-api
decision_needed: false
confidence_score: 90
outcome_confidence: 68
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 18
implementation_order_risk: true
---

# FEAT-1493: Bridge `commands/*.md` to Codex Skills API

## Summary

`ll-adapt-skills-for-codex` only adapts `skills/*/SKILL.md` — the markdown files under `commands/*.md` (where many `/ll:*` slash commands are defined) are not translated to Codex Skills API entries. From the Codex CLI, those commands are unreachable. Extend the adapter (or add a sibling tool) so command markdown is also exposed as `~/.codex/skills/<name>/SKILL.md` entries.

## Current Behavior

`scripts/little_loops/cli/adapt_skills_for_codex.py:158` walks `skills/*/SKILL.md` and emits `agents/openai.yaml` + Codex frontmatter additions for each. Files under `commands/` (e.g. `commands/scan-codebase.md`, `commands/check-code.md`) are not touched. A Codex user with `~/.codex/skills/` populated still cannot invoke `/ll:scan-codebase` style commands — only the 14 skills directory entries are discoverable.

## Expected Behavior

Running the Codex skills adapter exposes both `skills/*/SKILL.md` AND `commands/*.md` to Codex via the Skills API. After adaptation, `/ll:scan-codebase`, `/ll:check-code`, `/ll:commit`, etc. work identically in Codex and Claude Code (modulo skills with `disable-model-invocation: true`, which remain user-only — see ENH-1497).

## Use Case

A developer working in Codex CLI on a little-loops-enabled project runs `ll-adapt-skills-for-codex` once after installing the plugin. From that point on, they can invoke `/ll:check-code`, `/ll:scan-codebase`, `/ll:commit`, `/ll:open-pr`, and the other command-based `/ll:*` entries directly from the Codex CLI in the same way a Claude Code user would — without having to drop back into Claude Code for routine workflow steps. The goal is host parity so a team using Codex isn't restricted to the ~14 skill-directory entries while Claude Code users see the full surface.

## Motivation

This is the **biggest user-facing parity gap** identified by the Codex integration audit. EPIC-1463 originally asserted that the Skills API covers both commands and skills, but inspection shows the adapter only processes the `skills/` directory. Without this bridge, a Codex user is missing roughly half the `/ll:*` surface — including high-value commands like `scan-codebase`, `check-code`, `commit`, and `open-pr`.

## Proposed Solution

Two viable approaches:

1. **Extend `ll-adapt-skills-for-codex`** to also walk `commands/*.md`, treating each as a single-file skill: synthesize a `SKILL.md` wrapper, emit `agents/openai.yaml`, install under `skills/ll-<name>/` in-repo. Namespace prefix avoids collision with skills that share a name.

> **Selected:** Option 1: Extend `ll-adapt-skills-for-codex` — Reuses `_extract_short_desc`, `_make_openai_yaml`, and `_title_case` without modification; adds one sibling `_process_commands()` walker in the same module; no new CLI entrypoint or module.

2. **New tool `ll-adapt-commands-for-codex`** with its own CLI entrypoint, sharing the frontmatter/yaml-emission helpers with the skills adapter. Cleaner separation but more code.

Recommend (1) — most of the logic is already in place; commands and skills have similar enough structure that one tool is simpler than two.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-16.

**Selected**: Option 1: Extend `ll-adapt-skills-for-codex`

**Reasoning**: Three core helpers (`_extract_short_desc`, `_make_openai_yaml`, `_title_case`) reuse directly without modification; the only new code is a sibling `_process_commands()` walker diverging from `_process_skills()` only at the glob pattern and output path derivation. Option 2 would require duplicating 4 private helpers (following the codebase's observed migrate-tool pattern where `_set_fields()` and `_FM_FIELD_RE` appear identically across 2–3 separate files) or extracting them into a shared module — both paths add more code and maintenance surface than extending the existing tool.

**Output directory sub-decision: `skills/ll-{stem}/` in-repo (option a)** — Consistent with the existing tool's in-repo write pattern (`agents/openai.yaml` as a repo sibling), fully testable without home directory side effects, and uses the same Codex discovery path as existing skills. The acceptance criteria referencing `~/.codex/skills/` should be updated to `skills/ll-<command-name>/` during implementation.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option 1: Extend existing tool | 3/3 | 3/3 | 3/3 | 2/3 | 11/12 |
| Option 2: New tool | 1/3 | 1/3 | 2/3 | 1/3 | 5/12 |

**Key evidence**:
- Option 1: `_extract_short_desc` (line 31), `_make_openai_yaml` (line 104), `_title_case` (line 99) in `adapt_skills_for_codex.py` are zero-modification reuse; `main_adapt_skills_for_codex` sequential call pattern at line 202 accepts a second walker with no structural changes
- Option 2: Codebase precedent shows separate tools lead to helper duplication — 4 needed helpers are all module-private (`_` prefix) and not exported; codebase has never extracted CLI-layer helpers into a shared module across tools

## Acceptance Criteria

- [ ] Running `ll-adapt-skills-for-codex` discovers every `commands/*.md` file in addition to `skills/*/SKILL.md`
- [ ] Each discovered command produces a `skills/ll-<command-name>/SKILL.md` entry (in-repo, per resolved decision option a) with valid Codex frontmatter (`name:`, `metadata.short-description:`) and a populated `agents/openai.yaml`
- [ ] The `ll-` namespace prefix is applied so a command and a skill sharing a base name (e.g. `commit`) do not collide on disk
- [ ] Commands with `disable-model-invocation: true` in their frontmatter are skipped, matching the existing skills-adapter contract
- [ ] `scripts/tests/test_adapt_skills_for_codex.py` covers a command fixture: asserts `ll-<name>/SKILL.md` is written and `agents/openai.yaml` validates
- [ ] An end-to-end run against a fresh `~/.codex/skills/` makes at least one bridged command (e.g. `/ll:check-code`) discoverable from Codex
- [ ] `docs/reference/HOST_COMPATIBILITY.md` flips the `[^cmds]` row from ✗ to ✓ and the footnote is updated/removed
- [ ] `.claude/CLAUDE.md` description of `ll-adapt-skills-for-codex` mentions that commands are also bridged

## API/Interface

No new CLI entrypoint. Existing tool behavior is extended:

```text
ll-adapt-skills-for-codex [--dry-run]
  Before: walks skills/*/SKILL.md
  After:  walks skills/*/SKILL.md AND commands/*.md
          installs commands under skills/ll-<command-name>/   (in-repo, per option a)
          skills/<skill-name>/ unchanged (existing in-place adaptation)
```

Synthesized `SKILL.md` wrapper for a command lifts `description:` / trigger keywords from the command's frontmatter when present, and falls back to the H1 heading otherwise. No changes to the existing per-skill output layout.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/adapt_skills_for_codex.py` — extend walker to include `commands/`
- `docs/reference/HOST_COMPATIBILITY.md` — update the `[^cmds]` footnote (commands are now bridged)
- `.claude/CLAUDE.md` — update the `ll-adapt-skills-for-codex` description to mention commands

### Dependent Files (Callers/Importers)
- `scripts/tests/test_adapt_skills_for_codex.py` — extend fixtures and assertions for commands
- `scripts/little_loops/cli/__init__.py:30` — imports and re-exports `main_adapt_skills_for_codex`
- `scripts/pyproject.toml:72` — defines `ll-adapt-skills-for-codex` CLI entrypoint
- `scripts/little_loops/cli/generate_skill_descriptions.py:107` — reference implementation for the `disable-model-invocation` skip guard pattern

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — `TestFeat1486LlAdaptSkillsWiring` class (lines 277–293) asserts `ll-adapt-skills-for-codex` is registered in `help.md`, `CLAUDE.md`, CLI reference, and `configure/areas.md`; may need updates if tool description changes
- `scripts/tests/test_feat1483_doc_wiring.py` — `TestHostCompatibilityCodexSkills` class covers `HOST_COMPATIBILITY.md`; needs a new assertion that the "Slash-command discovery" row is `✓` after FEAT-1493 ships

### Similar Patterns
- `skills/*/SKILL.md` adaptation logic (existing reference implementation in same file)

### Tests

_Wiring pass added by `/ll:wire-issue`:_

**Tests that will break (must update):**
- `scripts/tests/test_adapt_skills_for_codex.py::TestMainAdaptSkillsForCodex::test_missing_skills_dir_returns_one` (line 290) — return code contract may change when `commands/` is absent; update fixture or assertion
- `scripts/tests/test_adapt_skills_for_codex.py::TestMainAdaptSkillsForCodex::test_dry_run_returns_zero_on_success` (line 276) — currently only creates `skills/` in `tmp_path`; will fail if missing `commands/` causes non-zero return; add `_make_command(tmp_path, ...)` call or a bare `commands/` dir
- `scripts/tests/test_adapt_skills_for_codex.py::TestMainAdaptSkillsForCodex::test_apply_flag_writes_files` (line 302) — same issue as above

**New tests to write:**
- `_make_command(tmp_path, name, description, ...)` factory — mirror `_make_skill()` at line 19 but write to `tmp_path / "commands" / f"{name}.md"` (flat, no subdirectory)
- `TestProcessCommands` class — mirror `TestProcessSkills` (lines 171–267): cover dry-run, apply, skip-already-adapted, skip-disable-model-invocation, namespace prefix `ll-`, name-from-stem
- `TestRealCommandsIntegrationGuard` class — mirror `TestRealSkillsIntegrationGuard` (lines 324–413); walk the chosen in-repo output directory (e.g., `skills/ll-<stem>/`) to assert `name:` and `metadata.short-description:` are populated after `--apply`

**Existing tests unaffected (pure unit helpers):**
- `TestExtractShortDesc`, `TestInsertFields`, `TestMakeOpenaiYaml`, `TestTitleCase`, all `TestProcessSkills` tests — call helpers directly, no directory-walking change needed

**Integration test:**
- Round-trip `commands/check-code.md` through the adapter and verify Codex can discover it (acceptance criterion 6)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-adapt-skills-for-codex` section (line ~1447): prose, flag table, and usage examples all describe skills-only behavior; must be updated to describe combined skills + commands processing
- `commands/help.md` — CLI TOOLS block entry for `ll-adapt-skills-for-codex` reads "to all skills"; update to mention commands
- `CONTRIBUTING.md` — `### New Skill Checklist` step 3 tells users to run `ll-adapt-skills-for-codex --apply` after adding a skill; no equivalent step exists in the `## Adding Commands` section; add a parallel instruction there
- `hooks/adapters/codex/README.md` — "Out of scope" paragraph at bottom names FEAT-1486/1487 as covering the skill/command gap; will be stale after FEAT-1493 ships; update to reference FEAT-1493 as completing the commands bridge

## Implementation Steps

1. Extend `adapt_skills_for_codex.py` to discover `commands/*.md` files in addition to `skills/*/SKILL.md`
2. Synthesize a SKILL.md wrapper for each command (lifting description/trigger keywords from frontmatter if present, falling back to the H1 heading)
3. Namespace installed directories as `ll-<command-name>` to avoid collision
4. Update test fixtures and add coverage in `test_adapt_skills_for_codex.py`
5. Update `HOST_COMPATIBILITY.md` to flip the `[^cmds]` row from ✗ to ✓ once shipped
6. Verify end-to-end: after `--apply`, the synthesized `skills/ll-<command-name>/` entries are discoverable by Codex via the existing skills discovery path (same as adapted real skills)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/CLI.md` `### ll-adapt-skills-for-codex` section — revise prose, flag table, and usage examples to describe combined skills + commands processing
8. Update `commands/help.md` — change "to all skills" in the `ll-adapt-skills-for-codex` entry to mention commands are also bridged
9. Update `CONTRIBUTING.md` `## Adding Commands` section — add a parallel step to run `ll-adapt-skills-for-codex --apply` after adding a new command (mirrors "New Skill Checklist" step 3)
10. Update `hooks/adapters/codex/README.md` "Out of scope" paragraph — replace FEAT-1486/1487 reference with FEAT-1493 as the completing implementation
11. Update `TestMainAdaptSkillsForCodex` failing tests (lines 276, 290, 302) — add `_make_command(tmp_path, ...)` call or bare `commands/` dir in fixtures; verify return code contract with missing dirs
12. Add `_make_command()` helper, `TestProcessCommands` class, and `TestRealCommandsIntegrationGuard` class to `test_adapt_skills_for_codex.py`
13. Add assertion to `test_feat1483_doc_wiring.py::TestHostCompatibilityCodexSkills` that "Slash-command discovery" row shows `✓`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Implementation anchor points:**
- Add `_process_commands(commands_dir, apply, quiet)` at `adapt_skills_for_codex.py` alongside the existing `_process_skills()` at line 109
- In `_process_commands()`, use `commands_dir.glob("*.md")` (flat — no subdirectory level); derive name from `cmd_md.stem` not `cmd_md.parent.name`
- Call `_process_commands(plugin_root / "commands", apply, quiet)` from `main_adapt_skills_for_codex()` after `_process_skills()` call
- Reuse `_extract_short_desc()` (line 31) and `_make_openai_yaml()` (line 104) unchanged — they work on command frontmatter as-is
- **Output directory decision (resolved: option a — `skills/ll-{stem}/` in-repo):** The current tool writes in-place — `agents/openai.yaml` is created as a sibling within the repo. For commands (flat files), the sibling pattern breaks; the synthesized `SKILL.md` + `agents/openai.yaml` go to `skills/ll-{stem}/` within the repo, making the entry discoverable alongside real skills via the same workflow. Writing to `~/.codex/skills/ll-{stem}/` (option b) was rejected as inconsistent with the existing in-repo pattern and untestable without home directory side effects. Acceptance criteria referencing `~/.codex/skills/` should be updated to `skills/ll-<command-name>/`.
- `disable-model-invocation` skip: no commands currently carry this flag, but add the guard anyway for consistency; model it after `generate_skill_descriptions.py:107` using the string-lowered membership check (not bare truthiness)

**Synthesized SKILL.md shape (for commands):**

Commands already have `description:` in their frontmatter (verified across `commands/check-code.md`, `commands/scan-codebase.md`, `commands/commit.md`). The synthesized `skills/ll-<stem>/SKILL.md` must include `description:` so `_extract_short_desc` (line 31) can read it via the existing path — copy it verbatim from the source command's frontmatter. After that, `_process_skills`-style logic can populate `name:` and `metadata.short-description:`.

Minimum synthesized frontmatter (one block, written whole — do NOT reuse `_insert_fields`, which is for editing files that already have frontmatter):
```yaml
---
name: ll-<stem>
description: <copied verbatim from commands/<stem>.md frontmatter description:>
metadata:
  short-description: <result of _extract_short_desc on the above>
---
```

Body content is not required for Codex discovery (the API reads frontmatter); a one-line pointer back to `commands/<stem>.md` is sufficient and keeps the synthesized file from drifting out of sync with the source command.

**Test fixture pattern:**
- Model `_make_command(tmp_path, name, description, ...)` after `_make_skill()` at line 19 — write to `tmp_path / "commands" / f"{name}.md"` (flat, no subdirectory)
- `TestRealSkillsIntegrationGuard` at line 324 checks in-tree files; the commands integration guard cannot assert `~/.codex/skills/` (outside repo), so verify whatever in-repo output directory is chosen instead

## Impact

- **Priority**: P3 — Largest single-surface parity gap for Codex users
- **Effort**: Medium — Adapter logic exists; needs extension + tests
- **Risk**: Low — Additive; existing skills adaptation unchanged
- **Breaking Change**: No

## Related Key Documentation

| Document | Why Relevant |
|----------|--------------|
| `docs/reference/HOST_COMPATIBILITY.md` | Codex compatibility matrix; defines the gap |
| `.claude/CLAUDE.md` | Describes `ll-adapt-skills-for-codex` and CLI tools |


## Blocks

- ENH-1495
- FEAT-1496

## Labels

`feat`, `captured`, `codex`, `host-compat`, `skills-api`

## Status

**Done** | Created: 2026-05-16 | Completed: 2026-05-16 | Priority: P3

## Resolution

Extended `scripts/little_loops/cli/adapt_skills_for_codex.py` with a sibling
`_process_commands()` walker plus a `_synthesized_skill_md()` builder.
`ll-adapt-skills-for-codex --apply` now walks `commands/*.md` in addition to
`skills/*/SKILL.md` and synthesizes a `skills/ll-<stem>/SKILL.md` +
`agents/openai.yaml` for each, namespaced with `ll-` to avoid collisions.

Key details:
- Description copied verbatim from the source command's frontmatter; multi-line
  descriptions are emitted as YAML block scalars (`description: |`) so the
  synthesized frontmatter parses cleanly with `yaml.safe_load`.
- `disable-model-invocation: true` commands are skipped (string-lowered check,
  matches `generate_skill_descriptions.py:107`).
- Helpers `_extract_short_desc`, `_make_openai_yaml`, `_title_case` reused
  unchanged from the skills path.
- Result on this repo: 28 commands bridged, 0 errors, no impact on the existing
  in-place skills adaptation.

Coverage added:
- `TestSynthesizedSkillMd` — name prefix, verbatim description, ≤80-char
  short-description truncation, body pointer to the source command file.
- `TestProcessCommands` — dry-run, apply, namespace collision avoidance,
  already-adapted skip, `disable-model-invocation` skip, missing-`commands/`
  is a no-op, multi-command run.
- `TestRealCommandsIntegrationGuard` — every active `commands/*.md` has a
  bridged `skills/ll-<stem>/SKILL.md`, every bridged file's frontmatter
  parses with `name: ll-<stem>` + `metadata.short-description:`, and every
  bridged dir has `agents/openai.yaml`.

Documentation updates:
- `docs/reference/HOST_COMPATIBILITY.md` — Slash-command discovery row flipped
  from `✗` to `✓`, footnote updated to credit FEAT-1493.
- `.claude/CLAUDE.md` — `ll-adapt-skills-for-codex` entry now mentions the
  commands bridge.
- `docs/reference/CLI.md` — section rewritten to describe both the skills
  in-place adaptation and the synthesized commands bridge.
- `commands/help.md` — CLI tools list entry updated.
- `CONTRIBUTING.md` — added "After Creating a New Command" subsection telling
  contributors to run `ll-adapt-skills-for-codex --apply` (mirrors the existing
  New Skill Checklist guidance).
- `hooks/adapters/codex/README.md` — "Out of scope" paragraph now lists
  FEAT-1493 alongside FEAT-1486/1487 as completing the discovery surface.

Wiring guard:
- `test_feat1483_doc_wiring.py::TestHostCompatibilityCodexSkills` now asserts
  the Slash-command Codex cell contains `✓` (and does not contain `✗`), plus a
  `FEAT-1493` tracking reference.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-16 (updated — decision resolved)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 68/100 → MODERATE

### Outcome Risk Factors
- **Broad touchpoint count (10 sites)** — while most non-code sites are mechanical doc edits (CLAUDE.md, CLI.md, help.md, HOST_COMPATIBILITY.md, codex README, CONTRIBUTING.md), the volume increases chance of a missed update; `test_create_extension_wiring.py::TestFeat1486LlAdaptSkillsWiring` (lines 277–293) serves as the completeness guard — run it after each doc touchpoint.
- **Tests are co-deliverables** — `TestProcessCommands` and `TestRealCommandsIntegrationGuard` must be written alongside `_process_commands()`; implement tests first so they drive the namespace-prefix assertions and output-directory structure before the function is finalized.

## Session Log
- `/ll:manage-issue` - 2026-05-16T14:44:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0010190c-509e-453e-bb85-c00575d1e590.jsonl`
- `/ll:ready-issue` - 2026-05-16T14:34:59 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5552b020-a161-462d-b52b-bde7de3f95a9.jsonl`
- `/ll:refine-issue` - 2026-05-16T14:27:24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/294b6cd1-8fe5-4d83-b159-1a7c4340f30e.jsonl`
- `/ll:confidence-check` - 2026-05-16T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c7559348-bfd0-4c60-b23c-022b113b6169.jsonl`
- `/ll:decide-issue` - 2026-05-16T14:21:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c1f75157-7a21-4776-94d5-de65373150bd.jsonl`
- `/ll:confidence-check` - 2026-05-16T15:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/eb8fc19d-3730-4a14-bee0-2c1b48a9c669.jsonl`
- `/ll:wire-issue` - 2026-05-16T14:11:48 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6cc5d7f3-0b4f-40a1-9684-95479666b681.jsonl`
- `/ll:refine-issue` - 2026-05-16T14:05:50 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6722ff2e-ab5e-415c-92ca-52f0e679ac77.jsonl`
- `/ll:format-issue` - 2026-05-16T13:18:16 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d491efd-1e9f-48e7-91e7-1d0390a23fbc.jsonl`
- `/ll:capture-issue` - 2026-05-16T13:04:12Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0f112cdc-ed18-410c-85e1-0d7cc45aa863.jsonl`
