---
id: FEAT-849
type: FEAT
priority: P3
discovered_date: 2026-03-20
discovered_by: capture-issue
---

# FEAT-849: Co-evolutionary Examples Mining Meta-Loop for apo-textgrad

## Summary

Build a continuous, self-calibrating meta-loop that mines completed issues and session logs to produce an adaptive `examples.json` for `apo-textgrad`. The mining loop and the optimization loop are coupled: each optimization cycle's gradient signal drives adversarial example generation in the next mining cycle, and the example corpus is continuously re-calibrated to the current prompt's capability level.

## Current Behavior

`apo-textgrad` requires a manually created `examples.json`. There is no mechanism to source examples from the project's existing history — 784+ completed issues and hundreds of linked session logs contain real labeled invocations but none of it is harvested. The corpus is static; once created it never updates to reflect evolved conventions or harder edge cases.

## Expected Behavior

A loop (`examples-miner.yaml` or similar) runs as a wrapper around `apo-textgrad` that:

1. **Harvests** skill invocations from all session logs linked in completed issues (`## Session Log` entries)
2. **Judges** each harvested pair using a rubric oracle (a separate calibrated prompt) that scores outputs against structured criteria rather than literal string matching
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

- [ ] `ll-loop run loops/examples-miner.yaml` harvests skill invocations from all session logs linked in completed issues via `## Session Log` entries
- [ ] Each harvested pair is scored by the oracle rubric; only pairs in the 40–80% pass-rate band are included in the active calibrated set
- [ ] Trivially easy (>80% pass rate) and noise-level hard (<40% pass rate) examples are excluded from the corpus
- [ ] After an optimizer run, adversarial examples are synthesized by perturbing passing example inputs using the type matched to `FAILURE_PATTERN`; original expected outputs are never reused
- [ ] `source: adversarial` examples are capped at ≤30% of the final corpus at all times
- [ ] Published `examples.json` includes per-example metadata: `source`, `perturbation_type`, `seed_id`, `difficulty_score`, `failure_cluster`, `freshness_weight`
- [ ] New completions from subsequent issues enter the harvest queue automatically; stale examples decay in weight via freshness field
- [ ] Loop terminates with a fresh `examples.json` written to `context.examples_file`

## Motivation

`apo-textgrad` is only as good as its examples. A static hand-crafted `examples.json` optimizes the prompt for known cases while leaving blind spots untouched. The project already has the labeled dataset — completed issues with accepted outputs are implicit human approvals — it just lacks the mining step. Without adaptive calibration, the corpus goes stale as the prompt improves and new conventions emerge. Without adversarial synthesis, the gradient signal only covers patterns already in the corpus. The co-evolutionary design ensures the example difficulty always leads the prompt's current capability, producing continuous improvement rather than convergence to a local optimum.

## Proposed Solution

A two-loop architecture using FSM sub-loop chaining:

**Outer loop** (`examples-miner.yaml`): harvest → judge → calibrate → run_optimizer (sub-loop) → synthesize → screen_adversarial → score_adversarial → merge → diversify → publish
**Inner loop** (`apo-textgrad`): test → gradient → apply → iterate

The outer loop invokes `apo-textgrad` as a child FSM via `loop: apo-textgrad` + `context_passthrough: true` in the `run_optimizer` state. The child's gradient output (`FAILURE_PATTERN`, `ROOT_CAUSE`, `GRADIENT`) is available in the parent as `${captured.run_optimizer.gradient.output}` for the `synthesize` state. The inner loop reads `examples.json` published by the outer loop via its `context.examples_file`. Both loops run within a single `ll-loop run` invocation — no file I/O required to pass the gradient signal.

Key components:
- **Harvest script** (extend `ll-messages`): `--skill` filter + `--examples-format` flag that extracts (invocation context, accepted output) pairs from `.jsonl` logs
- **Oracle prompt**: skill-scoped, not universal — one rubric per skill being optimized (e.g., a `capture-issue` oracle is distinct from a `refine-issue` oracle); the oracle prompt accepts a `skill_name` parameter and applies the corresponding rubric. Two phases: (1) mechanical/deterministic checks (schema conformance, file path existence, line number plausibility, required section presence) run first at zero LLM cost; (2) semantic LLM scoring (motivation coherence, codebase reference accuracy, implementer actionability) runs only for outputs that pass phase 1. The oracle is **manually maintained** in v1 — do not attempt to optimize it via `apo-textgrad` itself, as that requires a meta-oracle to score oracle scores (circular rabbit hole). Validate calibration using a small fixture set (10–15 hand-labeled examples per skill); if fixture scores drift before a mining cycle, halt rather than corrupt the corpus
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
  corpus_state_file: corpus.json     # optional: persisted calibration state across runs
  target_pass_rate: 0.6              # center of 40–80% band
```

Python API changes (ExampleRecord dataclass, `build_examples()`, `--skill`, `--examples-format` flags) are specified and owned by FEAT-850. No direct Python public API additions in this issue.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/messages.py` — add `--skill` filter and `--examples-format` output mode (`main_messages()` at line 11 is the CLI entry point)
- `scripts/little_loops/user_messages.py` — add `ExampleRecord` dataclass and `build_examples()` helper (covered by FEAT-850; also the harvest foundation via `extract_user_messages()` at line 347)
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
- `context.examples_file` in `apo-textgrad.yaml` — path to published examples (`apo-textgrad.yaml:9`: `context.examples_file: examples.json`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Gradient output format (`apo-textgrad.yaml:28–34`):**
- Captured in `captured.gradient.output`; the outer loop reads this from the inner loop's most recent run
- Structured as three lines: `FAILURE_PATTERN: <common theme>`, `ROOT_CAUSE: <what is wrong>`, `GRADIENT: <how to change>`
- Convergence signal: `CONVERGED` on its own line when `PASS_RATE >= target_pass_rate`

**Session log harvesting API:**
- `scripts/little_loops/session_log.py:23` — `parse_session_log(content)` extracts JSONL file paths from a completed issue's `## Session Log` section via `_SESSION_LOG_SECTION_RE` regex; returns distinct `/ll:*` command names
- `scripts/little_loops/issue_history/parsing.py:20` — `parse_completed_issue(file_path)` parses completed issues; scan `.issues/completed/` to enumerate the corpus
- `scripts/little_loops/user_messages.py:318` — `get_project_folder(cwd)` maps CWD → `~/.claude/projects/{encoded-path}/`; individual JSONL files discovered via `project_folder.glob("*.jsonl")`
- JSONL record structure: `{type, message, sessionId, uuid, timestamp, cwd, gitBranch, isSidechain}`; user records have `message.content` as string (real input) or array (tool results — skip)
- Skill detection: filter user records where `message.content` matches `r'/ll:?SKILL_NAME'`, or assistant records where `message.content` contains a `Skill` tool_use block (pairs with `--include-response-context` in `user_messages.py:352`)

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
- **Reference**: `loops/rl-coding-agent.yaml:30-36` has this pattern commented out as a pending upgrade; `docs/generalized-fsm-loop.md:195-211` and `loops/README.md:71-78` have canonical YAML examples; `scripts/tests/test_fsm_executor.py:3325-3357` has an integration test for `context_passthrough` capture merging.

**Test patterns:**
- `scripts/tests/test_user_messages.py` — uses `_write_jsonl` helper at line 107 + `tempfile.mkdtemp()`; add `ExampleRecord` and `build_examples()` unit tests here
- `scripts/tests/test_cli_messages_save.py` — CLI save behavior tests; add `--skill` and `--examples-format` integration tests here
- `scripts/tests/test_cli.py` — `TestMainMessages` class at ~line 580; add `--skill` and `--examples-format` CLI argument tests here
- `scripts/tests/test_builtin_loops.py` — loop YAML validation tests; add `examples-miner.yaml` schema validation here

**Adversarial synthesis — codebase anchors:**
- `docs/guides/LOOPS_GUIDE.md:700-709` — current `examples.json` schema is `[{"input": ..., "expected": ...}]` only; the metadata fields proposed here (`source`, `perturbation_type`, `seed_id`, `difficulty_score`, `failure_cluster`, `freshness_weight`) are all new additions with no existing schema definition
- `loops/oracles/` — does **not** exist yet; new directory to create; oracle YAML files (`oracle-capture-issue.yaml`, etc.) will be the first files placed here
- `scripts/little_loops/fsm/schema.py:179-231` — `StateConfig` dataclass; confirmed `action_type` options are `prompt`, `slash_command`, `shell`, `mcp_tool`; the four new synthesis states (`synthesize`, `screen_adversarial`, `score_adversarial`, `merge`) use `prompt`/`shell` alternately
- `loops/apo-beam.yaml:13-22` — closest structural analogue to `synthesize` state: `generate_variants` prompt state emits multiple candidates in a structured text block; follow this pattern for the synthesize action's JSON array output
- `loops/evaluation-quality.yaml:57-93` — closest structural analogue to `score_adversarial`: multi-input `score` prompt state that synthesizes prior captured outputs and emits structured scores; follow for the oracle phase-2 action format
- Perturbation type → `FAILURE_PATTERN` mapping is purely prompt-level logic — no code-level dispatch; the `synthesize` prompt must include the full taxonomy table (5 types) and instruct the LLM to select the best match for the observed pattern

## Implementation Steps

1. ~~**Implement FEAT-850 first**~~ — **DONE** (completed 2026-03-21). `ExampleRecord` (fields: `skill`, `input`, `output`, `session_id`, `timestamp`, `context_window`) and `build_examples()` are live in `scripts/little_loops/user_messages.py:145–176` and `753–806`. `--skill`, `--examples-format`, `--context-window` flags are implemented in `scripts/little_loops/cli/messages.py`. **Critical implication for oracle design**: `ExampleRecord.output` is a JSON-serialized `ResponseMetadata` summary (`{"tools_used": [...], "files_modified": [...], "completion_status": "success"}`) — NOT a free-text assistant response. The oracle's phase-2 LLM scoring must evaluate tool/file choices and completion status, not prose quality. Free-text response capture is deferred to a follow-on issue.
2. **Build `examples-miner.yaml`**: follow FSM schema from `loops/apo-textgrad.yaml`; states: `harvest` (shell: `ll-messages --skill <name> --examples-format -o ${context.examples_file}`) → `judge` (prompt: score each pair against rubric) → `calibrate` (prompt: select 40–80% pass-rate band) → `publish` (shell: write final `examples.json`)
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
5. **Add diversity enforcement**: coverage budget logic in the `calibrate`/`publish` state; enforce per-axis minimums (skill type, issue type, priority band, lifecycle stage, failure cluster)
6. **Add oracle prompts**: one scoring prompt per target skill in `loops/oracles/` (e.g., `oracle-capture-issue.yaml`, `oracle-refine-issue.yaml`); each accepts `skill_name`, `invocation`, and `output` context variables; phase 1 mechanical checks are deterministic (schema, file existence, required sections) and run before the LLM call; maintain a calibration fixture of 10–15 hand-labeled examples per skill and run it as a pre-flight check before each mining cycle — halt if score distribution drifts beyond threshold; treat oracle prompts as manually maintained in v1
7. **Add corpus maintenance**: freshness decay via weight field in `examples.json`; regression floor archiving; auto-ingest on new completions. **Hook mechanism constraint**: `hooks/hooks.json` has no "issue completion" event — available events are `SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `Stop`, `PreCompact`. Recommended approach: the `harvest` state in `examples-miner.yaml` uses a sentinel timestamp file (e.g., `corpus.last_harvested`) written by the `publish` state; on next run, `ll-messages --skill <name> --since <timestamp>` discovers sessions added after the last harvest. This is polling-based, not event-driven — no hook changes needed.

## Impact

- **Priority**: P3 — High leverage for prompt optimization quality, no existing workaround
- **Effort**: Large — multiple components (script extension, two new loops, oracle prompt)
- **Risk**: Medium — core loop logic is well-understood; oracle calibration is the open research question
- **Breaking Change**: No

## Related Key Documentation

- `loops/README.md` — loop catalog; add miner/optimizer pairing pattern and `examples-miner.yaml` entry here
- `loops/apo-textgrad.yaml` — inner loop; `context.examples_file: examples.json` (line 9) is the direct integration point; gradient format at lines 31–33
- `loops/apo-opro.yaml` — reference for history-chaining pattern (`captured.score_history` chain across iterations)
- `loops/harness-single-shot.yaml` — reference for `skill_invocation` pattern in loop YAML (note: no `examples/` subdirectory; file is at the `loops/` root)
- `docs/guides/LOOPS_GUIDE.md` — already references `examples_file` and `examples.json`; update with miner pairing
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `skill_invocation` patterns; relevant background
- `docs/generalized-fsm-loop.md` — FSM loop architecture doc; background on `context_passthrough` for sub-loop chaining
- `docs/reference/API.md` — public Python API; add `ExampleRecord` to surface once FEAT-850 is implemented
- `.issues/features/P3-FEAT-850-ll-messages-skill-filter-and-examples-format-flags.md` — blocking dependency with `ExampleRecord` API design and `build_examples()` specification

## Blocked By

- ~~FEAT-850~~ (completed 2026-03-21)

## Labels

`feat`, `loops`, `apo`, `prompt-optimization`, `captured`

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-03-21T05:53:44 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5b33b4-4f43-4816-926d-91f9358c3ab6.jsonl`
- `/ll:format-issue` - 2026-03-21T05:50:55 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29becafe-e61b-4664-a177-52d37aba9ad2.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:26:36 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2ef00304-0425-4493-86d1-986e0f3bbb29.jsonl`
- `/ll:refine-issue` - 2026-03-21T02:03:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37aaa01c-fc9c-49b3-a00c-669bbb0655ed.jsonl`
- `/ll:refine-issue` - 2026-03-21T01:28:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f97b7680-1084-46aa-9586-4d4827393f96.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2dab8d3-f1a2-4974-84ba-68f20250569c.jsonl`
