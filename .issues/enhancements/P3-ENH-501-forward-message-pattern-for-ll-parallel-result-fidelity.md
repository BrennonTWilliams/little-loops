---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
confidence_score: 80
outcome_confidence: 71
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — Investigation of `merge_coordinator.py` completed:_

**Phase 1 Investigation Result: MergeCoordinator does NOT synthesize sub-agent output.**

`merge_coordinator.py` is a pure git orchestrator. It has no concept of "reports" or sub-agent output:

- **Input**: `MergeRequest` objects wrapping `WorkerResult` (contains `issue_id`, `branch_name`, `worktree_path` — git metadata only, not text)
- **Processing**: The `_process_merge()` method (`merge_coordinator.py:690-915`) performs only git operations: stash, checkout, pull --rebase, merge --no-ff, unstash
- **Output interface**: Three read-only properties — `merged_ids` (list of merged issue IDs), `failed_merges` (dict of ID→error string), `stash_pop_failures` (dict)
- **No file reading**: Does not read worktree output files; only reads `git status --porcelain` output and git command return codes

**Consequence**: There is no "synthesis" step happening in MergeCoordinator. The Telephone Game Problem described in this issue is not occurring at the coordinator level.

**Where report aggregation actually happens**: The `ParallelOrchestrator` reads `merge_coordinator.merged_ids` and `merge_coordinator.failed_merges` to build the final status report. If any paraphrasing exists, it would be in `orchestrator.py`'s reporting section, not in `merge_coordinator.py`.

**Revised file references (if Phase 2 is warranted after investigating orchestrator):**
- `scripts/little_loops/parallel/merge_coordinator.py` — No changes needed (pure git ops)
- `scripts/little_loops/parallel/orchestrator.py` — Investigate `_generate_summary()` or similar reporting method for paraphrasing risk
- `scripts/little_loops/parallel/worker_pool.py` — Sub-agent output is captured here; check if result text is passed through or summarized

### Files to Modify (if Phase 2 needed, pending orchestrator investigation)
- `scripts/little_loops/parallel/orchestrator.py` — forwarding logic (if paraphrasing found in summary generation)
- `scripts/little_loops/parallel/worker_pool.py` — sub-agent report format

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
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Investigated merge_coordinator.py: no synthesis/paraphrasing found; MergeCoordinator is pure git orchestration. Investigation focus should shift to orchestrator.py reporting methods.

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-26
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: MEDIUM
- Complexity Added: MEDIUM
- Technical Debt Risk: MEDIUM
- Maintenance Overhead: MEDIUM

### Rationale
Investigation already found that MergeCoordinator does no synthesis/paraphrasing — it is pure git orchestration. The "Telephone Game Problem" premise partially collapsed. Remaining investigation into orchestrator.py reporting is speculative with no confirmed evidence of the problem occurring.
