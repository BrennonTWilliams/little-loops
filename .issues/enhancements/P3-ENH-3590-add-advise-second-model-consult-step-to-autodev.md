---
id: ENH-3590
type: ENH
title: Add advise second-model consult step to autodev
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:36:09Z'
relates_to:
- ENH-3601
- EPIC-3565
blocked_by:
- ENH-3601
---

# ENH-3590: Add advise second-model consult step to autodev

## Summary

Add an opt-in `ll-advise` (second-model consult) step to autodev's preparation path so autodev gets a review from a stronger or different model. After ENH-3601, the anchor states (`run_go_no_go`, the repair/defer decisions) live in `scripts/little_loops/loops/prepare-issue.yaml`, so the step goes there, not in `autodev.yaml`.

## Current Behavior

`autodev.yaml` never consults a stronger or different model. The only adversarial check is `run_go_no_go` (same-model `Agent` subagent debate, `oversized_atomic` deferrals only); `/ll:confidence-check` and `oracles/resolve-decision` run on the default model, and no state references `advise`, `ll-advise`, or a `model:` override.

## Expected Behavior

autodev can, when explicitly enabled, run a non-interactive `/ll:advise` consult at one or more decision points and route on a verdict persisted to frontmatter/JSON. When disabled (the default), behavior and cost are unchanged.

## Motivation

autodev currently has no review by a stronger or different model. Its only adversarial check is `run_go_no_go` (~line 2244, `/ll:go-no-go --auto`), a same-model (sonnet) `Agent` subagent debate that fires only for `oversized_atomic` deferrals; a GO verdict stamps `outcome_gate_waived: true`. `/ll:confidence-check` and `oracles/resolve-decision` also run on the default model, and neither `autodev.yaml` nor `oracles/resolve-decision.yaml` references `advise`, `ll-advise`, or a `model:` override.

## Proposed Solution

Add a shell state in `prepare-issue.yaml` (alongside or after `run_go_no_go`, or before
repair/defer decisions) that calls the `ll-advise` CLI directly. It does not use the
`/ll:advise` skill.

- **Persistence**: `/ll:advise` saves nothing. It surfaces the result in the transcript.
  `ll-advise --json` prints a 7-key payload on stdout (`recommendation`, `risks`,
  `confidence`, `dissent`, `signal`, `host`, `model`) and has **no verdict field**. The
  state runs
  `ll-advise --signal <signal> --question ... --context-file ... --json > ${context.run_dir}/advise-<ID>.json`
  and a later state reads that file with Python (MR-1: no stdout parsing in `evaluate`).
- **Verdict mapping**: define a deterministic mapping from the payload to a routing
  verdict. For example: `confidence` below a threshold, or a non-empty `dissent`,
  → `ADVISE_CONCERN`; otherwise `ADVISE_OK`. The mapping and the threshold are
  decisions for this issue.
- **Rate limits / failure**: a non-zero `ll-advise` exit is infra. Skill-free shell states
  do not get 429 interception from `with_rate_limit_handling`. Route a non-zero exit to
  the wrapper's `retryable_error` terminal, or treat it as "no advice" and continue. Do
  not route to `finalize_rate_limited`: that state exists only in `autodev.yaml`, not in
  `prepare-issue.yaml`.
- `ll-advise` already resolves its advisor host independently (`--host`, `advisor.host`);
  add no new `"claude"` literals.
- Opt-in through a context flag; off by default, so it adds no cost.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- The claim that skill-free shell states do not get 429 interception from `with_rate_limit_handling` is inaccurate as stated: interception is executor-side and fires for any state that produces an `action_result` with non-zero exit and a TRANSIENT rate-limit/quota classification (`fsm/executor.py`, 429-detection block before interceptors; see also the memory note that wrapping a host CLI in `if cmd; then`/`|| true` disables retry). It applies to shell and slash_command states and is inert only on `loop:` delegate states. What the advise state must still guarantee is that a rate-limited `ll-advise` exits non-zero with a classifiable reason rather than being swallowed by a redirect/`|| true`.
- Budget side effect: every `manual=True` consult spends the per-task budget (`record_consult` runs before the host call; `max_consults_per_task=3` default, enforced even with `advisor.enabled: false`). An opt-in advise state therefore competes with skill-path consults for the same budget, and budget exhaustion surfaces as exit 2 with `budget_exhausted` — a skip reason the state's failure routing should treat as "no advice", not infra.
- Exit-contract fact for the failure route: `ll-advise` exits 0 only on success and 2 on all seven skip reasons (`disabled`, `trigger_not_allowed`, `budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`), never a traceback. A shell state routing on its exit code sees exactly 0/2 — `on_no` (1) never fires for CLI refusals.
- MR-1 posture: the consult is LLM-judged and `advisor_consult` is excluded from `NON_LLM_EVALUATOR_TYPES` (`fsm/validation/_base.py`), so the advise state cannot be the loop's only gate; the existing non-LLM routing (readiness thresholds, format-check predicates) must remain the arbiters, matching the `run_go_no_go` → `check_go_no_go_waiver` frontmatter-read pattern.

## Scope Boundaries

- **In scope**: an opt-in advise state in `prepare-issue.yaml` with a persisted, deterministically-read verdict; infra handling for a failing `ll-advise`; a context flag to enable it, passed through from autodev.
- **Not part of EPIC-3565**: this is a new capability, not an audit finding (the epic's scope is F1–F10 plus the consolidation). It was moved out of the epic on 2026-09-25 and keeps a `relates_to` link.
- **Out of scope**: changing `/ll:advise` or `ll-advise` internals; replacing `run_go_no_go`; enabling the consult by default; consult steps in loops other than `autodev` (e.g. `oracles/resolve-decision`) unless the open questions resolve otherwise.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prepare-issue.yaml` (created by ENH-3601) - new advise state near `run_go_no_go`
- `scripts/little_loops/loops/autodev.yaml` - opt-in `context:` flag passed through to `prepare-issue`

### Dependent Files (Callers/Importers)
- `ll-advise` CLI (`--json` payload contract; see `skills/advise/SKILL.md` step 3 for the 7 keys)

### Similar Patterns
- `run_go_no_go` (moves to `prepare-issue.yaml` in ENH-3601) - existing adversarial-review state and its `outcome_gate_waived` stamping

### Tests
- `scripts/tests/test_autodev_loop.py` - state wiring, routing, default-off behavior
- `scripts/tests/test_fsm_validation_meta_rules.py` - MR rules (MR-1 no stdout parsing) still pass
- `scripts/tests/test_advise_skill.py`, `scripts/tests/test_cli_advise.py` - reference for advise invocation contract

### Documentation
- `docs/reference/CLI.md` - `ll-advise` reference (link only if the new flag is user-facing)

### Configuration
- New autodev `context:` flag, default off (name TBD in Open Questions resolution)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `scripts/little_loops/loops/prepare-issue.yaml` does not exist yet (repo-wide glob: no match) — it is created by ENH-3601 (open, `blocked_by` edge already present). Until it lands, the anchor states live in `autodev.yaml`: `check_go_no_go_eligible` (one-shot marker `autodev-go-no-go-attempted-$ID`, fail-closed), `run_go_no_go` (`slash_command` `/ll:go-no-go --auto`, `fragment: with_rate_limit_handling`, `on_rate_limit_exhausted: finalize_rate_limited`), `check_go_no_go_waiver` (`ll-issues check-flag … outcome_gate_waived`), `reopen_waived`.
- `outcome_gate_waived` is stamped by model instruction (`skills/go-no-go/SKILL.md`, outcome_gate_waived escalation section) and read back loop-side via `ll-issues check-flag` (`check_go_no_go_waiver`, whose comment cites MR-1 for reading frontmatter instead of skill stdout) and embedded Python in `regate_after_atomic_remediation` / `recheck_after_size_review` — the persistence-read discipline this issue's verdict file should match.
- Capability note (no shipped loop wires any second-model consult today, but two seams exist): besides the `ll-advise` CLI, the FSM has a native evaluator route — `evaluate: {type: advisor_consult, question, verdict_map}` (`fsm/evaluators.py:1743`, FEAT-3039) — which reaches the same `consult_for_trigger` with no shell-out and returns a neutral verdict on failure. It is exercised only by test fixtures (`test_fsm_validation_meta_rules.py`). The shell-state design and the evaluator are alternative seams onto the same budget and verdict type; choosing between them is this issue's call, not a gap.
- Opt-in flag idioms in force (contested — two shapes): `workflow-generator.yaml` declares string `"false"` defaults with a `[ "${context.enable_shrink}" = "true" ]` gate state and `on_no` skip route (`check_shrink_enabled` :657, `promotion_gate` :845), asserted by `test_builtin_loops.py:19074` (`test_shrink_gated_by_context_flag`); `autodev.yaml:42` declares the empty-string default `skip_learning_gate: ""` consumed with `[ -n … ]` to append a CLI flag, overrideable via `ll-loop run autodev <ids> --context skip_learning_gate=1`. Every `${context.*}` interpolation inside a shell action needs an `# ll-lint: mr11-ok(...)` suppression (MR-11).
- Default-off wiring assertions live in `test_builtin_loops.py` (the `workflow-generator` tests), not `test_autodev_loop.py` — the latter asserts state routing and extracted predicates only (e.g. `_load_autodev_yaml()` + `on_no`/`on_yes` equality checks, and heredoc execution via `_extract_python_script`/`_run_reconcile_predicate`).
- Context flags reach child loops via the delegate state's `with:` mapping or `context_passthrough: true` (autodev's `refine_current` forwards `captured.input` as the child's `context.input`) — the pass-through from autodev to the future `prepare-issue` wrapper has both precedents.

## Implementation Steps

1. Decide the decision point(s) and verdict semantics (see Open Questions); confirm how `/ll:advise` persists its verdict to frontmatter/JSON.
2. Add the opt-in context flag and the advise state to `autodev.yaml` using `with_rate_limit_handling` (`on_rate_limit_exhausted: finalize_rate_limited`), reading the verdict from persisted output, not stdout.
   > ⚠ Superseded — advise state belongs in prepare-issue.yaml
3. Route on the verdict; when the flag is off, skip the state so the existing flow is unchanged.
4. Add tests to `test_autodev_loop.py` covering default-off, enabled routing, and rate-limit exhaustion.
5. Verify with `ll-loop validate autodev` and `python -m pytest scripts/tests/test_autodev_loop.py scripts/tests/test_fsm_validation_meta_rules.py`.

## Impact

- **Priority**: P3 - quality improvement to autodev review, opt-in and not blocking
- **Effort**: Medium - one new state plus tests, but verdict persistence and decision points need design
- **Risk**: Low - disabled by default, so no change to existing runs
- **Breaking Change**: No

## Program Design

### Types

- `AdvisorVerdict` — frozen dataclass, `scripts/little_loops/advisor.py`; exactly the 7 fields the CLI prints (`recommendation`, `risks`, `confidence`, `dissent`, `signal`, `host`, `model`). There is no separate CLI payload dataclass.
- `ConsultOutcome` — `scripts/little_loops/advisor.py`; fields `task_key`, `verdict: AdvisorVerdict | None`, `skipped_reason` (7-value Literal: `disabled`, `trigger_not_allowed`, `budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`), `error`.
- `AdvisorConfig` — `scripts/little_loops/config/orchestration.py`; defaults `enabled=False`, `host=None`, `model="opus"`, `min_tier=None`, `timeout_seconds=180`, `triggers=[]`, `max_consults_per_task=3`, `store_verdict_body=False`.

### Signatures

- `main_advise(argv: list[str] | None = None) -> int` — `scripts/little_loops/cli/advise.py` (entry point `ll-advise = "little_loops.cli:main_advise"` in `scripts/pyproject.toml`); exit 0 = consult succeeded, exit 2 = refused/failed (mapped from `skipped_reason` via `_SKIP_MESSAGES`, optionally suffixed with error detail), never a traceback.
- `cmd_invoke(args: argparse.Namespace, logger: Logger) -> int` — `scripts/little_loops/cli/advise.py`; builds `BRConfig(Path.cwd())`, applies `--host`/`--model` overrides, reads `--context-file` (unreadable → logged error, exit 2), then calls `consult_for_trigger(..., manual=True)`.
- `consult_for_trigger(trigger, *, question, context="", config=None, main_host=None, main_model=None, manual=False) -> ConsultOutcome` — `scripts/little_loops/advisor.py`; `manual=True` (the CLI path) bypasses `advisor.enabled` and the triggers allowlist but never the budget (`record_consult` runs before the host call).
- `consult(*, question, signal, context="", config=None, main_host=None, main_model=None) -> AdvisorVerdict` — `scripts/little_loops/advisor.py`; resolves the advisor via `resolve_host_named(advisor_host)` (`scripts/little_loops/host_runner.py`; implemented as `resolve_host({"LL_HOST_CLI": name})` — never PATH-probes, never mutates ambient `LL_HOST_CLI`, unregistered names raise `HostNotConfigured`).
- `evaluate_advisor_consult(output, *, question, verdict_map, signal, timeout, context_from, state_name, context=None) -> EvaluationResult` — `scripts/little_loops/fsm/evaluators.py:1743` (FEAT-3039); the pre-existing evaluator route to the same `consult_for_trigger`; returns the neutral fallback verdict `"neutral"` on skip/fail/unparseable.

### Call Path

Shell-state route (what this issue proposes): loop state → `ll-advise --signal … --question … --context-file … --json > ${context.run_dir}/advise-<ID>.json` → `main_advise` → `cmd_invoke` → `consult_for_trigger` → `consult` → `resolve_host_named(...).build_blocking_json(...)` → `run_blocking_json`. Evaluator route (already wired in the FSM, used by no shipped loop): state with `evaluate: {type: advisor_consult, question, verdict_map}` → `evaluate_advisor_consult` → `consult_for_trigger`. Both routes spend the same per-task budget.

### Decision Rules

- Verdict-mapping inputs are typed: `confidence` is numeric, `dissent` a possibly-empty string, `recommendation` free text — the deterministic `ADVISE_OK`/`ADVISE_CONCERN` mapping consumes exactly these; the threshold value is this issue's open decision.
- Rate-limit interception is executor-side, not fragment-side: it fires when a state produces an `action_result` with `exit_code != 0` and `classify_failure(...)` returns TRANSIENT with "rate limit"/"quota" in the reason (`scripts/little_loops/fsm/executor.py`, 429-detection block before interceptors). This applies to shell and slash_command states; it is inert only on `loop:` delegate states.
- MR-1: `advisor_consult` is excluded from `NON_LLM_EVALUATOR_TYPES` (`scripts/little_loops/fsm/validation/_base.py`) — an LLM consult never counts as a meta-loop's non-LLM evaluator; the loop's non-LLM gates must remain the routing arbiters.

## Open Questions

- Which decision points warrant the consult (oversized_atomic deferral, repair/defer, decision resolution)?
- Can an advise verdict waive or override a go-no-go result?
- What cost/latency budget applies per issue and per run?

## Acceptance Criteria

- [ ] `prepare-issue` has an advise state that invokes `ll-advise --json` at the chosen decision point(s)
- [ ] The payload is written to `${context.run_dir}/advise-<ID>.json` and mapped to a verdict deterministically, without stdout parsing
- [ ] A failing `ll-advise` never blocks or silently passes an issue; its routing is documented and tested
- [ ] Disabled by default; enabled via config/context flag
- [ ] `ll-loop validate autodev` and `ll-loop validate prepare-issue` pass

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-25T19:53:37 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:38:31 - `5a268ea5-1e20-43b6-ab65-c60ca9422822.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:19 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
- `/ll:format-issue` - 2026-09-25T03:38:19 - `ad599d43-c063-4f11-b93f-27c8bb93bc23.jsonl`
- `/ll:capture-issue` - 2026-09-25T03:36:14 - `d36455b9-41a7-4bb9-9928-6288b5c7fed1.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The consult is opt-in and disabled by default, so it stays off the default path (consistent with EPIC-3565's out-of-scope clause on adding skills to the happy path). Anchor states (`run_go_no_go` etc.) move to `prepare-issue.yaml` under ENH-3601; target that loop after it lands. Open Question to resolve against ENH-3601's deterministic go/no-go predicate: may an advise verdict waive a go-no-go result?
