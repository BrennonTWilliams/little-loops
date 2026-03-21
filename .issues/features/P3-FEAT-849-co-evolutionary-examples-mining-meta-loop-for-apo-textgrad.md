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
4. **Synthesizes** new adversarial examples by reading the gradient output (`FAILURE_PATTERN`, `ROOT_CAUSE`) from the most recent `apo-textgrad` run and generating targeted perturbations of passing examples
5. **Diversifies** via a coverage budget: at least N examples per skill type, issue type, priority band, lifecycle stage, and failure cluster
6. **Publishes** a fresh `examples.json` with per-example metadata (provenance, difficulty score, failure cluster, freshness weight)
7. **Maintains** a living corpus: new completions enter the harvest queue automatically; stale examples decay in weight; an archived regression floor prevents backward drift

## Motivation

`apo-textgrad` is only as good as its examples. A static hand-crafted `examples.json` optimizes the prompt for known cases while leaving blind spots untouched. The project already has the labeled dataset — completed issues with accepted outputs are implicit human approvals — it just lacks the mining step. Without adaptive calibration, the corpus goes stale as the prompt improves and new conventions emerge. Without adversarial synthesis, the gradient signal only covers patterns already in the corpus. The co-evolutionary design ensures the example difficulty always leads the prompt's current capability, producing continuous improvement rather than convergence to a local optimum.

## Proposed Solution

A two-loop architecture using FSM sub-loop chaining:

**Outer loop** (`examples-miner.yaml`): harvest → judge → calibrate → run_optimizer (sub-loop) → synthesize → diversify → publish
**Inner loop** (`apo-textgrad`): test → gradient → apply → iterate

The outer loop invokes `apo-textgrad` as a child FSM via `loop: apo-textgrad` + `context_passthrough: true` in the `run_optimizer` state. The child's gradient output (`FAILURE_PATTERN`, `ROOT_CAUSE`, `GRADIENT`) is available in the parent as `${captured.run_optimizer.gradient.output}` for the `synthesize` state. The inner loop reads `examples.json` published by the outer loop via its `context.examples_file`. Both loops run within a single `ll-loop run` invocation — no file I/O required to pass the gradient signal.

Key components:
- **Harvest script** (extend `ll-messages`): `--skill` filter + `--examples-format` flag that extracts (invocation context, accepted output) pairs from `.jsonl` logs
- **Oracle prompt**: skill-scoped, not universal — one rubric per skill being optimized (e.g., a `capture-issue` oracle is distinct from a `refine-issue` oracle); the oracle prompt accepts a `skill_name` parameter and applies the corresponding rubric. Two phases: (1) mechanical/deterministic checks (schema conformance, file path existence, line number plausibility, required section presence) run first at zero LLM cost; (2) semantic LLM scoring (motivation coherence, codebase reference accuracy, implementer actionability) runs only for outputs that pass phase 1. The oracle is **manually maintained** in v1 — do not attempt to optimize it via `apo-textgrad` itself, as that requires a meta-oracle to score oracle scores (circular rabbit hole). Validate calibration using a small fixture set (10–15 hand-labeled examples per skill); if fixture scores drift before a mining cycle, halt rather than corrupt the corpus
- **Calibration state**: run current prompt against all candidates, compute pass rates, select 40–80% band
- **Adversarial synthesizer**: LLM-guided perturbation of passing examples using the current gradient
- **Diversity budget**: enforced per-axis coverage constraints

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

## Implementation Steps

1. **Implement FEAT-850 first**: `ExampleRecord` dataclass + `build_examples()` in `scripts/little_loops/user_messages.py`; `--skill`, `--examples-format`, `--context-window` args in `scripts/little_loops/cli/messages.py:main_messages()` (line 11); tests in `scripts/tests/test_user_messages.py` and `scripts/tests/test_cli_messages_save.py`
2. **Build `examples-miner.yaml`**: follow FSM schema from `loops/apo-textgrad.yaml`; states: `harvest` (shell: `ll-messages --skill <name> --examples-format -o ${context.examples_file}`) → `judge` (prompt: score each pair against rubric) → `calibrate` (prompt: select 40–80% pass-rate band) → `publish` (shell: write final `examples.json`)
3. **Validate end-to-end**: run miner on `ready-issue` session logs (`.issues/completed/` via `issue_history/parsing.py:20`), feed output to `loops/apo-textgrad.yaml` with `context.examples_file` pointing at miner output, verify gradient fires (`FAILURE_PATTERN`/`ROOT_CAUSE` present in `captured.gradient.output`)
4. **Add adversarial synthesis state**: insert a `run_optimizer` sub-loop state (after `calibrate`, before `synthesize`) that invokes `apo-textgrad` via `loop: apo-textgrad` + `context_passthrough: true`; then add a `synthesize` prompt state that reads `${captured.run_optimizer.gradient.output}` to extract `FAILURE_PATTERN` and `ROOT_CAUSE` and generates targeted perturbations of passing examples
5. **Add diversity enforcement**: coverage budget logic in the `calibrate`/`publish` state; enforce per-axis minimums (skill type, issue type, priority band, lifecycle stage, failure cluster)
6. **Add oracle prompts**: one scoring prompt per target skill in `loops/oracles/` (e.g., `oracle-capture-issue.yaml`, `oracle-refine-issue.yaml`); each accepts `skill_name`, `invocation`, and `output` context variables; phase 1 mechanical checks are deterministic (schema, file existence, required sections) and run before the LLM call; maintain a calibration fixture of 10–15 hand-labeled examples per skill and run it as a pre-flight check before each mining cycle — halt if score distribution drifts beyond threshold; treat oracle prompts as manually maintained in v1
7. **Add corpus maintenance**: freshness decay via weight field in `examples.json`; regression floor archiving; auto-ingest hook triggered on issue completion (see `hooks/hooks.json` for hook patterns)

## Impact

- **Priority**: P3 — High leverage for prompt optimization quality, no existing workaround
- **Effort**: Large — multiple components (script extension, two new loops, oracle prompt)
- **Risk**: Medium — core loop logic is well-understood; oracle calibration is the open research question
- **Breaking Change**: No

## Related Key Documentation

- `loops/README.md` — loop catalog; add miner/optimizer pairing pattern and `examples-miner.yaml` entry here
- `loops/apo-textgrad.yaml` — inner loop; `context.examples_file: examples.json` (line 9) is the direct integration point; gradient format at lines 31–33
- `loops/apo-opro.yaml` — reference for history-chaining pattern (`captured.score_history` chain across iterations)
- `loops/examples/harness-single-shot.yaml` — reference for `skill_invocation` pattern in loop YAML
- `docs/guides/LOOPS_GUIDE.md` — already references `examples_file` and `examples.json`; update with miner pairing
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — references `skill_invocation` patterns; relevant background
- `docs/generalized-fsm-loop.md` — FSM loop architecture doc; background on `context_passthrough` for sub-loop chaining
- `docs/reference/API.md` — public Python API; add `ExampleRecord` to surface once FEAT-850 is implemented
- `.issues/features/P3-FEAT-850-ll-messages-skill-filter-and-examples-format-flags.md` — blocking dependency with `ExampleRecord` API design and `build_examples()` specification

## Blocked By

- FEAT-850

## Labels

`feat`, `loops`, `apo`, `prompt-optimization`, `captured`

## Status

**Open** | Created: 2026-03-20 | Priority: P3

## Session Log
- `/ll:refine-issue` - 2026-03-21T02:03:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/37aaa01c-fc9c-49b3-a00c-669bbb0655ed.jsonl`
- `/ll:refine-issue` - 2026-03-21T01:28:26 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f97b7680-1084-46aa-9586-4d4827393f96.jsonl`
- `/ll:capture-issue` - 2026-03-20T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a2dab8d3-f1a2-4974-84ba-68f20250569c.jsonl`
