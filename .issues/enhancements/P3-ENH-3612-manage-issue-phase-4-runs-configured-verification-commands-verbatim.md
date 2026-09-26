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
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
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

The shipped Python `type_cmd` default is a bare `mypy`, which fails when run with no
target. The `src_dir` suffix hides this today. This issue also changes that default to a
complete command, so that running the commands verbatim does not break type checking for
default Python consumers.

## Current Behavior

- `skills/manage-issue/SKILL.md:356`, `:359`, `:362` append `tests/ -v` and `src_dir` to
  `test_cmd`, `lint_cmd` and `type_cmd`. The host mirrors carry the same text
  (`.gemini/`, `.kimi-code/`, `.qwen/` `skills/manage-issue/SKILL.md:355`, `:358`, `:361`).
- Phase 4 runs the full test suite twice: once from the code-block line (`:356`) and
  again from `### Headless-Safe Final Test Run` (`:387`, scratch-redirect form). The
  subsection does not say whether it replaces or follows the code-block line.
- The default `type_cmd` is bare `mypy` at five sites:
  `scripts/little_loops/config-schema.json:43` (`default`),
  `scripts/little_loops/config/core.py:219` (dataclass default) and `:243`
  (`from_dict` fallback), `scripts/little_loops/templates/python-generic.json:27`, and
  `scripts/little_loops/init/introspect.py:290` (`_python_command`, returned whenever a
  `[tool.mypy]` table exists). Verified 2026-09-26: bare `mypy` with a
  `[tool.mypy]\nstrict = true` config exits 2 with
  `mypy: error: Missing target module, package, files, or command.`

## Expected Behavior

- Phase 4 runs each configured command exactly as configured, with no added arguments.
- The Phase 4 test run happens once, in the scratch-redirect form of the
  "Headless-Safe Final Test Run" subsection (which already runs `test_cmd` bare and
  stays as is).
- Every default or introspected `type_cmd` runs successfully when invoked bare.

## Motivation

Commands with added arguments can run the wrong target, run a target twice, or fail on a
path that does not exist. Then the agent "fixes" a failure that the configured command
does not produce. Removing the arguments without fixing the `mypy` default would cause
the same failure mode for every default Python project.

## Proposed Solution

### 1. Phase 4 block (`skills/manage-issue/SKILL.md`, net 0 lines)

- Replace the three command lines with the bare placeholders
  (`{{config.project.test_cmd}}`, `{{config.project.lint_cmd}}`,
  `{{config.project.type_cmd}}`).
- Rewrite the existing intro line in place (`:352`, "Run each verification command if
  configured (non-null)…") so it also says to run each command exactly as configured,
  with no paths or flags appended. Do not add a new line.
- Rewrite the existing test comment line in place (`:355`, "# Run tests if test_cmd is
  configured (non-null)") so it points to the scratch-redirect form in
  `### Headless-Safe Final Test Run` and says to run the suite once. Do not add a new
  line.
- Do not remove the full-suite run from Phase 4. Phase 4 is the only verification under
  `ll-auto`, `ll-parallel` and `ll-sprint` when FEAT-3573's autodev gate is not in the
  call path.

### 2. `type_cmd` defaults

- Change the bare `mypy` default to `mypy .` at `config-schema.json:43`,
  `config/core.py:219` and `:243`, and `templates/python-generic.json:27`.
  `mypy .` matches the existing `ruff check .` / `ruff format .` defaults.
- In `init/introspect.py:_python_command` (`:288-293`): if `[tool.mypy]` sets `files`,
  return `mypy`, because mypy then takes its targets from config and a CLI target would
  override that. Otherwise return `mypy .`. Keep `pyright` bare; it checks the cwd with
  no arguments.
- Update `docs/reference/API.md:415` (`type_cmd: str | None = "mypy"`) to match.
- Migration: existing consumer configs that set `"type_cmd": "mypy"` explicitly are not
  rewritten. Add a CHANGELOG note in the release section (not `[Unreleased]`) saying that
  Phase 4 now runs `type_cmd` verbatim, so a bare `mypy` needs a target (`mypy .`) or a
  `[tool.mypy] files = [...]` setting.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Conventions in force for the regression test: SKILL.md section tests define a local `_phase_text`-style slicer per file (heading `.index()` to the next heading), live in flat `scripts/tests/test_<skill>_skill.py` files, and group assertions in `Test<Skill><Topic>` classes (evidence: `test_capture_issue_skill.py`, `test_issue_size_review_skill.py`, `test_audit_issue_conflicts_skill.py`). There is no shared helper; the end boundary varies (next `\n### `, a named sibling heading, or an explicit end header). The only fenced-block extraction is `re.findall(r"```bash\n(.*?)```", content, re.DOTALL)` in `test_audit_issue_conflicts_skill.py`.
- The `*_cmd` placeholder convention is split: bare form in `SKILL.md:42-43`, `templates.md`, `commands/iterate-plan.md:125`, `commands/run-tests.md:22` (which states the configured value "already includes the test path"); args-appended form in `SKILL.md:213`, `:356`, `:359`, `:362`, `commands/check-code.md`. This issue moves Phase 4 to the bare form only.
- Net line budget: the Phase 4 edit must land at ≤ +1 line (499 → ≤500). Extra "run verbatim" prose competes with that budget; overflow belongs in `skills/manage-issue/templates.md`, which `test_enh494_skill_companions.py` already lists in `EXPECTED_COMPANIONS`.
- Placeholders are substituted only by `skill_expander._substitute_config` (`scripts/little_loops/skill_expander.py`, called from `expand_skill()` in the `ll-auto`/`ll-parallel`/`ll-sprint` path via `issue_manager.py`). An unset value (`None`) becomes `""`; no line is dropped. Bare placeholders therefore leave a blank line when `type_cmd`/`build_cmd` is unset, where today's text leaves a stray ` src/`. The "skip silently if not configured" behavior is prose the model follows, not something the expander enforces.
- Host mirrors are byte-copies of `SKILL.md` with `{{config.*}}` left unexpanded (`.gemini/skills/manage-issue/SKILL.md` Phase 4 heading sits at line 349, one line above source). `test_host_artifacts_are_not_stale` (`test_wiring_skills_and_commands.py`, parametrized over `GATED_HOSTS` × kinds) fails for gemini/kimi-code/qwen until `ll-adapt --host <h> --apply` is run after any source edit. `test_skill_mirrors_carry_companions` covers companions only, not `SKILL.md` bodies.
- The Phase 4 block (`SKILL.md:354-372`) also carries three lines outside this issue's scope that legitimately take arguments: `build_cmd` (bare), `run_cmd` (`& pid=$!; sleep 3; kill $pid`, shell-level backgrounding), and the commented `custom_verification`. The regression-test rule must not flag the `run_cmd` line.
- `### Headless-Safe Final Test Run` (`SKILL.md:376-400`) uses bare `{{config.project.test_cmd}}` redirected to `.loops/tmp/scratch/test-results.txt`, and never says whether it replaces or follows the Phase 4 test line. Both BUG-2408 pins (`foreground-blocking`, `scheduled wakeup`) live only in that subsection, so they are unaffected by a Phase 4 block edit.
- `SKILL.md` is 499 lines (`wc -l`); `test_enh494_skill_companions.py` fails above 500, so there is exactly one line of headroom. Phase 3 (`SKILL.md:213`) also appends args to `test_cmd` (`[newly_written_test_files] -v`); that is a different, intentional targeted run and is not in this issue's scope.
- No existing test asserts on Phase 4 `tests/ -v` or the `src_dir` lint/type lines, so no test pins the current wrong text.
- Review 2026-09-26: `lint_cmd`'s default `ruff check .` is already complete. Today Phase 4 runs `ruff check . src/`, which lints `src/` twice. `pyright` and `npx tsc --noEmit` (the TS introspect value, `introspect.py:353`) also work bare. Only the `mypy` default depends on the appended `src_dir`.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — Phase 4 block (:350-:372), in-place rewrites only (net 0 lines)
- `.gemini/skills/manage-issue/SKILL.md`, `.kimi-code/skills/manage-issue/SKILL.md`, `.qwen/skills/manage-issue/SKILL.md` — regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. Do not hand-edit them.
- `scripts/little_loops/config-schema.json:43` — `type_cmd` default `mypy` → `mypy .`
- `scripts/little_loops/config/core.py:219`, `:243` — `ProjectConfig.type_cmd` default and `from_dict` fallback → `mypy .`
- `scripts/little_loops/templates/python-generic.json:27` — `type_cmd` → `mypy .`
- `scripts/little_loops/init/introspect.py:288-293` — `_python_command` `type_cmd` branch: `mypy` if `[tool.mypy]` has `files`, else `mypy .`
- `docs/reference/API.md:415` — `ProjectConfig` default listing
- `CHANGELOG.md` — migration note in the release section

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gates; BUG-2408 substring pins (`foreground-blocking`, `scheduled wakeup`); `SPAWN_SITE_INVENTORY` line pin (`skills/manage-issue/SKILL.md`, line 110). The edit is below line 110, so the pin is safe if the line count above it does not change.
- `scripts/tests/test_manage_issue_changelog_gate.py` — verbatim `GATE_SNIPPET`; do not touch it.
- `scripts/tests/test_enh494_skill_companions.py` — 500-line cap. The file is at 499 lines, and the Phase 4 edit is net 0.
- Tests that pin the bare `mypy` default; update them to `mypy .`:
  - `scripts/tests/test_config.py:145`
  - `scripts/tests/test_init_proposal.py:74`
  - `scripts/tests/test_init_introspect.py:75` (`test_type_cmd_declared_via_mypy_table`), `:84` (`test_type_cmd_defaults_when_no_mypy_table`), `:104` (generic-template regression)
  - `scripts/tests/integration/test_init_e2e.py:256`, `:269` (provenance summary string `type_cmd: mypy  (declared: [tool.mypy] present)`)
  - Check `scripts/tests/test_init_core.py:145` and `scripts/tests/test_init_tui.py:94`. These look like input fixtures, not assertions on the default; update them only if they fail.
- New: `scripts/tests/test_init_introspect.py` — `[tool.mypy]` with `files = ["src"]` → `type_cmd == "mypy"`; `[tool.mypy]` without `files` → `type_cmd == "mypy ."`.
- New (to create): `test_manage_issue_skill.py` under the tests dir, class `TestManageIssuePhase4Verbatim`:
  - Slice from `## Phase 4: Verify` to `### Headless-Safe Final Test Run`.
  - For every line that contains `{{config.project.test_cmd}}`, `{{config.project.lint_cmd}}` or `{{config.project.type_cmd}}`, assert that `line.strip()` equals the bare placeholder. Do not check other `*_cmd` placeholders, so the `run_cmd` line is not flagged.
  - Assert that the slice tells the model to run commands as configured (a short, stable substring such as `exactly as configured`).

## Implementation Steps

1. Write the new tests (Red): `test_manage_issue_skill.py`, the two new introspect cases, and the updated default assertions.
2. Edit the Phase 4 block in `skills/manage-issue/SKILL.md` (bare placeholders, in-place intro and test-comment rewrites; `wc -l` stays 499).
3. Change the `type_cmd` default at the schema, `config/core.py` (both sites), the `python-generic` template and `_python_command`. Update `docs/reference/API.md:415`.
4. Regenerate the three host mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`.
5. Add the CHANGELOG migration note.
6. Run `python -m pytest scripts/tests/ -k manage_issue_skill` (the new file), then `python -m pytest scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_manage_issue_changelog_gate.py scripts/tests/test_config.py scripts/tests/test_init_introspect.py scripts/tests/test_init_proposal.py scripts/tests/test_init_core.py scripts/tests/test_init_tui.py scripts/tests/integration/test_init_e2e.py`, then the full suite.

## Impact

- **Priority**: P3
- **Effort**: Small
- **Risk**: Low. The default change affects only new `ll-init` runs and configs that omit `type_cmd`. Explicit `"type_cmd": "mypy"` configs are left alone, and the CHANGELOG note covers them.

## Program Design

### Types

- `ProjectConfig.type_cmd: str | None` — `scripts/little_loops/config/core.py:219`; default value changes from `"mypy"` to `"mypy ."`, type unchanged.

### Signatures

- `process_issue_inplace(info: IssueInfo, config: BRConfig, logger: Logger, dry_run: bool = False) -> IssueProcessingResult` — `scripts/little_loops/issue_manager.py:720` (keyword-only options elided); the ll-auto driver that invokes `/ll:manage-issue` Phase 2, whose Phase 4 text this issue edits. Unchanged.
- `introspect(root: Path, template: TemplateMatch) -> IntrospectResult` — `scripts/little_loops/init/introspect.py:128`; public entry that reaches `_python_command`. Signature unchanged; the `type_cmd` value it returns for `[tool.mypy]` projects changes.

### Call Path

`ll-auto --only <ID>` → `process_issue_inplace` (`issue_manager.py:720`) → host `/ll:manage-issue` turn → Phase 4 Verify (`skills/manage-issue/SKILL.md:350`) → configured `test_cmd` / `lint_cmd` / `type_cmd` run verbatim.

`ll-init` → `introspect` (`introspect.py:128`) → `_python_command` (`:252`) → `type_cmd` value written to `.ll/ll-config.json`.

### Decision Rules

- A `{{config.project.<test|lint|type>_cmd}}` placeholder in Phase 4 is never followed by extra arguments on the same line.
- The full-suite run stays in Phase 4 and runs once, in the scratch-redirect form.
- A default or introspected `type_cmd` must be complete when run bare: `mypy .`, or `mypy` only when `[tool.mypy]` sets `files`.

## Acceptance Criteria

- [ ] Phase 4 runs `test_cmd`, `lint_cmd` and `type_cmd` verbatim, with no added arguments
- [ ] Phase 4 runs the full test suite once, in the scratch-redirect form
- [ ] Default and introspected `type_cmd` values run successfully when invoked bare (`mypy .`, or `mypy` when `[tool.mypy]` sets `files`)
- [ ] Host mirrors are regenerated and the mirror gates pass
- [ ] `skills/manage-issue/SKILL.md` stays at or under 500 lines (target: unchanged at 499)
- [ ] A regression test fails if an argument is appended to `test_cmd`, `lint_cmd` or `type_cmd` in Phase 4, and does not flag the `run_cmd` line
- [ ] CHANGELOG notes the bare-`mypy` migration

## Scope Boundaries

- Phase 4 keeps its full-suite run. FEAT-3573 decides separately whether autodev skips the
  run when its gate owns the suite.
- `commands/check-code.md:59`/`:69` and `commands/iterate-plan.md:126`/`:127` still append
  `src_dir` to `lint_cmd`/`type_cmd`. After this issue they are inconsistent with Phase 4
  (they keep working, but double-target with `ruff check .`/`mypy .`). Capture a follow-up
  issue to move them to the verbatim form.
- `lint_cmd` candidates `pylint` (the `python-generic` `command_options` pool and the
  `_TOOL_FALLBACK_COMMANDS` fallback) have the same problem: bare `pylint` has no target.
  This is out of scope; include it in the follow-up above.
- Existing consumer configs are not rewritten. The CHANGELOG note covers them. An
  init-time validation warning (`little_loops.init.validate`) for bare `mypy` is out of scope.
- No `format_cmd` stage is added to Phase 4.

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:confidence-check` - 2026-09-26T06:54:48 - `b6236edd-3c2e-4487-b3b9-c892c0144a8f.jsonl`
- `/ll:refine-issue` - 2026-09-26T06:42:16 - `f4536461-4b4c-49df-b9dd-8cc9f5906a6c.jsonl`
