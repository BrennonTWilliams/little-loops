---
id: ENH-2841
type: ENH
title: Move <example> blocks out of agent descriptions to cut ~1.9K tokens from every invocation
priority: P3
status: done
captured_at: '2026-07-27T00:22:46Z'
discovered_date: 2026-07-26
discovered_by: capture-issue
parent: EPIC-2456
relates_to:
- ENH-2714
- ENH-2839
- BUG-2840
- EPIC-2456
labels:
- token-cost
- agents
- context-window
completed_at: '2026-07-27T00:22:46Z'
---

# ENH-2841: Move `<example>` blocks out of agent descriptions to cut ~1.9K tokens from every invocation

## Summary

The `description:` frontmatter of every file in `agents/` is injected into the
static prefix of **every** invocation — interactive and automated alike. All 9
agent descriptions embedded 3–5 full `<example>` blocks each, making `agents/`
the single densest slice of the injected catalog at 3,353 tokens for 9 files
(vs. 3,188 for 71 skills).

Moving the examples into each agent's **body** — which loads only when that
agent actually runs — cuts the injected total to 1,395 tokens, a **~1,905-token
saving on every invocation**, while preserving the examples for the agent
itself.

## Motivation

Discovered while measuring ENH-2714's realized savings (ENH-2839). The static
breakdown showed the catalog, not CLAUDE.md, was the largest prunable bucket —
and that `agents/` carried disproportionate weight per file.

This lever is strictly better than the pruning feature it was found alongside:

| | Realized saving | Config surface | Host dependency | Applies to |
|---|---:|---|---|---|
| `pruning_profile:` (ENH-2714, as shipped) | ~970 tokens | loop/state YAML | env-signal only | automation only |
| `agents/` description trim | **~1,905 tokens** | none | none | every invocation |

The trim recovers nearly **2x the entire realized benefit** of the pruning
feature, with no config surface, no `ll-doctor` capability check, and no
correctness risk — and unlike pruning it also benefits interactive sessions.

## Current Behavior

Per-file injected description cost, before:

| Agent | desc tokens | examples |
|---|---:|---:|
| loop-specialist | 520 | 3 |
| codebase-pattern-finder | 395 | 3 |
| codebase-locator | 380 | 3 |
| workflow-pattern-analyzer | 370 | 3 |
| codebase-analyzer | 352 | 3 |
| prompt-optimizer | 344 | 3 |
| plugin-config-auditor | 321 | 3 |
| consistency-checker | 314 | 3 |
| web-search-researcher | 304 | 5 |
| **Total** | **3,300** | |

## Expected Behavior

Descriptions carry only what the dispatcher needs to route correctly; long-form
examples live in the body, loaded on demand when the agent runs.

## Implementation

Mechanical transform across all 9 files:

1. Strip `<example>…</example>` blocks from the `description:` block scalar.
2. Append them to the body under a `## When to use` heading.
3. Retain in the description: the purpose sentence, the "When NOT to use" list,
   and the trigger-keywords line — these are the actual dispatch signal.

Result: **3,300 → 1,395 tokens** injected (saved 1,905).

Retaining the negative-trigger list was deliberate. It is compact and prevents
misdispatch, which is the failure mode that costs the most; the examples were
the bulk of the weight without being the bulk of the routing signal.

## Trade-off

Examples no longer inform the *dispatch* decision — only the agent's own
execution once selected. Accepted because the purpose sentence, the
"When NOT to use" list, and the explicit trigger keywords remain, and those are
the more direct routing signal. If dispatch accuracy regresses, the remedy is to
fold one compact exemplar phrase into the trigger-keywords line rather than to
restore full `<example>` blocks.

## Acceptance Criteria

- [x] All 9 `agents/*.md` descriptions have `<example>` blocks removed.
- [x] Examples preserved in each agent body under `## When to use`.
- [x] Purpose sentence, "When NOT to use", and trigger keywords retained.
- [x] Frontmatter still parses as valid YAML on all 9 files.
- [x] Codex adapter, claude-code adapter, loop-specialist eval, and wiring
      suites pass.
- [x] Full suite green.

## Impact

~1,905 tokens off every invocation, project-wide. Post-trim the injected
catalog drops from ~8,334 to ~6,429 tokens, which also lowers the ceiling on
what a future `suppress_catalog` implementation could recover.

## Scope Boundaries

**In scope:** the 9 files in `agents/`, description-only changes, examples
relocated to the body.

**Out of scope:** `skills/*/SKILL.md` and `commands/*.md` descriptions (larger
in aggregate but not audited here), adding a budget check for agent
descriptions, and any change to agent behavior, tools, or model settings.

## Status

Completed and verified, but **uncommitted** — the change lives only in the
working tree, and it was already silently reverted once this session by a
concurrent agent. Nothing in the test suite pins it (those suites use synthetic
fixtures), so it will regress unnoticed if the tree is discarded again.

## Session Log
- `hook:posttooluse-status-done` - 2026-07-27T00:25:06 - `a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`
- interactive session - 2026-07-27T00:22:46Z - `a2c83098-37d1-4d7b-86d1-fbf55d285134.jsonl`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-07-27
- **Status**: Completed
- **Implementation**: Mechanical extraction of `<example>` blocks from
  `description:` frontmatter into a `## When to use` body section across all 9
  agent definitions.

### Verification

- YAML frontmatter parses on all 9 files; every `description` non-empty.
- 280 passed across `test_adapt_agents_for_codex.py`,
  `test_claude_code_adapter.py`, `test_feat1544_loop_specialist_eval.py`,
  `test_wiring_skills_and_commands.py`.
- Full suite: **16,436 passed, 42 skipped**, exit 0.
- Tests in these suites use synthetic fixtures rather than the real `agents/`
  files, so they do not pin the trim — it is unguarded against reversion.

### Files Changed

`agents/codebase-analyzer.md`, `agents/codebase-locator.md`,
`agents/codebase-pattern-finder.md`, `agents/consistency-checker.md`,
`agents/loop-specialist.md`, `agents/plugin-config-auditor.md`,
`agents/prompt-optimizer.md`, `agents/web-search-researcher.md`,
`agents/workflow-pattern-analyzer.md` — 9 files, 201 insertions, 174 deletions.

**Uncommitted at time of writing.** The trim was applied once, silently reverted
by a concurrent session (`b1141b9c`) that discarded working-tree changes while
cleaning unrelated repo pollution, and re-applied. It remains in the working
tree only.

### Follow-ups

- `ll-verify-skill-budget` polices skill descriptions but nothing polices agent
  descriptions; a budget check over `agents/*.md` would prevent regrowth.
- Same trim may apply to `skills/*/SKILL.md` descriptions (3,188 tokens across
  71 files) and `commands/*.md` (1,793 across 29) — not audited here.
