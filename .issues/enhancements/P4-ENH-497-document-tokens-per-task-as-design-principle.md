---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 88
outcome_confidence: 100
---

# ENH-497: Document Tokens-per-Task as ll-auto/ll-parallel Design Principle

## Summary

Add an explicit architecture decision record establishing "tokens-per-task-completion" (not "tokens-per-request") as the correct efficiency metric for ll-auto, ll-parallel, and ll-sprint. This reframe affects compression decisions, context retention tradeoffs, and how we evaluate automation efficiency.

## Current Behavior

There is no documented guidance on how to measure or optimize token efficiency in our automation tools. The implicit assumption is that shorter conversations are better, which leads to over-aggressive compression that causes re-fetching, retries, and error cascades — costing more tokens overall.

## Expected Behavior

`docs/ARCHITECTURE.md` (or a new ADR) includes an explicit principle:

> **Efficiency metric: tokens-per-task, not tokens-per-request.**
> Over-aggressive compression that causes retries, re-reads, or error recovery is less efficient than a longer conversation that completes the task cleanly. When evaluating context compression tradeoffs in ll-auto/ll-sprint, optimize for task completion with minimum total tokens, not minimum per-turn tokens.

This principle should also inform the trigger threshold for context checkpoints (e.g., "compress at 70-80% utilization, not earlier").

## Motivation

This is a subtle but important reframe validated by published research. Without it, contributors naturally optimize for shorter individual turns, which can be counterproductive. Documenting it prevents re-learning the same lesson repeatedly and provides a rationale for design decisions that would otherwise appear wasteful.

Secondary benefit: it provides the conceptual foundation for the context degradation checkpoint work (ENH-499).

## Proposed Solution

1. Add a "Context Efficiency" section to `docs/ARCHITECTURE.md`
2. Define tokens-per-task as the primary metric
3. Explain why tokens-per-request is misleading for sequential automation
4. Document the 70-80% utilization compression trigger recommendation
5. Reference this principle from ll-auto and ll-sprint documentation where compression decisions are made

## Scope Boundaries

- **In scope**: Documentation only — `docs/ARCHITECTURE.md`, no code changes
- **Out of scope**: Actually implementing compression triggers (see ENH-499)

## Implementation Steps

1. Read `docs/ARCHITECTURE.md` to find the right insertion point
2. Draft "Context Efficiency" section with the principle, rationale, and implications
3. Add cross-references from relevant CLI tool documentation

## Integration Map

### Files to Modify
- `docs/ARCHITECTURE.md` — new `### Context Efficiency` sub-section within `## Key Design Decisions`

### Related Issues
- ENH-499 — Context degradation checkpoints (implements this principle) — **COMPLETED** (in `.issues/completed/`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — Exact insertion point in ARCHITECTURE.md:_

**Best insertion point:** After `### Context Monitor and Session Continuation` section (which ends at approximately line 839), before `## Data Flow Summary` (at approximately line 842). This slots the new section inside `## Key Design Decisions` (line 694) alongside related automation design rationale.

**Structure of `## Key Design Decisions` (existing sub-sections):**
```
## Key Design Decisions (line 694)
├── ### Git Worktree Isolation     (line 696)
├── ### Sequential Merging         (line 719)
├── ### State Persistence          (line 738)
├── ### Merge Strategy             (line 757)
├── ### Context Monitor and Session Continuation  (line 771)
└── ### Context Efficiency         ← INSERT HERE (after ~line 839)

## Data Flow Summary               (line 842)
```

**Existing 80% threshold documentation** (`docs/ARCHITECTURE.md:851`): The `auto_handoff_threshold: 80` config value is documented in the Context Monitor section (confirmed line 851 in current file). ENH-497's compression trigger recommendation directly references this — the new section should cross-link to the existing config block.

**ENH-499 status (COMPLETED)**: ENH-499 (context degradation checkpoints) is in `.issues/completed/` — it was completed. Its proposed `context_checkpoint_threshold` (default 70%) is NOT present in `config-schema.json`, suggesting the inter-issue checkpoint threshold may have been implemented differently or omitted. The draft section below uses only the confirmed `auto_handoff_threshold: 80` value; do not reference `context_checkpoint_threshold` until confirmed.

**Internal research support**: `docs/research/LCM-Lossless-Context-Management.md` (Ehrlich & Blackman, arXiv:submit/7269166) directly validates the tokens-per-task principle — Section 2.4 documents "Zero-Cost Continuity" where below the soft threshold no summarization overhead occurs; Section 4.3 notes that over-aggressive chunking introduces error variance. This paper is available to cite as supporting evidence in the new section.

**Cross-reference scope confirmed**: `docs/reference/CLI.md` contains no context management coverage. Cross-references should target `docs/ARCHITECTURE.md` only; no changes needed to CLI docs.

**Exact insertion point (confirmed)**: After the `---` separator at line 863 (end of `### Context Monitor and Session Continuation`), before `## Data Flow Summary` at line 865. The `---` separator at line 863 is the boundary line.

**Draft section content:**
```markdown
### Context Efficiency

> **Efficiency metric: tokens-per-task, not tokens-per-request.**

For ll-auto, ll-parallel, and ll-sprint, the correct optimization target is minimizing total tokens consumed per completed issue, not per individual turn. Over-aggressive compression that causes retries, re-reads, or error recovery is less efficient than a longer conversation that completes the task cleanly.

This principle is validated by published research on long-context LLM architectures (see `docs/research/LCM-Lossless-Context-Management.md`, Section 4.3): systems that aggressively chunk context introduce variance and error cascades, while systems that preserve working context through task completion achieve better reliability per token.

**Implications for compression decisions:**
- Compress at 80% context utilization (see `auto_handoff_threshold` in the section above), not earlier
- Prefer keeping relevant tool outputs in context over re-fetching when needed again
- A failed task that restarts from scratch costs more tokens than a task that completes in a longer conversation

**Relationship to ENH-499**: The inter-issue context checkpoint (implemented in ENH-499) applies this principle at issue boundaries — it triggers a structured summarization reset rather than re-running tool calls to reconstruct state.
```

## Impact

- **Priority**: P4 — Documentation only; low urgency
- **Effort**: Low — Writing only
- **Risk**: Low
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/ARCHITECTURE.md` | Target file — new `### Context Efficiency` section inserts after line 839 (inside `## Key Design Decisions`); existing `auto_handoff_threshold` docs at lines 819–832 |

## Labels

`enhancement`, `documentation`, `context-engineering`, `architecture`

## Verification Notes

- **2026-03-05** — VALID. `docs/ARCHITECTURE.md` exists; no `### Context Efficiency` section present; `## Key Design Decisions` section confirmed; `auto_handoff_threshold: 80` documented. Insertion point after `### Context Monitor and Session Continuation` remains valid.

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Identified insertion point in ARCHITECTURE.md (after line ~839, inside ## Key Design Decisions, after Context Monitor section)
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by FEAT-441
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9c629849-3bc7-41ac-bef7-db62aeeb8917.jsonl`
- `/ll:refine-issue` - 2026-03-03T23:10:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` - Linked `docs/ARCHITECTURE.md` (line 839) to Related Key Documentation
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:verify-issues` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7e4136f8-62b5-4ca5-a35a-929d4c59fd71.jsonl`
- `/ll:refine-issue` - 2026-03-06 - Codebase research: confirmed ENH-499 COMPLETED (in .issues/completed/); `context_checkpoint_threshold` NOT in config-schema.json; `auto_handoff_threshold: 80` confirmed at ARCHITECTURE.md:851; LCM research paper (docs/research/LCM-Lossless-Context-Management.md §4.3) cited as internal support; CLI.md has no context coverage so no cross-refs needed there; exact insertion point confirmed (after line 863 `---`, before `## Data Flow Summary`); draft content updated to remove unconfirmed 70% threshold reference
- `/ll:confidence-check` - 2026-03-06 - Re-scored: ready=88 (up from 80), outcome_confidence=100 — all knowledge gaps closed: insertion point confirmed, draft finalized, ENH-499 status resolved, cross-reference scope narrowed
- `/ll:verify-issues` - 2026-03-06T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/f8de0c26-1ae9-4a68-b489-a58a6458da2f.jsonl` — VALID: no Context Efficiency section in ARCHITECTURE.md
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: `### Context Efficiency` section still absent from ARCHITECTURE.md

---

## Status

**Open** | Created: 2026-02-24 | Priority: P4

## Blocked By
- ENH-665
