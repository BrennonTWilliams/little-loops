---
id: FEAT-1791
title: `check_contract` Boundary-Mismatch Evaluator
type: FEAT
priority: P3
captured_at: '2026-05-29T19:08:54Z'
discovered_date: '2026-05-29'
discovered_by: capture-issue
status: open
labels: [feature, loops, evaluator, qa, integration]
parent: EPIC-1663
---

# FEAT-1791: `check_contract` Boundary-Mismatch Evaluator

## Summary

Add a new evaluator kind (`check_contract` / `evaluate.type: contract`) that reads two related artifacts simultaneously and asserts contract alignment between them — API response shape ↔ consumer hook type, file path ↔ link `href`, state-transition map ↔ actual `.update({status})` calls. Designed as a stronger replacement for `check_semantic` in build-feature harnesses where "did this PR break the contract between producer and consumer?" is the actual quality bar.

## Current Behavior

The loop FSM currently provides these evaluator types:

- **Mechanical**: `exit_code`, `output_numeric`, `mcp_result`, `convergence`, `diff_stall`
- **Semantic**: `llm_structured` (evaluates a single output blob against a prompt)

None of these evaluators read *both sides of an interface simultaneously*. When a harness implements a producer (e.g., API endpoint) and a consumer (e.g., front-end hook), there is no built-in way to assert that their contracts align. Harness authors must hand-roll paired checks inside `check_semantic` prompts, which are single-output evaluators by design and tend to evaluate one artifact at a time.

## Expected Behavior

A new `contract` evaluator type (`evaluate.type: contract`) is available. Harness authors declare one or more `(producer, consumer)` pairs with optional regex extraction patterns and a contract rule. The evaluator:

1. Reads both files in each pair
2. Applies optional regex to extract the relevant slices
3. Composes a focused LLM judge prompt with both slices side-by-side
4. Returns a per-pair verdict and routes the FSM accordingly

Verdicts: `yes` (all pairs aligned → `on_yes`), `no` (any pair fails → `on_no`), `error` (file unreadable or regex no-match → `on_no`).

## Motivation

`revfactory/harness`'s `qa-agent-guide.md` documents (with 7 production bug case studies from SatangSlide) a failure class our current evaluators miss: **boundary mismatch** — two components each correctly implemented but disagreeing at the integration seam. Static type checks and existence checks miss these because:

- TypeScript generic casts (`fetchJson<SlideProject[]>()`) make the compiler accept any runtime shape
- `npm run build` exit-code 0 ≠ runtime correctness
- "API endpoint exists" ≠ "API response shape matches consumer expectation"

Our current evaluators address two layers — mechanical (`exit_code`, `output_numeric`, `mcp_result`) and semantic (`llm_structured`) — but nothing reads *both sides of an interface at once*. `check_semantic` could in principle do this with the right prompt, but in practice it tends to evaluate a single output blob, not a paired (producer, consumer) read.

This issue formalizes the pattern as a distinct evaluator kind so harness authors can declare integration gates explicitly rather than hand-rolling them in semantic prompts.

## Use Case

A user has a harness that implements a new API endpoint and its corresponding front-end hook. They want to gate progression on shape alignment. They write:

```yaml
check_contract:
  action_type: contract
  pairs:
    - producer: "src/app/api/projects/route.ts"
      producer_pattern: "NextResponse\\.json\\((.+?)\\)"
      consumer: "src/hooks/useProjects.ts"
      consumer_pattern: "fetchJson<(.+?)>"
      contract: "shape and field names must align (camelCase on both sides, no wrapping mismatch)"
  evaluate:
    type: contract
  on_yes: check_invariants
  on_no: execute
```

The evaluator reads both files, extracts the producer's response shape and the consumer's expected type, and asks an LLM judge a focused question: *"Does this producer shape satisfy this consumer contract?"* — with both code blocks in the prompt. Routes to `on_yes` only on a clean match.

## API/Interface

New evaluator kind:

```yaml
evaluate:
  type: contract
```

State-level config (under the state, not under `evaluate`):

```yaml
check_contract:
  action_type: contract  # new action_type — runs the contract read+compare, no shell needed
  pairs:                 # one or more producer/consumer pairs
    - producer: <path>
      producer_pattern: <regex>   # optional — extract just the relevant slice
      consumer: <path>
      consumer_pattern: <regex>
      contract: <string>          # the alignment rule the judge enforces
  evaluate:
    type: contract
    severity: error               # any pair-level failure routes on_no
  on_yes: <state>
  on_no: <state>
```

Verdicts: `yes` (all pairs aligned), `no` (any pair fails), `error` (file unreadable / pattern matches zero hits).

## Implementation Steps

1. **Schema** — extend `ll-loop validate` to accept `action_type: contract` and `evaluate.type: contract`; validate `pairs` structure (list of dicts with required `producer`, `consumer`, `contract`).
2. **Runner** — new evaluator in `scripts/little_loops/evaluators/contract.py`: reads each pair, applies optional regex extraction, composes a judge prompt with both slices side-by-side, calls the host runner via `resolve_host().build_blocking_json(...)`.
3. **Verdict normalization** — return `{verdict: yes|no|error, pair_results: [...]}` so `audit-loop-run` can render which pair failed.
4. **Tests** — pytest cases: aligned pair (yes), mismatched field names (no), camelCase/snake_case mismatch (no), missing file (error), regex no-match (error). Mock host runner.
5. **Docs** — add `check_contract` section to `AUTOMATIC_HARNESSING_GUIDE.md` under "Evaluation Phases Explained", placed between `check_mcp` and `check_skill` (it's deterministic-input + LLM-judged, cheaper than `check_skill`'s full agentic session).
6. **Example loop** — add a `loops/examples/contract-demo.yaml` or extend `harness-multi-item.yaml` with a commented `check_contract` block.

## Integration Map

### Files to Modify
- `scripts/little_loops/evaluators/contract.py` (new)
- `scripts/little_loops/loops/schema.py` (extend evaluator type enum)
- `scripts/little_loops/loops/runner.py` (wire new evaluator)
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md`

### Dependent Files (Callers/Importers)
- `scripts/little_loops/loops/loop_runner.py` — imports evaluator registry
- `scripts/little_loops/cli/ll_loop.py` — `validate` subcommand imports schema

### Similar Patterns
- Existing evaluators in `scripts/little_loops/evaluators/` for structural conventions
- `check_semantic` evaluator for LLM judge call patterns

### Tests
- `scripts/tests/test_contract_evaluator.py` (new) — aligned, mismatched, file-missing, regex-no-match cases

### Documentation
- `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` — add `check_contract` section between `check_mcp` and `check_skill`

### Configuration
- N/A

## Acceptance Criteria

- [ ] `ll-loop validate` accepts the new schema and rejects malformed `pairs:` blocks with clear errors
- [ ] Evaluator runs without spawning a shell action (action_type: contract is self-contained)
- [ ] Multi-pair states report which specific pair failed
- [ ] Documentation added to AUTOMATIC_HARNESSING_GUIDE.md with placement guidance
- [ ] Tests cover aligned, mismatched, file-missing, regex-no-match cases

## Impact

- **Priority**: P3 — Important for harness quality but not blocking existing workflows; `check_semantic` is an available workaround
- **Effort**: Medium — New evaluator module (~100-150 lines), schema extension, tests, and docs; no changes to existing evaluators
- **Risk**: Low — Net-new code path behind `action_type: contract`; existing loops and evaluators unaffected
- **Breaking Change**: No

## Out of Scope

- Auto-detecting producer/consumer pairs from the codebase (that's a separate skill, possibly an extension to `/ll:audit-architecture`).
- Code mutation to *fix* mismatches (this evaluator only reports; fixes belong to the harness's `execute` retry).

## Related Key Documentation

| Path | Why relevant |
|------|--------------|
| `docs/guides/AUTOMATIC_HARNESSING_GUIDE.md` | New evaluator slots into the existing chain documentation |
| `scripts/little_loops/evaluators/` | Where the implementation lands |
| `scripts/little_loops/loops/harness-multi-item.yaml` | Example loop to extend with `check_contract` demo |

## Session Log
- `/ll:verify-issues` - 2026-05-31T05:40:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e9b1fe44-19f3-4b83-9d6b-0194f265fb9a.jsonl`
- `/ll:verify-issues` - 2026-05-31T02:30:15 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5267cfef-4fe8-420d-9d08-62e8f926a297.jsonl`
- `/ll:format-issue` - 2026-05-29T19:28:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/aea29468-dd94-4692-a4e8-f97561c7c2a7.jsonl`
- `/ll:capture-issue` - 2026-05-29T19:08:54Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5f057c8d-4a84-4a3e-a47b-50580694d9d6.jsonl`

---

## Status
open
