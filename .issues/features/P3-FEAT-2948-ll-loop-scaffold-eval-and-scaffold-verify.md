---
id: FEAT-2948
title: 'll-loop scaffold-eval / scaffold-verify: YAML templating for eval and verification
  loops'
type: FEAT
priority: P3
status: done
discovered_by: skill-audit
discovered_date: 2026-07-31
parent: EPIC-2938
epic: EPIC-2938
labels:
- cli
- loops
- eval
learning_tests_required:
- ruamel.yaml
testable: true
confidence_score: 92
outcome_confidence: 84
score_complexity: 19
score_test_coverage: 23
score_ambiguity: 21
score_change_surface: 21
completed_at: '2026-08-01T12:06:43Z'
---

# FEAT-2948: `ll-loop scaffold-eval` / `scaffold-verify` — FSM YAML templating in Python

## Summary

`skills/create-eval-from-issues/SKILL.md` (482 lines) and `skills/verify-issue-loop/SKILL.md` (212 lines + templates.md) hand-assemble FSM YAML in prose: create-eval carries two full YAML templates (L265–422) including proof-state slugification, `check_proof_t1.on_yes: check_proof_t2` chaining, and `execute.next` rewiring; verify-issue-loop normalizes bullet markers (L129–135) and selects timeouts. Mis-chaining states is a real bug class. Emit the YAML from Python; the LLM supplies only prompt/criteria strings.

## Current Behavior

The LLM reads acceptance criteria via `ll-issues show --json`, then assembles loop YAML by following ~250 lines of templating instructions, validated only after the fact by `ll-loop validate`.

## Expected Behavior

- `ll-loop scaffold-eval --issues FEAT-1,FEAT-2 [--dsl] [--out PATH|--stdout] --json` — reads criteria via `issue_parser.parse_file`, emits schema-valid loop YAML with placeholder slots for the `execute` prompt and per-criterion `llm_structured` prompts; proof-state chaining generated, not narrated.
- `ll-loop scaffold-verify <id> [--adversarial] [--out PATH|--stdout] --json` — same for single-issue verification loops (criteria extraction with bullet-marker normalization, timeout selection).
- Both skills shrink to: synthesize the natural-language prompts/criteria (genuine authoring), fill the placeholders, run `ll-loop validate`.

## Proposed Solution

Reuse the loop schema/validation already in `ll-loop` (`fsm/schema.py`, `fsm/validation.py`) so scaffolds are validated at generation time; criteria extraction shares `issue_parser` section parsing. The two scaffolds share a templating core.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **`issue_parser.py` has no body-section extractor to reuse directly.** `IssueParser.parse_file()` (`issue_parser.py:1310`) returns `IssueInfo` — frontmatter/title/`learning_tests_required`/relationship fields only, no `## Acceptance Criteria`/`## Expected Behavior`/`## Use Case` body text. The closest reusable primitive is `IssueParser._parse_section_items()` (`issue_parser.py:1665`), whose *section-location* half (regex `^##\s+{section_name}\s*$`, slice to next `^##\s+` header, strip code fences via `_strip_code_fences`) is generalizable, but its *item-extraction* half currently only pulls issue IDs via `ISSUE_ID_PATTERN.findall` (used for `## Blocked By`/`## Blocks`). `extract_criteria()` needs a new bullet-line regex (`- [ ]`/`- [x]`/`- `/`* `/`N. `, skip blank lines and indented sub-bullets) replacing that ID-extraction step — this is the Python home for the bullet-normalization rules currently only spelled out as prose at `skills/verify-issue-loop/SKILL.md:129-135`.
- **No existing "chain states via on_yes" helper exists anywhere in the codebase** — both proof-state chaining (`skills/create-eval-from-issues/SKILL.md:306-327`: slugify each `learning_tests_required` target via `issue_parser.py:1015 slugify()`, emit one `check_proof_<slug>` state per target, chain `check_proof_t1.on_yes: check_proof_t2` …, splice before `check_skill`, rewire `execute.next`) and the criteria-mode linear chain (`skills/verify-issue-loop/templates.md:27-40`: `verify-criterion-<i>.on_yes` → `verify-criterion-<i+1>`, last → `done`, every state's `on_no`/`on_partial` → `failed`) are pure prose today. `scaffold_eval()`/`scaffold_verify()` are genuinely new code for this, not reuse — but both are instances of the same "chain + splice into a state graph" shape and should share one helper.
- **Validation should happen in-process, not via `ll-loop validate` shell-out.** `fsm.validation.validate_fsm(fsm: FSMLoop, orchestration_request_path=None) -> list[ValidationError]` (`fsm/validation/structural_rules.py:908`) validates an already-constructed `FSMLoop` object directly — build the `FSMLoop`/`StateConfig` dataclasses (`fsm/schema.py`, `to_dict()` at `FSMLoop.to_dict():1352`) and call `validate_fsm()` before writing/returning, rather than writing the file first and shelling to `ll-loop validate` per `cli/loop/config_cmds.py:cmd_validate()`'s pattern (`load_and_validate()`, `structural_rules.py:1541`, is the file-reading wrapper around the same call — useful for the CLI's own `--out` round-trip check, not the core generation path).
- **`ruamel.yaml` + `LiteralScalarString` is the only existing precedent for generating clean FSM YAML from Python** (`loops/yaml_state_editor.py:extract_action()`/`replace_action()`) — use `LiteralScalarString` for multi-line `action`/`evaluate.prompt` fields so scaffolds emit `action: |` block scalars instead of ugly single-line strings, and `file_utils.py:16 atomic_write()` for the `--out` file write.
- **Adversarial mode's fixed template** (`skills/verify-issue-loop/templates.md:146-421`) is 3 fixed probe states (`probe-boundary`, `probe-malformed-hostile`, `probe-failure-mode`) chained on `on_yes`, each `on_no: failed_with_finding`, routing to a non-LLM `count_probes` gate (`action_type: shell`, `ls "${context.run_dir}"/probe-*.json | wc -l`, `output_numeric operator: ge target: 3`) rather than `done` — `scaffold_verify(..., adversarial=True)` should emit this fixed structure verbatim (no per-issue variation), only `criteria=` mode varies state count with the extracted `CriterionSlot` list.
- **CLI dispatch convention**: `ll-loop`'s existing subcommands (`cli/loop/__init__.py`) still use the older inline `subparsers.add_parser(...)` + `elif args.command == "..."` chain (register name in `known_subcommands` set, lines 57–92; add parser block near `audit`'s at lines 938–997; add dispatch clause near lines 1014–1064) — unlike `ll-issues`'s newer `add_<name>_parser(subs)`/`cmd_<name>(config, args)` batch-registration pattern. Follow `ll-loop`'s existing style, not `ll-issues`'s, since this lands in `cli/loop/`.

## Implementation Steps

1. Shared scaffold core + `scaffold-verify` (smaller): `scripts/little_loops/cli/loop/scaffold_verify.py` — `extract_criteria()` (new bullet-normalizer generalizing `IssueParser._parse_section_items()`'s section-location logic, `issue_parser.py:1665`), fixed adversarial-mode 3-probe template (`skills/verify-issue-loop/templates.md:146-421`), timeout selection (1800/2700) in code. Register via `known_subcommands`/`add_parser`/dispatch in `cli/loop/__init__.py` following the `audit`/`rename`/`cleanup` shape (module → pure function → `cmd_*` entry point, per `cli/loop/rename.py`).
2. `scaffold-eval` incl. proof-state chaining (slug via `issue_parser.py:1015 slugify()`, splice `check_proof_<slug>` states before `check_skill`, rewire `execute.next` per `skills/create-eval-from-issues/SKILL.md:306-327`); defer `--dsl` growth to a follow-up if it balloons. Both scaffolds build `FSMLoop`/`StateConfig` (`fsm/schema.py`) and call `validate_fsm()` (`fsm/validation/structural_rules.py:908`) in-process before returning `ScaffoldResult`.
3. Slim `skills/create-eval-from-issues/SKILL.md` (drop the Variant A/B YAML templates at L265–422) and `skills/verify-issue-loop/SKILL.md` + `templates.md` (drop the bullet-normalization prose at L129–135 and the per-mode state templates) down to: call the scaffold CLI, synthesize prompts/criteria text, fill placeholders, `ll-loop validate`.
4. Tests: `scripts/tests/test_ll_loop_scaffold_eval.py` / `test_ll_loop_scaffold_verify.py`, modeled on `test_cli_loop_rename.py`/`test_cli_loop_cleanup.py` (import pure functions directly, not via `main_loop()` subprocess) — generated YAML passes `validate_fsm()` (incl. MR-gates) for fixture issues; chaining correctness for N proof states / N criteria; adversarial template emitted verbatim.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

5. Add `"scaffold-eval"`/`"scaffold-verify"` to `known_subcommands` (`cli/loop/__init__.py` ~lines 57–92) — `cmd_run`'s loop-name shorthand check (`argv[0] not in known_subcommands`, ~line 98) misinterprets an unregistered subcommand string as a loop name, so this must land before/with the dispatch registration, not after.
6. Add a `handler_specs` entry for `scaffold-eval`/`scaffold-verify` in `scripts/tests/test_cli_loop_dispatch.py`'s `_mock_handlers()` (~line 29) and a `test_scaffold_eval_routes_to_handler`/`test_scaffold_verify_routes_to_handler` pair, mirroring existing `TestMainLoopDispatch` cases.
7. Rework `scripts/tests/test_verify_issue_loop.py`'s `TestMergedSkillModeDispatch.test_mode_documented_as_optional_default_criteria` (~line 748), which asserts literal prose via `SKILL_MD.read_text()` — either retain the asserted phrases in the slimmed skill body or retarget the test at `scaffold_verify()`'s output.
8. Verify `skills/verify-issue-loop/SKILL.md`'s frontmatter `allowed-tools` includes an `ll-loop:*` Bash glob (mirroring `skills/create-eval-from-issues/SKILL.md`'s existing `Bash(ll-issues:*, ll-loop:*, mkdir:*)`) before wiring in the CLI-delegation call.
9. Regenerate host-mirror skill copies (`.kimi-code/skills/{create-eval-from-issues,verify-issue-loop}/SKILL.md`, `.gemini/skills/{create-eval-from-issues,verify-issue-loop}/SKILL.md`) via `ll-adapt --host <host> --apply` after the source `SKILL.md` bodies are slimmed — do not hand-edit these generated copies.

## Integration Map

### Files to Modify

- `scripts/little_loops/cli/loop/__init__.py` — register `scaffold-eval`/`scaffold-verify` in `known_subcommands` (lines 57–92), add `add_parser(...)` blocks near `audit`'s (lines 938–997), add dispatch clauses near lines 1014–1064; deferred-import the new modules alongside the other `from little_loops.cli.loop.X import cmd_Y` lines (25–44)
- `scripts/little_loops/cli/loop/scaffold_verify.py` (new) — `extract_criteria()`, `scaffold_verify()`, `cmd_scaffold_verify(args, loops_dir)`
- `scripts/little_loops/cli/loop/scaffold_eval.py` (new) — `scaffold_eval()`, `cmd_scaffold_eval(args, loops_dir)`; likely shares a `_scaffold_core.py` chaining helper with `scaffold_verify.py`
- `scripts/little_loops/issue_parser.py` — extend/generalize `_parse_section_items()` (line 1665) or add a sibling body-section extractor for `## Acceptance Criteria`/`## Expected Behavior`/`## Use Case`
- `skills/create-eval-from-issues/SKILL.md` — drop Variant A/B YAML templates and proof-first-gate chaining prose (L265–422); replace with a call to `ll-loop scaffold-eval`
- `skills/verify-issue-loop/SKILL.md` — drop bullet-marker normalization prose (L129–135) and timeout-selection logic (L173–190); replace with a call to `ll-loop scaffold-verify`
- `skills/verify-issue-loop/templates.md` — drop per-mode state-synthesis templates (criteria N-state chain, adversarial 3-probe chain); becomes prompt-authoring guidance only

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — add `scaffold-eval`/`scaffold-verify` subcommand sections + quick-reference table rows
- `docs/reference/COMMANDS.md` — fix stale "validated with `ll-loop validate`" prose at the `/ll:create-eval-from-issues`/`/ll:verify-issue-loop` entries

### Reused Primitives

- `scripts/little_loops/issue_parser.py:1015 slugify(text)` — proof-state slug generation
- `scripts/little_loops/issue_parser.py:1310 IssueParser.parse_file()` — title/frontmatter/`learning_tests_required`
- `scripts/little_loops/issue_parser.py:1665 IssueParser._parse_section_items()` — section-location half reusable for `extract_criteria()`
- `scripts/little_loops/fsm/schema.py` — `StateConfig`, `EvaluateConfig`, `FSMLoop` dataclasses + `to_dict()`
- `scripts/little_loops/fsm/validation/structural_rules.py:908 validate_fsm()` — in-process validation of a built `FSMLoop`
- `scripts/little_loops/loops/yaml_state_editor.py` — `LiteralScalarString` import for clean multi-line `action`/prompt block scalars
- `scripts/little_loops/file_utils.py:16 atomic_write()` — `--out` file write

### Dependent Files (Callers)

- `skills/create-eval-from-issues/SKILL.md` — sole current caller of the eval-harness YAML templating being replaced
- `skills/verify-issue-loop/SKILL.md` (+ `templates.md`) — sole current caller of the verify-loop YAML templating being replaced

### Similar Patterns

- `scripts/little_loops/cli/loop/rename.py` — closest existing analog: dataclass report + pure computation function separate from a thin `cmd_*` entry point
- `scripts/little_loops/cli/loop/cleanup.py` / `audit.py` — EPIC-2938 "mechanical port of skill prose" module docstring convention (cite the skill section being ported, note what stays LLM judgment)
- `scripts/little_loops/cli/loop/config_cmds.py:cmd_validate()` — call-site precedent for `load_and_validate()`/`validate_fsm()`

### Tests

- `scripts/tests/test_cli_loop_rename.py` / `test_cli_loop_cleanup.py` — direct-import test convention (no subprocess) to model `test_ll_loop_scaffold_eval.py`/`test_ll_loop_scaffold_verify.py` after
- `scripts/tests/test_create_eval_from_issues.py` / `test_verify_issue_loop.py` — existing eval/verify YAML fixtures (`VARIANT_A_YAML`/`VARIANT_B_YAML`) usable as expected-output comparisons for the new scaffolds
- `scripts/tests/test_fsm_validation_meta_rules.py` — MR-gate coverage the generated YAML must pass

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_cli_loop_dispatch.py` — `_mock_handlers()`'s `handler_specs` list (~line 29) has no entry for `rename`/`cleanup`/`audit` either, so `scaffold-eval`/`scaffold-verify` need a new `("little_loops.cli.loop.scaffold_eval", ["cmd_scaffold_eval"])`-style entry added for dispatch-routing coverage, following `TestMainLoopDispatch`'s `test_<cmd>_routes_to_handler` pattern
- `scripts/tests/test_verify_issue_loop.py` — `TestMergedSkillModeDispatch.test_mode_documented_as_optional_default_criteria` (~line 748) asserts literal prose (`"mode"`, `"criteria"`, `"adversarial"`, `"default"`, `"silently"`) via `SKILL_MD.read_text()`; will break once the skill body is slimmed to a CLI-delegation call — rework to target `scaffold_verify()` output directly or preserve the asserted phrases in the new prose
- `scripts/tests/test_create_eval_from_issues.py` — hand-authored `VARIANT_A_YAML`/`VARIANT_B_YAML`-style fixture classes describe the *current* prose-templated shape only; add new tests calling `scaffold_eval()`/`extract_criteria()` directly rather than relying on these fixtures once generation moves to Python

### Documentation

- `docs/reference/API.md` — add entries for the new scaffold modules
- `.claude/CLAUDE.md` `ll-loop` CLI bullet — append `scaffold-eval`/`scaffold-verify` to the subcommand list

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — canonical `ll-loop` subcommand reference: add `#### \`ll-loop scaffold-eval\`` / `#### \`ll-loop scaffold-verify\`` sections (~after line 1139, following the `rename`/`cleanup`/`audit` pattern) plus matching quick-reference table rows (~lines 980–998)
- `docs/reference/COMMANDS.md` — `/ll:create-eval-from-issues` (~line 623) and `/ll:verify-issue-loop` (~line 650) entries both state output is "validated with `ll-loop validate` before writing"; update to reflect in-process `validate_fsm()` validation inside the new scaffold CLI commands

## Use Case

`/ll:create-eval-from-issues FEAT-1234` runs `ll-loop scaffold-eval --issues FEAT-1234 --stdout`, receives schema-valid loop YAML with `<PROMPT>` / `<CRITERION_N>` placeholder slots, writes the two synthesized natural-language strings into them, and validates — the model never assembles states or chains `on_yes` routes by hand.

## Program Design

### Types

- `ScaffoldResult: dataclass`
  - `yaml_path: Path | None`
  - `yaml_text: str`
  - `placeholders: list[str]`
  - `validated: bool`
- `CriterionSlot: dataclass`
  - `index: int`
  - `source_text: str`
  - `state_name: str`

### Signatures

- `extract_criteria(issue: IssueInfo, body: str) -> list[CriterionSlot]` — bullet-marker normalization (`- [ ]`, `- [x]`, `-`, `*`, `1.`; skip sub-bullets)
- `scaffold_eval(issue_ids: list[str], dsl: bool) -> ScaffoldResult` — generates execute + chained `llm_structured` proof states
- `scaffold_verify(issue_id: str, adversarial: bool) -> ScaffoldResult` — timeout selection (1800/2700) in code
- Both validate via `fsm.validation` before returning

### Call Path

- `main_loop()` (existing, `cli/loop/__init__.py`) -> `scaffold_eval()` / `scaffold_verify()`
- `extract_criteria()` -> `find_issues()` (existing, `issue_parser.py`)

## Impact

- **Priority**: P3 - Removes a real mis-chaining bug class, but eval/verify authoring is lower-traffic than issue flow
- **Effort**: Medium - Shared templating core + two frontends
- **Risk**: Low - Output validated at generation time by the existing FSM validator

## Status

**Open** | Created: 2026-07-31 | Priority: P3

## Acceptance Criteria

- [ ] Generated YAML always passes `ll-loop validate` before the LLM touches it
- [ ] Both skills contain no YAML templates or state-chaining instructions
- [ ] Placeholder slots are the only LLM-filled content
- [ ] pytest coverage in `scripts/tests/`


## Session Log
- `ll-auto` - 2026-08-01T12:06:43 - `1cf9ae6d-4727-4d27-ad4f-29ac5c9aed2b.jsonl`
- `/ll:confidence-check` - 2026-08-01T11:40:30 - `56d32d35-c4a1-4d0c-9d22-485d9210a185.jsonl`
- `/ll:wire-issue` - 2026-08-01T11:39:17 - `f3f28a01-fa36-46c4-b185-507c70472442.jsonl`
- `/ll:refine-issue` - 2026-08-01T11:32:52 - `92786dbe-d778-4d4a-9fa1-4ee590311248.jsonl`


---

## Resolution

- **Action**: implement
- **Completed**: 2026-08-01
- **Status**: Completed (automated fallback)
- **Implementation**: Command exited early but issue was addressed


### Files Changed
- See git history for details

### Verification Results
- Automated verification passed

### Commits
- See git log for details
