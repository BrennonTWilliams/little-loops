---
id: BUG-3489
type: BUG
title: 'Policy-router runtime: stale LLM scores across passes and decision-table dispatch
  errors route to a success outcome'
priority: P2
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-16'
captured_at: '2026-09-16T22:14:21Z'
labels:
- policy-builder
relates_to:
- BUG-3486
- BUG-3490
- FEAT-3474
---

# BUG-3489: Policy-router runtime: stale LLM scores across passes and decision-table dispatch errors route to a success outcome

## Summary

Fix two runtime defects in the policy-router loop fragments and decision-table YAML emission: stale per-dimension score files survive a second LLM scoring pass, and decision-table dispatch errors route to the first outcome (which may be a success state) because decision-table mode emits no failure terminal.

Split from BUG-3486 (2026-09-16 whole-builder review, defects f and g). Independent of the browser/core template work in BUG-3486 and the catalog-discovery work in BUG-3490.

## Current Behavior

- The `policy_parse_scores` fragment (`scripts/little_loops/loops/lib/policy-router.yaml`, ~lines 84-116) writes `rubric-dim-<name>.txt` only for `DIMENSION:` lines present in the current pass and never deletes pre-existing files. `policy_table_dispatch` (same file, ~197-208) then reads every `rubric-dim-*.txt` via `os.listdir(run_dir)`. Running the fragment twice in one run dir, omitting a dimension on pass two, leaves the pass-one score in play. A previous `citations` score of 100 survives a second pass that emitted no citations line. The deterministic `frontmatter_scores` scorer already clears stale files via `_clean_slate()` (`scripts/little_loops/fsm/frontmatter_scores.py:158-169`).
- `_serializeDecisionTable()` (`scripts/little_loops/templates/policy_builder_core.mjs` ~800-804) sets `errorState = tokens[0] || fallbackState`, where `tokens[0]` is whichever outcome the first authored rule targets. No dedicated failure terminal is emitted for decision-table mode, so a dispatch or scoring failure can report successful completion. `_serializeIssueLifecycle()` (mjs ~974-1041) already emits an explicit `failed:` terminal and routes `_error: failed`.

## Expected Behavior

Fresh scoring cannot use previous-pass evidence: every `policy_parse_scores` pass starts from a clean slate of `rubric-dim-*.txt` and `rubric-aggregate.txt`. Decision-table loops route `_error` and `on_error` to a dedicated failure terminal that can never be confused with a success outcome.

## Motivation

Users cannot trust routing decisions when evidence leaks between passes or when a failure lands on a success state. These are runtime defects, independent of the browser preview, and block FEAT-3488's execution handoff.

## Proposed Solution

- Add clean-slate handling to `policy_parse_scores`, mirroring `_clean_slate()` in `frontmatter_scores.py`: glob and unlink `rubric-dim-*.txt` and `rubric-aggregate.txt` in `${context.run_dir}` before writing new scores. Consider factoring the heredoc body into an importable module (like `frontmatter_scores.py`) so the two-pass behavior is unit-testable; today no such module exists.
- Emit a `failed:` terminal in `_serializeDecisionTable()`, matching the `_serializeIssueLifecycle()` precedent, and route `_error: failed`. Also set `on_error: failed` on the dispatch state itself (the fragment docstring says `on_error` is caller-supplied, so the `_error` sentinel alone is not sufficient). Use the name `failed` so `fsm/schema.py`'s `FAILURE_TERMINAL_NAMES` recognizes it without a schema change. Reserve `failed` as a user outcome name (coordinate with BUG-3486's reserved-name validation).

## Implementation Steps

1. Add a two-pass regression test for `policy_parse_scores` proving an omitted dimension cannot retain its prior score (closest precedent: `scripts/tests/test_frontmatter_scores.py::TestMainHappyPath.test_two_pass_clean_slate`).
2. Add clean-slate handling to the fragment.
3. Emit the `failed` terminal and `on_error`/`_error` routing in `_serializeDecisionTable()`; add a test asserting a decision-table model's YAML never routes `_error` to a user outcome.
4. Regenerate `scripts/tests/fixtures/policy_builder/sample-decision-table.yaml` and `.model.json` together; update the three pinned tests: `scripts/tests/js/policy_validator.test.mjs` ("serializeLoopYaml matches golden decision-table fixture"), `scripts/tests/test_policy_builder_emit.py::test_golden_yaml_validates`, `scripts/tests/test_policy_builder_node_gate.py::test_round_trip_yaml_validates_for_each_mode`.
5. Regenerate `scripts/tests/fixtures/policy_builder/golden_policy_router_builder.html` (required by `scripts/tests/test_enh3035_artifact_template_kit.py`).
6. Update `docs/guides/POLICY_ROUTER_GUIDE.md` to document the failure terminal and clean-slate scoring.

## Impact

- **Priority**: P2 - stale evidence and mis-routed failures make runtime routing wrong even when the preview is healthy
- **Effort**: Small - two localized changes plus fixture regeneration
- **Risk**: Low - clean slate mirrors an existing, tested pattern; new terminal only adds a state
- **Breaking Change**: No - valid decision-table YAML gains a `failed` state; `failed` becomes a reserved outcome name

## Program Design

### Types

No new types. The fragment gains a clean-slate step; the decision-table serializer gains one emitted state.

### Signatures

- `_serializeDecisionTable(model) -> string` in `scripts/little_loops/templates/policy_builder_core.mjs` — unchanged signature; emits `failed:` terminal and routes `_error: failed` plus `on_error: failed` on the dispatch state.
- Factor the `policy_parse_scores` heredoc into a new module `scripts/little_loops/fsm/policy_parse_scores.py` so the two-pass test is a unit test rather than a shell harness, mirroring `scripts/little_loops/fsm/frontmatter_scores.py`:
  - `def main(argv: list[str] | None = None) -> int` — entry point invoked from the fragment (`python3 -m little_loops.fsm.policy_parse_scores <run_dir>`).
  - `def parse_scores(output: str) -> tuple[int, dict[str, str]]` — extracts aggregate and per-dimension scores.
  - `def _clean_slate(run_dir: Path) -> None` — unlinks `rubric-dim-*.txt` and `rubric-aggregate.txt` before writing (same contract as `frontmatter_scores._clean_slate`).

### Call Path

`policy_parse_scores` (shell action in `scripts/little_loops/loops/lib/policy-router.yaml`) -> `main` -> `_clean_slate` -> `parse_scores` -> write `rubric-dim-*.txt` -> `policy_table_dispatch` -> `parse_rules` / `evaluate_rules` (`scripts/little_loops/fsm/policy_rules.py`) -> `_error`/`on_error: failed`.

`serializeLoopYaml` -> `_serializeDecisionTable` -> `validate_fsm` (Python round-trip in `scripts/tests/test_policy_builder_node_gate.py`).

## Acceptance Criteria

- [ ] Two-pass scorer test proves an omitted dimension cannot retain its prior score; `rubric-aggregate.txt` is also reset.
- [ ] Decision-table YAML emits a `failed` terminal; `_error` and the dispatch state's `on_error` both route to it; a dispatch/scoring failure cannot report successful completion.
- [ ] Valid decision-table models still pass `validate_fsm` (runtime validation) in the Node gate round-trip test.
- [ ] Golden fixtures regenerated; full local suite passes.

## Scope Boundaries

Includes the two runtime fragment/emission defects only. Browser preview, validation, and editing defects are BUG-3486; catalog discovery is BUG-3490.

## Steps to Reproduce

1. Run the `policy_parse_scores` fragment twice in one temporary run directory, omitting a dimension on pass two; inspect the retained `rubric-dim-*.txt`.
2. Serialize the seeded decision-table model and inspect the `_error` sentinel: it names the first rule's target, not a failure state.

## Root Cause

The LLM score parser lacks clean-slate handling. `_serializeDecisionTable()` never emits a failure terminal and reuses the first outcome token for `_error`.

## Status

**Open** | Created: 2026-09-16 | Priority: P2
