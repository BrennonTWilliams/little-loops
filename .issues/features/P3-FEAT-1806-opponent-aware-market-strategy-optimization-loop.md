---
id: FEAT-1806
title: Opponent-Aware Market Strategy Optimization Loop
type: FEAT
priority: P3
status: open
parent: EPIC-1811
discovered_date: 2026-05-29
discovered_by: capture-issue
captured_at: "2026-05-30T04:44:25Z"
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

Add a new built-in loop YAML under `loops/builtin/` following the existing pattern from FEAT-723 (RL loops) and FEAT-1540 (deep-research loop). The FSM design follows the standard `diagnose → propose → apply → measure-externally` shape, adapted for strategic analysis where "apply" means generating strategy artifacts rather than code changes.

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
# loops/builtin/market-strategy-optimize.yaml
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

## Integration Map

### Files to Modify
- `loops/builtin/` — new `market-strategy-optimize.yaml` file

### Dependent Files (Callers/Importers)
- `scripts/little_loops/ll_loop.py` — loop discovery/registry may need updating for new built-in
- `skills/create-loop/SKILL.md` — wizard should list the new loop as an option

### Similar Patterns
- `loops/builtin/deep-research.yaml` (FEAT-1540) — another data-operating built-in loop
- `loops/` — existing built-in loop YAML files for structural conventions
- FEAT-723 (RL loops) — prior art for adding built-in loop families

### Tests
- `scripts/tests/test_ll_loop.py` — add validation test for the new loop YAML
- `scripts/tests/test_builtin_loops.py` — add integration test if this test file exists

### Documentation
- `docs/reference/API.md` — document the new loop type if loop registry is documented
- `.claude/CLAUDE.md` — add to loop authoring section if relevant

### Configuration
- N/A (no config changes needed unless loop requires new config keys)

## Implementation Steps

1. Design the full FSM state machine with exact transition predicates and schemas
2. Create `loops/builtin/market-strategy-optimize.yaml` following existing built-in loop conventions
3. Define JSON Schema blocks for structured LLM states (opponent model, position, strategy, counterfactual, recommendation)
4. Wire the loop into the built-in registry so `/ll:create-loop` discovers it
5. Add `ll-loop validate` test coverage for the new loop
6. Run the loop against little-loops itself as a dogfooding validation

## Acceptance Criteria

- [ ] `ll-loop validate loops/builtin/market-strategy-optimize.yaml` passes with no errors
- [ ] Loop appears in `/ll:create-loop` wizard as a selectable built-in template
- [ ] Loop completes a full run (market_scan → recommend) without state-transition errors
- [ ] Structured output schemas enforce valid strategy artifacts at each LLM state
- [ ] Non-LLM evaluator is paired with at least one LLM-structured state per MR-1
- [ ] Convergence or max-iterations terminates the loop cleanly (no infinite oscillation)

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

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:13 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:capture-issue` - 2026-05-30T04:44:25Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1065b200-e53c-4a55-9ff7-5c1d55a0cc90.jsonl`

---

## Status

**Open** | Created: 2026-05-29 | Priority: P3
