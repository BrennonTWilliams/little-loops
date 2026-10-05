---
id: FEAT-3596
type: FEAT
title: Brainstorm engine integration, reference runs, and evaluation
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T17:05:42Z'
parent: EPIC-3581
labels:
- loops
- brainstorm
blocked_by:
- FEAT-3582
- FEAT-3583
- FEAT-3667
- FEAT-3686
relates_to:
- FEAT-2248
- FEAT-3584
- FEAT-3585
- FEAT-3586
---

# FEAT-3596: Brainstorm engine integration, reference runs, and evaluation

## Summary

Verify and close EPIC-3581's **core engine**: all four text-judged modes, automatic classification, built-knob override wiring, failure routing, sink compatibility, core step/time budgets and comparable old/new evidence. Optional-capability combinations, rendered galleries and all-features budget verification belong to ENH-3734 under EPIC-3687; they do not gate this issue.

## Current Behavior

The core implementation issues own their own contracts and merge checks. This issue supplies the final mode/classifier calibration and integration evidence, without waiting for grounding, materialize or pre-mortem.

## Baseline and Evidence

The existing local-only postmortems/brainstorm-baseline/BASELINE.md and fresh-20260929/ preserve old-loop runs from commit 2fe16824a with claude-sonnet-5-5. FEAT-3686 is done/GO and owns postmortems/brainstorm-spike/tags.jsonl and RESULTS.md. Do not recapture or relabel the old baseline as new evidence. If recovery is needed, extract the old YAML plus lib/common.yaml from that commit, and force the checkout/package import origin explicitly; a worktree alone does not override a local-editable install.

The fixed briefs (same text for old/new):
1. "Suggest names and one-line taglines for an open-source CLI that watches a repository's issue backlog and drafts implementation plans."
2. "Design how little-loops should let a user pause a running FSM loop, edit its context, and resume it without losing state."

| Old-loop brief | Kept/generated ideas | LLM calls (including finalize summary) | Input context incl. cache | Output tokens | Total gate tokens | Runtime |
|---|---|---|---|---|---|---|
| Artifact | 42/45 | 14 | 879,243 | 23,502 | 902,745 | 336 s |
| Functional | 45/45 | 14 | 888,628 | 26,829 | 915,457 | 354 s |

These are arithmetic reconciliations of the preserved usage columns, not new measurements. The authoritative formula/ceilings are EPIC-3581 § Comparable token gate; input context alone is informational.

Spike evidence under the original grids: six occupied cells on each brief, five / approximately nineteen retained redundant ideas. Functional approach agreement was 0.72, below 0.75; dedup labels were produced by Claude rather than humans. These are provisional reference values with limitations, not universal quality thresholds. The lean-call spike latency (judge approximately 4.6–6.0 s) is a lower bound; measure real executor sessions for budgets.

## Expected Behavior

- Four explicitly requested mode=auto reference runs (the shipped default is still artifact), one per mode, record the chosen mode/confidence/fallback, expected layout, idea/finalist counts, tie/abstention rates, actual calls/tokens/runtime and import origin. Explicitly set ground=none, materialize=none and premortem=false for these core-only runs if optional children have already landed and changed preset defaults. Visual mode is text judged here; functional has no codebase filter; winner_risks layout omits unavailable annotations visibly.
- One explicit-mode run with a **built numeric override**, e.g. mode=business ideas_per_round=3, proves override precedence; malformed/unbuilt explicit options fail before any LLM dispatch. Classification host errors/timeouts fall back visibly to artifact.
- Deterministic MockActionRunner fixtures exercise only built states, including bounded/invalid preflight, zero ideas, insufficient cells/finalists, child timeout/error salvage, write-once round/probe replay, changed judging inputs with unchanged IDs, init interruption/re-entry, abstention thresholds, and all sink branches. No live LLM/browser is required in pytest.
- Sinks see only a validated eligible portfolio and legacy winners.md text/rationale/role keys. sink_file receives a nonempty report; issue/decision sinks are stubbed or isolated to temporary stores for verification (reference runs use sink=none).
- Enumerate actual core success/failure/salvage paths with at most nine lenses. Assert exact visits against shipped max_steps and time-guard constants, including classifier, report, sinks/finalization, judge timeouts and bounded rate-limit handling. Do not raise budget for unbuilt capabilities.
- Comparable evaluation tags **both old and new idea sets** blindly with the same final grid definitions, duplicate criterion, model/version and scoring procedure. Historical tags can be reused only when definitions/procedure match. Changed FEAT-3583 axes require re-tagging both sets; preserve original results separately. The new generator's own tags are not an evaluation baseline. Preserve evaluator inputs/outputs and distinguish estimated duplicate labels from human judgments.
- Re-run the two-brief blind human A/B for the final four-mode core configuration, randomized order and neutral title/body formatting. A human records win/tie/loss; the implementing agent cannot fill in the verdict or replace it with LLM judgment. Pass = new winner wins or ties on both. If no human result exists, preserve concrete comparison artifacts and leave this criterion pending.
- Core gates: occupied cells >= old and retained duplicates <= old under the comparable evaluation; actual LLM calls <=30 per successful default run, including classifier/finalize and retries; total context tokens <=1.5 times the corresponding old brief. Use the same model/host/settings and EPIC-3581 § Comparable token gate, including its exact denominators and integer comparison; do not maintain another formula here. Missing usage is unverified, not zero. A changed model/settings makes cost evidence incomparable until a matching baseline exists.
- Flip the shipped default to auto only as the final integration change: FEAT-3583's tuning gate and all core gates must pass, and each of the four live auto runs must select the expected known mode with confidence >=0.6 and no fallback. A miss leaves the default artifact and this acceptance criterion pending; preserve the miss rather than cherry-picking a passing rerun. Fix the demonstrated defect and repeat the same fixed brief(s), retaining earlier outcomes. After the flip, a deterministic fixture proves an omitted mode takes the same classifier path as explicit auto. This reuses the planned runs, without an added calibration corpus.
- Record blind A/B as a two-brief smoke check for regressions, not proof of improvement or significance. Cost/metric failure blocks closure until resolved; a documented explanation alone does not turn a failed gate into a pass.

## Motivation

This closes the core with evidence from real runs and meaningful failure fixtures. It preserves the optional/core split and avoids grading new ideas using their own generated grid labels or silently changed axes.

## Proposed Solution

Reuse FEAT-3582's pre-merge core evidence and FEAT-3686 baseline artifacts; add the final classifier/mode/override runs and a single consistent comparison record under postmortems/. Engine/YAML mismatches demonstrated by fixtures are corrected here. Optional features get their own runs and ENH-3734 gets their interactions.

## Program Design

### Types

- FailureFixture: {name: str, stub_outputs: dict[str,str], expected_terminal: str, sinks_fired: bool}.
- ComparisonRow: {brief: str, loop: str, preset_version: str, duplicates_retained: int, occupied_cells: int, llm_calls: int, input_tokens: int, cache_read_tokens: int, cache_creation_tokens: int, output_tokens: int, runtime_s: float, tie_rate: float | null, abstention_rate: float | null}.

### Signatures

- run_failure_fixture(fixture: FailureFixture, tmp_path: Path) -> str — test helper using FSMExecutor/MockActionRunner.
- worst_case_steps(state_visits: list[str]) -> int — count actual executed paths; no unbuilt optional increments.

### Call Path

FSMExecutor.run -> init -> classify_mode -> resolve_profile -> frame -> diverge/ingest -> dedup -> shortlist -> check_floors_pre_tournament -> tournament/salvage_tournament -> portfolio -> render_report -> validate_portfolio -> route_sink -> finalize_done

## Integration Map

### Behavior Parity

| Artifact | Behavior | Disposition |
|---|---|---|
| brainstorm.yaml / brainstorm_engine.py | Core routing, portfolio, sinks | Preserved; correct demonstrated wiring/budget defects only |
| brainstorm.yaml | Core max_steps/timeout | Verify derived bounds; no speculative all-features increase |
| brainstorm.yaml | Artifact default after FEAT-3583 | Flip to auto only after the four explicit-auto live runs and core gates pass |

### Files to Modify
- scripts/tests/test_brainstorm.py — core executor fixtures, sinks and derived budgets.
- scripts/tests/test_brainstorm_engine.py — any missing combined artifact/rate invariant fixtures.
- scripts/little_loops/loops/brainstorm.yaml / scripts/little_loops/brainstorm_engine.py — demonstrated core budget/guard corrections and the gated artifact -> auto default switch; no optional state changes.

### Dependent Files
- Final preset definitions and classifier from FEAT-3583; FEAT-3667 module; completed FEAT-3686 baseline.
- ENH-3734 reads these core records for later optional integration, but does not block this issue.

### Documentation
- scripts/little_loops/loops/README.md — core modes, the measured default switch, available capabilities and measured cost notes if needed.

## Implementation Steps

1. Verify baseline availability, package import origin and final preset definitions; preserve baseline provenance.
2. Add deterministic core/classifier/failure/sink fixtures and enumerate executed core budgets.
3. Record four auto-mode runs plus explicit built-knob override; compare both pinned briefs with matched model/settings and blind tagging.
4. Prepare neutral randomized A/B artifacts and record actual human results; keep missing judgments pending.
5. Resolve failed gates; keep the default artifact while any required evidence is pending. After all four live auto choices and other core gates pass, switch the default to auto, update mode documentation, verify omitted-mode routing, both loop validation and the full local suite.

## Impact

- **Priority**: P3 — closes the core epic with evidence.
- **Effort**: Medium — fixtures, bounded runs, comparison and budget arithmetic.
- **Risk**: Low — verification plus demonstrated corrections.
- **Breaking Change**: No.

## Use Case

The maintainer closes EPIC-3581 with four core mode runs, compatible sinks, bounded execution and credible regression checks, independently of optional capability delivery.

## Acceptance Criteria

- Four documented explicit mode=auto core runs select expected profiles/layouts with confidence >=0.6 and no fallback; only then, with tuning and other core gates passing, does this issue switch the default to auto; visual is text judged until FEAT-3585, and optional capability runs do not gate closure.
- Explicit built-knob override and preflight/classifier failure fixtures pass.
- No sink executes before validation; all sink compatibility tests use temporary/stubbed destinations.
- Nominal longest core/salvage visits fit max_steps; injected retries that exceed the parent cap reach its deterministic failure report, and child caps reach salvage. All prompt/action bounds, derived pre-tournament work (including classifier) and tail agree with the parent timeout; the child overrun remains one action plus one sleep. Native resume/queue acknowledgement and actionless terminals are verified; timeout/guard values agree, and rate-limit behavior cannot inherit a six-hour wait. Slow-call worst cases may intentionally salvage/fail at the child bound; preserve the parent reporting tail. Committed results cannot be overwritten or reused against changed judging inputs.
- Comparable old/new tags/duplicate groups, EPIC-3581's exact shared token accounting, per-brief calls/runtime/tie/abstention and import origin are recorded. Cells >= old, duplicates <= old, <=30 actual calls and <=1.5x matching baseline context tokens pass.
- Blind human A/B wins or ties on both pinned briefs, with actual recorded verdicts and the n=2 limitation stated.
- python -m pytest scripts/tests/ exits 0 and both brainstorm loops validate. Cross-capability/all-features requirements belong exclusively to ENH-3734 under EPIC-3687.

## Review Notes

_2026-10-05 implementation-boundary review; `/ll:advise` with claude-opus-5-5, confidence 0.78:_ Assigned the gated default switch here after four explicit-auto live runs pass; reconciled preserved input/output counters to the exact shared token denominators, and added queue/resume, local-terminal and derived-budget verification. No baseline rerun or new quality judgment occurred.

_2026-10-05 follow-up, Opus consult confidence 0.72:_ core evidence verifies bounded ingestion and durable replay. The matched token cap also gates FEAT-3582 before main; final-core comparison still belongs here. Existing baseline/GO results remain the evidence; new human judgments and live runs are pending implementation.

## Status

**Open** | Created: 2026-09-25 | Priority: P3
## Session Log
- Implementation-boundary review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.78; issue updates only) - 2026-10-05
- Follow-up pre-implementation review (Codex; `/ll:advise` with claude-opus-5-5, confidence 0.72; no new live measurements) - 2026-10-05
- Pre-implementation review and directive reconciliation (Codex; Opus consult unavailable: advisor task budget exhausted) - 2026-10-05
- `/ll:audit-issue-conflicts` - 2026-10-05T03:38:25 - `a86cd5e0-6077-4ee6-8374-60b76cefc32b.jsonl`
- `/ll:audit-issue-conflicts` - 2026-10-01T20:26:28 - `b32e58bb-e3b8-4048-9c71-1c2f63665ce9.jsonl`
