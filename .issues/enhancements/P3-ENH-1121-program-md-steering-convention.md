---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
confidence_score: 100
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 18
decision_needed: false
completed_at: 2026-04-25T18:30:57Z
status: done
---

# ENH-1121: `.ll/program.md` Steering Convention for Long-Horizon Loop Runs

## Summary

Adopt a single canonical human-authored steering file — `.ll/program.md` — as the directive input for long-horizon, unattended loop runs (initially `harness-optimize`, FEAT-1120). Running `ll-loop run harness-optimize` with no args reads `.ll/program.md` and kicks off. Existing workflows are untouched; the file is optional.

## Current Behavior

Steering for long-horizon loop runs is scattered across multiple surfaces: `CLAUDE.md`, `.ll/ll-config.json`, issue files, and per-invocation CLI args. There is no single file a user can edit to declare "here's what to optimize, here are the targets, here is the budget, here are the constraints." Users starting an overnight harness-optimization run must assemble configuration from multiple channels — making runs hard to set up, impossible to replay exactly, and inaccessible without memorizing the CLI flag surface.

## Motivation

This enhancement would:
- Give long-horizon runs a single, obvious steering surface. The user edits one file instead of threading args through the CLI.
- Make overnight runs replayable — `program.md` is the durable record of what the run was *told* to do, not just what flags it received.
- Lower the effort ceiling for harness-optimize and any future long-horizon loops: typing `ll-loop run harness-optimize` should Just Work if the user has populated `.ll/program.md`.

## Expected Behavior

- `.ll/program.md` is a markdown file with a conventional (but not rigid) structure:
  - **Directive** — free-form prose of what to optimize and why
  - **Targets** — file paths / globs the loop may mutate
  - **Benchmark** — task directory and scorer to use
  - **Budget** — wall-clock / $ / token cap (pairs with long-horizon run UX if that ships later)
  - **Constraints** — free-form guardrails (e.g., "don't touch CLAUDE.md section between `<!-- frozen -->` markers")
- `ll-loop run harness-optimize` with no args reads `.ll/program.md`. CLI args override file values when both are present.
- Absent `.ll/program.md`, the command prints a helpful message pointing at a scaffold command (or a doc link) and exits non-zero.
- The file is optional and specific to loops that opt into it. No existing loop's behavior changes.

## Use Case

**Who**: Power user kicking off an overnight harness-optimization run

**Context**: Wants to walk away for 8+ hours and come back to a branch of accepted mutations

**Goal**: Edit `.ll/program.md` once, run `ll-loop run harness-optimize`, close the laptop

**Outcome**: The loop reads the directive, uses the declared targets/benchmark/budget, and produces an auditable trajectory keyed to a single durable input file

## Scope Boundaries

- **In scope**: `ll-loop run <name>` loading `.ll/program.md` when present; `harness-optimize` (FEAT-1120) as the first consumer loop; `docs/reference/program-md.md` convention documentation; optional scaffold via `ll-init` or a new `/ll:init-program` command
- **Out of scope**: Replacing or deprecating `CLAUDE.md`, `ll-config.json`, or issue files; enforcing a strict schema on `program.md` (convention over spec — formalize only if drift shows up); migration tooling for existing CLI-arg-based invocations; non-loop commands reading `program.md`; any GUI or editor integration for the file

## Proposed Solution

### `scripts/little_loops/cli/loop/__init__.py`

- When `ll-loop run <name>` is called with no args (or with `--program-md`), check for `.ll/program.md`. If present, parse and merge into the loop's initial context.
- Precedence: CLI args > `program.md` > loop defaults.
- Parsing can be pragmatic (find known section headings, extract code-fenced blocks for path lists). No schema required yet — the convention emerges; formalize only if drift shows up.

### `scripts/little_loops/loops/harness-optimize.yaml` (FEAT-1120)

First consumer. `load_directive` state reads `.ll/program.md` via the CLI-provided context.

### Documentation

- `docs/reference/program-md.md` — the convention, recommended sections, examples
- `/ll:help` — mention the file for relevant loops
- Optional scaffold: `ll-init` or a new `/ll:init-program` command can seed a starter `.ll/program.md`

## API/Interface

```python
# ll-loop run CLI — reads .ll/program.md by default when no conflicting args are given
ll-loop run <name>                     # reads .ll/program.md if present
ll-loop run <name> --program-md PATH   # explicit path override

# Precedence (higher wins):
# 1. Explicit CLI args (--directive, --targets, --benchmark, --budget)
# 2. .ll/program.md parsed sections
# 3. Loop YAML defaults
```

`program.md` parsed structure (heading-based, no schema enforcement):

```markdown
## Directive
[free-form prose describing what to optimize and why]

## Targets
- path/or/glob

## Benchmark
task_dir: evals/
scorer: pass_rate

## Budget
wall_clock: 8h
```

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/__init__.py` — add `--program-md` flag and heading-based parser
- `scripts/little_loops/loops/harness-optimize.yaml` — extend existing `load_directive` state to read `.ll/program.md` and populate context (state already exists as initial state; currently reads trajectory only)
- `scripts/little_loops/cli/loop/run.py` — consume `args.program_md` in the context injection pipeline (lines 62-81): parse `.ll/program.md` and merge fields into `fsm.context` before the existing `--context KEY=VALUE` loop; `__init__.py` declares the flag but `run.py` is where context is actually applied [Wiring pass]

### Dependent Files (Callers/Importers)

_Wiring pass added by `/ll:wire-issue` (pass 2):_
- `scripts/little_loops/cli/loop/_helpers.py:230-266` — `run_background()` reconstructs CLI argv per-flag (not reflectively); must explicitly forward `--program-md PATH` in the cmd list construction or background-mode invocations of `harness-optimize` silently drop `program.md` [Agent 1 + Agent 2 finding]

### Similar Patterns
- Existing context-merge and arg-parsing logic in `scripts/little_loops/cli/loop/__init__.py`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Heading-based section extraction (the parser to model after):**
- `scripts/little_loops/issue_history/doc_synthesis.py:104-127` — `_extract_section(content, heading)` uses `rf"^##\s+{re.escape(heading)}\s*$"` with `re.MULTILINE`, then scans forward for the next `^## ` to bound the section. Returns `""` on miss. Handles multi-word headings correctly (e.g., `## Directive`, `## Benchmark`). This is the exact pattern the `program.md` heading parser should replicate.
- `scripts/little_loops/output_parsing.py:118-146` — `parse_sections()` is an alternative (line-scan, all sections at once, uppercase keys) but uses `\w+` regex so multi-word headings would not match. Prefer `_extract_section`'s per-heading approach.
- `scripts/little_loops/issue_parser.py:598-634` — `_parse_section_items()` uses the identical `## heading` regex pattern with `re.IGNORECASE` added; confirms the approach.

**`--program-md` flag declaration insertion point:**
- `scripts/little_loops/cli/loop/__init__.py:147-152` — `--context action="append"` block; add `--program-md type=Path, default=None` immediately after (line 153 area), following the same inline `run_parser.add_argument(...)` pattern. The `args` namespace flows to `cmd_run` at line 368.
- `scripts/little_loops/cli_args.py:35-43` — `add_config_arg()` helper shows the `type=Path, default=None` flag pattern if a shared helper is preferred.

**Exact injection point in run.py:**
- `scripts/little_loops/cli/loop/run.py:76-77` — insert `program.md` context merge between line 76 (end of positional input stage) and line 77 (start of `--context KEY=VALUE` loop). The `--context` loop at 77-81 is last-write-wins, so any `program.md` values it may override will be correctly superseded.

**`load_directive` → `propose` wiring detail:**
- `scripts/little_loops/loops/harness-optimize.yaml:24-34` — `load_directive` state: `action` shell script echoes `"ready"` and captures it as `captured.directive` (line 33). Needs replacing the echo with `.ll/program.md` parsing that populates `context.targets`, `context.tasks_dir`, `context.scorer`, and echoes the `## Directive` prose.
- `scripts/little_loops/loops/harness-optimize.yaml:53-64` — `propose` state action: currently references `${context.targets}`, `${captured.baseline.output}`, `${captured.benchmark_score.output}`. Add `${captured.directive.output}` as a leading context line (e.g., `Optimization directive: ${captured.directive.output}`).

**"file-if-present" utility pattern:**
- `scripts/little_loops/subprocess_utils.py:47-59` — `read_continuation_prompt()` is the canonical pattern: `path.exists()` guard, `path.read_text()`, returns `None` on miss.
- `scripts/little_loops/goals_parser.py:92-109` — `ProductGoals.from_file()` adds an `OSError` catch around `read_text` for robustness; follow this for `program.md` loading.

**Test files to model after:**
- `scripts/tests/test_ll_loop_parsing.py:183-199` — `--context` flag parsing tests with `_create_run_parser()` helper that builds a standalone `ArgumentParser` mirroring the real subparser. Use this pattern for `--program-md` flag tests.
- `scripts/tests/test_goals_parser.py:136-166` — `test_from_file_missing` / `test_from_file_missing_frontmatter` patterns for file-absent + graceful fallback tests.
- `scripts/tests/test_cli_loop_lifecycle.py:417-441` — `test_context_overrides_applied_to_fsm` patches `load_loop` returning a `MagicMock` with real `dict` for `context`, then asserts `fsm.context["key"] == value`. Follow this for program.md → context merge tests.
- `scripts/tests/test_ll_loop_commands.py:2068-2144` — `TestCmdRunContextInjection` class for CLI-level run command context injection tests.

### Tests
- `scripts/tests/test_ll_loop_program_md.py` — unit tests: file present + parsed, file absent + graceful fallback, CLI override wins (note: no `scripts/tests/cli/` subdir exists; all tests live directly in `scripts/tests/`)

_Wiring pass added by `/ll:wire-issue` (pass 2):_

Tests requiring updates when `--program-md` is added to the run subparser:
- `scripts/tests/test_ll_loop_parsing.py:26-41` — `_create_run_parser()` standalone parser helper; add `parser.add_argument("--program-md", type=Path, default=None)` to match the real subparser [update needed]
- `scripts/tests/test_cli_loop_lifecycle.py:683-704` and `:770-791` — two `_make_args` helpers construct `argparse.Namespace` without `program_md`; add `program_md=None` to both [update needed]
- `scripts/tests/test_cli_loop_worktree.py:543-563` — `_make_args` helper missing `program_md=None` [update needed]
- `scripts/tests/test_ll_loop_commands.py:2120-2135` — inline `argparse.Namespace` construction missing `program_md=None` [update needed]
- `scripts/tests/test_harness_optimize.py:50-59` — `test_context_defaults` does not pin new YAML context keys; if a `directive: ""` key is added to the YAML `context:` block, this test won't verify it [gap — confirm coverage when implementing]
- `scripts/tests/test_cli_loop_background.py` — no existing test asserts `--program-md` is forwarded through `run_background()`; add a forwarding test [new test needed]

### Documentation
- `docs/reference/program-md.md` — new convention doc (create from scratch)
- `commands/help.md` — mention `program.md` for loops that support it

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1877-1894` — Run Flags table: add `--program-md PATH` row and precedence note vs `--context` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:669` — `harness-optimize` table entry: expand or cross-reference new `program.md` invocation pattern [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:1728` — Add `harness-optimize` subsection in Harness Loops section documenting `program.md` usage and precedence chain [Agent 2 finding]

_Wiring pass added by `/ll:wire-issue` (pass 2):_
- `docs/reference/loops.md:17-31` — `harness-optimize` invocation examples show `--context` flag only; add `program.md` invocation pattern [update needed]
- `docs/reference/loops.md:46` — `load_directive` state description describes pre-ENH-1121 behavior (reads trajectory only); update to reflect `program.md` reading [update needed]
- `docs/reference/loops.md:71-73` — Resume Behavior section describes stale `load_directive` behavior that will change [update needed]
- `docs/reference/CLI.md:296-320` — `ll-loop run` flags table (separate from LOOPS_GUIDE.md) missing `--program-md PATH` row [update needed]

### Configuration
- N/A — `.ll/program.md` is user-authored input, not a configuration file

## Implementation Steps

1. Add `--program-md` flag and heading-based parser to `scripts/little_loops/cli/loop/__init__.py`
2. Implement precedence chain: CLI args > `program.md` > loop defaults in the context merge
3. Extend the existing `load_directive` state in `scripts/little_loops/loops/harness-optimize.yaml` to parse `.ll/program.md` and populate `context.targets`, `context.tasks_dir`, and `context.scorer` (state already exists as the initial state; currently only reads the trajectory file). Capture the free-form Directive prose as `captured.directive.output` (currently the state echoes `"ready"`, making the capture inert).
4. Wire `${captured.directive.output}` into the `propose` state's LLM prompt so the free-form directive is visible to the model when it selects and proposes edits. Without this, Targets/Benchmark/Budget feed context variables but the Directive prose goes nowhere.
5. Write `docs/reference/program-md.md` — convention, recommended sections, worked example
6. Unit-test: file present + parsed, file absent + graceful fallback, CLI override wins
7. Run regression suite (`python -m pytest scripts/tests/`) to confirm no existing loop regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. Update `scripts/little_loops/cli/loop/run.py` (lines 62-81) — consume `args.program_md` in the context injection pipeline: parse `.ll/program.md` and merge parsed fields into `fsm.context` **before** the existing `--context KEY=VALUE` loop at line 77. This is the actual injection point; `__init__.py` only declares the flag and parser.
9. Update `docs/guides/LOOPS_GUIDE.md` — (a) add `--program-md PATH` row to the Run Flags table (lines 1877-1894) with precedence note vs `--context`; (b) expand the `harness-optimize` table entry (line 669) with a cross-reference to `program.md`; (c) add a `harness-optimize` + `program.md` usage subsection in the Harness Loops section (around line 1728)
10. Update `scripts/little_loops/cli/loop/_helpers.py` (lines 230-266) — add explicit `--program-md PATH` forwarding in `run_background()`'s per-flag cmd list construction. Without this, background-mode invocations silently drop `program.md` (the forwarding block is explicit per-flag, not reflective).
11. Update test namespace helpers: add `program_md=None` to `_make_args` in `test_cli_loop_lifecycle.py` (×2, lines 683-704 and 770-791), `test_cli_loop_worktree.py` (lines 543-563), and inline `Namespace` in `test_ll_loop_commands.py` (lines 2120-2135); add `--program-md` argument to `_create_run_parser()` in `test_ll_loop_parsing.py` (lines 26-41)
12. Add `--program-md` background forwarding test to `scripts/tests/test_cli_loop_background.py` — verify `run_background` includes `--program-md PATH` in the reconstructed argv when `args.program_md` is set
13. Update `docs/reference/loops.md` — invocation examples (lines 17-31), `load_directive` state description (line 46), and Resume Behavior section (lines 71-73) to reflect ENH-1121 behavior
14. Update `docs/reference/CLI.md` (lines 296-320) — add `--program-md PATH` row to the `ll-loop run` flags table (structurally parallel to LOOPS_GUIDE.md Run Flags table but a separate file)

## Related Key Documentation

| Document | Relevance |
|---|---|
| `.claude/CLAUDE.md` | Current steering surface — program.md does not replace it, it complements it for loop runs |
| `.ll/ll-config.json` | Machine config — orthogonal to program.md (which is prose directive) |
| `docs/ARCHITECTURE.md` | FSM loop execution, context propagation |

## Acceptance Criteria

- [ ] `ll-loop run <name>` reads `.ll/program.md` when present and merges parsed fields into loop context
- [ ] CLI args override file values; absent file is not an error for loops that don't require it
- [ ] `harness-optimize` (FEAT-1120) consumes the file's Directive/Targets/Benchmark fields
- [ ] `docs/reference/program-md.md` documents the convention with a worked example
- [ ] Unit test covers: file present + parsed, file absent + graceful fallback, CLI override wins
- [ ] No regression: existing loops unaffected (`python -m pytest scripts/tests/`)

## Dependencies

Related: FEAT-1120 (harness-optimize loop) — first consumer. This enhancement is useful but not required for FEAT-1120 to ship; it can land alongside or shortly after.

## Impact

- **Priority**: P3 — Usability enhancement for power users; not blocking core workflows; can land alongside or shortly after FEAT-1120
- **Effort**: Medium — New CLI parsing logic, context merge, one new loop YAML state, and a reference doc; no schema enforcement keeps scope contained
- **Risk**: Low — File is optional; absent file is not an error; no changes to existing loop execution paths or YAML schemas
- **Breaking Change**: No — existing `ll-loop run` invocations with explicit CLI args are unaffected

## Labels

`enhancement`, `captured`

## Go/No-Go Findings

_Added by `/ll:go-no-go` on 2026-04-25_ — ~~**NO-GO (SKIP)**~~ **GO** _(revised 2026-04-25)_

**Original Deciding Factor**: The `captured.directive` output in `harness-optimize.yaml:26-34` is never consumed by any downstream state — no state references `${captured.directive.output}` — meaning the Directive section of `program.md` would be loaded and immediately discarded.

**Revision**: The wiring gap is not a blocker; it is a missing implementation step. Wiring `${captured.directive.output}` into the `propose` prompt is a single-line change in the same file and is inseparable from the `program.md` parsing work. It has been added explicitly as step 4 in Implementation Steps above. The original no-go concern is now fully addressed within ENH-1121's scope — no separate prerequisite issue is needed.

### Key Arguments For
- All context-injection infrastructure already exists in `run.py:62-81` and `frontmatter.py` — implementation is ~30-50 lines with a clear insertion point in the staged context pipeline
- FEAT-1120's completion notes explicitly named ENH-1121 as the intended next step; `load_directive` state was architecturally designed with `program.md` loading in mind
- The wiring (`load_directive` captures real prose → `propose` prompt includes it) is contained in one file and requires no new architecture

### Key Arguments Against
- `ll-loop install harness-optimize` + editing the `context:` block is documented at `docs/guides/LOOPS_GUIDE.md:270` as the existing durable-defaults path, solving the core UX problem today without new code

## Session Log
- `/ll:ready-issue` - 2026-04-25T18:14:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/096e08ad-573b-4e17-9674-d27d7d807c46.jsonl`
- `/ll:confidence-check` - 2026-04-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb86effc-6421-4dbf-b1a1-86368e1d4644.jsonl`
- `/ll:wire-issue` - 2026-04-25T18:09:23 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/435d237f-22dd-4664-8fe2-215738a163f3.jsonl`
- `/ll:refine-issue` - 2026-04-25T18:02:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c63d5643-3cd6-4194-a8ec-e96b36f6f089.jsonl`
- `/ll:verify-issues` - 2026-04-25T17:54:43 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/008a2f03-f9f5-4084-b150-f39e97039172.jsonl`
- `/ll:wire-issue` - 2026-04-25T17:52:54 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/96749c6f-f17b-4d10-b158-4822f481e6b6.jsonl`
- `/ll:confidence-check` - 2026-04-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/71b43b70-5185-4ea0-abcc-f27ef3f5177c.jsonl`
- `/ll:go-no-go` - 2026-04-25T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c5791a1c-1f5c-4e4c-aa52-09e8dd7d510d.jsonl`
- `/ll:ready-issue` - 2026-04-25T17:26:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/587fda44-a2b8-4c66-9daa-c634f91dbf78.jsonl`
- `/ll:format-issue` - 2026-04-25T01:21:29 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4acbc6d5-2175-415e-8228-17ec102d80fe.jsonl`
- `/ll:verify-issues` - 2026-04-24T03:02:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1faa7404-23ae-4397-94a1-06150dae54dd.jsonl`
- `/ll:capture-issue` - 2026-04-16T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2fb1a4ee-5512-43ed-b858-2a21a4738fb8.jsonl`

---

## Verification Notes

**Verdict**: VALID — Verified 2026-04-25

- `scripts/little_loops/cli/loop/__init__.py` — no `--program-md` flag or `.ll/program.md` loading logic ✓
- `scripts/little_loops/cli/loop/run.py` — context injection pipeline at lines 62-81 (for kv loop at line 77) unchanged; no `program.md` merge ✓
- `scripts/little_loops/loops/harness-optimize.yaml` — `load_directive` state (line 24) reads trajectory only; `${captured.directive.output}` not wired into `propose` state ✓
- `docs/reference/program-md.md` — does not exist ✓
- `scripts/tests/test_ll_loop_program_md.py` — does not exist ✓
- LOOPS_GUIDE.md wiring touchpoints: Run Flags table (~line 1878), harness-optimize table entry (~line 670), Harness Loops section (~line 1730) — all exist, line numbers accurate within ±3 lines ✓
- Feature not yet implemented ✓

## Status

Completed

## Resolution

Implemented 2026-04-25 via `/ll:manage-issue enhancement implement ENH-1121`.

### Changes made

- `scripts/little_loops/cli/loop/__init__.py` — added `--program-md PATH` flag to `run` subparser
- `scripts/little_loops/cli/loop/run.py` — added `_parse_program_md()` helper and context merge (precedence: CLI args > program.md > YAML defaults)
- `scripts/little_loops/cli/loop/_helpers.py` — added `--program-md PATH` forwarding in `run_background()`
- `scripts/little_loops/loops/harness-optimize.yaml` — updated `load_directive` to extract `## Directive` section with awk; wired `${captured.directive.output}` into `propose` prompt
- `docs/reference/program-md.md` — created convention doc with section reference, precedence rules, worked example
- `docs/guides/LOOPS_GUIDE.md` — added `--program-md` to Run Flags table; added `harness-optimize` + `program.md` subsection; expanded `harness-optimize` table entry
- `docs/reference/loops.md` — updated invocation examples, state graph description, and Resume Behavior
- `docs/reference/CLI.md` — added `--program-md PATH` row to `ll-loop run` flags table
- `scripts/tests/test_ll_loop_program_md.py` — new test file (14 tests: parsing, graceful fallback, precedence, integration)
- `scripts/tests/test_cli_loop_background.py` — added forwarding/non-forwarding tests for `--program-md`
- Test namespace updates: added `program_md=None` to `_make_args` helpers in `test_cli_loop_lifecycle.py` (×2), `test_cli_loop_worktree.py`, `test_ll_loop_commands.py`; added `--program-md` to `_create_run_parser()` in `test_ll_loop_parsing.py`

### Acceptance criteria

- [x] `ll-loop run <name>` reads `.ll/program.md` when present and merges parsed fields into loop context
- [x] CLI args override file values; absent file is not an error for loops that don't require it
- [x] `harness-optimize` (FEAT-1120) consumes the file's Directive/Targets/Benchmark fields
- [x] `docs/reference/program-md.md` documents the convention with a worked example
- [x] Unit test covers: file present + parsed, file absent + graceful fallback, CLI override wins
- [x] No regression: existing loops unaffected (5318 passed, 5 skipped)

## Session Log
- `/ll:manage-issue` - 2026-04-25T18:30:57Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/096e08ad-573b-4e17-9674-d27d7d807c46.jsonl`
