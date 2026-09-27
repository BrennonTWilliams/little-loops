---
id: ENH-3590
type: ENH
title: Add advise second-model veto to the go-no-go waiver in prepare-issue
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T03:36:09Z'
relates_to:
- ENH-3601
- EPIC-3565
- ENH-3626
blocked_by:
- ENH-3623
- ENH-3626
confidence_score: 75
outcome_confidence: 79
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 18
score_change_surface: 25
---

# ENH-3590: Add advise second-model veto to the go-no-go waiver in prepare-issue

## Summary

Add an opt-in `ll-advise` (second-model consult) step to autodev's preparation path so autodev gets a review from a stronger or different model. Once ENH-3606 moves the anchor states (`run_go_no_go`, the repair/defer decisions) into `scripts/little_loops/loops/prepare-issue.yaml` (ENH-3601/ENH-3605 only created the pass-through wrapper), the step goes there, not in `autodev.yaml`.

## Current Behavior

`autodev.yaml` never consults a stronger or different model. The only adversarial check is `run_go_no_go` (same-model `Agent` subagent debate, `oversized_atomic` deferrals only); `/ll:confidence-check` and `oracles/resolve-decision` run on the default model, and no state references `advise`, `ll-advise`, or a `model:` override.

## Expected Behavior

When explicitly enabled, autodev's preparation path runs one `ll-advise` CLI consult at a single decision point: after a go-no-go GO verdict has stamped `outcome_gate_waived: true`, and before the waiver re-opens the issue. The consult can **veto** the waiver. It can never grant one. The payload is persisted to `${context.run_dir}/advise-<ID>.json` and read back deterministically. When disabled (the default), or when the consult fails or is skipped, behavior and cost are unchanged.

## Motivation

autodev currently has no review by a stronger or different model. Its only adversarial check is `run_go_no_go` (~line 2420, `/ll:go-no-go --auto`), a same-model (sonnet) `Agent` subagent debate that fires only for `oversized_atomic` deferrals; a GO verdict stamps `outcome_gate_waived: true`. `/ll:confidence-check` and `oracles/resolve-decision` also run on the default model, and neither `autodev.yaml` nor `oracles/resolve-decision.yaml` references `advise`, `ll-advise`, or a `model:` override.

## Proposed Solution

- **Re-cut required after ENH-3623 (2026-09-26)**: ENH-3606 was cancelled and superseded
  by ENH-3623 (prepare-issue as a policy dispatch loop). Under that design the anchor
  states `check_go_no_go_waiver` and `reopen_waived` no longer exist. Go/no-go becomes a
  `GO_NO_GO` policy step, and the reopen becomes a precondition of the step after a GO.
  The veto consult therefore becomes a policy step after `GO_NO_GO`, or a precondition on
  the reopen. Re-cut the state chain below after ENH-3623 lands. The Resolved Decisions
  still hold: veto-only, fail-open, per-issue billing, and the `ll-advise` CLI seam.
- **Shared helper from ENH-3626 (2026-09-27)**: ENH-3626 adds the complementary
  done-path consult to `refine-to-ready-issue` and builds a shared Python helper that
  runs `ll-advise`, persists `advise-<ID>.{json,err,rc}`, and maps the payload to
  PROCEED/VETO/SKIPPED. This issue's consult calls that helper with its own signal and
  question instead of the hand-written `run_advise`/`read_advise_verdict` pair below.
  The two consults are not redundant: this one covers issues that fail the outcome
  threshold and are waived by a GO; ENH-3626 covers issues that pass the thresholds.

**Design: veto-only consult on the go-no-go waiver, via the `ll-advise` CLI in shell
states** (not the `/ll:advise` skill, and not the `advisor_consult` evaluator — see
Resolved Decisions).

Chain in `prepare-issue.yaml`, spliced into the existing
`check_go_no_go_waiver.on_yes` edge (state names are proposals):

```
check_go_no_go_waiver --on_yes--> check_advise_enabled
check_advise_enabled  --on_no/on_error--> reopen_waived          # flag off: today's path
                      --on_yes--> run_advise
run_advise            --next--> read_advise_verdict              # always exits 0
read_advise_verdict   --on_yes (PROCEED / SKIPPED)--> reopen_waived
                      --on_no  (VETO)--> veto_waiver
                      --on_error--> reopen_waived                 # unreadable = no advice
veto_waiver           --next--> <same target as check_go_no_go_waiver.on_no>
                      --on_error--> <wrapper's ladder-error terminal from ENH-3606>
```

- **Gate (`check_advise_enabled`)**: `[ -n "${context.advise_go_no_go}" ]`, which follows
  autodev's own empty-string idiom (`skip_learning_gate: ""`, `autodev.yaml:42`). Declare
  `advise_go_no_go: ""` in the `context:` blocks of both `autodev.yaml` and
  `prepare-issue.yaml`, and pass it through the delegate state. Enable with
  `ll-loop run autodev <ids> --context advise_go_no_go=1`.
- **Consult (`run_advise`)**: a shell state that captures everything and **always exits 0**:
  ```bash
  LL_ISSUE_ID="$ID" ll-advise --signal autodev_go_no_go_waiver \
    --question "<fixed question text; see below>" \
    --context-file "$ISSUE_FILE" --json \
    > "${context.run_dir}/advise-$ID.json" 2> "${context.run_dir}/advise-$ID.err"
  echo $? > "${context.run_dir}/advise-$ID.rc"; exit 0
  ```
  - This **deliberately opts out of executor-side 429 interception**, and a comment on the
    state must say so. Swallowing a host CLI's exit code (`|| true`,
    `if cmd; then`) disables 429 retry, which is a bug for main-host calls. Here it is intentional: the advisor may run on a different host than
    the loop (`advisor.host`). If the advisor is rate limited, autodev must not wait in
    place (up to 6h) or halt the queue. Without the swallow, the executor would also send
    an advisor auth failure (`NON_RECOVERABLE`) to `on_error`.
  - Do not use `fragment: with_rate_limit_handling`, and do not route to
    `retryable_error`, `mark_rate_limited` (ENH-3606's rate-limit terminal), or
    `finalize_rate_limited`.
  - `LL_ISSUE_ID="$ID"` bills the per-issue budget bucket, following the
    `autodev.yaml:2061` idiom. The default `LL_LOOP_RUN_ID` bucket would exhaust
    `max_consults_per_task=3` after three issues in one run.
  - `ll-advise` resolves its advisor host itself (`--host`, `advisor.host`). Add no new
    `"claude"` literals.
- **Question**: the question asks whether an issue the go-no-go debate approved despite
  outcome confidence below threshold should proceed. It instructs the advisor to begin
  `recommendation` with exactly one word, `PROCEED` or `VETO`. The context file is the
  issue file itself, which carries the go-no-go verdict and the confidence-check notes.
- **Verdict read (`read_advise_verdict`)**: embedded Python, per MR-1 (no stdout parsing in
  `evaluate`). It reads `.rc` and `.json` and exits 0 for PROCEED/SKIPPED and 1 for VETO:
  - `.rc` is missing or non-zero, or the JSON is missing or unparseable → **SKIPPED**
    (proceed, as if disabled). Log the skip reason from `.err` (one of the 7
    `_SKIP_MESSAGES`) to stderr and to the issue's session log.
  - The first word of `recommendation`, uppercased with punctuation stripped, equals
    `VETO` → **VETO**.
  - Anything else (`PROCEED`, no decision word, other text) → **PROCEED**.
  - `confidence` and `dissent` are **logged but not routed on**. `AdvisorVerdict.confidence`
    is a `float` whose scale neither the schema nor the prompt pins down, and `dissent`
    is non-empty in almost every response.
- **Veto (`veto_waiver`)**: removes `outcome_gate_waived` from frontmatter with
  `little_loops.frontmatter.remove_frontmatter_keys`, because no `ll-issues` subcommand
  clears a flag. It then appends a session-log line quoting the advisor's
  `recommendation`, and routes the same way as a NO-GO (`check_go_no_go_waiver.on_no`).
  The issue stays in its `oversized_atomic` deferral. The key must be removed, not
  skipped: `check-readiness`, `regate_after_atomic_remediation` (`autodev.yaml:2307`),
  `recheck_after_size_review` (`autodev.yaml:2642`), and the `:881` sweep all honor a
  stamped `outcome_gate_waived: true` on later passes.
- **`not_configured` when the flag is on**: an operator who sets `advise_go_no_go=1` without
  configuring `advisor.host` would otherwise skip every consult silently.
  `read_advise_verdict` writes a `WARNING: advise_go_no_go set but advisor host not
  configured` line to stderr when the skip reason is `not_configured`. It still proceeds
  and does not fail the issue.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- The claim that skill-free shell states do not get 429 interception from `with_rate_limit_handling` is inaccurate as stated: interception is executor-side and fires for any state that produces an `action_result` with non-zero exit and a TRANSIENT rate-limit/quota classification (`fsm/executor.py`, 429-detection block before interceptors; see also the memory note that wrapping a host CLI in `if cmd; then`/`|| true` disables retry). It applies to shell and slash_command states and is inert only on `loop:` delegate states. _(Superseded 2026-09-26: the design now swallows the exit code on purpose, so the advisor's rate limit can never stall or halt autodev. See Proposed Solution → Consult.)_ The executor also sends `NON_RECOVERABLE` (auth) failures to `on_error`, so without that swallow, exit codes would not be limited to 0/2.
- Budget side effect: every `manual=True` consult spends the per-task budget (`record_consult` runs before the host call; `max_consults_per_task=3` default, enforced even with `advisor.enabled: false`). An opt-in advise state therefore competes with skill-path consults for the same budget, and budget exhaustion surfaces as exit 2 with `budget_exhausted` — a skip reason the state's failure routing should treat as "no advice", not infra.
- Exit-contract fact for the failure route: `ll-advise` exits 0 only on success and 2 on all seven skip reasons (`disabled`, `trigger_not_allowed`, `budget_exhausted`, `not_configured`, `floor_violation`, `failed`, `timeout`), never a traceback. A shell state routing on its exit code sees exactly 0/2 — `on_no` (1) never fires for CLI refusals.
- MR-1 posture: the consult is LLM-judged and `advisor_consult` is excluded from `NON_LLM_EVALUATOR_TYPES` (`fsm/validation/_base.py`), so the advise state cannot be the loop's only gate; the existing non-LLM routing (readiness thresholds, format-check predicates) must remain the arbiters, matching the `run_go_no_go` → `check_go_no_go_waiver` frontmatter-read pattern.

## Scope Boundaries

- **In scope**: the four-state veto chain in `prepare-issue.yaml` (gate → consult → verdict read → veto), with a persisted, deterministically read verdict; fail-open handling for a failing or skipped `ll-advise`; the `advise_go_no_go` context flag, passed through from autodev.
- **Out of scope (by decision)**: the consult granting a waiver or overriding a NO-GO; consults at other decision points (repair/defer, decision resolution); using `confidence`/`dissent` for routing.
- **Not part of EPIC-3565**: this is a new capability, not an audit finding (the epic's scope is F1–F10 plus the consolidation). It was moved out of the epic on 2026-09-25 and keeps a `relates_to` link.
- **Out of scope**: changing `/ll:advise` or `ll-advise` internals; replacing `run_go_no_go`; enabling the consult by default; consult steps in loops other than `autodev` (e.g. `oracles/resolve-decision`) unless the open questions resolve otherwise.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/prepare-issue.yaml` (wrapper created by ENH-3605; anchor states arrive via ENH-3606) - new advise state near `run_go_no_go`
- `scripts/little_loops/loops/autodev.yaml` - opt-in `context:` flag passed through to `prepare-issue`

### Dependent Files (Callers/Importers)
- `ll-advise` CLI (`--json` payload contract; see `skills/advise/SKILL.md` step 3 for the 7 keys)

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:849` — `process_issue_inplace` calls `consult_for_trigger` with trigger `confidence_gate`; `scripts/little_loops/hooks/pre_done.py:175` calls it with trigger `pre_done` — both spend the same per-task `max_consults_per_task=3` budget the advise state competes with; exhaustion surfaces as exit 2 (`budget_exhausted`) [Agent 1 finding]
- `scripts/little_loops/cli/loop/runner.py:359` — sets `LL_LOOP_RUN_ID` for the whole run, so a bare shell-state `ll-advise` bills the per-run budget bucket; the per-issue idiom (`LL_ISSUE_ID="$ID" ...`, autodev.yaml:2061) is the alternative — pick deliberately [Agent 2 finding]
- `scripts/little_loops/cli/loop/run.py:345` — run pre-flight aborts on any `${context.<key>}` without `:default=` that is missing from that loop's `context:` block; the flag must be declared in BOTH `autodev.yaml` and `prepare-issue.yaml` [Agent 2 finding]
- `scripts/little_loops/cli/loop/next_loop.py:131` — `_resolve_autodev_params` binds only `input` for `ll-loop next-loop`; the new autodev context key must stay optional or this resolver's behavior changes [Agent 1 finding]
- `scripts/little_loops/init/writers.py:133` — `Bash(ll-advise:*)` is already in consuming projects' permission allowlist (synced by `ll-verify-cli-allowlist`); no change needed — confirms the shell-state route won't hit a permission wall [Agent 1 finding]
- `scripts/little_loops/session_store/writers.py:2272` — every consult writes an `advisor_consults` telemetry row (`write_advisor_consult`); enabled advise states generate rows automatically [Agent 1 finding]
- `scripts/tests/test_advisor.py:718` — `test_only_consult_for_trigger_calls_consult` pins `consult()`'s single-caller contract; the shell route via `ll-advise` is unaffected, a direct Python call would break it [Agent 1 finding]

### Similar Patterns
- `run_go_no_go` (moves to `prepare-issue.yaml` in ENH-3606) - existing adversarial-review state and its `outcome_gate_waived` stamping

### Tests
- `scripts/tests/test_autodev_loop.py` - state wiring, routing, default-off behavior
- `scripts/tests/test_fsm_validation_meta_rules.py` - MR rules (MR-1 no stdout parsing) still pass
- `scripts/tests/test_advise_skill.py`, `scripts/tests/test_cli_advise.py` - reference for advise invocation contract

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — the anchor-pattern file (not previously listed): `test_go_no_go_escalation_chain_shape` (:8146) + `_run_go_no_go_eligible` (:8182, bash -c with a stub CLI on PATH) are the template for the advise chain; `TestLearningGateConsistency.test_skip_flag_threads_through_sprint_chain` (:18280) is the flag pass-through chain pattern; `TestNoContextParameterKeyDuplication` (:21059) forbids the flag in both `context:` and `parameters:`; `TestBuiltinLoopReferencesResolve` (:17093) fails on any `loop: prepare-issue` reference before ENH-3601 lands [Agent 3 finding]
- `scripts/tests/test_cli_advise.py:38` — `_isolate_advisor_budget` isolates `.ll/advisor-budget/` state to tmp_path — reuse it so repeated state-routing tests don't trip the budget; `test_success_prints_exact_json_keys` (:53) pins the 7-key payload the mapping state parses [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py:212` — `test_autodev_yaml_loads_and_validates` is the in-process `ll-loop validate autodev` equivalent (no subprocess test runs the CLI) [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py:2461` / `scripts/tests/test_fsm_executor.py:7402` — `context_passthrough` schema round-trip and executor merge semantics — the pass-through mechanism's contract tests [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` - `ll-advise` reference (link only if the new flag is user-facing)

### Configuration
- New `context:` flag `advise_go_no_go: ""` (empty = off), declared in both `autodev.yaml` and `prepare-issue.yaml`

_Wiring pass added by `/ll:wire-issue`:_
- No new schema keys needed: `fsm-loop-schema.json` top-level `context` is free-form and all `AdvisorConfig` keys already exist (`config-schema.json:1879`); the flag needs only `context:` declarations in both loop files (MR-11) [Agent 2 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `scripts/little_loops/loops/prepare-issue.yaml` exists as the ENH-3605 pass-through wrapper only (`clear_record`, `run_refine_to_ready`, `forward_done`, `forward_stop`, `mark_inner_error`, `done`, `failed`); the anchor states move in via ENH-3606 (open, `blocked_by` edge). Until then they live in `autodev.yaml`: `check_go_no_go_eligible` (one-shot marker `autodev-go-no-go-attempted-$ID`, fail-closed), `run_go_no_go` (`slash_command` `/ll:go-no-go --auto`, `fragment: with_rate_limit_handling`, `on_rate_limit_exhausted: finalize_rate_limited`), `check_go_no_go_waiver` (`ll-issues check-flag … outcome_gate_waived`), `reopen_waived`.
- `outcome_gate_waived` is stamped by model instruction (`skills/go-no-go/SKILL.md`, outcome_gate_waived escalation section) and read back loop-side via `ll-issues check-flag` (`check_go_no_go_waiver`, whose comment cites MR-1 for reading frontmatter instead of skill stdout) and embedded Python in `regate_after_atomic_remediation` / `recheck_after_size_review` — the persistence-read discipline this issue's verdict file should match.
- Capability note (no shipped loop wires any second-model consult today, but two seams exist): besides the `ll-advise` CLI, the FSM has a native evaluator route — `evaluate: {type: advisor_consult, question, verdict_map}` (`fsm/evaluators.py:1743`, FEAT-3039) — which reaches the same `consult_for_trigger` with no shell-out and returns a neutral verdict on failure. It is exercised only by test fixtures (`test_fsm_validation_meta_rules.py`). The shell-state design and the evaluator are alternative seams onto the same budget and verdict type; choosing between them is this issue's call, not a gap.
- Opt-in flag idioms in force (contested — two shapes): `workflow-generator.yaml` declares string `"false"` defaults with a `[ "${context.enable_shrink}" = "true" ]` gate state and `on_no` skip route (`check_shrink_enabled` :657, `promotion_gate` :845), asserted by `test_builtin_loops.py:18656` (`test_shrink_gated_by_context_flag`); `autodev.yaml:42` declares the empty-string default `skip_learning_gate: ""` consumed with `[ -n … ]` to append a CLI flag, overrideable via `ll-loop run autodev <ids> --context skip_learning_gate=1`. Every `${context.*}` interpolation inside a shell action needs an `# ll-lint: mr11-ok(...)` suppression (MR-11).
- Default-off wiring assertions live in `test_builtin_loops.py` (the `workflow-generator` tests), not `test_autodev_loop.py` — the latter asserts state routing and extracted predicates only (e.g. `_load_autodev_yaml()` + `on_no`/`on_yes` equality checks, and heredoc execution via `_extract_python_script`/`_run_reconcile_predicate`).
- Context flags reach child loops via the delegate state's `with:` mapping or `context_passthrough: true` (autodev's `refine_current` forwards `captured.input` as the child's `context.input`) — the pass-through from autodev to the future `prepare-issue` wrapper has both precedents.

## Implementation Steps

1. After ENH-3606 lands, confirm where `check_go_no_go_waiver`'s `on_yes`/`on_no` edges point in `prepare-issue.yaml`, and find the name of the ladder-error terminal.
2. Declare `advise_go_no_go: ""` in the `context:` blocks of `autodev.yaml` and `prepare-issue.yaml`, and pass it through autodev's `prepare-issue` delegate state. Keep it out of `parameters:`.
3. Add `check_advise_enabled`, `run_advise`, `read_advise_verdict`, and `veto_waiver` to `prepare-issue.yaml` per the Proposed Solution chain, and retarget `check_go_no_go_waiver.on_yes` to `check_advise_enabled`. Add an `# ll-lint: mr11-ok(...)` suppression on each `${context.*}` interpolation inside a shell action. Add no states to `autodev.yaml`.
4. Tests in `test_builtin_loops.py`, alongside the go-no-go chain tests (`test_go_no_go_escalation_chain_shape`, `_run_go_no_go_eligible`):
   - chain-shape pin covering every edge in the diagram, including that `check_go_no_go_waiver.on_yes` reaches `reopen_waived` when the flag is empty;
   - `run_advise` exits 0 when a stub `ll-advise` on PATH exits 2, and when it prints rate-limit text on stderr; `.rc` records 2;
   - `run_advise` carries no `with_rate_limit_handling` fragment and no `on_rate_limit_exhausted`;
   - `read_advise_verdict` over fixture `.json`/`.rc` pairs: `VETO …` → exit 1; `PROCEED …`, `veto` embedded mid-text, missing JSON, rc 2, and malformed JSON → exit 0; `not_configured` in `.err` → exit 0 with the WARNING on stderr;
   - `veto_waiver` removes `outcome_gate_waived` from a tmp issue file, leaves other frontmatter intact, and routes to `check_go_no_go_waiver.on_no`'s target;
   - flag pass-through from autodev to `prepare-issue`, modeled on `test_skip_flag_threads_through_sprint_chain`.
   Reuse `_isolate_advisor_budget` (`test_cli_advise.py:38`) for any test that runs the real CLI.
5. Verify with `ll-loop validate autodev`, `ll-loop validate prepare-issue`, and `python -m pytest scripts/tests/test_builtin_loops.py scripts/tests/test_autodev_loop.py scripts/tests/test_fsm_validation_meta_rules.py scripts/tests/test_autodev_decision_gate.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Declare the opt-in flag in BOTH `autodev.yaml` and `prepare-issue.yaml` `context:` blocks (run pre-flight `cli/loop/run.py:345` + MR-11); keep it out of `parameters:` (`TestNoContextParameterKeyDuplication`); adding only a context flag adds no states to `autodev.yaml` — advise *states* belong in `prepare-issue.yaml`, never in `autodev.yaml`
- Match the go-no-go chain shape: gate state (flag check, default-off skip route) → advise state (writes `advise-<ID>.json`) → verdict-read state (embedded Python, MR-1). _Superseded 2026-09-26: the advise state deliberately carries **no** `with_rate_limit_handling` fragment; see Proposed Solution._
- Exit-code routing: _Resolved 2026-09-26: fail open._ `run_advise` always exits 0, and every non-success is SKIPPED → `reopen_waived`. Nothing routes to `retryable_error`. No failure edge enters a success terminal (`test_no_failure_edge_routes_to_a_success_terminal`).
- Budget billing: _Resolved 2026-09-26: per-issue_ (`LL_ISSUE_ID` prefix idiom, autodev.yaml:2061). The state shares the cap with the `issue_manager.py:849` and `hooks/pre_done.py:175` consults.
- Write the new structural tests in `test_builtin_loops.py` alongside the go-no-go chain tests (chain-shape pins + bash -c stub-`ll-advise` execution + default-off), not only in `test_autodev_loop.py`

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

## Resolved Decisions

_Resolved 2026-09-26 in review; these replace the former Open Questions._

- **Decision point**: exactly one. The consult runs after a go-no-go GO has stamped `outcome_gate_waived: true` on an `oversized_atomic` deferral, and before `reopen_waived`. Repair/defer and decision-resolution consults are out of scope.
- **Advise vs go-no-go**: veto-only. The consult can block a waiver that go-no-go granted. It can never grant a waiver or override a NO-GO. Because an LLM verdict can only tighten the gate, it never acts as a non-LLM arbiter (MR-1), and the existing deterministic `oversized_atomic` go/no-go trigger (ENH-3601 AC) stays unchanged.
- **Cost budget**: at most 1 consult per issue per pass, and only on the rare `oversized_atomic` GO path. It bills the per-issue bucket (`LL_ISSUE_ID`), so it shares `max_consults_per_task=3` with the `confidence_gate`/`pre_done` consults for the same issue. `budget_exhausted` is a SKIPPED.
- **Failure semantics**: fail open to today's behavior. Every non-success (exit 2 with any of the 7 skip reasons, advisor rate limit, advisor auth failure, unreadable output) is SKIPPED, logged, and proceeds exactly as if the flag were off. Disabling the consult cannot make an issue worse off than today, so failing open is safe.
- **Verdict mapping**: the leading decision word in `recommendation` (`VETO` → veto; everything else → proceed). `confidence` and `dissent` are logged but not routed on, because the confidence scale is unpinned and dissent is almost always non-empty.
- **Seam**: the `ll-advise` CLI in shell states, not the `advisor_consult` evaluator (`fsm/evaluators.py:1743`). Two reasons: the run_dir JSON file is the audit trail these ACs require, and the CLI's `manual=True` path makes the context flag the single opt-in. The evaluator would also require `advisor.enabled` and a `triggers` allowlist entry, and it would be that evaluator's first shipped use. Revisit if a second loop wants the same consult.

## Acceptance Criteria

- [ ] With `advise_go_no_go` empty (the default), `check_go_no_go_waiver.on_yes` reaches `reopen_waived` without invoking `ll-advise`; state count and routing are otherwise unchanged
- [ ] With the flag set, a GO waiver invokes `ll-advise --signal autodev_go_no_go_waiver --json` once, billed to the per-issue budget (`LL_ISSUE_ID`)
- [ ] The payload, stderr, and exit code are written to `${context.run_dir}/advise-<ID>.{json,err,rc}` and mapped to PROCEED/VETO/SKIPPED by embedded Python, without stdout parsing
- [ ] A `VETO` removes `outcome_gate_waived` from frontmatter, logs the advisor's recommendation to the session log, and routes like a NO-GO
- [ ] Any `ll-advise` failure (exit 2, advisor rate limit, auth failure, unreadable output) is equivalent to the flag being off: the waiver proceeds, the skip reason is logged, the loop never halts, and it never waits on a rate-limit retry. `not_configured` emits a WARNING line
- [ ] `run_advise` carries no `with_rate_limit_handling` fragment, and a comment explains the intentional interception opt-out
- [ ] `ll-loop validate autodev` and `ll-loop validate prepare-issue` pass; this issue adds no states to `autodev.yaml`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-25 | Priority: P3

## Verification Notes

_Added by `/ll:verify-issues` — 2026-09-26_

Verdict at time of check: **NEEDS_UPDATE** (all findings below corrected in the same pass, so the issue as it now reads is up to date — this section is a record of what was wrong and fixed, not an outstanding action item)

- **Stale premise (fixed: Summary, Integration Map, Scope Boundary now cite ENH-3606)**: ENH-3601 is `Completed`, but `scripts/little_loops/loops/prepare-issue.yaml` (90 lines) is only the ENH-3605 pass-through wrapper (`clear_record`, `run_refine_to_ready`, `forward_done`, `forward_stop`, `mark_inner_error`, `done`, `failed`). `run_go_no_go`, `check_go_no_go_waiver`, and the repair/defer states are still in `autodev.yaml` (`run_go_no_go` :2420, `finalize_rate_limited` :2973). They move under ENH-3606 (open). The Summary, Proposed Solution, and Integration Map claim the anchors live in `prepare-issue.yaml` "after ENH-3601"; that is false today.
- **`blocked_by` (fixed: now ENH-3606)**: `ENH-3601` is satisfied; the real blocker is ENH-3606. `retryable_error` also does not yet exist in any shipped loop.
- **Corrected**: `run_go_no_go` line ref (~2244 → ~2420); `test_builtin_loops.py` anchors (:8187→:8146, :8223→:8182, :18698→:18280, :21482→:21059, :17511→:17093, :19074→:18656); `autodev.yaml:2065` → :2061; `test_autodev_decision_gate.py:315` → :212.
- **Verified**: `issue_manager.py:849`, `pre_done.py:175`, `runner.py:359`, `run.py:345`, `evaluators.py:1743`, `Bash(ll-advise:*)` in `init/writers.py:133`, `finalize_rate_limited` present only in `autodev.yaml`. Evidence-quote check clean; no active required decision rules.
- **Advisory**: the confidence-check note's `stale_cli_flag` item (subcommand is `next-loop`) does not affect any directive here.
- **Graph**: provider=`codegraph` freshness=`stale` (not used to originate any verdict; checks were Grep/Read).

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-26 (supersedes 2026-09-25 run)_

**Readiness Score**: 75/100 → STOP — ADDRESS GAPS (Dependencies Hard Override; raw score would be PROCEED WITH CAUTION)
**Outcome Confidence**: 79/100 → MODERATE

### Concerns
- Design is fully specified and format-check is clean (no parity, claim, structure, or decision gaps); Program Design gate passes. Only the dependency blocks.
- Step names in the chain (`check_advise_enabled`, `veto_waiver`, etc.) and the ladder-error terminal are proposals until ENH-3606 lands; the exact edge targets must be re-confirmed then (Implementation Step 1).

### Gaps to Address
- blocked_by ENH-3606 (open) — the go-no-go anchor states (`check_go_no_go_waiver`, `reopen_waived`) still live in `autodev.yaml`; they move into `prepare-issue.yaml` there. Wait for or prioritize ENH-3606, then re-run `/ll:confidence-check`.

### Outcome Risk Factors
- Chain edits depend on states that do not yet exist in the target file (retarget of `check_go_no_go_waiver.on_yes` + error terminal), so tests cannot be written against the real shape until ENH-3606 merges.

## Session Log
- `/ll:confidence-check` - 2026-09-26T20:20:07 - `5304de58-f491-45bb-a965-830806ea2e48.jsonl`
- `/ll:verify-issues` - 2026-09-26T20:03:20 - `fad4d529-a955-4d85-a909-ec88da4f9e33.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:37 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:49:53 - `4a475966-a47c-4657-a3e4-16e6706f4c4d.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:53:37 - `52506a27-e6a0-49d9-99b0-9b89990953d8.jsonl`
- `/ll:decide-issue` - 2026-09-25T19:38:31 - `5a268ea5-1e20-43b6-ab65-c60ca9422822.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:19 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
- `/ll:format-issue` - 2026-09-25T03:38:19 - `ad599d43-c063-4f11-b93f-27c8bb93bc23.jsonl`
- `/ll:capture-issue` - 2026-09-25T03:36:14 - `d36455b9-41a7-4bb9-9928-6288b5c7fed1.jsonl`

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`): The consult is opt-in and disabled by default, so it stays off the default path (consistent with EPIC-3565's out-of-scope clause on adding skills to the happy path). Anchor states (`run_go_no_go` etc.) move to `prepare-issue.yaml` under ENH-3606; target that loop after it lands. The question of whether an advise verdict may waive a go-no-go result was resolved as veto-only: it may block a GO waiver but never grant one. ENH-3601's deterministic `oversized_atomic` go/no-go trigger is untouched.
