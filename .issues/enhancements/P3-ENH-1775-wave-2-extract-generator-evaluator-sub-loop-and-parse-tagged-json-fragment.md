---
captured_at: "2026-05-29T01:01:55Z"
discovered_date: 2026-05-28
discovered_by: capture-issue
parent: EPIC-1773
---

# ENH-1775: Wave 2 — Extract `generator-evaluator` Sub-loop and Add `parse_tagged_json` Fragment

## Summary

Extract the most-duplicated multi-state pattern in the codebase — the `generate → evaluate (Playwright) → score (LLM rubric) → iterate` cycle used by 5 harness loops — into a standalone `generator-evaluator` sub-loop. Also add a `parse_tagged_json` fragment to unify the tagged-JSON-line parsing pattern shared by 3 integration loops.

## Current Behavior

**Generator-Evaluator pattern** — 5 harness loops each reimplement the full cycle inline:

- `html-website-generator.yaml`
- `svg-image-generator.yaml`
- `html-anything.yaml`
- `hitl-md.yaml`
- `hitl-compare.yaml`

Each duplicates: Playwright screenshot invocation, CAPTURED/ALL_PASS output_contains routing, critique.md writeback, and the multi-criterion weighted rubric scoring pattern with structured output.

**Tagged JSON parsing** — 3 integration loops each contain a near-identical python3 heredoc that parses a tagged JSON line from LLM output:

- `adopt-third-party-api.yaml` — parses `ENUMERATE_JSON:` tag
- `integrate-sdk.yaml` — parses `ENUMERATE_JSON:` tag
- `assumption-firewall.yaml` — parses `ASSUMPTIONS_JSON:` tag

Each duplicates the python3 invocation, line-splitting, tag-matching, and JSON extraction.

## Expected Behavior

**`generator-evaluator` sub-loop** at `loops/oracles/generator-evaluator.yaml`:

Accepts parameters: generate prompt, rubric criteria, pass_threshold, design_tokens_context, run_dir. The 5 parent loops become thin wrappers that supply these inputs and delegate to the sub-loop.

**`parse_tagged_json` fragment** in `loops/lib/common.yaml`:

```yaml
parse_tagged_json:
  action_type: shell
  action: |
    python3 -c "
    import sys, json
    text = sys.stdin.read()
    for line in text.splitlines():
        if '${context.json_tag}:' in line:
            print(line.split('${context.json_tag}:', 1)[1].strip())
            break
    "
```

Callers set `context.json_tag` (e.g., `ENUMERATE_JSON`, `ASSUMPTIONS_JSON`).

## Motivation

The generator-evaluator cycle is the most-repeated multi-state pattern in the entire codebase. A bug in the Playwright invocation or rubric scoring currently requires fixing 5 separate files. The tagged-JSON parsing pattern is identical across 3 loops but differed only in the tag string — a clear case for parameterization.

## Proposed Solution

1. Design `generator-evaluator` sub-loop with parameterized inputs
2. Extract the sub-loop to `loops/oracles/generator-evaluator.yaml`
3. Convert all 5 harness loops to delegate to the sub-loop
4. Add `parse_tagged_json` fragment to `loops/lib/common.yaml`
5. Convert all 3 integration loops to use the fragment
6. Run `ll-loop validate` on all modified loops and the new sub-loop
7. Run `python -m pytest scripts/tests/ -v --tb=short`

## Integration Map

### Files to Modify
- `loops/oracles/generator-evaluator.yaml` — new sub-loop
- `loops/html-website-generator.yaml` — convert to thin wrapper
- `loops/svg-image-generator.yaml` — convert to thin wrapper
- `loops/html-anything.yaml` — convert to thin wrapper
- `loops/hitl-md.yaml` — convert to thin wrapper
- `loops/hitl-compare.yaml` — convert to thin wrapper
- `loops/lib/common.yaml` — add `parse_tagged_json` fragment
- `loops/adopt-third-party-api.yaml` — convert parse_enumeration state
- `loops/integrate-sdk.yaml` — convert parse_enumeration state
- `loops/assumption-firewall.yaml` — convert extract_assumptions state

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop_cmd.py` — `ll-loop validate` must resolve oracle sub-loops and new fragment

### Similar Patterns
- `svg-textgrad.yaml` — may also use generator-evaluator pattern; evaluate for conversion

### Tests
- `scripts/tests/` — regression suite; verify sub-loop can be validated independently

### Documentation
- N/A — no user-facing docs changes

### Configuration
- N/A

## Implementation Steps

1. Design sub-loop interface: identify required context variables and outputs
2. Extract `generator-evaluator` sub-loop to `loops/oracles/generator-evaluator.yaml`
3. Add `parse_tagged_json` fragment to `loops/lib/common.yaml`
4. Convert 5 harness loops to delegate to `generator-evaluator` sub-loop
5. Convert 3 integration loops to use `parse_tagged_json` fragment
6. Run `ll-loop validate` on every modified loop and the new sub-loop
7. Run `python -m pytest scripts/tests/ -v --tb=short`

## API/Interface

N/A — Internal loop composition interfaces only. Sub-loop parameters and fragment YAML contract are detailed in Expected Behavior.

## Success Metrics

- `generator-evaluator` sub-loop eliminates 5 duplicate generate→evaluate→score→iterate cycles
- `parse_tagged_json` fragment eliminates 3 duplicate python3 heredoc parsing states
- New sub-loop passes `ll-loop validate` independently
- All 8 modified loops pass `ll-loop validate`
- Test suite passes with no regressions

## Scope Boundaries

- Sub-loop extraction and fragment addition only — no behavioral changes to the generate/evaluate/score cycle
- The sub-loop is an oracle (called by parent loops), not a standalone runnable loop
- Only the listed loops; `svg-textgrad.yaml` conversion is out of scope for this wave

## Impact

- **Priority**: P3 — High ROI but non-urgent; significant deduplication but no user-facing impact
- **Effort**: Medium — Sub-loop extraction requires careful interface design to avoid breaking 5 callers
- **Risk**: Medium — Sub-loop extraction is the most complex refactoring in the epic; the 5 harness loops have subtle differences that must be parameterized correctly
- **Breaking Change**: No

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Loop composition and sub-loop delegation |
| guidelines | .claude/CLAUDE.md | Loop authoring conventions, meta-loop design rules |

## Labels

`enhancement`, `captured`

## Session Log
- `/ll:format-issue` - 2026-05-29T01:15:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/29882a14-54b1-4f76-8bb9-fe34f236114f.jsonl`
- `/ll:capture-issue` - 2026-05-29T01:01:55Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17b05161-9ff0-48f9-baaf-69470f937b48.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts` 2026-05-28): The `generator-evaluator` sub-loop embeds rubric scoring (`ll_rubric_score` equivalent) as part of its evaluate-score-iterate cycle. ENH-1776 (Wave 3) extracts `ll_rubric_score` as a standalone fragment — it MUST target this sub-loop's internal `score` state rather than the 5 parent wrapper loops, since those wrappers no longer contain inline rubric states after Wave 2. The `parse_tagged_json` fragment and Wave 3's `enumerate-prove-flow` share `adopt-third-party-api.yaml` and `integrate-sdk.yaml` as integration targets; the flow MUST compose from the fragment rather than inlining its own parse logic.

---

## Scope Addition

**Source**: Merged from ENH-1774 (Wave 1) during `/ll:audit-issue-conflicts` conflict resolution.

The following fragments from ENH-1774 are now part of this wave:

- **`ll_commit` fragment** in `loops/lib/cli.yaml` — eliminates 6 duplicate commit-state implementations across `dead-code-cleanup.yaml`, `test-coverage-improvement.yaml`, `backlog-flow-optimizer.yaml`, `issue-staleness-review.yaml`, `docs-sync.yaml`, and `incremental-refactor.yaml`.
- **`playwright_screenshot` fragment** in `loops/lib/harness.yaml` — eliminates 5 duplicate Playwright screenshot implementations. The `generator-evaluator` sub-loop MUST compose from this fragment rather than inlining its own screenshot logic.

The Integration Map, Implementation Steps, and caller conversion plan from ENH-1774 are absorbed here.

## Status

**Open** | Created: 2026-05-28 | Priority: P3
