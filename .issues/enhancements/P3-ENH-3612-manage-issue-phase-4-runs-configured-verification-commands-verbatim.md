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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Conventions in force for the regression test: SKILL.md section tests define a local `_phase_text`-style slicer per file (heading `.index()` to the next heading), live in flat `scripts/tests/test_<skill>_skill.py` files, and group assertions in `Test<Skill><Topic>` classes (evidence: `test_capture_issue_skill.py`, `test_issue_size_review_skill.py`, `test_audit_issue_conflicts_skill.py`). There is no shared helper; the end boundary varies (next `\n### `, a named sibling heading, or an explicit end header). The only fenced-block extraction is `re.findall(r"```bash\n(.*?)```", content, re.DOTALL)` in `test_audit_issue_conflicts_skill.py`.
- The `*_cmd` placeholder convention is split: bare form in `SKILL.md:42-43`, `templates.md`, `commands/iterate-plan.md:125`, `commands/run-tests.md:22` (which states the configured value "already includes the test path"); args-appended form in `SKILL.md:213`, `:356`, `:359`, `:362`, `commands/check-code.md`. This issue moves Phase 4 to the bare form only.
- Net line budget: the Phase 4 edit must land at ≤ +1 line (499 → ≤500). Extra "run verbatim" prose competes with that budget; overflow belongs in `skills/manage-issue/templates.md`, which `test_enh494_skill_companions.py` already lists in `EXPECTED_COMPANIONS`.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — Phase 4 block (:350-:372)
- `.gemini/skills/manage-issue/SKILL.md`, `.kimi-code/skills/manage-issue/SKILL.md`, `.qwen/skills/manage-issue/SKILL.md` — regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. Do not hand-edit them.

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gates; BUG-2408 substring pins (`foreground-blocking`, `scheduled wakeup`); `SPAWN_SITE_INVENTORY` line pin (`skills/manage-issue/SKILL.md`, line 110). The edit is below line 110, so the pin is safe if the line count above it does not change.
- `scripts/tests/test_manage_issue_changelog_gate.py` — verbatim `GATE_SNIPPET`; do not touch it.
- `scripts/tests/test_enh494_skill_companions.py` — 500-line cap. The file is at 499 lines, so the edit must not add net lines. If it does, move content to `templates.md`.
- Add a regression test: the Phase 4 block of `skills/manage-issue/SKILL.md` contains no `{{config.project.<x>_cmd}}` placeholder followed by more text on the same line.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Placeholders are substituted only by `skill_expander._substitute_config` (`scripts/little_loops/skill_expander.py`, called from `expand_skill()` in the `ll-auto`/`ll-parallel`/`ll-sprint` path via `issue_manager.py`). An unset value (`None`) becomes `""`; no line is dropped. Bare placeholders therefore leave a blank line when `type_cmd`/`build_cmd` is unset, where today's text leaves a stray ` src/`. The "skip silently if not configured" behavior is prose the model follows, not something the expander enforces.
- Host mirrors are byte-copies of `SKILL.md` with `{{config.*}}` left unexpanded (`.gemini/skills/manage-issue/SKILL.md` Phase 4 heading sits at line 349, one line above source). `test_host_artifacts_are_not_stale` (`test_wiring_skills_and_commands.py`, parametrized over `GATED_HOSTS` × kinds) fails for gemini/kimi-code/qwen until `ll-adapt --host <h> --apply` is run after any source edit. `test_skill_mirrors_carry_companions` covers companions only, not `SKILL.md` bodies.
- The Phase 4 block (`SKILL.md:354-372`) also carries three lines outside this issue's scope that legitimately take arguments: `build_cmd` (bare), `run_cmd` (`& pid=$!; sleep 3; kill $pid`, shell-level backgrounding), and the commented `custom_verification`. The regression-test rule must not flag the `run_cmd` line.
- `### Headless-Safe Final Test Run` (`SKILL.md:376-400`) uses bare `{{config.project.test_cmd}}` redirected to `.loops/tmp/scratch/test-results.txt`, and never says whether it replaces or follows the Phase 4 test line. Both BUG-2408 pins (`foreground-blocking`, `scheduled wakeup`) live only in that subsection, so they are unaffected by a Phase 4 block edit.
- `SKILL.md` is 499 lines (`wc -l`); `test_enh494_skill_companions.py` fails above 500, so there is exactly one line of headroom. Phase 3 (`SKILL.md:213`) also appends args to `test_cmd` (`[newly_written_test_files] -v`); that is a different, intentional targeted run and is not in this issue's scope.
- No existing test asserts on Phase 4 `tests/ -v` or the `src_dir` lint/type lines, so no test pins the current wrong text.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `skills/init/SKILL.md` — `### 6. Verify (Smoke Check)` says it mirrors manage-issue Phase 4 (skip-if-null per command); its bash block already uses bare `{{config.project.test_cmd}}`/`lint_cmd`. No edit needed; this edit brings Phase 4 into line with it [Agent 1/2 finding]
- `scripts/little_loops/issue_manager.py` — `expand_skill("manage-issue", _manage_args, config)` expands Phase 4 at run time; does not parse it, no change [Agent 2 finding]
- `scripts/.venv/lib/python3.12/site-packages/little_loops/skills/manage-issue/SKILL.md` — untracked installed copy, stale until reinstall; not a source to edit [Agent 1 finding]

### Tests
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_skill_expander.py` — `TestExpandSkillAgainstRealManageIssue.test_manage_issue_expansion_has_no_raw_tokens` expands the real skill and asserts no `{{config.` remains; bare placeholders must still fully expand. Should still pass, re-run it [Agent 1/2/3 finding]
- New test file `scripts/tests/test_manage_issue_phase4_verify.py` (or a new class in an existing manage-issue skill test) — `test_manage_issue_changelog_gate.py` is the only `test_manage_issue*.py` file and this issue says not to touch it. Follow its `SKILL_FILE = REPO_ROOT / "skills" / "manage-issue" / "SKILL.md"` constant and `Test<Topic>` class naming, and slice `## Phase 4: Verify` up to `## Phase 4.5: Integration Review` (`test_audit_issue_conflicts_skill.py::TestAuditIssueConflictsEpicScoping._phase` is the slicer pattern). Scan the slice line by line (as `_run_in_background_satisfied` in `test_wiring_skills_and_commands.py` does) and exempt the `run_cmd` line (`& pid=$!`) [Agent 3 finding]
- `scripts/tests/test_wiring_skills_and_commands.py` — `SPAWN_SITE_INVENTORY` pins `("skills/manage-issue/SKILL.md", 110)` and the BUG-2408 rows pin `foreground-blocking`/`scheduled wakeup` in the Headless-Safe section; both are outside the edited lines, so no change [Agent 1/3 finding]
- `scripts/tests/test_wheel_smoke.py`, `scripts/tests/test_session_log_prose_sweep.py` — presence / whole-file prose checks on manage-issue `SKILL.md`; not Phase 4 specific, no change [Agent 1 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- No doc states that Phase 4 appends `tests/ -v` or `src_dir`; no doc edit needed. `.ll/decisions.yaml` (lines ~4270, ~4630) cites `manage-issue/SKILL.md:355-356` as historical log text, not a gate [Agent 1/2 finding]

## Implementation Steps

1. Edit the Phase 4 code block in `skills/manage-issue/SKILL.md` to use the bare configured commands.
2. Add the regression test.
3. Regenerate the three host mirrors with `ll-adapt --host <host> --apply`.
4. Run `python -m pytest scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_manage_issue_changelog_gate.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Add `scripts/tests/test_manage_issue_phase4_verify.py` — new file for the Phase 4 regression test (do not extend `test_manage_issue_changelog_gate.py`)
- Also run `scripts/tests/test_skill_expander.py` in step 4 — `TestExpandSkillAgainstRealManageIssue` must still pass with bare placeholders

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


## Session Log
- `/ll:wire-issue` - 2026-09-26T06:50:01 - `02fec509-62c9-43bc-b938-817b8efa3dab.jsonl`
- `/ll:refine-issue` - 2026-09-26T06:42:16 - `f4536461-4b4c-49df-b9dd-8cc9f5906a6c.jsonl`
