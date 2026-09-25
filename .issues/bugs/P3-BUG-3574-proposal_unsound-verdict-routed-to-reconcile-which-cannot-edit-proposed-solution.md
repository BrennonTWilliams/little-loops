---
id: BUG-3574
type: BUG
title: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution
priority: P3
status: done
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
completed_at: '2026-09-25T15:23:18Z'
parent: EPIC-3565
blocks:
- ENH-3577
confidence_score: 100
outcome_confidence: 78
score_complexity: 10
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 18
---

# BUG-3574: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution

## Summary

In `refine-to-ready-issue.yaml`, `check_proposal_unsound` (ENH-3250) routes a
`verify_verdict: PROPOSAL_UNSOUND` to `check_reconcile_limit` → `/ll:reconcile-issue`. Its
comment describes the failure as the Proposed Solution itself contradicting the code. But
reconcile has a binding contract (`commands/reconcile-issue.md`, "Contract"). That contract
rewrites only
`## Implementation Steps`, `## Acceptance Criteria`, `## Integration Map` and, conditionally,
`## Scope Boundaries`. It does not rewrite `## Proposed Solution` or decision rationale.
Reconcile can fix drifted directives, but not a refuted chosen design.

## Current Behavior

A genuinely unsound proposal is sent to a remedy that cannot edit it. It burns the reconcile
budget and eventually defers.

## Expected Behavior

Directive drift goes to reconcile. A refuted selected proposal goes to a bounded design
revision (re-open the decision via `resolve-decision`), then wire and verify the revised
approach. An unsound proposal with no eligible alternative — including a single proposal with
no enumerable `### Option` blocks, and a revised option that is itself refuted once the
revision budget is spent — stops with a distinct `proposal_unsound` deferral reason.

## Steps to Reproduce

1. Take an issue whose Proposed Solution, implemented as written, contradicts the code it names
2. Run refine-to-ready-issue; verify-issues persists `verify_verdict: PROPOSAL_UNSOUND`
3. Observe the route to `/ll:reconcile-issue`, which leaves `## Proposed Solution` untouched per its contract; the verdict recurs until the reconcile budget is spent

## Motivation

Unsound proposals are exactly the cases where implementation would do the most damage. Routing them to a remedy that cannot touch the proposal guarantees a wasted budget and eventual deferral.

## Root Cause

- **One verdict, two remedies.** `commands/verify-issues.md` check B6 (ENH-3250) assigns
  `PROPOSAL_UNSOUND` for any consequence finding. Some B6 findings are fixable by editing
  directive sections alone — "AC coverage of identified integration points" (an AC gap) and
  often "test-fixture invalidation" (an Implementation Steps gap). Others refute the chosen
  mechanism itself (e.g. "exception-handler compatibility" when the selected design must
  raise through a handler it cannot pass). The verdict does not say which.
- **Reconcile anchors to the proposal.** `commands/reconcile-issue.md` § 3 reads "the
  selected option / decision under `### Decision Rationale`" and makes the directive
  sections describe **that** mechanism. Given a refuted proposal, reconcile re-derives
  directives from the refuted design.
- **The fallback cannot fix it either.** After one reconcile (`check_reconcile_limit`,
  `target: 2` → one attempt per run), the route falls to `check_gate_refine_limit` →
  `/ll:refine-issue`, which is additive and never rewrites `## Proposed Solution` (see the
  BUG-3002 comment on autodev's `refine_for_design`). Only `/ll:decide-issue` changes the
  selected option.
- **No re-open mode.** `/ll:decide-issue` picks among enumerable options. BUG-3592 added the
  refuted-option exclusion (`issue_parser.refuted_option_labels`), but nothing arms it for a
  B6 refutation, so on an already-decided issue decide-issue would either find nothing to
  decide or re-select the same option.
- **A refuted selection still counts as a resolved decision.** `is_group_resolved` treats a
  group as resolved when any member option's span carries a `> **Selected:**` callout, or when
  the section has a `### Decision Rationale` and holds a single group. It does not consult
  `refuted_option_labels`. Verified 2026-09-25 with a probe: Options A/B, `Selected:` on A,
  `### Decision Rationale`, and a refuted marker for A give
  `locate_enumerable_options` → `[('Option A', False), ('Option B', True)]`, but
  `locate_unresolved_decisions` → `[]`. decide-issue applies the exclusion only to
  `unresolved[0]`, and its per-group idempotency rule skips the write, so arming the marker
  alone never re-opens the decision. BUG-3592's spike path avoids this only because the spike
  write-back rebuilds `## Proposed Solution` from scratch.
- **Directive sections go stale after a re-decision.** decide-issue writes only the
  `Selected:` callout, `### Decision Rationale` and the marker's `✅ RESOLVED` suffix. It never
  touches Implementation Steps, Acceptance Criteria or Integration Map, and `/ll:wire-issue`
  only adds to them. After a revision those sections still describe the refuted option.
- **Return route skips verify.** `resolve_decision_pre_breakdown.on_success` →
  `confidence_check`, so a revised selection would be scored without re-running wire and
  verify.

## Proposed Solution

1. **Split the verdict in `/ll:verify-issues --check`** (not in the gate). The alternative —
   `check_proposal_unsound` inspecting which section the evidence cites — parses prose in a
   gate, breaking the convention that gates read a written frontmatter field. Classify by
   **which section must change to fix the finding**, not by B6 sub-check:
   - `DIRECTIVE_DRIFT` — the fix is confined to Implementation Steps / Acceptance Criteria /
     Integration Map; the selected mechanism stands. → reconcile (today's route).
   - `PROPOSAL_UNSOUND` — the selected option / Proposed Solution must change. → decision
     revision.
   - Precedence: `EVIDENCE_UNVERIFIED` > `PROPOSAL_UNSOUND` > `DIRECTIVE_DRIFT` (a refuted
     proposal makes directive drift moot).
   - On `PROPOSAL_UNSOUND`, `--check` also persists a one-line `verify_evidence:` frontmatter
     field (the B6 finding, single line, no newlines). §2.5 must require a **double-quoted
     YAML scalar** with `"` and `\` escaped (e.g. `verify_evidence: "handler at x.py:40 swallows
     it"`). A bare value holding `: `, a leading backtick, `#` or quotes breaks the frontmatter,
     and `check-verify-verdict` then reads the verdict as absent and classes the run `infra`.
     This stays inside § 2.5's existing "persist to frontmatter" carve-out. **`--check` makes no body edits** — its documented
     contract (`commands/verify-issues.md` § 2.5, and the `--check` flag description:
     "without applying changes") is preserved. verify-issues never invents alternatives.

2. **Arm the revision deterministically in a loop state, not in verify-issues.** A new
   `arm-proposal-revision <ID>` subcommand of `ll-issues` (new; modeled on BUG-3593's `rearm-spike`)
   reuses BUG-3592's refuted → `decision_needed` contract:
   - Locate the selected option: `_selected_option_title` over `## Proposed Solution` returns
     the **whole** callout remainder (e.g. `Option A: Raise through handler — simplest`), so
     reduce it with `_option_label()` (→ `option a`). Match that against the
     `_normalize_option_label` form of the `locate_enumerable_options(...)` labels. The marker
     is written with the exact `LocatedOption.label` (`Option A`) so `refuted_option_labels`
     matches it. Only callouts on **eligible** options count: skip a callout whose option is
     already refuted, because after an earlier revision the refuted option's callout may still
     come first physically. Pattern D callouts (`> **Selected:** (x) — …`) carry no
     `Option X` label and fall to `[NO_ALTERNATIVE]`.
   - Evidence: read `verify_evidence` from frontmatter, collapse whitespace, strip newlines.
     When missing or empty, use `B6 finding (no evidence persisted)` so the marker keeps its
     `<label> — …` shape.
   - **Arm** (exit 0, prints `[PROPOSAL_REVISION_ARMED] <ID>`) only when the selected option
     is an enumerable `### Option <X>:` block **and** at least one other option stays
     eligible after marking it refuted. Then set `decision_needed: true` and append an
     `## Open Questions` item in BUG-3592's literal marker shape (parsed by
     `_REFUTED_OPTION_RE`):
     `1. **Refuted option**: Option A — /ll:verify-issues <date>: <verify_evidence>. Which remaining option replaces it?`
   - **No alternative** (exit 1, prints `[NO_ALTERNATIVE] <ID>`, no file change) when there
     are no enumerable option blocks, no `Selected:` callout on an eligible option (including
     a Pattern D callout with no `Option X` label), or no eligible option would remain. This is decided **before** decide-issue runs because decide-issue
     cannot be trusted with it: with `OPTIONS == 0`, auto mode invokes `/ll:refine-issue`
     to deposit options and its Phase 3b Pattern D scan can lock a winner from provisional
     wording (`skills/decide-issue/SKILL.md` Phase 2.5) — the marker label matches no
     located option, `all_refuted` never fires, and the refuted design can be re-selected.
   - Exit 2 on unresolvable ID (matches `rearm-spike`).

3. **Re-open the decided group (parser change) — then BUG-3592's exclusion applies.**
   BUG-3592 alone is not enough (Root Cause: *a refuted selection still counts as a resolved
   decision*). Change `issue_parser.is_group_resolved` (signature unchanged):
   - A `> **Selected:**` callout resolves the group only when it sits in an option that is
     **not** named by `refuted_option_labels(content)`.
   - The section-level `### Decision Rationale` branch does not resolve a group that has a
     refuted member unless an eligible member carries a `Selected:` callout. The rationale
     cannot say which option it chose, so a refuted member means an eligible callout is
     required.
   - Effect: once armed, `locate_unresolved_decisions` returns the group. decide-issue scores
     only the eligible options, adds `Selected:` on the winner, and the group resolves again
     through the eligible callout. The refuted callout and the old rationale stay in place as
     history. They never re-resolve the group or get re-selected.
   - Chosen over having the CLI strip A's callout and rename the rationale heading. The lenient
     `_DECISION_RATIONALE_SECTION_MARKER_RE` (`\b`-bounded) still matches suffixed headings
     such as "(superseded)", and deleting provenance is worse than excluding it. This also
     covers a future spike refutation of an already-selected option.

   With ≥1 eligible
   option, decide-issue selects among them, rewrites `### Decision Rationale`, and marks the
   marker item `✅ RESOLVED`. With none (only reachable if the CLI's eligibility check and
   decide-issue disagree), it emits **`## RESULT: ALL_OPTIONS_REFUTED`**, exits 1, and
   leaves `decision_needed: true` and the marker unresolved — the oracle's failed terminal,
   handled by step 4's failure routing.
   - **Not `NO_ACTIONABLE_DECISIONS`** (corrected 2026-09-24). That exit (decide-issue
     Phase 3b-i) fires only when every `## Open Questions` item is already marked resolved.

4. **Routing in refine-to-ready:**
   - `check_proposal_unsound.on_yes` → new `check_proposal_revision_budget`: a per-issue run-dir
     counter `refine-to-ready-proposal-revisions` (reset to `0` in `resolve_issue`),
     incremented before use, `target: 2` → one revision per run. **Deliberately does not
     route through `check_decide_attempts`**: a decision resolved earlier in the same run
     leaves that counter at 1, which would defer the issue as `decision_unresolved` without
     ever re-deciding — the same trap BUG-3593's `check_spike_budget` bypasses
     (`refine-to-ready-issue.yaml` `check_spike_budget` comment). Budget exhausted (a
     revised option was itself refuted) → `record_proposal_unsound`.
   - `on_yes` → new `arm_proposal_revision` (shell: the new `arm-proposal-revision` subcommand, then
     write the run-dir marker `refine-to-ready-proposal-revision` only on exit 0).
     Exit 0 → `resolve_decision_pre_breakdown`; exit 1 / error → `record_proposal_unsound`.
   - `resolve_decision_pre_breakdown.on_success` → new `check_proposal_revision`: marker
     present → `rm -f` it, then new `reconcile_revision`; absent → `confidence_check` as
     today.
   - New `reconcile_revision`: `/ll:reconcile-issue <ID>` (same shape and pruning profile as
     `reconcile_issue`). It is **not** routed through `check_reconcile_limit`: an earlier
     `DIRECTIVE_DRIFT` or `check_ac_automatable` reconcile in the same run would have spent
     that budget. The revision cycle is already bounded by `check_proposal_revision_budget`.
     Reconcile reads the new `### Decision Rationale` and rewrites Implementation Steps /
     Acceptance Criteria / Integration Map to match the new option (Root Cause: *directive
     sections go stale*). Without this step, verify reads directives for the refuted option.
     It either flags `PROPOSAL_UNSOUND` again, a false `proposal_unsound` deferral because the
     revision budget is spent, or `DIRECTIVE_DRIFT` into a spent reconcile budget and then
     `gate_unmet`. `next` / `on_error` → `wire_issue` (→ `mark_wire_done` →
     `check_decision_mid_wire` → `normalize_structure` → BUG-3571's `clear_verify_verdict` →
     `verify_issue`). **The state consumes the marker** so a later, unrelated
     `check_decision_needed → resolve_decision_pre_breakdown` pass in the same run does not
     re-route to `wire_issue`. `resolve_issue` also `rm -f`s it at init.
   - Failure routing: `resolve_decision_pre_breakdown` failures go
     `check_decide_rate_limited` → (on_no) new `check_proposal_revision_failed`: marker
     present → `record_proposal_unsound`, else `record_decision_unresolved`. Rate-limit
     precedence is unchanged (`check_decide_rate_limited.on_yes` → `mark_rate_limit_infra`
     still fires first).
   - New `record_proposal_unsound`, modeled on BUG-3593's `record_spike_inconclusive`:
     write `proposal_unsound` to `refine-terminal-class`, append the ID to
     `${context.run_dir}/autodev-proposal-unsound.txt`, skip if status already
     done/cancelled, else `ll-issues set-status "$ID" deferred --by automation --reason proposal_unsound || true`,
     then `next: failed`.
   - New `check_directive_drift` inserted at `check_proposal_unsound.on_no`:
     `check-verify-verdict <ID> --directive-drift` (new flag); `on_yes` → `check_reconcile_limit`;
     `on_no` / `on_error` → `check_gate_refine_limit` (today's `check_proposal_unsound.on_no`
     target). Chain order encodes precedence: `check_verify_verdict` →
     `check_evidence_unverified` → `check_proposal_unsound` → `check_directive_drift`.
   - `max_steps`: currently **70** (BUG-3593 raised it from 60). The revision cycle is
     ~16 steps: check_proposal_revision_budget → arm_proposal_revision →
     resolve_decision_pre_breakdown → check_proposal_revision → reconcile_revision →
     wire_issue → mark_wire_done → check_decision_mid_wire → normalize_structure →
     clear_verify_verdict → verify_issue → check_verify_verdict → check_evidence_unverified →
     check_proposal_unsound → check_directive_drift, plus one hop onward. Raise to **≥ 85**
     and update the comment with this count.
   - `circuit.recurrent_window: 6`: its comment budgets the hottest legitimate gate-band
     recurrence at ~4, plus 2 margin. The revision cycle adds one more pass through the gate
     band (`check_evidence_unverified` / `check_proposal_unsound` triples). Recount the worst
     case with one revision. If it exceeds 5, raise the window to 7 and update the comment.
     Otherwise the circuit fires `diagnose` → `classify_terminal` → `quality` partway through
     a legitimate revision.

5. **autodev ledger**: a nested `record_proposal_unsound` exits `failed` without passing
   `classify_terminal`, so autodev's `skip_inflight` must `grep -qxF "$ID"
   autodev-proposal-unsound.txt` and skip the `refine_failed` ledger line, exactly as
   BUG-3593 did for `autodev-spike-inconclusive.txt` (`autodev.yaml` `skip_inflight`).
   Surface the ledger in autodev's finalize summary alongside the spike-inconclusive one.

6. **Legacy values need no migration**: BUG-3571 clears `verify_verdict` before every verify,
   so a persisted `PROPOSAL_UNSOUND` from an earlier run is never read. `ll-issues
   clear-verify-verdict` must also clear `verify_evidence` so a stale finding never reaches a
   later marker. This is a **Python** change: `cmd_clear_verify_verdict` passes the hard-coded
   tuple `("verify_verdict",)` to `remove_frontmatter_keys`. Widen it to
   `("verify_verdict", "verify_evidence")`. The YAML state's action is unchanged.

## Program Design

### Types

- `DIRECTIVE_DRIFT` — new `verify_verdict` value, written by `/ll:verify-issues --check`.
- `verify_evidence` — new single-line frontmatter field, written by `/ll:verify-issues --check` only alongside `verify_verdict: PROPOSAL_UNSOUND`; cleared by `clear_verify_verdict`.
- `DeferReason.PROPOSAL_UNSOUND` — new `issue_lifecycle.DeferReason` member, value `"proposal_unsound"`.

### Signatures

- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; gains a `--directive-drift` query mode (exit 0 when `verify_verdict == DIRECTIVE_DRIFT`, 1 otherwise), mirroring `--proposal-unsound`. Default mode treats `DIRECTIVE_DRIFT` as non-VALID (exit 1).
- `cmd_arm_proposal_revision(config: BRConfig, args: argparse.Namespace) -> int` — new, in `cli/issues/arm_proposal_revision.py` (new file); 0 = armed (marker + `decision_needed`), 1 = no eligible alternative (no file change), 2 = issue not found.
- `add_arm_proposal_revision_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser` — new; registers `arm-proposal-revision`.
- `is_group_resolved(content: str, group: DecisionGroup) -> bool` — existing; behavior change only. A `Selected:` callout on a refuted option does not resolve the group, and the section-level Decision Rationale branch does not resolve a group with a refuted member unless an eligible member carries a callout.
- `cmd_clear_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; also removes `verify_evidence`.

### Call Path

`cmd_arm_proposal_revision` -> `locate_enumerable_options` -> `refuted_option_labels`

`cmd_check_unresolved_decisions` -> `locate_unresolved_decisions` -> `is_group_resolved` -> `refuted_option_labels`

`cmd_check_verify_verdict` -> `parse_frontmatter`

`cmd_clear_verify_verdict` -> `remove_frontmatter_keys`

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — §B6 verdict split by fix location; §C verdict table adds `DIRECTIVE_DRIFT`; § 2.5 frontmatter mapping adds `DIRECTIVE_DRIFT` and `verify_evidence` as a double-quoted YAML scalar (frontmatter only — no body edits in `--check`)
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `--directive-drift` query mode. The default mode already returns 1 for any value other than `VALID`, so `DIRECTIVE_DRIFT` needs only a test there, no code change
- `scripts/little_loops/issue_parser.py` — `is_group_resolved` excludes refuted options (Proposed Solution step 3)
- `scripts/little_loops/cli/issues/clear_verify_verdict.py` — also remove `verify_evidence`
- `scripts/little_loops/cli/issues/arm_proposal_revision.py` (new) — new CLI (see Program Design)
- `scripts/little_loops/cli/issues/__init__.py` — parser registration for both, `_USAGE` / help text
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason.PROPOSAL_UNSOUND = "proposal_unsound"` (the `set-status --reason` argparse `choices` validate against this enum; the shell state's `|| true` would hide a rejection)
- `scripts/little_loops/cli/issues/deferred_triage.py` — `_REASON_RANK["proposal_unsound"] = 3` (same needs-human tier as `decision_unresolved` / `spike_inconclusive`)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `resolve_issue` resets `refine-to-ready-proposal-revisions` and removes `refine-to-ready-proposal-revision`; new states `check_directive_drift`, `check_proposal_revision_budget`, `arm_proposal_revision`, `check_proposal_revision`, `reconcile_revision`, `check_proposal_revision_failed`, `record_proposal_unsound`; `check_proposal_unsound.on_yes`/`on_no` rewired; `resolve_decision_pre_breakdown.on_success` → `check_proposal_revision`; `check_decide_rate_limited.on_no` → `check_proposal_revision_failed`; `max_steps` 70 → ≥ 85 + comment; `circuit.recurrent_window` recount (raise to 7 if the worst case exceeds 5); header comment chain, ENH-3250 comment on `check_proposal_unsound`, and `classify_terminal`'s list of states that bypass it (add `record_proposal_unsound`). Accepted residual, not a change: `record_proposal_unsound` routes straight to `failed` and writes its own class, but an `on_max_steps` fall-through still runs `classify_terminal` and overwrites any class, as it does for every other `record_*` state
- `skills/decide-issue/reference.md` — § Refuted-option handling: say that a `Selected:` callout on a refuted option does not resolve the group, so an already-decided issue re-opens once the marker is armed
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` greps `autodev-proposal-unsound.txt` (mirrors the BUG-3593 `autodev-spike-inconclusive.txt` block); finalize summary surfaces the ledger

### Dependent Files (Callers/Importers)
- `commands/reconcile-issue.md` — unchanged contract; receives only `DIRECTIVE_DRIFT` now
- `skills/decide-issue/SKILL.md` — unchanged; the option exclusion, marker resolution and `ALL_OPTIONS_REFUTED` exit landed in BUG-3592. It sees the re-opened group only because of the `is_group_resolved` change
- `scripts/little_loops/cli/issues/check_unresolved_decisions.py`, `locate_options` CLI — unchanged; both inherit the `is_group_resolved` change through `locate_unresolved_decisions`
- `skills/spike/write-back.md` — unchanged; it rebuilds `## Proposed Solution` and so never relied on the old behavior
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — unchanged; its `failed` terminal on `ALL_OPTIONS_REFUTED` feeds `check_proposal_revision_failed`

### Similar Patterns
- BUG-3592 refuted spike → `decision_needed` + enumerable options + refuted-option marker
- BUG-3593 `check_spike_budget` (bypasses `check_decide_attempts`), `record_spike_inconclusive` + autodev ledger, `ll-issues rearm-spike` (deterministic arming CLI)
- autodev `refine_for_design` (BUG-3002): a dedicated remedy chosen because the default remedy's contract excludes the failing section

### Tests
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — `--directive-drift` query mode class; default mode exits 1 on `DIRECTIVE_DRIFT`
- `scripts/tests/test_arm_proposal_revision.py` (new) — arms with ≥2 options + `Selected:` callout (marker parses via `refuted_option_labels`, `decision_needed: true`, label is the exact `LocatedOption.label` even when the callout reads `Option A: <title> — <rationale>`); **after arming, `locate_unresolved_decisions` returns the group** (the probe case in Root Cause); a second revision identifies the eligible option B as selected, not the earlier-refuted A whose callout comes first; missing `verify_evidence` still yields a well-formed marker; exit 1 and no file change for: no option blocks, no `Selected:` callout, a Pattern D `(x)` callout, selected option is the only eligible one, all others already refuted; exit 2 on unknown ID
- `scripts/tests/test_issue_parser_refuted.py` (BUG-3592 module; `test_issue_parser_unresolved.py` for the regression guard) — `is_group_resolved`: a callout on a refuted option → unresolved; a callout on an eligible option alongside a refuted one → resolved; a section-level Decision Rationale with a refuted member and no eligible callout → unresolved; groups with no refuted marker behave exactly as before (regression guard)
- `scripts/tests/test_ll_issues_check_verify_verdict.py::TestClearVerifyVerdict` — `verify_evidence` removed alongside `verify_verdict`; absent keys are a no-op
- `scripts/tests/test_builtin_loops.py` — routing assertions for every new state and rewired edge (incl. `test_check_verify_verdict_on_no_reaches_check_proposal_unsound`); `check_proposal_revision` consumes the marker and routes marker-present → `reconcile_revision` → `wire_issue`; `reconcile_revision` is not reached through `check_reconcile_limit`; `resolve_issue` resets both run-dir files; `max_steps` value test; stub `ll-issues` on `PATH` running the real state `action`. **Replace** these existing tests, whose asserted edges this issue rewires: `test_resolve_decision_pre_breakdown_on_success_reenters_confidence_check` (~line 2994; the new target is `check_proposal_revision`, and the marker-absent branch keeps the `confidence_check` re-entry) and `test_check_proposal_unsound_on_yes_routes_to_check_reconcile_limit` (~line 3091; the new target is `check_proposal_revision_budget`, and the reconcile route moves to `check_directive_drift.on_yes`)
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes` — add `proposal_unsound`
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — `DIRECTIVE_DRIFT` appears in §C and as `verify_verdict: DIRECTIVE_DRIFT` in §2.5; `--check` still documents no body edits
- autodev `skip_inflight` test: a nested `proposal_unsound` stop is not ledgered as `refine_failed`

### Documentation
- `docs/reference/CLI.md` — `check-verify-verdict --directive-drift` (new flag); `arm-proposal-revision` subcommand (new)
- `docs/guides/LOOPS_REFERENCE.md` — claim-verification gate chain and the proposal-revision cycle
- `docs/reference/DEFERRAL_CODES.md` — `proposal_unsound`
- Host mirrors of `commands/verify-issues.md`: `.gemini/commands/verify-issues.toml`, `.qwen/commands/ll/verify-issues.md` — regenerate with `ll-adapt --host <gemini|qwen> --apply` (gated by `test_host_artifacts_are_not_stale`)

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- `scripts/little_loops/issue_lifecycle.py` — `DeferReason` enum (`DECISION_UNRESOLVED = "decision_unresolved"` at ~line 78) is the registry the `ll-issues set-status --reason` argparse `choices` validate against; a `proposal_unsound` deferral code must be a member or the CLI rejects it, and the shell state's `|| true` hides the rejection
- `scripts/tests/test_set_status_cli.py::test_set_status_deferred_stamps_autodev_reason_codes` (~line 341) — parametrized list of registered reason codes; guards exactly the silent-rejection failure above
- `scripts/tests/test_enh3250_verify_issues_proposal_vs_code.py` — pins that each verdict appears in `commands/verify-issues.md` §C and as `verify_verdict: X` in §2.5; `DIRECTIVE_DRIFT` must satisfy the same contract
- `scripts/tests/test_decide_issue_skill.py` — existing contract test for `skills/decide-issue/SKILL.md`
- Conventions in force: (1) `check-verify-verdict` query modes are mutually exclusive binary probes — exit 0 only when `verify_verdict` equals that value case-insensitively, exit 1 for absent/other/VALID, `NOT_<VERDICT>` on stderr (evidence: `check_verify_verdict.py` `cmd_check_verify_verdict`, `--evidence-unverified` and `--proposal-unsound` branches; tests are one class per flag in `test_ll_issues_check_verify_verdict.py`); (2) gate states in `refine-to-ready-issue.yaml` are `fragment: shell_exit` with `on_yes`/`on_no`/`on_error`, `on_error` failing open to the `on_no` target, chain order encoding precedence (`check_verify_verdict` → `check_evidence_unverified` → `check_proposal_unsound`); (3) each new gate state bumps the `max_steps` value (currently **70** after BUG-3593) and its comment; (4) loop routing tests assert state existence, `fragment`, action flag, and each edge separately in `test_builtin_loops.py`; (5) run-dir markers live under `${context.run_dir}/`, initialized in the init state and tested with `[ -f ... ]`; (6) deferral emit pattern is `record_spike_inconclusive` / `record_decision_unresolved` — write `refine-terminal-class`, append to an autodev ledger file, skip if status already done/cancelled, then `ll-issues set-status "$ID" deferred --by automation --reason <code> || true`; `refine-terminal-class` values today are `gate_unmet`, `infra`, `decision_unresolved`, `spike_inconclusive`, so `proposal_unsound` needs one too
- _Review 2026-09-25 (post-BUG-3593):_ `check_decide_attempts` is shared across every decide path in a run, so routing a refutation through it defers as `decision_unresolved` whenever any earlier decision ran — BUG-3593's `check_spike_budget` bypasses it for this reason. `refuted_option_labels` only affects **located** options, so a marker naming a non-enumerable proposal never makes `all_refuted` fire; decide-issue's `OPTIONS == 0` auto path (deposit via `/ll:refine-issue`, then Pattern D) can then re-select the refuted design. `issue_parser._selected_option_title` reads the `> **Selected:**` callout used to identify the refuted option.
- _Review 2026-09-25 (pre-implementation):_ (1) `is_group_resolved` ignores refuted markers, so an armed, already-decided group stays resolved and decide-issue never re-decides (confirmed by a parser probe) → Proposed Solution step 3 parser change. (2) decide-issue and wire-issue leave directive sections describing the refuted option → unbudgeted `reconcile_revision`. (3) `_selected_option_title` returns the full callout line and picks the first callout → reduce with `_option_label`, eligible options only. (4) `clear_verify_verdict.py` hard-codes the key tuple → Python change. (5) `verify_evidence` must be a quoted YAML scalar. (6) Two existing routing tests pin edges this issue rewires. (7) `max_steps` ≥ 85 and a `recurrent_window` recount.

## Implementation Steps

1. `issue_lifecycle.DeferReason.PROPOSAL_UNSOUND` + `deferred_triage._REASON_RANK` entry
2. `issue_parser.is_group_resolved`: refuted-option exclusion (TDD: write the probe case from Root Cause as a failing test first) + `decide-issue/reference.md` note
3. `clear_verify_verdict.py`: also remove `verify_evidence`
4. `check_verify_verdict.py`: `--directive-drift` query mode (default mode needs a test only)
5. `arm_proposal_revision.py` (new) CLI + registration in `cli/issues/__init__.py`
6. verify-issues: split B6 verdict by fix location; add `DIRECTIVE_DRIFT`; persist `verify_evidence` as a quoted scalar on `PROPOSAL_UNSOUND`; frontmatter-only in `--check`
7. refine-to-ready: `check_directive_drift` → reconcile; `PROPOSAL_UNSOUND` → `check_proposal_revision_budget` → `arm_proposal_revision` → `resolve_decision_pre_breakdown` → `check_proposal_revision` (consume marker) → `reconcile_revision` (unbudgeted) → `wire_issue`; failure → `check_proposal_revision_failed` → `record_proposal_unsound`; `resolve_issue` resets; `max_steps` ≥ 85; `recurrent_window` recount
8. autodev `skip_inflight` + finalize ledger handling
9. Tests for each route and CLI (replace the two rewired-edge tests); docs and host mirrors

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Medium — changes the verify-issues verdict taxonomy, adds a revision cycle to refine-to-ready, and changes `is_group_resolved`, which is shared by `check-unresolved-decisions`, `locate-options` and decide-issue. The parser change is inert for any issue without a refuted-option marker; guard that with a regression test. decide-issue's skill text is unchanged.
- **Sequencing**: BUG-3571 (verdict clearing) and BUG-3592 (refuted → `decision_needed` contract and decide-issue exclusion) are done. BUG-3593 (done in code) touches the same `refine-to-ready-issue.yaml` band, `DeferReason`, `deferred_triage.py` and autodev `skip_inflight` — rebase onto it. The BUG-3595 close-out (automated-run artifact for BUG-3593) is in the working tree but not committed as of 2026-09-25 (BUG-3595 deleted, BUG-3593 modified). Commit it before starting so the two don't collide.

## Acceptance Criteria

- [x] A refuted Proposed Solution is never routed only to reconcile
- [x] Directive-only drift (`DIRECTIVE_DRIFT`) still routes to reconcile
- [x] A refuted proposal with a remaining eligible alternative is re-decided, then reconciled, re-wired and re-verified before scoring
- [x] On an already-decided issue (`Selected:` callout + `### Decision Rationale` on the refuted option), arming makes `ll-issues check-unresolved-decisions` report the group as unresolved
- [x] After a revision, Implementation Steps / Acceptance Criteria / Integration Map are rewritten for the new option even when the run's `check_reconcile_limit` budget is already spent
- [x] `ll-issues clear-verify-verdict` removes `verify_evidence` as well as `verify_verdict`
- [x] The revision path is not gated by `check_decide_attempts`: a decision resolved earlier in the same run does not defer the revision as `decision_unresolved`
- [x] `/ll:decide-issue` never re-selects an option named as refuted
- [x] A refuted proposal with no enumerable `### Option` blocks defers as `proposal_unsound` without invoking decide-issue
- [x] A refuted proposal whose alternatives are all refuted defers as `proposal_unsound`, not via exhausted reconcile/refine budgets
- [x] A revised option that verify also finds `PROPOSAL_UNSOUND` defers as `proposal_unsound` once the revision budget is spent
- [x] `/ll:verify-issues --check` makes no body edits (frontmatter `verify_verdict` / `verify_evidence` only)
- [x] The proposal-revision marker is consumed by `check_proposal_revision`, so a later unrelated decision in the same run returns to `confidence_check`
- [x] Under autodev, a nested `proposal_unsound` stop is not also ledgered as `refine_failed`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Resolution

Implemented: `DIRECTIVE_DRIFT` verdict + `verify_evidence` in verify-issues; `check-verify-verdict --directive-drift`; `ll-issues arm-proposal-revision`; `is_group_resolved` ignores refuted selections; `clear-verify-verdict` clears `verify_evidence`; `DeferReason.PROPOSAL_UNSOUND`; refine-to-ready proposal-revision cycle (`max_steps` 85, `recurrent_window` stays 6 after recount = 5); autodev ledger. Host mirrors regenerated.

Known unrelated failures on clean `main` (BUG-3593 leftovers, not touched here): spike-routing tests in test_builtin_loops / autodev topology / interp-sweep baseline, README loop count, evidence gate on BUG-1688.

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:manage-issue` - 2026-09-25T15:23:18 - `5d21391f-77bd-4745-a714-575794ff0d5b.jsonl`
- `/ll:ready-issue` - 2026-09-25T15:07:38 - `4310a48d-60cd-49e8-81df-b0e629e139c1.jsonl`
- `/ll:confidence-check` - 2026-09-25T15:04:36 - `2879e1b8-58ef-47c7-a4d2-34a25e460e4e.jsonl`
- `/ll:refine-issue` - 2026-09-25T01:44:08 - `b5d091e6-10b4-4f2f-9812-d49831a68b8b.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
