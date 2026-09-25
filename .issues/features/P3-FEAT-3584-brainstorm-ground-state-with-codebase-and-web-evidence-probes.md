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

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Stale state names in this issue**: `brainstorm.yaml` (459 lines) has no `shortlist` or `tournament` state today. The live flow is `init → frame → pop_lens ⇄ diverge → dedup_novelty → saturation_gate → (pop_lens | cluster) → rank → converge → route_sink`. `ideas.jsonl` is appended per lens round inside `dedup_novelty`, so a `ground` pass can only see the complete set after the lens loop drains. Placement "between `dedup` and `shortlist`" is therefore only meaningful relative to FEAT-3582's restructure (blocked_by); until it lands, the natural seam is immediately before `cluster`.
- **Routing constraint**: three edges currently target `cluster` — `pop_lens.on_no`, `saturation_gate.on_no`, and `saturation_gate.on_error` (plus `dedup_novelty.on_no`). A gated `ground` state must intercept all of them, or ungrounded ideas reach `cluster`/`rank` via the unintercepted edge. `test_brainstorm.py::TestBrainstormShellStates` asserts routing of `pop_lens`, `saturation_gate`, `dedup_novelty`, and `cluster`/`rank` `on_error`; those contracts must keep passing or be updated deliberately.
- **Idea schema today is `{text, rationale}` only** (`diverge` prompt and `dedup_novelty` parser); no `IdeaRecord` class exists in `scripts/little_loops/` — the `Program Design` type is a JSONL row shape, not a Python dataclass. `dedup_novelty` writes rows verbatim (`json.dumps(idea)`), so added `evidence`/`grounded` keys survive downstream states that read `ideas.jsonl` (`cluster`, `rank`, `converge` all read it via prompt and would need to be told to exclude `grounded: false`).
- **Exit-code contract to inherit**: `dedup_novelty` documents (BUG-2468) that exit 2 = crash → `on_error: finalize_failed`, and a crash must never look like "nothing to do". A probe script must likewise separate "anchor not found" (a normal grounding result, exit 0 with `grounded: false`) from script failure (exit 2). LLM payloads reach Python only via a quoted heredoc file, never interpolated into source.
- **`ll-issues show <ID>`** exits 0 on found, 1 with `Error: Issue '<id>' not found.` on stdout when absent (`cli/issues/show.py:cmd_show`) — exit 1 is "unknown ID", so an unavailable/absent `ll-issues` binary (exit 127) or missing `.issues/` must be distinguished from exit 1 to keep the Issue-system decoupling AC honest.
- **`.loops/probes/` is not a matching precedent**: its contents are `.mjs` browser/DOM probes (`feat-3488-browser-probes.mjs`, etc.), not shell/Python existence probes. The Integration Map "Similar Patterns" entry should not be read as a template; the in-repo convention for non-LLM checks is an inline `action_type: shell` state with an `exit_code` evaluator (`dedup_novelty`, `saturation_gate`).
- **Loop-authoring constraints**: `test_required_states_exist` lists required states (adding `ground` is safe; renaming existing ones is not); `max_steps: 60` bounds the run; bash `${...}` inside FSM shell actions must be escaped `$${...}`; `${captured.run_dir.output}` uses in new states need the same `mr11-ok` handling or a `${context.run_dir}` path as `dedup_novelty` does; `ll-loop validate` enforces MR-1..MR-14, and `test_builtin_loops.py` (~line 20421 onward) carries per-loop interpolation-site allowlists that a new state referencing `${context.*}` may trip.
- **Open dependency on FEAT-3583**: the `ground` context key (`none|codebase|web`) is expected to be resolved from the mode profile; until that lands the key needs a standalone default (`none`, so existing behavior is unchanged) in `context:`.

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
- `/ll:refine-issue` - 2026-09-25T01:46:47 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:44 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
