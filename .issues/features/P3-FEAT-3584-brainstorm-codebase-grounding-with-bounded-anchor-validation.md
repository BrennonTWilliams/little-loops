---
id: FEAT-3584
type: FEAT
title: Brainstorm codebase grounding with bounded anchor validation
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

# FEAT-3584: Brainstorm codebase grounding with bounded anchor validation

## Summary

Add profile-gated **codebase anchor validation** before shortlisting. Existing touchpoints must exist; proposed new paths must not collide. This is an existence filter, not proof of semantic support or consistency with open issues. Web grounding is deferred and is not an implementation or closure requirement here.

## Current Behavior

The shipped loop does not verify anchors. The core engine from FEAT-3667/3582 preserves extra.touchpoints/creates and the optional top-level grounded field, but ships ground=none.

## Expected Behavior

- When ground=codebase, collapse routes to ground_codebase before shortlist_block. The single shell state calls the packaged engine, verifies all ideas, writes top-level grounded and extra.evidence, then continues to shortlist_block. No LLM call or separate gate state.
- Grounding discovers the repository once in a bounded engine helper using git rev-parse from the consuming project's working directory, not the installed package path or run_dir. Pass --project-dir explicitly; an optional --repo-root uses the same helper validation. Failed/non-Git discovery produces unknown evidence (repo_unavailable), succeeds without git probes, and leaves otherwise-valid ideas eligible; lexical/schema validation still rejects definitely invalid anchor data. Do not let a failing shell command substitution abort before recording this result. Repo-summary uses the same discovery rule and emits an unavailable marker when needed.
- Configuration is loaded from the explicit consuming project directory, including local overrides, independently of the discovered Git top-level. Resolve its configured issue store against that project and convert its exclusions to Git-root-relative pathspecs. Issue anchors match exact canonical IDs from one bounded all-status issue-store snapshot, obtained directly through the configured loader or `ll-issues list --status all --json --config PROJECT_DIR`. A missing ID is false only when that snapshot is complete and valid; absent store, config/tool/JSON failure or an incomplete snapshot is unknown. Do not infer missing from exit 1 or use type-tolerant show resolution as proof of exact typed identity. A nested project must not search its parent's or the package checkout's issue store.
- Git file anchors and configured exclusion directories are literal paths, not glob/pathspec expressions. Verify the exact normalized tracked filename; a successful wildcard match against a different file does not validate an anchor. Preserve legal glob characters in actual filenames and custom directory names. A tracked symlink's presence is tested without following its target, consistent with the existence-only contract.
- One shared invocation context carries root/config/deadline, tracked-path membership, issue IDs, completeness flags and the probe cache. File/create/issue checks use bounded local/index lookups rather than launching a CLI per anchor; symbol searches are deduplicated by literal value. Collected inventories are capped at 4 MiB each; overflow or incomplete collection leaves unresolved membership unknown, never false. Cheap lookups precede bounded symbol probes, which are dispatched fairly across ideas so a deadline does not consistently starve the final lens. Do not batch symbols in a way that loses overlapping literal matches. No fresh-context construction occurs per idea.
- Anchor strings have explicit prefixes: file:<relative path>, symbol:<literal symbol>, issue:<validated ID>. Diverge's profile block documents this syntax. File anchors must be git-tracked and present; normalize repo-relative paths and reject absolute paths/NUL/traversal escapes just as for creates. This existence-only probe does not read file contents or certify symlink targets; an in-repo tracked symlink is reported as a symlink rather than semantic support. Symbol checks use git grep -q -F -e <symbol> -- with explicit pathspec exclusions for the configured issues.base_dir, .ll/ and .loops/ (literal occurrence in the remaining tracked files, not definition proof). A symbol appearing only in issue/runtime prose is not found; explicit issue: and file: anchors remain available for those artifacts. Issue checks use the shared exact-ID snapshot, distinguishing complete verified absence from unavailable/incomplete evidence.
- extra.creates contains repo-relative new paths. Reject absolute/traversal/symlink escapes; reject existing destinations (including untracked files and dangling symlinks). The in-root parent directory must exist. A new file is not rejected merely because it is new.
- A verified missing/invalid anchor or create-path collision gives false; all available required probes passing gives true; no touchpoints or an unavailable optional issue store/tool gives unknown. False dominates unknown when both occur. A failed git command/tool timeout is unknown with a recorded reason, not a fictitious missing anchor; unexpected engine/I/O exceptions fail the state.
- Zero-touchpoint ideas remain unknown (no_anchors) unless creates has a definite violation, which makes them false. Unknown ideas remain eligible and are flagged. False ideas are excluded before shortlisting and the generation floor; no reserve promotion occurs in codebase v1.
- A bounded tracked-file summary (at most 200 lines and 16 KB, with truncation indicated) reaches the existing diverge prompt-block when codebase grounding is enabled. This informs generation without adding a separate context-gathering state; do not claim full semantic repository analysis.
- Each repo-summary invocation has a whole-operation deadline of 5 s, including discovery and inventory, and emits an explicit unavailable/deadline marker rather than aborting generation on expected probe failures. Bound inventory output while collecting it, rather than buffering an unrestricted listing before truncation. The maximum nine diverge-block invocations each incur this cost; include it in the pre-tournament elapsed bound separately from the later ground-codebase deadline. No cross-run inventory cache is implied.
- LLM strings are subprocess argv values, never shell code. Per idea, touchpoints and creates are lists of at most eight nonempty strings each; each value is <=512 UTF-8 bytes with no NUL/newline. Bad type, oversized list or invalid string is false (invalid_anchor_data), not silently truncated into passing evidence. Diverge's extra-field instructions state these limits; the core extra-object cap still applies.
- Each external probe/discovery has a timeout <=5 s, and ground-codebase has a 60 s whole-operation monotonic deadline including discovery. Cache repeated probes within that invocation; retries recheck repository state rather than trusting an unspecified stale cross-run cache. At the deadline stop dispatching; unresolved valid probes become unknown/probe_deadline, while previously established false remains false. Non-Git discovery makes repository-dependent checks unknown, not missing. Persist evidence atomically after the deadline; give the shell state timeout >=75 s for bounded publication overhead and include its actual configured timeout/retries in the feature budget. Unexpected engine/I/O errors remain failures. The reference run records elapsed time, deadline exhaustion and the discovered root.

## Use Case

A user asks for a functional design in a consuming repository. The generator sees a bounded file inventory and an idea cannot win by citing a nonexistent anchor. New components remain eligible.

## Motivation

Deterministic existence checks catch hallucinated references cheaply while keeping the core independent of the issue system.

## Proposed Solution

Add ground-codebase/probe-anchor engine commands, typed probe results, and a bounded repo-summary helper used by prompt-block. Rewrite ideas.jsonl atomically, preserving IDs, lens identity, bodies and cells. Widen BUILT_CAPABILITIES and flip functional.json ground to codebase in the same change; map collapse's ground_codebase token explicitly. Route deterministic engine crashes to finalize_failed.

## Program Design

### Types

- AnchorResult: {status: true | false | "unknown", reason: str, anchor: str}.
- GroundContext (proposed): consuming project/config root, optional repository root, monotonic deadline, bounded tracked/issue indexes with completeness flags, and invocation-local probe cache; injected clock/probe runner support deterministic fixtures.

- IdeaRecord.extra gains touchpoints: list[str], creates: list[str], evidence: {anchors: list[AnchorResult], create_checks: list[AnchorResult]}; top-level grounded is the FEAT-3582 tri-state field.

### Signatures

- build_ground_context(project_dir: Path, repo_root: Path | None, timeout_s: float) -> GroundContext — one bounded discovery/indexing context per command invocation.
- probe_anchor(anchor: str, context: GroundContext) -> AnchorResult — existence/tool-availability outcome, not a bool that loses unknown.
- ground_idea(idea: IdeaRecord, context: GroundContext) -> IdeaRecord — false-dominant aggregation; preserve canonical idea data and share the operation deadline/cache.
- repo_summary(context: GroundContext, max_lines: int = 200, max_bytes: int = 16384) -> str — bounded inventory with truncation marker; summary contexts use the 5 s bound.

CLI: ground-codebase --run-dir DIR --project-dir DIR [--repo-root ROOT] reads ideas/profile and atomically updates ideas/evidence; exit 0 for completed probing (including false/unknown/deadline outcomes), exit 2 for an engine failure. probe-anchor --project-dir DIR [--repo-root ROOT] --anchor VALUE emits a typed result using the same context/discovery rules. The inventory path also receives --project-dir through prompt-block when grounding is enabled. YAML uses the quoted LL_PYTHON interpreter and :shell argument quoting.

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
- scripts/little_loops/fsm/fence.py — register the repository inventory in the existing diverge block's untrusted-output fence.
- scripts/little_loops/loops/brainstorm-profiles/functional.json — ground=codebase; touchpoint syntax in prompt data.
- scripts/tests/test_brainstorm_engine.py — direct-import git fixture tests; no inline YAML-extracted Python.
- scripts/tests/test_brainstorm.py — route, generation-floor and +1 step/budget checks.
- scripts/tests/test_builtin_loops.py and scripts/tests/data/loop_interpolation_baseline.json — validator/warning updates as required.

### Dependent Files
- ll-issues show; consuming git repository; FEAT-3585 receives only the shortlist's surviving IDs.
- FEAT-3667 supplies the engine/profile/CLI contract; FEAT-3582 supplies the collapse/shortlist wiring; FEAT-3583 supplies the functional preset/overrides. Their implementation is required before this feature can work; references to engine/profile/test files above describe planned prerequisite artifacts, not existing code.

### Conventions in Force
- `scripts/little_loops/cli/issues/__init__.py::main_issues` selects configuration from `--config` or cwd; `scripts/little_loops/issue_parser.py::resolve_issue_path` permits type-tolerant resolution. Grounding needs the consuming project's configuration and exact typed-anchor identity, rather than relying on those CLI defaults.
- `scripts/little_loops/fsm/evaluators.py::evaluate` treats nonzero action exits as errors before classification. Grounding's shell action must explicitly route errors/timeouts to finalize_failed; a trailing token or classify `_` default alone is not the error route.

### CLI Contract Extension

- This child owns the additive, capability-gated `prompt-block --project-dir`/repository-root argument and bounded inventory output. Update the CLI contract/conformance tests when it lands; existing `ground=none` calls and output remain compatible. FEAT-3667's freeze rule permits this named extension.

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

- Direct-import tests cover tracked-present/missing/untracked file anchors, lexical file-path rejection and tracked symlink reporting, literal symbol occurrence/missing symbol, symbol found only in excluded/custom issue directories, found/missing/unavailable issue IDs, create collisions/missing parents, zero anchors, non-Git discovery, invalid/over-limit anchor lists and false-dominates-unknown aggregation. Fake-clock deadline tests stop dispatches, preserve established false and mark unresolved probes unknown; pytest never sleeps.
- Absolute paths and traversal are rejected for file/create paths; create-path symlink escapes and dangling-symlink collisions are rejected; unusual symbol/path characters are argv data and never shell execution.
- Nested-project fixtures distinguish project/config root from Git root, honor custom/local issue-directory settings, reject a typed anchor resolving to a different issue type, and treat malformed config/tool output as unknown rather than missing. Inventory deadline/output-cap fixtures cover each repeated diverge-block invocation without sleeping.
- Literal-path fixtures distinguish a nonexistent `*.py` anchor from a present ordinary Python file, accept a genuinely tracked filename containing glob characters, and keep custom issue-directory exclusions literal. Track symlink presence independently of target existence.
- Dispatch-count fixtures cover shared file/issue indexes, repeated and overlapping symbols, capped/incomplete inventories, and fair deadline handling across ideas. Grounding must not start a new issue CLI process for every one of the possible 720 issue anchors. One complete all-status snapshot recognizes done/cancelled issue IDs as existing.
- Git/probe failure and tool absence remain distinguishable from verified absence; evidence/reasons and top-level grounded are persisted atomically.
- Bounded repo inventory reaches diverge before generation without another parent state or LLM call.
- False ideas never reach shortlist/judging; floor failure after grounding happens before any judge or sink. Unknown ideas stay eligible with report flags.
- Lands with BUILT_CAPABILITIES enablement, functional preset flip, explicit token wiring and its derived +1 state/time cost; ENH-3734 owns cumulative combinations.
- Whichever optional feature lands first replaces the literal max_steps==60 assertion with one derived from built capability paths. This child does not wait for ENH-3734 to repair that assertion.
- One consuming-project functional reference run with import origin and probe time is recorded here; FEAT-3596 is not its owner.
- Web probes, cited sources and reserve promotion are deferred; ground=web continues to be rejected by resolve-profile.

## Deferred Follow-up

Web grounding would require a separate issue and measurements for source retrieval, network/quote verification, tri-state errors and same-cell reserve promotion after shortlist. No such implementation or evidence is needed to close this issue or EPIC-3687's v1 scope.

## Review History

_2026-10-05 executor/configuration review and `/ll:advise` with Opus (confidence 0.70):_ clarified consuming-project configuration and exact/literal anchor identity, bounded shared indexes and repeated repo-summary work, and assigned the additive CLI/fence changes. Renamed the issue to match its codebase-only v1 scope; web remains deferred. Actual engine/profile paths remain unbuilt prerequisites. Historical web directives below are superseded by the current contract above. No new grounding throughput measurements were made.

_2026-10-05 follow-up, `/ll:advise` with Opus (confidence 0.72):_ accepted graceful non-Git discovery, lexical file-anchor validation, runtime/issue-prose exclusions for symbol search, bounded anchor lists and a whole-operation deadline. Kept existence-only scope: no file-content or symlink-target certification and no new semantic analyzer. Caps/deadline are design bounds, not new measurements.

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
- `/ll:refine-issue` - 2026-10-05T17:31:36-06:00 - `EPIC-3687 pre-implementation review`
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:33 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
- `/ll:reconcile-issue` - 2026-09-25T17:15:17 - `f2fe6fc2-4dc3-4f38-a10c-f2bd8be05a0c.jsonl`
- `/ll:wire-issue` - 2026-09-25T02:07:45 - `6e813375-6da8-496a-a222-6bd92b308c4c.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:46:47 - `2ac59930-bb65-4013-a3d3-8f842b856fd9.jsonl`
- `/ll:format-issue` - 2026-09-25T01:01:32 - `825370f4-2bf5-4bb8-a770-49c1a90d8b61.jsonl`
- `/ll:capture-issue` - 2026-09-25T00:33:44 - `ba660a81-2414-4092-808d-95f51543dbb1.jsonl`
