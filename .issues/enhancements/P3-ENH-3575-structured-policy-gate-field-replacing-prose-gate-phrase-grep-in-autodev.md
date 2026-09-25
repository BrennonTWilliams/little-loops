---
id: ENH-3575
type: ENH
title: Structured policy gate field replacing prose gate-phrase grep in autodev
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-24'
captured_at: '2026-09-24T19:33:14Z'
parent: EPIC-3565
blocks:
- ENH-3577
confidence_score: 85
outcome_confidence: 60
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 10
score_change_surface: 18
decision_needed: false
---

# ENH-3575: Structured policy gate field replacing prose gate-phrase grep in autodev

## Summary

Autodev detects policy-gated issues by grepping the **whole issue file** for gate phrases
(e.g. "evidence gate", "gate opens", "do not implement before"). It does this in
`check_gate_at_dequeue` (ENH-3148) and again, duplicated inline, in
`recheck_after_size_review`'s `GATE_MARKER` (BUG-3147). A match defers the issue as
`blocked_by_gate` without checking whether the gate is already satisfied, or whether a spike
or learning test could satisfy it. Historical findings, quoted requirements and resolved-gate
notes keep matching, so an issue can stay parked forever unless someone deletes useful
history just to change a routing verdict.

ENH-3148 explicitly left a structural frontmatter gate field out of scope, naming it the
preferred signal.

## Current Behavior

Any occurrence of a gate phrase, current or historical, parks the issue.

## Expected Behavior

Gate state is explicit and routable. External or manual prerequisites park the issue. Proof
obligations that a spike or `explore-api` can satisfy route to that remedy. Satisfied gates do
not block.

## Motivation

False-positive gate matches park good issues indefinitely, and the only workaround (deleting history) destroys useful context.

## Proposed Solution

Add a structured frontmatter field, e.g.
`gate: {kind: external|manual|proof, satisfied: bool, evidence: <ref>, owner: <who>}` (or a
list). Autodev reads the field first and falls back to the prose grep only when the field is
absent. Extract the duplicated phrase regex into one shared helper (a new `ll-issues` gate-check subcommand), which is the extraction BUG-3147 and ENH-3148 deferred.

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

**Option A**: `gate` is a single mapping — `gate: {kind, satisfied, evidence, owner}`. One gate per issue; simplest reader.

**Option B**: `gate` is a list of such mappings, with a lone mapping accepted and normalized to a one-item list. Multiple independent prerequisites (e.g. one `manual`, one `proof`) are expressible without a later schema break.

> **Selected:** Option B — list-of-mappings superset; a lone mapping normalizes to one item at the cost of one reader branch.

**Recommended**: Option B — the list form is a superset, and normalizing a lone mapping costs one branch in the reader; migrating from A to B later would change the field's shape under issues already written.

### Decision Rationale

**Selected option:** Option B — `gate` is a list of mappings; a lone mapping is normalized to a one-item list.

**Reasoning:** The Program Design already specifies `parse_gate(...) -> list[GateSpec]` normalizing both shapes, so B matches the designed signature. Research verified `parse_frontmatter`/`update_frontmatter` round-trip both a nested mapping and a list of mappings intact, so B adds no parsing risk over A. Choosing A and later moving to B would change the field's shape under already-written issues.

| Option | Consistency | Simplicity | Testability | Risk | Total |
|--------|-------------|------------|-------------|------|-------|
| A (single mapping) | 2 | 3 | 3 | 2 | 10/12 |
| B (list, lone mapping normalized) | 3 | 2 | 3 | 3 | 11/12 |

**Key evidence:** Program Design's `parse_gate -> list[GateSpec]` and the "structured verdicts" rules already iterate entries (any unsatisfied external/manual parks; proof routes to remedy); nested-scalar string coercion (`'false'`) must be handled in either option, so B's only extra cost is one normalize branch.

## Program Design

### Types
- `GateSpec(kind: Literal["external", "manual", "proof"], satisfied: bool, evidence: str | None, owner: str | None)` — new dataclass; parsed from the `gate` frontmatter mapping (or each list item) with `satisfied` coerced from the string `'false'`/`'true'` that `parse_frontmatter` returns for nested scalars
- `GateVerdict: Literal["structured_open", "structured_satisfied", "structured_proof", "prose", "none"]` — outcome of the read-structured-first-then-fall-back-to-prose resolution

### Signatures
- `parse_gate(frontmatter: dict[str, Any]) -> list[GateSpec]` — normalizes a lone mapping or a list of mappings; returns `[]` when the field is absent
- `detect_prose_gate(text: str) -> bool` — the single home of the 8-phrase regex now duplicated in `check_gate_at_dequeue` and `recheck_after_size_review`
- `cmd_check_gate(config: BRConfig, args: argparse.Namespace) -> int` — new `ll-issues` subcommand handler, modeled on the `cmd_check_flag` / `cmd_check_design` handler shape
- `add_check_gate_parser(subs: argparse._SubParsersAction) -> None` — parser registration, same shape as `add_spike_verdict_parser`

### Call Path
`check_gate_at_dequeue` -> `main_issues` -> `cmd_check_gate` -> `parse_frontmatter` -> `parse_gate` -> `detect_prose_gate`
`recheck_after_size_review` -> `main_issues` -> `cmd_check_gate` -> `parse_gate`

### Decision Rules
- **Inputs**: the issue's frontmatter `gate` value (mapping, list of mappings, or absent) and, only when absent, the whole-file text.
- **Precedence**: any `gate` field present → structured path only; the prose regex is not consulted. Absent → prose fallback with the current 8 literal phrases, unchanged.
- **Structured verdicts**: an entry with `satisfied` true never blocks; `kind` `external` or `manual` with `satisfied` false parks (`blocked_by_gate`); `kind` `proof` with `satisfied` false routes to the spike / learning-test remedy instead of parking, subject to the existing `spike_attempted` and `spike-runs-<ID>` (cap 2) guards so an unprovable gate still terminates in a deferral.
- **`satisfied` coercion**: nested scalars arrive as strings; only the literal `true` (case-insensitive) counts as satisfied. Missing/unparseable `kind` or `satisfied` → treated as unsatisfied `manual` (fail toward parking is the stated bias of the gate; fail-open applies to helper errors, not malformed data).
- **Escape hatch**: an issue that sets a satisfied gate, or removes the field and its gate prose, is not parked; the prose fallback is inert once the field exists.
- **Dequeue-only signal**: the placeholder-Acceptance-Criteria check stays in the dequeue path and is not folded into the phrase helper's result for the `recheck_after_size_review` caller.

## Integration Map

### Files to Modify
- `scripts/little_loops/loops/autodev.yaml` — `check_gate_at_dequeue`, `recheck_after_size_review`
- `scripts/little_loops/cli/issues/` — new gate helper
- `scripts/little_loops/config-schema.json` / frontmatter validation if the field is schema'd

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/__init__.py` — three hand-edited touchpoints for the new subcommand: the lazy import block (~lines 31-42), the `add_*_parser(subs)` registration (~lines 778-781), and the `if args.command == ...: return cmd_...` dispatch chain (~lines 1086-1093); plus the hand-written subcommand epilog list (~lines 134-175, check family at 152-155/173-174) [Agent 1 + 2 finding]
- `scripts/little_loops/cli/issues/show.py` — `--json` output is an explicit per-field dict (~lines 300-365, `frontmatter.get("decision_needed")` at ~129); add `gate` here if any autodev `python3 -c` selector needs to read it [Agent 1 + 2 finding]
- `scripts/little_loops/issue_parser.py` — `IssueInfo` (`to_dict`/`from_dict`/parse path) only if a typed `gate` field is wanted; optional, since `parse_gate` reads raw frontmatter [Agent 2 finding]
- `scripts/little_loops/loops/autodev.yaml` `recheck_after_size_review` (`GATE_MARKER`, ~lines 2760-2790) — `REMEDY` selector is `python3 -c` piped from `ll-issues show --json` with `GATE_MARKER` as an env prefix; the helper must expose the phrase/gate signal separately from the dequeue-only placeholder-AC signal [Agent 2 finding]

### Dependent Files (Callers/Importers)
- `defer_gated`, `mark_gate_blocked` ledgers

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason.BLOCKED_BY_GATE` (~line 95) feeds `_DEFERRAL_REASON_CODES` / `set-status --reason`; no change if the reason code stays `blocked_by_gate` [Agent 1 finding]
- `scripts/little_loops/cli/issues/deferred_triage.py` — `"blocked_by_gate": 7` reason-code ranking; no change unless a new code is introduced [Agent 1 finding]
- `scripts/little_loops/loops/refine-to-ready-issue.yaml` — has `check_spike_needed` / `run_spike` but no gate-phrase grep; the only other loop on the proof-routing surface, not a consumer of the prose detector [Agent 1 finding]
- `scripts/little_loops/frontmatter.py` — `parse_frontmatter` (BaseLoader: all scalars → strings), `update_frontmatter` (yaml round-trip), `remove_frontmatter_keys`; the `_parse_frontmatter_lines` fallback warns on non-scalar list items, so list-of-mappings depends on the PyYAML path [Agent 2 finding]
- The prose phrases and `blocked_by_gate` occur in no other loop, skill, hook, agent or `.loops/` file — `autodev.yaml` is the sole live consumer [Agents 1 + 2 finding]

### Similar Patterns
- `ll-issues check-flag`, `ll-issues check-readiness`
- `scripts/little_loops/cli/issues/check_open_questions.py`, `check_verify_verdict.py` — each defines `add_<name>_parser(subs)` + `cmd_<name>(config, args)` with `p.set_defaults(command="...")` [Agent 2 finding]
- `check-design` replacing an inline block in `autodev.yaml` (ENH-2967; call sites ~lines 1511, 1521, 2236, 2616) — closest precedent for swapping inline shell for an exit-code probe [Agent 2 finding]

### Tests
- `scripts/tests/test_autodev_loop.py` — `TestCheckGateAtDequeueMarkerLiterals`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_autodev_loop.py` — `TestRecheckAfterSizeReviewMeasurementGateBranch.test_marker_literals_present_in_action` (~line 715) asserts the 8 literals in the `recheck_after_size_review` action; will break when the grep moves to the helper — re-point [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py` — `TestRecheckAfterSizeReviewMeasurementGateBranch.test_gate_check_precedes_ambiguity_fallback` (~line 729) does `action.index("GATE_MARKER")`; breaks if the identifier is renamed/removed [Agent 3 finding]
- `scripts/tests/test_autodev_loop.py` — `_run_pre_deferral_remedy_selector` (~line 640) runs the `REMEDY=$(...)` block in bash with a stub `ll-issues` that returns one fixed JSON payload for every call; a new `ll-issues check-gate` call ahead of the pipeline would receive JSON, so the stub needs a `check-gate` arm. Behavioral cases `test_marker_present_forces_spike_even_when_ambiguity_not_weakest`, `test_marker_absent_falls_back_to_ambiguity_weakest_regression`, `test_marker_absent_and_ambiguity_not_weakest_falls_back_to_reconcile_regression`, `test_marker_present_but_already_attempted_yields_no_remedy`, `test_marker_absent_and_ambiguity_ties_weakest_falls_back_to_reconcile_regression` depend on it [Agent 2 + 3 finding]
- `scripts/tests/test_builtin_loops.py` — `test_check_gate_at_dequeue_routing` (~7199, incl. fail-open `on_error` at ~7206, `evaluate.pattern == "GATE_YES"`), `test_defer_gated_defers_via_set_status` (asserts `--reason blocked_by_gate`), and the literal/`GATE_MARKER` assertions on `recheck_after_size_review` (~lines 8761-8773); update if the state's command or evaluator changes [Agent 2 + 3 finding]
- `scripts/tests/test_check_family_not_found_exit_code.py` — `test_family_has_seven_members` will break (bump to 8) if the module is named `check_gate.py`; `_family_subcommands()` globs `cli/issues/check_*.py`, so a new module is auto-parametrized (exit 2 on unresolvable ID); add to `_EXTRA_ARGV` if it takes an extra positional [Agent 2 + 3 finding]
- `scripts/tests/test_autodev_scores_freshness.py` (~line 137) — stub `ll-issues` switches on subcommand (`check-design`); add a `check-gate` arm if that path is exercised [Agent 2 finding]
- `scripts/tests/test_fsm_topology.py` (~line 248) — state-count assertion (79); changes only if states are added/removed [Agent 1 + 2 finding]
- `scripts/tests/test_autodev_loop.py` — `TestRecheckScoresDesignGateEndToEnd` (~line 1046) and `TestPreDeferralRemedyContradictionExemption` (~line 840) — closest end-to-end templates for new structured-gate routing cases [Agent 3 finding]
- New: `scripts/tests/test_ll_issues_check_gate.py` — model on `test_ll_issues_check_flag.py` (`TestCheckFlagHappyPath` / `FalseOrAbsent` / `ErrorHandling` / `TestCliRegistration::test_subcommand_in_help`): exit 0/1/2, help registration [Agent 3 finding]
- New: `gate` frontmatter test in `scripts/tests/test_frontmatter.py` (near `TestUpdateFrontmatter::test_nested_dict_value_round_trips`, ~line 551) — list-of-mappings parse + round-trip, `satisfied: false` → `'false'` not treated as satisfied; no `gate`-specific test exists [Agent 3 finding]
- New: autodev behavioral cases for structured `gate` (satisfied → no defer; `proof` → spike routing; prose fallback when field absent) [Agent 3 finding]
- `scripts/tests/test_show.py` — no dedicated `--json` test exists; add a `gate` case if `show.py` is extended [Agent 3 finding]
- `scripts/tests/test_wiring_cli_registry.py` — list of `(file, literal, issue-id)` tuples; adding an entry for the new command is optional [Agent 2 finding]

### Documentation
- `docs/reference/DEFERRAL_CODES.md` (`blocked_by_gate`)

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/CLI.md` — new `#### ll-issues <name>` section in the check family (~lines 2247-2454; `check-design` "FSM loop use" paragraph at ~2321 is the precedent) [Agent 1 + 2 finding]
- `docs/reference/API.md` — one-line row for the new probe; `check_gate_at_dequeue` / `blocked_by_gate` prose at ~lines 4662-4678 [Agent 1 + 2 finding]
- `docs/reference/ISSUE_TEMPLATE.md` — frontmatter field table (~lines 918-921, `spike_attempted`/`spike_completed` rows): add a `gate` row [Agent 1 + 2 finding]
- `docs/guides/LOOPS_REFERENCE.md` — autodev flow diagram "explicitly gated (prose/placeholder ACs)?" (~lines 1034-1035) and `recheck_after_size_review` text (~1067-1087) [Agent 1 + 2 finding]
- `docs/reference/DEFERRAL_CODES.md` line ~28 — `blocked_by_gate` "Emitted by" wording currently says "prose gate language and/or a placeholder Acceptance Criteria section" [Agent 2 finding]
- No mirror regeneration needed unless a skill/command is edited (then `ll-adapt --host <gemini|kimi-code|qwen> --apply`) [Agent 2 finding]

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- **Two detectors, not one behavior.** `check_gate_at_dequeue` (`autodev.yaml`) and `recheck_after_size_review`'s `GATE_MARKER` share a byte-identical 8-phrase `grep -qiE` over the whole issue file, but feed different consumers: A emits `GATE_YES`/`GATE_NO` (`output_contains`) and routes to `defer_gated` (`set-status deferred --reason blocked_by_gate`); B only sets an env var consumed by the inline `REMEDY` selector, where a match biases the pre-deferral remedy to `spike` (after the `spike_attempted` / `SPIKE_SPENT` / `reconcile_attempted` guards). B does not defer. Only A has a second signal — the placeholder-Acceptance-Criteria heredoc (`to be settled|to be determined|TBD` with no checkbox lines). A shared helper must preserve that asymmetry.
- **`mark_gate_blocked` is not fed by these detectors.** It is reached via `check_learning_gate` (the `ll_auto_learning_gate_check` fragment in `loops/lib/common.yaml`, grepping `ll_auto_last.txt` for `LEARNING_GATE_BLOCKED`) and writes `autodev-gate-blocked.txt` / `--reason gate_blocked`, a different deferral code from `blocked_by_gate`. The Dependent Files line naming it as a ledger dependent of the prose detectors is inaccurate; the true dependents are `defer_gated` (`autodev-skipped.txt`) and the `REMEDY` selector → `autodev-pre-deferral-remedy.txt` → `check_pre_deferral_remedy` → dispatcher states.
- **No frontmatter schema or known-keys registry exists.** `config-schema.json` has no issue-frontmatter section; `frontmatter.py` has only `DEPRECATED_FRONTMATTER_KEYS` (a deprecation map, not an allowlist). Each field is hand-plumbed at its readers, so the "config-schema / frontmatter validation if schema'd" line has no target. The nearest validation precedent is `check_format_gaps` in `issue_parser.py`, which shape-checks dependency-ID list fields (`gaps.malformed_dep_id`).
- **`ll-issues show --json` emits only explicitly-handled fields** (`show.py`, per-field `frontmatter.get(...)` with booleans lowercased to strings). Autodev consumes flags through that JSON, so a `gate` field is invisible to autodev's `python3 -c` selectors unless `show.py` also surfaces it — or the loop reads it through the new subcommand instead.
- **Frontmatter type constraint (verified by probe, this pass).** `parse_frontmatter(..., coerce_types=True)` round-trips a nested mapping and a list of mappings intact through `update_frontmatter`, but nested scalar values come back as **strings**: `satisfied: false` → `'false'`, `evidence: null` → `'null'`. Only top-level scalars are coerced. Any truthiness test on `gate.satisfied` must compare against the string, or the helper must coerce; a bare `if gate["satisfied"]` treats `'false'` as satisfied. No existing field is a nested mapping, so this is the first.
- **Test-guard constraint on naming.** `test_check_family_not_found_exit_code.py` globs `cli/issues/check_*.py`, auto-asserts exit 2 on an unresolvable ID for each, and pins the family size (`test_family_has_seven_members`, hand-edited). A module named `check_gate.py` joins the family and changes that count; the issue's "gate-check" name (`gate_check.py`) would not be globbed. Either choice must leave that test green and, if the module takes an extra positional, register it in `_EXTRA_ARGV`.
- **Exit-code convention for `check-*` probes** (`docs/reference/CLI.md`, BUG-3294 paragraph): 0 = yes, 1 = genuine negative, 2 = issue unresolvable, 3 = abstain (used by `check_readiness` / `spike_verdict`). `harness_exit` maps 3 to `on_cannot_judge`, which a state must declare; `shell_exit` maps 2+ to `on_error`. `check_gate_at_dequeue` is currently fail-open (`on_error: refine_current`) and must stay so.
- **Existing proof-routing surface a `proof` gate can reuse:** `check_spike_needed` (predicate `spike_needed == 'true' and spike_attempted != 'true'`, budget file `${context.run_dir}/spike-runs-<ID>` capped at 2) → `run_spike` (`/ll:spike --auto`); and the learning path (`learning_tests_required` list → proof-first-task gate in `parallel/worker_pool.py`, `LEARNING_GATE_BLOCKED` → `mark_gate_blocked` → "prove with /ll:explore-api"). Nothing routes on a gate `kind` today.
- **Docs surfaces per `ll-issues` subcommand:** `docs/reference/CLI.md` (`#### ll-issues <name>` section with args table, examples, "FSM loop use"), `docs/reference/API.md` one-line table row, the `__init__.py` epilog list, and the `blocked_by_gate` row of `docs/reference/DEFERRAL_CODES.md` (whose "Emitted by" / trigger text currently says "prose gate language and/or a placeholder Acceptance Criteria section"). Wiring tests (`test_wiring_cli_registry.py`, `test_wiring_reference_docs.py`, `test_doc_counts.py`) may pin counts.

## Implementation Steps

1. Define the frontmatter `gate` schema (and validation in `ll-issues`)
2. Add a shared gate-check helper that reads structured first, then falls back to prose
3. Replace both inline regexes in autodev
4. Route `proof` gates to spike/explore-api
5. Tests for satisfied, external and proof gates

### Codebase Research Findings

_Added by `/ll:refine-issue` — 2026-09-25 — based on codebase analysis:_

- Outcome constraints (order incidental except where noted): (1) `gate` parses via one reader that handles mapping / list / absent and coerces nested-scalar strings — covered by a unit test asserting `satisfied: false` is *not* treated as satisfied; (2) the phrase regex has exactly one source in the repo, and `TestCheckGateAtDequeueMarkerLiterals` / `TestRecheckAfterSizeReviewMeasurementGateBranch` (which today assert the literals inside each state's `action`) are re-pointed at the helper without losing the literal coverage; (3) both autodev states keep fail-open on helper error and keep their differing consumers (defer vs. spike bias) and the dequeue-only placeholder-AC signal; (4) the new module leaves `test_check_family_not_found_exit_code.py` green (exit 2 on unresolvable ID, family-size pin); (5) `show.py` or the new subcommand exposes `gate` state to any autodev selector that needs it; (6) `docs/reference/CLI.md`, `API.md`, the `__init__.py` epilog and the `DEFERRAL_CODES.md` `blocked_by_gate` row describe the new behavior. Verification: `python -m pytest scripts/tests/test_autodev_loop.py scripts/tests/test_check_family_not_found_exit_code.py -v` plus the new subcommand's own subprocess-style test (pattern: `test_ll_issues_check_design.py` grouping — passes / fails / error handling / CLI registration). Forced order: the reader and helper must exist before either autodev state is switched to call them.

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

- Register the new subcommand in `scripts/little_loops/cli/issues/__init__.py` — lazy import, `add_*_parser` call, dispatch branch, and epilog list entry
- Update `scripts/little_loops/cli/issues/show.py` — surface `gate` in `--json` if any autodev selector reads it (otherwise the loop reads it via the new subcommand)
- Update `scripts/tests/test_check_family_not_found_exit_code.py` — bump `test_family_has_seven_members` to 8 (if named `check_gate.py`); add `_EXTRA_ARGV` entry if an extra positional is taken
- Update `scripts/tests/test_autodev_loop.py` — re-point `TestCheckGateAtDequeueMarkerLiterals` and `TestRecheckAfterSizeReviewMeasurementGateBranch` literal/`GATE_MARKER`-index tests at the helper; add a `check-gate` arm to the `_run_pre_deferral_remedy_selector` stub `ll-issues`
- Update `scripts/tests/test_builtin_loops.py` (~7199-7261, ~8761-8773) and `scripts/tests/test_autodev_scores_freshness.py` stub — adapt to the changed state actions
- Add `scripts/tests/test_ll_issues_check_gate.py` and a `gate` list-of-mappings round-trip test in `scripts/tests/test_frontmatter.py`
- Update `docs/reference/CLI.md`, `docs/reference/API.md`, `docs/reference/ISSUE_TEMPLATE.md`, `docs/guides/LOOPS_REFERENCE.md`, and the `blocked_by_gate` row of `docs/reference/DEFERRAL_CODES.md`

## Impact

- **Priority**: P3
- **Effort**: Medium
- **Risk**: Low. The fallback keeps today's behavior for issues without the field.

## Scope Boundaries

- In scope: autodev's two gate detectors and the new field.
- Out of scope: migrating existing issues' prose gates to the field (the fallback covers them); rn-* loops' gate handling.

## Acceptance Criteria

- [ ] A satisfied structured gate does not defer the issue
- [ ] A `proof` gate routes to spike/explore-api rather than parking
- [ ] One shared gate-detection helper; no duplicated phrase regex in autodev

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Status

**Open** | Created: 2026-09-24 | Priority: P3


## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-09-25_

**Readiness Score**: 85/100 → STOP — ADDRESS GAPS (Program Design hard override; raw tier PROCEED WITH CAUTION)
**Outcome Confidence**: 60/100 → MODERATE

### Concerns
- Schema is stated as "e.g." and "(or a list)" — single object vs list of gates is undecided.

### Gaps to Address
- `## Program Design` section is missing (`ll-issues check-design` fails). Add concrete types, signatures and a call path via `/ll:refine-issue` or `/ll:reconcile-issue`, or set `program_design_not_applicable: true` if trivial.

### Outcome Risk Factors
- Open design decisions: gate schema shape (object vs list), what `satisfied`/`evidence` mean, and how a `proof` gate routes to spike vs `explore-api` are unspecified.
- Moderate per-site complexity: two autodev.yaml states plus a new `ll-issues` subcommand and a fallback path that must preserve current prose-grep behavior.

## Session Log
- `/ll:wire-issue` - 2026-09-25T16:16:14 - `53cc9ee9-2fce-4262-8fb3-74a571d4aabf.jsonl`
- `/ll:decide-issue` - 2026-09-25T15:50:09 - `15f88de1-71aa-4840-8254-7f346d788eff.jsonl`
- `/ll:refine-issue` - 2026-09-25T15:48:14 - `2c2217f3-faed-46a2-9f48-d3c79062bfca.jsonl`
- `/ll:confidence-check` - 2026-09-25T15:43:11 - `88d59a88-839a-4f32-8b82-4e5b4f322725.jsonl`
- `/ll:verify-issues` - 2026-09-25T15:27:33 - `bc279096-6a89-4a82-b7c2-8e6f11cc30f5.jsonl`
- `/ll:capture-issue` - 2026-09-24T19:42:32 - `59fe3bd4-3622-4dd2-bb8b-ad5cc55e79ec.jsonl`
