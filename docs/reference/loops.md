# Built-in Loop Reference

This document provides detailed reference information for selected built-in FSM loops.
For a full catalog and conceptual guide, see [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md).

---

## `harness-optimize`

**Category**: optimization
**File**: `scripts/little_loops/loops/harness-optimize.yaml`

Score-gated hill-climbing on harness artifacts (skills, commands, `CLAUDE.md`). Each iteration proposes an edit to a declared target file set, runs a Harbor-format benchmark, accepts the change if the score rises (or reaches the target threshold), and reverts otherwise. Accepted mutations are committed to the current branch. Stops on the first stall.

### Invocation

Via `.ll/program.md` (recommended for overnight runs):

```bash
# Populate .ll/program.md with Directive, Targets, Benchmark sections, then:
ll-loop run harness-optimize
```

Via `--context` flags:

```bash
ll-loop run harness-optimize \
  --context targets="skills/foo/SKILL.md" \
  --context tasks_dir=./benchmarks/foo \
  --context scorer=./scripts/score.sh
```

Multiple targets (space-separated):

```bash
ll-loop run harness-optimize \
  --context "targets=skills/foo/SKILL.md skills/bar/SKILL.md" \
  --context tasks_dir=./benchmarks/foo \
  --context scorer=./scripts/score.sh
```

See [`.ll/program.md` convention](program-md.md) for the steering file format and precedence rules.

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `targets` | `""` | **Required.** Whole-file mode: space-separated file paths to optimize (e.g. `"skills/foo/SKILL.md"`). State mode: path to a loop YAML file whose `targets:` block contains `states:` entries. |
| `tasks_dir` | `""` | **Required.** Path to Harbor task directory passed to scorer. |
| `scorer` | `""` | **Required.** Scorer command that prints a bare float to stdout on exit 0. |
| `target_score` | `1.0` | Early-stop threshold. `1.0` means "never early-stop on target reached". |
| `max_iterations` | `30` | Hard budget ceiling. |
| `STATE_NAME` | — | State-mode only. Name of the state being optimized; set by `dequeue_state` and read by `propose`, `apply`, and `write_trajectory_*`. |
| `EXAMPLES_FILE` | — | State-mode only. Path to the examples file for the current state; set by `dequeue_state` and injected into the `propose` prompt. |

### State Graph

```
init_run  (shell: create .ll/runs/harness-optimize/<run-id>/ dir, capture traj_path)
  → load_directive  (reads .ll/program.md; builds state queue when targets is a loop YAML)
      on_yes (state-mode: queue non-empty) → check_queue
        on_yes → dequeue_state  (pops STATE_NAME + EXAMPLES_FILE from queue)
          → baseline_score  (fragment: run_benchmark)
              on_yes → init_prev
                → propose  (LLM: extracts state action block; proposes revised action text)
                  → apply  (LLM: writes candidate action via yaml_state_editor.replace_action)
                    → score  (fragment: run_benchmark)
                        on_yes → gate  (convergence evaluator, direction: maximize)
                          target/progress → commit_and_log
                            → write_trajectory_accepted
                                on_yes (state-mode) → check_queue  (advance to next state)
                                on_no  (whole-file)  → capture_prev → propose  (continues)
                          stall/error → revert_and_log
                            → write_trajectory_rejected
                                on_yes (state-mode) → check_queue  (advance to next state)
                                on_no  (whole-file)  → done
                        on_no/on_error → revert_and_log → write_trajectory_rejected → ...
              on_no/on_error → done
        on_no (queue exhausted) → done
      on_no (whole-file mode) → baseline_score  (same subgraph; loops via capture_prev)
```

### Trajectory

Each iteration appends one JSON line to `.ll/runs/harness-optimize/<run-id>/states/<state>/trajectory.jsonl`:

```json
{"iter": 3, "score": 0.82, "accepted": true, "commit_sha": "abc1234"}
{"iter": 4, "score": 0.79, "accepted": false, "commit_sha": ""}
```

In whole-file mode `<state>` is `whole-file`. In state mode `<state>` is the name of the state being optimized (e.g. `propose`, `apply`). The `<run-id>` is a nanosecond timestamp captured by `init_run`.

### Resume Behavior

On resume, `load_directive` reads the trajectory and checks out the best-scoring accepted commit's files before re-running the baseline. It also re-reads `.ll/program.md` to capture the Directive prose, ensuring the LLM proposal step has the optimization goal available even after a handoff. The run continues from the best known state, not the last attempted state.

### Scorer Contract

The scorer command must follow the Harbor scorer protocol:
- Exit 0 + bare float on stdout → `yes` (accepted score)
- Exit 0 + non-float stdout → `error`
- Exit non-zero → `no`

### Dependencies

Imports `lib/benchmark.yaml` for the `run_benchmark` fragment.

### Output Artifacts

> **Runner-written files**: every loop run also produces `usage.jsonl` under `<run_dir>/` when at least one LLM action (prompt/slash_command) executes. Each line records `{iteration, state, action_type, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model, timestamp}`. Shell and mcp_tool actions produce no row. The file lives permanently at `.loops/runs/<id>/usage.jsonl` and is **not** archived to `.loops/.history/`.

In addition to trajectory JSONL files written to `.ll/runs/harness-optimize/<run-id>/`, `harness-optimize` is a meta-loop and produces:

| File | Location | Description |
|------|----------|-------------|
| `<stem>.meta-eval.jsonl` | `.loops/.running/` (archived as `meta-eval.jsonl` under `.loops/.history/<run-id>-<loop-name>/`) | One entry per iteration that passes through an `llm_structured` evaluate state, pairing the LLM self-grade verdict with the external evaluator result. Fields: `iteration`, `ts`, `loop`, `state`, `llm_verdict`, `llm_rationale`, `external_verdict`, `external_state`, `external_evaluator`, `external_value`, `external_target`, `diff_stats`, `agreed`. |

---

## `deep-research`

**Category**: research
**File**: `scripts/little_loops/loops/deep-research.yaml`

Iterative web research synthesis loop. Accepts a research topic or question, generates an initial set of faceted search queries, performs web searches, evaluates and deduplicates sources, scores per-facet coverage, and iterates until coverage is sufficient or `max_iterations` is exhausted. Produces a structured Markdown report with executive summary, key findings, source table, coverage gaps, and conclusion.

### Invocation

```bash
# Basic — positional arg injected into context.topic via input_key: topic
ll-loop run deep-research "What are the trade-offs of CRDT vs OT for collaborative editing?"

# Deeper research with higher coverage target
ll-loop run deep-research "your research topic" \
  --context depth=5 \
  --context coverage_threshold_pct=90
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `topic` | `""` | **Required.** Research question or topic (injected from positional arg via `input_key: topic`). |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/deep-research-{timestamp}/`); created automatically before the `init` state. Override with `--context run_dir=path/` to write to a fixed location. |
| `depth` | `3` | Minimum number of search rounds before accepting convergence. |
| `coverage_threshold_pct` | `85` | Target coverage percentage; surfaced in the `score_coverage` prompt. |

### State Graph

```
init  (shell: mkdir run_dir, touch 4 artifact files, capture run_dir)
  → generate_queries  (prompt: write 3–5 faceted queries to query-log.md;
                       initialize coverage.md with facet list)
    → search_web  (prompt: WebSearch/WebFetch; append findings + [Source: <url>] to knowledge-base.md)
      → evaluate_sources  (prompt: score relevance/credibility, deduplicate, mark LOW-QUALITY)
        → score_coverage  (prompt: score facets 1–5, update coverage.md;
                           emit COVERAGE_SUFFICIENT or NEED_MORE)
          on_yes (COVERAGE_SUFFICIENT) → synthesize
          on_no  (NEED_MORE)           → plan_next
          on_error                     → synthesize  (graceful degradation)
            → plan_next  (prompt: generate gap-filling queries, append to query-log.md)
              → search_web  (loop back)
  synthesize  (prompt: consolidate knowledge-base.md into structured report.md)
    → done  (terminal: report final output paths and facet scores)
```

### Output Artifacts

All artifacts are written to `${context.run_dir}` (the per-run directory injected by the runner):

| File | Description |
|------|-------------|
| `report.md` | Primary output — executive summary, key findings, source table, coverage gaps, conclusion |
| `knowledge-base.md` | Accumulated findings with `[Source: <url>]` (relevance: N/5, credibility: N/5) annotations |
| `coverage.md` | Per-facet coverage scores (1–5) updated each iteration; includes iteration count and average |
| `query-log.md` | All search queries grouped by iteration (`## Iteration N` blocks) |

### Convergence

`score_coverage` uses the **inline sentinel** pattern (Option A, `rn-plan`-style):

- Emits `COVERAGE_SUFFICIENT` when: average facet score ≥ 4.0 AND iteration ≥ `depth`
- Emits `NEED_MORE` otherwise
- `on_error` routes to `synthesize` (write what we have; don't stall)

Knowledge accumulation: `knowledge-base.md` **appends** across iterations (sources accumulate); `coverage.md` **overwrites** each iteration (only latest score matters for routing).

---

## `oracles/generator-evaluator`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/generator-evaluator.yaml`

Reusable iterative artifact generation oracle. Loops `generate → evaluate (Playwright screenshot) → score (LLM rubric)` until `ALL_PASS` or `max_iterations`. Returns `done` on success; the calling thin-wrapper routes `on_yes` to its next state.

Used by `html-website-generator`, `svg-image-generator`, `html-anything`, `hitl-md`, and `hitl-compare` as a `loop:` delegation state named `run_gen_eval` (ENH-1869).

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | Directory path for generated artifacts (absolute or runner-injected relative path) |
| `generate_prompt` | yes | — | Full LLM prompt for the `generate` state, including output file instructions |
| `rubric` | no | `""` | Rubric criteria markdown passed to the `score` state |
| `pass_threshold` | no | `6` | Minimum score per criterion to accept (out of 10) |
| `artifact_path` | no | `"index.html"` | Artifact filename relative to `run_dir` for Playwright screenshot capture |

### Invocation (thin-wrapper pattern)

```yaml
run_gen_eval:
  loop: oracles/generator-evaluator
  with:
    run_dir: ${captured.run_dir.output}
    generate_prompt: |
      Write index.html to ${captured.run_dir.output}/ ...
    rubric: |
      - criterion_a: description
    pass_threshold: 7
  on_yes: done        # or smoke_test / finalize for wrappers that post-process
  on_no: failed
  on_error: failed
```

### Internal state machine

```
generate → evaluate (playwright_screenshot fragment) → score (ll_rubric_score fragment)
  score.on_yes → done (terminal)
  score.on_no  → generate
  evaluate.on_yes/no/error → score   # graceful degradation if Playwright unavailable
```

### Fragment dependency

Imports `lib/harness.yaml` for the `playwright_screenshot` fragment used in the `evaluate` state and the `ll_rubric_score` fragment used in the `score` state. See `## Fragment Catalog → lib/harness.yaml fragments` in `skills/create-loop/reference.md`.

---

## `oracles/research-coverage`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/research-coverage.yaml`

Reusable iterative web research synthesis oracle. Runs `generate_queries → search_web → evaluate_sources → score_coverage` until coverage is sufficient, then `synthesize → done`. Parameterized for both general web research and arxiv-only academic research.

Used by `deep-research` (general web, `source_filter=""`, `academic_mode=false`) and `deep-research-arxiv` (arxiv-only, `source_filter="site:arxiv.org"`, `academic_mode=true`) as a `loop:` delegation state named `run_research` (ENH-1876).

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | Absolute path to the per-run artifact directory created by the caller's `init` state |
| `topic` | yes | — | Research topic or question (passed from caller's `input_key` binding) |
| `source_filter` | no | `""` | Site constraint appended to every search query (e.g. `"site:arxiv.org"`); empty string = no constraint |
| `academic_mode` | no | `false` | Gates academic-specific behaviors: recency scoring axis, arxiv ID dedup key, BibTeX section in `synthesize`, academic query terminology in `generate_queries` |

### Invocation (thin-wrapper pattern)

```yaml
run_research:
  loop: oracles/research-coverage
  with:
    run_dir: ${captured.run_dir.output}
    topic: ${context.topic}
    source_filter: ""        # or "site:arxiv.org" for arxiv mode
    academic_mode: false     # or true for arxiv mode
  on_success: done
  on_failure: failed
  on_error: failed
```

### Internal state machine

```
generate_queries → search_web → evaluate_sources → score_coverage
  score_coverage.on_yes (COVERAGE_SUFFICIENT) → synthesize → done (terminal)
  score_coverage.on_no  (NEED_MORE)           → plan_next  → search_web
  score_coverage.on_error                     → synthesize (graceful degradation)
```

### Fragment dependency

Imports `lib/common.yaml`. No Playwright or harness fragments required.
