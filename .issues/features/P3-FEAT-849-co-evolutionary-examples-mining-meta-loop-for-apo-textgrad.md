---
id: FEAT-849
type: FEAT
priority: P3
discovered_date: 2026-03-20
discovered_by: capture-issue
confidence_score: 98
outcome_confidence: 79
---

# FEAT-849: Co-evolutionary Examples Mining Meta-Loop for apo-textgrad

## Summary

Build a continuous, self-calibrating meta-loop that mines completed issues and session logs to produce an adaptive `examples.json` for `apo-textgrad`. The mining loop and the optimization loop are coupled: each optimization cycle's gradient signal drives adversarial example generation in the next mining cycle, and the example corpus is continuously re-calibrated to the current prompt's capability level.

## Current Behavior

`apo-textgrad` requires a manually created `examples.json`. There is no mechanism to source examples from the project's existing history — 784+ completed issues and hundreds of linked session logs contain real labeled invocations but none of it is harvested. The corpus is static; once created it never updates to reflect evolved conventions or harder edge cases.

## Expected Behavior

A loop (`examples-miner.yaml` or similar) runs as a wrapper around `apo-textgrad` that:

1. **Harvests** skill invocations from all session logs linked in completed issues (`## Session Log` entries). When multiple invocations of the same skill exist for an issue, candidates are ranked by downstream stability — the last invocation before the issue advanced, weighted by how long that output persisted in the codebase unmodified — and only the highest-ranked candidate is forwarded to the judge step
2. **Judges** each harvested candidate through a three-layer quality stack: (1) **Code persistence + persistence age** (primary) — checks whether `files_modified` from the invocation still exist in `HEAD` via `git blame`; weights by commit count since introduction without a revert; BUG fixes still present mean the fix held; FEAT/ENH code still present means it was valuable enough to keep; (2) **Revision distance** (secondary) — `git diff` the issue file between the commit immediately following the invocation and the final completed state; low edit distance signals the output was accepted nearly as-is; (3) **Oracle rubric** (tertiary) — a skill-scoped prompt scores outputs that survive the behavioral gates against structured criteria. Completing an issue is not treated as a quality signal on its own; only pairs that clear all three layers enter the calibrated pool
3. **Calibrates** the active example set to the informative difficulty band (40–80% pass rate against the current prompt) — trivially easy examples are retired, noise-level hard examples are excluded
4. **Synthesizes** new adversarial examples by reading `FAILURE_PATTERN`/`ROOT_CAUSE` from the most recent `apo-textgrad` run and applying a named perturbation type to the **inputs** of passing examples — expected outputs are never carried over; they are regenerated fresh for each perturbed input to prevent ground-truth corruption. Perturbation taxonomy (gradient `FAILURE_PATTERN` selects which type to apply):
   - **Complexity injection**: add a second symptom that may or may not belong in the same issue — tests scope boundary judgment
   - **Ambiguity injection**: strip specific file/function names from the description, forcing the model to discover rather than copy references
   - **Domain shift**: same failure pattern reproduced in a different subsystem — tests generalization vs. overfitting
   - **Priority boundary**: edge case sitting between two adjacent priority levels — exercises the decision criteria
   - **Type confusion**: description that looks like FEAT but is BUG, or vice versa — tests classification robustness

   Synthesized pairs are quality-gated by the oracle (both phases) before corpus inclusion and compete for corpus slots on equal footing with harvested examples. At most 25–30% of the final corpus may have `source: adversarial` at any time.
5. **Diversifies** via a coverage budget: at least N examples per skill type, issue type, priority band, lifecycle stage, and failure cluster
6. **Publishes** a fresh `examples.json` with per-example metadata (provenance, difficulty score, failure cluster, freshness weight)
7. **Maintains** a living corpus: new completions enter the harvest queue automatically; stale examples decay in weight; an archived regression floor prevents backward drift

## Use Case

**Who**: Developer or automation engineer running `ll-loop` prompt optimization

**Context**: After `apo-textgrad` has plateaued on hand-crafted examples, or after skill conventions have evolved and the static corpus is stale

**Goal**: Have `examples.json` regenerated automatically from real project history — 784+ completed issues and session logs — with adversarial examples targeting the current gradient's failure pattern

**Outcome**: `apo-textgrad` receives a continuously calibrated, adversarially enriched corpus that stays ahead of the prompt's current capability, producing ongoing gradient signal rather than convergence to a local optimum

## Acceptance Criteria

- [x] `ll-loop run loops/examples-miner.yaml` harvests skill invocations from all session logs linked in completed issues via `## Session Log` entries
- [x] Each harvested candidate passes a three-layer quality stack before corpus inclusion: (1) code persistence check — `files_modified` still present in `HEAD` with persistence age computed; (2) revision distance check — low edit distance between post-invocation state and final completed state; (3) oracle rubric scoring — only survivors of both behavioral gates are oracle-scored
- [x] When multiple invocations of the same skill exist for an issue, candidates are ranked by downstream stability and only the highest-ranked is forwarded
- [x] Only pairs that clear all three quality layers and fall in the 40–80% pass-rate band are included in the active calibrated set
- [x] Trivially easy (>80% pass rate) and noise-level hard (<40% pass rate) examples are excluded from the corpus
- [x] After an optimizer run, adversarial examples are synthesized by perturbing passing example inputs using the type matched to `FAILURE_PATTERN`; original expected outputs are never reused
- [x] `source: adversarial` examples are capped at ≤30% of the final corpus at all times
- [x] Published `examples.json` includes per-example metadata: `source`, `perturbation_type`, `seed_id`, `difficulty_score`, `failure_cluster`, `freshness_weight`
- [x] New completions from subsequent issues enter the harvest queue automatically; stale examples decay in weight via freshness field
- [x] Loop terminates with a fresh `examples.json` written to `context.examples_file`

## Motivation

`apo-textgrad` is only as good as its examples. A static hand-crafted `examples.json` optimizes the prompt for known cases while leaving blind spots untouched. The project already has the labeled dataset — completed issues with accepted outputs are implicit human approvals — it just lacks the mining step. Without adaptive calibration, the corpus goes stale as the prompt improves and new conventions emerge. Without adversarial synthesis, the gradient signal only covers patterns already in the corpus. The co-evolutionary design ensures the example difficulty always leads the prompt's current capability, producing continuous improvement rather than convergence to a local optimum.

## Proposed Solution

A two-loop architecture using FSM sub-loop chaining:

**Outer loop** (`examples-miner.yaml`): harvest → judge → calibrate → run_optimizer (sub-loop) → synthesize → screen_adversarial → score_adversarial → merge → diversify → publish
**Inner loop** (`apo-textgrad`): test → gradient → apply → iterate

The outer loop invokes `apo-textgrad` as a child FSM via `loop: apo-textgrad` + `context_passthrough: true` in the `run_optimizer` state. The child's gradient output (`FAILURE_PATTERN`, `ROOT_CAUSE`, `GRADIENT`) is available in the parent as `${captured.run_optimizer.gradient.output}` for the `synthesize` state. The inner loop reads `examples.json` published by the outer loop via its `context.examples_file`. Both loops run within a single `ll-loop run` invocation — no file I/O required to pass the gradient signal.

Key components:
- **Harvest script** (extend `ll-messages`): `--skill` filter + `--examples-format` flag that extracts (invocation context, accepted output) pairs from `.jsonl` logs
- **Oracle prompt**: skill-scoped, not universal — one rubric per skill being optimized (e.g., a `capture-issue` oracle is distinct from a `refine-issue` oracle); the oracle prompt accepts a `skill_name` parameter and applies the corresponding rubric. Two phases: (1) mechanical/deterministic checks (schema conformance, file path existence, line number plausibility, required section presence) run first at zero LLM cost; (2) semantic LLM scoring (motivation coherence, codebase reference accuracy, implementer actionability) runs only for outputs that pass phase 1. The oracle is **manually maintained** in v1 — do not attempt to optimize it via `apo-textgrad` itself, as that requires a meta-oracle to score oracle scores (circular rabbit hole). Calibrate via **ensemble agreement bootstrapping** rather than assumed-good fixtures: run multiple oracle variants (different temperatures, different prompt phrasings) against the full candidate pool; examples where all variants agree strongly become the fixture set — their label is stable regardless of whether the ground truth is known. Rather than pre-specifying a variance threshold, select the top-N% of candidates by stability where N is chosen so you have at least 10 fixture examples; observe the resulting distribution on the first run and tighten or loosen from there. Validate the ensemble against deliberately degraded examples (strip required sections, corrupt file paths in known candidates) — if the ensemble does not reliably score them low, the oracle is miscalibrated. If oracle scores on the fixture set drift across consecutive runs, halt rather than corrupt the corpus
- **Calibration state**: run current prompt against all candidates, compute pass rates, select 40–80% band
- **Adversarial synthesizer**: LLM-guided perturbation of passing examples using the current gradient
- **Diversity budget**: enforced per-axis coverage constraints

## API/Interface

New loop invocation (external interface):

```bash
ll-loop run loops/examples-miner.yaml
```

New loop YAML (context contract for `examples-miner.yaml`):

```yaml
context:
  examples_file: examples.json       # path where fresh corpus is published
  prompt_file: <skill-prompt-path>   # prompt being optimized (passed to apo-textgrad)
  skill_name: <skill-name>           # skill to mine (e.g., capture-issue, refine-issue) — used by harvest state
  corpus_state_file: corpus.json     # optional: persisted calibration state across runs
  target_pass_rate: 0.6              # center of 40–80% band
```

Python API changes (ExampleRecord dataclass, `build_examples()`, `--skill`, `--examples-format` flags) are specified and owned by FEAT-850. No direct Python public API additions in this issue.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — add `--skill` filter and `--examples-format` output mode (`main_messages()` at line 11 is the CLI entry point)
- `scripts/little_loops/user_messages.py` — add `ExampleRecord` dataclass and `build_examples()` helper (covered by FEAT-850; also the harvest foundation via `extract_user_messages()` at line 383)
- `loops/apo-textgrad.yaml` — add optional `examples_miner` pre-step or document pairing pattern

### Dependent Files (Callers/Importers)
- `loops/examples-miner.yaml` (new) — the outer loop definition
- Any `apo-*.yaml` loop that uses an `examples_file` context variable

### Similar Patterns
- `loops/apo-textgrad.yaml` — inner loop being wrapped
- `loops/apo-opro.yaml` — similar prompt optimization pattern
- `scripts/little_loops/cli/messages.py` + `scripts/little_loops/user_messages.py` — source of session log parsing logic

### Tests
- TBD — unit tests for harvest script (`--examples-format` output)
- TBD — integration test: mine a small fixture corpus, verify examples.json schema

### Documentation
- `loops/README.md` — document the miner/optimizer pairing pattern
- `docs/guides/` — add guide for setting up apo-textgrad with a live corpus

### Configuration
- `loops/examples-miner.yaml` — new loop config
- `context.examples_file` in `apo-textgrad.yaml` — path to published examples (`apo-textgrad.yaml:14`: `context.examples_file: examples.json`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Gradient output format (`apo-textgrad.yaml:29–40`):**
- Captured in `captured.gradient.output`; the outer loop reads this from the inner loop's most recent run
- Structured as three lines: `FAILURE_PATTERN: <common theme>`, `ROOT_CAUSE: <what is wrong>`, `GRADIENT: <how to change>` (lines 36–38)
- Convergence signal: `CONVERGED` on its own line when `PASS_RATE >= target_pass_rate`

**Session log harvesting API:**
- `scripts/little_loops/session_log.py:23` — `parse_session_log(content)` extracts JSONL file paths from a completed issue's `## Session Log` section via `_SESSION_LOG_SECTION_RE` regex; returns distinct `/ll:*` command names
- `scripts/little_loops/issue_history/parsing.py:23` — `parse_completed_issue(file_path)` parses completed issues; scan `.issues/completed/` to enumerate the corpus
- `scripts/little_loops/user_messages.py:354` — `get_project_folder(cwd)` maps CWD → `~/.claude/projects/{encoded-path}/`; individual JSONL files discovered via `project_folder.glob("*.jsonl")`
- JSONL record structure: `{type, message, sessionId, uuid, timestamp, cwd, gitBranch, isSidechain}`; user records have `message.content` as string (real input) or array (tool results — skip)
- Skill detection: filter user records where `message.content` matches `r'/ll:?SKILL_NAME'`, or assistant records where `message.content` contains a `Skill` tool_use block (pairs with `--include-response-context` in `user_messages.py:388`)

**FSM loop YAML schema (for `examples-miner.yaml`):**
- Top-level: `name`, `description`, `initial`, `max_iterations`, `timeout`, `on_handoff: spawn`, `context`
- Context block: `examples_file`, `prompt_file`, optionally `corpus_state_file`, `target_pass_rate` (40–80 calibration band)
- State fields: `action_type: prompt|shell`, `timeout`, `action` (interpolates `${context.*}` and `${captured.*.output}`), `capture`, `next`, `on_blocked`
- Routing state fields: `evaluate: {type: output_contains, source: ..., pattern: ...}`, `on_yes`, `on_no`, `on_error`
- Reference implementations: `loops/apo-textgrad.yaml` (gradient-driven), `loops/apo-opro.yaml` (history-guided with `score_history` capture chain)

**Gradient persistence — decided: FSM sub-loop with `context_passthrough: true` (option b):**
- `captured.gradient.output` lives only in memory per `ll-loop run` invocation; it is **not** written to disk automatically. The chosen mechanism is FSM sub-loop chaining so that `examples-miner.yaml` invokes `apo-textgrad` as a child loop within a single run and reads its gradient directly from the merged captures.
- **Mechanism** (`scripts/little_loops/fsm/schema.py:230-231`, `scripts/little_loops/fsm/executor.py:571-619`): a state sets `loop: apo-textgrad` and `context_passthrough: true`. The executor loads the child FSM, merges parent context + captures into the child's context, runs the child to completion, then stores the child's full `captured` dict into the parent's `captured` dict keyed by the state name (e.g., state name `run_optimizer` → `captured.run_optimizer.*`). Routing uses `on_success` / `on_failure` (aliases for `on_yes` / `on_no`).
- **Exact YAML syntax** for the miner's optimizer invocation state:
  ```yaml
  run_optimizer:
    loop: apo-textgrad
    context_passthrough: true
    on_success: synthesize     # child terminated cleanly → proceed to adversarial synthesis
    on_failure: publish        # child hit max_iterations/timeout → skip synthesis, publish anyway
  ```
- **Accessing child captures** in subsequent states: the child's `captured.gradient.output` is available in the parent as `${captured.run_optimizer.gradient.output}` (child captures nested under the invoking state's name per `executor.py:611-612`).
- **Persistence** (`scripts/little_loops/fsm/persistence.py:83`, `persistence.py:466`): the parent's `captured` dict (including the nested child captures) is written on every `state_enter` and `loop_complete` event and restored on resume — so a mid-run restart does not lose gradient data from a completed `run_optimizer` state.
- **Mutual exclusion** (`scripts/little_loops/fsm/validation.py:198-206`): a state with `loop:` cannot also have `action:` — `run_optimizer` must be a pure sub-loop delegation state with no action.
- **No changes to `apo-textgrad.yaml`** required: the child loop runs as-is; its terminal state already resolves with `terminated_by == "terminal"` which routes the parent to `on_success`. Option (a) (write_gradient terminal state) is **rejected** — it would require modifying `apo-textgrad.yaml` and couples the inner loop to the outer loop's file layout.
- **Reference**: `loops/rl-coding-agent.yaml:30-36` has this pattern commented out as a pending upgrade (predates FEAT-659 completion); `docs/generalized-fsm-loop.md:195-211` and `loops/README.md:71-78` have canonical YAML examples; `scripts/tests/test_fsm_executor.py:3325-3357` has an integration test for `context_passthrough` capture merging. **FEAT-659 is confirmed complete** — `loops/oracles/` and `rl-coding-agent.yaml` simply haven't been upgraded yet.
- **Context merge behavior** (`executor.py:590`): `child_fsm.context = {**self.fsm.context, **self.captured, **child_fsm.context}`. Parent captures (flat dict) are merged into child context — so parent's `captured.harvest.output` is available in child as `${context.harvest.output}`. Child's own context keys take precedence. Child's returned captures are stored in parent as `self.captured[current_state]` — so `captured.run_optimizer.gradient.output` is a nested access: `captured["run_optimizer"]["gradient"]["output"]`.

**Test patterns:**
- `scripts/tests/test_user_messages.py` — uses `_write_jsonl` helper at line 109 + `tempfile.mkdtemp()`; add `ExampleRecord` and `build_examples()` unit tests here
- `scripts/tests/test_cli_messages_save.py` — CLI save behavior tests; add `--skill` and `--examples-format` integration tests here
- `scripts/tests/test_cli.py` — `TestMainMessagesIntegration` class at line 572; add `--skill` and `--examples-format` CLI argument tests here
- `scripts/tests/test_builtin_loops.py` — loop YAML validation tests; add `examples-miner.yaml` schema validation here

**Adversarial synthesis — codebase anchors:**
- `docs/guides/LOOPS_GUIDE.md:700-709` — current `examples.json` schema is `[{"input": ..., "expected": ...}]` only; the metadata fields proposed here (`source`, `perturbation_type`, `seed_id`, `difficulty_score`, `failure_cluster`, `freshness_weight`) are all new additions with no existing schema definition
- `loops/oracles/` — does **not** exist yet; new directory to create; oracle YAML files (`oracle-capture-issue.yaml`, etc.) will be the first files placed here
- `scripts/little_loops/fsm/schema.py:179-231` — `StateConfig` dataclass; confirmed `action_type` options are `prompt`, `slash_command`, `shell`, `mcp_tool`; the four new synthesis states (`synthesize`, `screen_adversarial`, `score_adversarial`, `merge`) use `prompt`/`shell` alternately
- `loops/apo-beam.yaml:13-22` — closest structural analogue to `synthesize` state: `generate_variants` prompt state emits multiple candidates in a structured text block; follow this pattern for the synthesize action's JSON array output
- `loops/evaluation-quality.yaml:57-93` — closest structural analogue to `score_adversarial`: multi-input `score` prompt state that synthesizes prior captured outputs and emits structured scores; follow for the oracle phase-2 action format
- Perturbation type → `FAILURE_PATTERN` mapping is purely prompt-level logic — no code-level dispatch; the `synthesize` prompt must include the full taxonomy table (5 types) and instruct the LLM to select the best match for the observed pattern

## Implementation Steps

1. ~~**Implement FEAT-850 first**~~ — **DONE** (completed 2026-03-21). `ExampleRecord` (fields: `skill`, `input`, `output`, `session_id`, `timestamp`, `context_window`) and `build_examples()` are live in `scripts/little_loops/user_messages.py:145–176` and `750–806`. `--skill`, `--examples-format`, `--context-window` flags are implemented in `scripts/little_loops/cli/messages.py`. **Critical implication for oracle design**: `ExampleRecord.output` is a JSON-serialized `ResponseMetadata` summary (`{"tools_used": [...], "files_modified": [...], "completion_status": "success"}`) — NOT a free-text assistant response. The oracle's phase-2 LLM scoring must evaluate tool/file choices and completion status, not prose quality. Free-text response capture is deferred to a follow-on issue.
2. **Build `examples-miner.yaml`**: follow FSM schema from `loops/apo-textgrad.yaml`; states: `harvest` → `judge` → `calibrate` → `publish`
   - **`harvest`** (`action_type: shell`, timeout: 120): incremental harvest using `--since` sentinel file (`corpus.last_harvested`). Shell command — use `--stdout` to capture output into the FSM (not `-o`):
     ```bash
     SINCE_ARG="" && [ -f corpus.last_harvested ] && SINCE_ARG="--since $(cat corpus.last_harvested)"; \
     ll-messages --skill ${context.skill_name} --examples-format --context-window 3 $SINCE_ARG --stdout
     ```
     Capture as `harvested_examples`; `next: judge`. On first run with no sentinel file the flag is omitted and all sessions are harvested.
   - **`judge`** (`action_type: shell` then `prompt`, timeout: 300): three-layer quality scoring per candidate. Layer 1 (shell): for each candidate, use `ExampleRecord.files_modified` to run `git log --follow` and `git blame` on those paths in `HEAD`; compute `persistence_score` (files still present) and `persistence_age` (commit count since introduction without revert); discard candidates whose modified files are fully absent from `HEAD`. Layer 2 (shell): `git diff` the issue file between the commit immediately after the invocation timestamp and the final completed-state commit; compute `revision_distance` (normalized edit distance); flag high-distance candidates as lower confidence. Layer 3 (prompt): run oracle rubric on survivors from layers 1–2; emit per-pair composite scores (`persistence_score`, `persistence_age`, `revision_distance`, `oracle_score`); capture as `judge_scores`; `next: calibrate`. See Step 6 for oracle YAML structure — `judge` can call `loop: oracles/oracle-<skill>.yaml` with `context_passthrough: true` when the oracle is promoted to a sub-loop in v2.
   - **`calibrate`** (`action_type: prompt`, timeout: 120): read `${captured.judge_scores.output}`; compute pass rates; emit the subset of examples in the 40–80% band as a JSON array with per-example metadata (`source: harvested`, `difficulty_score`); capture as `calibrated_corpus`; `next: run_optimizer` (or `publish` in the minimal v1 build)
   - **`publish`** (`action_type: prompt`, timeout: 60): write the final corpus to disk and update the sentinel. Instruct the LLM to: (1) write `${captured.merged_corpus.output}` (or `${captured.calibrated_corpus.output}` in v1) to `${context.examples_file}`; (2) run `date -u +%Y-%m-%dT%H:%M:%SZ > corpus.last_harvested` via Bash; (3) confirm count written. Using a `prompt` action (not `shell`) avoids shell-escaping hazards with JSON content in captured outputs.
3. **Validate end-to-end**: run miner on `ready-issue` session logs (`.issues/completed/` via `issue_history/parsing.py:20`), feed output to `loops/apo-textgrad.yaml` with `context.examples_file` pointing at miner output, verify gradient fires (`FAILURE_PATTERN`/`ROOT_CAUSE` present in `captured.gradient.output`)
4. **Add adversarial synthesis states**: after `calibrate`, insert `run_optimizer` and four new states before `diversify`. Full outer loop becomes: `harvest → judge → calibrate → run_optimizer → synthesize → screen_adversarial → score_adversarial → merge → diversify → publish`
   - **`run_optimizer`**: `loop: apo-textgrad`, `context_passthrough: true`, `on_success: synthesize`, `on_failure: publish` — skip synthesis entirely if the optimizer hit `max_iterations`/timeout
   - **`synthesize`** (`action_type: prompt`, timeout: 300): reads `${captured.run_optimizer.gradient.output}` and the passing-example list from `${captured.calibrate.output}`; executes five sub-steps in a single prompt action:
     1. Parse `FAILURE_PATTERN` from `${captured.run_optimizer.gradient.output}`; map it to one of the five perturbation types (complexity injection, ambiguity injection, domain shift, priority boundary, type confusion — see Expected Behavior §4)
     2. Select up to N passing examples nearest the 80% difficulty boundary as seeds (highest information density for perturbation)
     3. Apply the selected perturbation type to each seed's **input only** — the original expected output must NOT be reused
     4. For each perturbed input, generate a fresh expected output by running the skill prompt against it as if it were a live invocation
     5. Emit results as a JSON array: `[{"input": ..., "expected": ..., "source": "adversarial", "perturbation_type": ..., "seed_id": ...}]`; capture as `adversarial_candidates`; `next: screen_adversarial`
   - **`screen_adversarial`** (`action_type: shell`): runs oracle phase-1 mechanical checks (schema conformance, required sections, file path plausibility) on each pair in `${captured.adversarial_candidates.output}`; discards incoherent pairs immediately at zero LLM cost; emits survivors; capture as `screened_adversarial`; `next: score_adversarial`
   - **`score_adversarial`** (`action_type: prompt`): runs oracle phase-2 LLM scoring on `${captured.screened_adversarial.output}` using the same skill-scoped oracle prompt used in `judge`; filters to the 40–80% pass-rate band; enforces adversarial cap — if survivors would push `source: adversarial` above 25–30% of corpus, trim lowest-scoring pairs first; captures final adversarial set as `validated_adversarial`; `next: merge`
   - **`merge`** (`action_type: shell`): concatenates `${captured.calibrate.output}` (harvested corpus) with `${captured.validated_adversarial.output}`; each pair retains its `source` field (`harvested` or `adversarial`) as provenance metadata; captures combined corpus as `merged_corpus`; `next: diversify`
5. **Add diversity enforcement** (`action_type: prompt`, timeout: 120): `diversify` state reads `${captured.merged_corpus.output}` (the combined harvested + validated adversarial corpus from `merge`), counts examples per axis (skill type, issue type, priority band, lifecycle stage, failure cluster), identifies under-represented axes, and either flags them for the next harvest cycle or sub-samples over-represented axes to hit per-axis minimums. Output is the final diversified corpus as a JSON array; capture as `final_corpus`; `next: publish`. Follow `generate_variants` output style from `apo-beam.yaml:13-22`: emit structured JSON in a single block, no prose commentary. If the corpus already meets coverage minimums, pass through unchanged.
6. **Add oracle prompts**: one scoring loop per target skill in `loops/oracles/` (e.g., `oracle-capture-issue.yaml`, `oracle-refine-issue.yaml`). **Critical constraint**: the `loop:` field in `executor.py:585` uses `state.loop` as a raw string via `resolve_loop_path()` — no context interpolation is applied. So `loop: oracles/oracle-${context.skill_name}.yaml` does NOT work. Each `examples-miner.yaml` instance must hardcode its oracle path (e.g., `loop: oracles/oracle-capture-issue.yaml`). Oracle YAML structure (2-phase FSM, `context_passthrough: true` from `judge` state provides `invocation` and `output`):
   ```yaml
   name: oracle-capture-issue
   description: "Two-phase rubric scoring for capture-issue ExampleRecord pairs"
   initial: check_mechanical
   max_iterations: 1
   context:
     skill_name: capture-issue
     invocation: ""   # provided by parent via context_passthrough
     output: ""       # provided by parent — serialized ResponseMetadata JSON
   states:
     check_mechanical:
       action_type: shell
       timeout: 30
       action: |
         python3 -c "
         import json, sys
         try:
             data = json.loads(r'''${context.output}''')
             failures = []
             if 'tools_used' not in data: failures.append('missing tools_used')
             if 'completion_status' not in data: failures.append('missing completion_status')
             print('PHASE1_FAIL: ' + '; '.join(failures) if failures else 'PHASE1_PASS')
         except Exception as e:
             print(f'PHASE1_FAIL: invalid JSON — {e}')
         "
       capture: phase1
       next: route_phase1
     route_phase1:
       evaluate:
         type: output_contains
         source: "${captured.phase1.output}"
         pattern: "PHASE1_PASS"
       on_yes: score_semantic
       on_no: done
     score_semantic:
       action_type: prompt
       timeout: 120
       action: |
         Score this ${context.skill_name} invocation for training utility.
         Invocation context: ${context.invocation}
         Response metadata (JSON): ${context.output}
         Evaluate tool choices and completion_status for correctness.
         Output: SCORE=<0-100>
       capture: score
       next: done
     done:
       terminal: true
   ```
   Note: `context_passthrough` at `executor.py:590` merges parent context + parent captures into child context — so parent's `captured.harvested_examples` entries become `${context.harvested_examples.*}` in the child; the `invocation` and `output` per-example values must be injected explicitly by the `judge` state action before calling the oracle sub-loop (v1 approach: inline LLM judging in `judge` state, oracle sub-loop promoted in v2). Bootstrap oracle calibration fixtures via ensemble agreement: run multiple oracle variants (different temperatures, different prompt phrasings) against the candidate pool; examples with low score variance across all variants become the fixture set. Validate the ensemble against deliberately degraded examples (corrupt known candidates) as a sanity check before each mining cycle — halt if score distribution on the fixture set drifts beyond threshold.
7. **Add corpus maintenance**: freshness decay via weight field in `examples.json`; regression floor archiving; auto-ingest on new completions. **Hook mechanism constraint**: `hooks/hooks.json` has no "issue completion" event — available events are `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `PreCompact`. Recommended approach: the `harvest` state in `examples-miner.yaml` uses a sentinel timestamp file (e.g., `corpus.last_harvested`) written by the `publish` state; on next run, `ll-messages --skill <name> --since <timestamp>` discovers sessions added after the last harvest. This is polling-based, not event-driven — no hook changes needed.

## Impact

- **Priority**: P3 — High leverage for prompt optimization quality, no existing workaround
- **Effort**: Large — multiple components (script extension, two new loops, oracle prompt)
- **Risk**: Medium — core loop logic is well-understood; oracle calibration is the open research question
- **Breaking Change**: No

## Related Key Documentation

- `loops/README.md` — loop catalog; add miner/optimizer pairing pattern and `examples-miner.yaml` entry here
- `loops/apo-textgrad.yaml` — inner loop; `context.examples_file: examples.json` (line 14) is the direct integration point; gradient format at lines 36–38
- `loops/apo-opro.yaml` — reference for history-chaining pattern (`captured.score_history` chain across iterations)
- `loops/harness-single-shot.yaml` — reference for `skill_invocation` pattern in loop YAML (note: no `examples/` subdirectory; file is at the `loops/` root)
- `docs/guides/LOOPS_GUIDE.md` — already references `examples_file` and `examples.json`; update with miner pairing
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `skill_invocation` patterns; relevant background
- `docs/generalized-fsm-loop.md` — FSM loop architecture doc; background on `context_passthrough` for sub-loop chaining
- `docs/reference/API.md` — public Python API; add `ExampleRecord` to surface once FEAT-850 is implemented
- `.issues/completed/P3-FEAT-850-ll-messages-skill-filter-and-examples-format-flags.md` — blocking dependency with `ExampleRecord` API design and `build_examples()` specification (completed 2026-03-21)

## Blocked By

- ~~FEAT-850~~ (completed 2026-03-21)

## Labels

`feat`, `loops`, `apo`, `prompt-optimization`, `captured`

## Resolution

**Completed**: 2026-03-21

Implemented `loops/examples-miner.yaml` — a 12-state FSM outer loop that wraps `apo-textgrad` as a child sub-loop via `loop: apo-textgrad` + `context_passthrough: true`.

**Files created:**
- `loops/examples-miner.yaml` — main 12-state co-evolutionary mining loop
- `loops/oracles/oracle-capture-issue.yaml` — standalone two-phase oracle for v2 sub-loop promotion

**Files modified:**
- `loops/README.md` — added `examples-miner` to APO section
- `scripts/tests/test_builtin_loops.py` — added `examples-miner` to `test_expected_loops_exist` set
- `docs/guides/LOOPS_GUIDE.md` — added full `examples-miner` documentation section with pairing guide

**Architecture decisions:**
- Used `calibrated_corpus` as a single accumulating capture variable (overwritten by `merge` and `diversify`) so `publish` always has a valid corpus regardless of which path was taken (optimizer success/failure, blocked states)
- Added `write_examples` state between `calibrate` and `run_optimizer` to write the calibrated corpus to `examples.json` before the inner loop reads it
- Used `prompt` actions for adversarial quality gates (v1 inline oracle) rather than sub-loop delegation (v2); oracle YAML created for future promotion
- Inline oracle scoring in `judge` and `score_adversarial` states; `loops/oracles/oracle-capture-issue.yaml` documents the v2 sub-loop pattern
- FSM validation: 0 errors, 0 warnings; full test suite: 3835 passed

## Status

**Completed** | Created: 2026-03-20 | Completed: 2026-03-21 | Priority: P3

## Session Log
- `/ll:ready-issue` - 2026-03-21T22:21:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/361c2c3a-bd3c-417b-9d69-cfd541e136fc.jsonl`
- `/ll:confidence-check` - 2026-03-21T22:30:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1eac459c-1c68-4bf6-b2ef-87583a85dec3.jsonl`
- `/ll:confidence-check` - 2026-03-21T22:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4323075c-a536-4375-b649-525fbfdd6bf7.jsonl`
- `/ll:confidence-check` - 2026-03-21T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/546d021c-f4c2-487a-b4ec-147443a5ce85.jsonl`
- `/ll:refine-issue` - 2026-03-21T21:22:51 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/349449a7-2c6b-4cd5-9168-7b45a4a09364.jsonl`
- `/ll:refine-issue` - 2026-03-21T05:53:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5b33b4-4f43-4816-926d-91f9358c3ab6.jsonl`
- `/ll:format-issue` - 2026-03-21T05:50:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29becafe-e61b-4664-a177-52d37aba9ad2.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:26:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ef00304-0425-4493-86d1-986e0f3bbb29.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:03:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37aaa01c-fc9c-49b3-a00c-669bbb0655ed.jsonl`
- `/ll:refine-issue` - 2026-03-21T01:28:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f97b7680-1084-46aa-9586-4d4827393f96.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2dab8d3-f1a2-4974-84ba-68f20250569c.jsonl`
