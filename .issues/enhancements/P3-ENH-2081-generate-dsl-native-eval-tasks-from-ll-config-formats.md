---
id: ENH-2081
title: Generate DSL-native eval tasks from ll's own config formats
type: ENH
priority: P3
status: done
captured_at: '2026-06-10T18:12:09Z'
completed_at: '2026-06-11T20:05:27Z'
discovered_date: '2026-06-10'
discovered_by: capture-issue
parent: EPIC-2087
confidence_score: 99
outcome_confidence: 82
score_complexity: 18
score_test_coverage: 20
score_ambiguity: 23
score_change_surface: 21
decision_needed: false
---

# ENH-2081: Generate DSL-native eval tasks from ll's own config formats

## Summary

Extend `ll:create-eval-from-issues` and `ll-harness` with a DSL-native evaluation mode that generates and runs fill-in-the-blank and transform tasks targeting ll's own YAML loop syntax, issue frontmatter, and FSM spec — producing more discriminating model benchmarks than general Python coding tasks.

## Current Behavior

`ll:create-eval-from-issues` generates general coding evaluation tasks. `ll-harness` runs these tasks but has no DSL-specific mode. Neither tool can generate or evaluate tasks targeting ll's own YAML/frontmatter DSLs (loop transitions, FSM routing tables, issue frontmatter schemas).

## Expected Behavior

`ll:create-eval-from-issues --dsl <loop-yaml>` accepts a loop YAML or issue file and generates DSL-specific tasks (fill-in-the-blank FSM transitions, malformed frontmatter correction, state routing completion) stored under `evals/dsl/<source-name>/` with a metadata header indicating the source DSL. `ll-harness --dsl` runs these task sets and reports pass rates per model.

## Motivation

Standard Python coding tasks compress capability differences between models. Evaluating agent capability on ll's own YAML loop syntax, issue frontmatter, and FSM spec — low-ecosystem DSLs with no training-data saturation — produces more discriminating benchmarks. This directly improves the signal quality of ll-harness and ll-eval for choosing between models or loop designs.

## Proposed Solution

Extend `ll:create-eval-from-issues` to include a DSL task generation mode: given a loop YAML or issue file as a reference, generate a set of fill-in-the-blank and transform tasks (e.g., 'complete this FSM transition table', 'fix this malformed issue frontmatter') that exercise ll-specific syntax rather than general Python. Store the generated tasks under `evals/dsl/` with a metadata header indicating the source DSL. Add a `--dsl` flag to `ll-harness` to run these task sets and report pass rates by model.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Architecture note**: `ll:create-eval-from-issues` is a Markdown skill file (`skills/create-eval-from-issues/SKILL.md`) — instructions executed by the host agent, not a Python program. There is no Python implementation counterpart. The `--dsl` mode is added as new instruction branches in that skill file. `ll-harness` is a Python CLI (`scripts/little_loops/cli/harness.py`) and receives a new `dsl` subcommand via the existing `subparsers` dispatch pattern.

**Open question resolved — DSL task file format** (two concrete options based on codebase patterns):

**Option A: Reuse FSM loop YAML format** (`category: dsl-eval`)
- Task files are valid `FSMLoop` YAMLs stored in `evals/dsl/<source-name>/`; `execute` state contains the fill-in-the-blank prompt; `check_skill` uses `evaluate.type: llm_structured` or `evaluate.type: output_contains`
- Reuses `FSMLoop.from_dict()` (`scripts/little_loops/fsm/schema.py`), `ll-loop validate`, and all 13 evaluator types without new parsing infrastructure
- Downside: FSM overhead is heavy for simple fill-in-the-blank tasks; `max_iterations` and state machinery are extraneous

**Option B: New lightweight task YAML schema**
> **Selected:** Option B: New lightweight task YAML schema — follows exact subparser/dataclass/yaml.safe_load patterns already in harness.py with minimal new code and no FSM overhead.
- Task files use a minimal schema: `prompt:`, `blanks:` (list of field names to complete), `expected:` (ground-truth values), `source_dsl: loop|issue`, `task_type: fill-in-the-blank|transform|correction`, plus YAML frontmatter metadata
- `ll-harness dsl` loads these directly without FSM overhead via a small new dataclass
- More portable and simpler to generate from templates, but requires a new YAML parser (~30 lines) in `harness.py`

**Open question resolved — `ll-harness --dsl` task-discovery protocol**
- Add `subparsers.add_parser("dsl", ...)` in `_build_harness_parser()` following the existing `skill`/`cmd`/`mcp`/`prompt` subparser pattern
- `path` positional argument: single task file or directory (directory → glob `*.yaml`)
- Reuse `_add_evaluator_flags()` for shared `--exit-code`, `--semantic`, `--timeout`, `--output` criteria flags

**Open question resolved — Metadata header structure**
- YAML frontmatter block in each DSL task file:
  ```yaml
  source_dsl: loop|issue
  source_file: <relative-path-to-source>
  task_type: fill-in-the-blank|transform|correction
  generated_at: <ISO-8601-timestamp>
  ```

**Open question resolved — Evaluation scoring rubric**
- Exact-match tasks: compare output against `expected:` field; exit 0 = correct, exit 1 = wrong
- Semantic/transform tasks: `evaluate_llm_structured()` from `scripts/little_loops/fsm/evaluators.py`
- Per-model pass rates aggregated via `wilson_ci(k, n)` from `scripts/little_loops/stats.py`, formatted following the `_print_ab_summary()` table pattern in `scripts/little_loops/cli/loop/_helpers.py` (~line 1423)

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-11.

**Selected**: Option B: New lightweight task YAML schema

**Reasoning**: Option B follows every established pattern in `harness.py` exactly — the `_add_evaluator_flags`/subparser dispatch, the `@dataclass`+`from_dict`+`yaml.safe_load` loading pattern from `sprint.py`/`automation.py`, and `wilson_ci` from `stats.py` — requiring only a ~15-line dataclass, a ~35-line `cmd_dsl()`, and one `import yaml`. Option A introduces a cross-layer import (`harness.py` → `fsm.schema`) not currently present, has no minimal single-task loop template to copy, and would fire MR-4 partial-route validation warnings on every eval task file — genuine overhead for fill-in-the-blank tasks that only need `prompt:`/`blanks:`/`expected:` fields.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A: Reuse FSM loop YAML | 2/3 | 1/3 | 2/3 | 2/3 | 7/12 |
| Option B: New lightweight task YAML | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |

**Key evidence**:
- **Option A**: `FSMLoop.from_dict()` has 38 call sites and all 13 evaluator types are available, but `harness.py` has no import into `fsm.schema`; MR-4 partial-route warnings fire on minimal 2-state eval loops; `ll-loop run` requires full agent sessions per task.
- **Option B**: Subparser dispatch, `_add_evaluator_flags`, `@dataclass`+`from_dict`, `yaml.safe_load`, `wilson_ci`, and `TestParser` class are all exact-match patterns in `harness.py`, `sprint.py`, `automation.py`, `stats.py`, and `test_cli_harness.py` (reuse score 3/3).

## Implementation Steps

1. Add `--dsl` mode to `ll:create-eval-from-issues` that accepts a loop YAML or issue file as input
2. Implement DSL task templates: fill-in-the-blank FSM transitions, malformed frontmatter correction, state routing completion
3. Write generated tasks to `evals/dsl/<source-name>/` with source DSL metadata header
4. Add `--dsl` flag to `ll-harness` CLI to run DSL task sets
5. Report pass rates per model in `ll-harness` output when `--dsl` is active

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

1. **Add `--dsl` argument handling to `skills/create-eval-from-issues/SKILL.md`**: add an `$ARGUMENTS` parsing branch detecting `--dsl <source-file>` and routing to DSL task generation instructions; follow the existing `if [[ "$FLAGS" == *"--dsl"* ]]` shell guard pattern used by other skills
2. **Implement DSL task generation in the skill**: for loop YAML inputs, load via `ll-loop show -j <file>` to extract `states` and routing tables (JSON output includes full FSM config); for issue inputs, read frontmatter via `parse_frontmatter()` (`scripts/little_loops/frontmatter.py`); generate fill-in-the-blank YAML files to `evals/dsl/<source-name>/` using the task schema decided in Proposed Solution
3. **Add `dsl` subparser to `harness.py:_build_harness_parser()`**: `subparsers.add_parser("dsl", help="Run a DSL task set and report pass rates by model")` with `path` positional arg and `_add_evaluator_flags(dsl_p)`; follow the existing pattern at `_build_harness_parser()` lines ~80–130
4. **Implement `cmd_dsl()` in `harness.py`**: glob `*.yaml` task files from `args.path`; per file, construct a prompt from `prompt:` + `blanks:` fields, invoke `cmd_prompt`, collect pass/fail via `_evaluate_and_report()`; aggregate and print pass-rate table using `wilson_ci(k, n)` from `scripts/little_loops/stats.py`
5. **Add dispatch in `main_harness()`**: add `elif args.runner == "dsl": return cmd_dsl(args)` branch after existing runner branches
6. **Tests**: add `TestDslSubcommandParser` class in `scripts/tests/test_cli_harness.py`; use `scripts/tests/test_cross_host_baseline.py:TestCrossHostFlagParsed` as the structural template for flag-parsing tests

### Updated Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`cmd_dsl()` per-task invocation via `cmd_prompt`**: `cmd_prompt` (`harness.py:336`) reads `args.target` as the raw prompt string and calls `resolve_host().build_blocking_json(prompt=args.target, model=args.model)`. Invoke it per DSL task by constructing a synthetic `argparse.Namespace` — do not call the parser again:
```python
import argparse
task_args = argparse.Namespace(
    target=f"{task.prompt}\n\nBlanks to fill: {task.blanks}",
    exit_code=None,
    semantic=args.semantic,   # pass through from dsl subparser args
    timeout=args.timeout,
    output=args.output,
    verbose=args.verbose,
    model=args.model,          # pass through --model from dsl subparser
)
result_code = cmd_prompt(task_args)
```
This reuses `_evaluate_and_report()` through `cmd_prompt`'s internal call without any re-parsing.

**Pass-rate table must be built inline**: `_print_ab_summary()` (`_helpers.py:1422`) reads from `ab.json` and is only usable with the A/B run store — it is NOT directly callable for DSL pass-rate reporting. Build the per-task aggregate table inline using `wilson_ci`:
```python
from little_loops.stats import wilson_ci
lo, hi = wilson_ci(pass_count, total)
print(f"  pass-rate: {pass_count}/{total}  [{lo:.2f}, {hi:.2f}] (95% CI)")
```
Use `_print_ab_summary` only as a formatting reference (column widths, percentage display, verdict text).

**`_add_evaluator_flags()` is a nested function** inside `_build_harness_parser()` (`harness.py:55`), not a module-level helper. The DSL subparser registration (`subparsers.add_parser("dsl", ...)`) and `_add_evaluator_flags(dsl_p)` call must both happen inside `_build_harness_parser()`, just like the existing `skill`/`cmd`/`mcp`/`prompt` subparsers. `cmd_dsl()` itself (module-level) cannot call `_add_evaluator_flags` — it only receives the already-populated `args.Namespace`.

**`TestCrossHostFlagParsed` exact pattern**: stubs execution with `monkeypatch.setattr("little_loops.cli.loop.run.cmd_run", MagicMock(return_value=0))`, patches `sys.argv` via `patch.object(sys, "argv", [...])`, calls `main_loop()`, then asserts `mock_run.call_args[0][1].cross_host is True`. For DSL: stub `cmd_dsl`, patch `sys.argv = ["ll-harness", "dsl", str(task_path)]`, call `main_harness()`, assert `mock_dsl.call_args[0][0].path == str(task_path)`.

### Go/No-Go Blocker Resolutions (added by `/ll:refine-issue`)

_The two blockers from the No-Go verdict are resolved below with verified codebase findings._

**Blocker 1 (resolved): Use `ll-loop show -j` for state extraction, not `ll-loop validate -j`**

`ll-loop validate -j` exists (`scripts/little_loops/cli/loop/__init__.py:271`) but its JSON output is `{loop, valid, violations}` only — no `states` or routing tables. For extracting FSM states and routing tables for fill-in-the-blank task generation, use `ll-loop show -j <loop>` instead, which outputs the full FSM config:
```json
{"name": "...", "initial": "...", "states": {"<state>": {"action": "...", "action_type": "...", "evaluate": {...}, "on_yes": "...", "on_no": "...", "route": {...}}}, "description": "...", "max_iterations": N}
```
For Python code in `cmd_dsl()` that needs the fully expanded config (with `from:` inheritance, `flow:` shorthands, and `fragments:` applied), call `load_and_validate(path, raise_on_error=False)` from `scripts/little_loops/fsm/validation.py` directly — it returns `(FSMLoop, list[ValidationError])` and the `FSMLoop.states` dict has all state objects post-expansion.

**Correction to implementation step 2**: replace "load via `ll-loop validate --json <file>` to extract `states` and routing tables" with "load via `ll-loop show -j <file>` to extract `states` and routing tables (CLI), or call `load_and_validate(path, raise_on_error=False)` directly (Python)".

**Blocker 2 (resolved): `--model` flag exists on `prompt` subparser; mirror on `dsl`**

`--model` was added to the `prompt_p` subparser in commit `947179ba` (`harness.py:133-138`); `cmd_prompt` passes it as `resolve_host().build_blocking_json(prompt=args.target, model=args.model)`. Add identical `--model` to `dsl_p` and pass it through the synthetic `task_args.model` to `cmd_prompt`:
```python
dsl_p.add_argument("path", help="DSL task file or directory")
dsl_p.add_argument(
    "--model",
    default=None,
    metavar="MODEL",
    help="Override Claude model (e.g. claude-haiku-4-5-20251001)",
)
_add_evaluator_flags(dsl_p)
```
"Pass rates by model" = per-invocation (`ll-harness dsl <path> --model <model-id>` once per model to compare). Multi-model comparison in a single run is out of scope.

## Integration Map

### Files to Modify

- `skills/create-eval-from-issues/SKILL.md` — add `--dsl <source-file>` argument parsing branch and DSL task generation instructions (skill is Markdown, no separate Python implementation)
- `scripts/little_loops/cli/harness.py` — add `subparsers.add_parser("dsl", ...)` in `_build_harness_parser()` and implement `cmd_dsl()` following the `cmd_skill` / `cmd_cmd` dispatch pattern; add `elif args.runner == "dsl": return cmd_dsl(args)` in `main_harness()`

### New Files to Create

- `evals/dsl/` — new top-level directory for DSL task files (does not currently exist)
- `scripts/tests/test_dsl_eval.py` — new test file for DSL task generation and `ll-harness dsl` execution

### Reusable Modules (No Modification)

- `scripts/little_loops/fsm/schema.py` — `FSMLoop.from_dict()`, `StateConfig`, `EvaluateConfig`, `RouteConfig` — DSL schema reference for fill-in-the-blank content generation
- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for loop YAML validation (reference for malformed-YAML correction tasks)
- `scripts/little_loops/issue_parser.py` — `IssueParser.parse_file()` and `IssueInfo` — issue frontmatter field catalog for correction task generation
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter()`, `STATUS_SYNONYMS` — identifies common malformation patterns (deprecated field names, wrong status values)
- `scripts/little_loops/stats.py` — `wilson_ci(k, n)` — per-model pass rate confidence intervals
- `scripts/little_loops/cli/loop/_helpers.py` (~line 1423) — `_print_ab_summary()` — pass-rate table formatting pattern to follow

### Dependent Files (Callers/Importers)

- `scripts/little_loops/cli/harness.py:main_harness()` — entry point; dispatches to all runner subcommands; `dsl` adds a new branch
- `scripts/little_loops/cli/harness.py:_add_evaluator_flags()` — shared helper for `--exit-code`, `--semantic`, `--timeout`, `--output`; reuse for `dsl` subparser

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/__init__.py` — imports `main_harness` and re-exports via `__all__`; module docstring on line 4 enumerates `(skill, cmd, mcp, prompt)` — stale once `dsl` is added; also registers `ll-harness` entry point via `pyproject.toml` pointing here

### Tests

- `scripts/tests/test_cli_harness.py` — extend with `TestDslSubcommandParser` class (follow `TestHarnessParser` / `TestParser` pattern calling `_parse_harness_args(["dsl", ...])`) and `TestCmdDsl` class using `_make_namespace(runner="dsl", path=...)` helper; add one method to `TestMainHarness` following `test_main_harness_cmd_pass` shape
- `scripts/tests/test_cross_host_baseline.py` — structural template for CLI flag-parsing end-to-end tests (stub `cmd_dsl`, patch `sys.argv`, assert `args.path`)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_eval_from_issues.py` — existing structural tests for skill artifact YAML; add a DSL task YAML structural fixture (inline `yaml.safe_load` pattern) asserting `source_dsl:`, `task_type:`, `prompt:`, `blanks:`, `expected:` fields are present in generated output
- `scripts/tests/test_cli_e2e.py` — contains `TestLlHarnessE2E` class (`@pytest.mark.integration`); add optional `test_dsl_task_passes` smoke test for `ll-harness dsl <task-file>` against a fixture task YAML on disk

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — `### ll-harness` Runners table enumerates `skill`, `cmd`, `mcp`, `prompt`; add `dsl` row and a `dsl` usage example
- `commands/help.md` — `ll-harness` description reads `"skill, cmd, mcp, or prompt"` — add `dsl` to enumeration
- `scripts/little_loops/cli/__init__.py` — module docstring line 4: `"(skill, cmd, mcp, prompt)"` — add `dsl`
- `scripts/little_loops/init/writers.py` — `_CLI_SECTION` constant string contains the same `(skill, cmd, mcp, prompt)` enumeration used when `ll-init` writes `CLAUDE.md` for new projects — add `dsl`
- `skills/init/SKILL.md` — two occurrences (lines 394, 430) of `ll-harness` description with the same enumeration — add `dsl` to both
- `.claude/CLAUDE.md` — `ll-harness` CLI Tools entry: `"(skill, cmd, mcp, prompt)"` — add `dsl`
- `docs/reference/COMMANDS.md` — `### /ll:create-eval-from-issues` section has no `--dsl` argument documented — add argument hint and DSL mode description

### Configuration

_Wiring pass added by `/ll:wire-issue`:_
- `.gitignore` — `evals/dsl/` directory does not exist yet and has no gitignore coverage; decide whether generated DSL task YAML files should be committed to the repo (likely yes, as reference evals) or ignored (generated artifacts); add an `evals/dsl/` entry or explicit positive `!evals/` pattern accordingly

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `docs/reference/CLI.md` — add `dsl` row to the `### ll-harness` Runners table and add a `dsl` usage example
8. Update `commands/help.md` — change `"skill, cmd, mcp, or prompt"` to include `dsl` in the `ll-harness` description line
9. Update `scripts/little_loops/cli/__init__.py` — change module docstring from `(skill, cmd, mcp, prompt)` to `(skill, cmd, mcp, prompt, dsl)`
10. Update `scripts/little_loops/init/writers.py` — change `_CLI_SECTION` constant to include `dsl` in the `ll-harness` runner enumeration (affects `ll-init` output for new projects)
11. Update `skills/init/SKILL.md` — change both occurrences (lines ~394, ~430) of the `ll-harness` runner enumeration
12. Update `.claude/CLAUDE.md` — change `ll-harness` CLI Tools entry runner enumeration
13. Decide `.gitignore` for `evals/dsl/` — add explicit entry before the directory is created (recommended: commit generated evals, so add `!evals/` positive pattern or no entry needed if `evals/` has no parent ignore rule)
14. Update `scripts/tests/test_create_eval_from_issues.py` — add a DSL task YAML structural fixture test asserting required fields
15. Update `docs/reference/COMMANDS.md` — add `--dsl` argument documentation to `### /ll:create-eval-from-issues` section

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-06-11_ — **NO-GO (REFINE)** → _Blockers resolved by `/ll:refine-issue` on 2026-06-11_

**Original deciding factor**: Two blockers were cited: (1) `ll-loop validate --json` does not exist; (2) `harness.py` has no `--model` flag.

**Blocker 1 (resolved)**: `ll-loop validate -j/--json` does exist (`loop/__init__.py:271`), but its JSON output is `{loop, valid, violations}` — not states/routing tables. **Fix**: implementation step 2 now uses `ll-loop show -j <file>` which outputs the full FSM config including `states`. See "Go/No-Go Blocker Resolutions" in the Updated Codebase Research Findings section.

**Blocker 2 (resolved)**: `--model` was added to the `prompt` subparser in commit `947179ba` (`harness.py:133-138`). **Fix**: `dsl_p` mirrors the identical `--model` argument; "pass rates by model" = per-invocation comparison (run `ll-harness dsl <path> --model <model-id>` once per model). Acceptance criterion 3 updated accordingly.

### Key Arguments For
- `cmd_dsl()` implementation is a mechanical application of existing patterns — `dsl` subparser mirrors `prompt` in `harness.py:32–141`, `DslTask` mirrors `RunnerResult` at line 21, `wilson_ci` already in `stats.py`; changes are purely additive.
- Three of six EPIC-2087 siblings are `done`; foundational infrastructure (Wilson CI, `evals/` convention) is in place.

### Key Arguments Against (previously; now resolved)
- ~~`ll-harness` has no `--model` flag~~ — `--model` exists on `prompt_p`; `dsl_p` mirrors it.
- ~~Implementation step 2 references `ll-loop validate --json <file>` which does not exist~~ — corrected to `ll-loop show -j <file>`.

### Rationale
Both blockers are resolved with verified codebase findings. The core feature concept and Option B schema decision remain valid. Issue is now implementation-ready.

## Acceptance Criteria

- [ ] `ll:create-eval-from-issues --dsl <loop-yaml>` generates DSL-specific tasks in `evals/dsl/`
- [ ] Generated tasks include fill-in-the-blank and transform variants for ll YAML/frontmatter syntax
- [ ] `ll-harness dsl <path>` runs the task set and reports a pass rate with Wilson CI; `--model <model-id>` overrides the model for cross-model comparison via separate invocations
- [ ] Task files include metadata header with source DSL reference

## Scope Boundaries

- Out of scope: changes to existing general Python evaluation modes (unchanged behavior)
- Out of scope: automated ML training or fine-tuning of models based on task results
- Out of scope: task quality validation beyond the metadata header written at generation time
- Out of scope: multi-DSL cross-format tasks (e.g. mixing loop YAML and issue frontmatter in one task) in this iteration

## Impact

- **Priority**: P3 — improves benchmark discriminability for model/loop selection; non-urgent
- **Effort**: Medium — new CLI flags on two tools, DSL task template engine, `evals/dsl/` storage convention
- **Risk**: Low — purely additive; no changes to existing evaluation paths or harness output format
- **Breaking Change**: No

## Labels

`enhancement`, `eval`, `harness`, `dsl`, `captured`

## Status

**Open** | Created: 2026-06-10 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-10; updated 2026-06-10_

**Readiness Score**: 88/100 → PROCEED
**Outcome Confidence**: 65/100 → LOW

### Concerns
- Missing Integration Map / Files to Modify section

### Outcome Risk Factors
- **Open question: DSL task file format** — the issue does not specify the schema/fields for fill-in-the-blank FSM task files or expected response format. This is an open decision that needs to be resolved before writing the task template engine.
- **Open question: `ll-harness --dsl` task-discovery protocol** — the issue does not specify how `ll-harness --dsl` locates tasks (directory scan vs. explicit path argument) or what evaluation criteria it applies to DSL task outputs.
- **Open question: metadata header structure** — "metadata header indicating the source DSL" is mentioned but the format is unspecified (YAML frontmatter? JSON? inline comment?).
- **Open question: evaluation scoring** — "report pass rates per model" is stated but the grading rubric (exact match, partial match, semantic judge?) is not defined.

## Resolution

- Added `dsl` subparser to `ll-harness` (`scripts/little_loops/cli/harness.py`) with `DslTask` dataclass and `cmd_dsl()` implementing Option B lightweight YAML schema
- Added `--dsl <source-file>` mode to `ll:create-eval-from-issues` skill (`skills/create-eval-from-issues/SKILL.md`) for generating fill-in-the-blank/transform/correction tasks under `evals/dsl/<source-name>/`
- Created `evals/dsl/` directory as the storage root for generated DSL task files
- Updated all documentation: `docs/reference/CLI.md`, `commands/help.md`, `scripts/little_loops/cli/__init__.py`, `scripts/little_loops/init/writers.py`, `skills/init/SKILL.md`, `.claude/CLAUDE.md`, `docs/reference/COMMANDS.md`
- Added 16 tests in `test_cli_harness.py` (`TestDslSubcommandParser`, `TestCmdDsl`, dispatch test) and 13 DSL structural tests in `test_create_eval_from_issues.py`
- All 171 targeted tests pass; lint and mypy clean

## Session Log
- `/ll:ready-issue` - 2026-06-11T19:52:16 - `2a361b86-3249-43d1-bbe6-7e28464dba59.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `f33ba808-6bac-42a7-bedf-708478379450.jsonl`
- `/ll:refine-issue` - 2026-06-11T19:07:05 - `6629f98d-c43f-4ffa-bfee-4e29baead61f.jsonl`
- `/ll:go-no-go` - 2026-06-11T00:00:00Z - `b95b2d03-efb8-4e85-96bb-84acda74afc4.jsonl`
- `/ll:confidence-check` - 2026-06-11T14:00:00Z - `3b0e3fbc-1efe-4adb-997b-120bb2f1792a.jsonl`
- `/ll:refine-issue` - 2026-06-11T13:47:01 - `4db5f025-34a9-4096-91e0-fde7dc7d687f.jsonl`
- `/ll:decide-issue` - 2026-06-11T13:32:44 - `de7ca28e-3c08-484c-89ab-7b3895f18e53.jsonl`
- `/ll:refine-issue` - 2026-06-11T13:23:01 - `ba45a1bf-287b-4f54-a6e0-d925861be5b8.jsonl`
- `/ll:decide-issue` - 2026-06-11T03:47:32 - `26bee10d-f173-4904-92ec-7625750a7371.jsonl`
- `/ll:confidence-check` - 2026-06-10T00:00:00Z - `7c955a46-8e58-4db5-98b5-f8965296ecab.jsonl`
- `/ll:confidence-check` - 2026-06-11T00:00:00Z - `4a059ba1-7741-429c-acd5-bbaa7aeb09dc.jsonl`
- `/ll:decide-issue` - 2026-06-11T03:22:56 - `d894c9c1-6275-4e3c-8327-c75215a32cb0.jsonl`
- `/ll:format-issue` - 2026-06-10T23:31:13 - `714a8869-591f-4a9c-91ec-045042d7d120.jsonl`
- `/ll:confidence-check` - 2026-06-10T23:45:00Z - `7a3f7d68-548f-4c2a-bce7-6414775a985c.jsonl`
- `/ll:wire-issue` - 2026-06-11T13:41:49 - `fffefcf7-6dbd-438c-bdd1-259bea8d77b7.jsonl`
