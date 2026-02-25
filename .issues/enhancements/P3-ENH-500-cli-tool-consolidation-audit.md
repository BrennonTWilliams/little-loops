---
discovered_date: 2026-02-24
discovered_by: context-engineering-analysis
source: https://github.com/muratcankoylan/Agent-Skills-for-Context-Engineering
---

# ENH-500: CLI Tool Consolidation Audit

## Summary

Apply the "tool consolidation" heuristic to our CLI tools: if a human engineer cannot decide which tool to use for a given task, neither can an agent. With five similar-sounding sequential/parallel execution tools (ll-auto, ll-parallel, ll-sprint, ll-loop, ll-workflows), there is meaningful overlap risk. Audit for confusion, merge candidates, and clarify distinctions.

## Current Behavior

The CLI surface includes:
- `ll-auto` — Automated sequential issue processing
- `ll-parallel` — Parallel issue processing with git worktrees
- `ll-sprint` — Sprint-based issue processing
- `ll-loop` — FSM-based automation loop execution
- `ll-workflows` — Workflow sequence analyzer

A new user or a Claude session resuming from context must choose between five tools with partially overlapping descriptions. The `ll:help` output lists these but may not make distinctions clear enough.

Additionally, the documented principle "limit to 10-20 tools" (from the consolidation research) is worth auditing against our total CLI command count.

## Expected Behavior

Each CLI tool has a crisp, differentiated description that allows unambiguous tool selection. The test: given a user's goal, is there exactly one correct tool choice? If two tools are plausible, either the descriptions need sharpening or the tools need merging.

The audit produces one of:
- A set of description improvements
- A proposal to merge overlapping tools
- Confirmation that the current tool set is well-differentiated

## Motivation

Ambiguous tool selection wastes tokens (the agent tries the wrong tool first) and degrades automation reliability. This is particularly important for `ll-auto` vs `ll-sprint` — both process issues sequentially, but their scope and resumability differ. If Claude can't reliably pick between them, automation quality suffers.

## Proposed Solution

1. For each CLI tool, write the user goal it is uniquely suited for (one sentence)
2. Apply the consolidation test: are there overlapping use cases?
3. Sharpen `--help` text and `ll:help` descriptions to be mutually exclusive
4. If tools are genuinely redundant, propose merging (do not merge without a separate issue)
5. Check total tool count against the 10–20 tool recommendation

## Scope Boundaries

- **In scope**: Audit of tool descriptions and use-case differentiation; description improvements; consolidation proposals
- **Out of scope**: Actually merging tools (separate issue), adding new tools, changing tool behavior

## Implementation Steps

1. Run `ll-auto --help`, `ll-parallel --help`, `ll-sprint --help`, `ll-loop --help`, `ll-workflows --help`
2. Read `commands/help.md` and `docs/` for each tool's intended use case
3. For each tool, write the one-sentence unique use case
4. Identify any overlap and assess: description problem vs. genuine redundancy
5. Update `--help` text and `commands/help.md` accordingly
6. Document consolidation proposals as separate issues if merging is warranted

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/*.py` — `--help` text / argparse descriptions
- `commands/help.md` — tool summaries
- `docs/` — tool documentation where descriptions appear

### Tests
- Manual: ask Claude "which tool should I use to process 3 issues sequentially?" — verify unambiguous answer

## Impact

- **Priority**: P3 — Moderate; affects new user experience and automation reliability
- **Effort**: Low to Medium — Audit is low effort; description updates are low effort; merges (if any) are medium
- **Risk**: Low — Description-only changes initially
- **Breaking Change**: No

## Labels

`enhancement`, `cli`, `context-engineering`, `ux`, `tooling`

## Session Log
- `/ll:format-issue` - 2026-02-24 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cfefb72b-eeff-42e5-8aa5-7184aca87595.jsonl`

---

## Status

**Open** | Created: 2026-02-24 | Priority: P3
