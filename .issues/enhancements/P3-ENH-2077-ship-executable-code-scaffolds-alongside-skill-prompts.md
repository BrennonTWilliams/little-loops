---
id: ENH-2077
title: Ship executable code scaffolds alongside skill prompts
type: ENH
priority: P3
status: cancelled
captured_at: '2026-06-10T18:12:09Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
relates_to:
- EPIC-2087
- FEAT-958
confidence_score: 93
outcome_confidence: 84
score_complexity: 17
score_test_coverage: 20
score_ambiguity: 22
score_change_surface: 25
decision_needed: false
---

# ENH-2077: Ship executable code scaffolds alongside skill prompts

## Summary

Skills like `create-loop`, `manage-issue`, and `create-eval-from-issues` currently provide strategy guidance in prose but ship no runnable code scaffolds. Adding scaffold artifacts alongside each skill's prompt — and injecting them into context before the generation step — bridges the gap from conceptual guidance to executable reference and is expected to lift mid-tier model performance on complex automation tasks.

## Current Behavior

Skills `create-loop`, `manage-issue`, and `create-eval-from-issues` provide strategy guidance exclusively through prose instructions. There are no runnable starter scaffolds, template YAMLs, or example code snippets shipped alongside these skill prompts. Agents must infer correct structure from descriptions alone, increasing error rates and retry counts on complex generation tasks.

## Expected Behavior

Each identified high-complexity skill has a `scaffolds/` subdirectory containing a runnable template (YAML, Python module, or annotated snippet). Skill invocation automatically injects scaffold content into context before the generation step. Retry counts for ll-loop runs on these skills are tracked before and after scaffold introduction.

## Motivation

Skills like create-loop, manage-issue, and eval harness templates currently provide strategy guidance in prose. Conceptual descriptions tell agents what to do; only runnable code scaffolds bridge the gap to execution. Providing a working reference library of primitives alongside prompts dramatically lifts mid-tier model performance on complex automation tasks.

## Proposed Solution

Identify the highest-complexity skills (create-loop, manage-issue, create-eval-from-issues) and accompany each with a starter scaffold: a template YAML, a Python helper module, or an example-driven code snippet embedded in the skill preamble rather than prose instructions. Add a `scaffolds/` directory under each skill folder to hold these artifacts. Update skill invocation to inject the scaffold content into context before the generation step. Track whether including the scaffold reduces retry counts in ll-loop runs.

## Implementation Steps

1. **Design decision** (resolved): Use **both** invocation paths — subprocess path via `skill_expander.py:expand_skill()` for `manage-issue`; **SKILL.md embedding** (inline in the skill preamble) for `create-loop` and `create-eval-from-issues`. Decided 2026-06-13.
2. **Extend `skill_expander.py:expand_skill()`** (subprocess path, `scripts/little_loops/skill_expander.py:96`): After resolving `content_path` and reading SKILL.md body, check for a `scaffolds/` directory in `content_path.parent`; if present, read all files and prepend to `body` as a fenced block. Follow the existing `_substitute_relative_refs()` pattern at line 69.
3. **Author scaffold for `manage-issue`** (`skills/manage-issue/scaffolds/`): A runnable code snippet showing the implementation plan structure — the subprocess path is relevant here since `issue_manager.py:842` calls `expand_skill("manage-issue", ...)`.
4. **Author scaffold for `create-loop`** (`skills/create-loop/scaffolds/`): A minimal working loop YAML showing state machine structure (distinct from `templates.md` which covers template selection flow). Content to inject depends on Step 1 decision.
5. **Author scaffold for `create-eval-from-issues`** (`skills/create-eval-from-issues/scaffolds/`): An eval harness template YAML (this skill has no templates.md — scaffold would be the first runnable artifact).
6. **Add tests** in `scripts/tests/test_skill_expander.py`: Add `TestExpandSkillWithScaffolds` class testing scaffold directory discovered and content prepended, following pattern in `TestExpandSkill` (lines 169–235).
7. **Track retry delta**: Instrument `ll-loop run` or capture run metadata before/after scaffold introduction to measure retry count delta. Document baseline and post-scaffold counts.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `docs/reference/API.md:7374` — extend `expand_skill` docstring to mention scaffold injection: add "prepends any files found in `scaffolds/` directory alongside the skill as a fenced block" to the function description
9. Update `docs/ARCHITECTURE.md:1229` — revise skill pre-expansion description to include scaffold prepend as a pipeline step after config substitution
10. Update `CONTRIBUTING.md:565` — the "not nested subdirectories" rule contradicts `scaffolds/`; update to document `scaffolds/` as an approved exception for auto-injected content artifacts (distinct from flat companion files)
11. After authoring `skills/manage-issue/scaffolds/` content: add a positive assertion to `TestExpandSkillAgainstRealManageIssue.test_manage_issue_expansion_has_no_raw_tokens` confirming scaffold content appears in the real-file expansion result

## Acceptance Criteria

- [ ] `scaffolds/` directory exists under at least create-loop, manage-issue, create-eval-from-issues skill folders
- [ ] Each scaffold contains a runnable template (YAML, Python module, or annotated snippet)
- [ ] Skill invocation injects scaffold content before the generation step
- [ ] Retry count tracking is documented or instrumented

## Success Metrics

- Retry count delta: measurable reduction in ll-loop retry counts for targeted skills after scaffold injection
- Scaffold coverage: `scaffolds/` directory present under all 3 identified skills
- Injection verification: scaffold content confirmed in skill context preamble via test or trace

## Scope Boundaries

- **In scope**: `scaffolds/` directories under `create-loop`, `manage-issue`, and `create-eval-from-issues`; context injection for these three skills; retry count tracking
- **Out of scope**: Scaffolds for all other skills; automated scaffold generation; changes to FSM loop YAML schema

## API/Interface

N/A - No public API changes. Scaffold injection is internal to skill invocation context.

## Integration Map

### Files to Modify
- `scripts/little_loops/skill_expander.py` — add scaffold injection logic to `expand_skill()`: after reading SKILL.md, read `scaffolds/` directory (if it exists) and prepend content to the expanded prompt. Key function: `expand_skill(name, args, config)` at line 96.
- `skills/create-loop/` — add `scaffolds/` directory with template YAML scaffold (supplement existing `templates.md`, `loop-types.md`, `reference.md`)
- `skills/manage-issue/` — add `scaffolds/` directory with example code snippet (supplement existing `templates.md`)
- `skills/create-eval-from-issues/` — add `scaffolds/` directory with eval harness template (this skill has no templates.md; only `agents/` and `SKILL.md`)

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_manager.py:37` — imports `expand_skill`; calls it at lines 586, 640, 802, 842 for `manage-issue`, `ready-issue`, and `decide-issue` skills. This is the **only** caller of `expand_skill()` in production code. Entry point for **ll-auto only**.
- `scripts/little_loops/parallel/worker_pool.py` — `_process_issue()` does NOT call `expand_skill()`: uses `ParallelConfig.get_ready_command()`/`get_manage_command()` from `parallel/types.py` which return raw slash commands. **ll-parallel is not in the subprocess expansion path.**
- `scripts/little_loops/cli/action.py` — `cmd_invoke()` passes raw slash commands; does NOT call `expand_skill()`.
- `scripts/little_loops/cli/harness.py` — `cmd_skill()` passes raw slash commands; does NOT call `expand_skill()`.
- `scripts/little_loops/subprocess_utils.py` — `run_claude_command()` receives the expanded prompt and spawns `claude --dangerously-skip-permissions --verbose --output-format stream-json -p <prompt>`.

### Subprocess vs. Direct Path (Resolved: both, 2026-06-13)
**Critical finding**: Only `ll-auto` (via `issue_manager.py:process_issue_inplace()`) uses `expand_skill()`. `ll-parallel`, `ll-sprint`, `ll-action`, and `ll-harness` all pass raw slash commands — they use the Skill tool (direct) path inside the subprocess.

Of the three target skills: only `manage-issue` is in the `expand_skill()` path. `create-loop` and `create-eval-from-issues` are never pre-expanded — they are invoked via Skill tool in all contexts.

**Decision**: use both paths, each by the mechanism appropriate to the skill:
- `manage-issue` subprocess path: add scaffold prepend in `skill_expander.py:expand_skill()` (after `_substitute_arguments()`, before returning)
- `create-loop` and `create-eval-from-issues` Skill tool path: **embed scaffold content directly in SKILL.md** (inline in the skill preamble, not a "Read this file now" pointer — that would be indistinguishable from the existing `templates.md` on-demand pattern)

### scaffolds/ vs templates.md Differentiation
`create-loop` and `manage-issue` already ship `templates.md` files referenced via `[text](templates.md)` links in their SKILL.md. In both paths, `_substitute_relative_refs()` (`skill_expander.py:69`) resolves these to absolute paths, but the content is NOT inlined — the LLM must proactively Read the file. Scaffolds should be distinct from templates.md by being **auto-injected** (inlined in context) rather than "available to read on demand."

### Similar Patterns
- `skills/create-loop/templates.md` — template selection flow and YAML definitions (AskUserQuestion pattern, fix-until-clean, harness-skill templates)
- `skills/manage-issue/templates.md:1` — agent prompt templates and research findings structure
- `scripts/little_loops/skill_expander.py:69` — `_substitute_relative_refs()` pattern for resolving relative file references; scaffold injection would extend this approach to inline file content rather than just resolve paths
- `scripts/little_loops/cli/create_extension.py:35` — `_write_scaffold(target, files)` function: writes multi-file scaffolds to disk with directory creation; reuse this pattern for authoring scaffold files under `skills/<name>/scaffolds/`
- `.issues/features/P2-FEAT-958-skill-pre-expansion-to-eliminate-toolsearch-dependency-in-ll-auto.md` — completed predecessor that built the `expand_skill()` infrastructure this issue extends

### Tests
- `scripts/tests/test_skill_expander.py` — existing tests for `expand_skill`, `_substitute_config`, `_substitute_relative_refs` (classes `TestExpandSkill`, `TestExpandSkillAgainstRealManageIssue`). Add tests here for scaffold injection: `TestExpandSkillWithScaffolds` covering scaffold directory exists/missing, single/multiple scaffold files, prepend ordering.
- `scripts/tests/test_skill_expander.py:238` — `TestExpandSkillAgainstRealManageIssue` pattern: integration test against the real skill file; extend for scaffold injection smoke test.

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_skill_expander.py:241` — `TestExpandSkillAgainstRealManageIssue.test_manage_issue_expansion_has_no_raw_tokens`: **UPDATE** — once `skills/manage-issue/scaffolds/` is added, this integration test expands real skill+scaffold content. Existing `not in` assertions (for `{{config.`, `$ARGUMENTS`, `(templates.md)`) remain valid as long as scaffold files don't contain those literal strings. Add a positive assertion that scaffold content appears in the result after scaffold is authored. [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — parametrized tests that assert specific strings exist in `skills/create-loop/SKILL.md`, `skills/create-loop/templates.md`, and `skills/manage-issue/SKILL.md`. Safe — these check for PRESENCE of specific strings; adding scaffold content (whether embedded in SKILL.md or in `scaffolds/`) does not remove existing strings. No action required, but exercise this file after modifying SKILL.md files to catch regressions. [Agent 1 finding]

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — skill authoring guide; may need a new section on scaffold authoring conventions
- `skills/create-loop/SKILL.md:390` — "For pre-built loop templates, see templates.md"; would gain scaffold reference

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:7374` — `expand_skill` docstring currently reads: "Reads the Markdown source for name, strips frontmatter, substitutes `{{config.xxx}}` placeholders, converts relative `(file.md)` link targets to absolute paths, and replaces the `$ARGUMENTS` token with the joined args." This description becomes incomplete after scaffold injection — update to add: "…and prepends any files found in `scaffolds/` directory alongside the skill as a fenced block." [Agent 2 finding]
- `docs/ARCHITECTURE.md:1229` — describes skill pre-expansion as "the full skill/command Markdown is read, config placeholders substituted, and the resulting self-contained prompt string is passed directly." Needs updating to mention scaffold prepend as an additional step in the expansion pipeline. [Agent 2 finding]
- `CONTRIBUTING.md:565` — **convention conflict**: the `### Skill File Size: 500-Line Limit & Companion Files` section explicitly states "Use descriptive flat filenames — `templates.md`, `reference.md`, `rubric.md`, `areas.md` — **not nested subdirectories**." The `scaffolds/` directory introduced by this issue is the first content-bearing nested subdirectory in a skill (note: `agents/openai.yaml` already exists under each target skill as a Codex-adaptation artifact, so two patterns coexist). Update CONTRIBUTING.md to document `scaffolds/` as an approved exception: nested subdirectories are permitted for auto-injected scaffold artifacts distinct from human-authored companion files. [Agent 2 finding]

### Configuration
- N/A — no config changes; scaffold directories are discovered by convention (`skills/{name}/scaffolds/`)

## Impact

- **Priority**: P3 - Developer experience improvement; not blocking active work
- **Effort**: Medium - authoring 3 scaffolds and updating invocation logic; no infrastructure changes
- **Risk**: Low - additive only; does not modify existing skill prompts, only prepends scaffold context
- **Breaking Change**: No

## Labels

`enhancement`, `skill-enhancement`, `developer-experience`

## Status

**Cancelled** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-11_

**Readiness Score**: 65/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 52/100 → LOW

### Gaps to Address
- **`skill_expander.py` missing from Integration Map** — this is the subprocess injection path; add it to "Files to Modify" and spec how `expand_skill()` reads `scaffolds/` content and prepends it to the expanded prompt
- **Resolve dual invocation path design (`decision_needed: true` still active)** — specify whether scaffold injection applies to the Skill tool direct path, the subprocess path, or both, and by what mechanism for each
- **Clarify scaffolds vs templates.md** — `create-loop/templates.md` and `manage-issue/templates.md` already ship runnable YAML templates; without explaining the differentiation, scaffolds/ risks creating redundant artifacts alongside the existing templates
- **Fill TBD sections** — enumerate callers via `grep -r "expand_skill" scripts/`, define a test strategy for injection verification, identify relevant skill authoring docs

### Outcome Risk Factors
- **Unresolved design decision: dual invocation paths** — `Skill tool` direct invocation vs `skill_expander.py` subprocess path are not distinguished; resolve before implementing which path(s) receive scaffold injection and by what mechanism
- **Existing `templates.md` overlap** — `create-loop/templates.md` and `manage-issue/templates.md` already ship runnable YAML templates into skill context; no differentiation from proposed scaffolds risks redundant or conflicting artifacts
- **skill_expander.py blast radius** — modification to inject scaffolds touches `ll-auto`, `ll-parallel`, `ll-sprint`, `ll-action` via issue_manager.py; Integration Map does not enumerate these callers
- **TBD test path** — acceptance criterion "Skill invocation injects scaffold content before the generation step" has no designed test strategy; integration verification is listed as TBD

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-13_ — **NO-GO (REFINE)**

**Deciding Factor**: The issue needs to be re-scoped against what scaffolds actually exist versus what is missing, and the acceptance criteria must be reformulated around a measurable signal before implementation can be justified — the current framing conflates a content-delivery problem with a content-existence problem.

### Key Arguments For
- The `expand_skill()` pipeline at `skill_expander.py:96` is designed for additive `str → str` transforms; scaffold injection slots in as one step with no architectural friction and an existing `try/except` fallback at line 126–127
- `create-eval-from-issues` lacks a dedicated `templates.md` and scaffold directory, so a partial content-delivery gap exists even if inline YAML exists in SKILL.md itself

### Key Arguments Against
- The issue's foundational claim — that target skills have no runnable starter scaffolds — is factually incorrect for `create-eval-from-issues`: full FSM YAML (Variant A and B) is already embedded in `SKILL.md` lines 241–355, making that skill's scaffold redundant
- The primary acceptance criterion ("measure retry count delta") cannot be verified: no CLI command, export format, or aggregation tool captures per-skill retry counts across runs; success is unmeasurable without out-of-scope infrastructure work

### Rationale
The against argument presents stronger codebase-grounded evidence: `create-eval-from-issues/SKILL.md` already embeds complete Variant A and B YAML templates inline (lines 241–355), directly undermining the issue's core premise that no runnable artifacts exist. The dual-path injection mechanism has no programmatic verification path for the Skill tool path on two of the three target skills, and the primary success metric (retry count delta) has zero measurement infrastructure. While the implementation touchpoints in `skill_expander.py` are genuinely surgical, the value proposition rests on a partially false content-gap claim and an unmeasurable outcome.

## Session Log
- `/ll:confidence-check` - 2026-06-13T00:00:00Z - `4eb981d4-8f19-4dc6-94ee-c96367c0e356.jsonl`
- `/ll:go-no-go` - 2026-06-13T00:00:00Z - `51541558-3fd6-4606-8c12-a24b92b6f47f.jsonl`
- `/ll:wire-issue` - 2026-06-13T20:19:23 - `f54e41c4-8dc0-4793-a95a-bb1de890b523.jsonl`
- `/ll:decide-issue` - 2026-06-13T19:53:33 - `0689c23b-e672-439e-9ad3-4d3ec529ef82.jsonl`
- `/ll:refine-issue` - 2026-06-13T19:50:49 - `19d5bdfe-2e2a-4a82-b53c-e33bd0f34b47.jsonl`
- `/ll:decide-issue` - 2026-06-11T22:41:42 - `983ceb53-ffc0-4d38-84e0-e816279d5414.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `c8c21a0c-df7a-456a-96eb-def0511bffc3.jsonl`
- `/ll:decide-issue` - 2026-06-11T20:44:55 - `c11253e7-4c76-4648-93ac-00ac2e0101cb.jsonl`
- `/ll:format-issue` - 2026-06-11T20:10:58 - `e6b03fdf-7ce2-4da2-bdd7-2966c8e338a9.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `51577893-49ed-4585-85fe-085f192947be.jsonl`
