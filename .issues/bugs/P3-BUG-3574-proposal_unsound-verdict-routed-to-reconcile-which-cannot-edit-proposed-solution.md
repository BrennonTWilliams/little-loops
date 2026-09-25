---
id: BUG-3574
type: BUG
title: PROPOSAL_UNSOUND verdict routed to reconcile, which cannot edit Proposed Solution
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:13Z'
parent: EPIC-3565
blocks:
- ENH-3577
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
     field (the B6 finding, single line, no newlines). This stays inside § 2.5's existing
     "persist to frontmatter" carve-out. **`--check` makes no body edits** — its documented
     contract (`commands/verify-issues.md` § 2.5, and the `--check` flag description:
     "without applying changes") is preserved. verify-issues never invents alternatives.

2. **Arm the revision deterministically in a loop state, not in verify-issues.** A new
   `arm-proposal-revision <ID>` subcommand of `ll-issues` (new; modeled on BUG-3593's `rearm-spike`)
   reuses BUG-3592's refuted → `decision_needed` contract:
   - Locate the selected option: `_selected_option_title` over `## Proposed Solution` (the
     `> **Selected:**` callout), matched against `locate_enumerable_options(...)` labels.
   - **Arm** (exit 0, prints `[PROPOSAL_REVISION_ARMED] <ID>`) only when the selected option
     is an enumerable `### Option <X>:` block **and** at least one other option stays
     eligible after marking it refuted. Then set `decision_needed: true` and append an
     `## Open Questions` item in BUG-3592's literal marker shape (parsed by
     `_REFUTED_OPTION_RE`):
     `1. **Refuted option**: Option A — /ll:verify-issues <date>: <verify_evidence>. Which remaining option replaces it?`
   - **No alternative** (exit 1, prints `[NO_ALTERNATIVE] <ID>`, no file change) when there
     are no enumerable option blocks, no `Selected:` callout matching one, or no eligible
     option would remain. This is decided **before** decide-issue runs because decide-issue
     cannot be trusted with it: with `OPTIONS == 0`, auto mode invokes `/ll:refine-issue`
     to deposit options and its Phase 3b Pattern D scan can lock a winner from provisional
     wording (`skills/decide-issue/SKILL.md` Phase 2.5) — the marker label matches no
     located option, `all_refuted` never fires, and the refuted design can be re-selected.
   - Exit 2 on unresolvable ID (matches `rearm-spike`).

3. **Decide-issue exclusion — delivered by BUG-3592; nothing new here.** With ≥1 eligible
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
     present → `rm -f` it, then `wire_issue` (→ `mark_wire_done` → `check_decision_mid_wire`
     → `normalize_structure` → BUG-3571's `clear_verify_verdict` → `verify_issue`); absent →
     `confidence_check` as today. **The state consumes the marker** so a later, unrelated
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
   - `max_steps`: currently **70** (BUG-3593 raised it from 60). Bump for the revision cycle
     (budget → arm → resolve → check_proposal_revision → wire → mark_wire_done →
     check_decision_mid_wire → normalize → clear → verify → verdict chain) and update its
     comment.

5. **autodev ledger**: a nested `record_proposal_unsound` exits `failed` without passing
   `classify_terminal`, so autodev's `skip_inflight` must `grep -qxF "$ID"
   autodev-proposal-unsound.txt` and skip the `refine_failed` ledger line, exactly as
   BUG-3593 did for `autodev-spike-inconclusive.txt` (`autodev.yaml` `skip_inflight`).
   Surface the ledger in autodev's finalize summary alongside the spike-inconclusive one.

6. **Legacy values need no migration**: BUG-3571 clears `verify_verdict` before every verify,
   so a persisted `PROPOSAL_UNSOUND` from an earlier run is never read. `clear_verify_verdict`
   must also clear `verify_evidence` so a stale finding never reaches a later marker.

## Program Design

### Types

- `DIRECTIVE_DRIFT` — new `verify_verdict` value, written by `/ll:verify-issues --check`.
- `verify_evidence` — new single-line frontmatter field, written by `/ll:verify-issues --check` only alongside `verify_verdict: PROPOSAL_UNSOUND`; cleared by `clear_verify_verdict`.
- `DeferReason.PROPOSAL_UNSOUND` — new `issue_lifecycle.DeferReason` member, value `"proposal_unsound"`.

### Signatures

- `cmd_check_verify_verdict(config: BRConfig, args: argparse.Namespace) -> int` — existing; gains a `--directive-drift` query mode (exit 0 when `verify_verdict == DIRECTIVE_DRIFT`, 1 otherwise), mirroring `--proposal-unsound`. Default mode treats `DIRECTIVE_DRIFT` as non-VALID (exit 1).
- `cmd_arm_proposal_revision(config: BRConfig, args: argparse.Namespace) -> int` — new, in `cli/issues/arm_proposal_revision.py` (new file); 0 = armed (marker + `decision_needed`), 1 = no eligible alternative (no file change), 2 = issue not found.
- `add_arm_proposal_revision_parser(subs: argparse._SubParsersAction) -> argparse.ArgumentParser` — new; registers `arm-proposal-revision`.

### Call Path

`cmd_arm_proposal_revision` -> `locate_enumerable_options` -> `refuted_option_labels`

`cmd_check_verify_verdict` -> `parse_frontmatter`

## Integration Map

### Files to Modify
- `commands/verify-issues.md` — §B6 verdict split by fix location; §C verdict table adds `DIRECTIVE_DRIFT`; § 2.5 frontmatter mapping adds `DIRECTIVE_DRIFT` and `verify_evidence` (frontmatter only — no body edits in `--check`)
- `scripts/little_loops/cli/issues/check_verify_verdict.py` — `--directive-drift` query mode; default mode non-VALID for it
- `scripts/little_loops/cli/issues/arm_proposal_revision.py` (new) — new CLI (see Program Design)
- `scripts/little_loops/cli/issues/__init__.py` — parser registration for both, `_USAGE` / help text
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason.PROPOSAL_UNSOUND = "proposal_unsound"` (the `set-status --reason` argparse `choices` validate against this enum; the shell state's `|| true` would hide a rejection)
- `scripts/little_loops/cli/issues/deferred_triage.py` — `_REASON_RANK["proposal_unsound"] = 3` (same needs-human tier as `decision_unresolved` / `spike_inconclusive`)
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — `resolve_issue` resets `refine-to-ready-proposal-revisions` and removes `refine-to-ready-proposal-revision`; `clear_verify_verdict` also clears `verify_evidence`; new states `check_directive_drift`, `check_proposal_revision_budget`, `arm_proposal_revision`, `check_proposal_revision`, `check_proposal_revision_failed`, `record_proposal_unsound`; `check_proposal_unsound.on_yes`/`on_no` rewired; `resolve_decision_pre_breakdown.on_success` → `check_proposal_revision`; `check_decide_rate_limited.on_no` → `check_proposal_revision_failed`; `max_steps` bump + comment; header comment chain and ENH-3250 comment on `check_proposal_unsound`; `classify_terminal` must leave an already-written `proposal_unsound` class alone
- `scripts/little_loops/loops/autodev.yaml` — `skip_inflight` greps `autodev-proposal-unsound.txt` (mirrors the BUG-3593 `autodev-spike-inconclusive.txt` block); finalize summary surfaces the ledger

### Dependent Files (Callers/Importers)
- `commands/reconcile-issue.md` — unchanged contract; receives only `DIRECTIVE_DRIFT` now
- `skills/decide-issue/SKILL.md` — unchanged; the option exclusion, marker resolution and `ALL_OPTIONS_REFUTED` exit landed in BUG-3592
- `scripts/little_loops/loops/oracles/resolve-decision.yaml` — unchanged; its `failed` terminal on `ALL_OPTIONS_REFUTED` feeds `check_proposal_revision_failed`

### Similar Patterns
- BUG-3592 refuted spike → `decision_needed` + enumerable options + refuted-option marker
- BUG-3593 `check_spike_budget` (bypasses `check_decide_attempts`), `record_spike_inconclusive` + autodev ledger, `ll-issues rearm-spike` (deterministic arming CLI)
- autodev `refine_for_design` (BUG-3002): a dedicated remedy chosen because the default remedy's contract excludes the failing section

### Tests
- `scripts/tests/test_ll_issues_check_verify_verdict.py` — `--directive-drift` query mode class; default mode exits 1 on `DIRECTIVE_DRIFT`
- `scripts/tests/test_arm_proposal_revision.py` (new) — arms with ≥2 options + `Selected:` callout (marker parses via `refuted_option_labels`, `decision_needed: true`); exit 1 and no file change for: no option blocks, no `Selected:` callout, selected option is the only eligible one, all others already refuted; exit 2 on unknown ID
- `scripts/tests/test_builtin_loops.py` — routing assertions for every new state and rewired edge (incl. `test_check_verify_verdict_on_no_reaches_check_proposal_unsound`); `check_proposal_revision` consumes the marker; `resolve_issue` resets both run-dir files; `max_steps` value test; stub `ll-issues` on `PATH` running the real state `action`
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

## Implementation Steps

1. `issue_lifecycle.DeferReason.PROPOSAL_UNSOUND` + `deferred_triage._REASON_RANK` entry
2. `check_verify_verdict.py`: `--directive-drift` query mode; default mode non-VALID for it
3. `arm_proposal_revision.py` (new) CLI + registration in `cli/issues/__init__.py`
4. verify-issues: split B6 verdict by fix location; add `DIRECTIVE_DRIFT`; persist `verify_evidence` on `PROPOSAL_UNSOUND`; frontmatter-only in `--check`
5. refine-to-ready: `check_directive_drift` → reconcile; `PROPOSAL_UNSOUND` → `check_proposal_revision_budget` → `arm_proposal_revision` → `resolve_decision_pre_breakdown` → `check_proposal_revision` (consume marker) → `wire_issue`; failure → `check_proposal_revision_failed` → `record_proposal_unsound`; `resolve_issue` resets; `clear_verify_verdict` clears `verify_evidence`; `max_steps`
6. autodev `skip_inflight` + finalize ledger handling
7. Tests for each route and CLI; docs and host mirrors

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low-Medium — changes the verify-issues verdict taxonomy and adds a revision cycle to refine-to-ready; decide-issue is unchanged (exclusion delivered by BUG-3592).
- **Sequencing**: BUG-3571 (verdict clearing) and BUG-3592 (refuted → `decision_needed` contract and decide-issue exclusion) are done. BUG-3593 (done in code) touches the same `refine-to-ready-issue.yaml` band, `DeferReason`, `deferred_triage.py` and autodev `skip_inflight` — rebase onto it; close out BUG-3595 (automated-run artifact for BUG-3593) first so the two don't collide.

## Acceptance Criteria

- [ ] A refuted Proposed Solution is never routed only to reconcile
- [ ] Directive-only drift (`DIRECTIVE_DRIFT`) still routes to reconcile
- [ ] A refuted proposal with a remaining eligible alternative is re-decided, then re-wired and re-verified before scoring
- [ ] The revision path is not gated by `check_decide_attempts`: a decision resolved earlier in the same run does not defer the revision as `decision_unresolved`
- [ ] `/ll:decide-issue` never re-selects an option named as refuted
- [ ] A refuted proposal with no enumerable `### Option` blocks defers as `proposal_unsound` without invoking decide-issue
- [ ] A refuted proposal whose alternatives are all refuted defers as `proposal_unsound`, not via exhausted reconcile/refine budgets
- [ ] A revised option that verify also finds `PROPOSAL_UNSOUND` defers as `proposal_unsound` once the revision budget is spent
- [ ] `/ll:verify-issues --check` makes no body edits (frontmatter `verify_verdict` / `verify_evidence` only)
- [ ] The proposal-revision marker is consumed by `check_proposal_revision`, so a later unrelated decision in the same run returns to `confidence_check`
- [ ] Under autodev, a nested `proposal_unsound` stop is not also ledgered as `refine_failed`

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Session Log
- `/ll:refine-issue` - 2026-09-25T01:44:08 - `b5d091e6-10b4-4f2f-9812-d49831a68b8b.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
