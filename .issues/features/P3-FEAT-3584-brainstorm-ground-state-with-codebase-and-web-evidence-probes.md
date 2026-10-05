---
id: FEAT-3584
type: FEAT
title: Brainstorm ground state with codebase and web evidence probes
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T00:33:14Z'
parent: EPIC-3687
labels:
- loops
- brainstorm
- captured
blocked_by:
- FEAT-3582
- FEAT-3583
- FEAT-3667
reconcile_attempted: true
---

# FEAT-3584: Brainstorm ground state with codebase and web evidence probes

## Summary

Add profile-gated **codebase anchor validation** before shortlisting. Existing touchpoints must exist; proposed new paths must not collide. This is an existence filter, not proof of semantic support or consistency with open issues. Web grounding is deferred and is not an implementation or closure requirement here.

## Current Behavior

The shipped loop does not verify anchors. The core engine from FEAT-3667/3582 preserves extra.touchpoints/creates and the optional top-level grounded field, but ships ground=none.

## Expected Behavior

- When ground=codebase, collapse routes to ground_codebase before shortlist_block. The single shell state calls the packaged engine, verifies all ideas, writes top-level grounded and extra.evidence, then continues to shortlist_block. No LLM call or separate gate state.
- Grounding resolves the repository from the consuming project's working directory with git rev-parse, not from the installed package path or run_dir. Supply --repo-root explicitly to the engine state and use that cwd for subprocesses.
- Anchor strings have explicit prefixes: file:<relative path>, symbol:<literal symbol>, issue:<validated ID>. Diverge's profile block documents this syntax. File anchors must be git-tracked and present; symbol checks use git grep -F -e <symbol> -- (literal occurrence, not definition proof); issue checks use ll-issues show only when the issue store/tool exists.
- extra.creates contains repo-relative new paths. Reject absolute/traversal/symlink escapes; reject existing destinations (including untracked files and dangling symlinks). The in-root parent directory must exist. A new file is not rejected merely because it is new.
- A verified missing/invalid anchor or create-path collision gives false; all available required probes passing gives true; no touchpoints or an unavailable optional issue store/tool gives unknown. False dominates unknown when both occur. A failed git command/tool timeout is unknown with a recorded reason, not a fictitious missing anchor; unexpected engine/I/O exceptions fail the state.
- Zero-touchpoint ideas remain unknown (no_anchors) unless creates has a definite violation, which makes them false. Unknown ideas remain eligible and are flagged. False ideas are excluded before shortlisting and the generation floor; no reserve promotion occurs in codebase v1.
- A bounded tracked-file summary (at most 200 lines and 16 KB, with truncation indicated) reaches the existing diverge prompt-block when codebase grounding is enabled. This informs generation without adding a separate context-gathering state; do not claim full semantic repository analysis.
- LLM strings are subprocess argv values, never shell code. Probes have finite timeouts and memoize repeated anchors within the run; the reference run records the complete state's elapsed time.

## Use Case

A user asks for a functional design in a consuming repository. The generator sees a bounded file inventory and an idea cannot win by citing a nonexistent anchor. New components remain eligible.

## Motivation

Deterministic existence checks catch hallucinated references cheaply while keeping the core independent of the issue system.

## Proposed Solution

Add ground-codebase/probe-anchor engine commands, typed probe results, and a bounded repo-summary helper used by prompt-block. Rewrite ideas.jsonl atomically, preserving IDs, lens identity, bodies and cells. Widen BUILT_CAPABILITIES and flip functional.json ground to codebase in the same change; map collapse's ground_codebase token explicitly. Route deterministic engine crashes to finalize_failed.

## Program Design

### Types

- AnchorResult: {status: true | false | "unknown", reason: str, anchor: str}.
- IdeaRecord.extra gains touchpoints: list[str], creates: list[str], evidence: {anchors: list[AnchorResult], create_checks: list[AnchorResult]}; top-level grounded is the FEAT-3582 tri-state field.

### Signatures

- probe_anchor(anchor: str, repo_root: Path) -> AnchorResult — existence/tool-availability outcome, not a bool that loses unknown.
- ground_idea(idea: IdeaRecord, repo_root: Path) -> IdeaRecord — false-dominant aggregation; preserve canonical idea data.
- repo_summary(repo_root: Path, max_lines: int = 200, max_bytes: int = 16384) -> str — bounded inventory with truncation marker.

CLI: ground-codebase --run-dir DIR --repo-root ROOT reads ideas/profile and atomically updates ideas/evidence; exit 0 for completed probing (including false/unknown ideas), exit 2 for an engine failure. probe-anchor --repo-root ROOT --anchor VALUE emits a typed result with the same distinction. YAML uses $${LL_PYTHON:-python3} -m little_loops.brainstorm_engine.

### Call Path

FSMExecutor.run -> collapse -> ground_codebase -> shortlist_block -> shortlist -> shortlist_apply -> check_floors (generation) -> check_floors_pre_tournament -> tournament

## Integration Map

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml | ground=none flow | Preserved with zero additional visits |
| brainstorm_engine.py | Unverified ideas eligible | Changed only for enabled grounding: verified false ideas excluded, unknown eligible |
| functional.json | ground=none | Changed to codebase when implementation lands |

### Files to Modify
- scripts/little_loops/brainstorm_engine.py — probes, repo summary, aggregate grounded status, prompt-block/report extensions, capability allowlist.
- scripts/little_loops/loops/brainstorm.yaml — ground_codebase state and consuming-root argument.
- scripts/little_loops/loops/brainstorm-profiles/functional.json — ground=codebase; touchpoint syntax in prompt data.
- scripts/tests/test_brainstorm_engine.py — direct-import git fixture tests; no inline YAML-extracted Python.
- scripts/tests/test_brainstorm.py — route, generation-floor and +1 step/budget checks.
- scripts/tests/test_builtin_loops.py and scripts/tests/data/loop_interpolation_baseline.json — validator/warning updates as required.

### Dependent Files
- ll-issues show; consuming git repository; FEAT-3585 receives only the shortlist's surviving IDs.

### Documentation
- scripts/little_loops/loops/README.md, docs/guides/LOOPS_GUIDE.md, docs/guides/LOOPS_REFERENCE.md — anchor syntax and existence-only interpretation.

## Implementation Steps

1. Recheck the landed engine schema and implement typed probes/aggregation with temporary git-repo fixtures.
2. Feed the bounded inventory through diverge's existing engine block and add ground_codebase between collapse and shortlist_block.
3. Enable the capability/preset together, extend token wiring and derive its +1 step/time increment.
4. Record this issue's functional reference run and verify loop validation, package portability and the local suite.

## Impact

- **Priority**: P3 — improves functional mode while the core works without it.
- **Effort**: Medium — one state and deterministic engine probes.
- **Risk**: Low — read-only, bounded probes; optional tool absence remains unknown.
- **Breaking Change**: No.

## Acceptance Criteria

- Direct-import tests cover tracked-present/missing/untracked file anchors, literal symbol occurrence/missing symbol, found/missing/unavailable issue IDs, create collisions/missing parents, zero anchors, and false-dominates-unknown aggregation.
- Absolute paths, traversal, symlink escapes and dangling-symlink collisions are rejected; unusual symbol/path characters are argv data and never shell execution.
- Git/probe failure and tool absence remain distinguishable from verified absence; evidence/reasons and top-level grounded are persisted atomically.
- Bounded repo inventory reaches diverge before generation without another parent state or LLM call.
- False ideas never reach shortlist/judging; floor failure after grounding happens before any judge or sink. Unknown ideas stay eligible with report flags.
- Lands with BUILT_CAPABILITIES enablement, functional preset flip, explicit token wiring and its derived +1 state/time cost; ENH-3734 owns cumulative combinations.
- One consuming-project functional reference run with import origin and probe time is recorded here; FEAT-3596 is not its owner.
- Web probes, cited sources and reserve promotion are deferred; ground=web continues to be rejected by resolve-profile.

## Deferred Follow-up

Web grounding would require a separate issue and measurements for source retrieval, network/quote verification, tri-state errors and same-cell reserve promotion after shortlist. No such implementation or evidence is needed to close this issue or EPIC-3687's v1 scope.

## Review History

Historical rationale only; the reconciled directive sections above define current scope (2026-10-05).

_Added 2026-09-30 (EPIC-3581 fifth review, `/ll:advise` with Opus):_ this issue moved to **EPIC-3687** (optional capabilities) so it no longer gates EPIC-3581 or FEAT-3596. Re-run `/ll:reconcile-issue` and `/ll:confidence-check` after FEAT-3667 lands (scores are missing or stale). Its own enablement change (widen `BUILT_CAPABILITIES`, flip the preset knob, wiring test, `max_steps`) and its own reference run stay in scope.

_Added 2026-09-29 (EPIC-3581 pre-implementation review, `/ll:advise` with Opus):_

- **Stale directives are superseded, not deleted, until `/ll:reconcile-issue` runs after FEAT-3667 lands** (line anchors shift): where § Similar Patterns, § Wiring Additions → Tests, § Implementation Steps 2 and the Codebase Research Findings describe inline `_bash`-extracted probe scripts, an inline `ground` state, or "adds 1 fixed step", read them as: probes are FEAT-3667 engine commands tested by direct import; `ground_codebase` and `ground_web` are the only new parent steps (2 + 1 LLM search), and the profile gate is routed by the **`collapse`** engine command's stdout token `ground_codebase` \| `shortlist` (no `ground_gate` state). _Corrected 2026-09-30 (fourth review): this previously said `check_floors`, which cannot gate a state that runs before `shortlist` and before `check_floors` (generation)._
- `grounded` is a top-level optional field (see Types); `evidence` stays in `extra`.

_Added 2026-09-29 (EPIC-3581 second review):_

- Probes (`probe_anchor`, `probe_source`) and the `finalists.json` rewrite are `little_loops.brainstorm_engine` commands (FEAT-3582 Review Decision 23), not inline YAML scripts; tests import them directly. The `web` research prompt stays in the YAML. The "Similar Patterns"/"Wiring" notes about inline `_bash`-extracted probe scripts describe the superseded approach.
- Floor enforcement moved from `validate_portfolio` to `check_floors --stage pre_tournament` (FEAT-3582 Review Decision 25); floors count `grounded != false` ideas.

_Added 2026-09-28 (EPIC-3581 sub-issue review):_

- `touchpoints` vs `creates` split so functional ideas proposing new files aren't marked ungrounded; zero-touchpoint ideas are `unknown`.
- Bounded repo summary fed to `diverge` in codebase mode (ideas were previously generated with no repo context).
- Web probe hardening: scheme allowlist, private-range block, timeout/size caps, 401/403/429 → `unknown`, quote normalization.
- No backfill back-edge: `shortlist` keeps a top-2 reserve per cell when `ground=web`.
- Two states (`ground_codebase`, `ground_web`) because the insertion points differ.

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:33 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:17 - `f2fe6fc2-4dc3-4f38-a10c-f2bd8be05a0c.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:45 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:47 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:44 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
