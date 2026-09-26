---
id: ENH-3612
type: ENH
title: manage-issue Phase 4 runs configured verification commands verbatim
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-26'
captured_at: '2026-09-26T05:02:45Z'
parent: EPIC-3565
relates_to:
- FEAT-3573
---

# ENH-3612: manage-issue Phase 4 runs configured verification commands verbatim

## Summary

`/ll:manage-issue` Phase 4 appends arguments to the configured verification commands.
`{{config.project.test_cmd}} tests/ -v` adds a trailing path and flag, and
`{{config.project.lint_cmd}} {{config.project.src_dir}}` and
`{{config.project.type_cmd}} {{config.project.src_dir}}` add `src_dir`. A configured
command is complete as written. In this repo `lint_cmd` is `ruff check scripts/`, so Phase 4
runs `ruff check scripts/ scripts/`, and `test_cmd tests/ -v` points pytest at a path that
does not exist here. Split out of FEAT-3573.

## Current Behavior

`skills/manage-issue/SKILL.md:356`, `:359`, `:362` append `tests/ -v` and `src_dir` to
`test_cmd`, `lint_cmd` and `type_cmd`. The host mirrors carry the same text
(`.gemini/`, `.kimi-code/`, `.qwen/` `skills/manage-issue/SKILL.md:355`, `:358`, `:361`).

## Expected Behavior

Phase 4 runs each configured command exactly as configured, with no added arguments. The
"Headless-Safe Final Test Run" subsection already does this for `test_cmd` and stays as is.

## Motivation

Commands with added arguments can run the wrong target, run a target twice, or fail on a
path that does not exist. Then the agent "fixes" a failure that the configured command
does not produce.

## Proposed Solution

Replace the three lines in the Phase 4 code block with the bare placeholders
(`{{config.project.test_cmd}}`, `{{config.project.lint_cmd}}`,
`{{config.project.type_cmd}}`). Add one sentence that says to run the commands verbatim.
Do not remove the full-suite run from Phase 4. Phase 4 is the only verification under
`ll-auto`, `ll-parallel` and `ll-sprint` when FEAT-3573's autodev gate is not in the call
path.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — Phase 4 block (:350-:372)
- `.gemini/skills/manage-issue/SKILL.md`, `.kimi-code/skills/manage-issue/SKILL.md`, `.qwen/skills/manage-issue/SKILL.md` — regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. Do not hand-edit them.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gates; BUG-2408 substring pins (`foreground-blocking`, `scheduled wakeup`); `SPAWN_SITE_INVENTORY` line pin (`skills/manage-issue/SKILL.md`, line 110). The edit is below line 110, so the pin is safe if the line count above it does not change.
- `scripts/tests/test_manage_issue_changelog_gate.py` — verbatim `GATE_SNIPPET`; do not touch it.
- `scripts/tests/test_enh494_skill_companions.py` — 500-line cap. The file is at 499 lines, so the edit must not add net lines. If it does, move content to `templates.md`.
- Add a regression test: the Phase 4 block of `skills/manage-issue/SKILL.md` contains no `{{config.project.<x>_cmd}}` placeholder followed by more text on the same line.

## Implementation Steps

1. Edit the Phase 4 code block in `skills/manage-issue/SKILL.md` to use the bare configured commands.
2. Add the regression test.
3. Regenerate the three host mirrors with `ll-adapt --host <host> --apply`.
4. Run `python -m pytest scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_manage_issue_changelog_gate.py`.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low

## Program Design

### Types

- None. This is a skill-text edit; no Python types change.

### Signatures

- `process_issue_inplace(info: IssueInfo, config: BRConfig, logger: Logger, dry_run: bool = False) -> IssueProcessingResult` — `scripts/little_loops/issue_manager.py:720` (keyword-only options elided); the ll-auto driver that invokes `/ll:manage-issue` Phase 2, whose Phase 4 text this issue edits. Unchanged.

### Call Path

`ll-auto --only <ID>` → `process_issue_inplace` (`issue_manager.py:720`) → host `/ll:manage-issue` turn → Phase 4 Verify (`skills/manage-issue/SKILL.md:350`) → configured `test_cmd` / `lint_cmd` / `type_cmd` run verbatim.

### Decision Rules

- A `{{config.project.<x>_cmd}}` placeholder in Phase 4 is never followed by extra arguments on the same line.
- The full-suite run stays in Phase 4.


## Acceptance Criteria

- [ ] Phase 4 runs `test_cmd`, `lint_cmd` and `type_cmd` verbatim, with no added arguments
- [ ] Host mirrors are regenerated and the mirror gates pass
- [ ] `skills/manage-issue/SKILL.md` stays at or under 500 lines
- [ ] A regression test fails if an argument is appended to a configured command in Phase 4

## Scope Boundaries

- Phase 4 keeps its full-suite run. FEAT-3573 decides separately whether autodev skips the
  run when its gate owns the suite.
- `commands/check-code.md:59` and `commands/iterate-plan.md:126` have the same
  `lint_cmd` + `src_dir` pattern. They are out of scope; capture them separately if
  needed.
- No `format_cmd` stage is added to Phase 4.

## Status

**Open** | Created: 2026-09-26 | Priority: P3
