---
id: ENH-3602
type: ENH
title: Single budget owner for learning-proof evidence
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:59Z'
decision_needed: false
relates_to:
- ENH-3601
- ENH-3577
- FEAT-3598
parent: EPIC-3565
blocks:
- FEAT-3598
- ENH-3601
confidence_score: 95
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 10
---

# ENH-3602: Single budget owner for learning-proof evidence

## Summary

Give learning-proof evidence (learning tests, spike proofs) a single budget owner. Today
confidence-check, ready-issue and the `ll-auto` learning gate each consult it and each
treat refuted/stale records their own way. Step E of the ENH-3577 decomposition (Proposed
Solution item 4, first half). Owner decided: Option A, the registry (see Decision Rationale).

## Current Behavior

Learning-proof logic is read in at least three places:

- `skills/confidence-check/SKILL.md` + `rubric.md` — caps outcome confidence on unproven mechanisms (BUG-3591)
- `commands/ready-issue.md` — readiness verdict references learning evidence
- `little_loops.issue_manager` (`process_issue_inplace`) — prints `LEARNING_GATE_BLOCKED` in `ll-auto`, which autodev
  detects in `check_learning_gate` / `check_learning_gate_infra` *after* implementation is attempted
- the Learning Test Registry (`little_loops.learning_tests`)

Nothing owns the spend (how many spike/explore-api attempts per issue per run), and a
record can be treated as stale by one consumer and valid by another.

## Expected Behavior

One component decides whether learning proof is sufficient, stale or refuted, and owns the
per-issue attempt budget. Other consumers read its verdict and do not re-derive it.

## Proposed Solution

### Option A: Registry owns it

> **Selected:** Option A — registry already holds `is_record_stale`/`describe_staleness`/`run_learning_gate_for_issue`; deterministic and consumable by B/C-style callers.

`little_loops.learning_tests` exposes `assess_proof(issue_id) -> ProofVerdict`
(`proven | stale | refuted | absent`, plus budget remaining). Confidence-check, ready-issue
and the `ll-auto` gate all call it. Deterministic; one staleness rule.

### Option B: Confidence-check owns it

Confidence-check is the only place proof sufficiency is judged; it writes the verdict to
frontmatter, and ready-issue / the `ll-auto` gate read that field. Keeps judgment in one
skill, but staleness becomes as fresh as the last scoring run.

### Option C: Preparation controller owns it

The ENH-3577 child controller owns the proof budget and emits `PROOF` as an obligation
outcome (FEAT-3598's planned obligation-selector subcommand — unbuilt today);
the `ll-auto` gate becomes a pure assertion that should never fire after a `ready` outcome.

### Decision Rationale

**Selected:** Option A (Registry owns it).

Scoring (0–3 each): 

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A | 3 | 2 | 3 | 2 | 10/12 |
| B | 1 | 2 | 1 | 1 | 5/12 |
| C | 1 | 1 | 2 | 1 | 5/12 |

Key evidence: `learning_tests/gate.py` already owns staleness (`is_record_stale`, `describe_staleness`) and
`issue_manager` already calls `run_learning_gate_for_issue`, so A extends an existing seam. B makes a
deterministic fact depend on an LLM scoring run's freshness. C depends on unbuilt FEAT-3598/ENH-3577 and
still needs a verdict source; the controller (C) can consume A's `assess_proof` to emit `PROOF`.

## Proof sources and budget scope (post-decision; review-hardened 2026-09-25)

The registry (`little_loops.learning_tests`) stores only learning-test records, keyed by
target string from `learning_tests_required`. Spike proof lives elsewhere, and the only
spike state readable from the issue file alone is its frontmatter: the flag set
`spike_attempted` / `spike_completed` / `spike_refuted` (written back by `/ll:spike`,
`skills/spike/SKILL.md:275` and `:285`) and the `gate:` entries via
`resolve_gate_verdict(frontmatter, text, spike_proven)`
(`little_loops.cli.issues.check_gate:110`). **Not** usable here: `ll-issues spike-verdict`
/ `classify_spike_junit` is a JUnit-XML classifier — it needs the spike run's
`--report role:xml:exit` artifacts, which the issue does not carry.
`resolve_gate_verdict` takes `spike_proven` as an input; `assess_proof` derives it from
the frontmatter flags. The spike attempt counter is run-scoped:
`${context.run_dir}/spike-runs-<ID>`, cap 2. The registry has no run identity, so it
cannot hold a per-run counter. Therefore:

- `assess_proof` aggregates **both** readable sources: registry records for each
  `learning_tests_required` target, and the issue's spike flags + gate state.
- `assess_proof` owns the budget **policy**; callers pass counts, never rules:
  - Run-scoped callers (FSM gates) pass `attempts_used` from their `run_dir` counter;
    `budget_remaining = max(0, 2 - attempts_used)`.
  - `attempts_used=None` (standalone skills) → `budget_remaining: None`, no run-scoped
    budget applies. This is **not** unlimited spend: the policy caps provisioning at one
    attempt per unproven target per caller invocation, followed by a re-assessment whose
    verdict is final.
  - Per-status *response* (WARN vs block vs provision) stays consumer-specific —
    consumers may not re-derive the *classification*, only map it: ready-issue keeps
    stale→WARN (no spend) / refuted·absent→provision-once→NOT_READY; confidence-check
    keeps stale −5 / refuted −10 + STOP.
- `commands/ready-issue.md` (Learning Test Gate, lines 254-263) already spends
  provision-once; it moves onto `assess_proof`'s classification and policy so it stops
  re-deriving stale/refuted/missing itself.

## Program Design

### Types

- `ProofStatus: Literal["proven", "stale", "refuted", "absent", "not_required"]` — overall verdict; the worst status among declared targets wins. `absent` is reserved for a *declared* target with no registry record; `not_required` means the issue declares no `learning_tests_required` targets and carries no spike proof requirement — it must not block or trigger provisioning
- `ProofVerdict: dataclass` — `issue_id`, `status: ProofStatus`, `targets: dict[str, ProofStatus]` (learning-test targets plus `spike`; the `spike` key is omitted when no spike requirement exists), `budget_remaining: int | None`, `reason: str`

### Signatures

- `assess_proof(issue_path: Path, *, attempts_used: int | None = None, stale_after_days: int | None = None, cwd: Path | None = None) -> ProofVerdict` — the single source of truth for proof classification, staleness and refutation. Learning-test leg: `is_record_stale` per registry record. Spike leg: the issue's frontmatter flags + `resolve_gate_verdict` (see Proof sources — NOT the JUnit-XML classifier). Staleness knobs: `stale_after_days=None` resolves the `learning_tests` config trio (`stale_after_days`, `version_aware_staleness`, `version_match_backstop_multiplier` — the same set `fsm/executor.py:_execute_learning_state` reads); when `learning_tests.enabled` is false, staleness evaluation is off entirely (proven counts fresh), matching the executor. Import note: leaf imports of `little_loops.cli.issues.check_gate` execute that package `__init__` (`set_status`, `session_store`) — no cycle today (verified 2026-09-25); hoist `resolve_gate_verdict` to a neutral module only if that weight ever matters
- `run_learning_gate_for_issue(issue_path: Path, *, skip: bool = False, cwd: Path | None = None, targets: list[str] | None = None) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]` — existing; gains an `assess_proof` **pre-check**: `status in ("proven", "not_required")` returns "passed" without spawning the subprocess gate; any other status takes the existing subprocess path unchanged (keyword-only additions keep the `TestAutoManagerLearningGate` dotted-path mocks intact). The child loop's `type: learning` state keeps its own stale→re-prove spend (declared residual surface), so a stale fixture legitimately yields "stale" from the pre-check yet may still yield "passed" after the gate re-proves — classification vs remediation, by design; parity ACs key on the pre-check

### Call Path

`issue_manager.process_issue_inplace` -> `run_learning_gate_for_issue` -> `assess_proof` (pre-check; the subprocess gate spawns only when status ∉ {proven, not_required}) -> `is_record_stale`

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md`, `skills/confidence-check/rubric.md`
- `commands/ready-issue.md`
- `scripts/little_loops/issue_manager.py`
- `scripts/little_loops/learning_tests/`
- `scripts/little_loops/cli/learning_tests.py` — new `assess` subcommand: `ll-learning-tests assess --issue <ID> [--json]`, the surface prompt-driven consumers call; JSON `ProofVerdict` on stdout, exit 0 when `status ∈ {proven, not_required}`, 1 otherwise, 2 usage/issue-not-found
_Wiring pass added by `/ll:wire-issue`:_
- `.gemini/skills/confidence-check/{SKILL.md,rubric.md,reference.md}`, `.kimi-code/skills/confidence-check/{...}`, `.qwen/skills/confidence-check/{...}` — host mirrors of the skill; regenerate with `ll-adapt --host <gemini|kimi-code|qwen> --apply` (gated by `test_wiring_skills_and_commands.py::test_host_artifacts_are_not_stale` :489 and `test_skill_mirrors_carry_companions` :612)
- `.gemini/commands/ready-issue.toml`, `.kimi-code/skills/ll-ready-issue/SKILL.md` — command mirrors of `commands/ready-issue.md` (kimi renames it to a skill bridge)

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- Additional `is_record_stale` consumers that re-derive staleness today (the "single staleness rule" claim has this residual surface — consume `assess_proof` or record as explicitly out of scope): `scripts/little_loops/fsm/executor.py` `_execute_learning_state` (:1404, :1459), `scripts/little_loops/hooks/learning_tests_gate.py` (:28, :138, :145 — the only production `describe_staleness` consumer outside gate.py), `scripts/little_loops/hooks/install_learning_gate.py` (:32, :123), `scripts/little_loops/cli/learning_tests.py` `cmd_check --stale-aware` (:35-59), `scripts/little_loops/cli/ctx_stats.py` (:30, :1010), `scripts/little_loops/cli/history_context.py` (:69, :76), `scripts/little_loops/learning_tests/release_gate.py` `run_release_gate` (:36, :59), `scripts/little_loops/loops/migrate-sdk-version.yaml` (:37-44, embedded import)
- Proof-status consumers beyond the issue's three: `skills/go-no-go/SKILL.md` (:160-295 — runs `ll-learning-tests check` per target, a fourth stale/refuted judge), `scripts/little_loops/parallel/worker_pool.py` proof-first-task gate (:61-102 — ll-parallel), `scripts/little_loops/cli/sprint/run.py` `_run_learning_gate_preflight` (~:206), `scripts/little_loops/cli/history_context.py` (:104-121), `scripts/little_loops/cli/loop/scaffold_eval.py` (:64, :100, :178-192 — `check_proof_*` states shell `--stale-aware`), `scripts/little_loops/loops/rn-implement.yaml` `check_learning_ready` (:640, :1136)
- `LEARNING_GATE_BLOCKED` verdict-vocabulary consumers that must keep receiving the same tokens: `scripts/little_loops/loops/lib/common.yaml` `ll_auto_learning_gate_check` fragment (:368-386; consumed by autodev, rn-implement, rn-remediate), `rn-implement.yaml` (:995-1009, :1342-1353, :1431-1460, report-tally keys :1693-1694), `rn-remediate.yaml` (:887-1127), `skills/audit-loop-run/SKILL.md` (:275). The marker emit site `issue_manager.py:1216/:1234/:1255` (`LEARNING_GATE_BLOCKED` / `IMPLEMENT_FAILED` / `GATE_INFRA_FAILED`) must not move or rename
- `loops/oracles/verify-confidence-scores.yaml` (:23, :73) and `rn-remediate.yaml` (:148, :725) — additional `/ll:confidence-check` invokers sharing the rubric contract being edited

### Tests
- `scripts/tests/test_confidence_check_skill.py`, `test_spike_verdict.py`, `test_spike_skill.py`
- New: one staleness/refutation fixture yields the same verdict from every consumer
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_learning_tests_gate.py` (:12-353) — the full `run_learning_gate_for_issue` suite mocks `subprocess.run`; no test pins staleness there today. Signature-stability constraint: stay `(issue_path, *, skip, cwd, targets)` — a new `attempts_used` parameter must carry a default or the mocks break
- `scripts/tests/test_issue_manager.py` — `TestAutoManagerLearningGate` (:5243-5553) patches `"little_loops.issue_manager.run_learning_gate_for_issue"`; that dotted import path must remain, and :5511 asserts the `targets` kwarg
- `scripts/tests/test_ready_issue_lint.py` — pins today's auto-invoke policy: refuted (:168) / missing (:180) auto-invoke `/ll:explore-api`, stale does NOT (:187, WARN-only), rubric auto-provision rows (:197, :203) — moving ready-issue onto `assess_proof`'s budget means updating these, not just the prose
- `scripts/tests/test_confidence_check_skill.py` — content pins on the skill/rubric text: Phase 1.5 prefetch (:368-409, incl. STOP override :399), penalty rows −10 missing/refuted / −5 stale (:421-426) — keep or consciously update
- `scripts/tests/test_cli_learning_tests.py` (:274-340) — `--stale-aware` `cmd_check` behavior pins; plus new `assess` subcommand pins (exit contract 0/1/2, JSON verdict shape, `not_required` for empty requirements)
- `scripts/tests/test_learning_tests_version_staleness.py` + `test_learning_tests_discoverability.py:450-498` — `is_record_stale`/`describe_staleness` stay green (pure functions); new coverage should assert `ProofVerdict` carries the reason and that the budget cap is enforced
- `scripts/tests/test_fsm_fragments.py` (:2754, :2775 — `GATE_INFRA_FAILED`-before-`LEARNING_GATE_BLOCKED` ordering), `test_builtin_loops.py` (`TestLearningGateConsistency` :18467, learning-gate routing :7985-8066, `--skip-learning-gate` :8341, :18178, `LEARNING_GATE_BLOCKED_TOTAL` :17052), `test_rn_implement.py:464-472` (per-issue sidecar outcome)
- Shared-fixture convention: no repo-wide multi-module fixture exists — model the new "same fixture, every consumer" test on the dual-parametrize idiom of `test_route_spike_verdict_classification` (`test_spike_verdict_routing.py:50-63`); consumer-parity coverage over executor/hooks/ctx_stats/history_context/release_gate entry points is new territory (none tested today)
- Mirror/content gates: `test_wiring_skills_and_commands.py` (:489, :612, content rows :67/:364/:678/:888), `test_docs_audience_gate.py` (harness dirs — cite `little_loops.<module>`, never source-repo paths)

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:933` — the `learning_tests_required` verdict mapping (proven→PASS, stale→WARN, refuted/missing→NOT_READY) that `assess_proof` takes ownership of
- `docs/reference/API.md` — `little_loops.learning_tests` Public Functions table (:7458-7469) plus a new `### assess_proof` section; `### run_learning_gate_for_issue` (:7555-7572) prose needs the pre-check behavior
- `docs/reference/CLI.md` — new `ll-learning-tests assess` subcommand entry (exit contract + JSON verdict shape); the existing `:4489` row covers ll-history-context statuses only
- `docs/guides/LEARNING_TESTS_GUIDE.md` (:333-353), `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (:264-338 outcome-token table), `docs/guides/LOOPS_REFERENCE.md` (:469-488 pre-gate section), `docs/ARCHITECTURE.md` (Learning Test Registry :1543, schema v26 :665), `docs/reference/CLI.md:4489` (ll-history-context statuses)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate host mirrors after editing skills/commands: `ll-adapt --host <gemini|kimi-code|qwen> --apply` (confidence-check companions ×3 hosts; `.gemini/commands/ready-issue.toml`; `.kimi-code/skills/ll-ready-issue/SKILL.md`)
- Update `docs/reference/API.md` (`assess_proof` section + `run_learning_gate_for_issue` prose) and `docs/reference/ISSUE_TEMPLATE.md:933` verdict mapping
- Keep the marker triple (`LEARNING_GATE_BLOCKED` / `IMPLEMENT_FAILED` / `GATE_INFRA_FAILED`) emitting from `process_issue_inplace` at the same site — `loops/lib/common.yaml`'s fragment and the rn-* report tallies grep them
- Keep `run_learning_gate_for_issue` backward-compatible (keyword-only additions with defaults) — `TestAutoManagerLearningGate` mocks it by dotted path
- ~~Decide the disposition of the additional `is_record_stale` consumers listed under Dependent Files (executor, hooks ×2, cli ×3, release_gate, migrate-sdk-version.yaml): consume `assess_proof` or record as explicit residual surface~~ — decided 2026-09-25: recorded as explicit residual surface (see Scope Boundaries); they keep calling the stable pure functions and are not migrated in this issue

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - one verdict API/field and three consumers moved onto it
- **Risk**: Medium - changes when learning gates fire
- **Breaking Change**: No

## Scope Boundaries

- No change to how learning tests are authored (`/ll:explore-api`).
- The spike attempt counter stays in the caller's `run_dir`. Only the cap/policy moves into `assess_proof`.
- **Residual surface — decided 2026-09-25, out of scope:** every consumer listed under Dependent
  Files beyond the three in-scope ones keeps its current behavior. The additional
  `is_record_stale`/`describe_staleness` callers (`fsm/executor.py` `_execute_learning_state`,
  `hooks/learning_tests_gate.py`, `hooks/install_learning_gate.py`, `cli/learning_tests.py`
  `--stale-aware`, `cli/ctx_stats.py`, `cli/history_context.py`, `learning_tests/release_gate.py`,
  `loops/migrate-sdk-version.yaml`) keep calling the pure functions, which stay public and stable.
  The additional proof-status consumers (`go-no-go`, `parallel/worker_pool.py` proof-first-task
  gate, sprint preflight, `cli/history_context.py`, `loop/scaffold_eval.py`, `rn-implement.yaml`
  `check_learning_ready`) are likewise not migrated here. In-scope consumers stay exactly three:
  confidence-check, ready-issue, and the `ll-auto` learning gate.

## Acceptance Criteria

- [x] Owner option selected and recorded (Option A, registry)
- [ ] `assess_proof` is the source of truth for proof classification and the attempt-budget policy, covering learning-test targets and spike proof, exposed to prompt-driven consumers via `ll-learning-tests assess --issue` (exit 0 = implementation may proceed)
- [ ] A shared stale/refuted fixture classifies identically from `assess_proof`, the `assess` CLI, and the `ll-auto` pre-check; consumer *responses* may differ (WARN vs block vs provision) and must be declared in terms of `ProofStatus` (the controller-level learning-gate criterion lives in ENH-3601's AC)
- [ ] `ready-issue` spends provisioning attempts only within `assess_proof`'s policy — at most one `/ll:explore-api` per unproven target per invocation, final verdict from the re-assessment; the `test_ready_issue_lint.py` auto-invoke pins (:168, :180, :187) are updated to match
- [ ] `run_learning_gate_for_issue` short-circuits to "passed" on `proven`/`not_required` without spawning the subprocess gate, and returns blocked/impl_failed/infra_failed verbatim otherwise

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Confidence Check Notes

**Confidence Check — 2026-09-25** (Readiness 90/100 · Outcome Confidence 50/100)

### Outcome Risk Factors
- Very wide blast radius for learning-proof staleness verdicts — ~20 dependent consumers (executor, hooks ×2, cli ×3, release_gate, go-no-go, worker_pool, sprint preflight, rn-implement, `loops/lib/common.yaml` fragment, mirror gates ×3 hosts) must keep receiving identical verdict tokens; regression risk concentrates in the consumers whose stale/refuted behavior legitimately shifts (confidence-check, ready-issue, `ll-auto` gate)
- Consumer-parity test coverage is new territory — no multi-module fixture exists today; the "shared fixture, same verdict from every consumer" test must be authored from scratch (model on `test_route_spike_verdict_classification`'s dual-parametrize idiom)
- Residual judgment load: disposition of ~10 additional `is_record_stale` consumers (consume `assess_proof` vs record out of scope) is deferred to implementation

Advisory (Criterion 4 claim cap): Option C text cited a nonexistent `ll-issues` subcommand (FEAT-3598's planned obligation selector) as if it resolved today; harmless, but capped Criterion 4 at 10. Resolved 2026-09-25: the Option C text now marks it as planned/unbuilt, and the residual-surface scope decision (see Scope Boundaries) addresses the third risk factor above.

**Confidence Check — 2026-09-25 re-score** (Readiness 95/100 → PROCEED · Outcome Confidence 60/100 → MODERATE)

Prior run's Criterion 4 claim cap cleared (Option C text fixed, `stale_cli_flag` now empty);
prior risk factor 3 (residual judgment load) resolved by the Scope Boundaries decision.

### Outcome Risk Factors
- Broad preserved-contract surface: the marker triple (`LEARNING_GATE_BLOCKED` / `IMPLEMENT_FAILED` / `GATE_INFRA_FAILED`) consumers (`loops/lib/common.yaml` fragment, rn-implement/rn-remediate report tallies, audit-loop-run) must keep receiving identical tokens while the verdict source changes underneath — mitigation: keep the emit site at `issue_manager.py:1216-1255` unmoved and `run_learning_gate_for_issue`'s return contract + keyword-only signature backward-compatible (pinned by `TestAutoManagerLearningGate` and `test_fsm_fragments` ordering pins)
- Consumer-parity fixture is new territory — no repo-wide multi-module fixture exists today; model the "same fixture, same verdict from every consumer" test on the dual-parametrize idiom of `test_spike_verdict_routing.py:50-63`

**Review hardening — 2026-09-25** (pre-implementation review against source): pinned the ll-auto-gate integration to an `assess_proof` pre-check inside `run_learning_gate_for_issue` (the child loop's verdict-producing `type: learning` state stays residual; the stale-classification vs re-prove-remediation distinction is explicit), added the `ll-learning-tests assess` CLI surface required by the two prompt-driven consumers, corrected the spike source to frontmatter flags + `resolve_gate_verdict` (`classify_spike_junit` needs run artifacts the issue doesn't carry), added `not_required` to disambiguate `absent`, and pinned standalone budget semantics, staleness-knob resolution, and the `learning_tests.enabled` off-switch.

## Session Log
- `/ll:confidence-check` - 2026-09-25T22:57:17 - `615cf176-9cbb-485a-ab2f-e88a0321da3a.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:22:43 - `345d0814-f8e9-469f-ad62-bef9083d17be.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:51:15 - `85e4cae3-0d07-49cf-9a70-1d94df7e46ab.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:41:25 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:20 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:02:00 - `ccfdabfd-5c2e-49a6-bfd7-abb914a90640.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): The controller-level learning-gate criterion moved to ENH-3601, which this issue blocks. Test this issue with the shared stale/refuted fixture.
