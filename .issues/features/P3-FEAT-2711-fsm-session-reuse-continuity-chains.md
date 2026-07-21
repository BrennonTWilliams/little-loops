---
id: FEAT-2711
type: FEAT
title: FSM session reuse for continuity-of-reasoning state chains
priority: P3
status: deferred
captured_at: '2026-07-21T02:03:13Z'
discovered_date: '2026-07-21'
discovered_by: capture-issue
parent: EPIC-2456
labels:
- token-cost
- fsm
- orchestration
relates_to:
- EPIC-2456
- FEAT-2598
- ENH-2486
- ENH-2714
decision_needed: true
confidence_score: 35
outcome_confidence: 46
score_complexity: 10
score_test_coverage: 18
score_ambiguity: 0
score_change_surface: 18
missing_artifacts: true
spike_needed: true
spike_attempted: true
spike_completed: true
size: Very Large
deferred_by: automation
deferred_date: '2026-07-21T06:29:54Z'
deferred_reason: low_readiness
---

# FEAT-2711: FSM session reuse for continuity-of-reasoning state chains

## Summary

Every `HostRunner` adapter already implements a `resume` parameter
(`claude --continue`, `codex exec resume --last`, `gemini --resume latest`),
but `fsm/runners.py` never uses it — every FSM state spawns a fresh host
invocation. Add an opt-in per-state-chain `session_mode: continue` that threads
`resume=True` through the runner **for sequential reasoning chains where state
N+1 genuinely benefits from state N's working context** (e.g. plan → implement
on the same issue), saving the cost of re-deriving understanding, not just the
static prefix.

**Re-scoped 2026-07-20**: prefix-cost reduction is no longer this issue's
justification — that lever moved to ENH-2714 (static-prefix pruning), which
achieves it without breaking state isolation. This issue is now narrowly about
continuity of *reasoning*: chains where a fresh state would have to re-read the
codebase/plan to rebuild context the previous state already holds. If no builtin
loop has a chain where that re-derivation cost is demonstrably significant,
close this instead of implementing it.

## Motivation

For a plan → implement → self-review chain on one issue, a fresh session per
state re-reads the same files and re-derives the same understanding each time.
Resume keeps that working context (and the warm cache prefix) alive, sending
only the new state prompt as the next turn. This is a different saving from
ENH-2714's: it scales with task complexity, not catalog size.

Counterweights (why this is opt-in and narrow):
- Continued sessions re-read a growing transcript each turn — per-state input
  cost rises over the chain; savings decay as the chain lengthens.
- State isolation is the FSM's design point. Evaluator states
  (`check_semantic`/`llm_structured`) seeing prior conversation breaks
  MR-1-style independence; they must default to `fresh`.

## Current Behavior

`fsm/runners.py` calls `build_streaming(...)` with no `resume`; each state is an
independent conversation.

## Expected Behavior

With `session_mode: continue` set on a state chain, state N+1 resumes the
session started by state N. Default `fresh` everywhere, preserving current
behavior exactly.

## Proposed Solution

- Loop-YAML key `session_mode: fresh | continue` (default `fresh`); per-state
  override so evaluator/judge states in a continued chain force `fresh`.
- `fsm/runners.py` passes `resume=True` on non-first invocations when
  `continue` is active; reset to fresh on handoff/spawn boundaries and on
  host-CLI 429 retry (see `reference_fsm_rate_limit_exit_code` — don't mask
  exit codes).
- Guard: wire ENH-2486's per-invocation prompt-size guard to force a fresh
  session (or trigger compaction) when the continued session's context exceeds
  threshold.
- Validation: warn when an evaluator (`check_semantic`/`llm_structured`) state
  inherits `continue`.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Resume semantics are host-binary-scoped, not session-ID-scoped.** Every
  `HostRunner.build_streaming(resume=...)` implementation (`ClaudeCodeRunner`
  `host_runner.py:262`, `CodexRunner:520`, `GeminiRunner:902`,
  `OmpRunner:1090`) resumes "whichever conversation the host binary considers
  most recent" — none accept or forward a specific session/conversation ID.
  Under concurrent `ll-parallel` worktrees or multiple simultaneous
  `ll-loop run` invocations sharing one host CLI binary, a continued FSM
  state could resume a *different* concurrent loop's session rather than its
  own prior state. This is a real safety gap the issue's current
  Counterweights section doesn't mention.
- **ENH-2486's own research already confirmed and deliberately preserved the
  fresh-session-per-state invariant** ("No new host `--continue`/`--resume`
  behavior introduced" was an explicit AC of that closed issue) — this issue
  is a considered reversal of that boundary, not new ground.
- **A structurally different alternative already has real infrastructure**,
  raised in prior review (`ll-history-context FEAT-2711`): "What if instead
  we removed and/or changed the artifacts re-read every new session?"
  FEAT-2598's `compact_session()` / `compact_result_for_session()`
  (`session_store.py:3444`, `compaction/result.py:34`) already produces a
  portable `summary_text` condensed artifact keyed by session ID via LCM's
  3-level escalation — but has **zero FSM-side callers today**. Structurally
  this is a "compact summary injection" mechanism rather than true session
  resume: state N's transcript gets condensed into `summary_text`, which
  state N+1 interpolates into its prompt — avoiding the concurrency-safety
  risk above entirely, at the cost of an extra LLM summarization call per hop.

**Option A**: `session_mode: continue` via host-level `resume` (issue's
original proposal) — reuses the existing `resume`/`resume_session` kwarg
already plumbed through `host_runner.py`/`subprocess_utils.py`; smallest code
change (schema + wiring only, mirroring the ENH-2714 `PruningProfileConfig`
template). Carries the "most recent session" concurrency risk identified
above and needs a mitigation (e.g. restricting to non-parallel/non-worktree
runs) before it's safe to ship.

**Option B**: Compact-summary injection via FEAT-2598's `compact_session()` /
`compact_result_for_session()` — no concurrency risk (keyed by session ID, no
host-level "most recent" ambiguity), reuses already-shipped LCM
infrastructure, and produces a smaller prompt than a raw resumed transcript
(condensed summary vs. full growing conversation). Requires new FSM-side
wiring (no caller exists yet) and pays a summarization LLM call per state
transition, plus session-ID capture at the FSM layer (which doesn't exist
today — the only run-scoped identifier is `run_id`, an archival string
unrelated to the host CLI conversation ID).

> **Selected:** Option B — compact-summary injection avoids the confirmed
> "most recent session" concurrency hazard (BUG-1385) that Option A inherits
> unmitigated, at the cost of new (but low-risk) FSM-side wiring.

**Recommended**: Option B for the step-0 gate re-evaluation — it directly
answers the reviewer's alternative-approach question, avoids the concurrency
hazard Option A inherits from "most recent session" resume semantics, and
builds on already-shipped FEAT-2598 infrastructure rather than reopening the
fresh-session-per-state invariant ENH-2486 deliberately closed. If Option A
is still preferred for its smaller diff, the concurrency risk must become an
explicit Acceptance Criterion (e.g. "disabled automatically under
`ll-parallel`/multi-worktree execution").

### Decision Rationale

Decided by `/ll:decide-issue` on 2026-07-21.

**Selected**: Option B — Compact-summary injection via FEAT-2598's
`compact_session()`/`compact_result_for_session()`

**Reasoning**: Option A and B tied numerically (8/12 each) and tied on the
Consistency tiebreaker, so the decision turned on risk severity: BUG-1385 is
direct historical proof that Option A's underlying `--continue`/`--resume`
semantics resolve to "most recent session" (not a specific ID), and no code
path in `worker_pool.py`, `subprocess_utils.py`, or `host_runner.py`
mitigates this under concurrent `ll-parallel`/`ll-sprint` worktrees — a live,
unmitigated correctness hazard. Option B's cost (one bounded summarization
LLM call per state hop, new but well-scoped FSM-side wiring reusing FEAT-2598's
mature, tested `compact_session()`/`compact_result_for_session()` primitives)
is a known, contained tradeoff rather than an open safety gap, and it
preserves the fresh-session-per-state invariant ENH-2486 deliberately
established — matching both the issue's own Pattern-D recommendation and
prior reviewer feedback skeptical of a resume-based approach.

#### Scoring Summary

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|--------------|------|-------|
| A (host resume) | 2/3 | 3/3 | 3/3 | 0/3 | 8/12 |
| B (compact-summary injection) | 2/3 | 1/3 | 2/3 | 3/3 | 8/12 |

**Key evidence**:
- Option A: `resume_session`/`build_streaming(resume=...)` plumbing is fully
  shipped and tested (`subprocess_utils.py:299,341`; 7 `build_streaming`
  impls across host adapters), but zero existing callers demonstrate
  concurrency-safe resume, and BUG-1385 confirms the exact "most recent
  session" failure mode the issue's own research flags as unmitigated.
- Option B: `compact_session()`/`compact_result_for_session()`
  (`session_store.py:3444`, `compaction/result.py:34`) are mature, tested,
  session-ID-scoped utilities with zero concurrency ambiguity, but the FSM
  layer has zero session-ID capture today (confirmed by exhaustive grep) —
  genuinely new wiring, not pure reuse.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/schema.py` — add a `session_mode`/
  `SessionModeConfig` field on `StateConfig` (~line 637, alongside
  `pruning_profile`) and `FSMLoop` (~line 1206), following the
  `PruningProfileConfig` to_dict/from_dict/suppression-flag pattern
  (`pruning_profile_ok` at line 1221) as the direct template.
- `scripts/little_loops/fsm/runners.py` — `ActionRunner.run()` Protocol
  (line 39) and `DefaultActionRunner.run()` (line 95) currently have no
  `resume`/`session_mode` parameter; add one and forward to
  `run_claude_command(resume_session=...)` (call site line 164).
- `scripts/little_loops/subprocess_utils.py::run_claude_command()` (line 286)
  — `resume_session: bool = False` (line 299) already exists and forwards to
  `resolve_host().build_streaming(resume=resume_session, ...)`
  (lines 337–346); no changes needed here, just a new caller.
- `scripts/little_loops/fsm/executor.py::FSMExecutor._run_action()`
  (lines 1589–1614) — resolve effective `session_mode` (state override →
  loop default, mirroring `_effective_pruning_profile()` in validation.py)
  and pass through to `self.action_runner.run(...)`. Needs a reset hook in
  `_handle_rate_limit`/`_exhaust_rate_limit` (line 2302/2522) to force fresh
  on retry exhaustion, and must NOT thread `resume` across `_handle_handoff`
  (line 2646) / `HandoffHandler._spawn_continuation()`
  (`fsm/handoff_handler.py:97`), which always spawns a new host session via
  `build_detached` (no `resume` param in that Protocol method at all).
- `scripts/little_loops/fsm/validation.py` — new MR-rule warning when a
  `check_semantic`/`llm_structured` evaluator state inherits `continue`,
  following the `_validate_parse_swallow()` (MR-10, lines 2011–2057)
  template; register in `validate_fsm()`; add suppression-flag key to the
  allowed top-level keys set (line 233).

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py:869,1107` and
  `scripts/little_loops/issue_manager.py:425-480` already call
  `run_claude_command(resume_session=True)` for an unrelated sentinel-driven
  continuation path (BUG-1377 Option E) — architecturally separate from FSM
  states; do not conflate the two mechanisms.
- `scripts/little_loops/loops/rn-build.yaml` — the concrete target chain
  (see Implementation Steps step 0); would gain `session_mode: continue` on
  its prompt states if this feature ships.

### Similar Patterns
- `scripts/little_loops/fsm/schema.py` `PruningProfileConfig` (ENH-2714,
  fields on `StateConfig.pruning_profile`/`FSMLoop.pruning_profile` +
  `pruning_profile_ok` suppression flag) — exact schema/wiring shape to
  mirror for `session_mode`.
- `scripts/little_loops/fsm/validation.py::_effective_pruning_profile()`
  (lines 2063–2067) — the two-level "state override, then loop default"
  resolution helper template for a new `_effective_session_mode(fsm, state)`.
- `scripts/tests/test_fsm_runners.py::test_model_kwarg_forwarded` (line 479)
  and siblings (`test_agent_kwarg_forwarded` 451, `test_tools_kwarg_forwarded`
  465, `test_working_dir_kwarg_forwarded` 493) — the
  `patch("little_loops.fsm.runners.run_claude_command", side_effect=capture)`
  + `captured_kwargs.get(...)` idiom to model a new
  `test_resume_kwarg_forwarded` test after.

### Tests
- `scripts/tests/test_fsm_schema.py::TestPromptSizeGuardConfig` (line 2805)
  and the `PruningProfileConfig` test class — template for a new
  `SessionModeConfig` schema test class (`test_defaults`/`test_from_dict_*`/
  `test_round_trip`/`test_fsmloop_default_omits_key`).
- `scripts/tests/test_fsm_validation.py::TestParseSwallow` (lines 4055–4163)
  — template for the new evaluator-inheritance MR-rule test suite
  (`test_mrN_fires_for_*`, `test_mrN_suppressed_by_*_ok`,
  `test_mrN_wired_into_validate_fsm`).
- `scripts/tests/test_subprocess_utils.py::TestResumeSession`
  (lines 1935–1980) — existing `--continue` flag-ordering assertions to
  reuse/extend, not duplicate.
- `scripts/tests/test_fsm_runners.py`, `scripts/tests/test_fsm_executor.py`
  — new state-sequence resume-flag and reset-on-retry regression tests.

### Documentation
- `docs/guides/LOOPS_GUIDE.md` / `docs/guides/LOOPS_REFERENCE.md` —
  state-field reference tables need a `session_mode` entry.
- `docs/guides/SESSION_HANDOFF.md` — should document that
  `session_mode: continue` never crosses a CONTEXT_HANDOFF boundary
  (handoff-spawn always starts fresh per
  `HandoffHandler._spawn_continuation`).
- `.claude/CLAUDE.md` Loop Authoring MR table — new row once the
  evaluator-inheritance rule ships (same pattern as the existing `haiku-gen`
  row).

## Implementation Steps

0. **Gate**: identify a concrete builtin-loop chain and estimate the
   re-derivation cost a continued session would avoid, from a locked trace.
   If not significant, close as superseded by ENH-2714. **Corrected target**:
   `rn-implement.yaml`'s states are almost entirely `action_type: shell` that
   delegate real work to sub-loops (`run_remediation: loop: rn-remediate`,
   `run_decomposition: loop: rn-decompose`) — not a direct prompt-mode chain.
   The genuine sequential `action_type: prompt` chain is
   `scripts/little_loops/loops/rn-build.yaml`: `tech_research` (line 268) →
   `design_artifacts` (line 318) → `commit_design` (line 338) →
   `check_substrate` → `scope_project` (line 374), where `design_artifacts`
   re-reads `${captured.tech_research.output}` via prompt interpolation on a
   fresh host session each time.
1. Schema: `session_mode` in `fsm/schema.py` + evaluator-inheritance warning.
2. Wiring in `fsm/runners.py` / `fsm/executor.py`; reset on handoff, error, and
   retry paths.
3. ENH-2486 guard integration (size threshold → fresh/compact).
4. Tests: state-sequence resume flag assertions; reset-on-retry regression;
   before/after total-token measurement on the locked chain trace.

## Acceptance Criteria

- [ ] Gate (step 0) documented in this issue: named chain + estimated
      re-derivation saving, or issue closed as superseded.
- [ ] `session_mode: continue` threads `resume=True` from state 2 onward on the
      Claude host; default behavior unchanged.
- [ ] Session resets on handoff/spawn, on hard errors, and per-state
      `session_mode: fresh` override.
- [ ] Validation warns when an evaluator state runs in continued mode.
- [ ] Measured total-token (not just prefix) delta on the locked chain trace
      recorded before close.

## Impact

- **Priority**: P3 — demoted from P2; ENH-2714 took the default savings lever.
  Value now contingent on the step-0 gate.
- **Effort**: Small-Medium (~80–120 LOC + tests) after the gate.
- **Risk**: Medium — changes state-isolation semantics; mitigated by opt-in
  default, evaluator warnings, and the narrowed scope.

## Confidence Check Notes

_Updated by `/ll:confidence-check` on 2026-07-21 (re-run after `/ll:spike`)_

**Readiness Score**: 35/100 → STOP — NOT READY
**Outcome Confidence**: 46/100 → Low

### Concerns
- Directive sections (Proposed Solution, Integration Map, Implementation Steps, Acceptance Criteria) still describe Option A end-to-end while the Decision Rationale selected Option B — this was flagged in the prior confidence-check pass and remains unresolved; `/ll:reconcile-issue` has not yet been run.
- The Spike Results section now shows Option B's core assumption doesn't hold as decided: `compact_session()`/`compact_result_for_session()` only summarize the "user" JSONL turn (the already-known interpolated prompt), never `assistant_messages` — so, used unmodified, they'd summarize the prompt sent, not the reasoning FEAT-2711 wants to carry forward. A new assistant-inclusive summarization path is required; this is closer to "new mechanism" than the Decision Rationale's "reuse of a mature, tested primitive" framing.
- The spike's promotion step (`session_id_capture.py`, `continuity_pipeline.py` moving from `scripts/tests/spike/fsm_continuity_compaction/` to `scripts/little_loops/`) and the new assistant-inclusive compaction function are not reflected anywhere in the Integration Map's "Files to Modify" list.

### Gaps to Address
- Reconcile Proposed Solution / Integration Map / Implementation Steps / Acceptance Criteria against the recorded Decision Rationale (Option B) — recommend `/ll:reconcile-issue`.
- Rewrite the Integration Map to add: (a) promotion of the spike's `session_id_capture.py` (into `run_claude_command()`'s stream-json parser) and `continuity_pipeline.py` (as a new FSM-side helper), and (b) the new assistant-inclusive summarization function the spike shows is actually needed (a new query joining `message_events` and `assistant_messages`, not a bare new caller of `compact_session()`).
- Re-baseline the Impact section's effort estimate ("Small-Medium, ~80–120 LOC") against the spike's finding that Option B needs a new mechanism, not just new wiring — the estimate predates the spike and likely understates real scope.

### Outcome Risk Factors
- No existing test exercises the required assistant-inclusive compaction path at the state-transition layer — this is a novel mechanism the current (Option-A-shaped) Integration Map does not address.
- The "reuse a mature, tested primitive" premise that justified Option B's low cost in the Decision Rationale's scoring (Simplicity 1/3, but assumed bounded) no longer holds per the spike — the real Depth is closer to moderate/deep (new cross-table query + summarization call) than the mechanical/local wiring the Integration Map describes.

## Spike Results

_Added by `/ll:spike` on 2026-07-21_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| Risk (a): zero precedent for FSM-side session-ID capture | `TestSessionIdCapture::test_parses_session_id_from_init_event` | ✓ pass — `session_id` is present and parseable in the `system`/`init` stream-json event `run_claude_command()` already consumes; it's currently discarded, not unavailable. Small addition, not new infrastructure. |
| Risk (b): unproven synchronous in-process backfill+compact for a just-finished session | `TestBackfillThenCompact::test_backfill_then_compact_same_process_no_race`, `::test_compact_returns_none_without_backfill` | ✓ pass — no async/race: `_backfill_messages`/`_backfill_assistant_messages` + `compact_session()` are ordinary synchronous calls; a same-process call right after a JSONL transcript is written works. Without that backfill step, compaction correctly no-ops (`message_events` empty → `compact_result_for_session` returns `None`). |
| Additional risk (surfaced during scoping, not in the original Outcome Risk Factors): does the unmodified compaction path actually capture reasoning continuity? | `TestSummaryOmitsAssistantContent::test_compact_summary_omits_assistant_derived_content` | ✓ pass — and the passing assertion is itself the finding: `compact_session()` reads only `message_events` (populated exclusively from `type == "user"` JSONL records by `_backfill_messages`); the assistant's derived understanding (file reads, analysis, decisions) lives in a separate `assistant_messages` table that `_compact_session_conn()` never queries. For a single FSM prompt-state invocation, the "user" turn is just the already-known interpolated prompt — the state's *new* information is entirely in the assistant turn. **Used unmodified, `compact_session()`/`compact_result_for_session()` would summarize the prompt already sent, not the reasoning FEAT-2711 wants to carry forward.** |

**Verdict**: The pipeline mechanics work (session-ID capture is feasible, synchronous backfill+compact has no race), so risks (a) and (b) are retired. But the third finding means Option B's Decision Rationale — which costed it as "reuse [of] already-shipped, tested primitives," small/contained relative to Option A — undercounts the real work: `compact_session()`/`compact_result_for_session()` cannot be reused as-is for this feature's actual goal. A genuinely new summarization path that also reads `assistant_messages` (or a new query joining both tables) is required, which is closer in scope to "new mechanism" than "new caller of a mature primitive." The Integration Map (still written for Option A per the Confidence Check Notes) needs to account for this when it's rewritten for Option B — not just add FSM-side callers, but likely add a new compaction function.

**Spike location**: `scripts/tests/spike/fsm_continuity_compaction/`
**Verification**: 7 spike tests pass across 1 command; 84 tests pass across 2 named regression suites (`test_compaction.py`: 18 passed; `test_session_store.py -k "backfill or compact"`: 66 passed).
**Promotion**: move `session_id_capture.py` (as an addition to `run_claude_command()`'s stream-json parser) and `continuity_pipeline.py` (as a new `fsm`-side helper) to `scripts/little_loops/spike/fsm_continuity_compaction/` in a separate PR, alongside a rewritten Integration Map that adds the assistant-inclusive summarization path this spike shows is actually needed.

## Session Log
- `/ll:confidence-check` - 2026-07-21T00:00:00 - `2c9bb61e-52c7-4382-bb2d-548f2ed16b2e.jsonl`
- `/ll:spike` - 2026-07-21T06:26:29 - `b8baac76-19eb-4fb4-b95c-b038dac192d6.jsonl`
- `/ll:confidence-check` - 2026-07-21T00:00:00 - `1b27a2d1-3395-4c44-b571-ca25f06f1c5c.jsonl`
- `/ll:decide-issue` - 2026-07-21T06:11:34 - `6c6a0724-c601-45b3-ad92-597103237076.jsonl`
- `/ll:refine-issue` - 2026-07-21T06:06:41 - `4d8712db-e54c-4500-8e35-7ec80f16793b.jsonl`
- `/ll:capture-issue` - 2026-07-21T02:03:13Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/79ab3d38-0b67-42aa-9ad2-b6f2af55d225.jsonl`
- Re-scoped 2026-07-20: narrowed to continuity-of-reasoning chains; prefix-cost
  justification moved to ENH-2714; added step-0 viability gate; demoted P2→P3.

---

## Status

**Open** | Created: 2026-07-21 | Priority: P3
