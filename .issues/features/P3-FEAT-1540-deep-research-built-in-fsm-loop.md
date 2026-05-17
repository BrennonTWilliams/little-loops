---
id: FEAT-1540
type: FEAT
priority: P3
status: done
discovered_date: 2026-05-16
discovered_by: capture-issue
captured_at: '2026-05-17T04:33:09Z'
completed_at: '2026-05-17T08:01:20Z'
decision_needed: false
confidence_score: 100
outcome_confidence: 82
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# FEAT-1540: Add deep-research built-in FSM loop for iterative web research synthesis

## Summary

Add a new built-in FSM loop `deep-research` that accepts a research topic or question, iteratively performs web searches, evaluates sources, identifies knowledge gaps, and synthesizes findings into a structured research report. Modeled on how deep research tools (Perplexity, ChatGPT deep research, Gemini deep research) work but as an ll automation loop.

## Current Behavior

No built-in loop exists for structured, iterative web research. Users must manually issue search queries, evaluate results, track coverage, and synthesize findings — a tedious and often incomplete process with no automated gap-identification or convergence criterion.

## Expected Behavior

Users can run:

```bash
ll-loop run deep-research --topic "What are the trade-offs of CRDT vs OT for collaborative editing?" --depth 3
```

or trigger via Claude Code:

```
/ll:create-loop deep-research
```

The loop:
1. Generates an initial set of search queries from the topic
2. Executes web searches and scores source relevance and credibility
3. Extracts key claims and synthesizes a running knowledge base
4. Identifies coverage gaps and generates follow-up queries
5. Iterates until coverage score meets threshold or `max_iterations` exhausted
6. Outputs a structured Markdown research report with citations

## Motivation

Deep research is one of the most common use cases Claude users perform manually and repetitively. An FSM-based loop that automates query generation, source evaluation, and gap-detection would:
- Reduce manual overhead for research-heavy workflows
- Produce consistently structured, cited outputs
- Complement the existing `rn-plan` loop (FEAT-1534) — deep-research feeds into planning
- Demonstrate ll's capability as a general automation platform beyond code tasks

## Use Case

A developer or researcher needs to answer a complex, multi-faceted question (e.g., "What are the trade-offs of CRDT vs OT for collaborative editing?") that requires synthesizing information from multiple sources. Instead of manually issuing search queries, evaluating sources, and tracking coverage, they run:

```bash
ll-loop run deep-research "What are the trade-offs of CRDT vs OT for collaborative editing?" --context depth=3
```

The loop iteratively searches the web, accumulates a cited knowledge base, identifies coverage gaps, and produces a structured `report.md` with an executive summary, key findings, source table, and conclusion — ready for use in planning or decision-making.

## Acceptance Criteria

- [ ] `ll-loop run deep-research "<topic>"` runs end-to-end without error for a given topic string
- [ ] The `init` state creates a run directory containing `report.md`, `knowledge-base.md`, `coverage.md`, and `query-log.md`
- [ ] The loop iterates through `generate_queries → search_web → evaluate_sources → score_coverage → plan_next` and loops back
- [ ] The `score_coverage` state emits `COVERAGE_SUFFICIENT` when facet scores are satisfied, routing to `synthesize`; otherwise routes to `plan_next`
- [ ] The `synthesize` state produces a structured `report.md` with: executive summary, key findings, source table (deduplicated URLs), coverage gaps, and conclusion
- [ ] `ll-loop list` includes `deep-research` in its output (auto-discovery confirmed)
- [ ] `ll-loop validate deep-research` passes schema validation without errors
- [ ] `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` passes with `"deep-research"` in the expected set
- [ ] `scripts/tests/test_deep_research.py` passes all structural, shell-state, evaluator, and resolution tests
- [ ] `--dry-run` mode exits 0 and prints the loop name

## Proposed Solution

The loop will be a single YAML file at `scripts/little_loops/loops/deep-research.yaml` — built-in loops are auto-discovered from that directory by `resolve_loop_path()` in `scripts/little_loops/cli/loop/_helpers.py:127`. No registration step is needed; drop the file and it's available as `ll-loop run deep-research "<topic>"`.

**FSM state sketch (modeled on `rn-plan.yaml`):**
- `init` (`action_type: shell`) — slug the topic, `mkdir -p ${context.output_dir}/<slug>`, touch `report.md` / `knowledge-base.md` / `coverage.md` / `query-log.md`, echo `$(pwd)/$DIR`, `capture: run_dir`
- `generate_queries` (`action_type: prompt`) — generate 3–5 initial search queries from `${context.topic}`, append to `${captured.run_dir.output}/query-log.md`
- `search_web` (`action_type: prompt`) — invoke WebSearch/WebFetch directly (LLM tools are available in prompt states; see `rn-plan.yaml:173-201` `research_web`), append findings to `knowledge-base.md` with source URLs
- `evaluate_sources` (`action_type: prompt`) — score relevance/credibility of new sources, deduplicate citations
- `score_coverage` (`action_type: prompt`) — compare knowledge base to topic facets, emit a numeric coverage score and a sentinel token (`COVERAGE_SUFFICIENT` or `NEED_MORE`)
- `plan_next` (`action_type: prompt`) — given gaps from `score_coverage`, generate next-round queries; loop back to `search_web`
- `synthesize` (`action_type: prompt`) — consolidate `knowledge-base.md` into structured `report.md` (executive summary, key findings, source table, gaps, conclusion)
- `done` (`terminal: true`) — final state

**CLI input plumbing:** Declare `input_key: topic` at the top level. Positional arg from `ll-loop run deep-research "<topic>"` is injected into `fsm.context["topic"]` by `cmd_run()` in `scripts/little_loops/cli/loop/run.py:126-139`. Reference as `${context.topic}` throughout. Additional inputs (`--context depth=5 --context coverage_threshold=0.85`) work with no extra wiring.

### Option A — Inline sentinel convergence (rn-plan pattern)

> **Selected:** Option A — Inline sentinel convergence (rn-plan pattern) — matches 5 existing scoring states exactly; one state handles both scoring and routing with no extra infrastructure.

Score and convergence-check happen in **one state** that prompts the LLM to write a coverage score *and* emit a sentinel token, evaluated by `output_contains`:

```yaml
score_coverage:
  action_type: prompt
  action: |
    Read ${captured.run_dir.output}/knowledge-base.md.
    Score coverage across topic facets ... (1-5 each).
    If all facets >= 4 AND total iterations >= 2, output: COVERAGE_SUFFICIENT
    Otherwise output: NEED_MORE
  evaluate:
    type: output_contains
    pattern: "COVERAGE_SUFFICIENT"
  on_yes: synthesize
  on_no: plan_next
  on_error: synthesize    # graceful degradation — write what we have
```

Mirrors `rn-plan.yaml:228-266` `score` state. Simpler — one state does both jobs.

### Option B — Separate scoring + router state (apo-textgrad pattern)

Split into `compute_coverage` (captures structured score) and `route_coverage` (pure evaluator with `source:` redirect):

```yaml
compute_coverage:
  action_type: prompt
  action: |
    ... compute facet scores, write to coverage.md ...
    On the final line output: COVERAGE=<integer 0-100>
    If COVERAGE >= ${context.coverage_threshold_pct}, also output CONVERGED.
  capture: coverage
  next: route_coverage

route_coverage:
  # no action — pure evaluator
  evaluate:
    type: output_contains
    source: "${captured.coverage.output}"
    pattern: "CONVERGED"
  on_yes: synthesize
  on_no: plan_next
  on_error: synthesize
```

Mirrors `apo-textgrad.yaml` `route_convergence` (lines 39–48). More verbose but gives `compute_gradient`-style states richer numeric context for `plan_next` to consume. `source:` is required when the router has no action of its own (tested in `test_rn_plan_apo.py::TestRouteConvergenceState::test_route_convergence_evaluator_source`).

**Recommendation:** Option A for v1 — simpler, matches `rn-plan`'s established style; promote to Option B only if iterative gap-driven query planning needs explicit numeric history.

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-05-17.

**Selected**: Option A — Inline sentinel convergence (rn-plan pattern)

**Reasoning**: Option A scores 12/12 vs Option B's 8/12. It is the established pattern for convergence states in this codebase, used identically in `rn-plan.yaml:228-266`, `html-anything.yaml`, `html-website-generator.yaml`, `svg-image-generator.yaml`, and `dataset-curation.yaml`. Option B adds a second state with a `source:` redirect that has a documented silent failure mode (forgetting `source:` causes the evaluator to always match the empty string from the no-action state). All required infrastructure for Option A is fully proven with direct test templates available in `test_rn_plan.py:255-265`.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| Option A (inline sentinel) | 3/3 | 3/3 | 3/3 | 3/3 | 12/12 |
| Option B (separate router) | 3/3 | 1/3 | 2/3 | 2/3 | 8/12 |

**Key evidence**:
- Option A: 5 existing loops use the identical inline scoring structure; direct test template at `test_rn_plan.py:255-265` copies verbatim; zero missing infrastructure
- Option B: 6 APO-family loops use the separate router pattern; requires 2 states vs 1; documented `source:`-omission failure mode in `test_rn_plan_apo.py:217-228`

### Secondary design question — knowledge accumulation pattern

| Pattern | Used by | Behavior |
|---------|---------|----------|
| **Overwrite per-iteration** | `rn-plan.yaml` (`research.md`) | Each iteration replaces the working file; final `synthesize` reads only the latest |
| **Append history** | `svg-textgrad.yaml` (`scores.md`, `gradients.md`) | Each iteration appends a `## Iteration N` block; later states can detect "no improvement in last 3 iterations" |

For deep-research, `knowledge-base.md` should **append** (sources accumulate across rounds) but `coverage.md` can **overwrite** (only the latest score matters for routing). This is a hybrid — established in the codebase, not a new pattern.

### Other key design decisions (resolved)

- **Coverage scoring model**: LLM-as-judge (consistent with `rn-plan` `score`, `harness-single-shot` `check_semantic`, `outer-loop-eval` `generate_report`). Keyword-overlap and embedding-similarity are not used anywhere in the codebase and would require new dependencies.
- **WebSearch invocation**: Natural-language instruction in a `prompt` state (per `rn-plan.yaml:173-201`). No tool restriction needed — leaving `state.tools` unset gives the LLM full WebSearch/WebFetch/Read/Write access. Only `agents/web-search-researcher.md` declares an explicit tools allowlist, and that's an agent definition, not a loop state.
- **Citation format**: Append `[Source: <url>]` inline in `knowledge-base.md`; final `synthesize` deduplicates URLs into a source table at the end of `report.md`. No central registry needed.
- **Resumable knowledge base across sessions**: Defer to v2 — current loop persistence (`fsm/persistence.py`) handles `captured` dict but not arbitrary on-disk artifact reuse. v1 is single-session.
- **Integration with `rn-plan`**: Defer to a follow-up issue — `rn-plan` could call `deep-research` via the `state.loop` sub-loop mechanism (see `FSMExecutor._execute_sub_loop()` in `fsm/executor.py`), but that's an additive enhancement after v1 lands.

## Integration Map

### Files to Modify
- **Create** `scripts/little_loops/loops/deep-research.yaml` — the new built-in loop YAML (~150-250 lines, modeled on `rn-plan.yaml`)
- `scripts/little_loops/loops/README.md` — add a row in the built-in loops table; consider a new "Research & Knowledge" category section
- `scripts/tests/test_builtin_loops.py` — add `"deep-research"` to the `expected` set in `TestBuiltinLoopFiles::test_expected_loops_exist`
- **Create** `scripts/tests/test_deep_research.py` — structural and shell-state tests (modeled on `scripts/tests/test_rn_plan.py`)
- `docs/guides/LOOPS_GUIDE.md` — add a section on the deep-research loop with a usage example
- `CHANGELOG.md` — entry under the next concrete release version (NOT `[Unreleased]`, per project convention)

### Dependent Files (Callers/Importers)

This is a **new built-in loop** with no callers at v1. Discovery happens automatically — the file is found at runtime by these existing call sites (no code changes required):

- `scripts/little_loops/cli/loop/_helpers.py:127` — `resolve_loop_path()` walks `<builtin_dir>/<name>.yaml` as the fallback path
- `scripts/little_loops/cli/loop/_helpers.py:122` — `get_builtin_loops_dir()` resolves to `scripts/little_loops/loops/`
- `scripts/little_loops/cli/loop/info.py:112-134` — `cmd_list` enumerates `*.yaml` in the built-in dir; the new loop appears in `ll-loop list` automatically

Potential downstream consumers (out of scope for v1 — listed for awareness):
- `scripts/little_loops/loops/rn-plan.yaml` `research_web` state could eventually delegate to deep-research via `state.loop` (sub-loop mechanism in `fsm/executor.py::_execute_sub_loop()`); tracked as a follow-up enhancement, not part of FEAT-1540

### Similar Patterns

_Existing path references in this section pointed at `.loops/built-in/` and `scripts/little_loops/loop_runner.py`, both of which are incorrect for the current codebase layout. Corrected and expanded below._

**Primary reference (sibling built-in loop):**
- `scripts/little_loops/loops/rn-plan.yaml` (FEAT-1534) — same structural pattern: shell `init` captures `run_dir`, prompt states cycle through research, scoring with sentinel-based convergence. **Copy this file as a starting template.**
- `scripts/little_loops/loops/rn-plan.yaml:20-35` (`init` state) — slug-based output dir setup, absolute-path capture (`$(pwd)/$DIR`)
- `scripts/little_loops/loops/rn-plan.yaml:173-201` (`research_web` state) — the **only** existing built-in usage of WebSearch/WebFetch; canonical pattern to mirror
- `scripts/little_loops/loops/rn-plan.yaml:228-266` (`score` state) — sentinel-based convergence via `output_contains` (Option A)

**Alternative convergence pattern:**
- `scripts/little_loops/loops/apo-textgrad.yaml:39-48` (`route_convergence`) — separate router state with `source:` redirect (Option B)
- `scripts/little_loops/loops/svg-textgrad.yaml:145-171` (`record_scores`) — file-append accumulation across iterations

**FSM engine (do not modify — reference for behavior):**
- `scripts/little_loops/fsm/executor.py` — `FSMExecutor.run()` drives the main loop; `_execute_state()` dispatches by `action_type`; `_route()` resolves verdicts
- `scripts/little_loops/fsm/schema.py` — `FSMLoop.from_dict()` defines required/optional top-level fields (`name`, `initial`, `states`, defaults for `max_iterations: 50`, etc.); `StateConfig.from_dict()` for per-state fields
- `scripts/little_loops/fsm/evaluators.py` — `evaluate_output_contains`, `evaluate_llm_structured`, `evaluate_output_numeric` (the three patterns viable for coverage convergence)
- `scripts/little_loops/fsm/interpolation.py` — `InterpolationContext.resolve()` defines `${context.X}`, `${captured.X.output}`, `${state.iteration}` namespaces
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` invokes Claude CLI for prompt states (this is where WebSearch becomes available)

**CLI entry point (do not modify):**
- `scripts/little_loops/cli/loop/run.py:126-139` (`cmd_run`) — positional CLI arg → `fsm.context[fsm.input_key]` injection; declare `input_key: topic` to receive the topic string

**Reusable fragments (optional — can pull from):**
- `scripts/little_loops/loops/lib/common.yaml` — `llm_gate` (LLM yes/no), `shell_exit`, `retry_counter`, `numeric_gate`
- `scripts/little_loops/loops/lib/score-plan-quality.yaml` — multi-dimensional scoring fragment; possible model for coverage scoring if Option B is chosen

**Agent reference (not used directly, but informs prompt design):**
- `agents/web-search-researcher.md` — documents WebSearch strategy ("2–3 well-crafted searches before fetching content"); useful as a model for the `search_web` and `plan_next` prompt bodies

### Tests

**New test file to create** — `scripts/tests/test_deep_research.py`. Model after `scripts/tests/test_rn_plan.py`. Required test classes:

- `TestDeepResearchYaml` — structural validation:
  - `test_fsm_validates_without_errors` — uses `load_and_validate()` and `validate_fsm()`
  - `test_required_top_level_fields` — asserts `name == "deep-research"`, `initial == "init"`, `input_key == "topic"`, valid `states` dict
  - `test_required_states_exist` — at minimum: `init`, `generate_queries`, `search_web`, `evaluate_sources`, `score_coverage`, `plan_next`, `synthesize`, `done`
  - `test_coverage_state_uses_sentinel` — asserts `evaluate.type == "output_contains"` and `pattern` is the convergence token (e.g., `COVERAGE_SUFFICIENT`)
  - `test_terminal_done_state` — `done.terminal == True`
- `TestDeepResearchShellStates` — exercise the `init` state's shell action via `subprocess.run` in a `tmp_path`, assert directory + sentinel files are created with `$(pwd)`-based absolute path
- `TestDeepResearchEvaluators` — unit-test the convergence evaluator with `evaluate_output_contains` directly (no subprocess)
- `TestDeepResearchResolution` — assert `resolve_loop_path("deep-research", get_builtin_loops_dir())` finds the file
- `TestDeepResearchDryRun` — CLI smoke test via `main_loop()` with `--dry-run` flag

**Existing test to update** — `scripts/tests/test_builtin_loops.py`:
- `TestBuiltinLoopFiles::test_expected_loops_exist` — add `"deep-research"` to the `expected` set (regression test will fail otherwise)

**Optional behavioral test (gated, slow)** — modeled on `scripts/tests/test_feat1544_loop_specialist_eval.py`: gate with `@pytest.mark.skipif(shutil.which("claude") is None, ...)` and `@pytest.mark.slow` for live LLM validation.

### Documentation

- `scripts/little_loops/loops/README.md` — add a table row under an appropriate category (suggest new "Research & Knowledge" section). Include name, one-line description, and primary inputs.
- `docs/guides/LOOPS_GUIDE.md` — add a usage example showing `ll-loop run deep-research "<topic>" --context depth=5`; reference the loop in the patterns section as an example of WebSearch-driven iteration.
- `docs/generalized-fsm-loop.md` — optionally cite `deep-research` alongside `rn-plan` as a worked example of the iterative-research-with-sentinel-convergence pattern (not required for ship; nice-to-have).
- `CHANGELOG.md` — entry under the next concrete release version (NOT `[Unreleased]` — promote during release prep per project convention).

_Wiring pass added by `/ll:wire-issue`:_
- `README.md:167` — hardcoded `**48 FSM loops**` count (48 actual as of validation); must be updated to 49 when deep-research ships [Agent 2 finding]
- `CONTRIBUTING.md:122` — hardcoded `(48 YAML files)` count in loops directory listing (48 actual as of validation); must be updated to 49 when deep-research ships [Agent 2 finding]
- `docs/reference/loops.md` — established pattern for major loops (`## harness-optimize` reference section exists here); add a `## deep-research` section with state graph, context variables, and invocation example [Agent 2 finding]

### Configuration
- N/A — no new config keys required. Existing context-variable mechanism (`--context KEY=VALUE`) handles all runtime parameters (`depth`, `coverage_threshold`, `output_dir`). No `.ll/ll-config.json` changes needed.

## Implementation Steps

1. **Decide convergence pattern** — run `/ll:decide-issue FEAT-1540` to choose Option A (inline sentinel, rn-plan style) vs Option B (separate router state, apo-textgrad style). Recommended default: Option A for v1.
2. **Scaffold YAML** — copy `scripts/little_loops/loops/rn-plan.yaml` as a starting template to `scripts/little_loops/loops/deep-research.yaml`. Set top-level: `name: deep-research`, `category: research`, `input_key: topic`, `initial: init`, `max_iterations: 30`, `timeout: 3600`, `context: {topic: "", output_dir: ".loops/research", depth: 3, coverage_threshold_pct: 85}`.
3. **Implement `init` state** — shell action that slugs `${context.topic}`, runs `mkdir -p ${context.output_dir}/<slug>`, touches `report.md`/`knowledge-base.md`/`coverage.md`/`query-log.md`, echoes `$(pwd)/$DIR`. `capture: run_dir`, `next: generate_queries`. Mirror `rn-plan.yaml:20-35`.
4. **Implement `generate_queries` prompt state** — prompt the LLM to produce 3–5 initial search queries from `${context.topic}` and append them to `${captured.run_dir.output}/query-log.md` with iteration marker. `next: search_web`.
5. **Implement `search_web` prompt state** — instruct LLM to "Use the WebSearch and WebFetch tools to investigate the queries in `${captured.run_dir.output}/query-log.md` (latest iteration block) ... Append findings to `${captured.run_dir.output}/knowledge-base.md` with `[Source: <url>]` markers." `next: evaluate_sources`. Mirror `rn-plan.yaml:173-201`.
6. **Implement `evaluate_sources` prompt state** — deduplicate citations, score relevance/credibility of new sources, prune low-quality entries from `knowledge-base.md`. `next: score_coverage`.
7. **Implement `score_coverage` state per chosen Option** — Option A: single prompt state with inline `evaluate.type: output_contains` for `COVERAGE_SUFFICIENT` sentinel; routes `on_yes: synthesize`, `on_no: plan_next`, `on_error: synthesize`. Option B: split into `compute_coverage` (capture: coverage) + `route_coverage` (pure evaluator with `source: ${captured.coverage.output}`).
8. **Implement `plan_next` prompt state** — read coverage gaps from `score_coverage` output, generate next-round queries appended to `query-log.md`. `next: search_web` (loop back).
9. **Implement `synthesize` prompt state** — read `knowledge-base.md`, consolidate into structured `report.md` (executive summary, key findings, source table with deduplicated URLs, coverage gaps, conclusion). `next: done`.
10. **Implement `done` state** — `terminal: true`, echo `${captured.run_dir.output}/report.md` so the report path is the final loop output.
11. **Validate** — run `ll-loop validate deep-research` and `python -m pytest scripts/tests/test_builtin_loops.py -v` to catch schema/discovery errors.
12. **Add `deep-research` to the regression set** — edit `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` and add `"deep-research"` to the `expected` set.
13. **Create `scripts/tests/test_deep_research.py`** — copy `scripts/tests/test_rn_plan.py` and adapt. At minimum: `TestDeepResearchYaml` (structural), `TestDeepResearchShellStates::test_init_creates_run_directory` (subprocess), `TestDeepResearchEvaluators::test_coverage_sentinel_matches`, `TestDeepResearchResolution::test_loop_resolves_as_builtin`.
14. **Run full test suite** — `python -m pytest scripts/tests/test_deep_research.py scripts/tests/test_builtin_loops.py -v`. Run linting: `ruff check scripts/` and `ruff format scripts/`.
15. **Live smoke test (manual)** — `ll-loop run deep-research "What are the trade-offs of CRDT vs OT for collaborative editing?" --context depth=2 --dry-run`, then without `--dry-run` to verify end-to-end. Inspect `report.md` for structure and citation quality.
16. **Update `scripts/little_loops/loops/README.md`** — add a row in the built-in loops table; consider adding a "Research & Knowledge" category section if none exists.
17. **Update `docs/guides/LOOPS_GUIDE.md`** — add a section describing `deep-research` with a copy-pasteable example.
18. **CHANGELOG entry** — add under the next concrete release version section (NOT `[Unreleased]`, per project memory `feedback_changelog_no_unreleased`).

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

19. Update `README.md:167` — increment the hardcoded `**48 FSM loops**` count to 49 when deep-research ships
20. Update `CONTRIBUTING.md:122` — increment the hardcoded `(48 YAML files)` count to 49 when deep-research ships
21. Add `## deep-research` section to `docs/reference/loops.md` — include state graph, context variable table, and a copy-pasteable invocation example; follow the `## harness-optimize` section as a structural template

## Impact

- **Priority**: P3 - High-value user workflow, no existing workaround, complements rn-plan
- **Effort**: Large - new FSM design, coverage scoring, report templating
- **Risk**: Medium - WebSearch rate limits and quality variance; coverage scoring may need tuning
- **Breaking Change**: No

## API/Interface

```yaml
# .loops/built-in/deep-research.yaml (sketch)
name: deep-research
description: Iterative web research synthesis loop
inputs:
  topic: str          # Research question or topic
  depth: int          # Max search rounds (default: 5)
  coverage_threshold: float  # Stop when coverage score >= this (default: 0.85)
  max_iterations: int  # Hard cap (default: 30)
outputs:
  report_path: str    # Path to generated Markdown report
```

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`feat`, `loops`, `built-in-loop`, `research`, `captured`

## Status

**Open** | Created: 2026-05-16 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-05-17T07:56:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b04d7fe6-41d0-4c72-8587-c000b50cae3f.jsonl`
- `/ll:decide-issue` - 2026-05-17T07:50:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/55f2e55d-e8d0-42f3-a13a-9bd3facc4209.jsonl`
- `/ll:confidence-check` - 2026-05-17T08:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aac60a3c-4bb3-4d31-b1a0-08e1bc0000bc.jsonl`
- `/ll:confidence-check` - 2026-05-17T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4e02d381-e090-4f5e-8b94-ad82b1def412.jsonl`
- `/ll:wire-issue` - 2026-05-17T07:43:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d7e4f13a-3acd-435c-a079-10fe48342d31.jsonl`
- `/ll:refine-issue` - 2026-05-17T07:37:22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/32201974-d8b4-4fa2-8deb-5675e43b50d7.jsonl`
- `/ll:capture-issue` - 2026-05-17T04:33:09Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/314d8cca-9d5a-4567-8a16-87fa357d45fb.jsonl`
