# Built-in Loop Reference

This document provides detailed reference information for selected built-in FSM loops.
For the full catalog see [LOOPS_REFERENCE.md](../guides/LOOPS_REFERENCE.md); for the conceptual guide see [LOOPS_GUIDE.md](../guides/LOOPS_GUIDE.md).

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
| `max_iterations` | `30` | Hard budget ceiling (context variable mirroring the top-level `max_steps`). |
| `STATE_NAME` | — | State-mode only. Name of the state being optimized; set by `dequeue_state` and read by `propose`, `apply`, and `write_trajectory_*`. |
| `EXAMPLES_FILE` | — | State-mode only. Path to the examples file for the current state; set by `dequeue_state` and injected into the `propose` prompt. |

### State Graph

```
init_run  (shell: create .ll/runs/harness-optimize-<unix-ts>/states/whole-file/ dir, capture traj_path)
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

Each iteration appends one JSON line to a trajectory file:

```json
{"iter": 3, "score": 0.82, "accepted": true, "commit_sha": "abc1234"}
{"iter": 4, "score": 0.79, "accepted": false, "commit_sha": ""}
```

The two modes write to **different roots** — `write_trajectory_accepted` /
`write_trajectory_rejected` branch on whether a state name is queued:

| Mode | Trajectory path |
|------|-----------------|
| whole-file (no state queue) | `.ll/runs/harness-optimize-<unix-ts>/states/whole-file/trajectory.jsonl` — minted by `init_run` and carried as `${captured.traj_path.output}` |
| state (queue non-empty) | `${context.run_dir}/states/<state>/trajectory.jsonl`, i.e. `.loops/runs/<instance-id>/states/<state>/trajectory.jsonl` — `run_dir` is injected by the runner (`cli/loop/run.py`), not by the loop |

In state mode `<state>` is the name of the state being optimized (e.g. `propose`,
`apply`). `load_directive`'s trajectory-resume scan searches under
`${context.run_dir}` only, so it recovers state-mode trajectories; whole-file
trajectories are read back through `traj_path` within the same run.

### Resume Behavior

On resume, `load_directive` reads the trajectory and checks out the best-scoring accepted commit's files before re-running the baseline. It also re-reads `.ll/program.md` to capture the Directive prose, ensuring the LLM proposal step has the optimization goal available even after a handoff. The run continues from the best known state, not the last attempted state.

### Scorer Contract

The scorer command must follow the Harbor scorer protocol:
- Exit 0 + bare float on stdout → `yes` (accepted score)
- Exit 0 + non-float stdout → `error`
- Exit non-zero → `no`

### Dependencies

Imports `lib/benchmark.yaml` (for the `run_benchmark` fragment) and `lib/common.yaml`.

### Output Artifacts

> **Runner-written files**: every loop run also produces `usage.jsonl` under `<run_dir>/` when at least one LLM action (prompt/slash_command) executes. Each line records `{iteration, state, action_type, input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens, model, timestamp}` plus the dotted OTel `gen_ai.usage.*` keys stamped alongside them (FEAT-2478; gated on `observability.otel_attributes.enabled`). Shell and mcp_tool actions produce no row. The file lives permanently at `.loops/runs/<id>/usage.jsonl` and is **not** archived to `.loops/.history/`.

In addition to trajectory JSONL files written under `${context.run_dir}/states/`, `harness-optimize` is a meta-loop and produces:

| File | Location | Description |
|------|----------|-------------|
| `<stem>.meta-eval.jsonl` | `.loops/.running/` (archived as `meta-eval.jsonl` under `.loops/.history/<run-id>-<loop-name>/`) | One entry per iteration that passes through an `llm_structured` evaluate state, pairing the LLM self-grade verdict with the external evaluator result. Fields: `iteration`, `ts`, `loop`, `state`, `llm_verdict`, `llm_rationale`, `external_verdict`, `external_state`, `external_evaluator`, `external_value`, `external_target`, `diff_stats`, `agreed`. |

---

## `workflow-generator`

**Category**: harness
**File**: `scripts/little_loops/loops/workflow-generator.yaml`

Meta-loop that lowers a prose brief into a reusable, validated FSM-loop YAML artifact. Six sequential "compiler lowering" passes (intent capture → state-graph sketch → evaluator attachment → routing-table resolution → artifact emission → optional adversarial minimum-coupling shrink), each LLM pass paired with a non-LLM `shell`/`exit_code` gate — MR-1 is satisfied by architecture, not a suppression flag. Does not delegate to `oracles/generator-evaluator` (that oracle scores visual/screenshot artifacts; this loop's artifact is FSM YAML, validated instead by `ll-loop validate`).

### Invocation

```bash
ll-loop run workflow-generator "triage a new bug report: read it, grep for the offending code, confirm repro, draft a fix plan, open a PR"
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `description` | `""` | **Required.** Prose brief describing the repeatable work to automate. |
| `enable_shrink` | `"false"` | Gate for the adversarial minimum-coupling shrink pass — off by default (no in-repo precedent, most outcome risk of the six passes). |
| `auto_promote` | `"false"` | Gate for the HITL promotion step — without it, the run stops at `await_confirmation` with the validated draft's path. |
| `max_emit_retries` | `"3"` | Bound on `emit_artifact` retries before routing to `diagnose`. |
| `loops_dir` | `".ll/loops"` | Promotion target directory. |

### State Graph

```
init → capture_intent → validate_intent (loops back on fail)
     → sketch_state_graph → validate_sketch (loops back on fail)
     → attach_evaluators → validate_evaluators (loops back on fail)
     → resolve_routing → validate_routing (loops back on fail)
     → emit_artifact → validate_artifact (`ll-loop validate`)
         on_no → count_emit_retry → emit_artifact (under limit) / diagnose (exhausted)
         on_yes → check_shrink_enabled
             on_no  → promotion_gate
             on_yes → shrink_baseline → shrink_select_candidate
                        → shrink_try_remove → shrink_probe_candidate
                            on_yes (outcome-neutral) → shrink_apply → shrink_select_candidate
                            on_no  (outcome changed) → shrink_select_candidate (try next)
                        (no candidates left) → promotion_gate
     → promotion_gate
         on_yes (auto_promote) → promote → done
         on_no  → await_confirmation (terminal)
diagnose → failed
```

### Shrink-pass probe

The shrink pass's discriminator is deliberately behavioral, not structural: `ll-loop validate` alone approves nearly every single-state removal (most still validate; routes degrade to warnings at worst), which is the toothless-evaluator failure mode `ll-loop diagnose-evaluators` exists to catch. The probe instead compares a full outcome tuple — `ll-loop simulate`'s reached terminal state, `ll-loop validate --json`'s violation set, and its warning count — between the candidate and the pre-removal baseline. A removal is kept only if all three are identical.

### Promotion

Promotion is HITL-gated (`auto_promote`, default off), mirroring `loop-composer`'s `auto: "false"` safe default: landing a runnable loop where `loop-router`/`loop-composer` can auto-select it has real blast radius. When enabled, the target name (derived from the emitted artifact's `name:` field) is checked against `ll-loop list --json` (built-ins + discovered project loops) and the loops dir itself; a collision appends a numeric suffix rather than overwriting, and a built-in name is never shadowed.

### v1 scope

FSM-YAML output only — a Workflow-JS output target is a follow-on gated by a lint-grade validator plus an execution shim for the `agent()`/`pipeline()` runtime globals. Prose-brief input only — mining `.ll/history.db` session traces for the brief is a follow-on.

---

## `deep-research`

**Category**: research
**File**: `scripts/little_loops/loops/deep-research.yaml`

Iterative web research synthesis loop. Accepts a research topic or question and delegates to the `oracles/research-coverage` oracle, which generates faceted search queries, performs web searches, evaluates and deduplicates sources, scores per-facet coverage, and iterates until coverage is sufficient. Produces a structured Markdown report with executive summary, key findings, source table, coverage gaps, and conclusion. Supports both general web research (default) and arxiv-only academic mode via `academic_mode=true`.

### Invocation

```bash
# Basic — positional arg injected into context.topic via input_key: topic
ll-loop run deep-research "What are the trade-offs of CRDT vs OT for collaborative editing?"

# Academic (arxiv-only) mode
ll-loop run deep-research "your research topic" \
  --context source_filter="site:arxiv.org" \
  --context academic_mode=true
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `topic` | `""` | **Required.** Research question or topic (injected from positional arg via `input_key: topic`). |
| `run_dir` | runner-injected | Per-run artifact directory (`.loops/runs/deep-research-{timestamp}/`); created automatically before the `init` state. Override with `--context run_dir=path/` to write to a fixed location. |
| `source_filter` | `""` | Site constraint appended to every search query (e.g. `"site:arxiv.org"`); empty string = web-wide. Forwarded to the `oracles/research-coverage` oracle. |
| `academic_mode` | `false` | Enable academic-specific behaviors: recency scoring axis, arxiv ID dedup, BibTeX section in the report, academic query terminology. Forwarded to the oracle. |
| `depth` | `3` | Declared in `deep-research` context but **not currently forwarded** to `oracles/research-coverage`; overriding via `--context depth=N` has no effect. Configure on the oracle directly if needed. |
| `coverage_threshold_pct` | `85` | Declared in `deep-research` context but **not currently forwarded** to `oracles/research-coverage`; overriding via `--context coverage_threshold_pct=N` has no effect. Configure on the oracle directly if needed. |

### State Graph

`deep-research` is a thin wrapper that delegates the full research FSM to `oracles/research-coverage`:

```
init  (shell: mkdir run_dir, touch 4 artifact files, capture run_dir)
  → run_research  (oracle: oracles/research-coverage;
                   passes run_dir, topic, source_filter, academic_mode)
      on_success → done  (terminal)
      on_failure → failed  (terminal)
      on_error   → failed  (terminal)
```

The oracle's internal chain is: `generate_queries → search_web → evaluate_sources → score_coverage → [plan_next →]* synthesize → done`.

### Output Artifacts

All artifacts are written to `${context.run_dir}` (the per-run directory injected by the runner):

| File | Description |
|------|-------------|
| `report.md` | Primary output — executive summary, key findings, source table, coverage gaps, conclusion |
| `knowledge-base.md` | Accumulated findings with `[Source: <url>]` (relevance: N/5, credibility: N/5) annotations |
| `coverage.md` | Per-facet coverage scores (1–5) updated each iteration; includes iteration count and average |
| `query-log.md` | All search queries grouped by iteration (`## Iteration N` blocks) |

### Convergence

Handled by `oracles/research-coverage`. The `score_coverage` state uses the **inline sentinel** pattern:

- Emits `COVERAGE_SUFFICIENT` when: average facet score ≥ 4.0 AND iteration ≥ `depth` (oracle default: 3)
- Emits `NEED_MORE` otherwise
- `on_error` routes to `synthesize` (write what we have; don't stall)

Knowledge accumulation: `knowledge-base.md` **appends** across iterations (sources accumulate); `coverage.md` **overwrites** each iteration (only latest score matters for routing).

---

## `apply-research`

**Category**: research
**File**: `scripts/little_loops/loops/apply-research.yaml`

Document ingestion pipeline for local research files. Accepts one or more paths to text, Markdown, or PDF files (space-separated), reads and understands each, scores ideas by relevance to the project, filters below a configurable threshold, synthesizes actionable issue descriptions, and captures Issues via `/ll:capture-issue`. Produces a summary report listing captured issue IDs, filtered counts, and run artifacts. PDF files are converted to Markdown sidecars via `pandoc` before reading (requires `pandoc ≥ 2.x` on PATH; `.txt` and `.md` files are read directly).

### Invocation

```bash
# Single file
ll-loop run apply-research "path/to/paper.pdf"

# Multiple files (space-separated)
ll-loop run apply-research "paper1.pdf notes.md rfc.txt"

# With higher relevance threshold
ll-loop run apply-research "paper.pdf" \
  --context relevance_threshold=0.7

# Cap issues per file
ll-loop run apply-research "paper.pdf notes.md" \
  --context max_issues_per_file=3
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `files` | `""` | **Required.** Space-separated file paths (injected from positional arg via `input_key: files`). |
| `relevance_threshold` | `"0.5"` | Items scoring below this relevance (0.0–1.0) are filtered and logged. Overridable via `--context relevance_threshold=0.7`. |
| `max_issues_per_file` | `"10"` | Cap on captured issues per file; survivors are ranked by `relevance × novelty` before the cap is applied. |

### State Graph

```
init  (shell: create run_dir artifacts; write pending-files.txt queue from context.files)
  → load_context  (shell: read CLAUDE.md + open issues into project-context.md)
    → read_file  (shell: pop next file from queue; pandoc PDF→MD if needed)
        on_yes (file popped) → extract_and_score
        on_no/on_error (queue empty) → finalize_report
      → extract_and_score  (prompt: read file via Read tool; emit RELEVANCE_SCORES: JSON)
        → validate_scores  (shell: parse JSON, validate 0–1 range; output count)
          on_yes (ge 0) → filter_items
          → filter_items  (shell: drop below threshold; cap at max_issues_per_file; output surviving count)
            on_yes (ge 1) → synthesize_recommendations
            on_no  (0 survivors) → next_file
          → synthesize_recommendations  (prompt: read filtered-items.json; emit RECOMMENDATION: blocks)
            → capture_issues  (prompt: invoke /ll:capture-issue per recommendation)
              → verify_captures  (shell: count confirmed .issues/ files; output count)
                → next_file
    → next_file  (shell: check pending-files.txt; exit 0=more, exit 1=empty)
        on_yes → read_file
        on_no/on_error → finalize_report
  finalize_report  (shell: read the total-*.txt counters + captured-issues.txt; emit summary table)
      next     → report   (terminal; no action)
      on_error → finalize_failed  (shell: emit fatal-init error, exit 1) → failed  (terminal)
```

`read_file` also routes `on_no` (queue empty) straight to `finalize_report`. The
report is produced by `finalize_report`; `report` is a bare terminal state that
does no work — the pair is the standard "do the work, then land on a clean
terminal" split, mirrored by `finalize_failed` → `failed` on the error path.

### Output Artifacts

All artifacts are written to `${context.run_dir}` (injected by the runner):

| File | Description |
|------|-------------|
| `pending-files.txt` | Remaining file queue; drained as files are processed |
| `project-context.md` | Snapshot of CLAUDE.md head + open issues table |
| `current-file.txt` | Path to the *source* file popped from the queue this iteration (pre-conversion) |
| `current-content-file.txt` | Path to the content file actually read (set each iteration) — same as `current-file.txt` except when a PDF was converted, where it points at the generated `.md` |
| `scored-items.json` | Validated relevance-scored items for the current file |
| `filtered-items.json` | Items surviving threshold and cap; input to synthesis |
| `captured-issues.txt` | Newline-separated list of confirmed captured issue IDs |
| `total-extracted.txt` | Running count of extracted items across all files |
| `total-filtered.txt` | Running count of filtered (dropped) items |
| `total-captured.txt` | Running count of confirmed captured issues |

### Non-LLM Evaluators (MR-1)

Two shell states provide non-LLM external validation:

- **`validate_scores`**: parses the `RELEVANCE_SCORES:` JSON block, validates each item's relevance is a float in `[0.0, 1.0]`, and outputs the count via `output_numeric`. Items with invalid scores are silently dropped before filtering.
- **`verify_captures`**: after `/ll:capture-issue` runs, counts how many claimed issue IDs actually exist on disk under `.issues/`; outputs the confirmed count via `output_numeric`. Accumulates IDs into `captured-issues.txt`.

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

Reusable iterative artifact generation oracle. Loops `generate → evaluate (Playwright screenshot) → score (LLM rubric)` until `ALL_PASS` or `max_steps`. Returns `done` on success; the calling thin-wrapper routes `on_yes` to its next state.

Used by `html-website-generator`, `html-anything`, `hitl-md`, `hitl-compare`, `svg-image-generator`, and `interactive-component-generator` as a `loop:` delegation state named `run_gen_eval` (ENH-1869).

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | Directory path for generated artifacts (relative or absolute; the `evaluate` action normalizes relative paths via `pwd` prefix). |
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
generate  (prompt: LLM renders artifact)
  on_yes/no/partial → evaluate    # route all verdicts to evaluate; on_error → failed
  on_error          → failed

evaluate  (fragment: playwright_screenshot)
  on_yes/no/error → snapshot      # graceful degradation if Playwright unavailable —
                                   # a timeout/failed capture arrives as on_no, not
                                   # on_error (output_contains never consults exit
                                   # code), so routing alone cannot discriminate a
                                   # bad artifact from a screenshot we never got

snapshot  (shell: copy artifact + screenshot to iter-N/ subdir for versioning;
           ENH-2903: also detects a missing/stale screenshot.png or a missing
           artifact copy and records the consecutive-miss count to
           ${run_dir}/.screenshot_misses)
  → score_gate  (unconditional)

score_gate  (shell: reads .screenshot_misses — ENH-2903)
  on_yes (miss count 0, fresh screenshot) → score
  on_no  (nonzero miss count)             → check_screenshot_abandon

check_screenshot_abandon  (shell: compares .screenshot_misses against a
                           max_step_attempts-style cap of 3 — ENH-2903)
  on_yes (cap breached)     → screenshot_abandoned_summary
  on_no  (below-cap miss)   → record_screenshot_skip

record_screenshot_skip  (shell: skip rubric-scoring this iteration — never scores
                         a stale/missing screenshot)
  → check_stall  (unconditional, rejoins the normal convergence chain)

screenshot_abandoned_summary  (shell: writes ${run_dir}/summary.json with an
                               "abandoned" key — MR-13 penultimate state)
  → screenshot_abandoned  (terminal, failure: true — downgraded verdict,
                           distinct from done)

score  (fragment: ll_rubric_score; local numeric-score override — emits SCORE: <0-10>)
  on_yes  → done  (terminal)
  on_no   → record_score
  on_error → generate

record_score  (shell: append parsed SCORE to ${run_dir}/.score_history)
  → check_stall  (unconditional)
  on_error → check_stall  # BUG-2824: a parse/write failure must not permanently
                          # starve check_stall's plateau detector of history

check_stall  (fragment: score_stall_gate; max_stall=2 — primary: score plateau)
  on_yes (score still improving) → check_diff_stall
  on_no  (score plateaued)       → done  (accept best-so-far)
  on_error                       → check_diff_stall

check_diff_stall  (fragment: diff_stall_gate; max_stall=3 — secondary/OR: byte plateau)
  on_yes (new changes observed) → generate
  on_no  (plateaued)            → done  (accept best-so-far)
  on_error                      → generate
```

**Budget** (BUG-2824): `max_steps: 40` — the fresh-screenshot cycle above costs
8 states (ENH-2903 added `score_gate`), so 40 buys 5 full scored iterations,
enough for `check_diff_stall`'s `max_stall: 3` to actually be reachable before
the step cap (the previous `max_steps: 20` capped the loop at ~2.8 cycles,
making the plateau detector structurally unreachable). `on_max_steps:
max_steps_summary` fires a terminal-doubling summary state (BUG-158 shape) on
exhaustion, so callers can distinguish "ran out of budget with usable output
on disk" from a genuine crash, instead of silently discarding a
generated-but-unscored artifact.

### Fragment dependency

Imports `lib/harness.yaml` for the `playwright_screenshot` fragment used in the `evaluate` state and the `ll_rubric_score` fragment used in the `score` state. See `## Fragment Catalog → lib/harness.yaml fragments` in `skills/create-loop/reference.md`.

---

## `rn-build`

Capstone orchestration loop for the recursive spec-to-project builder
(`category: orchestration`). Takes a spec file path (`required_inputs:
["spec"]`) and drives the full automated pipeline: spec validation → tech
research → design artifacts → commit → scope EPIC + feature stubs → issue
refinement → eval harness install → goal-cluster execution (dispatching
batches to `rn-implement` with `value_ranked` scheduling) → eval gate with
bounded re-entry → integration/acceptance gate (FEAT-2414: the spec's `##
Acceptance Criteria` are executed against the assembled, running project and
scored by a non-LLM gate) → synthesize result.

```bash
ll-loop run rn-build --context spec=<path>
```

`specs/SPEC_TEMPLATE.md` is the authoritative spec template (required
sections: Overview, Core Features, Acceptance Criteria); loosely-structured
specs are auto-normalized before `tech_research` without modifying the
original file. See `specs/sample.md` for a worked example.

## `rn-stepwise`

Same recursive decomposition walk as `rn-refine` (`category: planning`), but
each leaf is implemented and verified immediately after being refined —
before the walk continues to the next queued node — so implementation drift
is caught and corrected per-leaf instead of compounding across a whole tree
of unimplemented plans (ENH-2862).

This is a thin entry point: it does not fork `rn-refine`'s
decompose/refine/synth tree-walk logic. It sets `${context.stepwise}=1` (plus
a lower `max_nodes: 12` default vs. `rn-refine`'s planning-only default of 40
— implementation dominates runtime) and delegates the entire walk to
`rn-refine.yaml` via a `loop:` state. See `rn-refine.yaml`'s
`record_leaf`/`implement_leaf`/`verify_leaf`/`record_deviation`/`record_leaf_done`
chain for the actual per-leaf implement/verify/commit-or-revert mechanics.

```bash
ll-loop run rn-stepwise "path/to/plan.md"
```

---

## `oracles/generator-evaluator-cli`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/generator-evaluator-cli.yaml`

CLI-render oracle variant of `generator-evaluator`, created via `from: generator-evaluator` inheritance (first oracle to use `from:` — FEAT-2269). Overrides two states from the parent: `evaluate` (replaces Playwright screenshot with a caller-provided shell render command) and `snapshot` (replaces single `screenshot.png` copy with multi-file `views/*.png` copy, routing straight to `score` as before). All other states (`generate`, `score`, `record_score`, `check_stall`, `check_diff_stall`, `done`, `failed`) are inherited unchanged. `render_command`'s own `CAPTURED`/not-`CAPTURED` evaluator already discriminates a failed render (`on_no`/`on_error → failed`) before `snapshot` ever runs, so this variant does not need the ENH-2903 `score_gate`/`check_screenshot_abandon` screenshot-miss chain the parent gained — those inherited states remain present but unreachable here (allowlisted in `test_deterministic_warning_categories_do_not_regrow`).

Intended for any CLI-rendered artifact: OpenSCAD, graphviz, manim, CNC toolchains, etc. Currently used only by `openscad-model-generator` as a reusable component; `openscad-model-generator` invokes the oracle directly for its inner generate → render → score cycle.

### Parameters

Inherits all parameters from `generator-evaluator`, plus:

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | (inherited) Directory path for generated artifacts |
| `generate_prompt` | yes | — | (inherited) Full LLM prompt for the `generate` state |
| `rubric` | no | `""` | (inherited) Rubric criteria markdown |
| `pass_threshold` | no | `6` | (inherited) Minimum score per criterion |
| `artifact_path` | no | `"index.html"` | (inherited) Main artifact filename for snapshot copy |
| `render_command` | yes | — | Shell script that renders the artifact into `views/` under `run_dir` and echoes `CAPTURED` on success. Exit 0 with no `CAPTURED` output on binary-missing (routes `on_no → failed`). |

### Invocation (thin-wrapper pattern)

```yaml
run_gen_eval:
  loop: oracles/generator-evaluator-cli
  with:
    run_dir: ${captured.run_dir.output}
    artifact_path: "model.scad"
    generate_prompt: |
      Write model.scad to ${captured.run_dir.output}/ ...
    render_command: |
      if ! command -v openscad >/dev/null 2>&1; then
        echo "OPENSCAD_MISSING"; exit 0
      fi
      # ... render loop ...
      echo "CAPTURED"
    rubric: |
      Read views/view_0.png, view_1.png, view_2.png ...
    pass_threshold: 6
  on_yes: vision_gate
  on_no: diagnose
  on_error: diagnose
```

### Internal state machine (inherited from generator-evaluator, overridden states marked *)

```
generate   (prompt: LLM renders artifact via generate_prompt)
  on_yes/no/partial → evaluate    # unconditional forward
  on_error          → failed

evaluate * (shell: runs render_command; echoes CAPTURED on success)
  on_yes   → snapshot
  on_no    → failed   # render failed or binary missing
  on_error → failed

snapshot * (shell: copies artifact_path + views/*.png to iter-N/)
  → score  (unconditional)

score      (fragment: ll_rubric_score; inherited — numeric-score override + capture)
  on_yes  → done  (terminal)
  on_no   → record_score
  on_error → generate

record_score (shell: append parsed SCORE to ${run_dir}/.score_history; inherited)
  → check_stall  (unconditional)
  on_error → check_stall  # BUG-2824: inherited from the parent's fix

check_stall (fragment: score_stall_gate; inherited — primary: score plateau)
  on_yes → check_diff_stall
  on_no  → done
  on_error → check_diff_stall

check_diff_stall (fragment: diff_stall_gate; inherited — secondary/OR: byte plateau)
  on_yes → generate
  on_no  → done
  on_error → generate
```

**Budget** (BUG-2824): `max_steps: 40` and `on_max_steps: max_steps_summary`
are inherited unchanged from the parent — the `-cli` oracle picks up the
recalibrated budget and the terminal-doubling summary state for free via
`from:` resolution.

### Snapshot behavior difference from parent

The parent `generator-evaluator` snapshot copies `screenshot.png` (single file). The CLI oracle snapshot iterates `views/*.png` to capture all N rendered view files. This multi-file snapshot is required for multi-angle renders (OpenSCAD iso/front/top) where each angle produces an independent PNG.

---

## `oracles/research-coverage`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/research-coverage.yaml`

Reusable iterative web research synthesis oracle. Runs `generate_queries → search_web → evaluate_sources → score_coverage` until coverage is sufficient, then `synthesize → done`. Parameterized for both general web research and arxiv-only academic research.

Used by `deep-research` (general web, `source_filter=""`, `academic_mode=false`) as a `loop:` delegation state named `run_research`; `deep-research-arxiv` inherits from `deep-research` via `from:` and inherits the same delegation (ENH-1876, FEAT-1540/1673).

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

## `oracles/code-run-gate`

**Category**: oracle sub-loop
**File**: `scripts/little_loops/loops/oracles/code-run-gate.yaml`

Reusable Tier-1 deterministic oracle (FEAT-2551). Runs the project's `build` / `test` / `typecheck` / `lint` / `service_health` command matrix and emits `GATE_PASS` / `GATE_FAILED` / `GATE_SKIP` via the parent↔sub-loop token channel. Resolves commands from `.ll/ll-config.json` `project.*` with alias support per ARCHITECTURE-123 (`type_cmd`/`typecheck_cmd`, `run_cmd`/`start_cmd`). When ALL six command fields are null/empty, the oracle emits `GATE_SKIP` and routes to `done` (docs-only no-op pass). Each individual null command short-circuits its `run_*` state to a SKIP pass-through.

Used by FEAT-2552's wiring into `rn-implement` / `rn-remediate` (F2b). Safe to call directly via `ll-loop run oracles/code-run-gate` with `parameters.run_dir` pointing at a per-invocation absolute path.

### Parameters

| Parameter | Required | Default | Description |
|-----------|----------|---------|-------------|
| `run_dir` | yes | — | Per-invocation absolute path for artifact isolation (MR-3) |
| `issue_id` | yes | — | Token-channel identifier used in `subloop_outcome_<ID>.txt` |
| `min_pass_rate` | no | `0.95` | Pass-rate threshold, enforced by both `run_test`'s `output_numeric` evaluator and `aggregate`'s independent pass_rate detector |
| `health_bound_seconds` | no | `10` | `curl --max-time` budget for `service_health` probe |
| `build_cmd` | no | (from config) | Optional build command — null skips `run_build` |
| `test_cmd` | no | (from config) | Optional test command — null skips `run_test` |
| `typecheck_cmd` | no | (from config) | Optional type-check command — alias of `type_cmd` |
| `lint_cmd` | no | (from config) | Optional lint command — null skips `run_lint` |
| `run_cmd` | no | (from config) | Optional run/start command — alias of `start_cmd` |
| `health_url` | no | (from config) | URL to probe for service readiness — null skips `service_health` |

### Internal state machine

```
resolve_commands ──(writes commands.json + subloop_outcome_<ID>)──> run_build
   │                                                                     │
   └── all null ──> echo GATE_SKIP, exit 0 ───────────────────────────────┤
                                                                         ▼
                                              run_build  ─(self-skip if null)─> run_test
                                                                         ▼
                                              run_test   ─(self-skip if null)─> run_typecheck
                                                                         ▼
                                              run_typecheck ─(self-skip)─> run_lint
                                                                         ▼
                                              run_lint   ─(self-skip if null)─> service_health
                                                                         ▼
                                              service_health (PID + curl --fail) ─> aggregate
                                                                         ▼
                                              aggregate (classify + route:) ─> done | failed
```

### MR-1 / MR-3 compliance

- **MR-1 (trivial)**: only `exit_code` / `output_numeric` / `classify` evaluators — never `llm_structured` / `comparator` / `contract`. The oracle is not classified as a meta-loop (actions only write under `${context.run_dir}/`, never to harness artifacts), so MR-1 does not fire.
- **MR-3 (per-run isolation)**: every artifact (`commands.json`, `build.txt`, `test-results.txt`, `pytest.json`, `typecheck.txt`, `lint.txt`, `health.txt`, `service.pid`, `subloop_outcome_<ID>.txt`, `prepatch_evidence_<issue_id>.json` when `prepatch_check:` is set — ENH-2997) lives under `${context.run_dir}/`. No bare `.loops/tmp/` writes.

### Invocation (direct, for testing)

```yaml
run_code_run_gate:
  loop: oracles/code-run-gate
  with:
    run_dir: "/abs/path/.loops/runs/code-run-gate/<issue-id>/<run-uuid>"
    issue_id: "FEAT-XXXX"
    min_pass_rate: "0.95"
    health_bound_seconds: "10"
  on_success: done
  on_failure: failed
  on_error: failed
```

---

## `loop-composer`

**Category**: orchestration  
**File**: `scripts/little_loops/loops/loop-composer.yaml`

Decomposes a natural-language goal into an ordered DAG of up to 8 loop invocations, presents the plan for HITL approval, then walks the DAG sequentially. Returns a structured JSON summary of all step results. Imports shared DAG-walk logic from `lib/composer.yaml`.

### Invocation

```bash
ll-loop run loop-composer "your multi-step goal"

# Skip HITL approval
ll-loop run loop-composer "your goal" --context auto=true
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goal` | `""` | **Required.** Natural-language goal to decompose. Populated from `input_key: goal`. |
| `auto` | `"false"` | When `"true"`, skip HITL plan approval. |
| `include` | `""` | Allowlist: comma-separated selectors (`loop-name`, `builtin:*`, `project:*`, `category:<label>`); empty = all loops |
| `exclude` | `""` | Comma-separated loop names to exclude from the catalog. |
| `max_plan_nodes` | `"8"` | Maximum steps allowed in a single plan. |

Config override: `orchestration.composer.max_plan_nodes` in `.ll/ll-config.json`.

### State Graph

```
discover_loops
  → decompose_goal
      → parse_plan → validate_plan → check_auto_plan
          → (auto=true) execute_plan
          → (auto=false) present_plan (fragment: HITL approval)
              on_yes  → execute_plan
              on_no   → present_result (terminal)
  execute_plan  (walks DAG via dispatch_step → loop: <next_step_loop>)
      on_error → failed
  present_result (terminal: emit JSON plan + step_results + summary)
```

---

## `loop-composer-adaptive`

**Category**: orchestration  
**File**: `scripts/little_loops/loops/loop-composer-adaptive.yaml`

Fault-tolerant variant of `loop-composer`. When a sub-loop fails a reassess gate decides `CONTINUE` / `REPLAN_TAIL` / `ABORT`. Completed steps are checkpointed; `REPLAN_TAIL` replaces only the unexecuted portion of the plan. Replanning is bounded by `max_replans` (default 2).

### Invocation

```bash
ll-loop run loop-composer-adaptive "your multi-step goal"

# Allow more replan attempts
ll-loop run loop-composer-adaptive "your goal" --context max_replans=3
```

### Context Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `goal` | `""` | **Required.** Natural-language goal to decompose. |
| `auto` | `"false"` | Skip HITL plan approval when `"true"`. |
| `include` | `""` | Allowlist: comma-separated selectors (`loop-name`, `builtin:*`, `project:*`, `category:<label>`); empty = all loops |
| `exclude` | `""` | Comma-separated loop names to exclude from catalog. |
| `max_plan_nodes` | `"8"` | Maximum steps in a single plan. |
| `max_replans` | `"2"` | Maximum tail-replan attempts before `ABORT`. |

Config overrides: `orchestration.composer.max_plan_nodes`, `orchestration.composer.adaptive.*`.

### State Graph

```
discover_loops → decompose_goal → [approve_plan] → execute_plan
                                                      on_success → (more steps?) execute_plan | summarize → present_result (terminal)
                                                      on_failure → reassess
                                                                    CONTINUE    → execute_plan (next step)
                                                                    REPLAN_TAIL → route_reassess_replan → check_replan_budget
                                                                    ABORT       → finalize_abort_composer
                                        (any abort path) → finalize_abort_composer → abort_composer (terminal, failure: true)
```

The `REPLAN_TAIL` tail is four real states, not one:

```
route_reassess_replan   (only an actual REPLAN_TAIL token consults the budget)
  on_yes → check_replan_budget      (reads replan_count.txt BEFORE increment, so
                                     max_replans=N permits exactly N replans)
    on_yes → increment_replan_count (writes the bumped count back)
      next → apply_replan           (merges succeeded steps + the new tail)
        next → validate_replan      (fragment: validate_plan — re-runs the initial
                                     plan validation over the merged plan)
          on_yes → execute_plan
```

Every `on_no` / `on_error` in that chain routes to `finalize_abort_composer`. The
abort terminal is `abort_composer` (declared `failure: true`), reached only via
`finalize_abort_composer`; there is no bare `failed` state on this path. `CONTINUE`
and `ABORT` decisions never reach `check_replan_budget`, so they do not consume
replan budget.

---

## `goal-cluster`

**Category**: orchestration  
**File**: `scripts/little_loops/loops/goal-cluster.yaml`

Multi-goal batch orchestrator for sprint- or EPIC-shaped input. Normalizes a list of goals (raw multi-line, sprint name, EPIC ID, or JSON), groups them into batches by predicted loop, executes each batch sequentially with per-batch reassess gates, propagates cross-batch context hints, and synthesizes a cluster-wide summary.

### Invocation

```bash
# Multi-line goals
ll-loop run goal-cluster "Fix auth bug
Add retry logic"

# EPIC ID (expands to open child issues)
ll-loop run goal-cluster "EPIC-1811"

# JSON list
ll-loop run goal-cluster '[{"goal_id":"g01","goal_text":"Fix auth bug"}]'
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
| `max_replans` | `"1"` | Maximum reassess replan attempts per cluster run; exceeding it routes to `finalize_abort_cluster`. |
| `schedule_mode` | `"fifo"` | Scheduling mode passed through to dispatched batches. `"value_ranked"` hands value-ranked scheduling to `rn-implement`. |

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

`loop-router` and `loop-composer` variants exclude `goal-cluster` from their catalogs. `goal-cluster` excludes `loop-composer`, `loop-composer-adaptive`, and itself (`goal-cluster`) from dispatch suggestions; `loop-router` is the suggested fallback when uncertain. This prevents recursive orchestration cycles.

---

## Circuit Breaker (`circuit:`)

The `circuit:` top-level key groups loop-level safety guards. Currently it exposes `repeated_failure`, the stall detector (FEAT-1637).

### `circuit.repeated_failure`

Fires when the FSM keeps producing the same `(state, exit_code, verdict)` triple, indicating the loop is stuck. When triggered, either aborts the run (`terminated_by="stall_detected"`) or routes to a named recovery state. A `stall_detected` event is emitted to the event bus.

```yaml
circuit:
  repeated_failure:
    window: 3                      # consecutive identical triples required (default: 3)
    on_repeated_failure: abort     # "abort" or a declared state name
    progress_paths: []             # BUG-1674: reset window when any path changes
    exclude_paths: []              # BUG-1767: exclude bookkeeping files from fingerprint
    recurrent_window: null         # ENH-2245: total-occurrence threshold (non-consecutive)
```

| Key | Default | Description |
|-----|---------|-------------|
| `window` | `3` | Consecutive identical triples required to fire the consecutive stall guard |
| `on_repeated_failure` | `"abort"` | `"abort"` terminates the run; any declared state name routes there instead |
| `progress_paths` | `[]` | Paths to watch for `(mtime, size)` changes; a change resets the consecutive window |
| `exclude_paths` | `[]` | Paths excluded from the fingerprint (loop bookkeeping files that shouldn't reset the window) |
| `recurrent_window` | `null` | **ENH-2245**: Fire when the same triple has been seen this many times *total* in the run (non-consecutive). `null` = disabled. Minimum: 2 |

#### `recurrent_window` — catching cycling loops

The consecutive guard (`window`) only fires when the same triple appears N times *in a row*. Loops that rotate through intermediate states between each failure are never flagged:

```
run_final_tests(fail) → continue_work → select_step → do_work → verify_step
  → run_final_tests(fail) → ...   (8 states between each failure — never consecutive)
```

`recurrent_window: 5` catches this: after the 5th total occurrence of `(run_final_tests, 1, no)`, the circuit fires and routes to `on_repeated_failure`. The `stall_detected` event payload uses `recurrent` (total count) instead of `consecutive`.

```yaml
circuit:
  repeated_failure:
    on_repeated_failure: diagnose
    recurrent_window: 5
    exclude_paths:
      - "${context.run_dir}/plan.md"
      - "${context.run_dir}/dod.md"
```

**Note (BUG-3270):** `general-task.yaml` now carries a dedicated
`final_verify_spin_gate` state for the narrower, undominated case above the
worked example was originally written to catch — the direct
`continue_work → final_verify → run_final_tests → continue_work` cycle where
`continue_work` finds nothing left to remediate on every lap. That gate is a
working-tree content fingerprint (not `recurrent_window`), because it needed
to distinguish a byte-identical lap from one that legitimately re-attempts a
fix; see `general-task.yaml`'s `final_verify_spin_gate` state and
`.issues/bugs/` history for BUG-3270. `recurrent_window` remains the right
mechanism for the broader, multi-state remediation cycle shown above
(`run_final_tests → continue_work → select_step → do_work → verify_step →
run_final_tests`) — a real code change between failures resets
`final_verify_spin_gate`'s fingerprint even though the suite keeps failing,
so only `recurrent_window`'s total-occurrence count catches that shape.
