---
id: 2852
title: Add a program-design stage to issue refinement naming types, signatures, and call path
type: ENH
priority: P2
status: open
discovered_by: ll-product-promotion
discovered_date: 2026-07-27
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
---

# ENH-2852: Add a program-design stage to issue refinement naming types, signatures, and call path

Origin: ll-product #ENH-050

## Summary

The refinement chain (`/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`) researches the codebase and identifies integration points, but never requires an issue to state the concrete **types, method signatures, and call path** the change will follow. That leaves the most rework-prone decisions to be made mid-implementation by `ll-auto` / `ll-parallel` / `ll-sprint`, where no human reviews the plan before code exists.

Add a program-design stage that makes an issue name its intended shape at the signature level before it is eligible for batch processing, and gate `/ll:confidence-check` on that section being present and specific.

## Motivation

Architecture-level refinement (which components, which files, which integration points) is already covered. Program design is the level below it and is the one currently skipped:

- What new or changed **types** does this introduce, and what are their fields?
- What are the **function/method signatures** being added or modified — names, parameters, return types?
- What is the **call path**: which caller reaches the new code, through what, and what does it do with the result?

An issue that answers these three questions has had its rework-prone decisions made under review. An issue that doesn't hands them to an agent mid-implementation, which is exactly where they are most expensive to get wrong and least visible when they are.

This is deliberately *not* a design doc stage. It is a short, concrete section — a handful of signatures and one call path — not prose about approach.

## Proposed Change

1. **Issue template** — add a `## Program Design` section with three required subsections: `Types`, `Signatures`, `Call Path`.
2. **Refinement** — extend the refinement chain to populate that section from codebase research: read the actual call sites and existing type definitions, then name the concrete shapes rather than describing them abstractly. A call-graph sketch (caller → callee → callee) is the expected form for `Call Path`.
3. **Gate** — `/ll:confidence-check` fails an issue whose `## Program Design` section is missing, empty, or non-specific (prose with no identifiers). Specificity check should be mechanical where possible: require at least one identifier that resolves against the repo, and at least one signature-shaped line.
4. **Batch eligibility** — `ll-auto` / `ll-parallel` / `ll-sprint` treat a failing confidence gate as they do today; no new blocking mechanism is needed if the gate is wired.

## Design Notes

- Keep the gate cheap and mostly deterministic. A grep/parse for identifiers that exist in the repo carries more signal than asking a model whether a section is "specific enough".
- **New identifiers cannot resolve against the repo by definition.** The repo-resolution requirement targets the *call-path anchors* — the existing callers, modules, and types the new code hooks into. The new names being introduced only need to be signature-*shaped* (parseable `name(params) -> ret` / dataclass-field lines), not resolvable. Conflating these would make the gate unpassable for any issue that adds code.
- **The mechanical check lives in a CLI, not in skill prose.** **Decided (epic review, 2026-07-27): implement inside `check_format_gaps()` as an `ll-issues format-check` extension — not a standalone `ll-verify-*` binary.** `/ll:confidence-check` shells out to `ll-issues format-check` — matching the project's deterministic-CLI-plus-skill pattern and making it independently testable. This drops the standalone-binary wiring (`_LL_PERMISSIONS`, `areas.md` allowlist, new `[project.scripts]` entry) from scope entirely.
- Small mechanical issues (a one-line config change, a docs fix) should be able to satisfy the section trivially or declare it not applicable — the gate must not become a tax on trivial work. Provide an explicit escape hatch and make it visible in the issue rather than silent.
- **Amendment path, not a prohibition.** The section is written during refinement, but a hard "the implementing agent must not rewrite it" rule contradicts existing machinery (`/ll:reconcile-issue` rewrites directive sections by design) and ignores queue-latency staleness — a design fixed at refine time can be invalidated by codebase changes before implementation starts. Instead: the implementing agent may deviate, but the deviation is *recorded* in the issue (a `Deviations` note under the section stating what changed and why), never silently rewritten over the original.
- **Interaction with autodev's deferral machinery.** A new hard failure mode in `/ll:confidence-check` surfaces in `autodev.yaml`'s `check_reconcile_needed` / `recheck_after_size_review` as readiness stagnation — a refined-but-design-less issue could burn a reconcile/spike remedy cycle before deferring. Decide explicitly: a missing/non-specific `## Program Design` section should route to the `/ll:reconcile-issue` remedy (it is exactly the kind of directive-section gap reconcile exists to fix), not defer immediately; only if the section is still failing after the remedy attempt should the issue defer, and then under a distinct machine reason code (e.g. `design_gate_failed`) rather than generic `low_readiness`, so `ll-issues deferred-triage` can distinguish it.
- **Rollout for the existing backlog.** Every currently open issue lacks the section; a hard gate would mass-defer the backlog on day one. **Decided (epic review, 2026-07-27): grandfather.** Issues refined before the gate ships (determined by refine timestamp / `discovered_date`) are exempt from the gate; bulk-populate is not pursued — it is more expensive, and grandfathering is reversible per-issue by simply re-refining.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Section schema is per-type JSON, already the single source of truth.** `scripts/little_loops/templates/enh-sections.json` (and sibling `bug-sections.json`/`feat-sections.json`) define `common_sections`/`type_sections`, each with `required`, `description`, `quality_guidance`, and `creation_template`. Add `Program Design` as a new `common_sections` entry (required for BUG/FEAT/ENH alike, per the issue's own scope) with `Types`/`Signatures`/`Call Path` as sub-bullets inside its `creation_template`, mirroring the existing `API/Interface` type-section's fenced-code-block placeholder shape — the closest existing analog for a signature-shaped subsection.
- **The required-heading half of the gate already exists; the specificity half does not.** `check_format_gaps()` in `scripts/little_loops/issue_parser.py` (`FormatGaps` dataclass, ~line 136; function ~line 201) diffs actual `##` headings against `_required_sections(sections_data)` and already populates `missing`/`empty`/`boilerplate` gap lists this way — a `## Program Design` heading missing or boilerplate-only is caught for free once added to the schema. What's net-new is *content-shape* validation (identifier resolves against the repo; line is signature-shaped) — no existing gap category checks section content beyond heading presence/non-template-equality, so this needs a new `FormatGaps` list field (e.g. `program_design_nonspecific`) plus new detection logic in `check_format_gaps()`, wired through `scripts/little_loops/cli/issues/format_check.py:cmd_format_check()`.
- **Model the CLI on `ll-verify-cli-allowlist`** (`scripts/little_loops/cli/verify_cli_allowlist.py`): pure `_run() -> tuple[int, dict]` helper (unit-testable without mocking `sys.argv`), a `main_verify_<name>()` wrapper using `cli_event_context(...)`, `stderr`-prefixed `ERROR:`, `stdout`-prefixed `OK:`, and registration in `scripts/pyproject.toml` `[project.scripts]` next to `ll-verify-decisions`. New `ll-` entry points also need a matching addition to `skills/configure/areas.md`'s "All ll- commands" preset and `little_loops.init.writers._LL_PERMISSIONS` (enforced by `ll-verify-cli-allowlist` itself, BUG-2764) — or, per the issue's Design Notes preference for an `ll-issues format-check` extension, this logic can live inside `check_format_gaps()` directly rather than as a standalone `ll-verify-*` binary.
- **Call-path anchor resolution has two existing mechanisms to reuse**: (1) `resolve_anchor()` in `scripts/little_loops/issues/anchors.py` — regex-based, language-agnostic, returns `None` (not an exception) when unresolved, already consumed by `anchor_sweep.py:_sweep_file()`'s `skipped_refs` counter; (2) `FallbackProvider.defines()`/`defines_scan_for()` in `scripts/little_loops/codequery/fallback.py` — AST-based exact resolution via `ll-code defines`, with a `CodeRef.confidence: "exact" | "heuristic"` field that's a ready-made vocabulary for reporting anchor-resolution confidence rather than a bare pass/fail.
- **No existing parser validates a free-text `name(params) -> ret` or dataclass-field line against nothing** (i.e., signature-*shape* independent of a real file) — this is genuinely net-new; the closest precedent (`anchors.py`'s `_ANCHOR_PATTERNS`) only matches lines inside real source files, not prose in an issue body.
- **`DeferReason` enum** (`scripts/little_loops/issue_lifecycle.py`, lines 58–79) is the established, single place new deferral reason codes are added — each existing member (`BLOCKED_BY_UNMET`, `REMEDIATION_STALLED`, `LOW_READINESS`, `GATE_BLOCKED`, `DECISION_UNRESOLVED`, `OVERSIZED_ATOMIC`, `READINESS_STAGNATED`) carries an inline comment citing its originating issue ID; `DESIGN_GATE_FAILED = "design_gate_failed"  # ENH-2852: program-design stage failed verification` follows the same convention. Consumers to update: `scripts/little_loops/cli/issues/set_status.py` (`--reason` flag), `scripts/little_loops/cli/issues/deferred_triage.py`, and `scripts/little_loops/loops/autodev.yaml`.
- **Reconcile-before-defer routing point**: `autodev.yaml`'s `recheck_after_size_review` state (~line 1435) already implements the exact shape this issue needs — it computes `GATE=PASS/FAIL`, checks a stagnation backstop, and (per BUG-2803's "pre-deferral remedy guarantee") arms a one-shot `reconcile`/`spike` remedy via run-dir handshake files (`autodev-pre-deferral-remedy-fired`) before any deferral write. A design-gate-caused FAIL should plug into this same discriminator chain as a new case — checked before the generic `low_readiness` write, routed once through `reconcile_current` (state defined around `check_reconcile_needed`, ~line 1165), and only deferred with `--reason design_gate_failed` if the post-remedy pass still fails. No new remedy infrastructure is needed — this reuses BUG-2803/FEAT-2751's existing machinery.
- **Escape-hatch precedent**: `testable: false` (documented in `docs/reference/ISSUE_TEMPLATE.md`) is the closer analog for a Program-Design not-applicable hatch than `outcome_gate_waived: true` — `testable: false` fully skips a phase and is auto-inferable via keyword heuristics in `skills/capture-issue/SKILL.md`/`skills/format-issue/SKILL.md`, whereas `outcome_gate_waived` only bypasses half of an AND-gate. A `program_design_not_applicable: true` flag should follow the `testable: false` shape (full skip, auto-inferable for trivial issues, checked by the new mechanical gate).
- **`confidence-check`'s existing hard-override pattern to extend**: `skills/confidence-check/SKILL.md` Phase 3 already has one hard override — "Learning Test Hard Override: if Phase 1.5 found any `missing`/`refuted` target, output `STOP — ADDRESS GAPS` regardless of aggregate score." A Program Design gate failure should use the identical override shape (independent of the five-criterion sum), and its frontmatter flag write-back should follow Phases 4.6–4.10's five-part convention: skip in `CHECK_MODE`, source from the new CLI's exit code (not risk-factor prose, since this must be deterministic per the issue's own Design Notes), write via `Edit` on frontmatter, be idempotent, and log a confirmation line.
- **No existing "Deviations" section/frontmatter convention** — `skills/manage-issue/SKILL.md`'s "Mismatch Handling Protocol" (~lines 325–331) handles plan/reality divergence interactively at implementation time but doesn't persist a structured deviation record on the issue file. The `Deviations` note this issue proposes would be new markdown-section convention, not an extension of existing machinery.

## Acceptance Criteria

- [ ] The issue template includes a `## Program Design` section with `Types`, `Signatures`, and `Call Path` subsections.
- [ ] The refinement chain populates that section with identifiers drawn from the actual codebase, not placeholders.
- [ ] `/ll:confidence-check` fails an issue with a missing or empty `## Program Design` section.
- [ ] `/ll:confidence-check` fails an issue whose section contains only prose with no repo-resolvable call-path anchors or signature-shaped lines.
- [ ] `/ll:confidence-check` passes an issue naming concrete types, signatures, and a call path — where repo-resolution is required only of call-path anchors, and new identifiers need only be signature-shaped.
- [ ] The specificity check is implemented deterministically inside `check_format_gaps()` / `ll-issues format-check` (decided — no standalone `ll-verify-*` binary), shelled out to by the skill and testable without an LLM.
- [ ] An explicit not-applicable escape hatch exists for trivial issues and is recorded in the issue body when used.
- [ ] Implementation-time deviations from the design are recorded in the issue as a visible `Deviations` note rather than overwriting the original section.
- [ ] The grandfathering rollout (decided) is implemented: issues refined before the gate ships are exempt, so shipping the gate does not mass-defer the current backlog.
- [ ] Tests cover: missing section, prose-only section, valid section (including unresolvable-but-signature-shaped new identifiers), and the escape hatch.
- [ ] The intervention cutover point (the SHA/date at which this gate is enabled) is recorded under `thoughts/` before the gate ships, so FEAT-2855 can retroactively compute the pre-intervention window from immutable git history (see Scope Boundary below).
- [ ] A confidence-check failure caused solely by the `## Program Design` gate routes to the reconcile remedy before any deferral, and a post-remedy deferral uses a distinct machine reason code, not generic `low_readiness`.

---

## Integration Map

_Added by `/ll:refine-issue` — based on codebase research:_

### Files to Modify
- `scripts/little_loops/templates/enh-sections.json` (+ `bug-sections.json`, `feat-sections.json`) — add `Program Design` to `common_sections`, with `Types`/`Signatures`/`Call Path` in its `creation_template`
- `scripts/little_loops/issue_parser.py` — extend `FormatGaps` dataclass (~line 136) with a new gap list (e.g. `program_design_nonspecific`) and add detection logic to `check_format_gaps()` (~line 201)
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` surfaces the new gap in `--format json`/`text` output
- `skills/confidence-check/SKILL.md` — Phase 3 gains a new hard override (alongside the existing Learning Test Hard Override); Phases 4.6–4.10's flag-write pattern gains a new phase for the Program Design gate flag
- `scripts/little_loops/issue_lifecycle.py` — `DeferReason` enum (lines 58–79) gains `DESIGN_GATE_FAILED = "design_gate_failed"`
- `scripts/little_loops/loops/autodev.yaml` — `recheck_after_size_review` (~line 1435) gains a design-gate-caused-FAIL discriminator that routes once through `reconcile_current` before deferring with the new reason code
- `scripts/little_loops/cli/issues/deferred_triage.py` — recognize `design_gate_failed` for reporting; specifically the `_REASON_RANK` dict, which needs the new code inserted at an explicit rank with a dated `# ENH-2852:` rationale comment following the existing `# FEAT-2751:`/`# BUG-2734:` convention

### Dependent Files (Callers/Consumers)
- `scripts/little_loops/cli/issues/set_status.py` — `--reason` flag plumbing consumes `DeferReason` members
- `scripts/little_loops/issue_template.py` (`load_issue_sections()`, `assemble_issue_markdown()`) — consumes the section schema for new-issue creation
- `skills/format-issue/SKILL.md`, `skills/capture-issue/SKILL.md`, `skills/ready-issue/SKILL.md` — all read the same `*-sections.json` schema

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/sequence.py` — references `check_format_gaps()` logic for drift detection; new gap category flows through here too
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` state gates on the exit code of `ll-issues format-check "$ID"` (i.e. `FormatGaps.has_gaps`); a new gap category participates automatically, but the state's comment block enumerating the gap taxonomy should mention the new category
- `scripts/little_loops/issue_manager.py` — reads `deferred_reason` off issues; consumes `DeferReason` values including the new `design_gate_failed`
- `scripts/little_loops/init/writers.py` (`_LL_PERMISSIONS` tuple) + `skills/configure/areas.md` ("All ll- commands" preset) — only relevant if the mechanical checker ships as a standalone `ll-verify-*` binary (enforced by `ll-verify-cli-allowlist`, BUG-2764); not needed if implemented inside `check_format_gaps()` per the Design Notes' stated preference

### Similar Patterns
- `scripts/little_loops/cli/verify_cli_allowlist.py` — `_run() -> (exit_code, data)` / `main_verify_*()` split, the template for a new mechanical checker if implemented as a standalone `ll-verify-*` binary
- `scripts/little_loops/issues/anchors.py:resolve_anchor()` + `scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` — existing anchor-resolution-with-skip-counting pattern for the call-path-anchor check
- `scripts/little_loops/codequery/fallback.py:FallbackProvider.defines()`/`defines_scan_for()` — AST-based exact resolution with a `confidence: "exact"|"heuristic"` field

### Tests
- `scripts/tests/test_ll_issues_format_check.py`, `scripts/tests/test_issue_parser.py` — extend for the new gap category
- `scripts/tests/test_confidence_check_skill.py` — extend for the new hard-override gate
- `scripts/tests/test_autodev_loop.py`, `scripts/tests/test_autodev_decision_gate.py` — extend for the `design_gate_failed` routing
- `scripts/tests/test_verify_cli_allowlist.py` — model for a new CLI's test file if a standalone `ll-verify-*` binary is chosen

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py::TestFormatGradedChecker` — mirror `test_boilerplate_body_reports_boilerplate`: one new method asserting only the new gap field populates, all six others stay empty
- `scripts/tests/test_ll_issues_format_check.py` — the exact-dict JSON assertions in `test_clean_issue_json_output` and the gapped-issue JSON test need the new `FormatGaps` key added or they break; add a text-mode substring test mirroring the `prose_dep_drift` block
- `scripts/tests/test_autodev_loop.py::TestRecheckAfterSizeReviewStagnationBackstop` — add a sibling test class following the `readiness_stagnated` pattern: string-assertion that the action references `design_gate_failed` and any new marker files, plus an ordering test if the new branch must short-circuit `low_readiness`
- `scripts/tests/test_issues_anchors.py` — closest existing pattern (per-language `resolve_anchor()` fixture classes) to follow for new signature/call-path-shape parsing tests, since no parser for `name(params) -> ret` prose currently exists
- `scripts/tests/test_codequery_fallback.py` — real-git-repo fixture pattern (`_init_repo`/`_write_and_commit`/`monkeypatch.chdir`) to follow if call-path anchor resolution reuses `FallbackProvider.defines()`
- `scripts/tests/test_issue_lifecycle.py` — no existing test asserts `DeferReason` enum membership directly (only string values via `test_autodev_loop.py`/`test_issues_cli.py`/`test_set_status_cli.py`/`test_builtin_loops.py`); add here if exhaustive membership coverage is wanted

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### check_format_gaps` hardcodes "seven gap classes" with one bullet per field; needs an eighth bullet and the count updated. The `#### deferred-triage` section also enumerates every `DeferReason` code by name in ranked prose; `design_gate_failed` needs slotting into that list to match `_REASON_RANK`
- `docs/reference/ISSUE_TEMPLATE.md` § **Common Sections (All Issue Types)** — doc-of-record for required sections shared across issue types; needs a `Program Design` entry to match the new `common_sections` schema entry, or the doc drifts from the template JSON
- `commands/ready-issue.md` § **Dependency Status** — currently reads `prose_dep_drift`/`stale_prose_dep` individually from `format-check --format json`; decide whether Program Design should also block the readiness verdict (join this checklist) or stay confidence-check-only
- `scripts/little_loops/cli/issues/format_check.py` — `add_format_check_parser()`'s `help=` string and `cmd_format_check()`'s docstring both hardcode the literal gap-class list (`"missing/renamed/empty/boilerplate/malformed_id/prose_dep_drift/stale_prose_dep"`) as prose duplicates, independent of the dataclass fields — both need the new category name appended

## Scope Boundary

**Note** (added by `/ll:audit-issue-conflicts`; revised by epic review 2026-07-27): EPIC-2856 originally required a one-off manual pre-intervention sample of FEAT-2855's maintainability signals before this gate ships. That is unnecessary: every FEAT-2855 signal is computed from `git log`, which is immutable, so the tool can retroactively compute any pre-intervention window once it exists. What must be captured up front is only the **cutover point** — a short note under `thoughts/` recording the SHA and date at which this issue's gate was enabled (plus the caveat that `.ll/history.db` attribution for old windows depends on manual retention policy). Recording that stamp is a prerequisite of this issue, not part of FEAT-2855's scope.


## Session Log
- `/ll:wire-issue` - 2026-07-27T16:52:50 - `633b73fa-0e52-4f41-a802-c8a7e1eea54d.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:20:16 - `405e66e4-2b70-4b13-ac32-d29af45ab631.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T15:59:42 - `29cf17b6-04b4-4b01-9444-64f1bfdbdaa5.jsonl`
