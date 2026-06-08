---
id: FEAT-2024
type: FEAT
priority: P3
status: open
decision_needed: false
discovered_date: 2026-06-08
discovered_by: capture-issue
captured_at: '2026-06-08T18:32:45Z'
confidence_score: 80
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 25
---

# FEAT-2024: Add apply-research built-in FSM loop for synthesizing local research files into actionable issues

## Summary

Add a new built-in FSM loop `apply-research` that accepts one or more paths to local text, Markdown, or PDF files (e.g., research papers, design documents, RFCs), reads and understands the content, identifies what is relevant or applicable to the current project, synthesizes actionable recommendations, and captures Issues to implement those recommendations.

## Current Behavior

No built-in loop exists for ingesting local research artifacts and translating them into project issues. Users who read academic papers, design documents, or technical specs must manually:
1. Read and mentally parse the document
2. Identify which ideas or techniques are applicable to their project
3. Write up individual issue descriptions for each recommendation
4. Capture those issues via `/ll:capture-issue` one at a time

This is time-consuming, inconsistent, and incomplete — nuanced applicable content is often missed or under-captured.

## Expected Behavior

Users can run:

```bash
ll-loop run apply-research --files paper1.pdf paper2.md notes.txt
```

or via Claude Code:

```
/ll:create-loop apply-research
```

The loop:
1. Reads each file (supports `.txt`, `.md`, `.pdf`)
2. For each file, identifies what is relevant or applicable to the project context (reads `CLAUDE.md`, `.ll/ll-config.json`, recent open issues as context)
3. Synthesizes a ranked list of actionable recommendations
4. For each recommendation above a relevance threshold, captures a new Issue via `/ll:capture-issue` with the synthesized description
5. Produces a summary report of all captured issues, skipped recommendations, and reasoning

## Motivation

Research papers and technical documents often contain directly applicable ideas (algorithms, architecture patterns, evaluation strategies) that could significantly improve a project — but translating them into actionable work items requires significant manual effort. An FSM loop can automate this pipeline with structured evaluation steps: read → extract → filter-by-relevance → synthesize-description → capture.

This is particularly valuable for projects like little-loops itself, where AI alignment papers, eval methodology papers, and FSM research directly inform tooling design.

## Use Case

A developer reads a research paper on FSM evaluation strategies (e.g., a PDF from arXiv or an internal design doc) and wants to identify which ideas are applicable to little-loops. Rather than manually re-reading and writing up issue descriptions, they run:

```bash
ll-loop run apply-research --files paper.pdf notes.md
```

The loop reads each file, identifies relevant techniques (e.g., a new evaluator pattern, a loop termination heuristic), and automatically captures 2–4 issues with synthesized descriptions. The developer reviews the captured issues in `.issues/` and immediately proceeds to prioritize or implement them — no manual write-up required.

## Proposed Solution

Implement as an FSM loop YAML under `loops/apply-research.yaml` following the `diagnose → propose → apply → measure-externally` meta-loop shape (since it generates harness artifacts):

**States:**
1. `load_context` — read project context (CLAUDE.md, open issues, recent commits) to understand what's already known
2. `read_file` — read and chunk the target file; extract key claims, techniques, and ideas
3. `assess_relevance` — for each extracted item, score relevance to the project (0–1 scale) using structured LLM evaluation
4. `filter_items` — drop items below threshold (configurable, default 0.5); rank survivors by relevance × novelty
5. `synthesize_recommendations` — convert each surviving item into a structured issue description (title, type, motivation, proposed solution)
6. `capture_issues` — run `/ll:capture-issue` for each recommendation; collect resulting issue IDs
7. `next_file` — advance to the next input file or converge when all files processed
8. `report` — emit summary: files processed, items extracted, items filtered, issues captured (with IDs)

**Non-LLM evaluators** (required by MR-1):
- `exit_code` on `/ll:capture-issue` invocations (verifies issue was actually written)
- `output_numeric` on relevance scores (validates range 0–1 before filtering)
- `diff_stall` to detect when successive files produce zero new issues (convergence signal)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`apply-research` is NOT a meta-loop.** The Proposed Solution says "following the `diagnose → propose → apply → measure-externally` meta-loop shape (since it generates harness artifacts)" — but per CLAUDE.md, meta-loops are those that modify "loop YAMLs, skill files, agent definitions, commands, or CLAUDE.md itself." Issue files (`.issues/*.md`) are **not harness artifacts**. `apply-research` is a **research-category loop** (same as `deep-research`), not a meta-loop. The standard read → extract → filter → synthesize → capture pipeline shape is appropriate. The MR-1 non-LLM evaluator requirement still applies, but the `diagnose → propose → apply → measure-externally` scaffolding is not required.

**`diff_stall` is the wrong evaluator for "zero new issues."** `diff_stall` compares `git diff --stat` between iterations (detects working-tree changes), not issue capture counts. To detect when a file produces zero new issues, use `output_numeric` with `operator: eq` / `target: 0` on a shell state that counts newly captured issues. Or rely on the file-iteration loop completing naturally via the `next_file → done` transition without a stall detector.

## Integration Map

### Files to Modify
- `loops/apply-research.yaml` — new loop definition (primary artifact)
- `docs/reference/LOOPS.md` — add `apply-research` to built-in loop inventory
- `skills/create-loop/SKILL.md` — optionally add `apply-research` as an example in the "Harness a research paper" template branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loop_runner.py` — must support `--files` multi-value arg passthrough to the loop's `args` context
- `ll-loop` CLI — validate that `--files` args are accessible as `context.args.files` inside FSM states

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/validate.py` — `cmd_validate()` scans the loops directory and auto-exercises `apply-research.yaml` when created; no code changes needed, but this is the mechanism that enforces MR-1/MR-3/MR-4 compliance at CI time

### Similar Patterns
- `loops/deep-research.yaml` (FEAT-1540, done) — web research synthesis; similar FSM shape but input is web queries, not local files
- `loops/harness-optimize.yaml` — meta-loop that reads artifacts and generates harness changes; similar read→analyze→capture pattern

### Tests
- `scripts/tests/test_apply_research_loop.py` — validate FSM state transitions, relevance filtering threshold, exit-code evaluator wiring
- Add fixture PDFs/text files under `scripts/tests/fixtures/research/`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_parsing.py` — `TestLoopArgumentParsing`: if Option B (`--files` multi-value arg) is implemented, add parsing tests following the `test_context_flag_parses_key_value` pattern; not needed for Option A
- `scripts/tests/test_cli_loop_dispatch.py` — `TestMainLoopDispatch`: if Option B, add `test_files_forwarded` following `test_context_forwarded` (line 640) to confirm `--files` is forwarded to `cmd_run()`; not needed for Option A
- Note: `TestBuiltinLoopFiles.test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, and `test_all_have_description_field` use `rglob("*.yaml")` and will auto-run against `apply-research.yaml` with no changes needed

### Documentation
- `docs/guides/LOOP_AUTHORING_GUIDE.md` — add example of `apply-research` as a document-ingestion pattern
- `docs/reference/LOOPS.md` — inventory entry

### Configuration
- Add `apply_research.relevance_threshold` (default 0.5) to `config-schema.json`
- Add `apply_research.max_issues_per_file` (default 10) to prevent runaway capture on large documents

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Path corrections — all loop YAMLs live under `scripts/little_loops/loops/`, not `loops/`:**
- `scripts/little_loops/loops/apply-research.yaml` — new loop definition (corrected path)
- `docs/reference/loops.md` — built-in loop inventory (lowercase filename, not `LOOPS.md`)
- `docs/guides/LOOPS_GUIDE.md` — loop authoring guide (not `LOOP_AUTHORING_GUIDE.md`)
- `skills/create-loop/SKILL.md` — path confirmed correct

**`loop_runner.py` does not exist** — `scripts/little_loops/loop_runner.py` is not in the codebase. Correct files:
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`: CLI arg injection, `input_key` binding, `--context KEY=VALUE` parsing
- `scripts/little_loops/fsm/runners.py` — FSM core execution
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()`, `run` subparser with `--context` definition

**`context.args.files` and `--files` do not exist.** The `ll-loop run` CLI only has `--context KEY=VALUE` (no `--files` flag). The `context.args` nested namespace does not exist — context is a flat `dict[str, Any]`. The established convention for multi-value file inputs is a space-separated string in one context variable (e.g., `context.targets` in `harness-optimize.yaml`). Two viable approaches:
- **Option A (no CLI changes):** use `input_key: files` so `ll-loop run apply-research "paper1.pdf notes.md"` populates `context.files` as a space-separated string; shell states split with word expansion

> **Selected:** Option A (no CLI changes) — zero CLI changes, matches `input_key:` convention used by 27 existing loops

- **Option B (new CLI work):** add a `--files` flag to `scripts/little_loops/cli/loop/__init__.py` that populates `context.files` as a list — adds scope to Implementation Step 2

**Similar pattern paths (corrected):**
- `scripts/little_loops/loops/deep-research.yaml` — closest analog; `input_key: topic`, `init` shell state, oracle delegation via `loop: oracles/research-coverage`
- `scripts/little_loops/loops/harness-optimize.yaml` — space-separated `context.targets` for multi-path input

**`oracle-capture-issue.yaml` reuse opportunity:**
- `scripts/little_loops/loops/oracles/oracle-capture-issue.yaml` — existing oracle sub-loop wrapping `/ll:capture-issue` with mechanical+semantic evaluators; invocable via `loop: oracles/oracle-capture-issue` with `context_passthrough: true` instead of rolling custom capture logic

**Test file location — structural tests belong in `test_builtin_loops.py`, not a standalone file:**
- Add a `TestApplyResearchLoop` class to `scripts/tests/test_builtin_loops.py` (following `TestResearchCoverageOracle` pattern at line ~5627)
- Also add `"apply-research"` to the `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` at line 73; the test suite fails until this entry is added
- Shell-logic fixture files can still go in `scripts/tests/fixtures/research/`

**Config schema constraint:**
- `config-schema.json` has `"additionalProperties": false` on its `"loops"` block (line 863); no per-loop config sub-blocks exist anywhere in the schema
- To add `apply_research.*` config, add a new root-level `"apply_research"` property object (parallel to `"loops"`, `"project"`, etc.)
- **Simpler alternative:** declare defaults as context variables in the loop YAML (`relevance_threshold: 0.5`, `max_issues_per_file: 10`) and allow `--context relevance_threshold=0.7` override — no schema changes required

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-06-08.

**Selected**: Option A (no CLI changes)

**Reasoning**: Option A directly reuses the `input_key:` convention used by 27 existing loops with zero CLI changes. `hitl-compare.yaml` provides exact precedent for `input_key:` with whitespace-separated file paths, and `rn-build.yaml` demonstrates `input_key:` with multi-path shell iteration. Option B achieves a higher testability score (test scaffold fully in place) but adds scope across 4 files for functionality already coverable via `--context files=...`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (no CLI changes) | 3/3 | 3/3 | 2/3 | 2/3 | 10/12 |
| Option B (new CLI work) | 2/3 | 1/3 | 3/3 | 1/3 | 7/12 |

**Key evidence**:
- Option A: `input_key:` used by 27 loops; `hitl-compare.yaml` uses `input_key: inputs` for whitespace-separated file paths; `rn-build.yaml` uses `input_key: spec` with multi-path IFS-split iteration; zero CLI changes needed
- Option B: `action="append"` pattern matches existing CLI flags but adds scope to 4 files (`__init__.py`, `run.py`, two test files); `--context files=...` already covers the use case as a workaround

## Implementation Steps

1. Implement `loops/apply-research.yaml` with all 8 FSM states, non-LLM evaluators for MR-1 compliance, and `--files` args passthrough
2. Add `--files` multi-value arg support to `ll-loop run` CLI (if not already supported via `context.args`)
3. Add config schema entries for `apply_research.relevance_threshold` and `apply_research.max_issues_per_file`
4. Write test fixtures (sample research text snippets, not real papers) and unit tests for FSM transitions
5. Update `docs/reference/LOOPS.md` inventory
6. Run `ll-loop validate apply-research` to confirm MR-1/MR-3/MR-4 compliance

## API/Interface

```bash
# Single file
ll-loop run apply-research --files path/to/paper.pdf

# Multiple files
ll-loop run apply-research --files paper1.pdf notes.md rfc.txt

# With relevance threshold override
ll-loop run apply-research --files paper.pdf --arg relevance_threshold=0.7

# Via Claude Code
/ll:create-loop apply-research
```

## Acceptance Criteria

- Given one or more `--files` paths (`.txt`, `.md`, `.pdf`), the loop reads each file and extracts candidate recommendations
- Relevance scores are numeric values in range 0–1; items scoring below the configured threshold (default 0.5) are dropped and logged as "filtered"
- For each surviving recommendation, `/ll:capture-issue` is invoked and its exit code is checked (`exit_code` evaluator); a non-zero exit causes the loop to retry or surface an error — no silent swallow
- A summary report is emitted after all files are processed: files processed count, items extracted count, items filtered count, and list of captured issue IDs
- `ll-loop validate apply-research` exits 0 with no MR-1, MR-3, or MR-4 violations
- `context.args.files` is accessible inside FSM states when `--files` is passed to `ll-loop run`
- Config schema accepts `apply_research.relevance_threshold` (float, default 0.5) and `apply_research.max_issues_per_file` (int, default 10)
- Running with `max_issues_per_file=1` on a multi-recommendation document captures exactly 1 issue (cap enforced)

## Impact

- **Priority**: P3 - Valuable workflow automation; not blocking
- **Effort**: Medium — FSM loop YAML authoring + CLI arg passthrough + test fixtures (~1–2 days)
- **Risk**: Low — isolated new loop file; no changes to existing loops or core runner
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`loops`, `built-in-loop`, `research`, `automation`, `captured`

## Status

**Open** | Created: 2026-06-08 | Priority: P3

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-06-08_

**Readiness Score**: 80/100 → PROCEED WITH CAUTION
**Outcome Confidence**: 67/100 → MODERATE

### Concerns
- **AC#6 contradiction**: Acceptance criterion "context.args.files is accessible when --files is passed" references a non-existent CLI flag and contradicts the established `input_key`/positional arg convention. Either update AC#6 to reference `context.files` populated via `input_key: files` (Option A), or explicitly commit to Option B (new CLI flag) before starting.
- **oracle-capture-issue is a scoring oracle, not a creation oracle**: The integration map suggests reusing it "with context_passthrough: true instead of rolling custom capture logic" — this is wrong. The oracle evaluates existing captures via `invocation`/`output` bindings and returns a score; it cannot create issues. Disregard this reuse note; call `/ll:capture-issue` directly.
- **Impact section understates scope**: States "isolated new loop file; no changes to existing loops or core runner" but 7 files require changes: `README.md` FSM count (`79→80`), `CONTRIBUTING.md` YAML count (`76→77`), `loops/README.md` catalog row, `docs/reference/loops.md` entry, `docs/guides/LOOPS_GUIDE.md` table row. `ll-verify-docs` will fail CI until all count assertions are updated.

### Outcome Risk Factors
- **Open decision on input interface (Option A/B)**: Choosing Option B (dedicated `--files` CLI flag) expands scope to `scripts/little_loops/cli/loop/__init__.py` + `run.py` + test fixtures; Option A (`input_key: files` with space-separated positional arg) stays isolated and matches `harness-optimize`'s `context.targets` convention. Recommend deciding before implementation starts to avoid mid-flight scope expansion.
- **Seven required change sites vs stated three**: The `README.md` FSM count, `CONTRIBUTING.md` YAML count, `loops/README.md` catalog entry, `docs/reference/loops.md` full entry, and `docs/guides/LOOPS_GUIDE.md` table row are all required or CI fails. The issue's risk estimate of "Low — isolated new loop file" should be revised to reflect this broader surface.
- **oracle-capture-issue integration note is incorrect**: The refine-issue research recommended reusing the oracle for issue capture, but it is a rubric-scoring oracle (returns SCORE=0-100) incompatible with the creation use case. Following this note would result in a broken capture state.

## Session Log
- `/ll:decide-issue` - 2026-06-08T20:01:57 - `7ca27d70-ae36-4cb7-90a0-e6b796735d0c.jsonl`
- `/ll:confidence-check` - 2026-06-08T19:30:00 - `f85e77c0-412f-4a1e-932b-aeac2a4797f2.jsonl`
- `/ll:wire-issue` - 2026-06-08T18:58:14 - `d331825d-7e3c-457a-94d7-e13a9bf83a9d.jsonl`
- `/ll:refine-issue` - 2026-06-08T18:50:33 - `2a44cb62-9300-4369-8e0e-768735b76625.jsonl`
- `/ll:format-issue` - 2026-06-08T18:38:07 - `a728ce61-598a-41b4-88fb-5495fbc177b9.jsonl`
- `/ll:capture-issue` - 2026-06-08T18:32:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2487f4bf-03ad-45d6-b19b-7a8cbbb8e999.jsonl`
