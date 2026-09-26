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
complete command that keeps today's effective scope (`mypy <src_dir>`), so that running the
commands verbatim does not break type checking for default Python consumers. Because mypy
rejects any file reached through two targets, every other site that appends `src_dir` to
`type_cmd` must move to the verbatim form in the same change.

## Current Behavior

- `skills/manage-issue/SKILL.md:356`, `:359`, `:362` append `tests/ -v` and `src_dir` to
  `test_cmd`, `lint_cmd` and `type_cmd`. The host mirrors carry the same text
  (`.gemini/`, `.kimi-code/`, `.qwen/` `skills/manage-issue/SKILL.md:355`, `:358`, `:361`).
- Phase 4 runs the full test suite twice: once from the code-block line (`:356`) and
  again from `### Headless-Safe Final Test Run` (`:387`, scratch-redirect form). The
  subsection does not say whether it replaces or follows the code-block line.
- The default `type_cmd` is bare `mypy` at five sites:
  `scripts/little_loops/config-schema.json:43` (`default`),
  `scripts/little_loops/config/core.py:219` (dataclass default) and `:245`
  (`from_dict` fallback), `scripts/little_loops/templates/python-generic.json:27`, and
  `scripts/little_loops/init/introspect.py:290` (`_python_command`, returned whenever a
  `[tool.mypy]` table exists). Verified 2026-09-26: bare `mypy` with a
  `[tool.mypy]\nstrict = true` config exits 2 with
  `mypy: error: Missing target module, package, files, or command.`
- autodev's typecheck stage already runs `type_cmd` verbatim:
  `loops/oracles/code-run-gate.yaml:205` resolves `project.type_cmd` and `:408` runs
  `bash -c "$TYPECHECK_CMD"`. With the bare `mypy` default, that stage fails today for
  default Python consumers.
- Three other sites append `src_dir` to `type_cmd`: `commands/check-code.md:109`
  (`{{config.project.type_cmd}} {{config.project.src_dir}} --ignore-missing-imports`),
  `commands/iterate-plan.md:127` (success-criteria line), and
  `skills/create-loop/SKILL.md:338` (example `Action:` line). Their host mirrors carry the
  same text.

## Expected Behavior

- Phase 4 runs each configured command exactly as configured, with no added arguments.
- The Phase 4 test run happens once, in the scratch-redirect form of the
  "Headless-Safe Final Test Run" subsection (which already runs `test_cmd` bare and
  stays as is).
- Every default or introspected `type_cmd` runs successfully when invoked bare, and checks
  the same scope Phase 4 checks today (`src_dir`), not the whole repository.
- No site appends a target to `type_cmd`.

## Motivation

Commands with added arguments can run the wrong target, run a target twice, or fail on a
path that does not exist. Then the agent "fixes" a failure that the configured command
does not produce. Removing the arguments without fixing the `mypy` default would cause
the same failure mode for every default Python project. The default fix also repairs
autodev's typecheck stage, which already runs `type_cmd` verbatim.

## Proposed Solution

### 1. Phase 4 block (`skills/manage-issue/SKILL.md`, net −1 line)

- Replace the lint and type command lines with the bare placeholders
  (`{{config.project.lint_cmd}}`, `{{config.project.type_cmd}}`).
- Replace the two test lines (`:355` comment and `:356` command) with one comment line
  that says to run the full suite once, via the scratch-redirect form in
  `### Headless-Safe Final Test Run` below. Do not keep a `{{config.project.test_cmd}}`
  line in the code block. This removes the double run and frees one line under the
  500-line cap (499 → 498).
- Rewrite the existing intro line in place (`:352`, "Run each verification command if
  configured (non-null)…") so it also says to run each command exactly as configured,
  with no paths or flags appended. Do not add a new line.
- Do not remove the full-suite run from Phase 4. Phase 4 is the only verification under
  `ll-auto`, `ll-parallel` and `ll-sprint` when FEAT-3573's autodev gate is not in the
  call path. The run stays in `### Headless-Safe Final Test Run`.

### 2. `type_cmd` defaults: `mypy <src_dir>`

`mypy .` was considered and rejected. Verified 2026-09-26 in a scratch project with
`[tool.mypy] strict = true`:

- `mypy .` widens the scope from `src_dir` to the whole repo (`tests/`, `scripts/`, …) and
  exits 2 with `Duplicate module named 'conftest'` when `tests/conftest.py` and another
  top-level `conftest.py` exist; `mypy src/` passes on the same tree.
- `mypy . src/` exits 2 (`Source file found twice under different module names`), and even
  `mypy src/ src/` exits 2 (`Duplicate module named "pkg"`). mypy does not tolerate a
  duplicated target. `ruff check X X` does, so the `lint_cmd` sites are not affected.

The chosen default is `mypy <src_dir>`. It matches today's effective Phase 4 command, the
`docs/reference/CONFIGURATION.md:19` example (`"type_cmd": "mypy src/"`), and the
create-loop Python default (`skills/create-loop/templates.md:361`, `mypy {{src_dir}}`).

- Static defaults → `mypy src/` (the default `src_dir` is `src/`):
  `config-schema.json:43`, `config/core.py:219` (dataclass default),
  `templates/python-generic.json:27`.
- `config/core.py:245` (`ProjectConfig.from_dict`): when the `type_cmd` key is absent,
  derive it from the resolved `src_dir`: `f"mypy {src_dir}"`, or `mypy .` when `src_dir`
  is empty. An explicit `"type_cmd": null` stays `None`.
- `init/introspect.py`: move the `_introspect_src_dir` call (`:173-175`) above the command
  loop (`:150`), and pass the resolved `src_dir` value into `_python_command` as a new
  keyword argument. In the `type_cmd` branch (`:288-293`): if `[tool.mypy]` sets `files`,
  return `mypy`, because mypy then takes its targets from config and a CLI target would
  override that. Otherwise return `mypy <src_dir>` (`mypy .` if `src_dir` is empty). Keep
  `pyright` bare; it checks the cwd with no arguments.
- Update `docs/reference/API.md:415` (`type_cmd: str | None = "mypy"`),
  `docs/reference/CONFIGURATION.md:304` (defaults table `mypy`), and
  `skills/configure/show-output.md:15` (`(default: mypy)`) to `mypy src/`.
- Migration: existing consumer configs that set `"type_cmd": "mypy"` explicitly are not
  rewritten. Add a CHANGELOG note in the release section (not `[Unreleased]`) saying that
  Phase 4, `/ll:check-code` and `/ll:iterate-plan` now run `type_cmd` verbatim, so a bare
  `mypy` needs a target (`mypy src/`) or a `[tool.mypy] files = [...]` setting.

### 3. Other `type_cmd` sites that append `src_dir`

A complete `type_cmd` plus an appended `src_dir` hard-fails (see §2), so these move to the
verbatim form in this issue:

- `commands/check-code.md:109` →
  `{{config.project.type_cmd}} --ignore-missing-imports`. Keep the flag; only the
  `src_dir` target goes.
- `commands/iterate-plan.md:127` → `` `{{config.project.type_cmd}}` passes ``.
- `skills/create-loop/SKILL.md:338` → `Action: {{config.project.type_cmd}}` (example
  output; same line count).
- Regenerate host mirrors (`.gemini/commands/check-code.toml`,
  `.gemini/commands/iterate-plan.toml`, `.kimi-code/skills/ll-check-code/SKILL.md`,
  `.kimi-code/skills/ll-iterate-plan/SKILL.md`, `.qwen/commands/ll/check-code.md`,
  `.qwen/commands/ll/iterate-plan.md`, and each host's `skills/create-loop/SKILL.md`)
  with `ll-adapt`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Conventions in force for the regression test: SKILL.md section tests define a local `_phase_text`-style slicer per file (heading `.index()` to the next heading), live in flat `scripts/tests/test_<skill>_skill.py` files, and group assertions in `Test<Skill><Topic>` classes (evidence: `test_capture_issue_skill.py`, `test_issue_size_review_skill.py`, `test_audit_issue_conflicts_skill.py`). There is no shared helper; the end boundary varies (next `\n### `, a named sibling heading, or an explicit end header). The only fenced-block extraction is `re.findall(r"```bash\n(.*?)```", content, re.DOTALL)` in `test_audit_issue_conflicts_skill.py`.
- The `*_cmd` placeholder convention is split: bare form in `SKILL.md:42-43`, `templates.md`, `commands/iterate-plan.md:125`, `commands/run-tests.md:22` (which states the configured value "already includes the test path"); args-appended form in `SKILL.md:213`, `:356`, `:359`, `:362`, `commands/check-code.md`. This issue moves Phase 4 and every `type_cmd` site to the bare form; `lint_cmd` sites outside Phase 4 are deferred (ruff tolerates duplicate targets).
- Net line budget: `SKILL.md` is 499 lines and `test_enh494_skill_companions.py` fails above 500. The Phase 4 edit is net −1 (the test command line is dropped). Any overflow belongs in `skills/manage-issue/templates.md`, which `test_enh494_skill_companions.py` already lists in `EXPECTED_COMPANIONS`.
- Placeholders are substituted only by `skill_expander._substitute_config` (`scripts/little_loops/skill_expander.py`, called from `expand_skill()` in the `ll-auto`/`ll-parallel`/`ll-sprint` path via `issue_manager.py`). An unset value (`None`) becomes `""`; no line is dropped. Bare placeholders therefore leave a blank line when `type_cmd`/`build_cmd` is unset, where today's text leaves a stray ` src/`. The "skip silently if not configured" behavior is prose the model follows, not something the expander enforces.
- Host mirrors are byte-copies of `SKILL.md` with `{{config.*}}` left unexpanded (`.gemini/skills/manage-issue/SKILL.md` Phase 4 heading sits at line 349, one line above source). `test_host_artifacts_are_not_stale` (`test_wiring_skills_and_commands.py`, parametrized over `GATED_HOSTS` × kinds) fails for gemini/kimi-code/qwen until `ll-adapt --host <h> --apply` is run after any source edit. `test_skill_mirrors_carry_companions` covers companions only, not `SKILL.md` bodies.
- The Phase 4 block (`SKILL.md:354-372`) also carries three lines outside this issue's scope that legitimately take arguments: `build_cmd` (bare), `run_cmd` (`& pid=$!; sleep 3; kill $pid`, shell-level backgrounding), and the commented `custom_verification`. The regression-test rule must not flag the `run_cmd` line.
- `### Headless-Safe Final Test Run` (`SKILL.md:376-400`) uses bare `{{config.project.test_cmd}}` redirected to `.loops/tmp/scratch/test-results.txt`, and never says whether it replaces or follows the Phase 4 test line. Both BUG-2408 pins (`foreground-blocking`, `scheduled wakeup`) live only in that subsection, so they are unaffected by a Phase 4 block edit.
- Phase 3 (`SKILL.md:213`) also appends args to `test_cmd` (`[newly_written_test_files] -v`); that is a different, intentional targeted run and is not in this issue's scope.
- No existing test asserts on Phase 4 `tests/ -v` or the `src_dir` lint/type lines, so no test pins the current wrong text.
- Review 2026-09-26: `lint_cmd`'s default `ruff check .` is already complete. Today Phase 4 runs `ruff check . src/`, which lints `src/` twice. `pyright` and `npx tsc --noEmit` (the TS introspect value, `introspect.py:353`) also work bare. Only the `mypy` default depends on the appended `src_dir`.
- Review 2026-09-26 (mypy probe): `mypy .`, `mypy . src/` and `mypy src/ src/` all exit 2 on a src-layout project; `mypy src/` and (with `[tool.mypy] files = ["src"]`) bare `mypy` exit 0. See §2.
- `introspect()` computes `src_dir` after the command loop today (`introspect.py:150` loop, `:173-175` src_dir). `_introspect_src_dir` falls back to the template `src_dir` (`src/` for both `python-generic` and `generic`) when there is no marker or several candidates, so the introspected `type_cmd` is `mypy src/` in those cases.

## Integration Map

### Files to Modify
- `skills/manage-issue/SKILL.md` — Phase 4 block (:350-:372): lint/type lines to bare placeholders, test line pair collapsed to one pointer comment, intro rewritten in place (net −1 line)
- `commands/check-code.md:109` — drop `{{config.project.src_dir}}` from the `type_cmd` line; keep `--ignore-missing-imports`
- `commands/iterate-plan.md:127` — `type_cmd` success criterion to bare placeholder
- `skills/create-loop/SKILL.md:338` — example `Action:` line to bare placeholder
- Host mirrors of the four files above under `.gemini/`, `.kimi-code/`, `.qwen/` — regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply`. Do not hand-edit them.
- `scripts/little_loops/config-schema.json:43` — `type_cmd` default `mypy` → `mypy src/`
- `scripts/little_loops/config/core.py:219` — dataclass default → `mypy src/`
- `scripts/little_loops/config/core.py:245` — `from_dict` fallback → `f"mypy {src_dir}"` (or `mypy .` if `src_dir` is empty) when the key is absent
- `scripts/little_loops/templates/python-generic.json:27` — `type_cmd` → `mypy src/`
- `scripts/little_loops/init/introspect.py` — compute `src_dir` before the command loop; `_python_command` takes `src_dir`; `type_cmd` branch returns `mypy` if `[tool.mypy]` has `files`, else `mypy <src_dir>`
- `docs/reference/API.md:415` — `ProjectConfig` default listing
- `docs/reference/CONFIGURATION.md:304` — defaults table
- `skills/configure/show-output.md:15` — `(default: mypy)` → `(default: mypy src/)`
- `CHANGELOG.md` — migration note in the release section

### Tests
- `scripts/tests/test_wiring_skills_and_commands.py` — mirror gates; BUG-2408 substring pins (`foreground-blocking`, `scheduled wakeup`); `SPAWN_SITE_INVENTORY` line pin (`skills/manage-issue/SKILL.md`, line 110). The edit is below line 110, so the pin is safe if the line count above it does not change.
- `scripts/tests/test_manage_issue_changelog_gate.py` — verbatim `GATE_SNIPPET`; do not touch it.
- `scripts/tests/test_enh494_skill_companions.py` — 500-line cap. The file goes 499 → 498.
- Tests that pin the bare `mypy` default; update them:
  - `scripts/tests/test_config.py:145` → `mypy src/`
  - `scripts/tests/test_init_proposal.py:74`
  - `scripts/tests/test_init_introspect.py:74` (`test_type_cmd_declared_via_mypy_table`, no marker → template `src_dir` → `mypy src/`), `:83` (`test_type_cmd_defaults_when_no_mypy_table`, template default → `mypy src/`), `:104` (generic-template regression → `mypy src/`)
  - `scripts/tests/integration/test_init_e2e.py:256`, `:269` (provenance summary string `type_cmd: mypy  (declared: [tool.mypy] present)`)
  - Check `scripts/tests/test_init_core.py:145` and `scripts/tests/test_init_tui.py:94`. These look like input fixtures, not assertions on the default; update them only if they fail.
- New: `scripts/tests/test_init_introspect.py`:
  - `[tool.mypy]` with `files = ["src"]` → `type_cmd == "mypy"`
  - `[tool.mypy]` without `files`, plus a single top-level package directory `mypkg` (with an `__init__` module) in `tmp_path` → `type_cmd == "mypy mypkg/"` (proves `type_cmd` follows the detected `src_dir`, not the template default)
- New: `scripts/tests/test_config.py` — `ProjectConfig.from_dict({"src_dir": "lib/"}).type_cmd == "mypy lib/"`; `from_dict({"type_cmd": None}).type_cmd is None`.
- New (to create): `test_manage_issue_skill.py` under the tests dir, class `TestManageIssuePhase4Verbatim`:
  - Slice from `## Phase 4: Verify` to `### Headless-Safe Final Test Run`.
  - For every line that contains `{{config.project.lint_cmd}}` or `{{config.project.type_cmd}}`, assert that `line.strip()` equals the bare placeholder. Do not check other `*_cmd` placeholders, so the `run_cmd` line is not flagged.
  - Assert that no line in the slice contains `{{config.project.test_cmd}}` (the suite runs once, in the subsection), and that the slice references `Headless-Safe Final Test Run`.
  - Assert that the slice tells the model to run commands as configured (a short, stable substring such as `exactly as configured`).
- New: in the same file (or a parametrized test), assert that no line in `commands/check-code.md`, `commands/iterate-plan.md` or `skills/create-loop/SKILL.md` contains `{{config.project.type_cmd}} {{config.project.src_dir}}`.

## Implementation Steps

1. Write the new tests (Red): `test_manage_issue_skill.py`, the new introspect and `from_dict` cases, and the updated default assertions.
2. Edit the Phase 4 block in `skills/manage-issue/SKILL.md` (bare lint/type placeholders, test pair collapsed to one pointer comment, in-place intro rewrite; `wc -l` goes to 498).
3. Edit `commands/check-code.md:109`, `commands/iterate-plan.md:127`, `skills/create-loop/SKILL.md:338` to the verbatim `type_cmd` form.
4. Change the `type_cmd` defaults: schema, `config/core.py` (dataclass default and `from_dict` derivation), `python-generic` template. Reorder `introspect()` and extend `_python_command`. Update `docs/reference/API.md:415`, `docs/reference/CONFIGURATION.md:304`, `skills/configure/show-output.md:15`.
5. Regenerate the host mirrors with `ll-adapt --host <gemini|kimi-code|qwen> --apply`.
6. Add the CHANGELOG migration note.
7. Run `python -m pytest scripts/tests/ -k manage_issue_skill` (the new file), then `python -m pytest scripts/tests/test_wiring_skills_and_commands.py scripts/tests/test_enh494_skill_companions.py scripts/tests/test_manage_issue_changelog_gate.py scripts/tests/test_config.py scripts/tests/test_init_introspect.py scripts/tests/test_init_proposal.py scripts/tests/test_init_core.py scripts/tests/test_init_tui.py scripts/tests/integration/test_init_e2e.py`, then the full suite.

## Impact

- **Priority**: P3
- **Effort**: Small–Medium (more sites than originally scoped, all mechanical)
- **Risk**: Low. The default change affects only new `ll-init` runs and configs that omit `type_cmd`, and keeps the effective scope Phase 4 checks today (`mypy <src_dir>`). Explicit `"type_cmd": "mypy"` configs are left alone, and the CHANGELOG note covers them.

## Program Design

### Types

- `ProjectConfig.type_cmd: str | None` — `scripts/little_loops/config/core.py:219`; default value changes from `"mypy"` to `"mypy src/"`, type unchanged. `from_dict` derives it from `src_dir` when the key is absent.

### Signatures

- `process_issue_inplace(info: IssueInfo, config: BRConfig, logger: Logger, dry_run: bool = False) -> IssueProcessingResult` — `scripts/little_loops/issue_manager.py:720` (keyword-only options elided); the ll-auto driver that invokes `/ll:manage-issue` Phase 2, whose Phase 4 text this issue edits. Unchanged.
- `introspect(root: Path, template: TemplateMatch) -> IntrospectResult` — `scripts/little_loops/init/introspect.py:128`; public entry that reaches `_python_command`. Signature unchanged; it now resolves `src_dir` before the command loop, and the `type_cmd` value it returns for `[tool.mypy]` projects changes.
- `ProjectConfig.from_dict(data: dict[str, Any]) -> ProjectConfig` — `scripts/little_loops/config/core.py:237`; signature unchanged; absent `type_cmd` now derives from `src_dir`.

### Call Path

`ll-auto --only <ID>` → `process_issue_inplace` (`issue_manager.py:720`) → host `/ll:manage-issue` turn → Phase 4 Verify (`skills/manage-issue/SKILL.md:350`) → configured `lint_cmd` / `type_cmd` run verbatim; `test_cmd` runs once in `### Headless-Safe Final Test Run`.

`ll-init` → `introspect` (`introspect.py:128`) → `_introspect_src_dir` → `_python_command` (`:252`) → `type_cmd` value (`mypy <src_dir>` or `mypy`) written to `.ll/ll-config.json`.

`autodev` → `oracles/code-run-gate.yaml` `resolve_commands` (`:205`, `project.type_cmd`) → typecheck stage (`:408`, `bash -c "$TYPECHECK_CMD"`) → now gets a complete default command.

### Decision Rules

- A `{{config.project.<lint|type>_cmd}}` placeholder in Phase 4 is never followed by extra arguments on the same line, and Phase 4's code block carries no `test_cmd` line.
- No site appends `{{config.project.src_dir}}` to `{{config.project.type_cmd}}`. Flags (e.g. `--ignore-missing-imports`) may follow it.
- The full-suite run stays in Phase 4 and runs once, in the scratch-redirect form.
- A default or introspected `type_cmd` must be complete when run bare and scoped to `src_dir`: `mypy <src_dir>`, or `mypy` only when `[tool.mypy]` sets `files`.

## Acceptance Criteria

- [ ] Phase 4 runs `lint_cmd` and `type_cmd` verbatim, with no added arguments
- [ ] Phase 4 runs the full test suite once, in the scratch-redirect form, and its code block has no `test_cmd` line
- [ ] Default and introspected `type_cmd` values run successfully when invoked bare (`mypy <src_dir>`, or `mypy` when `[tool.mypy]` sets `files`)
- [ ] `commands/check-code.md`, `commands/iterate-plan.md` and `skills/create-loop/SKILL.md` no longer append `src_dir` to `type_cmd`
- [ ] Host mirrors are regenerated and the mirror gates pass
- [ ] `skills/manage-issue/SKILL.md` stays at or under 500 lines (target: 498)
- [ ] A regression test fails if an argument is appended to `lint_cmd` or `type_cmd` in Phase 4 or a `test_cmd` line returns to the Phase 4 code block, and does not flag the `run_cmd` line
- [ ] Docs and `/ll:configure` show-output list the new default (`mypy src/`)
- [ ] CHANGELOG notes the bare-`mypy` migration

## Scope Boundaries

- Phase 4 keeps its full-suite run. FEAT-3573 decides separately whether autodev skips the
  run when its gate owns the suite.
- `commands/check-code.md:59`/`:69`/`:154` and `commands/iterate-plan.md:126` still append
  `src_dir` to `lint_cmd`. After this issue they are inconsistent with Phase 4, but ruff
  tolerates a duplicated target, so they keep working (double-linting `src_dir`). Capture a
  follow-up issue to move them to the verbatim form.
- `lint_cmd` candidates `pylint` (the `python-generic` `command_options` pool and the
  `_TOOL_FALLBACK_COMMANDS` fallback) have the same problem: bare `pylint` has no target.
  This is out of scope; include it in the follow-up above.
- If the user edits `src_dir` in the `ll-init` TUI after introspection, the introspected
  `type_cmd` still carries the original `src_dir`. Keeping them in sync is out of scope.
- Existing consumer configs are not rewritten. The CHANGELOG note covers them. An
  init-time validation warning (`little_loops.init.validate`) for bare `mypy` is out of scope.
- No `format_cmd` stage is added to Phase 4.

## Status

**Open** | Created: 2026-09-26 | Priority: P3


## Session Log
- `/ll:verify-issues` - 2026-09-26T16:06:58 - `cd2a5969-8672-4f0e-924f-ea543f36e04a.jsonl`
- `/ll:confidence-check` - 2026-09-26T06:54:48 - `b6236edd-3c2e-4487-b3b9-c892c0144a8f.jsonl`
- `/ll:refine-issue` - 2026-09-26T06:42:16 - `f4536461-4b4c-49df-b9dd-8cc9f5906a6c.jsonl`
