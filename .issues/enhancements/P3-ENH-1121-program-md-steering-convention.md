---
discovered_date: "2026-04-16"
discovered_by: capture-issue
source: ~/.claude/plans/review-this-open-source-cosmic-galaxy.md
confidence_score: 98
outcome_confidence: 90
score_complexity: 18
score_test_coverage: 25
score_ambiguity: 22
score_change_surface: 25
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
- TBD — `grep -r "ll-loop run" docs/` to find doc references needing updates

### Similar Patterns
- Existing context-merge and arg-parsing logic in `scripts/little_loops/cli/loop/__init__.py`

### Tests
- `scripts/tests/test_ll_loop_program_md.py` — unit tests: file present + parsed, file absent + graceful fallback, CLI override wins (note: no `scripts/tests/cli/` subdir exists; all tests live directly in `scripts/tests/`)

### Documentation
- `docs/reference/program-md.md` — new convention doc (create from scratch)
- `commands/help.md` — mention `program.md` for loops that support it

_Wiring pass added by `/ll:wire-issue`:_
- `docs/guides/LOOPS_GUIDE.md:1877-1894` — Run Flags table: add `--program-md PATH` row and precedence note vs `--context` [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:669` — `harness-optimize` table entry: expand or cross-reference new `program.md` invocation pattern [Agent 2 finding]
- `docs/guides/LOOPS_GUIDE.md:1728` — Add `harness-optimize` subsection in Harness Loops section documenting `program.md` usage and precedence chain [Agent 2 finding]

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

Open
