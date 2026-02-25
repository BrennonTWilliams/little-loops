---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-501: Forward-Message Pattern for ll-parallel Result Fidelity

## Summary

Supervisor architectures lose fidelity when they paraphrase sub-agent outputs (the "Telephone Game Problem"). In ll-parallel, worktree agents produce detailed implementation reports that are aggregated by the orchestrator. Investigate whether the aggregation step is losing fidelity, and if so, implement a direct-pass-through pattern where sub-agent reports are forwarded verbatim to the user/log rather than synthesized by the coordinator.

## Current Behavior

ll-parallel uses git worktrees to run isolated sub-agents in parallel. After completion, a merge coordinator aggregates results. The coordinator reads each worktree's output and synthesizes a summary report. This synthesis step may paraphrase or compress information from sub-agents, potentially losing important detail about what changed, what failed, and why.

Research benchmarks (LangGraph) showed supervisor architectures performing 50% worse on downstream tasks because supervisor synthesis introduced errors and omissions that sub-agents had correctly captured.

## Expected Behavior

Sub-agent completion reports from each worktree are:
1. Written verbatim to a structured file (`thoughts/ll-parallel/<run-id>/<issue-id>-report.md`)
2. Forwarded directly to the final output log without synthesis-induced paraphrasing
3. The coordinator's role is **routing and aggregation** (merge, conflict detection), not **synthesis** (rewriting sub-agent findings)

## Motivation

This is a targeted fix for a specific failure mode. The worktree architecture already provides context isolation (which is good). The risk is in the aggregation step, not the isolation step. If our coordinator is rewriting sub-agent reports in its own words, we may be discarding signal that was correctly captured by the sub-agent.

This is worth investigating before implementing: if our coordinator already forwards verbatim, no change is needed.

## Proposed Solution

**Phase 1 (Investigation)**:
1. Review `scripts/little_loops/merge_coordinator.py` (or equivalent)
2. Identify whether sub-agent reports are paraphrased or forwarded verbatim
3. If forwarded verbatim, close this issue as not needed

**Phase 2 (If paraphrasing found)**:
1. Add structured report format for sub-agent completion (four-section schema from ENH-495)
2. Implement verbatim forwarding: coordinator reads sub-agent report file and includes it directly in output
3. Limit coordinator synthesis to coordination concerns only: merge conflicts, file contention, timing

## Scope Boundaries

- **In scope**: Investigating coordinator synthesis behavior; implementing verbatim forwarding if needed; structured sub-agent report format
- **Out of scope**: Changes to worktree creation, git operations, or issue selection logic

## Implementation Steps

1. Read `scripts/little_loops/merge_coordinator.py` to understand current aggregation behavior
2. Assess: is sub-agent output paraphrased or forwarded?
3. If paraphrasing: define sub-agent report schema, implement verbatim forwarding
4. If already verbatim: close issue, add a note about why the current approach is correct

## Integration Map

### Files to Modify (if Phase 2 needed)
- `scripts/little_loops/merge_coordinator.py` — forwarding logic
- `scripts/little_loops/parallel.py` — sub-agent report format

### Related Issues
- ENH-499 — Context degradation (complementary; addresses sequential not parallel)
- ENH-495 — Anchored summarization (report format)

### Tests
- Read a sample ll-parallel run log and compare sub-agent output to coordinator summary
- If paraphrasing found: regression test that coordinator output contains key sub-agent facts verbatim

## Impact

- **Priority**: P3 — Moderate; depends on investigation findings
- **Effort**: Low (investigation) to High (if Phase 2 needed)
- **Risk**: Low — Investigation first; Phase 2 only if warranted
- **Breaking Change**: No

## Labels

`enhancement`, `context-engineering`, `ll-parallel`, `multi-agent`, `fidelity`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
