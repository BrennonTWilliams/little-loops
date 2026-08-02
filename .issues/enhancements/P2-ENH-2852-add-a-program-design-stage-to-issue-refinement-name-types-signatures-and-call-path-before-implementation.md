---
id: ENH-2852
title: Add a program-design stage to issue refinement naming types, signatures, and
  call path
type: ENH
priority: P2
status: done
discovered_date: 2026-07-27
completed_at: '2026-07-27T22:51:05Z'
epic: EPIC-2856
parent: EPIC-2856
labels:
- rework
- verification
blocks:
- ENH-2870
relates_to:
- ENH-2871
confidence_score: 94
outcome_confidence: 79
score_complexity: 15
score_test_coverage: 22
score_ambiguity: 24
score_change_surface: 18
spike_needed: true
spike_attempted: true
spike_completed: true
---

# ENH-2852: Add a program-design stage to issue refinement naming types, signatures, and call path

> **Split (2026-07-27)**: this issue now covers the **core gate only** — section schema,
> `check_format_gaps()` specificity grading, `ll-issues format-check` surfacing, the
> `/ll:confidence-check` hard override, grandfathering, and tests. It ships **fail-open**
> (no cutover stamp written), so the gate is off everywhere until armed. Split out:
> **ENH-2870** (autodev reconcile-before-defer routing, `DeferReason.DESIGN_GATE_FAILED`,
> and arming the gate by writing the stamp — blocked by this issue) and **ENH-2871**
> (`manage-issue` Deviations-note writer — independent).

## Summary

The refinement chain (`/ll:refine-issue` → `/ll:wire-issue` → `/ll:confidence-check`) researches the codebase and identifies integration points, but never requires an issue to state the concrete **types, method signatures, and call path** the change will follow. That leaves the most rework-prone decisions to be made mid-implementation by `ll-auto` / `ll-parallel` / `ll-sprint`, where no human reviews the plan before code exists.

Add a program-design stage that makes an issue name its intended shape at the signature level before it is eligible for batch processing, and gate `/ll:confidence-check` on that section being present and specific.

## Current Behavior

`/ll:refine-issue` and `/ll:wire-issue` populate an "Integration Map" (files, callers, patterns, tests) but stop at the architecture level — which files and integration points are involved. Neither stage requires the issue to name the concrete types, function/method signatures, or call path the implementation will follow. `/ll:confidence-check` scores readiness without checking for this content, so an issue can pass the gate and reach `ll-auto`/`ll-parallel`/`ll-sprint` with signature-level decisions still unmade, left for the implementing agent to decide unreviewed.

## Expected Behavior

Every BUG/FEAT/ENH issue (unless explicitly exempted via a `program_design_not_applicable: true` escape hatch, or grandfathered per the cutover stamp) carries a `## Program Design` section with `Types`, `Signatures`, and `Call Path` subsections populated with real, repo-grounded identifiers before it is eligible for batch implementation. `/ll:confidence-check` fails deterministically (via `ll-issues format-check`) when that section is missing, empty, or contains only non-specific prose. (Routing that failure through the reconcile-before-defer remedy instead of an immediate `low_readiness` deferral is ENH-2870's scope; until it lands, no stamp is written and the gate stays off.)

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
- **New identifiers are never *required* to resolve — and never required *not* to.** The repo-resolution requirement targets the *call-path anchors* — the existing callers, modules, and types the new code hooks into. The new names being introduced only need to be signature-*shaped* (parseable `name(params) -> ret` / dataclass-field lines), not resolvable. Conflating these would make the gate unpassable for any issue that adds code. Equally important (surfaced by the spike's own promotion failure): the resolver contract must be **resolution-indifferent for new identifiers** — a new identifier that *happens* to resolve (because its defining code lands in the repo between refinement and gate re-check, or because the name collides with an existing symbol) must never flip the verdict. Do NOT implement this as "exclude symbols defined in the diff/PR under review": at format-check time (refinement, the autodev gate) no diff exists yet, so diff-exclusion is undefined exactly when the gate runs. The rule is simply: anchors extracted from `Call Path` must have ≥1 resolving; everything else is graded on shape alone, with resolution status recorded as informational only.
- **The mechanical check lives in a CLI, not in skill prose.** **Decided (epic review, 2026-07-27): implement inside `check_format_gaps()` as an `ll-issues format-check` extension — not a standalone `ll-verify-*` binary.** `/ll:confidence-check` shells out to `ll-issues format-check` — matching the project's deterministic-CLI-plus-skill pattern and making it independently testable. This drops the standalone-binary wiring (`_LL_PERMISSIONS`, `areas.md` allowlist, new `[project.scripts]` entry) from scope entirely.
- Small mechanical issues (a one-line config change, a docs fix) should be able to satisfy the section trivially or declare it not applicable — the gate must not become a tax on trivial work. Provide an explicit escape hatch and make it visible in the issue rather than silent.
- **Amendment path, not a prohibition.** The section is written during refinement, but a hard "the implementing agent must not rewrite it" rule contradicts existing machinery (`/ll:reconcile-issue` rewrites directive sections by design) and ignores queue-latency staleness — a design fixed at refine time can be invalidated by codebase changes before implementation starts. Instead: the implementing agent may deviate, but the deviation is *recorded* in the issue (a `Deviations` note under the section stating what changed and why), never silently rewritten over the original. The writer for that note is **ENH-2871** (split out); this issue only establishes the convention.
- **Interaction with autodev's deferral machinery — moved to ENH-2870.** The reconcile-before-defer routing, the `design_gate_failed` reason code, and all `DeferReason` consumer updates ship there. The safety invariant this issue owns is only: the gate stays off (no stamp) until ENH-2870's routing exists, so a design-gate failure can never reach autodev's deferral machinery unrouted.
- **Grandfathering must be honored at every `check_format_gaps()` consumer, not just `/ll:confidence-check`** (added epic review, 2026-07-27). Adding `Program Design` to `common_sections` makes it required for BUG/FEAT/ENH alike, and the new gap category then propagates to every consumer of the gap set — `rn-remediate.yaml`'s `ensure_formatted` state (which gates on `ll-issues format-check`'s exit code, i.e. `FormatGaps.has_gaps`), `ll-issues sequence`'s drift detection, and `commands/ready-issue.md`. If the exemption lives only in the skill's override logic, the existing backlog trips those other consumers on day one — exactly the mass-failure the grandfathering decision exists to prevent. The exemption therefore belongs in `check_format_gaps()` itself, so every consumer inherits it from one place.
- **`ready-issue` scope — decided (epic review, 2026-07-27): confidence-check only.** `commands/ready-issue.md` reads `prose_dep_drift`/`stale_prose_dep` individually from `format-check --format json` and must *not* add the Program Design gap to its blocking set. `ready-issue`'s job is to make an issue implementation-ready, and a missing program design is something it should surface and help fill, not something it should refuse on — the blocking decision happens once, at the confidence gate, where the reconcile-before-defer remedy path exists. Two gates enforcing the same requirement with different remedies is how an issue gets stuck between them.
- **The `Deviations` note needs a writer, or it is dead convention** (added epic review, 2026-07-27). Decided: give it a writer in `manage-issue` — **moved to ENH-2871** (split out; independent of the gate, can land before or after arming).
- **Rollout for the existing backlog.** Every currently open issue lacks the section; a hard gate would mass-defer the backlog on day one. **Decided (epic review, 2026-07-27): grandfather.** Issues refined before the gate ships are exempt from the gate; bulk-populate is not pursued — it is more expensive, and grandfathering is reversible per-issue by simply re-refining.
- **The grandfather cutoff IS the cutover stamp — one date, one file** (decided 2026-07-27; path pinned 2026-07-27). The stamp lives at **`.ll/program-design-cutover.json`** — NOT under `thoughts/`, which is a convention of this repo that target projects are not guaranteed to have; `.ll/` is the one directory little-loops guarantees in any installed project (it holds `ll-config.json` and `decisions.d/`, both committed, so the stamp is shared via git like they are). Schema: `{"sha": "<full 40-char SHA>", "date": "YYYY-MM-DD"}` — exactly these two keys, ISO date, machine-readable. This is the single source of truth for "before the gate shipped": `check_format_gaps()` reads the stamped date and exempts issues whose `discovered_date` (or refine timestamp from the Session Log, which takes precedence when both exist) predates it. Do not introduce a second cutoff constant in code or config — two dates that can diverge is how a grandfathered issue trips the gate anyway. FEAT-2867 and FEAT-2855 parse the same stamp file at the same path for their window comparisons, so the exemption boundary and the measurement boundary are guaranteed identical. **Boundary comparison pinned (2026-07-27): exemption applies iff the issue's timestamp is strictly earlier than the stamped `date`** (`issue_date < stamp_date`; same-day issues are NOT exempt). Because most of this epic's issues share a `discovered_date` equal to the likely stamp date, the stamp must be written with a `date` of the day *after* the gate merges (the SHA still records the exact commit) — this makes every pre-gate issue strictly earlier and avoids same-day ambiguity without SHA-ancestry lookups in `check_format_gaps()`. If the refine timestamp from the Session Log is present but unparseable, fall back to `discovered_date` rather than failing the exemption check.
- **No stamp → gate off (fail open), decided 2026-07-27.** `check_format_gaps()` is package code, but the stamp is a per-project file — every downstream install and fresh `ll-init` project starts without one. When `.ll/program-design-cutover.json` is absent (or unparseable), the Program Design gap check is skipped entirely for all issues: the gate is opt-in per project, armed by writing the stamp. This matches `check_format_gaps()`'s existing fail-open convention (cf. its `issue_statuses=None` handling) and prevents the mass-deferral failure mode in consumer projects. Arming is a documented manual step (write the file with the current SHA + date); wiring it into `ll-init`/`/ll:configure` is optional follow-up, not in scope here. For this repo, writing the stamp is **ENH-2870's final AC** (split out) — arming is only safe once the reconcile-before-defer routing exists, and that routing is ENH-2870. This issue ships unstamped: gate off everywhere.

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

- [x] The issue template includes a `## Program Design` section with `Types`, `Signatures`, and `Call Path` subsections.
- [x] The refinement chain populates that section with identifiers drawn from the actual codebase, not placeholders.
- [x] `/ll:confidence-check` fails an issue with a missing or empty `## Program Design` section.
- [x] `/ll:confidence-check` fails an issue whose section contains only prose with no repo-resolvable call-path anchors or signature-shaped lines.
- [x] `/ll:confidence-check` passes an issue naming concrete types, signatures, and a call path — where repo-resolution is required only of call-path anchors, and new identifiers need only be signature-shaped; a new identifier that happens to resolve (e.g. after its code is committed) must not change the verdict, and a test covers this.
- [x] The specificity check is implemented deterministically inside `check_format_gaps()` / `ll-issues format-check` (decided — no standalone `ll-verify-*` binary), shelled out to by the skill and testable without an LLM.
- [x] An explicit not-applicable escape hatch exists for trivial issues and is recorded in the issue body when used.
- [x] ~~Implementation-time deviations recorded via a `Deviations` note with a writer in `manage-issue`~~ — **moved to ENH-2871**. This issue only ensures the grading logic tolerates an appended `Deviations` subsection (inert to specificity — anchors/signatures are read from `Types`/`Signatures`/`Call Path` only).
- [x] The grandfathering rollout (decided) is implemented: issues refined before the gate ships are exempt, so shipping the gate does not mass-defer the current backlog.
- [x] The grandfather cutoff is read from the `.ll/program-design-cutover.json` cutover stamp (decided: no second cutoff constant anywhere) using strictly-earlier-than-stamp-date comparison (decided; the stamp is dated the day after the gate merges); grandfathering is implemented inside `check_format_gaps()` so every consumer inherits it; a test asserts a grandfathered issue produces no Program Design gap through `ll-issues format-check`, and therefore does not trip `rn-remediate.yaml`'s `ensure_formatted` or `ll-issues sequence` drift detection.
- [x] When the cutover stamp is absent or unparseable, the Program Design gap check is skipped for all issues (gate off, fail open — decided); a test asserts an unstamped project produces no Program Design gap for a section-less issue.
- [x] `commands/ready-issue.md`'s blocking set is unchanged (decided: confidence-check only); `ready-issue` may surface a missing Program Design section but does not refuse on it.
- [x] Tests cover: missing section, prose-only section, valid section (including unresolvable-but-signature-shaped new identifiers), and the escape hatch.
- [x] The stamp-reading code in `check_format_gaps()` parses `.ll/program-design-cutover.json` (`{"sha": ..., "date": ...}`, decided path + schema) — but **writing** the stamp (arming the gate) is ENH-2870's final AC, not this issue's; this issue merges unstamped, gate off everywhere.
- [ ] ~~Reconcile-before-defer routing with a distinct machine reason code~~ — **moved to ENH-2870** (blocked by this issue); intentionally left unchecked here, as no part of it is in this issue's scope.

---

## Integration Map

_Added by `/ll:refine-issue` — based on codebase research:_

### Files to Modify
- `scripts/little_loops/templates/enh-sections.json` (+ `bug-sections.json`, `feat-sections.json`) — add `Program Design` to `common_sections`, with `Types`/`Signatures`/`Call Path` in its `creation_template`
- `scripts/little_loops/issue_parser.py` — extend `FormatGaps` dataclass (~line 136) with a new gap list (e.g. `program_design_nonspecific`) and add detection logic to `check_format_gaps()` (~line 201)
- `scripts/little_loops/cli/issues/format_check.py` — `cmd_format_check()` surfaces the new gap in `--format json`/`text` output
- `skills/confidence-check/SKILL.md` — Phase 3 gains a new hard override (alongside the existing Learning Test Hard Override); Phases 4.6–4.10's flag-write pattern gains a new phase for the Program Design gate flag
- ~~`issue_lifecycle.py` `DeferReason`, `autodev.yaml` routing, `deferred_triage.py` `_REASON_RANK`~~ — **moved to ENH-2870**

### Dependent Files (Callers/Consumers)
- ~~`set_status.py` `--reason` plumbing~~ — **moved to ENH-2870**
- `scripts/little_loops/issue_template.py` (`load_issue_sections()`, `assemble_issue_markdown()`) — consumes the section schema for new-issue creation
- `skills/format-issue/SKILL.md`, `skills/capture-issue/SKILL.md`, `skills/ready-issue/SKILL.md` — all read the same `*-sections.json` schema
- ~~`skills/manage-issue/SKILL.md` `Deviations`-writing step~~ — **moved to ENH-2871**
- `scripts/little_loops/loops/rn-remediate.yaml` (`ensure_formatted`) and `scripts/little_loops/cli/issues/sequence.py` — inherit the new gap category automatically via `FormatGaps.has_gaps`; both must also inherit the grandfathering exemption, which is why it lives in `check_format_gaps()` rather than in skill prose

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/issues/sequence.py` — references `check_format_gaps()` logic for drift detection; new gap category flows through here too
- `scripts/little_loops/loops/rn-remediate.yaml` — `ensure_formatted` state gates on the exit code of `ll-issues format-check "$ID"` (i.e. `FormatGaps.has_gaps`); a new gap category participates automatically, but the state's comment block enumerating the gap taxonomy should mention the new category
- ~~`issue_manager.py` `deferred_reason` consumption~~ — **moved to ENH-2870**
- `scripts/little_loops/init/writers.py` (`_LL_PERMISSIONS` tuple) + `skills/configure/areas.md` ("All ll- commands" preset) — only relevant if the mechanical checker ships as a standalone `ll-verify-*` binary (enforced by `ll-verify-cli-allowlist`, BUG-2764); not needed if implemented inside `check_format_gaps()` per the Design Notes' stated preference

### Similar Patterns
- `scripts/little_loops/cli/verify_cli_allowlist.py` — `_run() -> (exit_code, data)` / `main_verify_*()` split, the template for a new mechanical checker if implemented as a standalone `ll-verify-*` binary
- `scripts/little_loops/issues/anchors.py:resolve_anchor()` + `scripts/little_loops/issues/anchor_sweep.py:_sweep_file()` — existing anchor-resolution-with-skip-counting pattern for the call-path-anchor check
- `scripts/little_loops/codequery/fallback.py:FallbackProvider.defines()`/`defines_scan_for()` — AST-based exact resolution with a `confidence: "exact"|"heuristic"` field

### Tests
- `scripts/tests/test_ll_issues_format_check.py`, `scripts/tests/test_issue_parser.py` — extend for the new gap category
- `scripts/tests/test_confidence_check_skill.py` — extend for the new hard-override gate
- ~~`test_autodev_loop.py`, `test_autodev_decision_gate.py` `design_gate_failed` routing~~ — **moved to ENH-2870**
- `scripts/tests/test_verify_cli_allowlist.py` — model for a new CLI's test file if a standalone `ll-verify-*` binary is chosen

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_parser.py::TestFormatGradedChecker` — mirror `test_boilerplate_body_reports_boilerplate`: one new method asserting only the new gap field populates, all six others stay empty
- `scripts/tests/test_ll_issues_format_check.py` — the exact-dict JSON assertions in `test_clean_issue_json_output` and the gapped-issue JSON test need the new `FormatGaps` key added or they break; add a text-mode substring test mirroring the `prose_dep_drift` block
- ~~`test_autodev_loop.py` sibling stagnation-backstop class~~ — **moved to ENH-2870**
- `scripts/tests/test_issues_anchors.py` — closest existing pattern (per-language `resolve_anchor()` fixture classes) to follow for new signature/call-path-shape parsing tests, since no parser for `name(params) -> ret` prose currently exists
- `scripts/tests/test_codequery_fallback.py` — real-git-repo fixture pattern (`_init_repo`/`_write_and_commit`/`monkeypatch.chdir`) to follow if call-path anchor resolution reuses `FallbackProvider.defines()`
- ~~`test_issue_lifecycle.py` `DeferReason` membership coverage~~ — **moved to ENH-2870**

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `#### check_format_gaps` hardcodes "seven gap classes" with one bullet per field; needs an eighth bullet and the count updated. (~~The `#### deferred-triage` `DeferReason` list update~~ — **moved to ENH-2870**)
- `docs/reference/ISSUE_TEMPLATE.md` § **Common Sections (All Issue Types)** — doc-of-record for required sections shared across issue types; needs a `Program Design` entry to match the new `common_sections` schema entry, or the doc drifts from the template JSON
- `commands/ready-issue.md` § **Dependency Status** — **decided (epic review, 2026-07-27): confidence-check only**, so its blocking set stays as-is. The only change here is optional surfacing (report the gap, don't refuse on it); see Design Notes
- `scripts/little_loops/cli/issues/format_check.py` — `add_format_check_parser()`'s `help=` string and `cmd_format_check()`'s docstring both hardcode the literal gap-class list (`"missing/renamed/empty/boilerplate/malformed_id/prose_dep_drift/stale_prose_dep"`) as prose duplicates, independent of the dataclass fields — both need the new category name appended

## Scope Boundaries

**Note** (added by `/ll:audit-issue-conflicts`; revised by epic review 2026-07-27): EPIC-2856 originally required a one-off manual pre-intervention sample of FEAT-2855's maintainability signals before this gate ships. That is unnecessary: every FEAT-2855 signal is computed from `git log`, which is immutable, so the tool can retroactively compute any pre-intervention window once it exists. What must be captured up front is only the **cutover point** — `.ll/program-design-cutover.json` (`{"sha": ..., "date": ...}`; see Design Notes for the pinned path/schema and the no-stamp fail-open rule) recording the SHA and date at which this issue's gate was enabled (plus the caveat that `.ll/history.db` attribution for old windows depends on manual retention policy). Recording that stamp is a prerequisite of *arming the gate* — now ENH-2870's final AC (split 2026-07-27), not part of FEAT-2855's scope. This issue only ships the stamp-*reading* code.


## Impact

- **Priority**: P2 - Rework-prone signature-level decisions currently reach unreviewed implementation agents; this closes the largest remaining gap in the refinement chain, but it's a process/gate change rather than a user-facing defect.
- **Effort**: Medium (post-split) - touches the section schema (3 files), `check_format_gaps()`/`FormatGaps` + `format_check.py`, the `/ll:confidence-check` hard override, and grandfathering/stamp-reading. Autodev routing/`DeferReason`/stamp-arming moved to ENH-2870; the `manage-issue` deviation writer to ENH-2871.
- **Risk**: Low-Medium (post-split) - ships fail-open (unstamped), so the gate is off everywhere until ENH-2870 arms it; mass-deferral requires both a stamped project and broken grandfathering, and the specificity check is deterministic rather than LLM-judged.
- **Breaking Change**: No - additive section/gate; grandfathered issues are unaffected until re-refined.

## Resolution

_Implemented by `/ll:manage-issue` on 2026-07-27._

The core gate ships **fail-open**: this repo writes no
`.ll/program-design-cutover.json`, and `ll-issues format-check --all` across the full
backlog reports zero Program Design gaps. Arming it is ENH-2870's final AC.

**What landed**

- `scripts/little_loops/issues/program_design.py` (new) — promotes the spike's proven
  contract to production: `parse_signature_lines()`, `extract_call_path_anchors()`,
  `grade_program_design()`, `git_grep_resolver()`, plus the stamp/grandfathering half
  (`read_cutover_stamp()`, `issue_design_timestamp()`, `program_design_gate_active()`).
  Two changes beyond the spike: evidence is read from `Types`/`Signatures`/`Call Path`
  only (so an appended `Deviations` note is inert both ways — ENH-2871's convention), and
  `_is_true()` coerces the frontmatter flag, since `parse_frontmatter` yields strings and
  a bare `is True` check would have made the escape hatch silently dead.
- `issue_parser.py` — `FormatGaps.program_design_nonspecific`; `_gate_program_design()`
  filters `Program Design` out of the *required* set for both `check_format_gaps()` and
  `is_formatted()` when the gate is off, so grandfathering suppresses the `missing`/
  `empty` entries too, not just the specificity one. Without that the schema change alone
  would have flagged every pre-existing issue on day one.
- `templates/{bug,feat,enh}-sections.json` — `Program Design` common section with a
  `Types`/`Signatures`/`Call Path` creation template.
- `cli/issues/format_check.py`, `skills/confidence-check/SKILL.md` (Phase 1.6 + Program
  Design Hard Override), `loops/rn-remediate.yaml`, `commands/ready-issue.md`
  (surface-only, non-blocking, as decided), `docs/reference/API.md`,
  `docs/reference/ISSUE_TEMPLATE.md`.

**Verification**: 29 new tests in `scripts/tests/test_program_design_gate.py` + 4 CLI
tests in `test_ll_issues_format_check.py`; full suite 16,681 passed (the 4 failures in
`test_builtin_loops`/`test_general_task_loop`/`test_prose_dep_sweep_gate` reproduce on a
clean tree and are unrelated). `ruff check`, `ruff format`, `mypy` (276 files),
`ll-verify-docs` all clean.

**Deliberately not done**: the spike at `scripts/tests/spike/program_design_specificity/`
stays in place, matching the `fsm_continuity_compaction` precedent for promoted spikes.


## Status

**Open** | Created: 2026-07-27 | Priority: P2

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-07-27 (re-scored post-split)_

**Readiness Score**: 94/100 → PROCEED
**Outcome Confidence**: 79/100 → HIGH

Post-split re-score: scope is now the core gate only (~6 files, 2 subsystems: section-schema JSONs + `issue_parser.py`/`format_check.py` + the confidence-check skill override). Ships unstamped/fail-open, so the gate is off everywhere on day one — the change-surface and complexity risks that held outcome confidence at 64 moved to ENH-2870 (routing + arming) and ENH-2871 (Deviations writer). All prior concerns resolved or relocated:

### Concerns
- ~~Large, multi-subsystem change (9+ files) with a shared cutover-stamp contract~~ — resolved by the split: this issue only *reads* the stamp; writing it (and the FEAT-2855/FEAT-2867 timing coupling) is ENH-2870's final AC.
- ~~Re-running the spike suite showed **10/11 passing**: `TestRealRepoResolution::test_real_repo_anchors_resolve_via_git_grep` failed because `grade_program_design` — asserted as the "genuinely new, must stay unresolved" identifier — is itself defined and git-tracked inside the spike file, so `git grep` resolves it.~~ **Resolved 2026-07-27**: the failing assertion tested the wrong property. The contract is now resolution-indifference for new identifiers (see Design Notes) — a new identifier that happens to resolve must never flip the verdict; only Call Path anchors carry a resolution *requirement*. The spike test was corrected to assert this and the suite is back to 11/11. (The earlier suggestion to "exclude symbols defined in the diff/PR" was rejected: no diff exists at format-check time.)

### Outcome Risk Factors
_None at the current threshold (79 ≥ 65). Prior factors retired: the 9+-site enumeration shrank to ~6 via the split (autodev routing → ENH-2870); the signature-shape parser and grading split are spike-proven (11/11 after the resolver-contract fix); the git-grep-resolves-newly-committed-identifiers edge case was resolved by the resolution-indifference contract (see Design Notes)._

## Spike Results

_Added by `/ll:spike` on 2026-07-27_

**Retired risks**

| Risk (from Outcome Risk Factors) | Proven by | Result |
|----------------------------------|-----------|--------|
| No precedent for the signature-shape prose parser; regex may be too strict (mass-defers good issues) | `TestSignatureShape::test_accepts_varied_real_signature_shapes` | ✓ pass |
| ...or too loose (gate inert — English prose parses as signatures) | `TestSignatureShape::test_rejects_prose_that_merely_contains_parentheses`, `TestGrading::test_prose_only_section_is_not_specific` | ✓ pass |
| New-vs-anchor split may be mechanically unimplementable (AC-3 vs AC-5 conflict) | `TestGrading::test_new_identifiers_need_only_be_shape_valid`, `TestGrading::test_unresolvable_call_path_anchors_fail` | ✓ pass |
| Repo-resolution reuse of `defines_scan_for()`'s git-grep shape may not resolve real anchors | `TestRealRepoResolution::test_real_repo_anchors_resolve_via_git_grep` (resolves `check_format_gaps`/`cmd_format_check` in this repo; verdict is indifferent to whether the new `grade_program_design` resolves) | ✓ pass |
| Missing/empty section handling | `TestGrading::test_missing_or_empty_section_is_not_specific` | ✓ pass |
| isolation guard (AST sniff: no `little_loops` import) | `TestIsolation::test_spike_does_not_import_production_core` | ✓ pass |

**Proven contract**: a `## Program Design` body is *specific* iff it carries ≥1
signature-shaped line **and** ≥1 `Call Path` anchor that resolves against the repo.
Whole-line anchoring is what separates signatures from prose; anchors are extracted from
the `Call Path` subsection only, so newly-introduced identifiers are never required to
resolve — **and never required *not* to** (amended 2026-07-27): a new identifier's
resolution status is informational only and must never flip the verdict, since the
identifier starts resolving the moment its implementation is committed.

**Finding worth carrying into implementation**: the first regex draft rejected
`dict[str, list[int]]` — a flat `\[[^\]]*\]` subscript stops at the inner bracket. Nested
generics must be handled (one nesting level suffices) or the gate is unpassable for any
issue naming a realistic return type.

**Spike location**: `scripts/tests/spike/program_design_specificity/`
**Plan**: `.ll/spikes/spike-ENH-2852.md`
**Verification**: 11 spike tests + 239 regression tests pass across 2 commands.
**Promotion**: move to `scripts/little_loops/spike/program_design_specificity/` (or fold
directly into `check_format_gaps()`) in a separate PR.

## Session Log
- `/ll:manage-issue` - 2026-07-27T22:50:13 - `6577d800-d15d-4962-91d5-5f38934803ff.jsonl`
- `/ll:confidence-check` - 2026-07-27T22:30:00 - `bb61a6ce-43ed-4be8-ad81-6e1ae13a8d93.jsonl`
- `/ll:confidence-check` - 2026-07-27T21:58:00 - `05f19764-4660-46a7-81ad-bef2f66b9679.jsonl`
- `/ll:confidence-check` - 2026-07-27T00:00:00 - `ea02e551-ac6e-4d98-ac1d-084d06c96d7c.jsonl`
- `/ll:spike` - 2026-07-27T21:45:42 - `d2141626-0669-4971-b4bc-52d0bc74f1e2.jsonl`
- `/ll:confidence-check` - 2026-07-27T00:00:00 - `85951f3a-b89e-434d-8a30-06b6640ed45e.jsonl`
- `/ll:format-issue` - 2026-07-27T20:01:45 - `5d7e896c-f17c-402a-875f-cf4d9906c0a7.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T19:42:08 - `e2303183-4e52-4649-af90-4b53254bbda4.jsonl`
- `/ll:wire-issue` - 2026-07-27T16:52:50 - `633b73fa-0e52-4f41-a802-c8a7e1eea54d.jsonl`
- `/ll:refine-issue` - 2026-07-27T16:20:16 - `405e66e4-2b70-4b13-ac32-d29af45ab631.jsonl`
- `/ll:audit-issue-conflicts` - 2026-07-27T15:59:42 - `29cf17b6-04b4-4b01-9444-64f1bfdbdaa5.jsonl`
