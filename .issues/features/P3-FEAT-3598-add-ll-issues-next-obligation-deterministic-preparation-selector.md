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
parent: EPIC-3565
relates_to:
- ENH-3577
- ENH-3602
blocked_by:
- ENH-3602
confidence_score: 60
outcome_confidence: 71
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 18
score_change_surface: 18
---

# FEAT-3598: Add ll-issues next-obligation deterministic preparation selector

## Summary

Add `ll-issues next-obligation ID --format json`: one deterministic selector that reads the
issue once, runs the format/design/AC/decision/proof/score checks, and returns the first
unmet obligation. Adopt it inside `refine-to-ready-issue` first, replacing its inline
predicates. Step B of the ENH-3577 decomposition.

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
`{issue_id, obligation, reason, evidence}`. Deterministic; no LLM calls. Obligations are
checked in a fixed order, and the first unmet one wins.

### Obligation set and order must match the child

The order must reproduce `refine-to-ready-issue`'s current gate sequence. Otherwise
"first unmet wins" reorders routing and the behavioral test set cannot pass unchanged.
The child's sequence, from `resolve_issue` onward, is:

format (`precheck_format`) → verify verdict (`check_verify_verdict`) → proposal soundness
(`check_proposal_unsound`, `check_directive_drift`) → hedges/placeholders (`check_hedges`,
`check_placeholders`) → AC (`check_ac_automatable`) → design (`check_design`) → **scores**
(`confidence_check`, `check_readiness`, `check_outcome`) → **decision**
(`check_decision_needed`) → **proof** (`check_spike_needed`) → artifacts
(`check_missing_artifacts`).

Starting enum, to be confirmed state by state during implementation:
`FORMAT`, `VERIFY`, `PROPOSAL`, `SPEC_QUALITY` (hedges/placeholders), `ACCEPTANCE_CRITERIA`,
`DESIGN`, `SCORES`, `DECISION`, `PROOF`, `ARTIFACTS`, `NONE`.

- SCORES comes **before** DECISION/PROOF. `confidence-check` is what sets
  `decision_needed` and applies the unproven-mechanism cap (BUG-3591), so the decision and
  proof checks read state that scoring produces.
- `GATE` (`ll-issues check-gate`, ENH-3575) folds into PROOF (`structured_proof` /
  `structured_open`). Record that in the enum docstring.
- Wiring and refine counts are per-run state (`refine-to-ready-wire-done`,
  `refine-to-ready-refine-count`), not issue state. They stay out of the selector.

### Relationship to `ll-issues next-action`

`ll-issues next-action` (`little_loops.cli.issues.next_action`) already exists. It is a
**cross-issue** queue selector that emits `NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>`
using its own `is_formatted` / session-log / threshold checks. `next-obligation` is
**per-issue**. To avoid two readiness orderings that drift apart, `next-action`'s
per-issue check should call `select_next_obligation` and map the result to its existing
output tokens. Its output format and exit codes stay unchanged, because
`issue-refinement.yaml`, `recursive-refine.yaml` and `lib/cli.yaml` consume them.

## Use Case

A loop state (or a developer) needs to know what an issue still lacks before it is
implementation-ready. Today each state re-derives that with its own `ll-issues show` +
inline Python; with this command it runs `ll-issues next-obligation ENH-123 --format json`
and routes on `obligation`.

## Proposed Solution

- `select_next_obligation(config: BRConfig, issue_id: str) -> ObligationResult` composing the
  existing check functions (`check_format_gaps` in `little_loops.issue_parser`, and the
  functions behind `check-verify-verdict`, `check-design`, `check-acceptance-criteria`,
  `check-unresolved-decisions`, `check-gate`, `spike-verdict`, `check-readiness`). Reuse
  them; do not reimplement.
- PROOF delegates to `little_loops.learning_tests.assess_proof` (ENH-3602, now a
  `blocked_by` edge), not to a separate staleness/refutation derivation.
- `cmd_next_obligation(config, args) -> int` subcommand wrapper; exit 0 always on a
  successful assessment, non-zero only on read errors.
- Replace the child's per-gate predicate states with a single dispatch on `obligation`
  where the mapping is 1:1; leave any state whose semantics differ, and note it.
- Keep distinct skills for research, wiring, decisions and reconciliation — the selector
  only chooses which runs next.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- The GATE→PROOF fold is already inside the delegate: `assess.py`'s `_spike_status` (:130) adds the `spike` key when a spike flag is set OR `resolve_gate_verdict(...)` returns `structured_proof` — so delegating PROOF to `assess_proof` folds the gate signal without a separate gate check in the selector. The parity caveat stands: the child does not run `check-gate` today, so this remains an added check outside the "reproduce the child's sequence" claim.
- Compose the function, not the subprocess — precedent: `cmd_run_record_write` calls `readiness_status(...)` directly ("resolved in-process rather than via a subprocess", `run_record.py:180-192`); `cmd_check_design` composes `check_format_gaps` + `design_gate_failed` (`check_design.py:31-40`); fabricating an `argparse.Namespace` to invoke a sibling cmd in-process is also done (`format_check.py:133-147`). Exit-code-only cmd bodies hold their predicates in module bodies — `_find_manual_criteria(content)` is importable though private-named (`check_acceptance_criteria.py:57`); `cmd_check_verify_verdict` has no importable predicate (frontmatter compare is inline in the cmd body, `check_verify_verdict.py:72-146`).

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/issues/__init__.py` (register subcommand)
- `scripts/little_loops/cli/issues/next_obligation.py` (new)
- `scripts/little_loops/cli/issues/next_action.py` (per-issue check delegates to the selector; output unchanged)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml`
- `.claude/workflows/refine-to-ready.js` (gitignored, machine-local mirror of the loop)
- `docs/reference/CLI.md`

### Behavior Parity

`next_action.py`'s per-issue checks delegate to `select_next_obligation`. Parity to keep:

- Output tokens `NEEDS_FORMAT|NEEDS_VERIFY|NEEDS_SCORE|NEEDS_REFINE <id>` / `ALL_DONE` and
  exit codes (1 = work remains, 0 = all done) are unchanged.
- Map: `FORMAT` → `NEEDS_FORMAT`, `VERIFY` → `NEEDS_VERIFY`, `SCORES` (absent) →
  `NEEDS_SCORE`, and below-threshold scores under `--refine-cap` → `NEEDS_REFINE`.
  Obligations that `next-action` does not report today (`PROPOSAL`, `DESIGN`,
  `DECISION`, `PROOF`, ...) keep today's behavior and are not surfaced as new tokens.
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

### Documentation
_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:4637` — ll-issues subcommand table needs a `next-obligation` row next to the `next-action` row [Agent 1 finding]
- `docs/reference/CLI.md:1763` — add a `#### ll-issues next-obligation` section following the `next-action` section pattern (flags table + `**FSM loop use**` attribution), plus a line in the quick-reference examples block (~:2013) [Agent 2 finding]

### Tests
- Unit tests per obligation, plus ordering tests (two unmet → first wins)
- Ordering parity test: for fixtures that each fail exactly one child gate, the selector's first obligation matches the child state that would fire first
- `ll-issues next-action` output unchanged on existing fixtures
- Behavioral set must pass unchanged: `test_spike_verdict_routing.py`,
  `test_format_probe_routing.py`, `test_arm_proposal_revision.py`,
  `test_ll_issues_check_verify_verdict.py`, `test_check_readiness.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_builtin_loops.py` (TestRefineToReadyIssueSubLoop) — routing-table tests for every state the selector dispatch replaces: `test_check_verify_verdict_state_routing()` (~:1586), `test_check_hedges_state_routing()` (~:1613), `test_check_design_state_routing()` (~:1762), `test_check_decision_needed_routes_through_decide_attempts()` (~:1998), `test_precheck_format_and_fallback_routing()` (~:2123), `test_check_missing_artifacts_on_no_routes_to_breakdown_issue()` (~:2877), the spike cluster (~:3254-3319) and the decision-mid-refine/wire cluster (~:3412-3510) [Agent 3 finding]
- `scripts/tests/test_format_probe_routing.py:34` — module parametrize loads `refine-to-ready-issue.yaml` `["states"]["precheck_format"]["action"]`; KeyError if `precheck_format` is deleted rather than kept as an action behind the dispatcher [Agent 3 finding]
- `scripts/tests/test_spike_verdict_routing.py:66` — `test_refine_to_ready_routing_table()` asserts the child's spike/decision route table; `test_resolve_issue_does_not_reset_spike_counter()` (~:153) pins `resolve_issue` counter behavior [Agent 3 finding]
- `scripts/tests/test_ll_issues_check_verify_verdict.py:317` — `TestCliRegistration::test_subcommand_in_help()` is the registration-check pattern to copy for `next-obligation` [Agent 3 finding]
- `scripts/tests/data/loop_interpolation_baseline.json:744` — `check_outcome` baseline entry goes stale if the state is deleted rather than converted; `TestInterpSweepBaseline::test_completeness_guard` fails in both directions [Agent 3 finding]
- `scripts/tests/test_arm_proposal_revision.py` — direct `cmd_*` + `argparse.Namespace` call pattern for the new `cmd_next_obligation` unit tests [Agent 3 finding]

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Existing predicates are mostly embedded in `cmd_*` bodies, not importable functions, so "reuse, don't reimplement" requires the selector to share them without duplicating: `cmd_check_verify_verdict` (`cli/issues/check_verify_verdict.py`) reads `verify_verdict` frontmatter inline (VALID → 0, absent → 3, `PROPOSAL_UNSOUND`/`DIRECTIVE_DRIFT`/`EVIDENCE_UNVERIFIED` are distinct probe modes); `cmd_check_acceptance_criteria` wraps `_find_manual_criteria(content)`; `cmd_check_design` is `design_gate_failed(check_format_gaps(path))` (`issue_parser.py`); `check_gate.py` exposes `resolve_gate_verdict(fm, text, spike_proven)`; `check_readiness.py` exposes `readiness_status(config, issue_id, ...) -> ReadinessStatus | None` (has `confidence_absent`/`outcome_absent`, `meets_readiness`, `meets_outcome_or_waived`); `check_open_questions.py` and `check_flag.py` are CLI-only.
- Predicates the child evaluates without any `ll-issues` subcommand: placeholders (`check_placeholders` counts `template_placeholders` from `format-check --format json`; `placeholder_count()` at `issue_parser.py:2375` has no CLI), spike need (`check_spike_needed`: `spike_needed == 'true' and spike_attempted != 'true'` via `show --json`), and hedges (`check-open-questions`, backed by `count_open_questions_in_sections`, `issue_parser.py:3702`).
- `ll-issues check-gate` is **not invoked** by `refine-to-ready-issue.yaml` (its only `check_gate*` matches are `check_gate_refine_limit`, a shared refine-budget state). The `GATE`→`PROOF` fold therefore adds a check the child does not run today; it cannot be part of the "must reproduce the child's sequence" parity claim.
- `check_spike_needed` and every retry/limit state (`check_hedge_attempts`, `check_refine_limit`, `check_gate_refine_limit`, `check_decide_attempts`, `spike-runs-<ID>`) carry per-run `${context.run_dir}` counters. The selector is stateless and per-issue, so it can report "obligation is unmet" but not "budget for retrying it is spent"; routing states that consume budget must stay.
- `confidence_check` is an LLM skill state that *produces* the scores the SCORES obligation reads; the selector can replace `check_readiness`/`check_outcome` predicates, not the scoring state.
- `next_action.py` has no per-issue helper today: `cmd_next_action` inlines `is_formatted` → `"/ll:verify-issues" in session_commands` → score absence → refine-count vs threshold inside its loop over `find_issues(...)`. Its `NEEDS_FORMAT` uses `is_formatted` (honors the `/ll:format-issue` session-log shortcut) whereas `FORMAT` should use `check_format_gaps` (which deliberately does not) — a fixture-level divergence Behavior Parity already anticipates.
- `assess_proof` (`little_loops.learning_tests`) does not exist yet; `learning_tests/` currently has only `extractor.py`, `gate.py`, `import_scan.py`, `release_gate.py`. PROOF cannot be implemented until ENH-3602 lands (already a `blocked_by` edge).
- Subcommands are registered in `cli/issues/__init__.py` two ways: `add_*_parser(subs)` helpers (e.g. `add_check_gate_parser`, `add_check_verify_verdict_parser`, called near `:781-784`) and inline parser blocks (`next-action` at `:661`, dispatch at `:1073`). Also add the entry to the help epilog list (`:149`).
- Tests present: `test_next_action.py`, `test_spike_verdict_routing.py`, `test_format_probe_routing.py`, `test_arm_proposal_revision.py`, `test_ll_issues_check_verify_verdict.py`, `test_check_readiness.py` (all under `scripts/tests/`).

_Added by `/ll:refine-issue` — 2026-09-26 — based on codebase analysis:_

- `readiness_status` has two production dependents this map omitted: `issue_manager.py:819-821` calls `readiness_status(config, info.issue_id)` directly, and `run_record.py:180` (`cmd_run_record_write`) resolves it in-process. A signature change for the selector ripples into both, plus ~15 monkeypatch sites in `scripts/tests/test_issue_manager.py:5827-6225`.
- `fsm/executor.py:1156/:1166` also calls `seed_confidence_thresholds` — a fourth seeder call site beyond the three listed (`cli/loop/run.py`, `cli/loop/lifecycle.py`, `cli/loop/info.py`); `next-action`'s independent threshold read must stay consistent with all four.
- `loops/lib/cli.yaml` carries a second next-action fragment besides `ll_issues_next` (:40): `ll_issues_next_issue` (:50) — both consume the unchanged output-token contract.
- API.md anchor drift: the ll-issues subcommand-table `next-action` row sits at `docs/reference/API.md:4639`, not :4637 as cited above; the `next-obligation` row goes adjacent to it.
- `assess_proof` now exists in the working tree (ENH-3602 deliverable, uncommitted): `learning_tests/assess.py:165` defines it, re-exported at `learning_tests/__init__.py:175-183`, already consumed in-process by `learning_tests/gate.py:285-294` and `cli/learning_tests.py:64-87`, with suite `scripts/tests/test_learning_tests_assess.py`. The earlier finding in this block ("does not exist yet") is superseded by working-tree state; the Blocked by ENH-3602 edge stays until it lands.
- New-subcommand docs are string-pinned by `scripts/tests/test_wiring_reference_docs.py` DOC_STRINGS_PRESENT (run-record pattern at :256-260): CLI.md heading, stdout token, and both API.md rows must be added as pinned needles, not just prose.

## Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Update `scripts/tests/test_builtin_loops.py` — TestRefineToReadyIssueSubLoop routing tests for the replaced predicate states
- Update `scripts/tests/data/loop_interpolation_baseline.json` — delete/convert the `check_outcome` entry in the same commit (`test_completeness_guard` ratchet)
- Update `docs/reference/API.md` — add `next-obligation` row to the ll-issues subcommand table
- Update `docs/reference/CLI.md` — new `#### ll-issues next-obligation` section + quick-reference example line
- Check `scripts/tests/test_issue_parser.py` `next_action:30` expectation-table anchor if `cmd_next_action` moves within `next_action.py`

## Impact

- **Priority**: P3 - child of ENH-3577 (EPIC-3565 consolidation)
- **Effort**: Medium - new subcommand composing existing checks, plus child predicate replacement
- **Risk**: Medium - replaces predicate states in refine-to-ready-issue
- **Breaking Change**: No

## Program Design

### Types

- `Obligation: Enum` — `FORMAT`, `VERIFY`, `PROPOSAL`, `SPEC_QUALITY`, `ACCEPTANCE_CRITERIA`, `DESIGN`, `SCORES`, `DECISION`, `PROOF`, `ARTIFACTS`, `NONE`, declared in check order
- `ObligationResult: dataclass` — `issue_id`, `obligation: Obligation`, `reason: str`, `evidence: list[str]`

### Signatures

- `select_next_obligation(config: BRConfig, issue_id: str) -> ObligationResult` — reads the issue once and returns the first unmet obligation with its reason and evidence
- `cmd_next_obligation(config: BRConfig, args: argparse.Namespace) -> int` — CLI wrapper emitting `{issue_id, obligation, reason, evidence}`

### Call Path

`cmd_next_obligation` -> `select_next_obligation` -> `check_format_gaps`

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
- Adoption in `autodev.yaml` is out of scope (ENH-3599 / ENH-3601).

## Acceptance Criteria

- [ ] `ll-issues next-obligation` returns the documented JSON for every obligation
- [ ] The selector calls existing check functions; no duplicated predicate logic
- [ ] Obligation order matches the child's gate sequence (parity test)
- [ ] `ll-issues next-action` reuses the selector's per-issue checks, with unchanged output
- [ ] `refine-to-ready-issue` uses the selector for at least the format/design/AC/decision gates
- [ ] Behavioral test set passes unchanged

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
- blocked_by ENH-3602 (open) — `assess_proof` does not exist yet, so the PROOF obligation cannot be implemented until it lands. Wait for ENH-3602 (or descope PROOF from the first cut).
- Advisory claim gap (`stale_cli_flag`): `ll-issues next-obligation` does not exist — forward-looking reference to this issue's own deliverable; no action beyond implementing it.
- Expected Behavior says `GATE` folds into `PROOF`, but Codebase Research found `check-gate` is not invoked by `refine-to-ready-issue.yaml` today, so the fold adds a check outside the parity claim. Resolve the directive/research tension before implementing.

## Session Log
- `/ll:refine-issue` - 2026-09-26T00:21:08 - `29654aaa-6763-4b73-821b-31710e26b186.jsonl`
- `/ll:confidence-check` - 2026-09-25T21:32:34 - `672e0da1-840e-4b60-a432-7b20e9ebbd01.jsonl`
- `/ll:wire-issue` - 2026-09-25T20:46:48 - `2b4a714f-91fd-41aa-b2ac-63b11e2476ce.jsonl`
- `/ll:refine-issue` - 2026-09-25T19:42:22 - `2f63920a-850e-4ac5-bf34-e7b8eb47e2e0.jsonl`
- `/ll:audit-issue-conflicts` - 2026-09-25T19:09:20 - `dcfdf31c-be65-47ce-9e6e-5b65d63239f2.jsonl`
