---
id: FEAT-2024
type: FEAT
priority: P3
status: done
decision_needed: false
discovered_date: 2026-06-08
discovered_by: capture-issue
captured_at: '2026-06-08T18:32:45Z'
completed_at: '2026-06-08T21:05:03Z'
confidence_score: 90
outcome_confidence: 72
score_complexity: 15
score_test_coverage: 18
score_ambiguity: 17
score_change_surface: 22
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
ll-loop run apply-research "paper1.pdf paper2.md notes.txt"
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
ll-loop run apply-research "paper.pdf notes.md"
```

The loop reads each file, identifies relevant techniques (e.g., a new evaluator pattern, a loop termination heuristic), and automatically captures 2–4 issues with synthesized descriptions. The developer reviews the captured issues in `.issues/` and immediately proceeds to prioritize or implement them — no manual write-up required.

## Proposed Solution

Implement as an FSM loop YAML under `loops/apply-research.yaml` following the `diagnose → propose → apply → measure-externally` meta-loop shape (since it generates harness artifacts):

**States:**
1. `load_context` — read project context (CLAUDE.md, open issues, recent commits) to understand what's already known
2. `read_file` — read and chunk the target file; extract key claims, techniques, and ideas. **Mechanism**: if the file is a `.pdf`, a `shell` action first converts it to a `.md` sidecar using `pandoc "$file" -o "${file%.pdf}.md"` (requires `pandoc` ≥ 2.x on `PATH`); the resulting `.md` (or the original `.txt`/`.md`) is then read via `action_type: prompt` using Claude Code's `Read` tool. All content entering the extraction step is plain Markdown — no pagination handling required
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

**`capture_issues` state should use `action_type: prompt`** — `exit_code` evaluators cannot be placed directly on multi-call `/ll:capture-issue` invocations; each run may call the skill N times (once per surviving recommendation). Existing loops that invoke `/ll:capture-issue` (`rn-build.yaml` `capture_eval_failures`, `greenfield-builder.yaml` `create_feature_issues`, `eval-driven-development.yaml` `capture_failures`) consistently use `action_type: prompt` with explicit per-item instructions. For MR-1 compliance, add a separate `verify_captures` shell state after `capture_issues` that counts newly-created issue files under `.issues/` and uses `output_numeric` with `operator: ge` / `target: 1` to confirm at least one was written.

**`$${...}` escaping required in shell states using bash array syntax** — If using `read -ra FILE_LIST <<< "${context.files}"` for per-file iteration, array expansion must be written `"$${FILE_LIST[@]}"` (double `$`), not `"${FILE_LIST[@]}"`. The FSM interpolator resolves `${...}` first; unescaped references that don't match a context variable raise "expected namespace.path." See `rn-build.yaml` lines 68–78 for the exact pattern.

**Declare `required_inputs: ["files"]`** at loop top level alongside `input_key: files` to enforce a non-empty input at run time. Without it, `ll-loop run apply-research` with no argument uses the empty-string default silently. Pattern from `goal-cluster.yaml` and `canvas-sketch-generator.yaml`.

**Queue-based file iteration alternative** — If per-file processing is complex, the `init` → pop-one → `advance` queue pattern (used by `prompt-across-issues.yaml` and `harness-optimize.yaml` `dequeue_state`) is more robust and observable. The `next_file` state pops from a queue file under `${context.run_dir}/pending-files.txt` via `head -1` / `tail -n +2`. A simple `for F in $FILES; do` loop is sufficient for shallow lists.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/apply-research.yaml` — new loop definition (primary artifact)
- `docs/reference/loops.md` — add `apply-research` to built-in loop inventory
- `scripts/little_loops/loops/README.md` — add catalog entry row
- `skills/create-loop/SKILL.md` — optionally add `apply-research` as an example in the "Harness a research paper" template branch

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py` — `cmd_run()`: handles `input_key:` binding that populates `context.files` from the positional arg; no code changes needed for Option A
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()`: defines the `--context KEY=VALUE` flag used for `relevance_threshold` and `max_issues_per_file` overrides

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` scans the loops directory and auto-exercises `apply-research.yaml` when created; no code changes needed, but this is the mechanism that enforces MR-1/MR-3/MR-4 compliance at CI time

### Similar Patterns
- `scripts/little_loops/loops/deep-research.yaml` — web research synthesis; uses `input_key: topic`, delegates to oracle via `loop: oracles/research-coverage`; closest FSM analog
- `scripts/little_loops/loops/harness-optimize.yaml` — uses `context.targets` as space-separated file paths; demonstrates queue-drain multi-file iteration

### Tests
- `scripts/tests/test_builtin_loops.py` — add `"apply-research"` to `TestBuiltinLoopFiles.test_expected_loops_exist` (line 75); add `TestApplyResearchLoop` class following `TestResearchCoverageOracle` pattern (line 5627)
- Add sample text/md fixture files under `scripts/tests/fixtures/research/` (not real papers)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_ll_loop_parsing.py` — `TestLoopArgumentParsing`: if Option B (`--files` multi-value arg) is implemented, add parsing tests following the `test_context_flag_parses_key_value` pattern; not needed for Option A
- `scripts/tests/test_cli_loop_dispatch.py` — `TestMainLoopDispatch`: if Option B, add `test_files_forwarded` following `test_context_forwarded` (line 640) to confirm `--files` is forwarded to `cmd_run()`; not needed for Option A
- Note: `TestBuiltinLoopFiles.test_all_parse_as_yaml`, `test_all_validate_as_valid_fsm`, and `test_all_have_description_field` use `rglob("*.yaml")` and will auto-run against `apply-research.yaml` with no changes needed

### Documentation
- `docs/guides/LOOPS_GUIDE.md` — add example of `apply-research` as a document-ingestion pattern
- `docs/reference/loops.md` — inventory entry (see also Files to Modify above)
- `README.md` — update FSM loop count (line 163); `CONTRIBUTING.md` — update YAML count (line 122); both checked by `ll-verify-docs`

### Configuration
- Declare `relevance_threshold: 0.5` and `max_issues_per_file: 10` as context defaults in `apply-research.yaml` — no `config-schema.json` changes needed (overridable via `--context KEY=VALUE`)

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

**`oracle-capture-issue.yaml` is a scoring oracle, not a creation tool:**
- `oracle-capture-issue.yaml` evaluates prior capture-issue invocations (scores tool selection, file relevance, completion status) — it does NOT call `/ll:capture-issue`. For the `capture_issues` state, invoke `/ll:capture-issue` directly via `action_type: slash_command` and verify with an `exit_code` evaluator.

**Test file location — structural tests belong in `test_builtin_loops.py`, not a standalone file:**
- Add a `TestApplyResearchLoop` class to `scripts/tests/test_builtin_loops.py` (following `TestResearchCoverageOracle` pattern at line ~5627)
- Also add `"apply-research"` to the `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` at line 73; the test suite fails until this entry is added
- Shell-logic fixture files can still go in `scripts/tests/fixtures/research/`

**`scripts/tests/fixtures/research/` does not yet exist** — this directory must be created during implementation. It should contain sample `.txt` and `.md` snippets (not real papers); `TestApplyResearchLoop` shell-logic tests will reference these fixtures.

**`test_expected_loops_exist` expected set spans lines 73–154** (line 73 reference is the `expected` set start, not the exact insert line) — add `"apply-research"` alphabetically within the set literal; the set currently enumerates root-level loop stems only (not `oracles/` or `lib/`).

**Related test class templates** — `scripts/tests/test_deep_research.py` and `scripts/tests/test_harness_optimize.py` demonstrate full test class structure; `TestApplyResearchLoop` should follow this pattern (YAML parsing, FSM validation, state graph assertions via `test_required_states_exist`, context variable checks). `TestResearchCoverageOracle` at `test_builtin_loops.py:5627–5710` is the closest structural template.

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

1. Implement `scripts/little_loops/loops/apply-research.yaml` with all 8 FSM states and non-LLM evaluators for MR-1 compliance; use `input_key: files` (Option A — no CLI changes needed)
2. Add `"apply-research"` to the `expected` set in `TestBuiltinLoopFiles.test_expected_loops_exist` (line 75, `scripts/tests/test_builtin_loops.py`); add a `TestApplyResearchLoop` class following the `TestResearchCoverageOracle` pattern (line 5627)
3. Declare `relevance_threshold: 0.5` and `max_issues_per_file: 10` as context defaults in the loop YAML — no `config-schema.json` changes needed (overridable via `--context KEY=VALUE`)
4. Add test fixtures under `scripts/tests/fixtures/research/` (sample text/md snippets, not real papers)
5. Update all documentation sites: `docs/reference/loops.md` inventory entry, `scripts/little_loops/loops/README.md` catalog entry, `CONTRIBUTING.md` loop count (line 122), and `docs/guides/LOOPS_GUIDE.md`
6. Run `ll-loop validate apply-research` to confirm MR-1/MR-3/MR-4 compliance

## API/Interface

```bash
# Single file (positional arg via input_key: files)
ll-loop run apply-research "path/to/paper.pdf"

# Multiple files (space-separated in positional arg)
ll-loop run apply-research "paper1.pdf notes.md rfc.txt"

# With relevance threshold override
ll-loop run apply-research "paper.pdf" --context relevance_threshold=0.7

# Via Claude Code
/ll:create-loop apply-research
```

## Acceptance Criteria

- Given one or more file paths passed as a positional arg (via `input_key: files`), supporting `.txt`, `.md`, `.pdf` formats, the loop reads each file and extracts candidate recommendations
- Relevance scores are numeric values in range 0–1; items scoring below the configured threshold (default 0.5) are dropped and logged as "filtered"
- For each surviving recommendation, `/ll:capture-issue` is invoked and its exit code is checked (`exit_code` evaluator); a non-zero exit causes the loop to retry or surface an error — no silent swallow
- A summary report is emitted after all files are processed: files processed count, items extracted count, items filtered count, and list of captured issue IDs
- `ll-loop validate apply-research` exits 0 with no MR-1, MR-3, or MR-4 violations
- `context.files` is populated from the positional CLI arg (via `input_key: files`) and accessible inside FSM states as `${context.files}`
- PDF files are converted to Markdown sidecars before reading: the `read_file` state runs `pandoc "$file" -o "${file%.pdf}.md"` (shell action, requires `pandoc` ≥ 2.x on `PATH`) and then reads the resulting `.md`; `.txt` and `.md` files are read directly without conversion. All content entering the extraction prompt is plain Markdown — no pagination needed
- Loop YAML declares `relevance_threshold: 0.5` and `max_issues_per_file: 10` as context defaults; both overridable via `--context KEY=VALUE` (no `config-schema.json` changes required)
- Running with `max_issues_per_file=1` on a multi-recommendation document captures exactly 1 issue (cap enforced)

## Impact

- **Priority**: P3 - Valuable workflow automation; not blocking
- **Effort**: Medium — FSM loop YAML authoring + CLI arg passthrough + test fixtures (~1–2 days)
- **Risk**: Low-Medium — primary artifact is the new loop YAML, but requires coordinated updates to: `scripts/tests/test_builtin_loops.py` (`test_expected_loops_exist` expected set, line 75), `docs/reference/loops.md`, `scripts/little_loops/loops/README.md`, `README.md` (FSM loop count, line 163), `CONTRIBUTING.md` (YAML count, line 122), and `docs/guides/LOOPS_GUIDE.md`. `ll-verify-docs` will fail CI until documented counts are updated.
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`loops`, `built-in-loop`, `research`, `automation`, `captured`

## Status

**Open** | Created: 2026-06-08 | Priority: P3

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-06-08 (prior run: 86/72 → current: 90/72)_

**Readiness Score**: 90/100 → PROCEED
**Outcome Confidence**: 72/100 → MODERATE

### Outcome Risk Factors
- **8 coordinated change sites across 3 subsystems** — loop YAML, 2 test additions, and 5 documentation updates (`docs/reference/loops.md`, `loops/README.md`, `README.md` FSM count at line 163, `CONTRIBUTING.md` YAML count at line 122, `docs/guides/LOOPS_GUIDE.md`); `ll-verify-docs` will fail CI until all count assertions are updated
- **State output schemas under-specified** — `assess_relevance` LLM structured output (0–1 relevance score) and `synthesize_recommendations` output fields (passed to `/ll:capture-issue`) are described conceptually but not as concrete YAML schemas; implementer must design these during authoring

## Resolution

Implemented `apply-research` as a 12-state research-category FSM loop under `scripts/little_loops/loops/apply-research.yaml`. Uses `input_key: files` (Option A — no CLI changes). Key design choices:

- `validate_scores` and `verify_captures` are shell states with `output_numeric` evaluators (MR-1 compliance)
- All inter-iteration artifacts written to `${context.run_dir}/` (MR-3 compliant)
- All prompt states with `on_yes` also have `on_no`, `on_partial`, `on_error` (MR-4 compliant)
- `capture_issues` uses `action_type: prompt` with `next: verify_captures` (per codebase pattern)
- PDF→Markdown via `pandoc` with fallback to raw file if pandoc unavailable
- `meta_self_eval_ok: true` suppresses false-positive meta-loop validator warning

23 structural tests added to `TestApplyResearchLoop` in `test_builtin_loops.py`. Test fixtures created under `scripts/tests/fixtures/research/`. All 714 tests pass. Loop validates clean (`ll-loop validate apply-research` exits 0). README.md loop count corrected to 82 (root 77 + oracles 5).

## Session Log
- `/ll:ready-issue` - 2026-06-08T20:49:52 - `4f8486be-fff7-4b6e-9bac-8236f0a63559.jsonl`
- `/ll:confidence-check` - 2026-06-08T23:00:00 - `2c3fbaa7-2397-4ead-8e81-58f893bcf942.jsonl`
- `/ll:refine-issue` - 2026-06-08T20:37:19 - `9bbdda2c-8cab-43ab-90fc-8bf9011921ae.jsonl`
- `/ll:confidence-check` - 2026-06-08T22:00:00 - `b11c9e94-9a39-44c0-9cb3-c9022529cb42.jsonl`
- `/ll:refine-issue` - 2026-06-08T20:17:21 - `3f0b2e7b-44ae-42c4-9637-de465af2a71b.jsonl`
- `/ll:refine-issue` - 2026-06-08T20:15:11 - `6392fbc2-f8f1-4751-8018-9e14c0b2037d.jsonl`
- `/ll:confidence-check` - 2026-06-08T21:00:00 - `c36c1c68-9f6e-46e8-8abb-d442d3aac92e.jsonl`
- `/ll:decide-issue` - 2026-06-08T20:01:57 - `7ca27d70-ae36-4cb7-90a0-e6b796735d0c.jsonl`
- `/ll:confidence-check` - 2026-06-08T19:30:00 - `f85e77c0-412f-4a1e-932b-aeac2a4797f2.jsonl`
- `/ll:wire-issue` - 2026-06-08T18:58:14 - `d331825d-7e3c-457a-94d7-e13a9bf83a9d.jsonl`
- `/ll:refine-issue` - 2026-06-08T18:50:33 - `2a44cb62-9300-4369-8e0e-768735b76625.jsonl`
- `/ll:format-issue` - 2026-06-08T18:38:07 - `a728ce61-598a-41b4-88fb-5495fbc177b9.jsonl`
- `/ll:capture-issue` - 2026-06-08T18:32:45Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2487f4bf-03ad-45d6-b19b-7a8cbbb8e999.jsonl`
