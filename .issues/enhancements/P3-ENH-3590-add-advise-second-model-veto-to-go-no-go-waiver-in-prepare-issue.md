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
- ENH-3633
blocked_by:
- ENH-3623
- ENH-3626
decision_needed: false
reconcile_attempted: true
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

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **ENH-3623 has now shipped (2026-09-27)**: `prepare-issue.yaml` is a 15-state policy-dispatch loop (`select_step`, `run_child`, `run_wire`, `run_refine_gap`, `run_rescore`, `run_reconcile`, `run_size_review`, `classify_guard2`, `record_guard2`, `record_step`, `run_go_no_go`, `apply_outcome`, `mark_rate_limited`, `done`, `failed` — pinned by `scripts/tests/test_prepare_issue.py::TestStructure.test_exactly_fifteen_states_stated_and_pinned`). `check_go_no_go_waiver`, `reopen_waived`, and `check_go_no_go_eligible` no longer exist anywhere — they were folded into `little_loops.preparation_policy._Decider.after_go_no_go()` (`scripts/little_loops/preparation_policy.py:455-463`), confirmed by `MOVED_STATES` in `scripts/tests/preparation_policy_harness.py:17-57`. The state-chain diagram, state names (`check_advise_enabled`, `run_advise`, `read_advise_verdict`, `veto_waiver`), and the `check_go_no_go_waiver.on_yes` splice point above this note are all obsolete and cannot be built as written.
- **`after_go_no_go()`'s current shape** (verbatim, `scripts/little_loops/preparation_policy.py:455-463`):
  ```python
  def after_go_no_go(self) -> Step:
      if not self.s.waived:
          return self.stop("oversized_atomic", "go/no-go did not stamp the waiver", row=True)
      # ENH-3606 accepted change 4: the waiver covers only the outcome gate.
      if (self.s.confidence or 0) < self.s.readiness_threshold:
          return self.stop("low_readiness", "waived but readiness below threshold", row=True)
      self.carry_preconditions.append("reopen")
      self.trail.append("GO: reopen")
      return self.pre_implement()
  ```
  The veto consult's insertion point is the third branch (waived + readiness OK), before `self.pre_implement()` is reached. `self.s.waived`/`self.s.confidence` come from `IssueSnapshot`, rebuilt fresh from frontmatter on every `decide()` call (`snapshot_issue()`, `preparation_policy.py:699-826`, `outcome_gate_waived` read via `_flag()`) — unchanged by this cutover. Note also: on the common (`FINISH`) exit of this same waived+ready branch, the `"reopen"` precondition is a documented no-op (`_run_preconditions` only runs on non-terminal steps, `preparation_policy.py:976-997`) — pinned as intentional/BUG-LIKE in `test_autodev_characterization.py:377-381`; unrelated to this issue but adjacent to the same function.
- **ENH-3626 decomposed into ENH-3632 (done) + ENH-3633 (open)**: the "shared Python helper" this issue's Proposed Solution names is `cmd_advise_consult`/`_cmd_advise_consult_inner` in `scripts/little_loops/cli/issues/advise_consult.py`, registered as `ll-issues advise-consult <issue_id> --run-dir <dir> [--signal ...] [--question ...] [--write-note]`. Its own module docstring names this issue directly: "the go-no-go waiver veto in ENH-3590." It differs from this issue's original hand-written design: it calls `little_loops.advisor.consult_for_trigger` in-process (no `ll-advise` subprocess, no `.json`/`.err`/`.rc` triple — it persists `<run_dir>/advise-<ID>.json` (payload) and `<run_dir>/advise-<ID>.verdict` (`{token, context_hash}`) via `_persist()`), prints exactly one of `PROCEED`/`VETO`/`SKIPPED` to stdout, and always exits 0. It preflights `config.advisor.host` before spending budget (empty host → `SKIPPED`, `"not_configured"`, no consult call). Replay is content-hash-gated: PROCEED/SKIPPED replay only while `trim_consult_context()`'s hash still matches; VETO is sticky regardless of hash. ENH-3633 (open, unblocked) is the sibling issue that wires this same helper into `refine-to-ready-issue.yaml`'s done path — its own (unimplemented) design proposes a loop-state gate→consult→`evaluate:{type:classify}`/`route:` chain calling `ll-issues advise-consult <ID> --run-dir ... --write-note`, which is the only extant design precedent for consuming this helper from a loop.
- **Layering conflict this issue must resolve**: `preparation_policy.py`'s own docstring (`:29-34`) states the pure decision layer is `little_loops.cli`-free, enforced by an import-boundary test. `advise_consult.py` lives under `little_loops.cli.issues`, so `after_go_no_go()` cannot import `cmd_advise_consult`/`_cmd_advise_consult_inner` directly without breaking that boundary.
- **The opt-in flag has nowhere to attach today**: `prepare-issue.yaml` declares no `context:` block at all (confirmed reading the full 199-line file) — it is a pure pass-through (`context_passthrough: true` from `autodev.yaml`'s `refine_current` state, `autodev.yaml:454-484`). `decide()`/`after_go_no_go()` is a pure function called via `ll-issues prep step`, which today takes only `issue_id`, `--run-dir`, `--readiness-threshold`, `--outcome-threshold` (no advise-related flag).

**Option A — new `StepKind` returned by `after_go_no_go()`, consult runs as a loop state**: `after_go_no_go()` gains a third exit — when waived+ready and the flag is set, return a new `StepKind` (e.g. `ADVISE_GO_NO_GO`) instead of falling into `pre_implement()`. `prepare-issue.yaml`'s `select_step.route` gets one new entry (`ADVISE_GO_NO_GO: run_advise_go_no_go`), and a new shell state `run_advise_go_no_go` calls `ll-issues advise-consult ${context.input} --run-dir ${context.run_dir} --signal autodev_go_no_go_waiver --question "..."` (the already-shipped, tested CLI surface), then `record_step` records the printed token as a new fact kind so a subsequent `decide()` call reads it back and branches: `VETO` → `stop("oversized_atomic", ...)` (same target as the current no-waiver branch); `PROCEED`/`SKIPPED` → falls through into the existing `carry_preconditions.append("reopen"); pre_implement()` path. Requires declaring `advise_go_no_go: ""` in `autodev.yaml`'s `context:` block only (mirroring `skip_learning_gate`, `autodev.yaml:44`) and adding a new `--advise-go-no-go` flag to `ll-issues prep step` so `decide()` can see it. Reuses the shipped `advise_consult.py` CLI exactly as built, keeps `preparation_policy.py`'s pure layer `cli`-free, and mirrors ENH-3633's own (not-yet-built) design for the sibling consult — the only extant precedent for consuming this helper from a loop.

> **Selected:** Option A — new `StepKind` returned by `after_go_no_go()`, consult runs as a loop state. It matches the existing 1:1 `StepKind`→state routing and fact-feedback precedents, reuses the shipped ENH-3632 helper verbatim, and mirrors the ENH-3633 sibling design instead of forking a second integration shape.

**Option B — in-process call from the pure layer**: `after_go_no_go()` imports `little_loops.advisor.consult_for_trigger` directly (that module is not under `little_loops.cli`, so this alone does not break the import-boundary test) and re-implements the persistence/verdict-mapping/replay-by-hash logic `advise_consult.py` already has, entirely inside `preparation_policy.py`. No new loop state or `StepKind` is needed; the whole decision resolves within one `decide()` call. This avoids an extra ladder round-trip but duplicates the shipped helper's persistence contract (`.json`/`.verdict`, replay-by-hash, VETO stickiness) rather than reusing it, and gives this issue and ENH-3633 two divergent implementations of what ENH-3632 was decomposed specifically to share.

**Recommended**: Option A for v1 — it reuses the shipped, tested helper byte-for-byte (no duplicated persistence/replay logic), keeps the pure `decide()` layer free of advisor-specific logic and CLI imports, and mirrors the sibling ENH-3633 design, so both consult sites converge on one integration shape instead of two.

### Decision Rationale

**Selected**: Option A — new `StepKind` returned by `after_go_no_go()`, consult runs as a loop state.

**Reasoning**: Option A reuses the existing 1:1 `StepKind`→state routing pattern (`select_step.route`, matching the shipped `GO_NO_GO` precedent) and the existing fact-feedback mechanism (`last_done()`) that already lets a prior step's recorded fact change a later `decide()` call. It calls the shipped, tested ENH-3632 helper (`ll-issues advise-consult`) exactly as built, keeps `after_go_no_go()`/`decide()` free of I/O (currently true, per `preparation_policy.py:313-676`), and matches ENH-3633's own sibling design for the parallel consult — so both consult sites converge on one integration shape. Option B would introduce the first I/O/subprocess call into the otherwise-pure `_Decider`, duplicate ~180 lines of `advise_consult.py`'s persistence/hash-replay/VETO-stickiness logic, diverge from the ENH-3633 precedent, and force mocking of host-CLI calls into `test_h4_after_go_no_go`, which is currently a trivial synchronous parametrized test.

| Dimension | Option A | Option B |
|---|---|---|
| Consistency | 3 | 0 |
| Simplicity | 2 | 0 |
| Testability | 3 | 1 |
| Risk | 3 | 1 |
| **Total** | **11/12** | **2/12** |

**Key evidence**:
- `select_step.route` in `prepare-issue.yaml:49-60` maps every `StepKind` 1:1 to a state (e.g. `GO_NO_GO: run_go_no_go`) — the precedent Option A's new route entry follows.
- `_Decider.run()` already branches on `self.f.last_done()` (e.g. `preparation_policy.py:390`) — the existing mechanism for feeding a prior step's fact into a later `decide()` call.
- Zero I/O calls exist inside `_Decider`/`decide()` today (`preparation_policy.py:313-676`); `consult_for_trigger` (`advisor.py:527-633`) makes a blocking host-CLI subprocess call (up to `timeout_seconds=180`) plus a SQLite telemetry write — Option B would be the first I/O in that layer.
- `advise_consult.py`'s persistence/replay contract (`_persist`, `trim_consult_context`, hash-gated replay, VETO stickiness, lines 80-247) is ~180 lines Option B would have to duplicate rather than reuse.
- ENH-3633's own design wires the same helper as a loop/shell state calling the CLI (`run_advise_ready` → `cmd_advise_consult`), matching Option A's shape, not Option B's.

## Scope Boundaries

- **In scope**: the new `ADVISE_GO_NO_GO` branch in `preparation_policy.py`'s `after_go_no_go()` (Option A) plus the single new `run_advise_go_no_go` state in `prepare-issue.yaml` calling the shipped `ll-issues advise-consult` helper, with a persisted, deterministically read verdict; fail-open handling for a failing or skipped consult; the `advise_go_no_go` opt-in flag, passed through from autodev.
- **Out of scope (by decision)**: the consult granting a waiver or overriding a NO-GO; consults at other decision points (repair/defer, decision resolution); using `confidence`/`dissent` for routing.
- **Not part of EPIC-3565**: this is a new capability, not an audit finding (the epic's scope is F1–F10 plus the consolidation). It was moved out of the epic on 2026-09-25 and keeps a `relates_to` link.
- **Out of scope**: changing `/ll:advise` or `ll-advise` internals; replacing `run_go_no_go`; enabling the consult by default; consult steps in loops other than `autodev` (e.g. `oracles/resolve-decision`) unless the open questions resolve otherwise.

## Integration Map

### Files to Modify
- `scripts/little_loops/preparation_policy.py` — primary file: `_Decider.after_go_no_go()` (`:455-463`) gains a new `StepKind.ADVISE_GO_NO_GO` branch on the waived+ready path (Option A); `add_prep_parser`/`cmd_prep`'s `step` subcommand gains a new `--advise-go-no-go` flag threaded into `decide()`
- `scripts/little_loops/loops/prepare-issue.yaml` - one new `select_step.route` entry (`ADVISE_GO_NO_GO: run_advise_go_no_go`) and one new shell state `run_advise_go_no_go`; bump the header's "15 states" count to 16
- `scripts/little_loops/loops/autodev.yaml` - opt-in `context: advise_go_no_go: ""` flag (mirroring `skip_learning_gate`, `:44`) passed through to `prepare-issue`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/preparation_policy.py` — `_Decider.run()`'s per-kind continuation ladder (`:380-408`, the `if kind == StepKind.GO_NO_GO.value: return self.after_go_no_go()` block) needs its own new `if kind == StepKind.ADVISE_GO_NO_GO.value:` branch to read the recorded verdict fact back and branch VETO → `stop("oversized_atomic", ...)` / PROCEED,SKIPPED → the reopen+`pre_implement()` continuation — the Call Path section names `after_go_no_go()` but not this separate ladder site as an edit target [Agent 1 finding]
- `scripts/little_loops/cli/issues/advise_consult.py` — contrary to this issue's current claim that this file "needs no changes": `_verdict_path()`/`_persist()` (`:174-188`) are private (module-local, confirmed zero external importers repo-wide) and there is no shared/importable helper for `<run_dir>/advise-<ID>.verdict`'s path. `prep_record()`'s new branch (see Dependent Files) must either duplicate the `run_dir / f"advise-{issue_id}.verdict"` construction or this file must export a public accessor [Agent 1 finding]

### Dependent Files (Callers/Importers)
- `ll-issues advise-consult` CLI (ENH-3632 helper, `cli/issues/advise_consult.py`) — calls `consult_for_trigger` in-process (no `ll-advise` subprocess), persists `advise-<ID>.json` (payload) and `advise-<ID>.verdict` (`{token, context_hash}`), and prints one of `PROCEED`/`VETO`/`SKIPPED` to stdout, always exiting 0

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_manager.py:849` — `process_issue_inplace` calls `consult_for_trigger` with trigger `confidence_gate`; `scripts/little_loops/hooks/pre_done.py:175` calls it with trigger `pre_done` — both spend the same per-task `max_consults_per_task=3` budget the advise state competes with; exhaustion surfaces as exit 2 (`budget_exhausted`) [Agent 1 finding]
- `scripts/little_loops/cli/loop/runner.py:359` — sets `LL_LOOP_RUN_ID` for the whole run, so a bare shell-state `ll-advise` bills the per-run budget bucket; the per-issue idiom (`LL_ISSUE_ID="$ID" ...`, autodev.yaml:2061) is the alternative — pick deliberately [Agent 2 finding]
- `scripts/little_loops/cli/loop/run.py:345` — run pre-flight aborts on any `${context.<key>}` without `:default=` that is missing from that loop's `context:` block; the flag must be declared in BOTH `autodev.yaml` and `prepare-issue.yaml` [Agent 2 finding]
- `scripts/little_loops/cli/loop/next_loop.py:131` — `_resolve_autodev_params` binds only `input` for `ll-loop next-loop`; the new autodev context key must stay optional or this resolver's behavior changes [Agent 1 finding]
- `scripts/little_loops/init/writers.py:133` — `Bash(ll-advise:*)` is already in consuming projects' permission allowlist (synced by `ll-verify-cli-allowlist`); no change needed — confirms the shell-state route won't hit a permission wall [Agent 1 finding]
- `scripts/little_loops/session_store/writers.py:2272` — every consult writes an `advisor_consults` telemetry row (`write_advisor_consult`); enabled advise states generate rows automatically [Agent 1 finding]
- `scripts/tests/test_advisor.py:718` — `test_only_consult_for_trigger_calls_consult` pins `consult()`'s single-caller contract; the shell route via `ll-advise` is unaffected, a direct Python call would break it [Agent 1 finding]
- `scripts/little_loops/preparation_policy.py:976-997` (`_run_preconditions`) — sole site enumerating legal precondition strings (`clear_records`, `clear_scores`, `defer_oversized_atomic`, `reopen`); confirmed no second allowlist exists elsewhere, so no new precondition name is needed for this issue, but the *sequencing* of the existing `"reopen"` precondition is a live bug for Option A — see Wiring Phase [Agent 1/2 finding]
- `scripts/little_loops/loops/prepare-issue.yaml:59-60` (`select_step.route`'s `_`/`_error` wildcard fallback to `apply_outcome`) — an unrouted `StepKind` token does not fail FSM validation; it silently reaches `_apply_outcome()`'s "Unknown outcome: fail closed as infra" catch-all (`preparation_policy.py:1288-1291`). Forgetting the new `ADVISE_GO_NO_GO: run_advise_go_no_go` route entry would fail closed as an infra error rather than a structural validation error, not a structural gap but a fail-mode worth confirming in tests [Agent 2 finding]

### Similar Patterns
- `select_step.route`'s 1:1 `StepKind`→state mapping (`prepare-issue.yaml:49-60`, e.g. `GO_NO_GO: run_go_no_go`) - the precedent the new `ADVISE_GO_NO_GO: run_advise_go_no_go` route entry follows
- `_Decider.run()`'s existing `self.f.last_done()` fact-feedback mechanism (`preparation_policy.py:390`) - feeds a prior step's recorded fact into a later `decide()` call, reused to read the advise verdict back
- ENH-3633's sibling design (wires the same ENH-3632 `ll-issues advise-consult` helper into `refine-to-ready-issue.yaml`'s done path) - the only extant precedent for a loop consuming this helper

### Tests
- `scripts/tests/test_preparation_policy.py` - pure-function `decide()`/`after_go_no_go()` coverage for the new `ADVISE_GO_NO_GO` branch (template: `test_h4_after_go_no_go`, `:606-641`)
- `scripts/tests/test_prepare_issue.py` - state-count pin (bump 15→16) and `select_step.route` coverage for `ADVISE_GO_NO_GO`
- `scripts/tests/test_prep_cli.py` - CLI coverage for the new `--advise-go-no-go` flag on `prep step`
- `scripts/tests/test_builtin_loops.py` - `advise_go_no_go` context-flag pass-through from `autodev.yaml` to `prepare-issue.yaml` (pattern: `TestLearningGateConsistency.test_skip_flag_threads_through_sprint_chain`, `:18280`)
- `scripts/tests/test_cli_advise.py` - `_isolate_advisor_budget` (`:38`) and the 7-key payload contract (`test_success_prints_exact_json_keys`, `:53`) for any test exercising the real advisor path
- `scripts/tests/test_fsm_validation_meta_rules.py` - MR-1 (no stdout parsing) still passes

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` — the anchor-pattern file (not previously listed): `test_go_no_go_escalation_chain_shape` (:8146) + `_run_go_no_go_eligible` (:8182, bash -c with a stub CLI on PATH) are the template for the advise chain; `TestLearningGateConsistency.test_skip_flag_threads_through_sprint_chain` (:18280) is the flag pass-through chain pattern; `TestNoContextParameterKeyDuplication` (:21059) forbids the flag in both `context:` and `parameters:`; `TestBuiltinLoopReferencesResolve` (:17093) fails on any `loop: prepare-issue` reference before ENH-3601 lands [Agent 3 finding]
- `scripts/tests/test_cli_advise.py:38` — `_isolate_advisor_budget` isolates `.ll/advisor-budget/` state to tmp_path — reuse it so repeated state-routing tests don't trip the budget; `test_success_prints_exact_json_keys` (:53) pins the 7-key payload the mapping state parses [Agent 3 finding]
- `scripts/tests/test_autodev_decision_gate.py:212` — `test_autodev_yaml_loads_and_validates` is the in-process `ll-loop validate autodev` equivalent (no subprocess test runs the CLI) [Agent 3 finding]
- `scripts/tests/test_fsm_schema.py:2461` / `scripts/tests/test_fsm_executor.py:7402` — `context_passthrough` schema round-trip and executor merge semantics — the pass-through mechanism's contract tests [Agent 3 finding]

_Wiring pass added by `/ll:wire-issue` (2026-09-27, second pass)_:
- `scripts/tests/test_preparation_policy_writers.py:110-167` (`TestPrepRecordClassifiesFromRunRecord`) — direct template for the new `prep_record()` `ADVISE_GO_NO_GO` branch test: write/omit the fake `<run_dir>/advise-<ID>.verdict` side-file the branch reads, call `prep_record()`, assert `done.payload[...]`, then call `prep_step()` again to assert the next `decide()` routes correctly off the recorded fact [Agent 3 finding]
- `scripts/tests/test_prep_cli.py` (e.g. `:104,107`, `test_cmd_prep_returns_2_for_unknown_subcommand`) — the `cmd_prep`/CLI-level test file; needs coverage for the new `--advise-go-no-go` flag on `prep step` [Agent 1 finding]
- `scripts/tests/test_prepare_issue.py:142-146` (`test_every_step_kind_routes_and_errors_fall_to_apply`) — hardcodes a route-key subset tuple that already omits `GO_NO_GO`, so it won't hard-fail without an update, but is the natural place to add `ADVISE_GO_NO_GO` for completeness [Agent 1/3 finding]
- New test mirroring `test_h4_after_go_no_go` / `test_h4_reopen_rides_on_a_decision_reentry_too` (`test_preparation_policy.py:606-641`) asserting `"reopen"` is **not** present in the `ADVISE_GO_NO_GO` step's `preconditions` and appears only on the step that follows a PROCEED/SKIPPED verdict — no existing test would catch the sequencing bug described in the Wiring Phase if implemented naively [Agent 2/3 finding]
- New real-FSM integration scenario extending `test_autodev_characterization.py`'s `oversized_atomic_go_reopen_implement` (`:359-386`) exercising `advise_go_no_go=1` for PROCEED, VETO, and SKIPPED (`not_configured`) outcomes — no scenario anywhere exercises the flag turned on today [Agent 3 finding]

### Documentation
- `docs/reference/CLI.md` - `ll-issues prep step`'s new `--advise-go-no-go` flag and the `StepKind` token list (`:2542-2548`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md:2542-2548` (`#### \`ll-issues prep\``) — enumerates the full `StepKind` token set verbatim (`RUN_CHILD, WIRE, REFINE_GAP, RESCORE, RECONCILE, SIZE_REVIEW, GO_NO_GO, FINISH, STOP`) and describes preconditions as "...reopening after one [go/no-go]" — both need the new token and the corrected (post-fix, see Wiring Phase) reopen sequencing [Agent 1/2 finding]
- `docs/reference/API.md:12311` — `StepKind` enum table row lists all 9 current values verbatim [Agent 1 finding]
- `docs/guides/LOOPS_REFERENCE.md:1096-1147` (`### \`prepare-issue\` — Preparation Dispatch Loop (internal)`) — "15-state dispatch loop" prose plus an ASCII flow diagram with no advise branch; the heading itself is pinned verbatim by `scripts/tests/test_wiring_reference_docs.py:271-274` (must not change), but the body (state count, diagram) is stale and not test-pinned [Agent 1/2 finding]
- `scripts/little_loops/loops/README.md:31` — a third independent "15 states" / command-list description of `prepare-issue` [Agent 1/2 finding]
- `docs/reference/DEFERRAL_CODES.md:25` — describes `oversized_atomic` as "a GO stamps `outcome_gate_waived: true` and reopens the issue for implementation" — single-step framing that becomes incomplete once an enabled veto can intervene between GO and reopen [Agent 2 finding]
- `skills/go-no-go/SKILL.md:402` — the `outcome_gate_waived` escalation paragraph has the same single-step GO→reopen framing [Agent 2 finding]
- `scripts/little_loops/loops/prepare-issue.yaml:5-26` — the loop file's own header comment ("Exactly 15 states (pinned by test_prepare_issue.py): ...") and call-chain comment need the new state name added [Agent 1/2 finding]

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

_Added by `/ll:refine-issue` — 2026-09-27 — based on codebase analysis:_

- **Files to Modify, corrected for post-ENH-3623 shape**: `scripts/little_loops/preparation_policy.py` (`_Decider.after_go_no_go()`, `:455-463` — new branch/StepKind on the waived+ready path) is now the primary file to modify, not `prepare-issue.yaml` states directly. Under Option A (recommended, see Proposed Solution), `scripts/little_loops/loops/prepare-issue.yaml` gets one new `select_step.route` entry and one new shell state (`run_advise_go_no_go`); `scripts/little_loops/loops/autodev.yaml` gains the opt-in `context: advise_go_no_go: ""` declaration (mirroring `skip_learning_gate`, `autodev.yaml:44`); `add_prep_parser`/`cmd_prep` (both defined in `scripts/little_loops/preparation_policy.py` itself, imported by `scripts/little_loops/cli/issues/__init__.py:140,810,1134` — the pure module already owns its own CLI-registration wrapper) need a new `--advise-go-no-go` flag on the `step` subcommand, threaded into `decide()`. `scripts/little_loops/cli/issues/advise_consult.py` (the ENH-3632 shared helper) needs no changes — it is called as-is via its existing `ll-issues advise-consult` CLI surface.
- **Dependent Files, corrected**: `scripts/tests/preparation_policy_harness.py:17-57` (`MOVED_STATES`) documents the states this issue's original design assumed still existed — now confirmed removed; `scripts/tests/test_preparation_policy.py:606-641` (`test_h4_after_go_no_go`, parametrized on `waived`/`confidence`) is the actual current unit-test template for a change to this decision point (pure-function `decide()` call + `check()` assertion on `Step.kind`/payload), superseding this issue's original `test_go_no_go_escalation_chain_shape`/`_run_go_no_go_eligible` references, neither of which exists anywhere in the codebase (confirmed 0 hits, repo-wide). `scripts/tests/test_prepare_issue.py` (`STATES` tuple + `"Exactly 15 states"` header-comment self-consistency pin) must be updated in lockstep if a new loop state is added (Option A). `.issues/enhancements/P3-ENH-3633-wire-opt-in-advise-ready-gate-into-refine-to-ready-issue-done-path.md` (status: open, unblocked) is the sibling consult-wiring issue and the only extant design precedent for a loop consuming the ENH-3632 helper.

## Implementation Steps

1. In `scripts/little_loops/preparation_policy.py`, add a new `StepKind.ADVISE_GO_NO_GO` value. In `_Decider.after_go_no_go()` (`:455-463`), on the waived+ready branch, when `advise_go_no_go` is set, return the new step instead of falling into `pre_implement()` — do **not** append `"reopen"` to `carry_preconditions` on this branch (see Wiring Phase sequencing correction).
2. Add a `run()`-ladder branch (`:380-408`, alongside `if kind == StepKind.GO_NO_GO.value:`) for `StepKind.ADVISE_GO_NO_GO.value` that reads the recorded verdict fact back via `self.f.last_done()` and branches: `VETO` → `stop("oversized_atomic", ...)`; `PROCEED`/`SKIPPED` → append `"reopen"` to `carry_preconditions` and call `pre_implement()`.
3. Add a `prep_record()` branch (`elif open_.step == StepKind.ADVISE_GO_NO_GO.value:`, mirroring `RUN_CHILD`/`SIZE_REVIEW`, `:1064-1078`) that reads `<run_dir>/advise-<ID>.verdict` and stamps the token into the fact payload — either duplicate the `run_dir / f"advise-{issue_id}.verdict"` path construction, or add a public accessor to `advise_consult.py`.
4. Add a new `--advise-go-no-go` flag to `add_prep_parser`'s `step` subcommand, threaded into `decide()`.
5. In `scripts/little_loops/loops/prepare-issue.yaml`, add one new `select_step.route` entry (`ADVISE_GO_NO_GO: run_advise_go_no_go`) and one new shell state `run_advise_go_no_go` calling `ll-issues advise-consult --signal autodev_go_no_go_waiver --question "..." --run-dir ${context.run_dir}`. Bump the header comment's state count from 15 to 16.
6. In `scripts/little_loops/loops/autodev.yaml`, declare `advise_go_no_go: ""` in the `context:` block (mirroring `skip_learning_gate`, `:44`) and pass it through to `prepare-issue`.
7. Update tests per the Integration Map's Tests section (pure-function `decide()` coverage, state-count pin, CLI flag coverage, flag pass-through, MR-1) and docs per the Documentation section.
8. Verify with `ll-loop validate autodev`, `ll-loop validate prepare-issue`, and `python -m pytest scripts/tests/test_preparation_policy.py scripts/tests/test_prepare_issue.py scripts/tests/test_prep_cli.py scripts/tests/test_builtin_loops.py scripts/tests/test_fsm_validation_meta_rules.py`.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Declare the opt-in flag in BOTH `autodev.yaml` and `prepare-issue.yaml` `context:` blocks (run pre-flight `cli/loop/run.py:345` + MR-11); keep it out of `parameters:` (`TestNoContextParameterKeyDuplication`); adding only a context flag adds no states to `autodev.yaml` — advise *states* belong in `prepare-issue.yaml`, never in `autodev.yaml`
  > ⚠ Superseded — prepare-issue.yaml declares no context: block; flag must reach decide() via a new CLI arg, not context interpolation, see Proposed Solution Option A
- Match the go-no-go chain shape: gate state (flag check, default-off skip route) → advise state (writes `advise-<ID>.json`) → verdict-read state (embedded Python, MR-1). _Superseded 2026-09-26: the advise state deliberately carries **no** `with_rate_limit_handling` fragment; see Proposed Solution._
  > ⚠ Superseded — no gate/verdict-read states exist; the decision lives in `after_go_no_go()`, see Proposed Solution Option A
- Exit-code routing: _Resolved 2026-09-26: fail open._ `run_advise` always exits 0, and every non-success is SKIPPED → `reopen_waived`. Nothing routes to `retryable_error`. No failure edge enters a success terminal (`test_no_failure_edge_routes_to_a_success_terminal`).
  > ⚠ Superseded — `run_advise`/`reopen_waived` don't exist; routing is now a `StepKind` branch in `after_go_no_go()`, see Proposed Solution
- Budget billing: _Resolved 2026-09-26: per-issue_ (`LL_ISSUE_ID` prefix idiom, autodev.yaml:2061). The state shares the cap with the `issue_manager.py:849` and `hooks/pre_done.py:175` consults.
- Write the new structural tests in `test_builtin_loops.py` alongside the go-no-go chain tests (chain-shape pins + bash -c stub-`ll-advise` execution + default-off), not only in `test_autodev_loop.py`
  > ⚠ Superseded — no go-no-go chain tests exist in test_builtin_loops.py; template is `test_preparation_policy.py:606-641` and `test_prepare_issue.py`, see Integration Map

**Second `/ll:wire-issue` pass (2026-09-27) — critical sequencing correction for Option A:**

- **Do not append `"reopen"` to `carry_preconditions` before returning the new `ADVISE_GO_NO_GO` step.** `_Decider.step()` (`preparation_policy.py:325-339`) merges `self.carry_preconditions` into whatever `Step` it constructs, and `prep_step()` (`:1000-1036`) only *skips* running preconditions when `step.kind in TERMINAL_KINDS` (`:1034`) — `ADVISE_GO_NO_GO` is not terminal, so a naive port of today's `after_go_no_go()` body (append "reopen" first, then return the new step instead of falling into `pre_implement()`) would reopen the issue immediately, before the advisor consult even runs, making the veto a no-op. This is not hypothetical: `test_h4_reopen_rides_on_a_decision_reentry_too` (`test_preparation_policy.py:638-641`) already pins `"reopen"` firing on a non-terminal `RUN_CHILD` step today via the same `carry_preconditions` mechanism. Move `self.carry_preconditions.append("reopen")` into the new continuation function that reads the `ADVISE_GO_NO_GO` fact back on PROCEED/SKIPPED, immediately before its call to `pre_implement()` — never on the branch that emits the `ADVISE_GO_NO_GO` step itself.
- Add the `run()`-ladder branch (`preparation_policy.py:380-408`, alongside `if kind == StepKind.GO_NO_GO.value:`) for `StepKind.ADVISE_GO_NO_GO.value` that performs the VETO/PROCEED/SKIPPED branch described above.
- Add a `prep_record()` `elif open_.step == StepKind.ADVISE_GO_NO_GO.value:` branch (mirroring `RUN_CHILD`/`SIZE_REVIEW`, `:1064-1078`) that reads `<run_dir>/advise-<ID>.verdict` and stamps the token into the fact payload; since `advise_consult.py`'s `_verdict_path`/`_persist` are private with zero external importers, either duplicate the path construction or add a public accessor.
- Bump `test_prepare_issue.py`'s `STATES` tuple and `"Exactly 15 states"` string (both there and in `prepare-issue.yaml`'s own header comment) to 16/`run_advise_go_no_go`.
- Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/guides/LOOPS_REFERENCE.md`, `scripts/little_loops/loops/README.md`, `docs/reference/DEFERRAL_CODES.md`, and `skills/go-no-go/SKILL.md` per the Documentation section above.

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
- `Step` / `StepKind` — `scripts/little_loops/preparation_policy.py`; `Step` carries `kind: StepKind`, `outcome`/`reason`, `preconditions: list[str]`. A veto branch (Option A) adds a new `StepKind` value (e.g. `ADVISE_GO_NO_GO`) alongside the existing `GO_NO_GO`/`FINISH`/`STOP`/etc.

### Signatures

- `main_advise(argv: list[str] | None = None) -> int` — `scripts/little_loops/cli/advise.py` (entry point `ll-advise = "little_loops.cli:main_advise"` in `scripts/pyproject.toml`); exit 0 = consult succeeded, exit 2 = refused/failed (mapped from `skipped_reason` via `_SKIP_MESSAGES`, optionally suffixed with error detail), never a traceback.
- `cmd_invoke(args: argparse.Namespace, logger: Logger) -> int` — `scripts/little_loops/cli/advise.py`; builds `BRConfig(Path.cwd())`, applies `--host`/`--model` overrides, reads `--context-file` (unreadable → logged error, exit 2), then calls `consult_for_trigger(..., manual=True)`.
- `consult_for_trigger(trigger, *, question, context="", config=None, main_host=None, main_model=None, manual=False) -> ConsultOutcome` — `scripts/little_loops/advisor.py`; `manual=True` (the CLI path) bypasses `advisor.enabled` and the triggers allowlist but never the budget (`record_consult` runs before the host call).
- `consult(*, question, signal, context="", config=None, main_host=None, main_model=None) -> AdvisorVerdict` — `scripts/little_loops/advisor.py`; resolves the advisor via `resolve_host_named(advisor_host)` (`scripts/little_loops/host_runner.py`; implemented as `resolve_host({"LL_HOST_CLI": name})` — never PATH-probes, never mutates ambient `LL_HOST_CLI`, unregistered names raise `HostNotConfigured`).
- `evaluate_advisor_consult(output, *, question, verdict_map, signal, timeout, context_from, state_name, context=None) -> EvaluationResult` — `scripts/little_loops/fsm/evaluators.py:1743` (FEAT-3039); the pre-existing evaluator route to the same `consult_for_trigger`; returns the neutral fallback verdict `"neutral"` on skip/fail/unparseable.
- `after_go_no_go(self) -> Step` — `scripts/little_loops/preparation_policy.py:455-463`; the pure decision function this issue's veto branch attaches to (see Proposed Solution).
- `cmd_advise_consult(config: BRConfig, args: argparse.Namespace) -> int` / `_cmd_advise_consult_inner(...)` — `scripts/little_loops/cli/issues/advise_consult.py`; the shipped ENH-3632 helper this issue's consult reuses via its `ll-issues advise-consult` CLI surface (not a direct import — see the layering-conflict finding in Proposed Solution), superseding the original hand-written `run_advise`/`read_advise_verdict` design.
- `map_advise_verdict(outcome: ConsultOutcome) -> tuple[str, str | None]` — `scripts/little_loops/cli/issues/advise_consult.py`; maps a `ConsultOutcome` to one of `PROCEED`/`VETO`/`SKIPPED` plus a log reason.

### Call Path

Shell-state route (what this issue's original design proposed — obsolete, see Proposed Solution): loop state → `ll-advise --signal … --question … --context-file … --json > ${context.run_dir}/advise-<ID>.json` → `main_advise` → `cmd_invoke` → `consult_for_trigger` → `consult` → `resolve_host_named(...).build_blocking_json(...)` → `run_blocking_json`. Evaluator route (already wired in the FSM, used by no shipped loop): state with `evaluate: {type: advisor_consult, question, verdict_map}` → `evaluate_advisor_consult` → `consult_for_trigger`. Both routes spend the same per-task budget.

Corrected route (post-ENH-3623, Option A recommended): `select_step` → `ll-issues prep step` → `decide()` → `_Decider.after_go_no_go()` → (new `StepKind` branch) → `select_step.route` → new state `run_advise_go_no_go` → `ll-issues advise-consult --signal autodev_go_no_go_waiver --question … --run-dir ${context.run_dir}` → `cmd_advise_consult` → `consult_for_trigger` → `consult` → `resolve_host_named(...)`. The verdict feeds back via `record_step` → `ll-issues prep record` → a fact `decide()` reads on its next call to branch `VETO` (`stop("oversized_atomic", ...)`) vs `PROCEED`/`SKIPPED` (`pre_implement()`).

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

- [ ] With `advise_go_no_go` empty (the default), `after_go_no_go()` returns to `pre_implement()` unchanged, without invoking any consult
- [ ] With the flag set on a GO waiver (readiness OK), `after_go_no_go()` returns the new `ADVISE_GO_NO_GO` step and `run_advise_go_no_go` invokes `ll-issues advise-consult --signal autodev_go_no_go_waiver` once, billed to the per-issue budget (`LL_ISSUE_ID`)
- [ ] The payload and verdict are persisted to `${context.run_dir}/advise-<ID>.json` and `advise-<ID>.verdict` by the shipped `ll-issues advise-consult` helper, and `prep_record()` reads the verdict back into the fact payload without stdout parsing
- [ ] A `VETO` removes `outcome_gate_waived` from frontmatter, logs the advisor's recommendation to the session log, and routes like a NO-GO (`stop("oversized_atomic", ...)`)
- [ ] Any consult failure (exit 2 skip reasons, advisor rate limit, auth failure, unreadable output) is equivalent to the flag being off: the waiver proceeds, the skip reason is logged, the loop never halts, and it never waits on a rate-limit retry. `not_configured` emits a WARNING line
- [ ] The `"reopen"` precondition is appended only on the PROCEED/SKIPPED continuation, never on the branch that emits the `ADVISE_GO_NO_GO` step itself (see Wiring Phase sequencing correction)
- [ ] `ll-loop validate autodev` and `ll-loop validate prepare-issue` pass; this issue adds no states to `autodev.yaml` and exactly one new state (`run_advise_go_no_go`) to `prepare-issue.yaml`

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

### Gaps to Address
- blocked_by ENH-3606 (open) — the go-no-go anchor states (`check_go_no_go_waiver`, `reopen_waived`) still live in `autodev.yaml`; they move into `prepare-issue.yaml` there. Wait for or prioritize ENH-3606, then re-run `/ll:confidence-check`.

### Outcome Risk Factors
- Chain edits depend on states that do not yet exist in the target file (retarget of `check_go_no_go_waiver.on_yes` + error terminal), so tests cannot be written against the real shape until ENH-3606 merges.

## Resolved Concerns
- [resolved 2026-09-27 by /ll:reconcile-issue] Step names in the chain (`check_advise_enabled`, `veto_waiver`, etc.) and the ladder-error terminal are proposals until ENH-3606 lands; the exact edge targets must be re-confirmed then (Implementation Step 1). — ENH-3606 was cancelled/superseded by ENH-3623; Implementation Steps and Integration Map were rewritten to the fully-specified Option A design (`ADVISE_GO_NO_GO` StepKind branch in `preparation_policy.py` + one new `run_advise_go_no_go` state), with no remaining dependency on speculative state names.

## Session Log
- `/ll:reconcile-issue` - 2026-09-28T00:28:01 - `c9e5a680-5288-484b-9789-01a430facd71.jsonl`
- `/ll:wire-issue` - 2026-09-28T00:17:35 - `1c278270-e2ba-4e4c-99ea-a1e85ca8ec50.jsonl`
- `/ll:decide-issue` - 2026-09-28T00:01:05 - `6f83d493-add8-470b-8556-2eaf26136968.jsonl`
- `/ll:refine-issue` - 2026-09-27T23:52:45 - `12973c7a-2ea6-47a2-9451-844e0bbe92d3.jsonl`
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
