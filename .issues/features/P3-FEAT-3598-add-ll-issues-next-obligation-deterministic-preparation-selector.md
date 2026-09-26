---
id: FEAT-3598
type: FEAT
title: Add ll-issues next-obligation deterministic preparation selector
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-25'
captured_at: '2026-09-25T18:51:49Z'
blocks:
- ENH-3599
- ENH-3601
- ENH-3604
parent: EPIC-3565
relates_to:
- ENH-3577
- ENH-3602
blocked_by:
- ENH-3602
confidence_score: 85
outcome_confidence: 75
score_complexity: 14
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3598: Add ll-issues next-obligation deterministic preparation selector

## Summary

Add `ll-issues next-obligation ID --format json`: one deterministic selector that resolves
the issue once, runs the format/verify/spec-quality/AC/design/score checks and, when the
outcome score falls short, the decision/proof/artifact diagnosis, and returns the unmet
obligation that `refine-to-ready-issue` would route on. Step B of the ENH-3577
decomposition.

**Scope (review 2026-09-25):** this issue delivers the selector, its CLI, docs, and
unit/parity tests only. Adopting it inside `refine-to-ready-issue` and delegating
`ll-issues next-action` to it are deferred to **ENH-3604** (see "Deferred: Child Adoption
and next-action Delegation"). ENH-3599 and ENH-3601 need only the selector.

## Current Behavior

Readiness predicates are copied across states: `ll-issues show` appears 12× in
`refine-to-ready-issue.yaml` and 37× in `autodev.yaml`; inline Python predicates 7× and 32×.
Individual gates already exist as separate subcommands (`format-check`, `check-design`,
`check-acceptance-criteria`, `check-unresolved-decisions`, `check-gate`, `spike-verdict`,
`check-readiness`), each invoked and interpreted ad hoc.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Child invocation style per state (`refine-to-ready-issue.yaml`): `precheck_format` (:449) and `normalize_structure` (:388) run `format-check --fix --apply` then a heredoc-JSON `directive_gaps` read behind the one-shot `refine-to-ready-format-fallback` counter, fail-open printing 0; `check_verify_verdict` (:527) uses `fragment: harness_exit` routing exit 3 via `on_cannot_judge`; `check_placeholders` (:760) re-implements `placeholder_count` shell-side (`format-check --format json` piped to python `len()`) because no CLI exposes it — a selector that calls `placeholder_count` (issue_parser.py:2375) removes that workaround for free.
- `check_readiness` (:876) / `check_outcome` (:918) / `check_scores_from_file` (:1222) in the child are NOT the `check-readiness` CLI: heredoc `ll-issues show --json` subprocess comparing `int(d.get('confidence') or 0)` against `${context.readiness_threshold}` / `${context.outcome_threshold}` seeded by the runner (BUG-3552 — deliberately not a config re-read). A selector that resolves thresholds via `readiness_status` changes where thresholds come from; override parity must be a conscious decision.
- `cmd_next_action` (`next_action.py:13`) re-sorts `find_issues` output by `(priority_int, -int(id_number))`, reads thresholds via its own raw-JSON read of `commands.confidence_gate` (:37-44 — never consults `enabled`, never uses `readiness_status`), and `refine_cap` comes only from argparse. Its `NEEDS_VERIFY` means "session log lacks /ll:verify-issues", not the verify verdict — the fixture divergence Behavior Parity anticipates.
- Budget counters interpose between each red gate and its repair state (`check_refine_limit`, `check_gate_refine_limit`, `check_hedge_refine_limit`, `check_reconcile_limit`, `check_hedge_attempts`, `check_decide_attempts`, `check_verify_retries`, `check_proposal_revision_budget`); three share the `refine-to-ready-refine-count` file (BUG-3551). The selector stays stateless; counter states stay.

## Expected Behavior

`ll-issues next-obligation ID --format json` emits
`{issue_id, obligation, sub_reason, reason, evidence, skipped, probe_errors}`.
Deterministic; no LLM calls; no file writes.

### The child's gates form a tree, not a chain

`refine-to-ready-issue.yaml`'s gate graph (verified 2026-09-25) is not linear, so a
plain "first unmet of N wins" selector would change routing. Three places differ:

1. **Passing scores go straight to `done`.** `check_outcome.on_yes = done`. DECISION,
   PROOF and ARTIFACTS are reached only via `check_outcome.on_no`, so the child uses them
   to diagnose a **low outcome**. A readiness failure goes to `check_refine_limit` and
   never reaches them. An issue with passing scores and `decision_needed=true` is `done`
   in the child.
2. **Proposal checks are sub-cases of a non-VALID verify verdict.** A VALID verdict
   (`check_verify_verdict.on_yes`) goes to `check_hedges` and skips
   `check_evidence_unverified`, `check_proposal_unsound` and `check_directive_drift`.
   Those three states read the same `verify_verdict` field, so they are not separate
   later obligations. With a separate `PROPOSAL` enum placed after `VERIFY`, `PROPOSAL`
   could never be returned.
3. **Some gates are soft.** When the hedge budget runs out,
   `check_hedge_attempts.on_no` goes to `check_placeholders` with the hedges still
   present. The format fallback also moves on after its one-shot counter, printing
   `[STRUCT_GAP_REMAINS]` and 0. A stateless selector keeps reporting that same
   obligation, so the caller needs a way to tell it to move past (see `--skip`).

### Obligation model

**Tier 1: pre-score gates, in order; first unmet wins:**

| Obligation | Child state(s) | Predicate (reused function) | `sub_reason` | Probe error |
|---|---|---|---|---|
| `FORMAT` | `precheck_format`, `normalize_structure` | `check_format_gaps(path)` directive gaps non-empty | — | fail-open (skip) |
| `VERIFY` | `check_verify_verdict` + `check_evidence_unverified` / `check_proposal_unsound` / `check_directive_drift` | `verify_verdict` frontmatter ≠ `VALID` | `absent` (child: exit 3 → `on_cannot_judge` → retry), `EVIDENCE_UNVERIFIED`, `PROPOSAL_UNSOUND`, `DIRECTIVE_DRIFT`, `other` | fail-closed (child: `on_error → mark_evidence_absent_infra`) |
| `HEDGES` | `check_hedges` | `count_open_questions_in_sections(content) > 0` | — | fail-open |
| `PLACEHOLDERS` | `check_placeholders` | `placeholder_count(path) > 0` (replaces the shell `len(template_placeholders)` workaround) | — | fail-open |
| `ACCEPTANCE_CRITERIA` | `check_ac_automatable` | `_find_manual_criteria(content)` non-empty | — | fail-open |
| `DESIGN` | `check_design` | `design_gate_failed(check_format_gaps(path))` | — | fail-open |

**Tier 2: scores** (`readiness_status`, checked after `confidence_check` has run):

| Obligation | `sub_reason` | Child routing |
|---|---|---|
| `SCORES` | `absent` (confidence or outcome absent) | inline heredoc coerces absent → 0, so routes like `readiness_below` |
| `SCORES` | `readiness_below` | `check_refine_limit` → `refine_followup` |
| `SCORES` (tier 3 found no explanation) | `outcome_below` | `check_missing_artifacts.on_no` → `breakdown_issue` |
| `NONE` | — | `done` — returned **even when** `decision_needed` / spike flags are set, matching `check_outcome.on_yes` |

Readiness is compared before outcome (`check_readiness` precedes `check_outcome`).
Probe errors fail closed (child: readiness error → `check_scores_from_file`, outcome
error → `diagnose`).

**Tier 3: low-outcome diagnosis.** Runs **only** when readiness passes and outcome is
below threshold. The first match wins:

| Obligation | Child state | Predicate | Probe error |
|---|---|---|---|
| `DECISION` | `check_decision_needed` | `decision_needed` frontmatter == `true` (`check-flag` semantics) | fail-open |
| `PROOF` | `check_spike_needed` | `assess_proof(path, cwd=…)` status ∈ {`absent`, `stale`, `refuted`}; status in `sub_reason` | fail-open |
| `ARTIFACTS` | `check_missing_artifacts` (`on_yes → done`) | `missing_artifacts` == `true`. **Reversed polarity:** the missing artifacts explain the low score, so preparation cannot raise it further and the child ends `done` | fail-open to `SCORES/outcome_below` (child: `on_error → breakdown_issue`) |
| `SCORES` / `outcome_below` | `check_missing_artifacts.on_no` → `breakdown_issue` | none of the above explains the shortfall | — |

### Decisions recorded (review 2026-09-25)

- **Thresholds.** Add `--readiness-threshold N` / `--outcome-threshold N` flags. They feed
  `readiness_status(..., readiness_override=, outcome_override=)`. Loop callers pass
  `${context.readiness_threshold}` / `${context.outcome_threshold}`, which keeps BUG-3552
  parity (the seeded value, not a config re-read). With no flags, the selector uses
  `readiness_status`'s defaults (85/65, which already equal the seeder's fallback).
- **Waiver.** By default `outcome_gate_waived` is **not** honoured, matching the child's
  inline `check_outcome`. `--honor-waiver` mirrors `check-readiness --honor-waiver`: a
  waived outcome shortfall counts as met.
- **Soft gates: `--skip OBLIGATION` (repeatable).** A skipped obligation is treated as met
  and listed in `skipped`. The caller's budget state decides what to tolerate; the
  selector stays stateless. This covers exhausted hedge attempts, the used format
  fallback, and callers that want the child's "`spike_attempted` means don't respawn"
  behaviour (`--skip PROOF`).
- **PROOF delegates to `assess_proof`, not the child's inline predicate.** This keeps
  ENH-3602's single owner of proof semantics. **Known departure from parity:**
  - `check_spike_needed` fires only when `spike_needed=='true' and spike_attempted!='true'`,
    and it also spends the `spike-runs-<ID>` budget.
  - `assess_proof` also reports `absent` for `spike_attempted=true` without
    `spike_completed`. Through `_spike_status` it also raises proof for a
    `structured_proof` gate verdict, which folds `check-gate` (ENH-3575) in; the child does
    not run `check-gate` today.
  - The parity test uses fixtures where the two agree: `spike_needed=true`, no
    `spike_attempted`, no structured gate. The divergences get their own unit tests.
    Record this in the `PROOF` docstring.
- **Probe errors.**
  - An unresolvable ID, or a probe error on a fail-closed obligation (`VERIFY`,
    `SCORES`), exits 2 with the error on stderr; "could not assess" is a read error.
  - A probe error on a fail-open obligation is recorded in `probe_errors`, and that
    obligation counts as met.
  - Resolve the ID once in `select_next_obligation` and pass the path/content down. Don't
    rely on each probe's not-found code (`cmd_format_check` returns 1, not 2).
- **Output formats: `--format {text,json,token}`.** `token` prints only
  `OBLIGATION[:sub_reason]` (e.g. `VERIFY:PROPOSAL_UNSOUND`, `SCORES:outcome_below`,
  `NONE`) so an FSM `route:` table can match it with no `jq` or `python`. That table works
  like `route_spike_verdict`.
- **Per-run state stays out.** Wiring and refine counts (`refine-to-ready-wire-done`,
  `refine-to-ready-refine-count`), hedge/decide/spike attempt counters and the format
  fallback counter all belong to the caller.
- **Stale verify verdicts.** The child runs `clear_verify_verdict` before every verify, so
  outside a child run `VERIFY` reflects the *last* persisted verdict, which may be from an
  earlier run. Say so in the CLI docs.

### Relationship to `ll-issues next-action`

`ll-issues next-action` (`little_loops.cli.issues.next_action`) is a **cross-issue** queue
selector that emits `NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>`.
`next-obligation` is **per-issue**. Their checks differ on each token:

- format: `is_formatted` (which honours the `/ll:format-issue` session-log shortcut) vs
  `check_format_gaps`
- verify: session-log presence vs the persisted verdict
- the order of the checks

The decision "parity wins over unification" makes a full delegation little more than
sharing threshold defaults. This issue leaves `next-action` **unchanged**. Delegation, or
a single shared threshold-resolution helper, moves to the follow-up.

## Use Case

A loop state (or a developer) needs to know what an issue still lacks before it is
implementation-ready. Today each state re-derives that with its own `ll-issues show` +
inline Python; with this command it runs `ll-issues next-obligation ENH-123 --format json`
and routes on `obligation`.

## Proposed Solution

- `select_next_obligation(config, issue_id, *, skip=(), readiness_override=None,
  outcome_override=None, honor_waiver=False) -> ObligationResult`. It implements the
  three-tier model in Expected Behavior by composing existing functions:
  - `check_format_gaps` / `design_gate_failed`
  - `count_open_questions_in_sections`
  - `placeholder_count`
  - `_find_manual_criteria`
  - `readiness_status`
  - `assess_proof`

  Reuse them; don't reimplement them. The ID is resolved once and the path/content passed
  down. Composed functions that re-read the file (`readiness_status`, `assess_proof`,
  `placeholder_count`) may do so; "read once" means resolve once, not read the bytes once.
- The `verify_verdict` comparison lives inline in `cmd_check_verify_verdict` and can't be
  imported. Extract it into a small pure helper in `check_verify_verdict.py` that returns
  the verdict class, and have both `cmd_check_verify_verdict` and the selector call it. That
  way the predicate is not duplicated. `test_ll_issues_check_verify_verdict.py` must pass
  unchanged.
- PROOF delegates to `little_loops.learning_tests.assess_proof` (ENH-3602, done) with
  `attempts_used=None` (standalone caller). Keep the import function-local.
- `cmd_next_obligation(config, args) -> int` is the subcommand wrapper, with flags
  `--format {text,json,token}`, `--skip` (repeatable, choices = obligation names),
  `--readiness-threshold`, `--outcome-threshold` and `--honor-waiver`. Exit 0 on any
  successful assessment (including `NONE`). Exit 2 on an unresolvable ID or a fail-closed
  probe error.
- The selector only chooses which repair runs next. Research, wiring, decisions and
  reconciliation stay separate skills.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- The GATE→PROOF fold is already inside the delegate: `assess.py`'s `_spike_status` (:130) adds the `spike` key when a spike flag is set OR `resolve_gate_verdict(...)` returns `structured_proof` — so delegating PROOF to `assess_proof` folds the gate signal without a separate gate check in the selector. The parity caveat stands: the child does not run `check-gate` today, so this remains an added check outside the "reproduce the child's sequence" claim.
- Compose the function, not the subprocess — precedent: `cmd_run_record_write` calls `readiness_status(...)` directly ("resolved in-process rather than via a subprocess", `run_record.py:180-192`); `cmd_check_design` composes `check_format_gaps` + `design_gate_failed` (`check_design.py:31-40`); fabricating an `argparse.Namespace` to invoke a sibling cmd in-process is also done (`format_check.py:133-147`). Exit-code-only cmd bodies hold their predicates in module bodies — `_find_manual_criteria(content)` is importable though private-named (`check_acceptance_criteria.py:57`); `cmd_check_verify_verdict` has no importable predicate (frontmatter compare is inline in the cmd body, `check_verify_verdict.py:72-146`).

## Integration Map

> **Scope note (review 2026-09-25):** this issue is narrowed to the selector. Wiring-pass
> entries below about **rewriting the child loop or delegating `next-action`** belong to
> the deferred follow-up. They are kept here as its research so it isn't lost. That
> covers:
> - `refine-to-ready-issue.yaml`, `refine-to-ready.js` and `next_action.py`
> - autodev / issue-refinement / recursive-refine blast radius, `refine_status.py`
> - `LOOPS_REFERENCE.md`, CLI.md state-name prose, `DEFERRAL_CODES.md`, `verify-issues.md`,
>   `loops/README.md`
> - `test_builtin_loops.py` routing/MR11 pins, `loop_interpolation_baseline.json`,
>   `test_run_record.py`, `test_format_probe_routing.py`, `test_next_action.py` fixture
>   enrichment, the `test_issue_parser.py` `next_action:30` anchor
> - the `$${...}` escaping sweep
>
> This issue must leave all of those files and tests **untouched and passing**.

### Files to Modify (this issue)
- `scripts/little_loops/cli/issues/__init__.py`: lazy import, parser registration, the
  hand-written epilog entry (`:138-184`), and the dispatch line
- `scripts/little_loops/cli/issues/next_obligation.py` (new):
  `Obligation`, `ObligationResult`, `select_next_obligation`, `cmd_next_obligation`,
  `add_next_obligation_parser`
- `scripts/little_loops/cli/issues/check_verify_verdict.py`: extract the pure verdict
  classifier (behaviour unchanged)
- `docs/reference/CLI.md`: new `#### ll-issues next-obligation` section and a
  quick-reference line
- `docs/reference/API.md`: subcommand-table row next to `next-action` (`:4639`), and
  `assess_proof` consumer list
- `scripts/tests/test_wiring_reference_docs.py`: `DOC_STRINGS_PRESENT` needles for the new
  docs

### Files to Modify (deferred to ENH-3604; recorded, not in scope)
- `scripts/little_loops/cli/issues/next_action.py` (per-issue check delegates to the selector; output unchanged)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local mirror of the loop)

### Behavior Parity (deferred follow-up: applies when `next-action` delegates)

`next_action.py`'s per-issue checks delegate to `select_next_obligation`. Parity to keep:

- Output tokens `NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>` / `ALL_DONE` and
  exit codes (1 = work remains, 0 = all done) are unchanged.
- Map: `FORMAT` → `NEEDS_FORMAT`, `VERIFY` → `NEEDS_VERIFY`, `SCORES` (absent) →
  `NEEDS_SCORE`, and below-threshold scores under `--refine-cap` → `NEEDS_REFINE`.
  Obligations that `next-action` does not report today (`VERIFY` proposal sub-reasons,
  `HEDGES`, `PLACEHOLDERS`, `ACCEPTANCE_CRITERIA`, `DESIGN`, `DECISION`, `PROOF`, ...)
  keep today's behaviour and are not surfaced as new tokens.
- `NEEDS_VERIFY` currently means "`/ll:verify-issues` absent from the session log", while
  `VERIFY` checks the verify verdict. If those semantics differ on a fixture, keep
  `next-action`'s current rule and record the difference here. Parity wins over
  unification.

### Dependent Files (Callers/Importers)
_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/loops/issue-refinement.yaml`, `scripts/little_loops/loops/recursive-refine.yaml`, `scripts/little_loops/loops/lib/cli.yaml` (fragment `ll_issues_next`, `lib/cli.yaml:40`) — consume `next-action` output tokens and exit codes; the contract is unchanged by this issue, so no edit expected, but they are the parity blast radius [Agent 1 finding]
- `scripts/little_loops/cli/issues/next_action.py:37` — `cmd_next_action()` re-implements threshold config reading separately from `fsm/context_seed.py::seed_confidence_thresholds` (`cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py` call the seeder); the delegation must keep both paths consistent [Agent 2 finding]
- `scripts/tests/test_fsm_fragments.py:913` — `test_ll_issues_next_defined()` asserts the `ll_issues_next` fragment action string [Agent 1 finding]
- `scripts/tests/test_issue_refinement_broke_down.py:39` — `test_alias_passes_next_action_ordering()` asserts issue-refinement binds `order: next-action` [Agent 1 finding]
- `scripts/tests/test_issue_parser.py:1626` — expectation table pins a `next_action:30` line anchor into `cmd_next_action`; a refactor that moves the function invalidates the entry [Agent 1 finding]
_Wiring pass added by `/ll:wire-issue` — 2026-09-26 (second pass):_
- `scripts/little_loops/loops/autodev.yaml` — embeds the refine-to-ready-issue sub-loop (`refine_current`, ~:534; delegation notes at :93/:185/:513); rewriting the child's states changes autodev behavior even though adoption there is out of scope (ENH-3599/ENH-3601) [Agent 1 finding]
- `scripts/little_loops/loops/issue-refinement.yaml:5` and `scripts/little_loops/loops/recursive-refine.yaml:229` — additional sites in known files: both delegate each issue INTO the sub-loop, so their blast radius is the child's internals, not just next-action tokens [Agent 1 finding]
- `scripts/little_loops/cli/issues/refine_status.py:372-373` — `cmd_refine_status` independently mirrors next-action's predicate inputs (`is_formatted` + `session_command_counts` refine count); extracting the selector is the seam to keep the copies consistent [Agent 2 finding]
- `scripts/little_loops/learning_tests/assess.py:154-156` — imports `resolve_gate_verdict` from `cli.issues.check_gate` function-level; a module-level `cli.issues` → `learning_tests` import in `next_obligation.py` inverts that edge — keep the new import function-local [Agent 2 finding]

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4637` — ll-issues subcommand table needs a `next-obligation` row next to the `next-action` row [Agent 1 finding]
- `docs/reference/CLI.md:1763` — add a `#### ll-issues next-obligation` section following the `next-action` section pattern (flags table + `**FSM loop use**` attribution), plus a line in the quick-reference examples block (~:2013) [Agent 2 finding]
_Wiring pass added by `/ll:wire-issue` — 2026-09-26 (second pass):_
- `docs/guides/LOOPS_REFERENCE.md` — the entire refine-to-ready gate-chain narrative goes stale when named predicate states collapse to dispatch: loop-table row (~:82), claim-verification gate chain (:144), three-stage threshold check + timeout recovery (~:148-154), typed run record (:158), ASCII diagrams naming `check_*` states (~:1050-1184), fragment table rows (~:3582-3583) [Agent 1/2 finding]
- `docs/reference/CLI.md` — additional state-name prose beyond the new section: check-flag "which gate states consume which flag" (~:2269-2274), run-record "called by every terminal-bearing state" (~:2383-2410), `--proposal-unsound`/`--directive-drift` flag prose (~:2433-2434), check-readiness FSM-loop-use note (~:2872) [Agent 1 finding]
- `docs/reference/API.md` — `### assess_proof` section (~:7559) and Public Functions rows (~:7472-7473) document its consumer set; next-obligation PROOF becomes a new consumer — extend the list [Agent 2 finding]
- `docs/reference/DEFERRAL_CODES.md:22-23` — `spike_inconclusive`/`proposal_unsound` rows name the `record_*` states as their source [Agent 1 finding]
- `commands/verify-issues.md:302-343` — persisted-verdict contract names `check_verify_verdict`/`check_proposal_unsound`; host mirrors (`.gemini`, `.kimi-code`, `.qwen`) follow via `ll-adapt` [Agent 1 finding]
- `scripts/little_loops/loops/README.md:29,31` — package-shipped loop catalog rows describe the child's gate sequence ("format → refine → wire → confidence-check") [Agent 1 finding]

### Tests
_This issue (a new test module `test_ll_issues_next_obligation.py` under `scripts/tests/`, on the
`test_ll_issues_check_gate.py` template):_
- A unit test for each obligation and each `sub_reason`. Also ordering tests within
  tier 1 (two unmet → the earlier one wins).
- **Tier tests:**
  - scores pass + `decision_needed=true` → `NONE`
  - readiness below + `decision_needed=true` → `SCORES/readiness_below`, not `DECISION`
  - outcome below + `decision_needed=true` → `DECISION`
  - outcome below + `missing_artifacts=true` → `ARTIFACTS`
  - outcome below with nothing to explain it → `SCORES/outcome_below`
- VERIFY sub-reasons: absent / `EVIDENCE_UNVERIFIED` / `PROPOSAL_UNSOUND` /
  `DIRECTIVE_DRIFT`; VALID moves on to `HEDGES`.
- `--skip`: a skipped obligation moves on to the next and is listed in `skipped`.
  `--skip HEDGES` still returns `PLACEHOLDERS`.
- Thresholds/waiver: the override flags change the verdict, and `--honor-waiver` turns
  `outcome_below` into met.
- **Probe errors:** a fail-open error goes into `probe_errors` and assessment continues.
  A fail-closed error, or an unresolvable ID, exits 2. `next_obligation.py` is not covered
  by the `check_*.py` family glob, so write that test explicitly.
- PROOF divergence tests: `spike_attempted=true` without `spike_completed` → `PROOF/absent`,
  and a structured `proof` gate → `PROOF`. Each is documented as a known departure.
- **Ordering parity test:**
  - Fixtures are built inline (`_write_issue` pattern) and each fails exactly one child
    gate.
  - Assert that the selector's token matches the child state reached. Derive that state by
    walking the child YAML's `on_yes` / `on_no` edges from `check_verify_verdict`, not from
    a hand-written list. The YAML is the source of truth.
- `--format token` / `json` / `text` output shape; help registration
  (`test_ll_issues_check_verify_verdict.py:317` pattern).
- **Must pass unchanged:**
  - `test_spike_verdict_routing.py`, `test_format_probe_routing.py`,
    `test_arm_proposal_revision.py`, `test_ll_issues_check_verify_verdict.py`
    (proves the verdict-classifier extraction is behaviour-neutral)
  - `test_check_readiness.py`, `test_next_action.py`, `test_run_record.py`,
    `test_builtin_loops.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` (TestRefineToReadyIssueSubLoop) — routing-table tests for every state the selector dispatch replaces: `test_check_verify_verdict_state_routing()` (~:1586), `test_check_hedges_state_routing()` (~:1613), `test_check_design_state_routing()` (~:1762), `test_check_decision_needed_routes_through_decide_attempts()` (~:1998), `test_precheck_format_and_fallback_routing()` (~:2123), `test_check_missing_artifacts_on_no_routes_to_breakdown_issue()` (~:2877), the spike cluster (~:3254-3319) and the decision-mid-refine/wire cluster (~:3412-3510) [Agent 3 finding]
- `scripts/tests/test_format_probe_routing.py:34` — module parametrize loads `refine-to-ready-issue.yaml` `["states"]["precheck_format"]["action"]`; KeyError if `precheck_format` is deleted rather than kept as an action behind the dispatcher [Agent 3 finding]
- `scripts/tests/test_spike_verdict_routing.py:66` — `test_refine_to_ready_routing_table()` asserts the child's spike/decision route table; `test_resolve_issue_does_not_reset_spike_counter()` (~:153) pins `resolve_issue` counter behavior [Agent 3 finding]
- `scripts/tests/test_ll_issues_check_verify_verdict.py:317` — `TestCliRegistration::test_subcommand_in_help()` is the registration-check pattern to copy for `next-obligation` [Agent 3 finding]
- `scripts/tests/data/loop_interpolation_baseline.json:744` — `check_outcome` baseline entry goes stale if the state is deleted rather than converted; `TestInterpSweepBaseline::test_completeness_guard` fails in both directions [Agent 3 finding]
- `scripts/tests/test_arm_proposal_revision.py` — direct `cmd_*` + `argparse.Namespace` call pattern for the new `cmd_next_obligation` unit tests [Agent 3 finding]
_Wiring pass added by `/ll:wire-issue` — 2026-09-26 (second pass):_
- `scripts/tests/test_run_record.py` — the heaviest child structural gate, missing from the first pass: loads the real YAML (:24), pins `DONE_PATH_GATES` = `check_outcome`/`check_scores_from_file`/`check_missing_artifacts` (:39), asserts RC-guard byte-order inside their actions (`test_done_path_gate_guards_on_rc`, :511), executes state actions under bash (`TestTerminalExecution`, :558-673), and `test_ready_iff_check_passed_would_pass` (:463) pins run-record `ready` ≡ `check-readiness --honor-waiver` — the selector's waiver/absence stance must match `readiness_status()` or this diverges [Agent 1/2/3 finding — will likely break]
- `scripts/tests/data/loop_interpolation_baseline.json` — refine-to-ready carries THREE baselined entries (`check_outcome`, `check_readiness`, `check_scores_from_file`), not only `check_outcome`; `TestInterpSweepBaseline::test_completeness_guard` (`test_builtin_loops.py:20630`) fails in both directions [Agent 2/3 finding]
- `scripts/tests/test_builtin_loops.py` — additional pins beyond the first pass's list: `check_readiness.on_error == check_scores_from_file` + `check_scores_from_file` existence/route tests (:1528-1560), `MR11_MARKER_ALLOWLIST` (:21088; refine tuples ~:21180-21218 — rewritten states must carry their `# ll-lint: mr11-ok(...)` markers or the allowlist changes in lockstep, and stale markers fail too), `test_context_fallbacks_match_selector_defaults` (:3350 — asserts seeded 85/65 equals the next-action fallback; move the defaults verbatim into the selector) [Agent 2/3 finding]
- `scripts/tests/test_format_probe_routing.py:34` — parametrize covers BOTH `normalize_structure` and `precheck_format` and executes their actions; deleting either state KeyErrors the module [Agent 3 finding]
- `scripts/tests/test_next_action.py` — the full `NEEDS_*`/`ALL_DONE` token/exit-code regression net (the delegation parity gate), plus fixture risk: `_make_issue` builds minimal issues, so once next-action delegates, `test_needs_score`/`test_needs_refine` fixtures trip earlier obligations (VERIFY/SPEC_QUALITY) and must be enriched to pass every preceding gate [Agent 3 finding]
- `scripts/tests/test_ll_issues_check_gate.py` — canonical new-subcommand test template (ENH-3575): parametrized verdict/exit-code table (:140 — the model for the obligation ordering-parity test), JSON output (:148), exit-2 (:154), help registration (:157), `_run_state_proc`/`_stub_env` fail-closed YAML-state routing (:165/:196) [Agent 3 finding]
- `scripts/tests/test_check_family_not_found_exit_code.py` — exit-2 family test globs `cli/issues/check_*.py` (:33); `next_obligation.py` is NOT auto-covered — the unresolvable-ID path needs its own exit-2 test [Agent 3 finding]
- Corpus gates re-validating the edited child: `test_builtin_loop_interpolation.py:100` (bare `${...}` must be `$${...}`), `test_fsm_fragments.py::test_builtin_loops_load_after_migration` (:993), MR-14 sweep `test_fsm_schema.py:1943` [Agent 2/3 finding]
- No per-gate fixture corpus exists under `scripts/tests/fixtures/` (157 files across 17 subdirs, none failing exactly one child gate) — the ordering-parity test must build per-obligation fixtures inline (`_write_issue` helper pattern, `test_run_record.py:90`; per-gate frontmatter keys visible in the child's own gate calls) [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Existing predicates are mostly embedded in `cmd_*` bodies, not importable functions, so "reuse, don't reimplement" requires the selector to share them without duplicating: `cmd_check_verify_verdict` (`cli/issues/check_verify_verdict.py`) reads `verify_verdict` frontmatter inline (VALID → 0, absent → 3, `PROPOSAL_UNSOUND`/`DIRECTIVE_DRIFT`/`EVIDENCE_UNVERIFIED` are distinct probe modes); `cmd_check_acceptance_criteria` wraps `_find_manual_criteria(content)`; `cmd_check_design` is `design_gate_failed(check_format_gaps(path))` (`issue_parser.py`); `check_gate.py` exposes `resolve_gate_verdict(fm, text, spike_proven)`; `check_readiness.py` exposes `readiness_status(config, issue_id, ...) -> ReadinessStatus | None` (has `confidence_absent`/`outcome_absent`, `meets_readiness`, `meets_outcome_or_waived`); `check_open_questions.py` and `check_flag.py` are CLI-only.
- Predicates the child evaluates without any `ll-issues` subcommand: placeholders (`check_placeholders` counts `template_placeholders` from `format-check --format json`; `placeholder_count()` at `issue_parser.py:2375` has no CLI), spike need (`check_spike_needed`: `spike_needed == 'true' and spike_attempted != 'true'` via `show --json`), and hedges (`check-open-questions`, backed by `count_open_questions_in_sections`, `issue_parser.py:3702`).
- `ll-issues check-gate` is **not invoked** by `refine-to-ready-issue.yaml` (its only `check_gate*` matches are `check_gate_refine_limit`, a shared refine-budget state). The `GATE`→`PROOF` fold therefore adds a check the child does not run today; it cannot be part of the "must reproduce the child's sequence" parity claim.
- `check_spike_needed` and every retry/limit state (`check_hedge_attempts`, `check_refine_limit`, `check_gate_refine_limit`, `check_decide_attempts`, `spike-runs-<ID>`) carry per-run `${context.run_dir}` counters. The selector is stateless and per-issue, so it can report "obligation is unmet" but not "budget for retrying it is spent"; routing states that consume budget must stay.
- `confidence_check` is an LLM skill state that *produces* the scores the SCORES obligation reads; the selector can replace `check_readiness`/`check_outcome` predicates, not the scoring state.
- `next_action.py` has no per-issue helper today: `cmd_next_action` inlines `is_formatted` → `"/ll:verify-issues" in session_commands` → score absence → refine-count vs threshold inside its loop over `find_issues(...)`. Its `NEEDS_FORMAT` uses `is_formatted` (honors the `/ll:format-issue` session-log shortcut) whereas `FORMAT` should use `check_format_gaps` (which deliberately does not) — a fixture-level divergence Behavior Parity already anticipates.
- **Updated:** an earlier pass recorded `assess_proof` as not yet landed. ENH-3602 is done (`710aac2e1`, `4cfd7c379`), and `assess_proof` is at
  `learning_tests/assess.py:166`.
- Subcommands are registered in `cli/issues/__init__.py` two ways: `add_*_parser(subs)` helpers (e.g. `add_check_gate_parser`, `add_check_verify_verdict_parser`, called near `:786-789`) and inline parser blocks (`next-action` at `:666`, dispatch at `:1079`). Also add the entry to the help epilog list (`:153`).
- Tests present: `test_next_action.py`, `test_spike_verdict_routing.py`, `test_format_probe_routing.py`, `test_arm_proposal_revision.py`, `test_ll_issues_check_verify_verdict.py`, `test_check_readiness.py` (all under `scripts/tests/`).

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- `readiness_status` has two production dependents this map omitted: `issue_manager.py:819-821` calls `readiness_status(config, info.issue_id)` directly, and `run_record.py:180` (`cmd_run_record_write`) resolves it in-process. A signature change for the selector ripples into both, plus ~15 monkeypatch sites in `scripts/tests/test_issue_manager.py:5827-6225`.
- `fsm/executor.py:1156/:1166` also calls `seed_confidence_thresholds` — a fourth seeder call site beyond the three listed (`cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py`); `next-action`'s independent threshold read must stay consistent with all four.
- `loops/lib/cli.yaml` carries a second next-action fragment besides `ll_issues_next` (:40): `ll_issues_next_issue` (:50) — both consume the unchanged output-token contract.
- API.md anchor drift: the ll-issues subcommand-table `next-action` row sits at `docs/reference/API.md:4639`, not :4637 as cited above; the `next-obligation` row goes adjacent to it.
- `assess_proof` exists (ENH-3602, committed and done): `learning_tests/assess.py:166` defines it, re-exported at `learning_tests/__init__.py:175-183`, already consumed in-process by `learning_tests/gate.py:285-294` and `cli/learning_tests.py:64-87`, with suite `scripts/tests/test_learning_tests_assess.py`. The earlier "not yet landed" finding no longer applies, and the `blocked_by: ENH-3602` edge is resolved (done).
- New-subcommand docs are string-pinned by `scripts/tests/test_wiring_reference_docs.py` DOC_STRINGS_PRESENT (run-record pattern at :256-260): CLI.md heading, stdout token, and both API.md rows must be added as pinned needles, not just prose.

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_builtin_loops.py` — TestRefineToReadyIssueSubLoop routing tests for the replaced predicate states
- Update `scripts/tests/data/loop_interpolation_baseline.json` — delete/convert the `check_outcome` entry in the same commit (`test_completeness_guard` ratchet)
- Update `docs/reference/API.md` — add `next-obligation` row to the ll-issues subcommand table
- Update `docs/reference/CLI.md` — new `#### ll-issues next-obligation` section + quick-reference example line
- Check `scripts/tests/test_issue_parser.py` `next_action:30` expectation-table anchor if `cmd_next_action` moves within `next_action.py`
_Wiring pass added by `/ll:wire-issue` — 2026-09-26 (second pass):_

- Update `scripts/tests/test_run_record.py` — re-pin done-path gates, RC-guard ordering, and terminal execution after the state rewrite
- Update `scripts/tests/data/loop_interpolation_baseline.json` — regenerate/remove ALL THREE refine entries (`check_outcome`, `check_readiness`, `check_scores_from_file`), not just `check_outcome`; baseline any new dispatch state that interpolates `context.run_dir`
- Update `scripts/tests/test_builtin_loops.py` — carry `# ll-lint: mr11-ok(...)` markers with rewritten state text and move `MR11_MARKER_ALLOWLIST` refine tuples in the same commit
- Escape bash `${...}` as `$${...}` in any new dispatch-state action (`test_builtin_loop_interpolation.py` bare-reference sweep)
- Enrich `scripts/tests/test_next_action.py` fixtures so they pass every obligation preceding NEEDS_SCORE/NEEDS_REFINE once next-action delegates
- Keep the `learning_tests` import in `next_obligation.py` function-local (import-edge inversion vs `assess.py:154`)
- Add an explicit unresolvable-ID exit-2 test for `next-obligation` (the `check_*.py` family glob does not cover it)
- Update gate-chain prose: `docs/guides/LOOPS_REFERENCE.md`, `docs/reference/CLI.md` state-name sections, `docs/reference/DEFERRAL_CODES.md`, `commands/verify-issues.md` (+ host mirrors via `ll-adapt`), `docs/reference/API.md` assess_proof consumer list, `scripts/little_loops/loops/README.md` catalog rows

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - new subcommand composing existing checks under a three-tier model; child adoption deferred
- **Risk**: Low - additive CLI; no loop YAML or `next-action` changes (the one refactor, the verify-verdict classifier extraction, is covered by its existing test suite)
- **Breaking Change**: No

## Program Design

### Types

- `Obligation: Enum` — `FORMAT`, `VERIFY`, `HEDGES`, `PLACEHOLDERS`, `ACCEPTANCE_CRITERIA`, `DESIGN`, `SCORES`, `DECISION`, `PROOF`, `ARTIFACTS`, `NONE`, declared in tier/check order. Its docstring records the three tiers and the known PROOF departure from parity (the check-gate fold and `spike_attempted`). `PROPOSAL` is gone (now `VERIFY` sub-reasons), and `SPEC_QUALITY` is split so that `--skip HEDGES` still enforces `PLACEHOLDERS`.
- `ObligationResult: dataclass` — `issue_id: str`, `obligation: Obligation`, `sub_reason: str | None`, `reason: str`, `evidence: list[str]`, `skipped: list[str]`, `probe_errors: list[str]`; `to_dict()` for JSON; `token()` → `OBLIGATION[:sub_reason]`

### Signatures

- `select_next_obligation(config: BRConfig, issue_id: str, *, skip: Iterable[Obligation] = (), readiness_override: int | None = None, outcome_override: int | None = None, honor_waiver: bool = False) -> ObligationResult | None` — resolves the issue once and returns the obligation under the three-tier model; None means the ID can't be resolved
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — CLI wrapper emitting `ObligationResult.to_dict()` (json), `token()` (token) or a summary line (text); exit 0 on assessment, 2 on an unresolvable ID or a fail-closed probe error
- `add_next_obligation_parser(subs) -> argparse.ArgumentParser` — Style A registration helper
- A pure verdict classifier extracted from `cmd_check_verify_verdict` (the name is the implementer's choice) — returns the verdict class that both the CLI and the selector use

### Call Path

`cmd_next_obligation` -> `select_next_obligation` -> `check_format_gaps` / `readiness_status` / `assess_proof`

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Each obligation needs a defined `evidence` element type (`list[str]`) and a mapping from the underlying probe's non-pass exit codes; probes that return exit 2 (unresolvable issue) must surface as a read error from `cmd_next_obligation`, not as an unmet obligation.
- `Obligation` order must be asserted against the child's edge list (`on_yes` chain from `precheck_format` through `check_missing_artifacts`) by the parity test, since the enum is declared in check order and the YAML is the source of truth for the order.
- Decision Rules: N/A — no new decision logic beyond composing existing gates in the child's order (SCORES before DECISION/PROOF).

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- Exact importable surfaces: `resolve_gate_verdict(frontmatter: dict, text: str, spike_proven: bool) -> tuple[GateVerdict, list[GateSpec]]` (`check_gate.py:110`, pure/stdlib-only); `readiness_status(config, issue_id, *, default_readiness=85, default_outcome=65, readiness_override=None, outcome_override=None) -> ReadinessStatus | None` (`check_readiness.py:74`; None = unresolvable ID; exposes `confidence_absent`/`outcome_absent`, `meets_readiness`, `meets_outcome_or_waived`); `locate_unresolved_decisions(content, *, include_approximate_tiers=False) -> list[DecisionGroup]` (`issue_parser.py:3516`, `DecisionGroup.to_dict()`); `locate_unresolved_options(content) -> tuple[int, str | None]` (`issue_parser.py:3085`); `count_open_questions_in_sections(content) -> int` (`issue_parser.py:3702`); `placeholder_count(issue_path, templates_dir=None) -> int` (`issue_parser.py:2375`, fails open); `assess_proof(issue_path: Path, *, attempts_used=None, stale_after_days=None, cwd=None, targets=None) -> ProofVerdict` (`learning_tests/assess.py:165` — takes a resolved path, not an ID; pass `cwd=` for config lookup; `ProofStatus = Literal["proven","stale","refuted","absent","not_required"]`, worst-status-wins via `_SEVERITY` proven < stale < absent < refuted; `_MAX_ATTEMPTS = 2`).
- Contested convention — ordered closed sets: the Types block above declares `Obligation: Enum`, but this codebase's ordered closed sets are module-level tuples paired with Literal aliases (`AXES`, `issues/research_triage.py:59-85`; `WRITERS`/`LEGACY_CLASSES`, `run_record.py:31-50`; `_IN_FORCE`, `check_gate.py:29`). Zero ordered `list(Enum)` iteration exists in `scripts/little_loops/`, and all 14 enums are plain Enum — no StrEnum (`issue_lifecycle.py:126-128` records the check). Both styles are viable; the implementer picks, and the parity test pins whichever order results.
- Exit-code conventions: house contract 0 positive / 1 genuine negative / 2 unresolvable / 3 abstention, documented at `check_unresolved_decisions.py:49-55`. The "exit 0 always on a successful assessment, non-zero only on read errors" shape has precedent in `research-triage` (`research_triage.py:50-63` — which returns 1, not 2, for unresolvable IDs); named exit constants precedent at `spike_verdict.py:26-28`. Deviation to absorb: `cmd_format_check` returns 1, not 2, for not-found (`format_check.py:630-631`) — resolve the ID once in `select_next_obligation` rather than trusting each probe's not-found code.
- Absent scores are a distinct signal: `cmd_check_readiness` exits 3 `SCORES_ABSENT` before any comparison (BUG-3588); explicit zero coerces to 0 with `confidence_absent=False`. Waivers: `outcome_gate_waived` is honored only under `--honor-waiver` (check-readiness) and always in run-record — NOT consulted by next-action or the child's inline heredocs; the selector's waiver stance is a decision to make knowingly.
- First-match-wins has a documented precedent: `outcome_from_legacy_class` (`run_record.py:140-169`) with a numbered rule list in its docstring. The parity test should assert the Obligation order against the child's on_yes chain in the YAML — the YAML is the source of truth for the order.
- cmd_*/registration conventions: signature `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` with BRConfig imported only under `if TYPE_CHECKING:` and heavy imports function-local; module docstring headline `"""ll-issues next-obligation: <desc> (ISSUE-ID)."""`; four registration touchpoints (lazy import, parser registration, hand-written epilog entry `cli/issues/__init__.py:138-184` — no completeness test covers it, dispatch line). Style A `add_next_obligation_parser(subs)` helper in the subcommand module (every subcommand since ~ENH-2971) vs Style B inline block (next-action itself, `:665-696`) — contested, trend is Style A. JSON via `print_json` (`cli/output.py:227`, indent=2); `--format {text,json}` choices style matches format-check (`format_check.py:93-99`).

## Scope Boundaries

- Deterministic only: no LLM calls, no file writes.
- No loop YAML is edited. Adoption in `refine-to-ready-issue` is deferred to the
  follow-up; adoption in `autodev.yaml` is ENH-3599 / ENH-3601.
- `ll-issues next-action` is not changed (delegation deferred).

## Acceptance Criteria

- [ ] `ll-issues next-obligation` returns the documented JSON / token / text for every obligation and `sub_reason`
- [ ] The selector calls existing check functions. The verify-verdict comparison is extracted, not copied, and there is no duplicated predicate logic
- [ ] The three-tier model holds: passing scores → `NONE` regardless of decision/spike flags; DECISION/PROOF/ARTIFACTS are returned only when outcome is below threshold
- [ ] Tier-1 order and routing match the child's edges (a parity test that walks the YAML)
- [ ] `--skip`, `--readiness-threshold`, `--outcome-threshold` and `--honor-waiver` behave as documented
- [ ] Unresolvable ID and fail-closed probe errors exit 2; fail-open probe errors appear in `probe_errors`
- [ ] Known PROOF departures from parity are documented in the docstring and CLI.md and pinned by tests
- [ ] CLI.md / API.md updated and pinned in `test_wiring_reference_docs.py`
- [ ] The listed existing test files pass unchanged

## Deferred: Child Adoption and next-action Delegation

Split out of this issue during the 2026-09-25 review and captured as **ENH-3604**
(which FEAT-3598 blocks). ENH-3604 is the authoritative home for this work; the
constraints below are kept here for context:

- **FORMAT can't be adopted.**
  - `precheck_format` and `normalize_structure` run `format-check --fix --apply`, which
    writes, and bump the `refine-to-ready-format-fallback` counter. The selector is
    read-only.
  - `test_format_probe_routing.py` parametrizes over both states and executes their
    actions.
  - Keep both states.
- **DECISION gains nothing.** `check_decision_needed` / `check_decision_mid_*` are already
  one-line `check-flag decision_needed` calls.
- **Adoption targets that pay off:**
  - the pre-score chain `check_verify_verdict` → `check_evidence_unverified` /
    `check_proposal_unsound` / `check_directive_drift` → `check_hedges` →
    `check_placeholders` (which has its own inline Python) → `check_ac_automatable` →
    `check_design`
  - the inline heredoc predicates in `check_readiness` / `check_outcome` /
    `check_scores_from_file`
- **Keep the done-path gate states.**
  - `check_outcome` and `check_missing_artifacts` write the run record when they pass, and
    `test_run_record.py` pins them as `DONE_PATH_GATES` (including RC-guard byte order).
  - Swap only their predicates, and keep `test_ready_iff_check_passed_would_pass`
    (`run-record ready` ≡ `check-readiness --honor-waiver`) consistent with the selector's
    waiver flag.
- **Dispatch mechanics.**
  - Use one `route:` state over `ll-issues next-obligation ID --format token --skip ...`,
    like `route_spike_verdict`.
  - It routes to the existing `check_*_limit` / `check_*_attempts` **budget states**, not
    straight to repair states.
  - Budget states that tolerate a soft gate pass `--skip` next time, via a per-run skip
    file under `${context.run_dir}`.
- **`next-action`.** Either delegate with the Behavior Parity map above (enriching the
  `test_next_action.py` fixtures), or reduce it to one shared threshold-resolution helper
  that `next-action`, the seeder (`fsm/context_seed.py`) and the selector all use. The
  second option is recommended because the token semantics differ.
- Every item in the Integration Map scope note applies.

## Verification Notes

Verdict at time of check: **NEEDS_UPDATE** (corrections below applied in the same
pass, so the issue as it now reads is up to date — this section is a record of
what was wrong and fixed, not an outstanding action item)

_Checked by `/ll:verify-issues --auto` on 2026-09-26 (graph: provider=codegraph
freshness=fresh)._

- Corrected stale `cli/issues/__init__.py` anchors: next-action inline parser
  `:661` → `:666`, dispatch `:1073` → `:1079`, `add_*_parser` helper calls
  `:781-784` → `:786-789`, epilog entry `:149` → `:153` (epilog block `:138-184`
  itself was accurate).
- Corrected `TestInterpSweepBaseline::test_completeness_guard` anchor
  `test_builtin_loops.py:21025` → `:20630` (both occurrences).
- Corrected the fixtures-corpus count: `scripts/tests/fixtures/` holds 157 files
  across 17 subdirs, not 38 (the "none failing exactly one child gate" substance
  stands).
- The Deferred section's "to be captured as a follow-up" was already superseded
  on disk by an ENH-3604 reference — confirmed ENH-3604 exists with
  `blocked_by: FEAT-3598`; no edit needed.
- Everything else verified against the working tree: every symbol anchor
  (`cmd_next_action` next_action.py:13; `placeholder_count` issue_parser.py:2375;
  `count_open_questions_in_sections` :3702; `locate_unresolved_decisions` :3516;
  `locate_unresolved_options` :3085; `_find_manual_criteria`
  check_acceptance_criteria.py:57; `readiness_status` check_readiness.py:74;
  `resolve_gate_verdict` check_gate.py:110; `assess_proof` assess.py:166;
  `_spike_status` :130; `WRITERS`/`LEGACY_CLASSES` run_record.py:40/:43;
  `outcome_from_legacy_class` :140; `print_json` output.py:227), every
  refine-to-ready-issue.yaml state anchor (:388/:449/:527/:760/:876/:918/:1222),
  the 12×/37× `ll-issues show` counts, `check-gate` not invoked by the child,
  the inline `check_readiness` heredoc semantics (BUG-3552 seeding,
  `int(d.get('confidence') or 0)`), the shell-side placeholder count in
  `check_placeholders`, doc anchors (API.md:4639/:7559/:7472-7473;
  CLI.md:1763/:2013; DEFERRAL_CODES.md:22-23; LOOPS_REFERENCE.md:82/:144/:158/
  :3582-3583; loops/README.md:29/:31), test anchors (test_run_record.py:24/:39/
  :90/:463/:558; test_ll_issues_check_verify_verdict.py:317;
  test_format_probe_routing.py:34; test_spike_verdict_routing.py:66;
  loop_interpolation_baseline.json:744/:753/:762 — all three entries;
  MR11_MARKER_ALLOWLIST :21088; test clusters ~:3254/:3412), the enum claims
  (zero `StrEnum`/`list(Enum)` in `scripts/little_loops/`;
  issue_lifecycle.py:126-128), and the ENH-3602 commits `710aac2e1`/`4cfd7c379`
  (both exist; `710aac2e1` touched `assess.py`).
- Dependencies: `blocked_by ENH-3602` satisfied (done — informational);
  backlinks confirmed in ENH-3599/ENH-3601/ENH-3604; no cycles.
- Proposal-consequence check (ENH-3250): no findings — every composed function
  exists with the documented signature; the `check_verify_verdict.py` extraction
  is feasible (predicate is inline at :72-146); no fixture invalidation; ACs
  cover the Integration Map's in-scope points.
- Evidence-quote check (BUG-3282): clean (`ll-verify-evidence`, 0 findings).
- Decisions: no active required rules (`ll-issues decisions list` empty).

## Parent Issue

Decomposed from ENH-3577: Consolidate autodev issue preparation into a single controller loop

## Status

**Open** | Created: 2026-09-25 | Priority: P3

---

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`, applied 2026-09-25): The `PROOF` obligation delegates to `little_loops.learning_tests.assess_proof`. ENH-3602 is now a `blocked_by` edge, so no follow-up swap is needed.

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25_

**Readiness Score**: 60/100 → STOP — ADDRESS GAPS
**Outcome Confidence**: 71/100 → MODERATE

### Gaps to Address
- ~~blocked_by ENH-3602 (open)~~ **Resolved:** ENH-3602 is done and `assess_proof` exists.
- Advisory claim gap (`stale_cli_flag`): `ll-issues next-obligation` does not exist yet. It is this issue's own deliverable, so implementing it closes the gap.
- ~~GATE→PROOF fold vs parity~~ **Resolved (review 2026-09-25):** PROOF delegates to `assess_proof`. The check-gate fold and the `spike_attempted` difference are recorded as known departures from parity, excluded from the parity fixtures and pinned by their own tests.
- ~~**Scores are stale.** The 60/71 scores predate the 2026-09-25 rescope; re-run `/ll:confidence-check`.~~ **Resolved:** re-scored 2026-09-26 (block below).

_Added by `/ll:confidence-check` on 2026-09-26_

**Readiness Score**: 85/100 → PROCEED WITH CAUTION (meets `readiness_threshold: 85`)
**Outcome Confidence**: 75/100 → MODERATE (≥ `outcome_threshold: 65`)

### Concerns
- Criterion 4 is capped at 10 by the advisory `stale_cli_flag` gap (`ll-issues next-obligation` does not resolve) — expected, since the subcommand is this issue's own deliverable; the gap closes on implementation.
- The verify-verdict classifier extraction must stay behavior-neutral: `test_ll_issues_check_verify_verdict.py` passing unchanged is the proof; drift there invalidates the ordering-parity claim.
- `stale_file_ref` on `.claude/workflows/refine-to-ready.js` is a git-tracking artifact (file exists locally, gitignored) — deferred ENH-3604 scope, no action here.

## Session Log
- `/ll:confidence-check` - 2026-09-26T02:19:56 - `af650890-b749-4228-9253-ada2de60ad41.jsonl`
- `/ll:verify-issues` - 2026-09-26T01:58:13 - `299955d0-6fe7-4f63-8308-3ba4f99868ac.jsonl`
- `/ll:wire-issue` - 2026-09-26T00:53:30 - `3a641232-a30c-4668-9080-a790d40c330b.jsonl`
- `/ll:refine-issue` - 2026-09-26T00:21:08 - `29654aaa-6763-4b73-821b-31710e26b186.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:34 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:46:48 - `2b4a714f-91fd-41aa-b2ac-63b11e2476ce.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:42:22 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:20 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
