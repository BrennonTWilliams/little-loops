---
id: FEAT-1806
title: Opponent-Aware Market Strategy Optimization Loop
type: FEAT
priority: P3
status: cancelled
parent: EPIC-1811
discovered_date: 2026-05-29
discovered_by: capture-issue
captured_at: '2026-05-30T04:44:25Z'
---

# FEAT-1806: Opponent-Aware Market Strategy Optimization Loop

## Summary

Add a new built-in FSM loop to `ll-loop` that performs opponent-aware market strategy optimization at the project product-level. The loop models competitive dynamics — analyzing market positioning, anticipating competitor moves, and recommending product strategy adjustments — as a reusable, autonomous FSM.

## Current Behavior

`ll-loop` has no built-in loop type for market strategy or competitive analysis. Product-level strategic decisions are made ad-hoc without systematic modeling of opponent behavior or market dynamics. Existing loops (deep-research, RL, policy optimization) operate at the implementation or code-quality level, not the product-strategy level.

## Expected Behavior

Users can select a built-in market strategy loop template when running `/ll:create-loop`, with pre-configured FSM states that:

- **Market scan**: Gather competitive intelligence (pricing, features, positioning) from available data sources
- **Opponent modeling**: Infer competitor strategies and likely responses using game-theoretic reasoning
- **Positioning analysis**: Evaluate the project's current market position relative to opponents
- **Strategy generation**: Propose product-level strategy adjustments (feature prioritization, positioning shifts, differentiation plays)
- **Counterfactual simulation**: Model how opponents might respond to each proposed strategy
- **Recommendation**: Output ranked strategy recommendations with expected outcomes and opponent-response mitigations

The loop runs periodically or on-demand, producing a structured strategy artifact that informs product decisions.

## Motivation

Current product decisions are driven by intuition and ad-hoc analysis. A systematic opponent-aware loop would:

- Surface competitive blind spots before they become threats
- Quantify trade-offs between differentiation and head-on competition
- Provide a structured record of strategic reasoning for retrospectives
- Enable continuous competitive monitoring without manual effort

For a developer tool like little-loops, understanding the competitive landscape (other Claude Code plugins, AI-assisted development tools) is critical to prioritizing the right features.

## Proposed Solution

### Approach

Add a new built-in loop YAML under `scripts/little_loops/loops/` following the existing pattern from FEAT-723 (RL loops) and FEAT-1540 (deep-research loop). The FSM design follows the standard `diagnose → propose → apply → measure-externally` shape, adapted for strategic analysis where "apply" means generating strategy artifacts rather than code changes.

### Key Design Decisions

1. **Loop shape**: The market strategy loop is closer to a data-operating loop (analyzes external data, produces recommendations) than a meta-loop. However, when the recommendations include modifications to loop/issue/sprint artifacts, it should follow meta-loop rules (non-LLM evaluator pairing per MR-1).

2. **Evaluation**: Strategy quality is inherently hard to measure automatically. The loop should include:
   - A non-LLM evaluator (e.g., `convergence` check on strategy iteration count)
   - An optional human-in-the-loop approval gate before applying strategy changes

3. **Integration**: The loop should integrate with:
   - `ll:scan-product` and `ll:product-analyzer` for product-goal awareness
   - `ll:prioritize-issues` for strategy-to-backlog wiring
   - `ll:create-sprint` for translating strategy into execution

### Loop YAML Skeleton

```yaml
# scripts/little_loops/loops/market-strategy-optimize.yaml
name: market-strategy-optimize
description: >
  Opponent-aware market strategy optimization at the project product-level.
  Models competitive dynamics and recommends product strategy adjustments.
version: "1.0"
meta_self_eval_ok: false

states:
  - id: market_scan
    type: llm_unstructured
    prompt: |
      Scan the competitive landscape for {project_name}...
    transitions:
      - target: opponent_model
        predicate: always

  - id: opponent_model
    type: llm_structured
    schema: opponent_model_schema
    prompt: |
      Model competitor strategies and likely responses...
    transitions:
      - target: position_analyze
        predicate: always

  - id: position_analyze
    type: llm_structured
    schema: position_schema
    prompt: |
      Evaluate current market position relative to opponents...
    transitions:
      - target: strategy_generate
        predicate: always

  - id: strategy_generate
    type: llm_structured
    schema: strategy_schema
    prompt: |
      Generate product strategy adjustments...
    transitions:
      - target: counterfactual_sim
        predicate: always

  - id: counterfactual_sim
    type: llm_structured
    schema: counterfactual_schema
    prompt: |
      Simulate opponent responses to each proposed strategy...
    transitions:
      - target: recommend
        predicate: always

  - id: recommend
    type: llm_structured
    schema: recommendation_schema
    prompt: |
      Output ranked strategy recommendations with rationale...
    transitions:
      - target: done
        predicate: convergence
        max_iterations: 3
```

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical**: The skeleton above uses three FSM constructs that do not exist in the actual schema. `ll-loop validate` will fail immediately. Use the corrected skeleton below.

#### Invalid Constructs → Corrections

| Invalid | Correction | Source |
|---------|-----------|--------|
| `type: llm_unstructured` as state type | Use `action_type: prompt`; no top-level `type:` field exists on states | `schema.py:StateConfig`, `executor.py:_action_mode()` |
| `type: llm_structured` as state type | Use `action_type: prompt`; `llm_structured` is only valid inside `evaluate:` blocks | `evaluators.py:741`, `schema.py:EvaluateConfig` |
| `predicate: always` / `predicate: convergence` in transitions | No `predicate:` field in schema (silently dropped by `from_dict()`); use `next:` for unconditional, `on_yes/on_no` for binary, `route: {target/progress/stall: ...}` for convergence | `executor.py:_route()`, `validation.py:KNOWN_TOP_LEVEL_KEYS` |
| `schema: opponent_model_schema` field | No `schema:` field on states; JSON schemas are embedded as prompt instructions with sentinel tokens for routing | `schema.py:StateConfig.from_dict()` |
| Missing `initial:` top-level field | FSM requires `initial: <state_id>` to know the entry point | `schema.py:FSMLoop` |

#### Schema-Valid Corrected Skeleton

Modeled on `deep-research.yaml` (init + `run_dir` isolation pattern), `backlog-flow-optimizer.yaml` (prompt→capture→route-shell split), and `rl-bandit.yaml` (non-LLM evaluator for quality gates). Note: `${context.run_dir}` is FSM interpolation; bare `$DIR` in shell actions is bash and does not need escaping.

```yaml
name: market-strategy-optimize
category: strategy
description: >
  Opponent-aware market strategy optimization at the project product-level.
  Models competitive dynamics and recommends product strategy adjustments.
initial: init
max_iterations: 10
timeout: 7200
on_handoff: spawn

parameters:
  project_name:
    type: string
    required: true
    description: "Project name to analyze"
  competitors:
    type: string
    default: "[]"
    description: "JSON array of competitor names"

states:
  init:
    action_type: shell
    action: |
      DIR="${context.run_dir}"
      mkdir -p "$DIR"
      : > "$DIR/scan.md"
      : > "$DIR/strategy.md"
      echo "$DIR"
    capture: run_dir
    next: market_scan

  market_scan:
    action_type: prompt
    timeout: 600
    action: |
      Scan the competitive landscape for ${context.project_name}.
      Competitors: ${context.competitors}
      Research features, positioning, strengths, weaknesses, and recent moves.
      Write a structured report to ${captured.run_dir.output}/scan.md.
      Output exactly on the last line: SCAN_COMPLETE
    capture: scan_result
    next: check_scan

  check_scan:
    evaluate:
      type: output_contains
      source: "${captured.scan_result.output}"
      pattern: "SCAN_COMPLETE"
    on_yes: opponent_model
    on_no: market_scan
    on_error: failed

  opponent_model:
    action_type: prompt
    timeout: 600
    action: |
      Read ${captured.run_dir.output}/scan.md. For each competitor infer: strategic goals,
      likely responses to ${context.project_name} feature additions,
      threat level (low/medium/high/critical), top 3 next moves.
      Append a "## Opponent Model" JSON block to ${captured.run_dir.output}/strategy.md.
      Output exactly on the last line: MODEL_COMPLETE
    capture: model_result
    next: position_analyze

  position_analyze:
    action_type: prompt
    timeout: 600
    action: |
      Read ${captured.run_dir.output}/strategy.md. Evaluate ${context.project_name}'s
      current market position: differentiators, market gaps, exploitable weaknesses.
      Append a "## Positioning Analysis" section.
      Output a positioning strength score (integer 1-10) as the LAST LINE ONLY.
    capture: position_result
    evaluate:
      type: output_numeric
      operator: ge
      target: 1
    on_yes: strategy_generate
    on_no: failed
    on_error: failed

  strategy_generate:
    action_type: prompt
    timeout: 600
    action: |
      Read ${captured.run_dir.output}/strategy.md. Generate 3-5 product strategy options.
      For each: name, core approach (1-2 sentences), target position,
      primary trade-off vs competitors, effort estimate (low/medium/high).
      Append a "## Strategy Options" section.
      Output exactly on the last line: STRATEGIES_READY
    capture: strategy_result
    next: counterfactual_sim

  counterfactual_sim:
    action_type: prompt
    timeout: 600
    action: |
      For each strategy option in ${captured.run_dir.output}/strategy.md, simulate
      competitor responses: copy timeline, price/speed undercut, partnerships.
      Append a "## Counterfactual Simulations" section.
      Output exactly on the last line: SIM_COMPLETE
    capture: sim_result
    next: recommend

  recommend:
    action_type: prompt
    timeout: 600
    action: |
      Produce ranked recommendations from ${captured.run_dir.output}/strategy.md.
      For each: rank 1-N, confidence score (0.0-1.0), watch triggers, backlog actions.
      Append a "## Recommendations" section.
      Output the top-recommendation confidence score (e.g. 0.87) as the LAST LINE ONLY.
    capture: recommend_result
    evaluate:
      type: output_numeric
      operator: ge
      target: 0.0
    on_yes: done
    on_no: failed
    on_error: failed

  done:
    terminal: true

  failed:
    terminal: true
```

**MR-1 note**: `_validate_meta_loop_evaluation()` in `validation.py` classifies a loop as a meta-loop only when its action strings reference harness artifact paths (`loops/*.yaml`, `skills/*/SKILL.md`, `.issues/`, etc.). This loop writes to `run_dir` only, so MR-1 will not fire. The `output_contains` in `check_scan` and `output_numeric` in `position_analyze`/`recommend` are non-LLM evaluators that satisfy the acceptance criterion regardless.

**Route-shell split pattern**: `check_scan` has no `action:` or `action_type:` — it evaluates `${captured.scan_result.output}` directly via `evaluate: source:`. This is the established pattern from `backlog-flow-optimizer.yaml:route_bloat` and is valid per `schema.py:StateConfig`.

**Skeleton correction (init echo)**: The init state above uses `echo "$DIR"`, which captures a relative path. All other `run_dir`-capturing loops use `echo "$(pwd)/$DIR"` to capture an absolute path (`deep-research.yaml:34`, `canvas-sketch-generator.yaml`, `html-anything.yaml`). Change the final line of the init action to `echo "$(pwd)/$DIR"` so `${captured.run_dir.output}` resolves to an absolute path in all subsequent prompt states.

**Pattern validation**: All other skeleton constructs are confirmed valid against actual loop files — `capture:` + inline `evaluate:` on the same state (`apply-research.yaml:scored_items_raw`), `evaluate: source: "${captured.X.output}"` pattern (`backlog-flow-optimizer.yaml:route_bloat`), `output_numeric` with `operator: ge` (`apply-research.yaml`, `canvas-sketch-generator.yaml`), and evaluate-only states without `action:` (`backlog-flow-optimizer.yaml:route_bloat`).

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/` — new `market-strategy-optimize.yaml` file

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — `TestBuiltinLoopFiles::test_expected_loops_exist()` uses exact set equality over all loop stem names; adding the YAML without updating this set causes an `AssertionError` on CI — **required change, will break immediately**

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/_helpers.py` (get_builtin_loops_dir) and `cli/loop/run.py` — loop discovery/registry; no standalone `ll_loop.py` module exists
- `skills/create-loop/SKILL.md` — wizard should list the new loop as an option

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/loop/info.py` — `cmd_list()` auto-discovers built-in loops via `get_builtin_loops_dir()` and groups by `category`; `_load_loop_meta()` reads `description`/`category` from YAML frontmatter; no code change needed but confirms this file is in the dependency graph
- `scripts/little_loops/cli/loop/config_cmds.py` — `cmd_validate()` and `cmd_install()` resolve paths via `get_builtin_loops_dir()`; auto-discovers without code change
- `scripts/little_loops/cli/loop/__init__.py` — `main_loop()` dispatches all loop subcommands (list, validate, install, run, show); `--category` filter wired at line 284

### Similar Patterns
- `scripts/little_loops/loops/deep-research.yaml` (FEAT-1540) — another data-operating built-in loop
- `loops/` — existing built-in loop YAML files for structural conventions
- FEAT-723 (RL loops) — prior art for adding built-in loop families

### Tests
- `scripts/tests/test_ll_loop.py` — add validation test for the new loop YAML
- `scripts/tests/test_builtin_loops.py` — add integration test if this test file exists

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py::TestBuiltinLoopFiles::test_expected_loops_exist` — **UPDATE**: add `"market-strategy-optimize"` to the hardcoded `expected` set (line ~76–157); the 6 batch validators (`test_all_validate_as_valid_fsm`, `test_all_parse_as_yaml`, etc.) auto-pick up the new YAML via `rglob("*.yaml")` + `is_runnable_loop()` and run without change
- `TestMarketStrategyOptimizeLoop` (new class) in `scripts/tests/test_builtin_loops.py` — follow `TestEvaluationQualityLoop` pattern (lines 495–598); structural assertions: `init` captures `run_dir` scoped to `${context.run_dir}`, `check_scan` is evaluate-only (no `action:`), `output_numeric` evaluators present in `position_analyze` and `recommend`, both `done` and `failed` are terminal, `category: strategy` set, `max_iterations` and `timeout` defined

### Documentation
- `docs/reference/API.md` — document the new loop type if loop registry is documented
- `.claude/CLAUDE.md` — add to loop authoring section if relevant

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/README.md` — master catalog organized by category; no `Strategy` section exists; add a new `### Strategy` section with a `market-strategy-optimize` table entry (description, context variables, state graph summary)
- `docs/guides/LOOPS_REFERENCE.md` — built-in loops reference with `## Contents` table and per-category subsections; no `[Strategy]` section exists; add anchor link to contents and a `### Strategy` subsection with full entry (description, invocation example, `--set project_name=X --set competitors='[...]'`)
- `docs/guides/LOOPS_GUIDE.md` — `## Choose Your Loop` decision tree has no strategy/competitive-analysis path; consider adding `market-strategy-optimize` as the recommendation for product/competitive analysis use cases

### Configuration
- N/A (no config changes needed unless loop requires new config keys)

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Missing wizard files** — the wizard discovers loop types from hard-coded options, not by scanning the filesystem. Adding the YAML is sufficient for `ll-loop run` (CLI auto-discovers via `get_builtin_loops_dir()` in `_helpers.py:815`), but `/ll:create-loop` will not show it until these three files are updated:

- `skills/create-loop/SKILL.md` — Step 1 `AskUserQuestion` options list and the type-mapping section (add `"Strategy: Market (scan → model → position → generate → simulate → recommend)"` → `market-strategy-optimize`)
- `skills/create-loop/templates.md` — template selection Step 0.1 options list (add new entry)
- `skills/create-loop/loop-types.md` — add a "Strategy: Market" section with the question flow and YAML generation template

**Test file correction** — `scripts/tests/test_ll_loop.py` does not exist; the correct test file for CLI command tests is `scripts/tests/test_ll_loop_commands.py`. The built-in loop validation target is `scripts/tests/test_builtin_loops.py` (confirmed present).

## Implementation Steps

1. Design the full FSM state machine with exact transition predicates and schemas
2. Create `scripts/little_loops/loops/market-strategy-optimize.yaml` following existing built-in loop conventions
3. Define JSON Schema blocks for structured LLM states (opponent model, position, strategy, counterfactual, recommendation)
4. Wire the loop into the built-in registry so `/ll:create-loop` discovers it
5. Add `ll-loop validate` test coverage for the new loop
6. Run the loop against little-loops itself as a dogfooding validation

### Codebase Research Findings

_Added by `/ll:refine-issue` — corrections to steps 1, 3, and 4:_

- **Step 1**: Use the corrected YAML skeleton from the "Codebase Research Findings" subsection above (in Proposed Solution), not the original skeleton — it has 5 invalid constructs.
- **Step 3**: There are no `schema:` fields in FSM states (`schema.py:StateConfig.from_dict()` has no such field). Structured output is achieved by embedding JSON format instructions in the prompt text and using sentinel tokens for routing. The `opponent_model_schema`, `strategy_schema`, etc. in the original skeleton must be replaced with inline prompt instructions (see corrected skeleton above).
- **Step 4**: The CLI auto-discovers any YAML placed in `scripts/little_loops/loops/` (no Python registry change needed). The wizard (`/ll:create-loop`) requires manual edits to three files: `skills/create-loop/SKILL.md`, `skills/create-loop/templates.md`, and `skills/create-loop/loop-types.md`. See Integration Map research findings for details.
- **Step 5**: The correct test file is `scripts/tests/test_builtin_loops.py` (not `test_ll_loop.py` which does not exist). `ll-loop validate scripts/little_loops/loops/market-strategy-optimize.yaml` is the primary acceptance gate.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Update `scripts/tests/test_builtin_loops.py` — add `"market-strategy-optimize"` to the `expected` set in `TestBuiltinLoopFiles::test_expected_loops_exist()` (hard-coded allowlist causes immediate CI failure without this change)
8. Add `TestMarketStrategyOptimizeLoop` class to `scripts/tests/test_builtin_loops.py` — structural tests following `TestEvaluationQualityLoop` pattern (lines 495–598): verify `init` captures `run_dir`, `check_scan` is evaluate-only, `output_numeric` evaluators present in `position_analyze`/`recommend`, terminal states valid, `category: strategy` set
9. Update `scripts/little_loops/loops/README.md` — add `market-strategy-optimize` entry under a new `### Strategy` category section
10. Update `docs/guides/LOOPS_REFERENCE.md` — add `[Strategy]` anchor in `## Contents` and a `### Strategy` subsection with full reference entry (description, context variables, invocation example)

## Acceptance Criteria

- [ ] `ll-loop validate scripts/little_loops/loops/market-strategy-optimize.yaml` passes with no errors
- [ ] Loop appears in `/ll:create-loop` wizard as a selectable built-in template
- [ ] Loop completes a full run (market_scan → recommend) without state-transition errors
- [ ] Structured output schemas enforce valid strategy artifacts at each LLM state
- [ ] Non-LLM evaluator is paired with at least one LLM-structured state per MR-1
- [ ] Convergence or max-iterations terminates the loop cleanly (no infinite oscillation)
- [x] **Decision gate (from `/ll:audit-issue-conflicts` 2026-06-04)**: Before writing any loop YAML, a decision must be recorded (in this issue or a `decisions.yaml` entry) on whether `market-strategy-optimize` ships as a standalone bespoke YAML or as a `loop-composer` plan template. If the latter, this issue's scope changes from "create a new loop YAML" to "create a saved plan template for loop-composer." Do not implement until FEAT-1808 has shipped and the decision is resolved.
  - **Decision (2026-06-12, epic audit)**: Ship as a **standalone bespoke YAML**. FEAT-1808 shipped (`loops/loop-composer.yaml`, `loop-composer-adaptive.yaml`) but loop-composer generates plans at runtime and has no saved/reusable plan-template mechanism, so the template option is not implementable today. Include a comment in the loop YAML noting it can be re-expressed as a composer plan if saved plan templates land later. Stale `blocked_by: [FEAT-1808]` removed from frontmatter — FEAT-1808 is done; this issue is unblocked.

## Use Case

A project maintainer wants to understand whether to prioritize a new feature against competitor offerings. They run the market strategy loop, which:

1. Scans competitor products for similar features, pricing, and positioning
2. Models how each competitor would likely respond to different prioritization choices
3. Evaluates the project's current differentiation and market gaps
4. Generates 3-5 strategy options (e.g., "beat them on performance", "differentiate on automation", "target underserved use case")
5. Simulates opponent counter-moves for each option
6. Recommends a ranked list with confidence scores and "what to watch" triggers

The maintainer reviews the recommendation, optionally approves strategy changes, and the loop wires priority adjustments into the issue backlog.

## API/Interface

```yaml
# Loop invocation
ll-loop run market-strategy-optimize --set project_name=little-loops --set competitors="['tool-a', 'tool-b']"

# Structured output schemas (representative)
opponent_model_schema:
  type: object
  properties:
    competitors:
      type: array
      items:
        type: object
        properties:
          name: {type: string}
          strengths: {type: array, items: {type: string}}
          weaknesses: {type: array, items: {type: string}}
          likely_moves: {type: array, items: {type: string}}
          threat_level: {type: string, enum: [low, medium, high, critical]}

recommendation_schema:
  type: object
  properties:
    recommendations:
      type: array
      items:
        type: object
        properties:
          strategy: {type: string}
          rationale: {type: string}
          expected_outcome: {type: string}
          opponent_response_risk: {type: string, enum: [low, medium, high]}
          confidence: {type: number, minimum: 0, maximum: 1}
          suggested_actions:
            type: array
            items: {type: string}
```

## Impact

- **Priority**: P3 — New capability with no blocking urgency; extends the loop ecosystem for strategic use cases
- **Effort**: Medium — New YAML file with ~6 states and 4-5 JSON schemas, plus minor registry wiring
- **Risk**: Low — Isolated new file; no changes to existing loop execution engine; opt-in via wizard
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| [docs/ARCHITECTURE.md](../../docs/ARCHITECTURE.md) | Loop architecture and FSM execution model |
| [docs/reference/API.md](../../docs/reference/API.md) | Loop YAML schema and state type reference |
| [.claude/CLAUDE.md](../../.claude/CLAUDE.md) | Loop authoring guidelines and meta-loop rules (MR-1) |

## Labels

`built-in-loop`, `strategy`, `captured`

## Verification Notes

_Added by `/ll:verify-issues` on 2026-06-03_

**Verdict: NEEDS_UPDATE** — Integration Map had incorrect paths: `loops/builtin/` does not exist (correct path is `scripts/little_loops/loops/`), and `scripts/little_loops/ll_loop.py` does not exist (loop discovery is in `scripts/little_loops/cli/loop/_helpers.py` via `get_builtin_loops_dir()`). Both paths have been corrected. Blocked by FEAT-1808 which is still open.

## Go/No-Go Findings

_Updated by `/ll:go-no-go` on 2026-06-13 (re-evaluation after two `/ll:refine-issue` passes)_ — **NO-GO (CLOSE)**

**Deciding Factor**: The issue proposes hardcoding a 6-state FSM for a use case that `loop-composer` already handles dynamically and more flexibly — this is not a gap in the catalog but a redundancy.

### Key Arguments For
- FSM skeleton validated live against `load_and_validate` + `validate_fsm`: ERRORS: 0, WARNINGS: 0 — previous NO-GO's deciding factor (invalid FSM constructs) is resolved
- All pre-implementation gates cleared: FEAT-1808 done, standalone-vs-template decision recorded, purely additive implementation with no Python runtime changes

### Key Arguments Against
- `loop-composer` already solves this dynamically — `ll-loop run loop-composer --input "analyze competitive landscape for little-loops, model competitor strategies..."` decomposes into the same deep-research → apply-research → rn-plan sequence (`scripts/little_loops/loops/loop-composer.yaml`); this issue is a hardcoded duplicate
- Both `output_numeric` evaluators are structurally toothless: `position_analyze` requires `>= 1` (any integer passes), `recommend` requires `>= 0.0` (floor always passes) — Bernoulli variance p*(1-p) ≈ 0.0, far below CLAUDE.md's 0.05 threshold
- Skeleton in the issue document still contains the unfixed relative-path bug flagged at issue line 287 (`echo "$DIR"` vs `echo "$(pwd)/$DIR"`) — the 0-error validation was run against a corrected version not present in the issue
- FEAT-1810 scope note explicitly instructs re-expressing FEAT-1806 as a cluster plan after goal-cluster ships (FEAT-1987/1988/1989 done)

### Rationale
The CON side presents stronger codebase-grounded evidence: `loop-composer` already dynamically constructs the exact pipeline this issue proposes to hardcode, making it a solved problem rather than a catalog gap. The skeleton's live validation was run against a corrected version, not the issue document (which still has the relative-path bug at line 287). The evaluator thresholds are structurally toothless by the project's own Bernoulli variance standard. Recommended next action: close this issue; use `loop-composer` or `goal-cluster` for competitive analysis tasks.

## Session Log
- `/ll:go-no-go` - 2026-06-13T14:17:00 - `6747bf7f-02da-4eae-acca-8ca35f8b9b52.jsonl`
- `/ll:refine-issue` - 2026-06-13T14:08:53 - `6b9c1e02-7539-4e7d-9e9b-7bd373ea9a24.jsonl`
- `/ll:wire-issue` - 2026-06-13T14:01:56 - `0df548d1-097e-4c28-ab0b-0c0e9ac98101.jsonl`
- `/ll:refine-issue` - 2026-06-13T13:51:58 - `b451544d-3c45-4ad5-b7e6-476b2c79b92a.jsonl`
- `/ll:go-no-go` - 2026-06-13T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/412f0bab-649e-49a4-9b56-96b23ce1ab49.jsonl`
- `/ll:verify-issues` - 2026-06-05T21:00:23 - `current-session.jsonl`

- `/ll:verify-issues` - 2026-06-05T01:35:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/579edc97-1110-41b7-9283-1612d1e82fee.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T20:02:29 - `0860b18c-08b7-4093-862a-cc8046f35aaa.jsonl`
- `/ll:audit-issue-conflicts` - 2026-06-04T19:55:07 - `d0974b20-4737-4771-8c63-e70d193dc3d5.jsonl`
- `/ll:verify-issues` - 2026-06-04T04:21:13 - `94e89e68-ddb3-448e-a123-eae4ee9ba582.jsonl`
- `/ll:verify-issues` - 2026-06-02T22:48:42 - `21850d04-bdf9-4e28-bf74-f68eaaaed883.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:48:17 - `6805d559-982e-47e7-9513-9c8b17a1c054.jsonl`
- `/ll:audit-issue-conflicts` - 2026-05-31T21:34:34 - `922ffae8-14ce-45e5-a71a-02187250e8c9.jsonl`
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T04:44:25Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1065b200-e53c-4a55-9ff7-5c1d55a0cc90.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): Once FEAT-1808 (`loop-composer`) ships, evaluate whether this loop is better implemented as a loop-composer plan template (a saved JSON plan that invokes the relevant analysis loops in sequence: scan → model → analyze → generate → simulate → recommend) rather than a bespoke FSM YAML. If implemented before FEAT-1808 as a standalone YAML, include a comment that it can be re-expressed as a loop-composer plan template once FEAT-1808 is available.

**Note** (added by `/ll:audit-issue-conflicts` on 2026-06-04): Once FEAT-1810 (`goal-cluster`) ships, evaluate whether market-strategy batch analysis (multi-competitor scans, multi-market positioning) is better expressed as goal-cluster input batches rather than inline iteration within the FSM. The cluster's shared-context propagation and cross-batch synthesis may be a cleaner fit for competitive-intelligence aggregation than a monolithic loop.

---

## Status

**Open** | Created: 2026-05-29 | Priority: P3
