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
confidence_score: 90
outcome_confidence: 50
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 0
---

# ENH-3602: Single budget owner for learning-proof evidence

## Summary

Give learning-proof evidence (learning tests, spike proofs) a single budget owner. Today
confidence-check, ready-issue and the `ll-auto` learning gate each consult it and each
treat refuted/stale records their own way. Step E of the ENH-3577 decomposition (Proposed
Solution item 4, first half). **Needs a decision on the owner.**

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

The ENH-3577 child controller owns the proof budget and emits `PROOF` via
`ll-issues next-obligation`; the `ll-auto` gate becomes a pure assertion that should never
fire after a `ready` outcome.

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

## Proof sources and budget scope (post-decision)

The registry (`little_loops.learning_tests`) stores only learning-test records, keyed by
target string from `learning_tests_required`. Spike proof lives elsewhere: issue
frontmatter (`spike_attempted`, the spike verdict read by `ll-issues spike-verdict`, the
`check-gate` `structured_proof`/`structured_open` state). The spike attempt counter is
run-scoped: `${context.run_dir}/spike-runs-<ID>`, cap 2. The registry has no run
identity, so it cannot hold a per-run counter. Therefore:

- `assess_proof` aggregates **both** sources: registry records for each
  `learning_tests_required` target, and the issue's spike verdict and gate state via the
  existing `spike-verdict` / `check-gate` functions.
- `assess_proof` owns the budget **policy** (the attempt cap and what "exhausted" means).
  The caller passes the attempt **count**, because it lives in the caller's `run_dir`.
  Standalone callers pass `None`, which means no run budget applies.
- `commands/ready-issue.md` (Learning Test Gate, lines 254-261) currently spends attempts
  on its own: it auto-invokes `/ll:explore-api` on `refuted` and on missing records. It
  moves onto `assess_proof`'s verdict and budget, so it stops re-deriving
  stale/refuted/missing itself.

## Program Design

### Types

- `ProofStatus: Literal["proven", "stale", "refuted", "absent"]` — overall verdict; the worst status among targets wins
- `ProofVerdict: dataclass` — `issue_id`, `status: ProofStatus`, `targets: dict[str, ProofStatus]` (learning-test targets plus `spike`), `budget_remaining: int | None`, `reason: str`

### Signatures

- `assess_proof(issue_path: Path, *, attempts_used: int | None = None, stale_after_days: int | None = None) -> ProofVerdict` — the single source of truth for proof sufficiency, staleness and refutation. Uses `is_record_stale` for registry records and the `spike-verdict` / `check-gate` helpers for spike proof
- `run_learning_gate_for_issue(issue_path: Path, *, skip: bool = False, cwd: Path | None = None, targets: list[str] | None = None) -> Literal["passed", "blocked", "impl_failed", "infra_failed", "skipped"]` — existing; its stale/refuted decision is taken from `assess_proof` instead of being re-derived

### Call Path

`issue_manager.process_issue_inplace` -> `run_learning_gate_for_issue` -> `assess_proof` -> `is_record_stale`

## Integration Map

### Files to Modify
- `skills/confidence-check/SKILL.md`, `skills/confidence-check/rubric.md`
- `commands/ready-issue.md`
- `scripts/little_loops/issue_manager.py`
- `scripts/little_loops/learning_tests/`
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
- `scripts/tests/test_cli_learning_tests.py` (:274-340) — `--stale-aware` `cmd_check` behavior pins
- `scripts/tests/test_learning_tests_version_staleness.py` + `test_learning_tests_discoverability.py:450-498` — `is_record_stale`/`describe_staleness` stay green (pure functions); new coverage should assert `ProofVerdict` carries the reason and that the budget cap is enforced
- `scripts/tests/test_fsm_fragments.py` (:2754, :2775 — `GATE_INFRA_FAILED`-before-`LEARNING_GATE_BLOCKED` ordering), `test_builtin_loops.py` (`TestLearningGateConsistency` :18467, learning-gate routing :7985-8066, `--skip-learning-gate` :8341, :18178, `LEARNING_GATE_BLOCKED_TOTAL` :17052), `test_rn_implement.py:464-472` (per-issue sidecar outcome)
- Shared-fixture convention: no repo-wide multi-module fixture exists — model the new "same fixture, every consumer" test on the dual-parametrize idiom of `test_route_spike_verdict_classification` (`test_spike_verdict_routing.py:50-63`); consumer-parity coverage over executor/hooks/ctx_stats/history_context/release_gate entry points is new territory (none tested today)
- Mirror/content gates: `test_wiring_skills_and_commands.py` (:489, :612, content rows :67/:364/:678/:888), `test_docs_audience_gate.py` (harness dirs — cite `little_loops.<module>`, never source-repo paths)

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/ISSUE_TEMPLATE.md:933` — the `learning_tests_required` verdict mapping (proven→PASS, stale→WARN, refuted/missing→NOT_READY) that `assess_proof` takes ownership of
- `docs/reference/API.md` — `little_loops.learning_tests` Public Functions table (:7458-7469) plus a new `### assess_proof` section; `### run_learning_gate_for_issue` (:7555-7572) prose needs the delegated stale/refuted decision
- `docs/guides/LEARNING_TESTS_GUIDE.md` (:333-353), `docs/guides/RECURSIVE_LOOPS_GUIDE.md` (:264-338 outcome-token table), `docs/guides/LOOPS_REFERENCE.md` (:469-488 pre-gate section), `docs/ARCHITECTURE.md` (Learning Test Registry :1543, schema v26 :665), `docs/reference/CLI.md:4489` (ll-history-context statuses)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Regenerate host mirrors after editing skills/commands: `ll-adapt --host <gemini|kimi-code|qwen> --apply` (confidence-check companions ×3 hosts; `.gemini/commands/ready-issue.toml`; `.kimi-code/skills/ll-ready-issue/SKILL.md`)
- Update `docs/reference/API.md` (`assess_proof` section + `run_learning_gate_for_issue` prose) and `docs/reference/ISSUE_TEMPLATE.md:933` verdict mapping
- Keep the marker triple (`LEARNING_GATE_BLOCKED` / `IMPLEMENT_FAILED` / `GATE_INFRA_FAILED`) emitting from `process_issue_inplace` at the same site — `loops/lib/common.yaml`'s fragment and the rn-* report tallies grep them
- Keep `run_learning_gate_for_issue` backward-compatible (keyword-only additions with defaults) — `TestAutoManagerLearningGate` mocks it by dotted path
- Decide the disposition of the additional `is_record_stale` consumers listed under Dependent Files (executor, hooks ×2, cli ×3, release_gate, migrate-sdk-version.yaml): consume `assess_proof` or record as explicit residual surface

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - one verdict API/field and three consumers moved onto it
- **Risk**: Medium - changes when learning gates fire
- **Breaking Change**: No

## Scope Boundaries

- No change to how learning tests are authored (`/ll:explore-api`).
- The spike attempt counter stays in the caller's `run_dir`. Only the cap/policy moves into `assess_proof`.

## Acceptance Criteria

- [x] Owner option selected and recorded (Option A, registry)
- [ ] `assess_proof` is the source of truth for proof sufficiency and the attempt-budget policy, covering learning-test targets and spike proof
- [ ] Confidence-check, ready-issue and the `ll-auto` learning gate agree on a shared stale and refuted fixture
- [ ] `ready-issue` no longer spends `/ll:explore-api` attempts outside `assess_proof`'s budget
- [ ] The shared stale/refuted fixture yields the same verdict from `assess_proof` and the `ll-auto` gate (the controller-level learning-gate criterion now lives in ENH-3601's AC)

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

Advisory (Criterion 4 claim cap): `ll-issues next-obligation` (Option C text) does not resolve — a forward-looking reference to a nonexistent subcommand under the rejected option; harmless, but caps Criterion 4 at 10.

## Session Log
- `/ll:confidence-check` - 2026-09-25T21:22:43 - `345d0814-f8e9-469f-ad62-bef9083d17be.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:51:15 - `85e4cae3-0d07-49cf-9a70-1d94df7e46ab.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:41:25 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:20 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:02:00 - `ccfdabfd-5c2e-49a6-bfd7-abb914a90640.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): The controller-level learning-gate criterion moved to ENH-3601, which this issue blocks. Test this issue with the shared stale/refuted fixture.
