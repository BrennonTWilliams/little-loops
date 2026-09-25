---
id: FEAT-3584
type: FEAT
title: Brainstorm ground state with codebase and web evidence probes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
---

# FEAT-3584: Brainstorm ground state with codebase and web evidence probes

## Summary

Add a gated `ground` state to the brainstorm engine that attaches evidence to ideas
before shortlisting, with **non-LLM probes** to reject unsupported ideas. Sources:
`none` (artifact/visual default), `codebase` (functional default), `web` (business
default).

## Current Behavior

Brainstorm performs no evidence check: an idea that cites a nonexistent file, symbol, or issue ID, or one that conflicts with an open issue, is ranked the same as a well-supported one.

## Expected Behavior

- `codebase`: each idea must cite concrete anchors (file paths, symbols, issue IDs);
  a script verifies they exist (git-tracked files, `git grep` for symbols,
  `ll-issues show` for IDs) and flags conflicts with open issues.
- `web`: research competitors, prior art, and demand signals; each idea carries
  cited sources and an explicit assumption list.
- Ideas failing grounding are dropped or marked `ungrounded` and excluded from the
  tournament per profile policy.
- Skipped entirely when `ground=none`.

## Use Case

**Who**: A little-loops user brainstorming a functional design (feature, architecture, API) in this repo, or a business opportunity.

**Context**: LLM-generated ideas often cite files, symbols, or issues that do not exist, or duplicate work already tracked.

**Goal**: Have unsupported ideas rejected by deterministic probes before they reach the tournament.

**Outcome**: `ideas.jsonl` records `evidence` and `grounded` per idea; ungrounded ideas are dropped or excluded per profile policy.

## Motivation

EPIC-3581 notes that functional designs need codebase grounding and business opportunities need market grounding. Non-LLM probes (git-tracked files, `git grep`, `ll-issues show`) give a cheap, deterministic filter that stops hallucinated anchors from winning a tournament.

## Proposed Solution

Add a gated `ground` state to `scripts/little_loops/loops/brainstorm.yaml`, between `dedup` and `shortlist`, skipped when `ground=none`:

- `codebase`: each idea must cite anchors (file paths, symbols, issue IDs); a script verifies files with `git ls-files`, symbols with `git grep`, issue IDs with `ll-issues show`, and flags conflicts with open issues.
- `web`: an LLM step researches competitors, prior art, and demand signals; each idea carries cited sources and an explicit assumption list.
- Failing ideas are dropped or marked `ungrounded` and excluded from the tournament per profile policy.

Issue-ID probing activates only when `.issues/` / `ll-issues` is available so the core stays decoupled from the Issue system.

## Program Design

### Types

- `Evidence`: `{anchors: [str], sources: [str], assumptions: [str]}`
- `IdeaRecord` gains `evidence: Evidence` and `grounded: bool`

### Signatures

- `probe_anchor(anchor: str) -> bool` — file/symbol/issue-ID existence check, no LLM
- `ground_idea(idea: IdeaRecord, source: str) -> IdeaRecord` — attaches evidence and sets `grounded`

### Call Path

`diverge` -> `ground` -> `probe_anchor` -> `ll-issues show`

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/brainstorm.yaml` — add gated `ground` state and probe script; extend idea schema with `evidence`/`grounded`

### Dependent Files (Callers/Importers)
- `ll-loop run brainstorm` callers and the sink adapters (`route_sink`, `sink_file`, `sink_issue`, `sink_decision`) inside the loop
- `scripts/little_loops/loops/lib/common.yaml` — imported fragments (`parse_tagged_json`, `queue_pop`, `retry_counter`)
- `ll-issues show` CLI (`scripts/little_loops/cli/issues/`) — issue-ID probe

### Similar Patterns
- `.loops/probes/` — existing non-LLM probe scripts for deterministic verification

### Tests
- `scripts/tests/test_brainstorm.py` — brainstorm loop structure/behavior tests
- `scripts/tests/test_builtin_loops.py` — built-in loop validation (`ll-loop validate`)
- New tests: probe pass/fail for missing file, missing symbol, unknown issue ID, using fixture ideas

### Documentation
- `scripts/little_loops/loops/README.md`, `docs/guides/LOOPS_GUIDE.md`, `docs/guides/LOOPS_REFERENCE.md` — brainstorm loop descriptions

### Configuration
- Context key: `ground` (none|codebase|web), normally resolved from the profile (FEAT-3583)

## Implementation Steps

1. Add the `ground` state with `none|codebase|web` routing driven by the resolved profile (FEAT-3583).
2. Implement the deterministic `probe_anchor` script (git-tracked file, `git grep` symbol, guarded `ll-issues show`).
3. Add the `web` research step with cited sources and assumption list, and the drop/mark-`ungrounded` policy.
4. Record `evidence` and `grounded` per idea in `ideas.jsonl`; exclude ungrounded ideas from `shortlist`/`tournament`.
5. Add probe pass/fail tests with fixture ideas and run `ll-loop validate brainstorm`.

## Impact

- **Priority**: P3 - improves idea quality for functional/business modes but the core works without it
- **Effort**: Medium - one gated state plus a small probe script; reuses existing git and `ll-issues` CLIs
- **Risk**: Low - skipped when `ground=none`; probes are read-only
- **Breaking Change**: No

## Acceptance Criteria

- Codebase probes are deterministic and cover: missing file, missing symbol,
  unknown issue ID.
- Grounding results recorded per idea in `ideas.jsonl` (`evidence`, `grounded`).
- Core loop stays decoupled from the Issue system: issue-ID probing is only active
  when `.issues/` / `ll-issues` is available.
- Tests cover probe pass/fail with fixture ideas.

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:44 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
