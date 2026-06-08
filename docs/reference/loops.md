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
init_run  (shell: create ${context.run_dir}/states/whole-file/ dir, capture traj_path)
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

Each iteration appends one JSON line to `.loops/runs/harness-optimize-<timestamp>/states/<state>/trajectory.jsonl`:

```json
{"iter": 3, "score": 0.82, "accepted": true, "commit_sha": "abc1234"}
{"iter": 4, "score": 0.79, "accepted": false, "commit_sha": ""}
```

In whole-file mode `<state>` is `whole-file`. In state mode `<state>` is the name of the state being optimized (e.g. `propose`, `apply`). The `<timestamp>` is the runner-injected run timestamp embedded in `${context.run_dir}`.

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

In addition to trajectory JSONL files written under `${context.run_dir}/states/`, `harness-optimize` is a meta-loop and produces:

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

## `sft-corpus`

**Category**: data
**File**: `scripts/little_loops/loops/sft-corpus.yaml`

Pipeline that stages session JSONL transcripts, batch-joins `history.db` session-quality metadata, runs a five-predicate filter chain, deduplicates by Jaccard similarity, splits into train/val/test splits, delegates to `dataset-curation` for quality validation, and publishes an SFT training corpus with a manifest and harvest sentinel for incremental re-runs.

### Invocation

```bash
# Default: stages from data/sessions, outputs to data/corpus
ll-loop run sft-corpus

# With custom data directory and quality gates
ll-loop run sft-corpus \
  --context data_dir=data/my-sessions \
  --context require_issue_outcome=true \
  --context exclude_user_corrections=true \
  --context min_tool_invocations=5

# With PII discarding and custom split ratios
ll-loop run sft-corpus \
  --context pii_action=discard \
  --context val_ratio=0.15 \
  --context test_ratio=0.15
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `data_dir` | `"data/sessions"` | Directory with session UUID JSONL transcript files |
| `output_dir` | `"data/corpus"` | Final corpus output directory (manifest, rejections, staged splits) |
| `sft_format` | `"chatml"` | SFT output format: `chatml`, `alpaca`, or `sharegpt` |
| `max_turns` | `20` | Maximum conversation turns per window |
| `min_tokens` | `50` | Discard examples below this word-count threshold (proxy) |
| `max_tokens` | `4096` | Discard examples above this word-count threshold (proxy) |
| `require_issue_outcome` | `false` | Drop sessions where no issue was closed (predicate 1) |
| `exclude_user_corrections` | `false` | Drop sessions containing user corrections (predicate 2) |
| `min_tool_invocations` | `0` | Drop sessions below this tool-call count (predicate 3) |
| `require_file_modifications` | `false` | Drop sessions with zero file modifications (predicate 4) |
| `pii_action` | `"flag"` | PII handling mode: `flag` (add `pii_detected` field), `redact` (replace with `[TYPE]` placeholders), or `discard` (drop example entirely) (predicate 5) |
| `val_ratio` | `0.1` | Fraction of sessions reserved for validation split |
| `test_ratio` | `0.1` | Fraction of sessions reserved for test split |
| `schema_path` | `"schemas/sft.json"` | Schema file for `dataset-curation` validation |
| `dedup_threshold` | `0.9` | Jaccard similarity threshold for near-duplicate removal (0.0–1.0) |

### State Graph

```
stage  (shell: ll-messages --sft-format to raw.jsonl; incremental via sft-corpus.last_harvested)
  → enrich  (shell: batch-join history.db metadata via lookup_session_metadata())
    → check_issue_outcome  (predicate 1; shell: gated by require_issue_outcome)
        on_yes → check_corrections
        on_no  → reject_issue_outcome  → check_corrections
    → check_corrections  (predicate 2; shell: gated by exclude_user_corrections)
        on_yes → check_tools
        on_no  → reject_corrections  → check_tools
    → check_tools  (predicate 3; shell: gated by min_tool_invocations > 0)
        on_yes → check_files
        on_no  → reject_tools  → check_files
    → check_files  (predicate 4; shell: gated by require_file_modifications)
        on_yes → check_pii
        on_no  → reject_files  → check_pii
    → check_pii  (predicate 5; shell: apply_pii_action() — flag/redact/discard)
        on_yes → check_token_length
        on_no  → reject_pii  → check_token_length
    → check_token_length  (shell: filter by [min_tokens, max_tokens]; writes token_filtered.jsonl)
        on_yes → dedup
        on_no  → reject_token_length → publish
    → dedup  (shell: Jaccard similarity near-duplicate removal; writes deduped.jsonl)
        on_yes → split
        on_no  → publish
    → split  (shell: session-stratified train/val/test split with seed 42)
      → curate  (sub-loop: dataset-curation; validates via schema_path)
          on_success → publish
          on_failure → done
    → publish  (shell: aggregate stats, write manifest.json, update sft-corpus.last_harvested)
      → done  (terminal)
```

All five rejection states (`reject_issue_outcome`, `reject_corrections`, `reject_tools`, `reject_files`, `reject_pii`) append a `{path, score, reason, timestamp}` entry to `${output_dir}/rejections.jsonl` and continue the chain — rejection does not short-circuit.

### Filter Predicate Chain

The five predicate checks run sequentially. Each predicate is gated by its context flag:

1. **`require_issue_outcome`** — keeps only sessions where an issue was closed (`issue_outcome == "done"`)
2. **`exclude_user_corrections`** — discards sessions where the user issued a correction
3. **`min_tool_invocations`** — drops sessions with tool-call counts below the threshold
4. **`require_file_modifications`** — drops sessions with zero file modifications
5. **`pii_action`** — `flag` adds a `pii_detected` boolean; `redact` replaces PII spans with `[TYPE]` placeholders; `discard` drops the example entirely

When a flag is `false`/`0` (or `pii_action` is not `discard` with detected PII), the check passes through.

### Output Artifacts

| File | Location | Description |
|------|----------|-------------|
| `raw.jsonl` | `${run_dir}/` | Staged transcripts from `ll-messages --sft-format` |
| `enriched.jsonl` | `${run_dir}/` | Transcripts with `metadata` block (has_corrections, issue_outcome, tool_count, files_modified) |
| `token_filtered.jsonl` | `${run_dir}/` | Post-token-length-filter examples |
| `deduped.jsonl` | `${run_dir}/` | Deduplicated examples |
| `train.jsonl` | `${output_dir}/staged/` | Training split |
| `val.jsonl` | `${output_dir}/staged/` | Validation split |
| `test.jsonl` | `${output_dir}/staged/` | Test split |
| `manifest.json` | `${output_dir}/` | Aggregate stats (total_enriched, accepted, rejected, rejection_reasons) |
| `rejections.jsonl` | `${output_dir}/` | Per-example rejection log with reason codes |
| `sft-corpus.last_harvested` | project root | UTC timestamp sentinel for incremental `stage` re-runs |

### Dependencies

- **Sub-loop**: Delegates to [`dataset-curation`](#) as the `curate` state for schema validation and quality checks
- **Python modules**: `little_loops.history_reader.lookup_session_metadata()` for metadata batch-join; `little_loops.pii.apply_pii_action()` for PII detection/redaction/discard; `little_loops.text_utils` (`extract_words`, `calculate_word_overlap`) for Jaccard dedup
- **CLI tool**: `ll-messages --sft-format --reader db` for DB-first transcript ingestion

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

---

## `oracles/implement-issue-chain`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/implement-issue-chain.yaml`

Reusable issue-implementation oracle. Drains the `recursive-refine-passed.txt` queue written by a calling loop's `recursive-refine` delegation: seeds a caller-prefixed impl-queue, pops each issue ID, gates it through `go-no-go`, and runs `ll-auto --only` to implement it. Skips issues already in `.issues/completed/`.

Used by `auto-refine-and-implement` and `sprint-refine-and-implement` as a `loop:` delegation state named `implement_chain` (ENH-1874).

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `caller_prefix` | yes | — | Prefix for queue and skip files under `.loops/tmp/` (e.g. `"auto-refine-and-implement"`). Prevents queue collisions when multiple loops run concurrently. |

### Invocation (thin-wrapper pattern)

```yaml
implement_chain:
  loop: oracles/implement-issue-chain
  with:
    caller_prefix: "my-loop-name"
  on_success: done
  on_failure: failed
  on_error: failed
```

### Internal state machine

```
get_passed_issues  (shell: seed impl-queue from recursive-refine-passed.txt)
  on_yes (queue non-empty) → implement_next
  on_no  (nothing to implement) → done

implement_next  (shell: pop head of impl-queue)
  on_yes (item popped) → go_no_go
  on_no  (queue empty) → done

go_no_go  (shell: ll-action invoke go-no-go --check --auto)
  on_yes → implement_issue
  on_no  → implement_next   (skip this issue)
  on_error → implement_issue (proceed on gate error)

implement_issue  (shell: ll-auto --only <issue-id>; fragment: with_rate_limit_handling)
  → implement_next  (unconditional; drain continues)
```

### Notes

- `shared_state_ok: true` is set at the loop level — the oracle reads `.loops/tmp/recursive-refine-passed.txt` written by the calling loop's `recursive-refine` sub-loop. This cross-run dependency is intentional.
- Issues already in `.issues/completed/` are silently skipped without calling `ll-auto`.

### Fragment dependency

Imports `lib/common.yaml` for `shell_exit` and `with_rate_limit_handling` fragments.

---

## `oracles/enumerate-and-prove`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/enumerate-and-prove.yaml`

Reusable enumeration-and-proof oracle. Parses a tagged `ENUMERATE_JSON:` line from captured LLM output, extracts and validates a targets list (up to 7 items), flattens it to a comma-joined string, and proves each target is ready-to-implement via the `ready-to-implement-gate` sub-loop. Eliminates the duplicated parse → flatten → prove state chain that previously appeared in both `adopt-third-party-api` and `integrate-sdk`.

Used by `adopt-third-party-api` and `integrate-sdk` as a `loop:` delegation state named `run_enumeration` (ENH-1873).

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `raw_enumeration` | yes | — | Captured LLM output containing the tagged JSON line (e.g. `${captured.enumerate_output.output}`) |
| `max_retries` | no | `"2"` | Per-target `explore-api` retries passed to `ready-to-implement-gate` |
| `tag` | no | `"ENUMERATE_JSON"` | Tag prefix to scan for in the LLM output (e.g. `"ENUMERATE_JSON"`) |

### Invocation (thin-wrapper pattern)

```yaml
run_enumeration:
  loop: oracles/enumerate-and-prove
  with:
    raw_enumeration: "${captured.enumerate_output.output}"
    max_retries: "3"
  on_success: done
  on_failure: failed
  on_error: failed
```

### Internal state machine

```
parse_enumeration  (shell: extract + validate ENUMERATE_JSON: line; fragment: parse_tagged_json)
  on_yes (count > 0) → flatten
  on_no  (no targets) → failed

flatten  (shell: join targets list to comma-separated string; captures: targets)
  → prove

prove  (sub-loop: ready-to-implement-gate; passes targets + max_retries)
  on_success → done
  on_failure → failed
  on_error   → failed
```

### Fragment dependency

Imports `lib/common.yaml` for the `parse_tagged_json` fragment used in `parse_enumeration`.

---

## `loop-composer`

**Category**: orchestration  
**File**: `scripts/little_loops/loops/loop-composer.yaml`

Decomposes a natural-language goal into an ordered DAG of up to 8 loop invocations, presents the plan for HITL approval, then walks the DAG sequentially. Returns a structured JSON summary of all step results. Imports shared DAG-walk logic from `lib/composer.yaml`.

### Invocation

```bash
ll-loop run loop-composer --input "your multi-step goal"

# Skip HITL approval
ll-loop run loop-composer --input "your goal" --context auto=true
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goal` | `""` | **Required.** Natural-language goal to decompose. Populated from `input_key: goal`. |
| `auto` | `"false"` | When `"true"`, skip HITL plan approval. |
| `exclude` | `""` | Comma-separated loop names to exclude from the catalog. |
| `max_plan_nodes` | `"8"` | Maximum steps allowed in a single plan. |

Config override: `orchestration.composer.max_plan_nodes` in `.ll/ll-config.json`.

### State Graph

```
discover_loops
  → decompose_goal
      → (auto=true) execute_plan
      → (auto=false) approve_plan
          on_yes  → execute_plan
          on_no   → revise_plan → approve_plan (loop)
  execute_plan  (walks DAG: invokes each sub-loop via ll-loop run)
      → summarize → done
      on_error → failed
```

---

## `loop-composer-adaptive`

**Category**: orchestration  
**File**: `scripts/little_loops/loops/loop-composer-adaptive.yaml`

Fault-tolerant variant of `loop-composer`. When a sub-loop fails a reassess gate decides `CONTINUE` / `REPLAN_TAIL` / `ABORT`. Completed steps are checkpointed; `REPLAN_TAIL` replaces only the unexecuted portion of the plan. Replanning is bounded by `max_replans` (default 2).

### Invocation

```bash
ll-loop run loop-composer-adaptive --input "your multi-step goal"

# Allow more replan attempts
ll-loop run loop-composer-adaptive --input "your goal" --context max_replans=3
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goal` | `""` | **Required.** Natural-language goal to decompose. |
| `auto` | `"false"` | Skip HITL plan approval when `"true"`. |
| `exclude` | `""` | Comma-separated loop names to exclude from catalog. |
| `max_plan_nodes` | `"8"` | Maximum steps in a single plan. |
| `max_replans` | `"2"` | Maximum tail-replan attempts before `ABORT`. |

Config overrides: `orchestration.composer.max_plan_nodes`, `orchestration.composer.adaptive.*`.

### State Graph

```
discover_loops → decompose_goal → [approve_plan] → execute_plan
                                                      on_success → (more steps?) execute_plan | summarize → done
                                                      on_failure → reassess
                                                                    CONTINUE    → execute_plan (next step)
                                                                    REPLAN_TAIL → replan_tail → execute_plan
                                                                    ABORT       → failed
                                                  (max_replans exhausted) → failed
```

---

## `goal-cluster`

**Category**: orchestration  
**File**: `scripts/little_loops/loops/goal-cluster.yaml`

Multi-goal batch orchestrator for sprint- or EPIC-shaped input. Normalizes a list of goals (raw multi-line, sprint name, EPIC ID, or JSON), groups them into batches by predicted loop, executes each batch sequentially with per-batch reassess gates, propagates cross-batch context hints, and synthesizes a cluster-wide summary.

### Invocation

```bash
# Multi-line goals
ll-loop run goal-cluster --input "Fix auth bug
Add retry logic"

# EPIC ID (expands to open child issues)
ll-loop run goal-cluster --input "EPIC-1811"

# JSON list
ll-loop run goal-cluster --input '[{"goal_id":"g01","goal_text":"Fix auth bug"}]'
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goals` | `""` | **Required.** Raw multi-line, sprint name, EPIC-NNN, or JSON list. |
| `auto` | `"false"` | Skip HITL plan review when `"true"`. |
| `exclude` | `""` | Comma-separated loop names to exclude from dispatch suggestions. |
| `max_batch_size` | `"5"` | Maximum goals per batch. |
| `enable_dedup` | `"true"` | Merge or skip overlapping goals before batching. |
| `propagate_context` | `"true"` | Extract cross-batch hints for injection into the next batch. |

Config overrides: `orchestration.cluster.*` in `.ll/ll-config.json`.

### State Graph

```
load_goals → normalize_goals → plan_batches → [approve_plan] → execute_batch
                                                                  on_success → extract_hints
                                                                                → (more batches) → execute_batch
                                                                                → synthesize → done
                                                                  on_failure → reassess
                                                                                CONTINUE/REPLAN → execute_batch
                                                                                ABORT → failed
```

### Dispatch guard

`loop-router` and `loop-composer` variants exclude `goal-cluster` from their catalogs. `goal-cluster` excludes `loop-composer` and `loop-router` from its own dispatch suggestions. This prevents recursive orchestration cycles.
